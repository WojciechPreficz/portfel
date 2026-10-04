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

export const usePortfolio = (portfolioId: ComputedRef<number | null>) => {
  const summary = ref<PortfolioSummary | null>(null);
  const instruments = ref<Instrument[]>([]);
  const loading = ref(true);
  const removingAll = ref(false);
  const refreshing = ref(false);
  const error = ref('');
  const notice = ref('');
  const historyDates = ref<string[]>([]);
  const historyValues = ref<number[]>([]);
  const form = ref(emptyTransactionForm());
  const positionToRemove = ref<Position | null>(null);
  const removalQuantity = ref('');
  const removalDate = ref(today());

  const filteredInstruments = computed(() =>
    instruments.value.filter((instrument) => instrument.type === form.value.marketType),
  );

  const loadData = async () => {
    loading.value = true;
    error.value = '';
    try {
      const [portfolio, history, catalog] = await portfolioService.loadSnapshot(portfolioId.value);
      summary.value = portfolio;
      instruments.value = catalog;
      historyDates.value = history.map((point) => point.date);
      historyValues.value = history.map((point) => point.value_pln);
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : 'Nie udało się pobrać danych.';
    } finally {
      loading.value = false;
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
      notice.value = result.errors.length
        ? `Odświeżono częściowo. Błędy: ${result.errors.join('; ')}`
        : 'Notowania zostały odświeżone.';
      await loadData();
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : 'Nie udało się odświeżyć notowań.';
      notice.value = '';
    } finally {
      refreshing.value = false;
    }
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
      notice.value = `Zaimportowano ${result.imported} zakupów i ${result.deposits} wpłat.`;
      await loadData();
    } catch (reason) {
      error.value =
        reason instanceof Error ? reason.message : 'Nie udało się zaimportować zakupów.';
      notice.value = '';
    }
  };

  watch(portfolioId, loadData, { immediate: true });

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
    importPurchases,
  };
};
