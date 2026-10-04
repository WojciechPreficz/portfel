<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue';
  import { useRoute, useRouter } from 'vue-router';
  import AppHeader from './components/AppHeader.vue';
  import AppSidebar from './components/AppSidebar.vue';
  import ImportModal from './components/ImportModal.vue';
  import PortfolioAlerts from './components/PortfolioAlerts.vue';
  import RemovalModal from './components/RemovalModal.vue';
  import TransactionModal from './components/TransactionModal.vue';
  import { createPortfolio as createPortfolioRequest, deletePortfolio as deletePortfolioRequest, getPortfolios, renamePortfolio as renamePortfolioRequest, type Portfolio } from './api';
  import { usePortfolio } from './composables/usePortfolio';

  const route = useRoute();
  const router = useRouter();
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
  const {
    summary,
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
  } = usePortfolio(activePortfolioId);

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
      error.value = reason instanceof Error ? reason.message : 'Nie udało się zmienić nazwy portfela.';
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

  onMounted(loadPortfolios);
</script>

<template>
  <div class="app-shell">
    <AppSidebar
      :portfolios="portfolios"
      :active-portfolio-id="activePortfolioId"
      @create-portfolio="createPortfolio"
    />
    <main class="main-content">
      <AppHeader
        :active-view="activeView"
        :refreshing="refreshing"
        :portfolio-name="portfolioName"
        :has-portfolio="activePortfolioId !== null"
        :portfolio="currentPortfolio"
        @refresh="updateQuotes"
        @add-purchase="showTransactionForm = true"
        @import-purchases="showImportModal = true"
        @rename-portfolio="renamePortfolio"
        @delete-portfolio="deletePortfolio"
      />
      <PortfolioAlerts :error="error" :notice="notice" @retry="loadData" />
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
          @show-holdings="router.push(activePortfolioId ? `/portfolios/${activePortfolioId}/holdings` : '/holdings')"
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
      @submit="(file, source) => { showImportModal = false; importPurchases(file, source); }"
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
