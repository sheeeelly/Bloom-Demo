const catEl = document.getElementById('dash-cat');
const warnEl = document.getElementById('dash-warn');
const statsEl = document.getElementById('dash-stats');
const sitesEl = document.getElementById('dash-sites');
const bulletsEl = document.getElementById('dash-bullets');
const gapsEl = document.getElementById('dash-gaps');
const funnelEl = document.getElementById('dash-funnel');
const ownEl = document.getElementById('dash-own');
const ownBlockEl = document.getElementById('dash-own-block');
const subEl = document.getElementById('dash-sub');
const eyebrowEl = document.getElementById('dash-eyebrow');
const extHintEl = document.getElementById('dash-ext-hint');
const briefMetaEl = document.getElementById('dash-brief-meta');

const DIM_ZH = {
  fabric: '面料',
  dressLength: '裙长',
  neckline: '领型',
  features: '设计',
  silhouette: '廓形',
  sleeve: '袖型',
  waistline: '腰线',
  colorFamily: '颜色',
};

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function fmt(n) {
  if (n == null || n === '') return '—';
  const num = Number(n);
  if (Number.isNaN(num)) return String(n);
  return num.toLocaleString('en-US');
}

function cleanMd(text) {
  return String(text || '')
    .replace(/\*\*/g, '')
    .replace(/`/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function kpiCard({ value, label, note, tone, unknown }) {
  const display = unknown ? 'unknown' : fmt(value);
  return `<article class="dash-kpi dash-kpi--${esc(tone || 'neutral')}${unknown ? ' is-unknown' : ''}">
    <div class="dash-kpi__label">${esc(label)}</div>
    <div class="dash-kpi__value">${esc(display)}</div>
    ${note ? `<div class="dash-kpi__note">${esc(note)}</div>` : ''}
  </article>`;
}

function renderSites(sites) {
  if (!sites.length) {
    sitesEl.hidden = true;
    sitesEl.innerHTML = '';
    return;
  }
  const max = Math.max(...sites.map((s) => Number(s.delist || 0) + Number(s.new || 0)), 1);
  sitesEl.hidden = false;
  sitesEl.innerHTML = sites
    .map((s) => {
      const neu = Number(s.new || 0);
      const off = Number(s.delist || 0);
      return `<div class="dash-site">
        <div class="dash-site__name">${esc(s.site)}</div>
        <div class="dash-site__bars">
          <span class="dash-site__bar dash-site__bar--new" style="width:${Math.max(6, (neu / max) * 100)}%" title="上新 ${neu}"></span>
          <span class="dash-site__bar dash-site__bar--off" style="width:${Math.max(off ? 6 : 0, (off / max) * 100)}%" title="下架 ${off}"></span>
        </div>
        <div class="dash-site__nums"><em>+${fmt(neu)}</em> / −${fmt(off)}</div>
      </div>`;
    })
    .join('');
}

function renderBriefs(bullets) {
  if (!bullets.length) {
    bulletsEl.innerHTML = '<li class="dash-brief dash-brief--empty">暂无周报摘要</li>';
    return;
  }
  bulletsEl.innerHTML = bullets
    .slice(0, 3)
    .map((raw, i) => {
      const text = cleanMd(raw);
      const cut = text.indexOf('，');
      const title = cut > 8 && cut < 36 ? text.slice(0, cut) : text.slice(0, 22);
      const body = cut > 8 && cut < 36 ? text.slice(cut + 1) : text;
      return `<li class="dash-brief">
        <span class="dash-brief__idx">${String(i + 1).padStart(2, '0')}</span>
        <div>
          <strong>${esc(title)}</strong>
          <p>${esc(body)}</p>
        </div>
      </li>`;
    })
    .join('');
}

function renderGaps(gaps) {
  if (!gaps.length) {
    gapsEl.innerHTML = '<p class="muted-note">暂无 Gap 表</p>';
    return;
  }
  const max = Math.max(...gaps.map((g) => Number(g.count || 0)), 1);
  gapsEl.innerHTML = gaps
    .map((g) => {
      const count = Number(g.count || 0);
      const pct = Math.max(8, (count / max) * 100);
      return `<div class="dash-gap">
        <div class="dash-gap__top">
          <span class="dash-gap__name">${esc(g.label || g.value)}</span>
          <span class="dash-gap__dim">${esc(DIM_ZH[g.dim] || g.dim || '')}</span>
        </div>
        <div class="dash-gap__track"><span style="width:${pct}%"></span></div>
        <div class="dash-gap__count">${fmt(count)}</div>
      </div>`;
    })
    .join('');
}

function renderOwn(list) {
  if (!list.length) {
    ownBlockEl.hidden = true;
    return;
  }
  ownBlockEl.hidden = false;
  ownEl.innerHTML = list
    .map((p, i) => {
      const img = p.image_url
        ? `<img src="${esc(p.image_url)}" alt="" />`
        : '<div class="dash-own__ph">AZ</div>';
      const trend = p.trend_label || 'unknown';
      return `<a class="dash-own" href="/monitor.html">
        ${img}
        <div>
          <em>#${i + 1}</em>
          <strong>${esc(p.title || '—')}</strong>
          <span>销量 ${fmt(p.sales_volume)} · 增速 ${esc(trend)}</span>
        </div>
      </a>`;
    })
    .join('');
}

function renderFunnel(plat) {
  const steps = [
    { key: 'generating', label: '生成中', tone: 'warn' },
    { key: 'succeeded', label: '已完成', tone: 'ok' },
    { key: 'failed', label: '失败', tone: 'bad' },
    { key: 'week_done', label: '本周完成', tone: 'ok' },
  ];
  funnelEl.innerHTML = steps
    .map((s, i) => {
      const n = plat[s.key] ?? 0;
      return `${i ? '<span class="dash-funnel__arrow" aria-hidden="true"></span>' : ''}
        <article class="dash-funnel__step dash-funnel__step--${s.tone}${n ? '' : ' is-zero'}">
          <div class="dash-funnel__n">${fmt(n)}</div>
          <div class="dash-funnel__l">${esc(s.label)}</div>
        </article>`;
    })
    .join('');
}

async function loadDash() {
  const cat = catEl.value || 'AT';
  const res = await fetch('/api/dashboard?category=' + encodeURIComponent(cat));
  if (!res.ok) throw new Error('总览加载失败');
  const data = await res.json();
  const ext = data.external || {};
  const plat = data.platform || {};
  const week = data.week || '—';
  eyebrowEl.textContent = `Executive · ${week} · ${cat}`;
  subEl.textContent = '竞品只看列表序 / 上新；自有热销来自 salesVolume';
  extHintEl.textContent = `来源：爬虫周报 ${week}`;
  briefMetaEl.textContent = `来源：爬虫周报 ${week}`;

  const warnings = data.warnings || [];
  warnEl.classList.toggle('hidden', !warnings.length);
  if (warnings.length) {
    warnEl.innerHTML = `<span class="dash-callout__tag">口径</span><span>${esc(warnings[0])}</span>`;
  }

  const accelUnknown = ext.own_accelerating == null;
  statsEl.innerHTML = [
    kpiCard({ value: ext.new_skc, label: '本周上新 SKC', tone: 'ok' }),
    kpiCard({
      value: ext.delist_skc,
      label: '本周下架 SKC',
      note: '以周报各站合计；大数先看清盘站',
      tone: 'warn',
    }),
    kpiCard({ value: ext.rank_up, label: '排名上升款', tone: 'ok' }),
    kpiCard({ value: ext.uncovered_colors, label: 'AZ 未覆盖新色', tone: 'accent' }),
    kpiCard({
      value: ext.own_accelerating,
      label: '自有加速款',
      note: accelUnknown ? '需满两周销量快照' : '',
      unknown: accelUnknown,
      tone: 'neutral',
    }),
  ].join('');

  renderSites(ext.sites || []);
  renderBriefs(ext.bullets || []);
  renderGaps(ext.gap_top || []);
  renderOwn(ext.own_hot_top || []);
  renderFunnel(plat);
}

catEl.addEventListener('change', () => loadDash().catch(showFail));
document.getElementById('btn-refresh').addEventListener('click', () => loadDash().catch(showFail));

function showFail(err) {
  warnEl.classList.remove('hidden');
  warnEl.innerHTML = `<span class="dash-callout__tag">错误</span><span>${esc(err.message || '总览加载失败')}</span>`;
}

loadDash().catch(showFail);
