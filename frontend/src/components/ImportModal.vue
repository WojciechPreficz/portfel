<script setup lang="ts">
  import { ref } from 'vue';

  type ImportSource = 'xstation5' | 'bossa';

  const source = ref<ImportSource>('xstation5');
  const fileInput = ref<HTMLInputElement | null>(null);

  const emit = defineEmits<{
    close: [];
    submit: [file: File, source: ImportSource];
  }>();

  const selectFile = () => fileInput.value?.click();

  const handleFile = (event: Event) => {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) emit('submit', file, source.value);
    input.value = '';
  };
</script>

<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <section class="modal import-modal">
      <div class="modal-heading">
        <div>
          <p class="panel-kicker">IMPORT TRANSAKCJI</p>
          <h2>Wybierz platformę</h2>
        </div>
        <button class="close-button" aria-label="Zamknij" @click="$emit('close')">×</button>
      </div>
      <label
        >Typ dokumentu
        <select v-model="source">
          <option value="xstation5">xStation5 · Excel</option>
          <option value="bossa">Bossa · CSV</option>
        </select>
      </label>
      <p class="import-modal-hint">
        {{ source === 'xstation5' ? 'Wybierz plik .xlsx z platformy xStation5.' : 'Wybierz plik .csv z platformy Bossa.' }}
      </p>
      <div class="modal-actions">
        <button type="button" class="button button-quiet" @click="$emit('close')">Anuluj</button>
        <button type="button" class="button button-primary" @click="selectFile">Wybierz plik</button>
      </div>
      <input
        ref="fileInput"
        class="visually-hidden"
        type="file"
        :accept="source === 'xstation5' ? '.xlsx' : '.csv'"
        @change="handleFile" />
    </section>
  </div>
</template>
