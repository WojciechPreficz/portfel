<script setup lang="ts">
  defineProps<{
    activeView: 'overview' | 'holdings';
    refreshing: boolean;
  }>();

  const emit = defineEmits<{
    refresh: [];
    addPurchase: [];
    importPurchases: [file: File];
  }>();

  const currentDateLabel = new Intl.DateTimeFormat('pl-PL', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
    .format(new Date())
    .toLocaleUpperCase('pl-PL');

  const selectImportFile = (event: Event) => {
    const input = event.target as HTMLInputElement;
    if (input.files?.[0]) emit('importPurchases', input.files[0]);
    input.value = '';
  };
</script>

<template>
  <header class="topbar">
    <div>
      <p class="eyebrow">{{ currentDateLabel }}</p>
      <h1>{{ activeView === 'overview' ? 'Dzień dobry, Wojciech' : 'Twoje pozycje' }}</h1>
    </div>
    <div class="top-actions">
      <button class="button button-quiet" :disabled="refreshing" @click="$emit('refresh')">
        {{ refreshing ? 'Odświeżam...' : 'Odśwież notowania' }}</button
      ><label class="button button-quiet"
        >Importuj zakupy<input
          class="visually-hidden"
          type="file"
          accept=".xlsx"
          @change="selectImportFile" /></label
      ><button class="button button-primary" @click="$emit('addPurchase')">+ Dodaj zakup</button>
    </div>
  </header>
</template>
