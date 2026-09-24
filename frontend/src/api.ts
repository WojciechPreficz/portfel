export type Instrument = {
  id: number;
  ticker: string;
  isin: string | null;
  name: string;
  type: string;
  currency: string;
  provider: string;
  symbol: string;
  unit: string;
};

export type Position = {
  instrument: Instrument;
  quantity: number;
  avg_cost: number;
  cost_pln: number;
  price: number | null;
  price_date: string | null;
  market_value_pln: number;
  pnl_pln: number;
  pnl_pct: number | null;
  change_1d_pln: number;
  change_1d_pct: number | null;
  weight_pct: number | null;
};

export type PortfolioSummary = {
  value_pln: number;
  value_prev_pln: number;
  change_1d_pln: number;
  change_1d_pct: number | null;
  cost_pln: number;
  pnl_pln: number;
  pnl_pct: number | null;
  xirr_pct: number | null;
  as_of: string | null;
  positions: Position[];
};

export type HistoryPoint = { date: string; value_pln: number };

export type TransactionPayload = {
  instrument_id: number;
  quantity: number;
  price: number;
  date: string;
  commission: number;
  type: 'BUY' | 'SELL';
};

const api = async <T>(path: string, options?: RequestInit): Promise<T> => {
  const response = await fetch(path, {
    headers: options?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Błąd API (${response.status})`);
  }
  return response.json() as Promise<T>;
};

export const getPortfolio = () => api<PortfolioSummary>('/api/portfolio/summary');
export const getHistory = () => api<HistoryPoint[]>('/api/portfolio/history');
export const clearPortfolio = () =>
  api<{
    deleted_instruments: number;
    deleted_transactions: number;
    deleted_prices: number;
  }>('/api/portfolio/holdings', { method: 'DELETE' });
export const getInstruments = (query = '', type?: string) => {
  const params = new URLSearchParams();
  if (query) params.set('q', query);
  if (type) params.set('type', type);
  const suffix = params.size ? `?${params.toString()}` : '';
  return api<Instrument[]>(`/api/instruments${suffix}`);
};

export const createTransaction = (payload: TransactionPayload) =>
  api('/api/transactions', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const importTransactions = (file: File, source: 'xstation5' | 'bossa') => {
  const body = new FormData();
  body.append('file', file);
  body.append('source', source);
  return api<{ imported: number; deposits: number; skipped: number; errors: string[] }>('/api/transactions/import', {
    method: 'POST',
    body,
  });
};

export const refreshQuotes = () =>
  api<{ errors: string[] }>('/api/quotes/refresh', { method: 'POST' });
