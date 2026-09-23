<script setup lang="ts">
  import { computed } from 'vue';
  import { use } from 'echarts/core';
  import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
  import { LineChart, PieChart } from 'echarts/charts';
  import { CanvasRenderer } from 'echarts/renderers';
  import VChart from 'vue-echarts';
  import { formatCurrency, formatPercent, isPositive } from '../utils/formatters';
  import type { PortfolioSummary } from '../api';

  use([CanvasRenderer, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent]);

  defineEmits<{
    addPurchase: [];
    showHoldings: [];
  }>();

  const props = defineProps<{
    summary: PortfolioSummary | null;
    loading: boolean;
    historyDates: string[];
    historyValues: number[];
  }>();

  const chartOption = computed(() => ({
    animationDuration: 700,
    grid: { left: 8, right: 12, top: 18, bottom: 8, containLabel: true },
    tooltip: { trigger: 'axis', valueFormatter: (value: number) => formatCurrency(value) },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: props.historyDates,
      axisLabel: { color: '#7b817b', formatter: (value: string) => value.slice(5) },
      axisLine: { lineStyle: { color: '#d8ddd6' } },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { color: '#7b817b', formatter: (value: number) => `${Math.round(value / 1000)}k` },
      splitLine: { lineStyle: { color: '#e7ebe5' } },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        symbol: 'none',
        data: props.historyValues,
        lineStyle: { width: 3, color: '#c2ec62' },
        areaStyle: { color: 'rgba(194, 236, 98, .18)' },
      },
    ],
  }));

  const allocationOption = computed(() => ({
    tooltip: {
      trigger: 'item',
      formatter: (params: { name: string; percent: number }) => {
        const position = props.summary?.positions.find(
          (item) => item.instrument.ticker === params.name,
        );
        return `${position?.instrument.name ?? params.name}: ${params.percent}%`;
      },
    },
    legend: { bottom: 0, left: 'center', textStyle: { color: '#596158' } },
    series: [
      {
        type: 'pie',
        radius: ['52%', '76%'],
        center: ['50%', '42%'],
        avoidLabelOverlap: true,
        label: { show: false },
        data: (props.summary?.positions ?? []).map((position) => ({
          name: position.instrument.ticker,
          value: position.market_value_pln,
        })),
        itemStyle: { borderColor: '#fbfcf8', borderWidth: 3 },
      },
    ],
    color: ['#17201b', '#b9e85d', '#ee806d', '#8cb7a4', '#d8ae57'],
  }));
</script>

<template>
  <section class="content-grid">
    <div class="hero-metric panel panel-dark">
      <div>
        <p class="panel-kicker">WARTOŚĆ PORTFELA</p>
        <div v-if="loading" class="skeleton skeleton-xl"></div>
        <strong v-else>{{ formatCurrency(summary?.value_pln) }}</strong>
        <p class="metric-sub">
          {{ summary?.as_of ? `Wycena z ${summary.as_of}` : 'Brak aktualnych notowań' }}
        </p>
      </div>
      <div class="hero-orbit"><span></span><span></span><span></span></div>
    </div>
    <div class="metric-card panel">
      <p class="panel-kicker">ZMIANA 1D</p>
      <div v-if="loading" class="skeleton skeleton-lg"></div>
      <strong v-else :class="isPositive(summary?.change_1d_pln) ? 'positive' : 'negative'">{{
        formatCurrency(summary?.change_1d_pln)
      }}</strong>
      <p :class="['metric-sub', isPositive(summary?.change_1d_pct) ? 'positive' : 'negative']">
        {{ formatPercent(summary?.change_1d_pct) }}
      </p>
    </div>
    <div class="metric-card panel">
      <p class="panel-kicker">P/L NIEZREALIZOWANY</p>
      <div v-if="loading" class="skeleton skeleton-lg"></div>
      <strong v-else :class="isPositive(summary?.pnl_pln) ? 'positive' : 'negative'">{{
        formatCurrency(summary?.pnl_pln)
      }}</strong>
      <p :class="['metric-sub', isPositive(summary?.pnl_pct) ? 'positive' : 'negative']">
        {{ formatPercent(summary?.pnl_pct) }} od zakupu
      </p>
    </div>
    <div class="metric-card panel">
      <p class="panel-kicker">XIRR ROCZNY</p>
      <div v-if="loading" class="skeleton skeleton-lg"></div>
      <strong v-else :class="isPositive(summary?.xirr_pct) ? 'positive' : 'negative'">{{
        formatPercent(summary?.xirr_pct)
      }}</strong>
      <p class="metric-sub">Zwrot ważony czasem</p>
    </div>
    <section class="panel chart-panel">
      <div class="section-heading">
        <div>
          <p class="panel-kicker">WARTOŚĆ W CZASIE</p>
          <h2>Jak rośnie kapitał</h2>
        </div>
        <span class="heading-meta">PLN</span>
      </div>
      <div v-if="!historyValues.length && !loading" class="empty-chart">
        Historia pojawi się po dodaniu transakcji i pobraniu cen.
      </div>
      <VChart v-else class="main-chart" :option="chartOption" autoresize />
    </section>
    <section class="panel allocation-panel">
      <div class="section-heading">
        <div>
          <p class="panel-kicker">ALOKACJA</p>
          <h2>Rozkład portfela</h2>
        </div>
      </div>
      <div v-if="!summary?.positions.length && !loading" class="empty-allocation">Brak pozycji</div>
      <VChart v-else class="allocation-chart" :option="allocationOption" autoresize />
    </section>
    <section class="panel positions-panel">
      <div class="section-heading">
        <div>
          <p class="panel-kicker">NAJWIĘKSZE POZYCJE</p>
          <h2>Co masz w portfelu</h2>
        </div>
        <button class="text-button" @click="$emit('showHoldings')">Zobacz wszystkie →</button>
      </div>
      <div v-if="!summary?.positions.length && !loading" class="empty-state">
        <div class="empty-icon">+</div>
        <h3>Portfel czeka na pierwszy zakup</h3>
        <p>Dodaj transakcję, aby zacząć śledzić wartość i wynik.</p>
        <button class="button button-primary" @click="$emit('addPurchase')">
          Dodaj pierwszy zakup
        </button>
      </div>
      <div v-else class="position-list">
        <div
          v-for="position in summary?.positions.slice(0, 4)"
          :key="position.instrument.id"
          class="position-row"
        >
          <div class="ticker-badge">{{ position.instrument.ticker.slice(0, 3) }}</div>
          <div class="position-name">
            <strong>{{ position.instrument.ticker }}</strong
            ><span>{{ position.instrument.name }}</span>
          </div>
          <div class="position-weight">
            <div>
              <span :style="{ width: `${Math.min(position.weight_pct ?? 0, 100)}%` }"></span>
            </div>
            <small>{{ formatPercent(position.weight_pct) }}</small>
          </div>
          <div class="position-value">
            <strong>{{ formatCurrency(position.market_value_pln) }}</strong
            ><span :class="isPositive(position.pnl_pln) ? 'positive' : 'negative'">{{
              formatCurrency(position.pnl_pln)
            }}</span>
          </div>
        </div>
      </div>
    </section>
  </section>
</template>
