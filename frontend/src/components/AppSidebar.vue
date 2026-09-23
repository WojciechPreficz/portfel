<script setup lang="ts">
  defineProps<{
    activeView: 'overview' | 'holdings';
    positionCount: number;
  }>();
</script>

<template>
  <aside class="sidebar">
    <div class="brand"><span class="brand-mark">P</span><span>portfel</span></div>
    <div class="sidebar-label">Widok</div>
    <nav class="nav-list">
      <RouterLink to="/" :class="{ active: activeView === 'overview' }"
        >Przegląd <span>01</span></RouterLink
      >
      <RouterLink to="/holdings" :class="{ active: activeView === 'holdings' }"
        >Pozycje <span>{{ positionCount }}</span></RouterLink
      >
    </nav>
    <div class="sidebar-bottom">
      <div class="status-dot"></div>
      <span>Portfel lokalny</span><small>PLN · bez logowania</small>
    </div>
  </aside>
</template>
