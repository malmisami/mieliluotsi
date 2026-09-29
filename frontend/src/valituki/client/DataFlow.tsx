import { useEffect } from 'react';
import type { RefObject } from 'react';

export interface Flow { id: string; label: string; target: 'profile' | 'match'; row?: string }

const SVG = 'http://www.w3.org/2000/svg';

/** Data leaving the phone: for every flow a labelled chip travels along a curve from the phone to the profile row or the
    matching table it updates. Drawn imperatively on a layer over the client stage, then removed; no layout change. */
export function DataFlow({ flows, asideRef }: { flows: Flow[]; asideRef: RefObject<HTMLElement | null> }) {
  useEffect(() => {
    const aside = asideRef.current;
    const stage = aside?.parentElement;
    const phone = stage?.querySelector('.phone');
    if (!aside || !stage || !phone || !flows.length) return undefined;
    // Played even with "reduce motion" (e.g. Windows with animation effects off): it is the demo's way of showing where the
    // data goes – short, one-off and never looping.
    if (getComputedStyle(stage).flexDirection === 'column') return undefined; // phone above the panel: no room for a path

    const box = stage.getBoundingClientRect();
    const from = phone.getBoundingClientRect();
    const panel = aside.getBoundingClientRect();
    const layer = document.createElement('div');
    layer.className = 'df-layer';
    const svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('width', String(box.width));
    svg.setAttribute('height', String(box.height));
    layer.appendChild(svg);
    stage.appendChild(layer);

    const running: Animation[] = [];
    flows.forEach((flow, i) => {
      const target = (flow.row && aside.querySelector(`[data-row="${flow.row}"]`))
        || aside.querySelector(flow.target === 'match' ? '.bm-card' : '.bp-doc') || aside;
      const to = target.getBoundingClientRect();
      const sx = from.right - box.left - 16;
      const sy = from.top - box.top + from.height * (0.3 + 0.07 * (i % 5));
      const ex = to.left - box.left + 14;
      const top = panel.top - box.top + 12;
      const bottom = panel.bottom - box.top - 12;
      const ey = Math.min(bottom, Math.max(top, to.top - box.top + Math.min(to.height / 2, 16)));
      const bend = (ex - sx) * 0.55;
      const d = `M ${sx} ${sy} C ${sx + bend} ${sy}, ${ex - bend} ${ey}, ${ex} ${ey}`;
      const delay = i * 170;

      const path = document.createElementNS(SVG, 'path');
      path.setAttribute('d', d);
      path.setAttribute('class', `df-path df-${flow.target}`);
      svg.appendChild(path);
      running.push(path.animate([{ opacity: 0, strokeDashoffset: 0 }, { opacity: 0.75, offset: 0.2 }, { opacity: 0.75, offset: 0.75 },
        { opacity: 0, strokeDashoffset: -60 }], { duration: 1700, delay, fill: 'both' }));

      const chip = document.createElement('span');
      chip.className = `df-chip df-${flow.target}`;
      chip.textContent = flow.label;
      chip.style.offsetPath = `path('${d}')`;
      layer.appendChild(chip);
      running.push(chip.animate([
        { offsetDistance: '0%', opacity: 0, transform: 'scale(0.7)' },
        { opacity: 1, transform: 'scale(1)', offset: 0.12 },
        { opacity: 1, offset: 0.86 },
        { offsetDistance: '100%', opacity: 0, transform: 'scale(0.85)' },
      ], { duration: 1350, delay: delay + 120, easing: 'cubic-bezier(0.45, 0.05, 0.3, 1)', fill: 'both' }));
    });

    void Promise.allSettled(running.map((a) => a.finished)).then(() => layer.remove());
    return () => layer.remove();
  }, [flows, asideRef]);

  return null;
}
