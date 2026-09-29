import type { TrendSeries } from './types';

/** Finnish formatting that mirrors backend/app/wellbeing/catalog.py (no percentages anywhere). */
export function formatMetric(series: Pick<TrendSeries, 'format' | 'unit' | 'metric'>, value: number | null): string {
  if (value === null || Number.isNaN(value)) return '–';
  if (series.format === 'duration') {
    const minutes = Math.round(value);
    return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')} min`;
  }
  const text = series.format === 'decimal1'
    ? value.toFixed(1).replace('.', ',')
    : Math.round(value).toLocaleString('fi-FI');
  return series.metric === 'steps' || !series.unit ? text : `${text} ${series.unit}`;
}

/** "1.9.2026 klo 08:16" for a sync time; a time without a zone is the demo clock's own local time. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '–';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const time = date.toLocaleTimeString('fi-FI', { hour: '2-digit', minute: '2-digit' }).replace('.', ':');
  return `${date.getDate()}.${date.getMonth() + 1}.${date.getFullYear()} klo ${time}`;
}

export function shortDate(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number);
  return `${day}.${month}.${String(year).slice(2)}`;
}
