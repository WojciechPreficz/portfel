import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { setImmediate } from 'node:timers/promises';
import test from 'node:test';
import ts from 'typescript';
import { computed, effectScope, nextTick, ref } from 'vue';

// Run the actual TypeScript modules using the existing compiler, with no
// additional test framework or build artifacts.
const moduleUrls = new Map();
function typescriptModule(url) {
  if (moduleUrls.has(url.href)) return moduleUrls.get(url.href);
  const { outputText } = ts.transpileModule(readFileSync(url, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
  });
  const source = outputText.replace(/from (['"])([^'"]+)\1/g, (_match, _quote, specifier) => {
    const dependency = specifier.startsWith('.')
      ? typescriptModule(new URL(`${specifier}.ts`, url))
      : import.meta.resolve(specifier);
    return `from ${JSON.stringify(dependency)}`;
  });
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
  moduleUrls.set(url.href, moduleUrl);
  return moduleUrl;
}
const { usePortfolio } = await import(
  typescriptModule(new URL('../src/composables/usePortfolio.ts', import.meta.url))
);

const summary = (value) => ({ value_pln: value, positions: [], as_of: '2026-10-10' });
const history = (value) => [{ date: '2026-10-10', value_pln: value }];

async function setup(t) {
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = (path) =>
    new Promise((resolve, reject) => {
      requests.push({ path, resolve, reject });
    });
  const portfolioId = ref(1);
  const enabled = ref(false);
  const scope = effectScope();
  const state = scope.run(() =>
    usePortfolio(
      computed(() => portfolioId.value),
      computed(() => enabled.value),
    ),
  );
  t.after(async () => {
    enabled.value = false;
    await nextTick();
    scope.stop();
    globalThis.fetch = originalFetch;
  });
  const take = (path) => {
    const index = requests.findIndex((request) => request.path === path);
    assert.notEqual(index, -1, `Missing request: ${path}`);
    return requests.splice(index, 1)[0];
  };
  const reply = (path, body) => take(path).resolve(Response.json(body));
  enabled.value = true;
  await nextTick();
  return { state, portfolioId, enabled, requests, take, reply };
}

test('summary appears while history and catalog are still pending', async (t) => {
  const { state, reply } = await setup(t);
  reply('/api/portfolio/summary?portfolio_id=1', summary(100));
  await setImmediate();
  assert.equal(state.summary.value.value_pln, 100);
  assert.equal(state.loading.value, false);
  assert.equal(state.historyLoading.value, true);
  assert.deepEqual(state.historyValues.value, []);
  reply('/api/portfolio/history?portfolio_id=1', history(100));
  reply('/api/instruments', []);
  await setImmediate();
  assert.deepEqual(state.historyValues.value, [100]);
  assert.equal(state.historyLoading.value, false);
});

test(
  'refresh completes after summary, and a history failure keeps the previous chart',
  { timeout: 2000 },
  async (t) => {
    const { state, reply, take } = await setup(t);
    reply('/api/portfolio/summary?portfolio_id=1', summary(100));
    reply('/api/portfolio/history?portfolio_id=1', history(100));
    reply('/api/instruments', []);
    await setImmediate();
    const refresh = state.updateQuotes();
    reply('/api/quotes/refresh', { errors: [] });
    await setImmediate();
    reply('/api/portfolio/summary?portfolio_id=1', summary(200));
    await refresh;
    assert.equal(state.summary.value.value_pln, 200);
    assert.equal(state.refreshing.value, false);
    assert.equal(state.notice.value, 'Notowania zostały odświeżone.');
    assert.equal(state.historyLoading.value, true);
    assert.deepEqual(state.historyValues.value, [100]);
    take('/api/portfolio/history?portfolio_id=1').reject(new Error('offline'));
    reply('/api/instruments', []);
    await setImmediate();
    assert.match(state.historyError.value, /Nie udało się pobrać historii portfela/);
    assert.equal(state.error.value, '');
    assert.equal(state.historyLoading.value, false);
    assert.deepEqual(state.historyValues.value, [100]);
  },
);

test('responses from the previous portfolio cannot overwrite the current one', async (t) => {
  const { state, portfolioId, reply, take } = await setup(t);
  const oldSummary = take('/api/portfolio/summary?portfolio_id=1');
  const oldHistory = take('/api/portfolio/history?portfolio_id=1');
  const oldCatalog = take('/api/instruments');
  portfolioId.value = 2;
  await nextTick();
  reply('/api/portfolio/summary?portfolio_id=2', summary(200));
  reply('/api/instruments', [{ id: 2 }]);
  await setImmediate();
  oldSummary.resolve(Response.json(summary(100)));
  oldHistory.resolve(Response.json(history(100)));
  oldCatalog.reject(new Error('old catalog failed'));
  await setImmediate();
  assert.equal(state.summary.value.value_pln, 200);
  assert.equal(state.historyLoading.value, true);
  assert.deepEqual(state.historyValues.value, []);
  assert.deepEqual(state.instruments.value, [{ id: 2 }]);
  assert.equal(state.error.value, '');
  reply('/api/portfolio/history?portfolio_id=2', history(200));
  await setImmediate();
  assert.deepEqual(state.historyValues.value, [200]);
});

test(
  'a newer reload wins over older requests for the same portfolio',
  { timeout: 2000 },
  async (t) => {
    const { state, take, reply } = await setup(t);
    const oldSummary = take('/api/portfolio/summary?portfolio_id=1');
    const oldHistory = take('/api/portfolio/history?portfolio_id=1');
    const oldCatalog = take('/api/instruments');
    const reload = state.loadData(false);
    reply('/api/portfolio/summary?portfolio_id=1', summary(300));
    assert.equal(await reload, true);
    reply('/api/portfolio/history?portfolio_id=1', history(300));
    reply('/api/instruments', []);
    await setImmediate();
    oldSummary.resolve(Response.json(summary(100)));
    oldHistory.reject(new Error('old history failed'));
    oldCatalog.resolve(Response.json([{ id: 1 }]));
    await setImmediate();
    assert.equal(state.summary.value.value_pln, 300);
    assert.deepEqual(state.historyValues.value, [300]);
    assert.equal(state.historyError.value, '');
    assert.equal(state.loading.value, false);
    assert.equal(state.historyLoading.value, false);
  },
);

test('logging out invalidates pending summary, history and catalog responses', async (t) => {
  const { state, enabled, reply } = await setup(t);
  enabled.value = false;
  await nextTick();
  reply('/api/portfolio/summary?portfolio_id=1', summary(100));
  reply('/api/portfolio/history?portfolio_id=1', history(100));
  reply('/api/instruments', [{ id: 1 }]);
  await setImmediate();
  assert.equal(state.summary.value, null);
  assert.deepEqual(state.historyValues.value, []);
  assert.deepEqual(state.instruments.value, []);
  assert.equal(state.historyLoading.value, false);
});

test(
  'history and catalog errors do not hide a successful summary',
  { timeout: 2000 },
  async (t) => {
    const { state, take, reply } = await setup(t);
    take('/api/portfolio/history?portfolio_id=1').reject(new Error('history unavailable'));
    take('/api/instruments').reject(new Error('catalog unavailable'));
    reply('/api/portfolio/summary?portfolio_id=1', summary(100));
    await setImmediate();
    assert.equal(state.summary.value.value_pln, 100);
    assert.equal(state.loading.value, false);
    assert.match(state.historyError.value, /history unavailable/);
    assert.match(state.error.value, /catalog unavailable/);
  },
);
