<script setup lang="ts">
  import { onMounted, ref } from 'vue';
  import AuthScreen from './components/AuthScreen.vue';
  import AppHeader from './components/AppHeader.vue';
  import AppSidebar from './components/AppSidebar.vue';
  import ImportModal from './components/ImportModal.vue';
  import PortfolioAlerts from './components/PortfolioAlerts.vue';
  import RemovalModal from './components/RemovalModal.vue';
  import TransactionModal from './components/TransactionModal.vue';
  import { setApiErrorHandler } from './api';
  import { useAuth } from './composables/useAuth';
  import { usePortfolio } from './composables/usePortfolio';
  import { usePortfolioCatalog, usePortfolioNavigation } from './composables/usePortfolioCatalog';
  import { usePortfolioCsv } from './composables/usePortfolioCsv';

  const {
    authStatus,
    isAuthenticated,
    authMessage,
    loginSubmitting,
    expireSession,
    checkSession,
    login,
    logout: logoutSession,
  } = useAuth();
  const { activeView, activePortfolioId, showHoldings } = usePortfolioNavigation();
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
    importPurchases,
  } = usePortfolio(activePortfolioId, isAuthenticated);
  const {
    portfolios,
    currentPortfolio,
    portfolioName,
    loadPortfolios,
    createPortfolio,
    renamePortfolio,
    deletePortfolio,
    clearPortfolios,
  } = usePortfolioCatalog(activePortfolioId, error, loadData);
  const { exportingCsv, exportPortfolioCsv } = usePortfolioCsv(error);

  setApiErrorHandler({
    onUnauthorized: expireSession,
    onRateLimited: () => {
      const message = 'Zbyt wiele prób. Spróbuj ponownie później.';
      if (isAuthenticated.value) {
        error.value = message;
      } else {
        authMessage.value = message;
      }
    },
  });

  const submitLogin = (password: string) => login(password, loadPortfolios);
  const logout = async () => {
    try {
      await logoutSession();
      clearPortfolios();
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : 'Nie udało się wylogować.';
    }
  };

  const showTransactionForm = ref(false);
  const showImportModal = ref(false);
  const submitPurchase = async () => {
    await submitTransaction(() => {
      showTransactionForm.value = false;
    });
  };
  const submitImport = (file: File, source: 'xstation5' | 'bossa') => {
    showImportModal.value = false;
    return importPurchases(file, source);
  };
  const confirmRemoveAll = async () => {
    if (!window.confirm('Czy na pewno chcesz usunąć wszystkie pozycje z portfela?')) return;
    await removeAllPositions();
  };

  onMounted(async () => {
    await checkSession();
    if (isAuthenticated.value) await loadPortfolios();
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
          :history-loading="historyLoading"
          :history-error="historyError"
          :is-aggregate="activePortfolioId === null"
          @add-purchase="showTransactionForm = true"
          @create-portfolio="createPortfolio"
          @show-holdings="showHoldings"
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
    <ImportModal v-if="showImportModal" @close="showImportModal = false" @submit="submitImport" />
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
