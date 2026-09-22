import { createRouter, createWebHistory } from "vue-router";
import DashboardOverview from "../views/DashboardOverview.vue";
import HoldingsView from "../views/HoldingsView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "overview", component: DashboardOverview },
    { path: "/holdings", name: "holdings", component: HoldingsView },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});

export default router;