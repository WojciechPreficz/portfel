import {
  createTransaction,
  clearPortfolio,
  getHistory,
  getInstruments,
  getPortfolio,
  importTransactions,
  refreshQuotes,
  type TransactionPayload,
} from '../api';

export type TransactionInput = Omit<TransactionPayload, 'portfolio_id' | 'type'>;

export const portfolioService = {
  loadSummary(portfolioId: number | null) {
    return getPortfolio(portfolioId);
  },

  loadHistory(portfolioId: number | null) {
    return getHistory(portfolioId);
  },

  loadInstruments() {
    return getInstruments();
  },

  buy(portfolioId: number, payload: TransactionInput) {
    return createTransaction({ ...payload, portfolio_id: portfolioId, type: 'BUY' });
  },

  sell(portfolioId: number, payload: TransactionInput) {
    return createTransaction({ ...payload, portfolio_id: portfolioId, type: 'SELL' });
  },

  refreshQuotes(instrumentIds?: number[]) {
    return refreshQuotes(instrumentIds);
  },

  clearPortfolio(portfolioId: number) {
    return clearPortfolio(portfolioId);
  },

  importPurchases(file: File, source: 'xstation5' | 'bossa', portfolioId: number) {
    return importTransactions(file, source, portfolioId);
  },
};
