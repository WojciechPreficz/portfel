import { computed, ref } from "vue";
import type { Instrument, PortfolioSummary, Position } from "../api";
import { formatNumber } from "../utils/formatters";
import { portfolioService } from "../services/portfolioService";

export type TransactionForm = {
  marketType: string;
  instrumentId: string;
  quantity: string;
  price: string;
  date: string;
  commission: string;
};

const today = () => new Date().toISOString().slice(0, 10);
const emptyTransactionForm = (): TransactionForm => ({
  marketType: "",
  instrumentId: "",
  quantity: "",
  price: "",
  date: today(),
  commission: "0",
});

export const usePortfolio = () => {
  const summary = ref<PortfolioSummary | null>(null);
  const instruments = ref<Instrument[]>([]);
  const loading = ref(true);
  const refreshing = ref(false);
  const error = ref("");
  const notice = ref("");
  const historyDates = ref<string[]>([]);
  const historyValues = ref<number[]>([]);
  const form = ref(emptyTransactionForm());
  const positionToRemove = ref<Position | null>(null);
  const removalQuantity = ref("");
  const removalDate = ref(today());

  const filteredInstruments = computed(() =>
    instruments.value.filter((instrument) => instrument.type === form.value.marketType),
  );

  const loadData = async () => {
    loading.value = true;
    error.value = "";
    try {
      const [portfolio, history, catalog] = await portfolioService.loadSnapshot();
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
    if (!form.value.marketType || !form.value.instrumentId || !form.value.quantity || !form.value.price || !form.value.date) return false;
    try {
      await portfolioService.buy({
        instrument_id: Number(form.value.instrumentId),
        quantity: Number(form.value.quantity),
        price: Number(form.value.price),
        date: form.value.date,
        commission: Number(form.value.commission || 0),
      });
      notice.value = "Zakup zapisany. Odśwież ceny, aby zobaczyć bieżącą wycenę.";
      form.value = emptyTransactionForm();
      await loadData();
      return true;
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : "Nie udało się zapisać transakcji.";
      return false;
    }
  };

  const openRemovalForm = (position: Position, removeAll = false) => {
    positionToRemove.value = position;
    const quantity = Number(position.quantity);
    removalQuantity.value = removeAll
      ? (Number.isInteger(quantity) ? String(quantity) : String(position.quantity))
      : "";
    removalDate.value = today();
  };

  const closeRemovalForm = () => {
    positionToRemove.value = null;
    removalQuantity.value = "";
  };

  const removePosition = async () => {
    const position = positionToRemove.value;
    const quantity = Number(removalQuantity.value);
    if (!position || !quantity || quantity <= 0 || quantity > position.quantity || !removalDate.value) return;
    try {
      await portfolioService.sell({
        instrument_id: position.instrument.id,
        quantity,
        price: position.price ?? 0,
        date: removalDate.value,
        commission: 0,
      });
      closeRemovalForm();
      notice.value = quantity === position.quantity
        ? `Usunięto pozycję ${position.instrument.ticker}.`
        : `Usunięto ${formatNumber(quantity)} ${position.instrument.ticker}.`;
      await loadData();
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : "Nie udało się usunąć pozycji.";
    }
  };

  const resetMarketSelection = () => {
    form.value.instrumentId = "";
  };

  const updateQuotes = async () => {
    refreshing.value = true;
    error.value = "";
    notice.value = "Pobieram najnowsze notowania...";
    try {
      const result = await portfolioService.refreshQuotes();
      notice.value = result.errors.length
        ? `Odświeżono częściowo. Błędy: ${result.errors.join("; ")}`
        : "Notowania zostały odświeżone.";
      await loadData();
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : "Nie udało się odświeżyć notowań.";
      notice.value = "";
    } finally {
      refreshing.value = false;
    }
  };

  const importPurchases = async (file: File) => {
    error.value = "";
    notice.value = "Importuję zakupy...";
    try {
      const result = await portfolioService.importPurchases(file);
      if (result.errors.length) {
        error.value = result.errors.join("; ");
        notice.value = "Import anulowany. Popraw wskazane wiersze i spróbuj ponownie.";
        return;
      }
      notice.value = `Zaimportowano ${result.imported} zakupów.`;
      await loadData();
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : "Nie udało się zaimportować zakupów.";
      notice.value = "";
    }
  };

  return {
    summary,
    instruments,
    loading,
    refreshing,
    error,
    notice,
    historyDates,
    historyValues,
    form,
    filteredInstruments,
    positionToRemove,
    removalQuantity,
    removalDate,
    loadData,
    submitTransaction,
    openRemovalForm,
    closeRemovalForm,
    removePosition,
    resetMarketSelection,
    updateQuotes,
    importPurchases,
  };
};
