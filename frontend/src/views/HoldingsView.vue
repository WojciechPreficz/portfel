<script setup lang="ts">
  import { computed, ref } from 'vue';
  import type { PortfolioSummary, Position } from '../api';
  import {
    formatCurrency,
    formatNumber,
    formatPercent,
    formatPrice,
    isPositive,
  } from '../utils/formatters';

  const props = defineProps<{
    summary: PortfolioSummary | null;
    loading: boolean;
    removingAll: boolean;
  }>();

  const emit = defineEmits<{
    addPurchase: [];
    removePosition: [position: Position, removeAll: boolean];
    removeAll: [];
  }>();

  type SortKey = 'instrument' | 'quantity' | 'market_value_pln' | 'weight_pct' | 'pnl_pln';

  const sortKey = ref<SortKey>('instrument');
  const sortDirection = ref<'asc' | 'desc'>('asc');

  const sortedPositions = computed(() => {
    const positions = props.summary?.positions ?? [];

    return positions
      .map((position, index) => ({ position, index }))
      .sort((left, right) => {
        let comparison = 0;
        if (sortKey.value === 'instrument') {
          comparison = left.position.instrument.ticker.localeCompare(
            right.position.instrument.ticker,
            'pl',
            { sensitivity: 'base' },
          );
        } else {
          const leftValue = left.position[sortKey.value] ?? 0;
          const rightValue = right.position[sortKey.value] ?? 0;
          comparison = Number(leftValue) - Number(rightValue);
        }

        return comparison === 0
          ? left.index - right.index
          : sortDirection.value === 'asc'
            ? comparison
            : -comparison;
      })
      .map(({ position }) => position);
  });

  const setSort = (key: SortKey) => {
    if (sortKey.value === key) {
      sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc';
    } else {
      sortKey.value = key;
      sortDirection.value = 'asc';
    }
  };

  const sortIndicator = (key: SortKey) =>
    sortKey.value === key ? (sortDirection.value === 'asc' ? '^' : 'v') : '';
  const sortAria = (key: SortKey) =>
    sortKey.value === key ? (sortDirection.value === 'asc' ? 'ascending' : 'descending') : 'none';
</script>

<template>
  <section class="panel holdings-view">
    <div class="section-heading">
      <div>
        <p class="panel-kicker">PORTFEL / {{ summary?.positions.length ?? 0 }} POZYCJI</p>
        <h2>Wszystkie pozycje</h2>
      </div>
      <div class="section-heading-actions">
        <span class="total-caption">Łącznie {{ formatCurrency(summary?.value_pln) }}</span>
        <button
          v-if="summary?.positions.length"
          class="text-button text-button-danger"
          :disabled="removingAll"
          @click="$emit('removeAll')"
        >
          {{ removingAll ? 'Usuwanie...' : 'Usuń wszystkie' }}
        </button>
      </div>
    </div>
    <div v-if="loading || removingAll" class="loading-state" role="status">
      <div class="loading-spinner"></div>
      <p>Usuwanie pozycji...</p>
    </div>
    <div v-else-if="!summary?.positions.length" class="empty-state">
      <div class="empty-icon">+</div>
      <h3>Nie ma jeszcze żadnych pozycji</h3>
      <p>Pierwszy zakup pojawi się tutaj wraz z wyceną.</p>
      <button class="button button-primary" @click="$emit('addPurchase')">Dodaj zakup</button>
    </div>
    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>
              <button
                class="table-sort-button"
                :aria-sort="sortAria('instrument')"
                @click="setSort('instrument')"
              >
                Instrument <span>{{ sortIndicator('instrument') }}</span>
              </button>
            </th>
            <th>
              <button
                class="table-sort-button"
                :aria-sort="sortAria('quantity')"
                @click="setSort('quantity')"
              >
                Ilość <span>{{ sortIndicator('quantity') }}</span>
              </button>
            </th>
            <th>Ostatnia cena</th>
            <th>
              <button
                class="table-sort-button"
                :aria-sort="sortAria('market_value_pln')"
                @click="setSort('market_value_pln')"
              >
                Wartość PLN <span>{{ sortIndicator('market_value_pln') }}</span>
              </button>
            </th>
            <th>
              <button
                class="table-sort-button"
                :aria-sort="sortAria('weight_pct')"
                @click="setSort('weight_pct')"
              >
                Udział <span>{{ sortIndicator('weight_pct') }}</span>
              </button>
            </th>
            <th>
              <button
                class="table-sort-button"
                :aria-sort="sortAria('pnl_pln')"
                @click="setSort('pnl_pln')"
              >
                Wynik <span>{{ sortIndicator('pnl_pln') }}</span>
              </button>
            </th>
            <th>Akcje</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="position in sortedPositions" :key="position.instrument.id">
            <td>
              <div class="table-instrument">
                <div class="ticker-badge">{{ position.instrument.ticker.slice(0, 3) }}</div>
                <div>
                  <strong>{{ position.instrument.ticker }}</strong>
                  <small>{{ position.instrument.name }}</small>
                </div>
              </div>
            </td>
            <td>
              {{ formatNumber(position.quantity) }}
              {{ position.instrument.unit === 'gram' ? 'g' : 'szt.' }}
            </td>
            <td>{{ formatPrice(position.price) }} {{ position.instrument.currency }}</td>
            <td>
              <strong>{{ formatCurrency(position.market_value_pln) }}</strong>
            </td>
            <td>{{ formatPercent(position.weight_pct) }}</td>
            <td :class="isPositive(position.pnl_pln) ? 'positive' : 'negative'">
              {{ formatCurrency(position.pnl_pln)
              }}<small>{{ formatPercent(position.pnl_pct) }}</small>
            </td>
            <td>
              <div class="table-actions">
                <button class="text-button" @click="$emit('removePosition', position, false)">
                  Usuń część
                </button>
                <button
                  class="text-button text-button-danger"
                  @click="$emit('removePosition', position, true)"
                >
                  Usuń całość
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
