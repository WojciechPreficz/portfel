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

export type TransactionInput = Omit<TransactionPayload, 'type'>;

export const portfolioService = {
  loadSnapshot() {
    return Promise.all([getPortfolio(), getHistory(), getInstruments()]);
  },

  buy(payload: TransactionInput) {
    return createTransaction({ ...payload, type: 'BUY' });
  },

  sell(payload: TransactionInput) {
    return createTransaction({ ...payload, type: 'SELL' });
  },

  refreshQuotes() {
    return refreshQuotes();
  },

  clearPortfolio() {
    return clearPortfolio();
  },

  importPurchases(file: File) {
    return importTransactions(file);
  },
};
