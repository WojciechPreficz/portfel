import { computed, ref, watch, type ComputedRef } from 'vue';
import type { Instrument, PortfolioSummary, Position } from '../api';
import { formatNumber } from '../utils/formatters';
import { portfolioService } from '../services/portfolioService';

export type TransactionForm = {
  marketType: string;
  instrumentId: string;
  quantity: string;
  price: string;
  date: string;
  commission: string;
  goldWeightGrams: string;
  goldOunces: string;
  goldPurity: string;
  goldManualWeight: boolean;
};

const today = () => new Date().toISOString().slice(0, 10);
const emptyTransactionForm = (): TransactionForm => ({
  marketType: '',
  instrumentId: '',
  quantity: '',
  price: '',
  date: today(),
  commission: '0',
  goldWeightGrams: '',
  goldOunces: '1',
  goldPurity: '9999',
  goldManualWeight: false,
});

const TROY_OUNCE_GRAMS = 31.1034768;

export const usePortfolio = (
  portfolioId: ComputedRef<number | null>,
  enabled: ComputedRef<boolean>,
) => {
  const summary = ref<PortfolioSummary | null>(null);
  const instruments = ref<Instrument[]>([]);
  const loading = ref(true);
  const removingAll = ref(false);
  const refreshing = ref(false);
  const error = ref('');
  const notice = ref('');
  const historyDates = ref<string[]>([]);
  const historyValues = ref<number[]>([]);
  const historyLoading = ref(false);
  const historyError = ref('');
  let loadVersion = 0;
  let displayedPortfolioId: number | null | undefined;
  const form = ref(emptyTransactionForm());
  const positionToRemove = ref<Position | null>(null);
  const removalQuantity = ref('');
  const removalDate = ref(today());

  const filteredInstruments = computed(() =>
    instruments.value.filter((instrument) => instrument.type === form.value.marketType),
  );

  const isCurrentLoad = (version: number, selectedPortfolioId: number | null) =>
    version === loadVersion && enabled.value && portfolioId.value === selectedPortfolioId;

  const loadHistory = async (version: number, selectedPortfolioId: number | null) => {
    historyLoading.value = true;
    historyError.value = '';
    try {
      const history = await portfolioService.loadHistory(selectedPortfolioId);
      if (!isCurrentLoad(version, selectedPortfolioId)) return;
      historyDates.value = history.map((point) => point.date);
      historyValues.value = history.map((point) => point.value_pln);
    } catch (reason) {
      if (!isCurrentLoad(version, selectedPortfolioId)) return;
      const detail = reason instanceof Error ? ` ${reason.message}` : '';
      historyError.value = `Nie udało się pobrać historii portfela.${detail}`;
    } finally {
      if (isCurrentLoad(version, selectedPortfolioId)) historyLoading.value = false;
    }
  };

  const loadInstruments = async (version: number, selectedPortfolioId: number | null) => {
    try {
      const catalog = await portfolioService.loadInstruments();
      if (isCurrentLoad(version, selectedPortfolioId)) instruments.value = catalog;
    } catch (reason) {
      if (!isCurrentLoad(version, selectedPortfolioId)) return;
      const detail = reason instanceof Error ? ` ${reason.message}` : '';
      error.value = `Nie udało się pobrać katalogu instrumentów.${detail}`;
    }
  };

  const loadData = async (showLoading = true) => {
    if (!enabled.value) return false;
    const version = ++loadVersion;
    const selectedPortfolioId = portfolioId.value;
    if (displayedPortfolioId !== selectedPortfolioId) {
      summary.value = null;
      historyDates.value = [];
      historyValues.value = [];
      displayedPortfolioId = selectedPortfolioId;
    }
    if (showLoading || !summary.value) loading.value = true;
    error.value = '';
    void loadHistory(version, selectedPortfolioId);
    void loadInstruments(version, selectedPortfolioId);
    try {
      const portfolio = await portfolioService.loadSummary(selectedPortfolioId);
      if (!isCurrentLoad(version, selectedPortfolioId)) return false;
      summary.value = portfolio;
      return true;
    } catch (reason) {
      if (!isCurrentLoad(version, selectedPortfolioId)) return false;
      error.value = reason instanceof Error ? reason.message : 'Nie udało się pobrać danych.';
      return false;
    } finally {
      if (isCurrentLoad(version, selectedPortfolioId)) loading.value = false;
    }
  };

  const submitTransaction = async (onSaved?: () => void) => {
    const isGold = form.value.marketType === 'gold';
    const goldInstrument = isGold
      ? filteredInstruments.value.find(
          (instrument) => instrument.ticker === `XAU-${form.value.goldPurity}`,
        )
      : undefined;
    const quantity = isGold
      ? form.value.goldManualWeight
        ? Number(form.value.goldWeightGrams)
        : Number(form.value.goldOunces) * TROY_OUNCE_GRAMS
      : Number(form.value.quantity);
    const purchasePrice = Number(form.value.price);
    if (
      !form.value.marketType ||
      portfolioId.value === null ||
      (!isGold && !form.value.instrumentId) ||
      !quantity ||
      quantity <= 0 ||
      !purchasePrice ||
      purchasePrice <= 0 ||
      !form.value.date
    )
      return false;
    if (isGold && !goldInstrument) {
      error.value = 'Nie znaleziono instrumentu złota dla wybranej próby.';
      return false;
    }
    const instrumentId = goldInstrument ? goldInstrument.id : Number(form.value.instrumentId);
    try {
      await portfolioService.buy(portfolioId.value, {
        instrument_id: instrumentId,
        quantity,
        price: isGold ? 0 : purchasePrice,
        ...(isGold ? { purchase_price_pln: purchasePrice } : {}),
        ...(isGold ? { currency: 'PLN' } : {}),
        date: form.value.date,
        commission: isGold ? 0 : Number(form.value.commission || 0),
      });
      form.value = emptyTransactionForm();
      onSaved?.();
      let savedNotice = 'Zakup zapisany.';
      if (isGold) {
        try {
          const result = await portfolioService.refreshQuotes();
          savedNotice = result.errors.length
            ? `Zakup zapisany. Nie udało się odświeżyć części notowań: ${result.errors.join('; ')}`
            : 'Zakup zapisany, a bieżąca wycena została pobrana.';
        } catch (reason) {
          const detail = reason instanceof Error ? reason.message : 'nieznany błąd';
          savedNotice = `Zakup zapisany, ale nie udało się odświeżyć wyceny: ${detail}`;
        }
      }
      await loadData();
      notice.value = savedNotice;
      return true;
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : 'Nie udało się zapisać transakcji.';
      return false;
    }
  };

  const openRemovalForm = (position: Position, removeAll = false) => {
    positionToRemove.value = position;
    const quantity = Number(position.quantity);
    removalQuantity.value = removeAll
      ? Number.isInteger(quantity)
        ? String(quantity)
        : String(position.quantity)
      : '';
    removalDate.value = today();
  };

  const closeRemovalForm = () => {
    positionToRemove.value = null;
    removalQuantity.value = '';
  };

  const removePosition = async () => {
    const position = positionToRemove.value;
    const quantity = Number(removalQuantity.value);
    if (
      !position ||
      !quantity ||
      quantity <= 0 ||
      quantity > position.quantity ||
      !removalDate.value
    )
      return;
    try {
      if (portfolioId.value === null) return;
      await portfolioService.sell(portfolioId.value, {
        instrument_id: position.instrument.id,
        quantity,
        price: position.price ?? 0,
        date: removalDate.value,
        commission: 0,
      });
      closeRemovalForm();
      notice.value =
        quantity === position.quantity
          ? `Usunięto pozycję ${position.instrument.ticker}.`
          : `Usunięto ${formatNumber(quantity)} ${position.instrument.ticker}.`;
      await loadData();
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : 'Nie udało się usunąć pozycji.';
    }
  };

  const removeAllPositions = async () => {
    const positions = summary.value?.positions ?? [];
    if (!positions.length) return;
    removingAll.value = true;
    try {
      if (portfolioId.value === null) return;
      const result = await portfolioService.clearPortfolio(portfolioId.value);
      notice.value = `Usunięto ${result.deleted_instruments} spółek oraz ${result.deleted_transactions} transakcji.`;
      await loadData();
    } catch (reason) {
      error.value =
        reason instanceof Error ? reason.message : 'Nie udało się usunąć wszystkich pozycji.';
    } finally {
      removingAll.value = false;
    }
  };

  const resetMarketSelection = () => {
    form.value.instrumentId = '';
  };

  const updateQuotes = async () => {
    refreshing.value = true;
    error.value = '';
    notice.value = 'Pobieram najnowsze notowania...';
    try {
      const result = await portfolioService.refreshQuotes();
      const dataLoaded = await loadData(false);
      if (!dataLoaded) {
        notice.value = '';
        return;
      }
      notice.value = result.errors.length
        ? `Odświeżono częściowo. Błędy: ${result.errors.join('; ')}`
        : 'Notowania zostały odświeżone.';
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : 'Nie udało się odświeżyć notowań.';
      notice.value = '';
    } finally {
      refreshing.value = false;
    }
  };

  const dismissNotice = () => {
    notice.value = '';
  };

  const importPurchases = async (file: File, source: 'xstation5' | 'bossa') => {
    if (portfolioId.value === null) return;
    error.value = '';
    notice.value = 'Importuję zakupy...';
    try {
      const result = await portfolioService.importPurchases(file, source, portfolioId.value);
      if (result.errors.length) {
        error.value = result.errors.join('; ');
        notice.value = 'Import anulowany. Popraw wskazane wiersze i spróbuj ponownie.';
        return;
      }
      let importNotice = `Zaimportowano ${result.imported} transakcji i ${result.deposits} wpłat.`;
      if (result.instrument_ids.length) {
        try {
          const quotes = await portfolioService.refreshQuotes(result.instrument_ids);
          if (quotes.errors.length) {
            importNotice += ` Notowania części instrumentów nie zostały odświeżone: ${quotes.errors.join('; ')}`;
          }
        } catch (reason) {
          const detail = reason instanceof Error ? reason.message : 'nieznany błąd';
          importNotice += ` Nie udało się pobrać notowań: ${detail}`;
        }
      }
      await loadData();
      notice.value = importNotice;
    } catch (reason) {
      error.value =
        reason instanceof Error ? reason.message : 'Nie udało się zaimportować zakupów.';
      notice.value = '';
    }
  };

  watch(
    [portfolioId, enabled],
    ([, isEnabled]) => {
      if (isEnabled) {
        void loadData();
      } else {
        ++loadVersion;
        loading.value = false;
        historyLoading.value = false;
        summary.value = null;
        instruments.value = [];
        historyDates.value = [];
        historyValues.value = [];
        historyError.value = '';
        displayedPortfolioId = undefined;
      }
    },
    { immediate: true },
  );

  return {
    summary,
    instruments,
    loading,
    removingAll,
    refreshing,
    error,
    notice,
    historyDates,
    historyValues,
    historyLoading,
    historyError,
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
    removeAllPositions,
    resetMarketSelection,
    updateQuotes,
    dismissNotice,
    importPurchases,
  };
};
