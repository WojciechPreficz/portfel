<script setup lang="ts">
import type { PortfolioSummary, Position } from "../api";
import { formatCurrency, formatNumber, formatPercent, formatPrice, isPositive } from "../utils/formatters";

defineProps<{
  summary: PortfolioSummary | null;
  loading: boolean;
}>();

defineEmits<{
  addPurchase: [];
  removePosition: [position: Position, removeAll: boolean];
}>();
</script>

<template>
  <section class="panel holdings-view"><div class="section-heading"><div><p class="panel-kicker">PORTFEL / {{ summary?.positions.length ?? 0 }} POZYCJI</p><h2>Wszystkie pozycje</h2></div><span class="total-caption">Łącznie {{ formatCurrency(summary?.value_pln) }}</span></div><div v-if="!summary?.positions.length && !loading" class="empty-state"><div class="empty-icon">+</div><h3>Nie ma jeszcze żadnych pozycji</h3><p>Pierwszy zakup pojawi się tutaj wraz z wyceną.</p><button class="button button-primary" @click="$emit('addPurchase')">Dodaj zakup</button></div><div v-else class="table-wrap"><table><thead><tr><th>Instrument</th><th>Ilość</th><th>Ostatnia cena</th><th>Wartość PLN</th><th>Udział</th><th>Wynik</th><th>Akcje</th></tr></thead><tbody><tr v-for="position in summary?.positions" :key="position.instrument.id"><td><div class="table-instrument"><div class="ticker-badge">{{ position.instrument.ticker.slice(0, 3) }}</div><div><strong>{{ position.instrument.ticker }}</strong><small>{{ position.instrument.name }}</small></div></div></td><td>{{ formatNumber(position.quantity) }} {{ position.instrument.unit === 'gram' ? 'g' : 'szt.' }}</td><td>{{ formatPrice(position.price) }} {{ position.instrument.currency }}</td><td><strong>{{ formatCurrency(position.market_value_pln) }}</strong></td><td>{{ formatPercent(position.weight_pct) }}</td><td :class="isPositive(position.pnl_pln) ? 'positive' : 'negative'">{{ formatCurrency(position.pnl_pln) }}<small>{{ formatPercent(position.pnl_pct) }}</small></td><td><div class="table-actions"><button class="text-button" @click="$emit('removePosition', position, false)">Usuń część</button><button class="text-button text-button-danger" @click="$emit('removePosition', position, true)">Usuń całość</button></div></td></tr></tbody></table></div></section>
</template>
