import { useId, useState } from 'react';
import { formatDate } from '../loop/labels';
import { formatMetric, shortDate } from './format';
import type { TrendSeries } from './types';

const W = 320;
const H = 132;
const PAD = { top: 10, right: 12, bottom: 22, left: 44 };

/** One metric over the chosen period against the user's own baseline (dashed line). A single series and a single
 * axis; the title names the series, so no legend box is needed. Hover shows the day's value. */
export default function TrendChart({ series }: { series: TrendSeries }) {
  const [hover, setHover] = useState<number | null>(null);
  const tableId = useId();
  const points = series.points;
  if (points.length < 2) {
    return <p className="muted small">Tältä jaksolta on liian vähän mittauksia kaavioon.</p>;
  }
  const values = points.map((p) => p.value).concat(series.baseline !== null ? [series.baseline] : []);
  let min = Math.min(...values);
  let max = Math.max(...values);
  const margin = (max - min) * 0.15 || Math.abs(max) * 0.05 || 1;
  min -= margin;
  max += margin;
  const first = new Date(points[0].date).getTime();
  const span = Math.max(1, new Date(points[points.length - 1].date).getTime() - first);
  const x = (iso: string) => PAD.left + ((new Date(iso).getTime() - first) / span) * (W - PAD.left - PAD.right);
  const y = (value: number) => PAD.top + (1 - (value - min) / (max - min)) * (H - PAD.top - PAD.bottom);
  const path = points.map((p, i) => `${i ? 'L' : 'M'}${x(p.date).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
  const ticks = [max - margin, (max + min) / 2, min + margin];
  const active = hover !== null ? points[hover] : null;

  function onMove(event: React.PointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const px = ((event.clientX - rect.left) / rect.width) * W;
    let best = 0;
    points.forEach((p, i) => {
      if (Math.abs(x(p.date) - px) < Math.abs(x(points[best].date) - px)) best = i;
    });
    setHover(best);
  }

  const summary = `${series.label} ${series.weekly ? 'viikkokeskiarvoina' : 'päivittäin'} ${formatDate(points[0].date)}–${formatDate(points[points.length - 1].date)}. `
    + `Oma tasosi ${series.baselineText ?? '–'}, viimeiset 7 päivää ${series.currentText ?? '–'}.`;

  return (
    <div className="trend-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={summary} aria-describedby={tableId}
        onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line className="trend-grid" x1={PAD.left} x2={W - PAD.right} y1={y(tick)} y2={y(tick)} />
            <text className="trend-tick" x={PAD.left - 6} y={y(tick) + 3} textAnchor="end">
              {series.format === 'duration' ? `${(tick / 60).toFixed(1).replace('.', ',')} h` : formatMetric({ ...series, unit: null }, tick)}
            </text>
          </g>
        ))}
        {series.baseline !== null && (
          <g>
            <line className="trend-baseline" x1={PAD.left} x2={W - PAD.right} y1={y(series.baseline)} y2={y(series.baseline)} />
            <text className="trend-baseline-label" x={W - PAD.right} y={y(series.baseline) - 4} textAnchor="end">oma taso</text>
          </g>
        )}
        <path className="trend-line" d={path} />
        <text className="trend-tick" x={PAD.left} y={H - 6}>{shortDate(points[0].date)}</text>
        <text className="trend-tick" x={W - PAD.right} y={H - 6} textAnchor="end">{shortDate(points[points.length - 1].date)}</text>
        {active && (
          <g>
            <line className="trend-crosshair" x1={x(active.date)} x2={x(active.date)} y1={PAD.top} y2={H - PAD.bottom} />
            <circle className="trend-dot" cx={x(active.date)} cy={y(active.value)} r={4} />
          </g>
        )}
      </svg>
      {active && (
        <div className="trend-tooltip" style={{ left: `${(x(active.date) / W) * 100}%` }} role="status">
          <strong>{formatMetric(series, active.value)}</strong>
          <span>{series.weekly ? `viikko ${formatDate(active.date)} asti` : formatDate(active.date)}</span>
        </div>
      )}
      <table id={tableId} className="visually-hidden">
        <caption>{series.label}</caption>
        <tbody>
          {points.map((p) => <tr key={p.date}><th scope="row">{formatDate(p.date)}</th><td>{formatMetric(series, p.value)}</td></tr>)}
        </tbody>
      </table>
    </div>
  );
}
