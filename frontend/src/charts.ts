/**
 * Tiny dependency-free SVG charts: line/area, bars, donut and horizontal bars.
 * Accessible (role="img" + aria-label), responsive (viewBox), with tooltips.
 */
import type { Point, Slice } from './types';

const NS = 'http://www.w3.org/2000/svg';
export const PALETTE = ['#0e7a4f', '#f28c28', '#2563eb', '#6d28d9', '#c2410c', '#0891b2', '#be185d', '#65a30d'];

function svg(tag: string, attrs: Record<string, string | number> = {}): SVGElement {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  return el;
}

function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string));
}

export function fmt(n: number, prefix = ''): string {
  const abs = Math.abs(n);
  const s = abs >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : abs >= 1e4 ? (n / 1e3).toFixed(1) + 'k'
    : Number.isInteger(n) ? n.toLocaleString() : n.toFixed(1);
  return prefix + s;
}

function shortDate(iso: string): string {
  const d = new Date(iso + (iso.length === 10 ? 'T00:00:00' : ''));
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

function frame(host: HTMLElement, title: string | undefined, label: string): { root: SVGSVGElement; tip: HTMLDivElement } {
  host.innerHTML = '';
  host.style.position = host.style.position || 'relative';
  if (title) {
    const h = document.createElement('h4');
    h.className = 'chart-title';
    h.textContent = title;
    host.appendChild(h);
  }
  const root = svg('svg', { viewBox: '0 0 600 220', role: 'img', 'aria-label': label, preserveAspectRatio: 'none' }) as SVGSVGElement;
  root.style.height = '220px';
  host.appendChild(root);
  const tip = document.createElement('div');
  tip.className = 'chart-tip';
  host.appendChild(tip);
  return { root, tip };
}

function showTip(host: HTMLElement, tip: HTMLDivElement, root: SVGSVGElement, x: number, y: number, html: string): void {
  const r = root.getBoundingClientRect();
  const hr = host.getBoundingClientRect();
  tip.innerHTML = html;
  tip.style.left = `${r.left - hr.left + (x / 600) * r.width}px`;
  tip.style.top = `${r.top - hr.top + (y / 220) * r.height}px`;
  tip.classList.add('show');
}

export function empty(host: HTMLElement, message: string, title?: string): void {
  host.innerHTML = (title ? `<h4 class="chart-title">${esc(title)}</h4>` : '') + `<div class="chart-empty">${esc(message)}</div>`;
}

interface LineOpts { title?: string; prefix?: string; color?: string; extra?: { points: Point[]; color: string; dashed?: boolean; band?: { low: number; high: number }[] } }

/** Line + soft area. Optional extra series (e.g. a forecast with a band). */
export function line(host: HTMLElement, points: Point[], opts: LineOpts = {}): void {
  const all = points.concat(opts.extra?.points ?? []);
  if (!all.length || all.every((p) => !p.y)) {
    empty(host, 'No data yet. This fills in as activity grows.', opts.title);
    return;
  }
  const { root, tip } = frame(host, opts.title, opts.title ?? 'Line chart');
  const pad = { l: 44, r: 12, t: 12, b: 26 };
  const bandHigh = opts.extra?.band?.map((b) => b.high) ?? [];
  const max = Math.max(1, ...all.map((p) => p.y), ...bandHigh) * 1.1;
  const n = all.length;
  const X = (i: number) => pad.l + (n === 1 ? 0.5 : i / (n - 1)) * (600 - pad.l - pad.r);
  const Y = (v: number) => 220 - pad.b - (v / max) * (220 - pad.t - pad.b);
  const color = opts.color ?? PALETTE[0];
  for (let g = 0; g <= 4; g++) {
    const v = (max / 4) * g;
    root.appendChild(svg('line', { x1: pad.l, x2: 600 - pad.r, y1: Y(v), y2: Y(v), stroke: '#e3e7ec', 'stroke-width': 1 }));
    const t = svg('text', { x: pad.l - 6, y: Y(v) + 4, 'text-anchor': 'end', 'font-size': 11, fill: '#5c677d' });
    t.textContent = fmt(Math.round(v), opts.prefix);
    root.appendChild(t);
  }
  const step = Math.max(1, Math.ceil(n / 6));
  all.forEach((p, i) => {
    if (i % step === 0 || i === n - 1) {
      const t = svg('text', { x: X(i), y: 214, 'text-anchor': 'middle', 'font-size': 11, fill: '#5c677d' });
      t.textContent = shortDate(p.x);
      root.appendChild(t);
    }
  });
  const path = (pts: Point[], offset: number) => pts.map((p, i) => `${i ? 'L' : 'M'}${X(i + offset).toFixed(1)},${Y(p.y).toFixed(1)}`).join(' ');
  if (points.length) {
    const id = `g${Math.random().toString(36).slice(2, 8)}`;
    const defs = svg('defs');
    const grad = svg('linearGradient', { id, x1: 0, x2: 0, y1: 0, y2: 1 });
    grad.appendChild(svg('stop', { offset: '0%', 'stop-color': color, 'stop-opacity': 0.25 }));
    grad.appendChild(svg('stop', { offset: '100%', 'stop-color': color, 'stop-opacity': 0 }));
    defs.appendChild(grad);
    root.appendChild(defs);
    const d = path(points, 0);
    root.appendChild(svg('path', { d: `${d} L${X(points.length - 1)},${Y(0)} L${X(0)},${Y(0)} Z`, fill: `url(#${id})` }));
    const stroke = svg('path', { d, fill: 'none', stroke: color, 'stroke-width': 2.5, 'stroke-linejoin': 'round', 'stroke-linecap': 'round', class: 'draw' });
    root.appendChild(stroke);
  }
  const extra = opts.extra;
  if (extra && extra.points.length) {
    const off = points.length;
    if (extra.band && extra.band.length) {
      const up = extra.band.map((b, i) => `${i ? 'L' : 'M'}${X(i + off)},${Y(b.high)}`).join(' ');
      const down = extra.band.map((b, i) => `L${X(i + off)},${Y(b.low)}`).reverse().join(' ');
      root.appendChild(svg('path', { d: `${up} ${down} Z`, fill: extra.color, opacity: 0.12 }));
    }
    const joined = points.length ? [points[points.length - 1], ...extra.points] : extra.points;
    root.appendChild(svg('path', { d: path(joined, points.length ? off - 1 : 0), fill: 'none', stroke: extra.color, 'stroke-width': 2.5, 'stroke-dasharray': extra.dashed ? '6 5' : '0' }));
  }
  // Hover targets.
  all.forEach((p, i) => {
    const isExtra = i >= points.length;
    const dot = svg('circle', { cx: X(i), cy: Y(p.y), r: 4, fill: '#fff', stroke: isExtra ? extra!.color : color, 'stroke-width': 2, class: 'dot' });
    const hit = svg('rect', { x: X(i) - 600 / n / 2, y: 0, width: 600 / n, height: 220, fill: 'transparent' });
    hit.addEventListener('mouseenter', () => showTip(host, tip, root, X(i), Y(p.y), `<strong>${fmt(p.y, opts.prefix)}</strong> · ${esc(p.label ?? shortDate(p.x))}${isExtra ? ' (forecast)' : ''}`));
    hit.addEventListener('mouseleave', () => tip.classList.remove('show'));
    root.appendChild(dot);
    root.appendChild(hit);
  });
}

/** Vertical bars for categories (e.g. attendance per session, payments by hour). */
export function bars(host: HTMLElement, items: Slice[], opts: { title?: string; prefix?: string; suffix?: string; max?: number } = {}): void {
  if (!items.length || items.every((i) => !i.value)) {
    empty(host, 'No data yet.', opts.title);
    return;
  }
  const { root, tip } = frame(host, opts.title, opts.title ?? 'Bar chart');
  const pad = { l: 36, r: 8, t: 10, b: 26 };
  const max = opts.max ?? Math.max(1, ...items.map((i) => i.value)) * 1.1;
  const w = (600 - pad.l - pad.r) / items.length;
  const H = 220 - pad.t - pad.b;
  for (let g = 0; g <= 4; g++) {
    const y = pad.t + H - (H * g) / 4;
    root.appendChild(svg('line', { x1: pad.l, x2: 600 - pad.r, y1: y, y2: y, stroke: '#e3e7ec' }));
    const t = svg('text', { x: pad.l - 6, y: y + 4, 'text-anchor': 'end', 'font-size': 11, fill: '#5c677d' });
    t.textContent = fmt(Math.round((max * g) / 4));
    root.appendChild(t);
  }
  const step = Math.max(1, Math.ceil(items.length / 12));
  items.forEach((it, i) => {
    const h = (it.value / max) * H;
    const x = pad.l + i * w + w * 0.15;
    const rect = svg('rect', { x, y: pad.t + H - h, width: w * 0.7, height: Math.max(0, h), rx: 4, fill: PALETTE[0], class: 'bar' });
    rect.addEventListener('mouseenter', () => showTip(host, tip, root, x + w * 0.35, pad.t + H - h, `<strong>${opts.prefix ?? ''}${fmt(it.value)}${opts.suffix ?? ''}</strong> · ${esc(it.label)}`));
    rect.addEventListener('mouseleave', () => tip.classList.remove('show'));
    root.appendChild(rect);
    if (i % step === 0) {
      const t = svg('text', { x: x + w * 0.35, y: 214, 'text-anchor': 'middle', 'font-size': 11, fill: '#5c677d' });
      t.textContent = it.label.length > 10 ? it.label.slice(0, 9) + '…' : it.label;
      root.appendChild(t);
    }
  });
}

/** Donut with a legend, e.g. the tutor / platform / fees split. */
export function donut(host: HTMLElement, items: Slice[], opts: { title?: string; prefix?: string } = {}): void {
  const total = items.reduce((s, i) => s + i.value, 0);
  if (!total) {
    empty(host, 'No sales yet.', opts.title);
    return;
  }
  host.innerHTML = '';
  if (opts.title) host.insertAdjacentHTML('beforeend', `<h4 class="chart-title">${esc(opts.title)}</h4>`);
  const root = svg('svg', { viewBox: '0 0 200 200', role: 'img', 'aria-label': opts.title ?? 'Donut chart' }) as SVGSVGElement;
  root.style.maxWidth = '200px';
  root.style.margin = '0 auto';
  root.style.display = 'block';
  const R = 80, C = 2 * Math.PI * R;
  let acc = 0;
  items.forEach((it, i) => {
    const frac = it.value / total;
    root.appendChild(svg('circle', { cx: 100, cy: 100, r: R, fill: 'none', stroke: PALETTE[i % PALETTE.length], 'stroke-width': 26,
      'stroke-dasharray': `${frac * C} ${C}`, 'stroke-dashoffset': -acc * C, transform: 'rotate(-90 100 100)' }));
    acc += frac;
  });
  const t = svg('text', { x: 100, y: 96, 'text-anchor': 'middle', 'font-size': 22, 'font-weight': 800, fill: '#0d1b2a' });
  t.textContent = fmt(total, opts.prefix);
  const s = svg('text', { x: 100, y: 118, 'text-anchor': 'middle', 'font-size': 11, fill: '#5c677d' });
  s.textContent = 'total';
  root.appendChild(t);
  root.appendChild(s);
  host.appendChild(root);
  const legend = document.createElement('div');
  legend.className = 'chart-legend';
  legend.innerHTML = items.map((it, i) => `<span><i style="background:${PALETTE[i % PALETTE.length]}"></i>${esc(it.label)}: ${fmt(it.value, opts.prefix)} (${Math.round((it.value / total) * 100)}%)</span>`).join('');
  host.appendChild(legend);
}

/** Horizontal bars: feature importance, per-course earnings, progress. */
export function hbars(host: HTMLElement, items: Slice[], opts: { title?: string; prefix?: string; suffix?: string; max?: number } = {}): void {
  if (!items.length) {
    empty(host, 'No data yet.', opts.title);
    return;
  }
  const max = opts.max ?? Math.max(1e-9, ...items.map((i) => Math.abs(i.value)));
  host.innerHTML = (opts.title ? `<h4 class="chart-title">${esc(opts.title)}</h4>` : '') + items.map((it, i) => {
    const pct = Math.min(100, (Math.abs(it.value) / max) * 100);
    const col = it.value < 0 ? '#2563eb' : PALETTE[i === 0 ? 0 : 0];
    return `<div class="bar-row"><span title="${esc(it.label)}">${esc(it.label.length > 20 ? it.label.slice(0, 19) + '…' : it.label)}</span>` +
      `<span class="bar-track"><span class="bar-fill" style="width:${pct}%;background:${col}"></span></span>` +
      `<span class="small muted">${opts.prefix ?? ''}${fmt(it.value)}${opts.suffix ?? ''}</span></div>`;
  }).join('');
}
