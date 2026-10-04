import { createRouter, createWebHistory } from 'vue-router';
import DashboardOverview from '../views/DashboardOverview.vue';
import HoldingsView from '../views/HoldingsView.vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: DashboardOverview },
    { path: '/holdings', name: 'aggregate-holdings', component: HoldingsView },
    { path: '/portfolios/:portfolioId', name: 'portfolio-overview', component: DashboardOverview },
    { path: '/portfolios/:portfolioId/holdings', name: 'portfolio-holdings', component: HoldingsView },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
});

export default router;
