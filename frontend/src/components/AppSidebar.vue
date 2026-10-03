<script setup lang="ts">
  import type { Portfolio } from '../api';

  defineProps<{
    portfolios: Portfolio[];
    activePortfolioId: number | null;
  }>();

  defineEmits<{
    createPortfolio: [];
  }>();
</script>

<template>
  <aside class="sidebar">
    <div class="brand"><span class="brand-mark">P</span><span>portfel</span></div>
    <nav class="nav-list">
      <RouterLink to="/" class="nav-link" :class="{ active: activePortfolioId === null }">
        Majątek <span>Σ</span>
      </RouterLink>
      <div class="sidebar-label">Portfele</div>
      <div class="portfolio-nav">
        <div v-for="portfolio in portfolios" :key="portfolio.id" class="portfolio-nav-row">
          <RouterLink
            :to="`/portfolios/${portfolio.id}`"
            class="nav-link"
            :class="{ active: activePortfolioId === portfolio.id }"
          >
            {{ portfolio.name }}
          </RouterLink>
        </div>
      </div>
      <button class="new-portfolio-button" @click="$emit('createPortfolio')">+ Nowy portfel</button>
    </nav>
    <div class="sidebar-bottom">
      <div class="status-dot"></div>
      <span>Portfel lokalny</span><small>PLN · bez logowania</small>
    </div>
  </aside>
</template>
