<script setup lang="ts">
  import type { Position } from '../api';
  import { formatNumber } from '../utils/formatters';

  const props = defineProps<{ position: Position }>();
  const quantity = defineModel<string>('quantity', { required: true });
  const date = defineModel<string>('date', { required: true });

  defineEmits<{
    close: [];
    submit: [];
  }>();
</script>

<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <section class="modal">
      <div class="modal-heading">
        <div>
          <p class="panel-kicker">ZMNIEJSZ POZYCJĘ</p>
          <h2>Usuń {{ props.position.instrument.ticker }}</h2>
        </div>
        <button class="close-button" aria-label="Zamknij" @click="$emit('close')">×</button>
      </div>
      <form @submit.prevent="$emit('submit')">
        <p class="modal-help">
          Posiadasz {{ formatNumber(props.position.quantity) }}
          {{ props.position.instrument.unit === 'gram' ? 'g' : 'szt.' }}. Sprzedaż zostanie zapisana
          jako transakcja.
        </p>
        <label
          >Ilość do usunięcia<input
            v-model="quantity"
            type="number"
            min="1"
            :max="props.position.quantity"
            step="1"
            required /></label
        ><label>Data sprzedaży<input v-model="date" type="date" required /></label>
        <div class="modal-actions">
          <button type="button" class="button button-quiet" @click="$emit('close')">Anuluj</button
          ><button type="submit" class="button button-danger">Usuń pozycję</button>
        </div>
      </form>
    </section>
  </div>
</template>
