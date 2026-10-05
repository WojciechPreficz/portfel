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

export type Portfolio = { id: number; name: string };

export type Position = {
  instrument: Instrument;
  quantity: number;
  avg_cost: number | null;
  cost_pln: number | null;
  price: number | null;
  price_date: string | null;
  market_value_pln: number | null;
  pnl_pln: number | null;
  pnl_pct: number | null;
  change_1d_pln: number | null;
  change_1d_pct: number | null;
  weight_pct: number | null;
};

export type PortfolioSummary = {
  value_pln: number | null;
  value_prev_pln: number | null;
  change_1d_pln: number | null;
  change_1d_pct: number | null;
  cost_pln: number | null;
  pnl_pln: number | null;
  pnl_pct: number | null;
  xirr_pct: number | null;
  as_of: string | null;
  positions: Position[];
};

export type HistoryPoint = { date: string; value_pln: number };

export type TransactionPayload = {
  portfolio_id: number;
  instrument_id: number;
  quantity: number;
  price: number;
  purchase_price_pln?: number;
  currency?: string;
  date: string;
  commission: number;
  type: 'BUY' | 'SELL';
};

export type GoldQuote = {
  spot_usd_oz: number;
  spot_date: string;
  usd_pln: number;
  fx_date: string;
  price_pln_g: number;
};

export type ApiErrorHandler = {
  onUnauthorized?: () => void;
  onRateLimited?: () => void;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

let apiErrorHandler: ApiErrorHandler = {};

export const setApiErrorHandler = (handler: ApiErrorHandler) => {
  apiErrorHandler = handler;
};

const api = async <T>(path: string, options?: RequestInit): Promise<T> => {
  const response = await fetch(path, {
    headers: options?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...options,
    credentials: 'include',
  });
  if (response.status === 401 && !path.startsWith('/api/auth/')) {
    apiErrorHandler.onUnauthorized?.();
  }
  if (response.status === 429) {
    apiErrorHandler.onRateLimited?.();
  }
  if (!response.ok) {
    const body = await response.text();
    let message = body || `Błąd API (${response.status})`;
    try {
      const parsed: unknown = JSON.parse(body);
      if (
        typeof parsed === 'object' &&
        parsed !== null &&
        'detail' in parsed &&
        typeof parsed.detail === 'string'
      ) {
        message = parsed.detail;
      }
    } catch {
      // Non-JSON error responses are displayed as-is.
    }
    if (response.status === 429) {
      message = 'Zbyt wiele prób. Spróbuj ponownie później.';
    }
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
};

export const getAuthStatus = () => api<{ authenticated: boolean }>('/api/auth/me');
export const login = (password: string) =>
  api<{ authenticated: boolean }>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ password }),
  });
export const logout = () => api<{ authenticated: boolean }>('/api/auth/logout', { method: 'POST' });

const portfolioQuery = (portfolioId: number | null) =>
  portfolioId === null ? '' : `?portfolio_id=${portfolioId}`;

export const getPortfolios = () => api<Portfolio[]>('/api/portfolios');
export const createPortfolio = (name: string) =>
  api<Portfolio>('/api/portfolios', { method: 'POST', body: JSON.stringify({ name }) });
export const renamePortfolio = (id: number, name: string) =>
  api<Portfolio>(`/api/portfolios/${id}`, { method: 'PATCH', body: JSON.stringify({ name }) });
export const deletePortfolio = (id: number) =>
  api<{ deleted_portfolio: number }>(`/api/portfolios/${id}`, { method: 'DELETE' });
export const getPortfolio = (portfolioId: number | null) =>
  api<PortfolioSummary>(`/api/portfolio/summary${portfolioQuery(portfolioId)}`);
export const getHistory = (portfolioId: number | null) =>
  api<HistoryPoint[]>(`/api/portfolio/history${portfolioQuery(portfolioId)}`);
export const clearPortfolio = (portfolioId: number) =>
  api<{
    deleted_instruments: number;
    deleted_transactions: number;
    deleted_prices: number;
  }>(`/api/portfolio/holdings?portfolio_id=${portfolioId}`, { method: 'DELETE' });
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

export const importTransactions = (
  file: File,
  source: 'xstation5' | 'bossa',
  portfolioId: number,
) => {
  const body = new FormData();
  body.append('file', file);
  body.append('source', source);
  body.append('portfolio_id', String(portfolioId));
  return api<{
    imported: number;
    deposits: number;
    skipped: number;
    errors: string[];
    instrument_ids: number[];
  }>('/api/transactions/import', {
    method: 'POST',
    body,
  });
};

export const refreshQuotes = (instrumentIds?: number[]) => {
  const query = new URLSearchParams();
  instrumentIds?.forEach((id) => query.append('instrument_ids', String(id)));
  const suffix = query.size ? `?${query.toString()}` : '';
  return api<{ errors: string[] }>(`/api/quotes/refresh${suffix}`, { method: 'POST' });
};
export const getGoldQuote = () => api<GoldQuote>('/api/quotes/gold');
