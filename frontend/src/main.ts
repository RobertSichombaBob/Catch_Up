/**
 * Catch Up front end. Server-rendered Django pages, enhanced by small
 * TypeScript "islands" that attach to data-* attributes. Every page works
 * without JavaScript; this file only makes it smoother.
 *
 * Build: npm run build   (writes ../static/js/app.js)
 */
import { bars, donut, empty, hbars, line } from './charts';
import type { AdminOverview, PaymentStatus, StudentOverview, TutorOverview } from './types';

const $ = <T extends Element = HTMLElement>(sel: string, root: ParentNode = document) => root.querySelector<T>(sel);
const $$ = <T extends Element = HTMLElement>(sel: string, root: ParentNode = document) => Array.from(root.querySelectorAll<T>(sel));
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

document.documentElement.classList.add('js');
document.documentElement.classList.remove('no-js');

/* ---------------------------------------------------------------- Header */
function initHeader(): void {
  const header = $('[data-header]');
  if (!header) return;
  const onScroll = () => header.classList.toggle('scrolled', window.scrollY > 4);
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });
  const toggle = $<HTMLButtonElement>('[data-menu-toggle]', header);
  toggle?.addEventListener('click', () => {
    const open = header.classList.toggle('menu-open');
    toggle.setAttribute('aria-expanded', String(open));
  });
}

function initDropdowns(): void {
  const all = $$('[data-dropdown]');
  const closeAll = (except?: Element) => all.forEach((d) => {
    if (d !== except) {
      d.classList.remove('open');
      $('[data-dropdown-toggle]', d)?.setAttribute('aria-expanded', 'false');
    }
  });
  all.forEach((d) => {
    const btn = $('[data-dropdown-toggle]', d);
    btn?.addEventListener('click', (e) => {
      e.stopPropagation();
      const open = !d.classList.contains('open');
      closeAll(d);
      d.classList.toggle('open', open);
      btn.setAttribute('aria-expanded', String(open));
    });
  });
  document.addEventListener('click', (e) => {
    if (!(e.target as Element).closest('[data-dropdown]')) closeAll();
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeAll(); });
}

/* -------------------------------------------------------------- Messages */
function initMessages(): void {
  $$('.messages .message').forEach((m, i) => {
    const hide = () => { m.classList.add('hide'); window.setTimeout(() => m.remove(), 320); };
    $('button', m)?.addEventListener('click', hide);
    if (!m.classList.contains('error')) window.setTimeout(hide, 6000 + i * 800);
  });
}

/* ------------------------------------------------------ Gentle animation */
function initReveal(): void {
  const items = $$('[data-reveal]');
  if (!('IntersectionObserver' in window) || reducedMotion) {
    items.forEach((el) => el.classList.add('in'));
    return;
  }
  const io = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        const el = entry.target as HTMLElement;
        const siblings = el.parentElement ? Array.from(el.parentElement.children).filter((c) => c.hasAttribute('data-reveal')) : [];
        el.style.transitionDelay = `${Math.min(siblings.indexOf(el), 5) * 70}ms`;
        el.classList.add('in');
        io.unobserve(el);
      }
    });
  }, { rootMargin: '0px 0px -40px 0px', threshold: 0.08 });
  items.forEach((el) => io.observe(el));
}

function initCounters(): void {
  const els = $$('[data-count]');
  if (reducedMotion || !('IntersectionObserver' in window)) return;
  const io = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      const el = entry.target as HTMLElement;
      io.unobserve(el);
      const target = Number(el.dataset.count) || 0;
      if (target < 2) return;
      const start = performance.now();
      const tick = (now: number) => {
        const t = Math.min(1, (now - start) / 900);
        el.textContent = Math.round(target * (1 - Math.pow(1 - t, 3))).toLocaleString();
        if (t < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
  });
  els.forEach((el) => io.observe(el));
}

/* ------------------------------------------------------------------ Tabs */
function initTabs(): void {
  $$('[data-tabs]').forEach((bar) => {
    const scope = bar.parentElement ?? document;
    const tabs = $$<HTMLElement>('[data-tab]', bar);
    const panels = $$<HTMLElement>('[data-panel]', scope);
    const show = (name: string, focus = false) => {
      if (!panels.some((p) => p.dataset.panel === name)) return;
      tabs.forEach((t) => {
        const on = t.dataset.tab === name;
        t.classList.toggle('active', on);
        t.setAttribute('aria-selected', String(on));
        if (on && focus) t.focus();
      });
      panels.forEach((p) => p.classList.toggle('active', p.dataset.panel === name));
    };
    bar.setAttribute('role', 'tablist');
    tabs.forEach((t, i) => {
      t.setAttribute('role', 'tab');
      t.setAttribute('type', 'button');
      t.addEventListener('click', () => {
        show(t.dataset.tab!);
        history.replaceState(null, '', `#${t.dataset.tab}`);
      });
      t.addEventListener('keydown', (e) => {
        const k = (e as KeyboardEvent).key;
        if (k === 'ArrowRight' || k === 'ArrowLeft') {
          const next = tabs[(i + (k === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
          show(next.dataset.tab!, true);
        }
      });
    });
    const fromHash = location.hash.slice(1);
    if (fromHash) show(fromHash);
    // Open the tab holding a form error, so the error is visible.
    const errorPanel = panels.find((p) => p.querySelector('.has-error, .form-error'));
    if (errorPanel) show(errorPanel.dataset.panel!);
  });
}

/* ---------------------------------------------------------- Confirmation */
function initConfirm(): void {
  $$<HTMLFormElement>('form[data-confirm]').forEach((f) => {
    f.addEventListener('submit', (e) => {
      if (!window.confirm(f.dataset.confirm || 'Are you sure?')) e.preventDefault();
    });
  });
  $$<HTMLButtonElement>('[data-confirm-submit]').forEach((b) => {
    b.addEventListener('click', (e) => {
      if (!window.confirm(b.dataset.confirmSubmit || 'Submit?')) e.preventDefault();
    });
  });
  // Stop double submissions (double-charging, duplicate posts) on slow networks.
  $$<HTMLFormElement>('form[method="post" i]').forEach((f) => {
    f.addEventListener('submit', (e) => {
      if (e.defaultPrevented) return;
      if (f.dataset.submitted) { e.preventDefault(); return; }
      f.dataset.submitted = '1';
      window.setTimeout(() => { delete f.dataset.submitted; }, 8000);
    });
  });
}

/* ------------------------------------------------------- Mobile payments */
const PREFIXES: Record<string, string> = { '96': 'MTN', '76': 'MTN', '97': 'AIRTEL', '77': 'AIRTEL', '95': 'ZAMTEL', '75': 'ZAMTEL' };

export function detectNetwork(raw: string): string | null {
  let d = raw.replace(/\D/g, '');
  if (d.startsWith('260')) d = d.slice(3);
  if (d.startsWith('0')) d = d.slice(1);
  return d.length >= 2 ? PREFIXES[d.slice(0, 2)] ?? null : null;
}

function initCheckout(): void {
  const phone = $<HTMLInputElement>('input[name="phone"]');
  const radios = $$<HTMLInputElement>('input[name="network"]');
  if (!phone || !radios.length) return;
  phone.setAttribute('inputmode', 'tel');
  phone.setAttribute('autocomplete', 'tel');
  phone.addEventListener('input', () => {
    const net = detectNetwork(phone.value);
    const r = radios.find((x) => x.value === net);
    if (r && !r.checked) {
      r.checked = true;
      r.dispatchEvent(new Event('change', { bubbles: true }));
    }
  });
}

function initPaymentPolling(): void {
  const box = $('[data-poll-url]');
  if (!box) return;
  const url = box.dataset.pollUrl!;
  const started = Date.now();
  let delay = 2500;
  const poll = async () => {
    if (document.hidden) { window.setTimeout(poll, delay); return; }
    try {
      const res = await fetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
      if (res.ok) {
        const data = (await res.json()) as PaymentStatus;
        if (data.final) { window.location.reload(); return; }
      }
    } catch { /* offline for a moment: try again */ }
    if (Date.now() - started < 4 * 60 * 1000) {
      delay = Math.min(delay * 1.25, 8000);
      window.setTimeout(poll, delay);
    }
  };
  window.setTimeout(poll, delay);
}

/* ------------------------------------------------------------- Classroom */
function initMarkAll(): void {
  $$<HTMLButtonElement>('[data-mark-all]').forEach((b) => {
    b.addEventListener('click', () => {
      const scope = b.closest('form') ?? b.closest('.card') ?? document;
      $$<HTMLInputElement>(`input[type="radio"][value="${b.dataset.markAll}"]`, scope).forEach((r) => { r.checked = true; });
    });
  });
}

function initTimer(): void {
  const form = $<HTMLFormElement>('form[data-timer]');
  if (!form) return;
  const display = $('[data-timer-display]', form);
  const key = `timer:${location.pathname}`;
  let deadline = 0;
  try { deadline = Number(sessionStorage.getItem(key)) || 0; } catch { /* private mode */ }
  if (!deadline || deadline < Date.now()) {
    deadline = Date.now() + Number(form.dataset.timer) * 60 * 1000;
    try { sessionStorage.setItem(key, String(deadline)); } catch { /* ignore */ }
  }
  form.addEventListener('submit', () => { try { sessionStorage.removeItem(key); } catch { /* ignore */ } });
  const tick = () => {
    const left = Math.max(0, deadline - Date.now());
    const m = Math.floor(left / 60000), s = Math.floor((left % 60000) / 1000);
    if (display) {
      display.textContent = `${m}:${String(s).padStart(2, '0')} left`;
      display.classList.toggle('low', left < 120000);
    }
    if (left <= 0) {
      try { sessionStorage.removeItem(key); } catch { /* ignore */ }
      $$('[data-confirm-submit]', form).forEach((b) => b.removeAttribute('data-confirm-submit'));
      form.requestSubmit ? form.requestSubmit() : form.submit();
      return;
    }
    window.setTimeout(tick, 1000);
  };
  tick();
}

function initUploads(): void {
  $$<HTMLFormElement>('[data-upload]').forEach((form) => {
    const input = $<HTMLInputElement>('input[type="file"]', form);
    if (!input) return;
    ['dragenter', 'dragover'].forEach((ev) => form.addEventListener(ev, (e) => { e.preventDefault(); form.classList.add('dragging'); }));
    ['dragleave', 'drop'].forEach((ev) => form.addEventListener(ev, () => form.classList.remove('dragging')));
    form.addEventListener('drop', (e) => {
      e.preventDefault();
      const files = (e as DragEvent).dataTransfer?.files;
      if (files && files.length) {
        input.files = files;
        input.dispatchEvent(new Event('change'));
      }
    });
    input.addEventListener('change', () => {
      const f = input.files?.[0];
      const title = $<HTMLInputElement>('input[name="title"]', form);
      if (f && title && !title.value) title.value = f.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ');
      if (f && f.size > 25 * 1024 * 1024) window.alert('This file is larger than 25 MB. Please compress it or split it.');
    });
    // Real progress bar via XHR; falls back to a normal submit on any problem.
    const bar = document.createElement('div');
    bar.className = 'upload-progress';
    bar.innerHTML = '<span></span>';
    form.appendChild(bar);
    form.addEventListener('submit', (e) => {
      if (!input.files?.length || !window.FormData) return;
      e.preventDefault();
      const btn = $<HTMLButtonElement>('button[type="submit"], button:not([type])', form);
      if (btn) { btn.disabled = true; btn.textContent = 'Uploading…'; }
      form.classList.add('uploading');
      const xhr = new XMLHttpRequest();
      xhr.open('POST', form.action || location.href);
      xhr.upload.addEventListener('progress', (ev) => {
        if (ev.lengthComputable) (bar.firstElementChild as HTMLElement).style.width = `${(ev.loaded / ev.total) * 100}%`;
      });
      const action = new URL(form.action || location.href, location.href).href;
      xhr.onload = () => {
        if (xhr.responseURL && xhr.responseURL !== action) {
          window.location.href = xhr.responseURL;  // followed the redirect after a successful upload
        } else {
          document.open();  // the form came back with errors: show it
          document.write(xhr.responseText);
          document.close();
        }
      };
      xhr.onerror = () => { form.classList.remove('uploading'); HTMLFormElement.prototype.submit.call(form); };
      xhr.send(new FormData(form));
    });
  });
}

function initReader(): void {
  $$('.side-toggle').forEach((b) => b.addEventListener('click', () => b.closest('.reader')?.classList.toggle('side-open')));
}

/* ---------------------------------------------------------------- Charts */
const cache = new Map<string, Promise<unknown>>();
function getJSON<T>(url: string): Promise<T> {
  if (!cache.has(url)) {
    cache.set(url, fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } }).then((r) => {
      if (!r.ok) throw new Error(String(r.status));
      return r.json();
    }));
  }
  return cache.get(url) as Promise<T>;
}

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string));

type Renderer = (el: HTMLElement, data: any) => void;  // eslint-disable-line @typescript-eslint/no-explicit-any
const RENDERERS: Record<string, Renderer> = {
  child: (el, d: StudentOverview) => {
    const series = (el.dataset.series ?? 'lessons_per_week') as 'lessons_per_week' | 'grades';
    line(el, d[series], { title: el.dataset.title });
  },
  'admin-revenue': (el, d: AdminOverview) => {
    line(el, d.revenue, { prefix: 'K', extra: { points: d.forecast, color: '#f28c28', dashed: true, band: d.forecast } });
    if (!d.revenue.length && d.forecast_message) empty(el, d.forecast_message);
  },
  'admin-split': (el, d: AdminOverview) => donut(el, d.split, { prefix: 'K' }),
  'admin-hours': (el, d: AdminOverview) => bars(el, d.hours),
  'admin-model': (el, d: AdminOverview) => {
    const m = d.model;
    const metrics = Object.entries(m.metrics || {}).filter(([, v]) => typeof v === 'number')
      .map(([k, v]) => `<span class="badge">${esc(k)}: ${(v as number) <= 1 ? (v as number).toFixed(2) : v}</span>`).join(' ');
    el.innerHTML = `<h4 class="chart-title">What drives dropout risk <span class="muted small">(${m.source === 'trained' ? 'trained on your data' : 'starting weights until there is enough data'})</span></h4>`;
    const holder = document.createElement('div');
    el.appendChild(holder);
    hbars(holder, m.importance.map((r) => ({ label: r.feature, value: r.weight })));
    el.insertAdjacentHTML('beforeend', `<div class="row small" style="margin-top:8px">${metrics}${m.trained_at ? `<span class="muted">Trained ${new Date(m.trained_at).toLocaleDateString()}</span>` : ''}</div>`);
  },
  'tutor-earnings': (el, d: TutorOverview) => {
    el.innerHTML = '';
    const a = document.createElement('div');
    const b = document.createElement('div');
    el.append(a, b);
    line(a, d.earnings, { title: 'Your earnings per week (your 50%)', prefix: 'K' });
    if (d.by_course.some((c) => c.value)) {
      b.style.marginTop = '14px';
      hbars(b, d.by_course, { title: 'By course', prefix: 'K' });
    }
  },
  'tutor-risk': (el, d: TutorOverview) => {
    if (!d.risk.length) {
      el.innerHTML = '<p class="muted small">Nobody is flagged right now. Nice.</p>';
      return;
    }
    el.innerHTML = `<ul class="risk-list">${d.risk.map((r) => `<li><span class="row-between"><strong>${esc(r.student)}</strong><span class="risk risk-${r.level}">${Math.round(r.risk * 100)}%</span></span><span class="muted small">${esc(r.course)}${r.reasons.length ? ' · ' + esc(r.reasons.join('; ')) : ''}</span></li>`).join('')}</ul>`;
  },
};

function initCharts(): void {
  const els = $$('[data-chart]');
  if (!els.length) return;
  const render = (el: HTMLElement) => {
    const kind = el.dataset.chart!;
    const fn = RENDERERS[kind];
    const src = el.dataset.src;
    if (!fn || !src) return;
    if (!el.innerHTML.trim()) el.innerHTML = '<div class="skeleton"></div>';
    getJSON(src).then((data) => fn(el, data)).catch(() => empty(el, 'Could not load this chart. Refresh to try again.'));
  };
  if (!('IntersectionObserver' in window)) { els.forEach(render); return; }
  const io = new IntersectionObserver((entries) => entries.forEach((e) => {
    if (e.isIntersecting) { io.unobserve(e.target); render(e.target as HTMLElement); }
  }), { rootMargin: '200px' });
  els.forEach((el) => io.observe(el));
}

/* ------------------------------------------------------------------ Boot */
function boot(): void {
  initHeader();
  initDropdowns();
  initMessages();
  initReveal();
  initCounters();
  initTabs();
  initConfirm();
  initCheckout();
  initPaymentPolling();
  initMarkAll();
  initTimer();
  initUploads();
  initReader();
  initCharts();
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();
