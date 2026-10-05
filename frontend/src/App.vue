<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue';
  import { useRoute, useRouter } from 'vue-router';
  import AuthScreen from './components/AuthScreen.vue';
  import AppHeader from './components/AppHeader.vue';
  import AppSidebar from './components/AppSidebar.vue';
  import ImportModal from './components/ImportModal.vue';
  import PortfolioAlerts from './components/PortfolioAlerts.vue';
  import RemovalModal from './components/RemovalModal.vue';
  import TransactionModal from './components/TransactionModal.vue';
  import {
    ApiError,
    createPortfolio as createPortfolioRequest,
    deletePortfolio as deletePortfolioRequest,
    getAuthStatus,
    getPortfolio,
    getPortfolios,
    login as loginRequest,
    logout as logoutRequest,
    renamePortfolio as renamePortfolioRequest,
    setApiErrorHandler,
    type Portfolio,
  } from './api';
  import { usePortfolio } from './composables/usePortfolio';

  const route = useRoute();
  const router = useRouter();
  const authStatus = ref<'checking' | 'authenticated' | 'unauthenticated'>('checking');
  const isAuthenticated = computed(() => authStatus.value === 'authenticated');
  const authMessage = ref('');
  const loginSubmitting = ref(false);
  const activeView = computed<'overview' | 'holdings'>(() =>
    route.name === 'portfolio-holdings' || route.name === 'aggregate-holdings'
      ? 'holdings'
      : 'overview',
  );
  const activePortfolioId = computed<number | null>(() => {
    if (route.name !== 'portfolio-overview' && route.name !== 'portfolio-holdings') return null;
    const id = Number(route.params.portfolioId);
    return Number.isInteger(id) && id > 0 ? id : null;
  });
  const portfolios = ref<Portfolio[]>([]);
  const currentPortfolio = computed(() =>
    portfolios.value.find((portfolio) => portfolio.id === activePortfolioId.value),
  );
  const portfolioName = computed(() => currentPortfolio.value?.name ?? 'Majątek');
  const showTransactionForm = ref(false);
  const showImportModal = ref(false);
  const exportingCsv = ref(false);
  const {
    summary,
    loading,
    removingAll,
    refreshing,
    error,
    notice,
    dismissNotice,
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
  } = usePortfolio(activePortfolioId, isAuthenticated);

  setApiErrorHandler({
    onUnauthorized: () => {
      authStatus.value = 'unauthenticated';
      authMessage.value = 'Sesja wygasła';
      loginSubmitting.value = false;
    },
    onRateLimited: () => {
      const message = 'Zbyt wiele prób. Spróbuj ponownie później.';
      if (authStatus.value === 'authenticated') {
        error.value = message;
      } else {
        authMessage.value = message;
      }
    },
  });

  const loadPortfolios = async () => {
    try {
      portfolios.value = await getPortfolios();
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : 'Nie udało się pobrać portfeli.';
    }
  };

  const createPortfolio = async () => {
    const name = window.prompt('Nazwa nowego portfela');
    if (!name?.trim()) return;
    try {
      const portfolio = await createPortfolioRequest(name.trim());
      await loadPortfolios();
      await router.push(`/portfolios/${portfolio.id}`);
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : 'Nie udało się utworzyć portfela.';
    }
  };

  const renamePortfolio = async (portfolio: Portfolio) => {
    const name = window.prompt('Nowa nazwa portfela', portfolio.name);
    if (!name?.trim() || name.trim() === portfolio.name) return;
    try {
      await renamePortfolioRequest(portfolio.id, name.trim());
      await loadPortfolios();
    } catch (reason) {
      error.value =
        reason instanceof Error ? reason.message : 'Nie udało się zmienić nazwy portfela.';
    }
  };

  const deletePortfolio = async (portfolio: Portfolio) => {
    const confirmed = window.confirm(
      `Usunięcie portfela "${portfolio.name}" trwale usunie wszystkie jego transakcje i wpłaty. Kontynuować?`,
    );
    if (!confirmed) return;
    try {
      await deletePortfolioRequest(portfolio.id);
      await loadPortfolios();
      if (activePortfolioId.value === portfolio.id) {
        await router.push('/');
        await loadData();
      } else if (activePortfolioId.value === null) {
        await loadData();
      }
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : 'Nie udało się usunąć portfela.';
    }
  };

  const submitPurchase = async () => {
    await submitTransaction(() => {
      showTransactionForm.value = false;
    });
  };

  const confirmRemoveAll = async () => {
    if (!window.confirm('Czy na pewno chcesz usunąć wszystkie pozycje z portfela?')) return;
    await removeAllPositions();
  };

  const formatCsvNumber = (value: unknown, label: string, allowEmpty = false) => {
    if (allowEmpty && (value == null || value === '')) return '';
    if (
      value == null ||
      (typeof value === 'string' && !value.trim()) ||
      !Number.isFinite(Number(value))
    ) {
      throw new Error(`Nieprawidłowa wartość pola „${label}” w danych portfela.`);
    }
    return Number(value).toFixed(2).replace('.', ',');
  };

  const exportPortfolioCsv = async () => {
    exportingCsv.value = true;
    error.value = '';
    try {
      const portfolio = await getPortfolio(null);
      const rows = [
        ['Ticker', 'ISIN', 'Nazwa', 'Waluta', 'Symbol', 'Ilość', 'Wartość PLN'],
        ...portfolio.positions.map(({ instrument, quantity, market_value_pln }) => [
          instrument.ticker,
          instrument.isin,
          instrument.name,
          instrument.currency,
          instrument.symbol,
          formatCsvNumber(quantity, 'Ilość'),
          formatCsvNumber(market_value_pln, 'Wartość PLN', true),
        ]),
      ];
      const csv = `\uFEFF${rows
        .map((row) =>
          row.map((value) => `"${String(value ?? '').replaceAll('"', '""')}"`).join(';'),
        )
        .join('\r\n')}`;
      const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `instrumenty-portfelowe-${new Date().toISOString().slice(0, 10)}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      error.value =
        reason instanceof Error ? reason.message : 'Nie udało się wyeksportować instrumentów.';
    } finally {
      exportingCsv.value = false;
    }
  };

  const submitLogin = async (password: string) => {
    loginSubmitting.value = true;
    authMessage.value = '';
    try {
      await loginRequest(password);
      authStatus.value = 'authenticated';
      await loadPortfolios();
    } catch (reason) {
      authMessage.value =
        reason instanceof ApiError && reason.status === 401
          ? 'Nieprawidłowe hasło.'
          : reason instanceof Error
            ? reason.message
            : 'Nie udało się zalogować.';
    } finally {
      loginSubmitting.value = false;
    }
  };

  const logout = async () => {
    try {
      await logoutRequest();
      portfolios.value = [];
      authMessage.value = '';
      authStatus.value = 'unauthenticated';
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : 'Nie udało się wylogować.';
    }
  };

  onMounted(async () => {
    try {
      const session = await getAuthStatus();
      if (!session.authenticated) {
        authStatus.value = 'unauthenticated';
        return;
      }
      authStatus.value = 'authenticated';
      await loadPortfolios();
    } catch (reason) {
      authStatus.value = 'unauthenticated';
      authMessage.value =
        reason instanceof ApiError && reason.status === 401
          ? ''
          : reason instanceof Error
            ? reason.message
            : 'Nie udało się sprawdzić sesji.';
    }
  });
</script>

<template>
  <AuthScreen
    v-if="authStatus !== 'authenticated'"
    :checking="authStatus === 'checking'"
    :submitting="loginSubmitting"
    :message="authMessage"
    @submit="submitLogin"
  />
  <div v-else class="app-shell">
    <AppSidebar
      :portfolios="portfolios"
      :active-portfolio-id="activePortfolioId"
      @create-portfolio="createPortfolio"
    />
    <main class="main-content">
      <AppHeader
        :active-view="activeView"
        :refreshing="refreshing"
        :exporting-csv="exportingCsv"
        :portfolio-name="portfolioName"
        :has-portfolio="activePortfolioId !== null"
        :portfolio="currentPortfolio"
        @refresh="updateQuotes"
        @export-csv="exportPortfolioCsv"
        @add-purchase="showTransactionForm = true"
        @import-purchases="showImportModal = true"
        @rename-portfolio="renamePortfolio"
        @delete-portfolio="deletePortfolio"
        @logout="logout"
      />
      <PortfolioAlerts :error="error" :notice="notice" @retry="loadData" @dismiss="dismissNotice" />
      <RouterView v-slot="{ Component }">
        <component
          :is="Component"
          :summary="summary"
          :loading="loading"
          :removing-all="removingAll"
          :history-dates="historyDates"
          :history-values="historyValues"
          :is-aggregate="activePortfolioId === null"
          @add-purchase="showTransactionForm = true"
          @create-portfolio="createPortfolio"
          @show-holdings="
            router.push(
              activePortfolioId ? `/portfolios/${activePortfolioId}/holdings` : '/holdings',
            )
          "
          @remove-position="openRemovalForm"
          @remove-all="confirmRemoveAll"
        />
      </RouterView>
      <footer>
        <span>Portfel prywatny · dane lokalne</span>
        <span>Ostatnia aktualizacja: {{ summary?.as_of ?? 'brak danych' }}</span>
      </footer>
    </main>
    <TransactionModal
      v-if="showTransactionForm"
      v-model="form"
      :instruments="filteredInstruments"
      @close="showTransactionForm = false"
      @submit="submitPurchase"
      @market-type-change="resetMarketSelection"
    />
    <ImportModal
      v-if="showImportModal"
      @close="showImportModal = false"
      @submit="
        (file, source) => {
          showImportModal = false;
          importPurchases(file, source);
        }
      "
    />
    <RemovalModal
      v-if="positionToRemove"
      v-model:quantity="removalQuantity"
      v-model:date="removalDate"
      :position="positionToRemove"
      @close="closeRemovalForm"
      @submit="removePosition"
    />
  </div>
</template>
