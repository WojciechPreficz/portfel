<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart, PieChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import {
  createTransaction,
  getHistory,
  getInstruments,
  getPortfolio,
  refreshQuotes,
  type Instrument,
  type PortfolioSummary,
} from "./api";

use([CanvasRenderer, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent]);

const summary = ref<PortfolioSummary | null>(null);
const instruments = ref<Instrument[]>([]);
const loading = ref(true);
const refreshing = ref(false);
const error = ref("");
const notice = ref("");
const activeView = ref<"overview" | "holdings">("overview");
const showTransactionForm = ref(false);
const historyDates = ref<string[]>([]);
const historyValues = ref<number[]>([]);

const form = ref({ marketType: "", instrumentId: "", quantity: "", price: "", date: new Date().toISOString().slice(0, 10), commission: "0" });

const marketTypeOptions = [
  { value: "stock_pl", label: "Spółka z polskiego rynku akcji" },
  { value: "etf", label: "ETF" },
];

const filteredInstruments = computed(() => instruments.value.filter((instrument) => instrument.type === form.value.marketType));

const numberFormat = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 2 });
const currencyFormat = new Intl.NumberFormat("pl-PL", { style: "currency", currency: "PLN", maximumFractionDigits: 0 });
const percentFormat = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 2, signDisplay: "always" });

const formatCurrency = (value: number | null | undefined) => (value == null ? "--" : currencyFormat.format(value));
const formatNumber = (value: number | null | undefined) => (value == null ? "--" : numberFormat.format(value));
const formatPercent = (value: number | null | undefined) => (value == null ? "--" : `${percentFormat.format(value)}%`);
const isPositive = (value: number | null | undefined) => (value ?? 0) >= 0;

const chartOption = computed(() => ({
  animationDuration: 700,
  grid: { left: 8, right: 12, top: 18, bottom: 8, containLabel: true },
  tooltip: { trigger: "axis", valueFormatter: (value: number) => formatCurrency(value) },
  xAxis: { type: "category", boundaryGap: false, data: historyDates.value, axisLabel: { color: "#7b817b", formatter: (value: string) => value.slice(5) }, axisLine: { lineStyle: { color: "#d8ddd6" } } },
  yAxis: { type: "value", scale: true, axisLabel: { color: "#7b817b", formatter: (value: number) => `${Math.round(value / 1000)}k` }, splitLine: { lineStyle: { color: "#e7ebe5" } } },
  series: [{ type: "line", smooth: true, symbol: "none", data: historyValues.value, lineStyle: { width: 3, color: "#c2ec62" }, areaStyle: { color: "rgba(194, 236, 98, .18)" } }],
}));

const allocationOption = computed(() => ({
  tooltip: { trigger: "item", formatter: "{b}: {d}%" },
  legend: { bottom: 0, left: "center", textStyle: { color: "#596158" } },
  series: [{ type: "pie", radius: ["52%", "76%"], center: ["50%", "42%"], avoidLabelOverlap: true, label: { show: false }, data: (summary.value?.positions ?? []).map((position) => ({ name: position.instrument.ticker, value: position.market_value_pln })), itemStyle: { borderColor: "#fbfcf8", borderWidth: 3 } }],
  color: ["#17201b", "#b9e85d", "#ee806d", "#8cb7a4", "#d8ae57"],
}));

const loadData = async () => {
  loading.value = true;
  error.value = "";
  try {
    const [portfolio, history, catalog] = await Promise.all([getPortfolio(), getHistory(), getInstruments()]);
    summary.value = portfolio;
    instruments.value = catalog;
    historyDates.value = history.map((point) => point.date);
    historyValues.value = history.map((point) => point.value_pln);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "Nie udało się pobrać danych.";
  } finally {
    loading.value = false;
  }
};

const submitTransaction = async () => {
  if (!form.value.marketType || !form.value.instrumentId || !form.value.quantity || !form.value.price || !form.value.date) return;
  try {
    await createTransaction({ instrument_id: Number(form.value.instrumentId), quantity: Number(form.value.quantity), price: Number(form.value.price), date: form.value.date, commission: Number(form.value.commission || 0), type: "BUY" });
    showTransactionForm.value = false;
    notice.value = "Zakup zapisany. Odśwież ceny, aby zobaczyć bieżącą wycenę.";
    form.value = { marketType: "", instrumentId: "", quantity: "", price: "", date: new Date().toISOString().slice(0, 10), commission: "0" };
    await loadData();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "Nie udało się zapisać transakcji.";
  }
};

const resetMarketSelection = () => {
  form.value.instrumentId = "";
  if (!form.value.marketType) return;
  const selectedStillVisible = filteredInstruments.value.some((instrument) => String(instrument.id) === form.value.instrumentId);
  if (!selectedStillVisible) {
    form.value.instrumentId = "";
  }
};

const updateQuotes = async () => {
  refreshing.value = true;
  error.value = "";
  notice.value = "Pobieram najnowsze notowania...";
  try {
    const result = await refreshQuotes();
    notice.value = result.errors.length ? `Odświeżono częściowo. Błędy: ${result.errors.join("; ")}` : "Notowania zostały odświeżone.";
    await loadData();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "Nie udało się odświeżyć notowań.";
    notice.value = "";
  } finally {
    refreshing.value = false;
  }
};

onMounted(loadData);
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand"><span class="brand-mark">P</span><span>portfel</span></div>
      <div class="sidebar-label">Widok</div>
      <nav class="nav-list">
        <button :class="{ active: activeView === 'overview' }" @click="activeView = 'overview'">Przegląd <span>01</span></button>
        <button :class="{ active: activeView === 'holdings' }" @click="activeView = 'holdings'">Pozycje <span>{{ summary?.positions.length ?? 0 }}</span></button>
      </nav>
      <div class="sidebar-bottom"><div class="status-dot"></div><span>Portfel lokalny</span><small>PLN · bez logowania</small></div>
    </aside>

    <main class="main-content">
      <header class="topbar">
        <div><p class="eyebrow">PONIEDZIAŁEK, 21 WRZEŚNIA 2026</p><h1>{{ activeView === 'overview' ? 'Dzień dobry, Wojciech' : 'Twoje pozycje' }}</h1></div>
        <div class="top-actions"><button class="button button-quiet" :disabled="refreshing" @click="updateQuotes">{{ refreshing ? 'Odświeżam...' : 'Odśwież notowania' }}</button><button class="button button-primary" @click="showTransactionForm = true">+ Dodaj zakup</button></div>
      </header>

      <div v-if="error" class="alert alert-error">{{ error }} <button @click="loadData">Spróbuj ponownie</button></div>
      <div v-if="notice" class="alert alert-notice">{{ notice }}</div>

      <section v-if="activeView === 'overview'" class="content-grid">
        <div class="hero-metric panel panel-dark"><div><p class="panel-kicker">WARTOŚĆ PORTFELA</p><div v-if="loading" class="skeleton skeleton-xl"></div><strong v-else>{{ formatCurrency(summary?.value_pln) }}</strong><p class="metric-sub">{{ summary?.as_of ? `Wycena z ${summary.as_of}` : 'Brak aktualnych notowań' }}</p></div><div class="hero-orbit"><span></span><span></span><span></span></div></div>
        <div class="metric-card panel"><p class="panel-kicker">ZMIANA 1D</p><div v-if="loading" class="skeleton skeleton-lg"></div><strong v-else :class="isPositive(summary?.change_1d_pln) ? 'positive' : 'negative'">{{ formatCurrency(summary?.change_1d_pln) }}</strong><p :class="['metric-sub', isPositive(summary?.change_1d_pct) ? 'positive' : 'negative']">{{ formatPercent(summary?.change_1d_pct) }}</p></div>
        <div class="metric-card panel"><p class="panel-kicker">P/L NIEZREALIZOWANY</p><div v-if="loading" class="skeleton skeleton-lg"></div><strong v-else :class="isPositive(summary?.pnl_pln) ? 'positive' : 'negative'">{{ formatCurrency(summary?.pnl_pln) }}</strong><p :class="['metric-sub', isPositive(summary?.pnl_pct) ? 'positive' : 'negative']">{{ formatPercent(summary?.pnl_pct) }} od zakupu</p></div>
        <section class="panel chart-panel"><div class="section-heading"><div><p class="panel-kicker">WARTOŚĆ W CZASIE</p><h2>Jak rośnie kapitał</h2></div><span class="heading-meta">PLN</span></div><div v-if="!historyValues.length && !loading" class="empty-chart">Historia pojawi się po dodaniu transakcji i pobraniu cen.</div><VChart v-else class="main-chart" :option="chartOption" autoresize /></section>
        <section class="panel allocation-panel"><div class="section-heading"><div><p class="panel-kicker">ALOKACJA</p><h2>Rozkład portfela</h2></div></div><div v-if="!summary?.positions.length && !loading" class="empty-allocation">Brak pozycji</div><VChart v-else class="allocation-chart" :option="allocationOption" autoresize /></section>
        <section class="panel positions-panel"><div class="section-heading"><div><p class="panel-kicker">NAJWIĘKSZE POZYCJE</p><h2>Co masz w portfelu</h2></div><button class="text-button" @click="activeView = 'holdings'">Zobacz wszystkie →</button></div><div v-if="!summary?.positions.length && !loading" class="empty-state"><div class="empty-icon">+</div><h3>Portfel czeka na pierwszy zakup</h3><p>Dodaj transakcję, aby zacząć śledzić wartość i wynik.</p><button class="button button-primary" @click="showTransactionForm = true">Dodaj pierwszy zakup</button></div><div v-else class="position-list"><div v-for="position in summary?.positions.slice(0, 4)" :key="position.instrument.id" class="position-row"><div class="ticker-badge">{{ position.instrument.ticker.slice(0, 3) }}</div><div class="position-name"><strong>{{ position.instrument.ticker }}</strong><span>{{ position.instrument.name }}</span></div><div class="position-weight"><div><span :style="{ width: `${Math.min(position.weight_pct ?? 0, 100)}%` }"></span></div><small>{{ formatPercent(position.weight_pct) }}</small></div><div class="position-value"><strong>{{ formatCurrency(position.market_value_pln) }}</strong><span :class="isPositive(position.pnl_pln) ? 'positive' : 'negative'">{{ formatCurrency(position.pnl_pln) }}</span></div></div></div></section>
      </section>

      <section v-else class="panel holdings-view"><div class="section-heading"><div><p class="panel-kicker">PORTFEL / {{ summary?.positions.length ?? 0 }} POZYCJI</p><h2>Wszystkie pozycje</h2></div><span class="total-caption">Łącznie {{ formatCurrency(summary?.value_pln) }}</span></div><div v-if="!summary?.positions.length && !loading" class="empty-state"><div class="empty-icon">+</div><h3>Nie ma jeszcze żadnych pozycji</h3><p>Pierwszy zakup pojawi się tutaj wraz z wyceną.</p><button class="button button-primary" @click="showTransactionForm = true">Dodaj zakup</button></div><div v-else class="table-wrap"><table><thead><tr><th>Instrument</th><th>Ilość</th><th>Ostatnia cena</th><th>Wartość PLN</th><th>Udział</th><th>Wynik</th></tr></thead><tbody><tr v-for="position in summary?.positions" :key="position.instrument.id"><td><div class="table-instrument"><div class="ticker-badge">{{ position.instrument.ticker.slice(0, 3) }}</div><div><strong>{{ position.instrument.ticker }}</strong><small>{{ position.instrument.name }}</small></div></div></td><td>{{ formatNumber(position.quantity) }} {{ position.instrument.unit === 'gram' ? 'g' : 'szt.' }}</td><td>{{ formatNumber(position.price) }} {{ position.instrument.currency }}</td><td><strong>{{ formatCurrency(position.market_value_pln) }}</strong></td><td>{{ formatPercent(position.weight_pct) }}</td><td :class="isPositive(position.pnl_pln) ? 'positive' : 'negative'">{{ formatCurrency(position.pnl_pln) }}<small>{{ formatPercent(position.pnl_pct) }}</small></td></tr></tbody></table></div></section>
      <footer><span>Portfel prywatny · dane lokalne</span><span>Ostatnia aktualizacja: {{ summary?.as_of ?? 'brak danych' }}</span></footer>
    </main>

    <div v-if="showTransactionForm" class="modal-backdrop" @click.self="showTransactionForm = false"><section class="modal"><div class="modal-heading"><div><p class="panel-kicker">NOWA TRANSAKCJA</p><h2>Dodaj zakup</h2></div><button class="close-button" aria-label="Zamknij" @click="showTransactionForm = false">×</button></div><form @submit.prevent="submitTransaction">
          <label>Typ instrumentu
            <select v-model="form.marketType" @change="resetMarketSelection" required>
              <option value="" disabled>Najpierw wybierz typ</option>
              <option v-for="option in marketTypeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>

          <label v-if="form.marketType">Instrument
            <select v-model="form.instrumentId" required>
              <option value="" disabled>Wybierz {{ form.marketType === 'stock_pl' ? 'spółkę' : 'ETF' }}</option>
              <option v-for="instrument in filteredInstruments" :key="instrument.id" :value="instrument.id">{{ instrument.ticker }} · {{ instrument.name }}</option>
            </select>
          </label>

          <div class="form-row"><label>Ilość<input v-model="form.quantity" type="number" min="0.00000001" step="any" placeholder="np. 10" required /></label><label>Cena za sztukę<input v-model="form.price" type="number" min="0" step="any" placeholder="np. 125.50" required /></label></div><div class="form-row"><label>Data zakupu<input v-model="form.date" type="date" required /></label><label>Prowizja<input v-model="form.commission" type="number" min="0" step="any" placeholder="0" /></label></div><div class="modal-actions"><button type="button" class="button button-quiet" @click="showTransactionForm = false">Anuluj</button><button type="submit" class="button button-primary">Zapisz zakup</button></div></form></section></div>
  </div>
</template>