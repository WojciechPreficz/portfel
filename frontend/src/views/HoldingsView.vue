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
    isAggregate: boolean;
  }>();

  const emit = defineEmits<{
    addPurchase: [];
    createPortfolio: [];
    removePosition: [position: Position, removeAll: boolean];
    removeAll: [];
  }>();

  type SortKey = 'instrument' | 'quantity' | 'market_value_pln' | 'weight_pct' | 'pnl_pln';

  const sortKey = ref<SortKey>('instrument');
  const sortDirection = ref<'asc' | 'desc'>('asc');

  const groupDefinitions = [
    { key: 'polish', label: 'Akcje polskie' },
    { key: 'us', label: 'Akcje USA' },
    { key: 'etf', label: 'ETF' },
    { key: 'other', label: 'Pozostałe aktywa' },
  ] as const;

  const numericValue = (value: number | null | undefined) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  };

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

  const positionGroups = computed(() => {
    const groups = new Map<(typeof groupDefinitions)[number]['key'], Position[]>([
      ['polish', []],
      ['us', []],
      ['etf', []],
      ['other', []],
    ]);

    for (const position of sortedPositions.value) {
      const type = position.instrument.type;
      const key =
        type === 'stock_pl'
          ? 'polish'
          : type === 'stock_us' || type === 'stock_us_nyse'
            ? 'us'
            : type === 'etf'
              ? 'etf'
              : 'other';
      groups.get(key)?.push(position);
    }

    return groupDefinitions.flatMap(({ key, label }) => {
      const positions = groups.get(key) ?? [];
      if (!positions.length) return [];

      const value = positions.reduce(
        (total, position) => total + numericValue(position.market_value_pln),
        0,
      );
      const pnl = positions.reduce((total, position) => total + numericValue(position.pnl_pln), 0);
      const cost = positions.reduce(
        (total, position) => total + numericValue(position.cost_pln),
        0,
      );
      const portfolioValue = numericValue(props.summary?.value_pln);

      return [
        {
          key,
          label,
          positions,
          value,
          pnl,
          pnlPct: cost !== 0 ? (pnl / cost) * 100 : null,
          sharePct: portfolioValue !== 0 ? (value / portfolioValue) * 100 : null,
        },
      ];
    });
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
        <p class="panel-kicker">
          {{ isAggregate ? 'MAJĄTEK' : 'PORTFEL' }} / {{ summary?.positions.length ?? 0 }} POZYCJI
        </p>
        <h2>Wszystkie pozycje</h2>
      </div>
      <div class="section-heading-actions">
        <span class="total-caption">Łącznie {{ formatCurrency(summary?.value_pln) }}</span>
        <button
          v-if="!isAggregate && summary?.positions.length"
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
      <button
        class="button button-primary"
        @click="isAggregate ? $emit('createPortfolio') : $emit('addPurchase')"
      >
        {{ isAggregate ? 'Utwórz portfel' : 'Dodaj zakup' }}
      </button>
    </div>
    <div v-else class="table-wrap holdings-groups">
      <details v-for="group in positionGroups" :key="group.key" class="holdings-group" open>
        <summary class="holdings-group-heading">
          <span class="holdings-group-name">{{ group.label }}</span>
          <span class="holdings-group-total">
            {{ formatCurrency(group.value) }}
            <small
              >({{ group.sharePct === null ? '--' : `${formatNumber(group.sharePct)}%` }})</small
            >
            <span :class="isPositive(group.pnl) ? 'positive' : 'negative'">
              {{ formatCurrency(group.pnl) }}
              <small>({{ formatPercent(group.pnlPct) }})</small>
            </span>
          </span>
        </summary>
        <div class="holdings-group-table">
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
                <th v-if="!isAggregate">Akcje</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="position in group.positions" :key="position.instrument.id">
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
                <td v-if="!isAggregate">
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
      </details>
    </div>
  </section>
</template>
