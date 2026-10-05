<script setup lang="ts">
  import type { Portfolio } from '../api';

  defineProps<{
    activeView: 'overview' | 'holdings';
    refreshing: boolean;
    exportingCsv: boolean;
    portfolioName: string;
    hasPortfolio: boolean;
    portfolio: Portfolio | undefined;
  }>();

  const emit = defineEmits<{
    refresh: [];
    exportCsv: [];
    addPurchase: [];
    importPurchases: [];
    renamePortfolio: [portfolio: Portfolio];
    deletePortfolio: [portfolio: Portfolio];
    logout: [];
  }>();

  const currentDateLabel = new Intl.DateTimeFormat('pl-PL', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
    .format(new Date())
    .toLocaleUpperCase('pl-PL');
</script>

<template>
  <header class="topbar">
    <div>
      <p class="eyebrow">{{ currentDateLabel }}</p>
      <h1>{{ activeView === 'holdings' ? `Pozycje · ${portfolioName}` : portfolioName }}</h1>
    </div>
    <div class="top-actions">
      <button class="button button-quiet" :disabled="refreshing" @click="$emit('refresh')">
        {{ refreshing ? 'Odświeżam...' : 'Odśwież notowania' }}</button
      ><button class="button button-quiet" :disabled="exportingCsv" @click="$emit('exportCsv')">
        {{ exportingCsv ? 'Eksportuję...' : 'Eksportuj CSV' }}</button
      ><template v-if="hasPortfolio"
        ><button class="button button-quiet" @click="$emit('importPurchases')">
          Importuj zakupy</button
        ><button class="button button-primary" @click="$emit('addPurchase')">
          + Dodaj zakup
        </button></template
      >
      <div v-if="portfolio" class="portfolio-actions">
        <button class="portfolio-action" @click="$emit('renamePortfolio', portfolio)">
          Zmień nazwę
        </button>
        <button
          class="portfolio-action portfolio-action-delete"
          @click="$emit('deletePortfolio', portfolio)"
        >
          Usuń portfel
        </button>
      </div>
      <button class="button button-quiet" @click="$emit('logout')">Wyloguj</button>
    </div>
  </header>
</template>
