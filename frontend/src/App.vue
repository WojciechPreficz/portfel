<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue';
  import { useRoute, useRouter } from 'vue-router';
  import AppHeader from './components/AppHeader.vue';
  import AppSidebar from './components/AppSidebar.vue';
  import ImportModal from './components/ImportModal.vue';
  import PortfolioAlerts from './components/PortfolioAlerts.vue';
  import RemovalModal from './components/RemovalModal.vue';
  import TransactionModal from './components/TransactionModal.vue';
  import { usePortfolio } from './composables/usePortfolio';

  const route = useRoute();
  const router = useRouter();
  const activeView = computed<'overview' | 'holdings'>(() =>
    route.name === 'holdings' ? 'holdings' : 'overview',
  );
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
  } = usePortfolio();

  const submitPurchase = async () => {
    if (await submitTransaction()) showTransactionForm.value = false;
  };

  const confirmRemoveAll = async () => {
    if (!window.confirm('Czy na pewno chcesz usunąć wszystkie pozycje z portfela?')) return;
    await removeAllPositions();
  };

  onMounted(loadData);
</script>

<template>
  <div class="app-shell">
    <AppSidebar :active-view="activeView" :position-count="summary?.positions.length ?? 0" />
    <main class="main-content">
      <AppHeader
        :active-view="activeView"
        :refreshing="refreshing"
        @refresh="updateQuotes"
        @add-purchase="showTransactionForm = true"
        @import-purchases="showImportModal = true"
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
          @add-purchase="showTransactionForm = true"
          @show-holdings="router.push('/holdings')"
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
