<script setup lang="ts">
  defineProps<{
    activeView: 'overview' | 'holdings';
    refreshing: boolean;
    portfolioName: string;
    hasPortfolio: boolean;
  }>();

  const emit = defineEmits<{
    refresh: [];
    addPurchase: [];
    importPurchases: [];
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
      ><template v-if="hasPortfolio"
        ><button class="button button-quiet" @click="$emit('importPurchases')">Importuj zakupy</button
        ><button class="button button-primary" @click="$emit('addPurchase')">+ Dodaj zakup</button></template
      >
    </div>
  </header>
</template>
