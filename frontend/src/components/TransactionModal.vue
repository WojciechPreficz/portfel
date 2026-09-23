<script setup lang="ts">
import type { Instrument } from "../api";

type TransactionForm = {
  marketType: string;
  instrumentId: string;
  quantity: string;
  price: string;
  date: string;
  commission: string;
};

const form = defineModel<TransactionForm>({ required: true });
defineProps<{ instruments: Instrument[] }>();

defineEmits<{
  close: [];
  submit: [];
  marketTypeChange: [];
}>();

const marketTypeOptions = [
  { value: "stock_pl", label: "Spółka z polskiego rynku akcji" },
  { value: "stock_us", label: "Spółka amerykańska notowana na NASDAQ" },
  { value: "stock_us_nyse", label: "Spółka amerykańska notowana na giełdzie nowojorskiej (NYSE)" },
  { value: "etf", label: "ETF" },
];
</script>

<template>
  <div class="modal-backdrop" @click.self="$emit('close')"><section class="modal"><div class="modal-heading"><div><p class="panel-kicker">NOWA TRANSAKCJA</p><h2>Dodaj zakup</h2></div><button class="close-button" aria-label="Zamknij" @click="$emit('close')">×</button></div><form @submit.prevent="$emit('submit')">
    <label>Typ instrumentu
      <select v-model="form.marketType" @change="$emit('marketTypeChange')" required>
        <option value="" disabled>Najpierw wybierz typ</option>
        <option v-for="option in marketTypeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
      </select>
    </label>
    <label v-if="form.marketType">Instrument
      <select v-model="form.instrumentId" required>
        <option value="" disabled>Wybierz {{ form.marketType === 'etf' ? 'ETF' : 'spółkę' }}</option>
        <option v-for="instrument in instruments" :key="instrument.id" :value="instrument.id">{{ instrument.ticker }} · {{ instrument.name }}</option>
      </select>
    </label>
    <div class="form-row"><label>Ilość<input v-model="form.quantity" type="number" min="0.00000001" step="any" placeholder="np. 10" required /></label><label>Cena za sztukę<input v-model="form.price" type="number" min="0" step="any" placeholder="np. 125.50" required /></label></div><div class="form-row"><label>Data zakupu<input v-model="form.date" type="date" required /></label><label>Prowizja<input v-model="form.commission" type="number" min="0" step="any" placeholder="0" /></label></div><div class="modal-actions"><button type="button" class="button button-quiet" @click="$emit('close')">Anuluj</button><button type="submit" class="button button-primary">Zapisz zakup</button></div>
  </form></section></div>
</template>
