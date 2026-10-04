<script setup lang="ts">
  import { computed, ref, watch } from 'vue';
  import { getGoldQuote, type GoldQuote, type Instrument } from '../api';

  type TransactionForm = {
    marketType: string;
    instrumentId: string;
    quantity: string;
    price: string;
    date: string;
    commission: string;
    goldWeightGrams: string;
    goldOunces: string;
    goldPurity: string;
    goldManualWeight: boolean;
  };

  const form = defineModel<TransactionForm>({ required: true });
  defineProps<{ instruments: Instrument[] }>();

  defineEmits<{
    close: [];
    submit: [];
    marketTypeChange: [];
  }>();

  const quote = ref<GoldQuote | null>(null);
  const quoteError = ref('');
  const quoteLoading = ref(false);
  const isGold = computed(() => form.value.marketType === 'gold');
  const referencePrice = computed(() => {
    if (!quote.value) return null;
    return quote.value.price_pln_g * (Number(form.value.goldPurity) / 9999);
  });
  const purities = [
    { value: '9999', label: '24K (999.9)' },
    { value: '9167', label: '22K (916.7)' },
    { value: '7500', label: '18K (750)' },
    { value: '5850', label: '14K (585)' },
    { value: '3750', label: '9K (375)' },
  ];

  watch(
    isGold,
    async (gold) => {
      if (!gold) return;
      quoteLoading.value = true;
      quoteError.value = '';
      try {
        quote.value = await getGoldQuote();
      } catch (reason) {
        quoteError.value =
          reason instanceof Error ? reason.message : 'Nie udało się pobrać bieżącej ceny złota.';
      } finally {
        quoteLoading.value = false;
      }
    },
    { immediate: true },
  );

  const marketTypeOptions = [
    { value: 'stock_pl', label: 'Spółka z polskiego rynku akcji' },
    { value: 'stock_us', label: 'Spółka amerykańska notowana na NASDAQ' },
    {
      value: 'stock_us_nyse',
      label: 'Spółka amerykańska notowana na giełdzie nowojorskiej (NYSE)',
    },
    { value: 'etf', label: 'ETF' },
    { value: 'gold', label: 'Złoto' },
  ];
</script>

<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <section class="modal">
      <div class="modal-heading">
        <div>
          <p class="panel-kicker">{{ isGold ? 'DODAJ ZŁOTO' : 'NOWA TRANSAKCJA' }}</p>
          <h2>{{ isGold ? 'Zakup złota' : 'Dodaj zakup' }}</h2>
        </div>
        <button class="close-button" aria-label="Zamknij" @click="$emit('close')">×</button>
      </div>
      <form @submit.prevent="$emit('submit')">
        <label
          >Typ instrumentu
          <select v-model="form.marketType" @change="$emit('marketTypeChange')" required>
            <option value="" disabled>Najpierw wybierz typ</option>
            <option v-for="option in marketTypeOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>
        <label v-if="form.marketType && !isGold"
          >Instrument
          <select v-model="form.instrumentId" required>
            <option value="" disabled>
              Wybierz {{ form.marketType === 'etf' ? 'ETF' : 'spółkę' }}
            </option>
            <option v-for="instrument in instruments" :key="instrument.id" :value="instrument.id">
              {{ instrument.ticker }} · {{ instrument.name }}
            </option>
          </select>
        </label>
        <template v-if="isGold">
          <div class="form-row gold-weight-row">
            <label
              >Próba
              <select v-model="form.goldPurity" required>
                <option v-for="purity in purities" :key="purity.value" :value="purity.value">
                  {{ purity.label }}
                </option>
              </select>
            </label>
            <label class="gold-checkbox">
              <span>Waga</span>
              <span class="gold-checkbox-control"
                ><input
                  v-model="form.goldManualWeight"
                  type="checkbox"
                  @change="
                    form.goldWeightGrams = '';
                    form.goldOunces = form.goldManualWeight ? '' : '1';
                  "
                />Podam wagę samodzielnie</span
              >
            </label>
          </div>
          <div class="form-row">
            <label v-if="form.goldManualWeight"
              >Waga (g)<input
                v-model="form.goldWeightGrams"
                type="number"
                min="0.00000001"
                step="any"
                placeholder="np. 50"
                required
              />
            </label>
            <label v-else
              >Ilość uncji<input
                v-model="form.goldOunces"
                type="number"
                min="0.00000001"
                step="any"
                placeholder="np. 1"
                required
              />
            </label>
            <label
              >Cena zakupu
              <span class="gold-price-input"
                ><input
                  v-model="form.price"
                  type="number"
                  min="0.01"
                  step="any"
                  placeholder="np. 13 250"
                  required
                /><span>PLN</span></span
              >
            </label>
          </div>
          <p v-if="quoteLoading" class="gold-quote">Pobieram cenę spot i kurs USD/PLN...</p>
          <p v-else-if="referencePrice" class="gold-quote">
            Cena referencyjna:
            {{ referencePrice.toLocaleString('pl-PL', { maximumFractionDigits: 2 }) }} PLN/g · spot
            {{ quote?.spot_usd_oz.toLocaleString('pl-PL', { maximumFractionDigits: 2 }) }} USD/oz ·
            NBP {{ quote?.usd_pln.toLocaleString('pl-PL', { maximumFractionDigits: 4 }) }} PLN/USD
          </p>
          <p v-else-if="quoteError" class="gold-quote gold-quote-error">{{ quoteError }}</p>
        </template>
        <template v-else>
          <div class="form-row">
            <label
              >Ilość<input
                v-model="form.quantity"
                type="number"
                min="0.00000001"
                step="any"
                placeholder="np. 10"
                required /></label
            ><label
              >Cena za sztukę<input
                v-model="form.price"
                type="number"
                min="0"
                step="any"
                placeholder="np. 125.50"
                required
            /></label>
          </div>
          <div class="form-row">
            <label
              >Prowizja<input
                v-model="form.commission"
                type="number"
                min="0"
                step="any"
                placeholder="0"
            /></label>
          </div>
        </template>
        <label>Data zakupu<input v-model="form.date" type="date" required /></label>
        <div class="modal-actions">
          <button type="button" class="button button-quiet" @click="$emit('close')">Anuluj</button
          ><button type="submit" class="button button-primary">
            {{ isGold ? 'Zapisz zakup złota' : 'Zapisz zakup' }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>
