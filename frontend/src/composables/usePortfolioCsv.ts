import { ref, type Ref } from 'vue';
import { getPortfolio } from '../api';

const formatCsvNumber = (value: unknown, label: string, allowEmpty = false) => {
  if (allowEmpty && (value == null || value === '')) return '';
  if (
    value == null ||
    (typeof value === 'string' && !value.trim()) ||
    !Number.isFinite(Number(value))
  ) {
    throw new Error(`Nieprawidłowa wartość pola „${label}” w danych portfela.`);
  }
  return Number(value).toFixed(2).replace('.', ',');
};

export const usePortfolioCsv = (error: Ref<string>) => {
  const exportingCsv = ref(false);

  const exportPortfolioCsv = async () => {
    exportingCsv.value = true;
    error.value = '';
    try {
      const portfolio = await getPortfolio(null);
      const rows = [
        ['Ticker', 'ISIN', 'Nazwa', 'Waluta', 'Symbol', 'Ilość', 'Wartość PLN'],
        ...portfolio.positions.map(({ instrument, quantity, market_value_pln }) => [
          instrument.ticker,
          instrument.isin,
          instrument.name,
          instrument.currency,
          instrument.symbol,
          formatCsvNumber(quantity, 'Ilość'),
          formatCsvNumber(market_value_pln, 'Wartość PLN', true),
        ]),
      ];
      const csv = `\uFEFF${rows
        .map((row) =>
          row.map((value) => `"${String(value ?? '').replaceAll('"', '""')}"`).join(';'),
        )
        .join('\r\n')}`;
      const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `instrumenty-portfelowe-${new Date().toISOString().slice(0, 10)}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      error.value =
        reason instanceof Error ? reason.message : 'Nie udało się wyeksportować instrumentów.';
    } finally {
      exportingCsv.value = false;
    }
  };

  return { exportingCsv, exportPortfolioCsv };
};
