import { computed, ref, type ComputedRef, type Ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  createPortfolio as createPortfolioRequest,
  deletePortfolio as deletePortfolioRequest,
  getPortfolios,
  renamePortfolio as renamePortfolioRequest,
  type Portfolio,
} from '../api';

export const usePortfolioNavigation = () => {
  const route = useRoute();
  const router = useRouter();
  const activeView = computed<'overview' | 'holdings'>(() =>
    route.name === 'portfolio-holdings' || route.name === 'aggregate-holdings'
      ? 'holdings'
      : 'overview',
  );
  const activePortfolioId = computed<number | null>(() => {
    if (route.name !== 'portfolio-overview' && route.name !== 'portfolio-holdings') return null;
    const id = Number(route.params.portfolioId);
    return Number.isInteger(id) && id > 0 ? id : null;
  });
  const showHoldings = () =>
    router.push(
      activePortfolioId.value ? `/portfolios/${activePortfolioId.value}/holdings` : '/holdings',
    );

  return { activeView, activePortfolioId, showHoldings };
};

export const usePortfolioCatalog = (
  activePortfolioId: ComputedRef<number | null>,
  error: Ref<string>,
  reloadData: () => Promise<unknown>,
) => {
  const router = useRouter();
  const portfolios = ref<Portfolio[]>([]);
  const currentPortfolio = computed(() =>
    portfolios.value.find((portfolio) => portfolio.id === activePortfolioId.value),
  );
  const portfolioName = computed(() => currentPortfolio.value?.name ?? 'Majątek');

  const loadPortfolios = async () => {
    try {
      portfolios.value = await getPortfolios();
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : 'Nie udało się pobrać portfeli.';
    }
  };

  const createPortfolio = async () => {
    const name = window.prompt('Nazwa nowego portfela');
    if (!name?.trim()) return;
    try {
      const portfolio = await createPortfolioRequest(name.trim());
      await loadPortfolios();
      await router.push(`/portfolios/${portfolio.id}`);
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : 'Nie udało się utworzyć portfela.';
    }
  };

  const renamePortfolio = async (portfolio: Portfolio) => {
    const name = window.prompt('Nowa nazwa portfela', portfolio.name);
    if (!name?.trim() || name.trim() === portfolio.name) return;
    try {
      await renamePortfolioRequest(portfolio.id, name.trim());
      await loadPortfolios();
    } catch (reason) {
      error.value =
        reason instanceof Error ? reason.message : 'Nie udało się zmienić nazwy portfela.';
    }
  };

  const deletePortfolio = async (portfolio: Portfolio) => {
    const confirmed = window.confirm(
      `Usunięcie portfela "${portfolio.name}" trwale usunie wszystkie jego transakcje i wpłaty. Kontynuować?`,
    );
    if (!confirmed) return;
    try {
      await deletePortfolioRequest(portfolio.id);
      await loadPortfolios();
      if (activePortfolioId.value === portfolio.id) {
        await router.push('/');
        await reloadData();
      } else if (activePortfolioId.value === null) {
        await reloadData();
      }
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : 'Nie udało się usunąć portfela.';
    }
  };

  const clearPortfolios = () => {
    portfolios.value = [];
  };

  return {
    portfolios,
    currentPortfolio,
    portfolioName,
    loadPortfolios,
    createPortfolio,
    renamePortfolio,
    deletePortfolio,
    clearPortfolios,
  };
};
