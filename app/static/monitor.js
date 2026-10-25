const warnEl = document.getElementById('mon-warn');
const subEl = document.getElementById('mon-sub');
const filtersEl = document.getElementById('mon-filters');
const gridEl = document.getElementById('mon-grid');
const metaEl = document.getElementById('mon-meta');

const DESIGN_DIMS = [
  { key: 'fabric', label: '面料' },
  { key: 'silhouette', label: '廓形' },
  { key: 'neckline', label: '领型' },
  { key: 'length', label: '裙长' },
  { key: 'color', label: '颜色' },
  { key: 'pattern', label: '图案' },
  { key: 'sleeve', label: '袖长' },
];

let seed = {
  products: [],
  sites: [],
  weeks: [],
  markets: ['US', 'UK', 'AU'],
  statuses: ['上新', '上升', '下降', '下架', '在售', '热销'],
  filter_options: {},
  week: '',
  categories: ['AT'],
};

const filters = {
  weeks: [],
  categories: ['AT'],
  markets: [],
  statuses: [],
  shipsNow: [],
  sites: [],
  fabric: [],
  silhouette: [],
  neckline: [],
  length: [],
  color: [],
  pattern: [],
  sleeve: [],
};

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function toggleValue(list, value, on) {
  const next = list.filter((x) => x !== value);
  if (on) next.push(value);
  return next;
}

function matchesMulti(selected, value) {
  if (!selected.length) return true;
  const values = Array.isArray(value) ? value : [value];
  const set = new Set(values.map((v) => String(v || '').toLowerCase()).filter(Boolean));
  return selected.some((s) => set.has(String(s).toLowerCase()));
}

function msLabel(selected, fallback) {
  if (!selected.length) return fallback || '全部';
  if (selected.length === 1) return selected[0];
  return `${selected[0]} +${selected.length - 1}`;
}

function optionList(key) {
  if (key === 'weeks') return seed.weeks || [];
  if (key === 'categories') return ['AT', 'BD'];
  if (key === 'markets') return seed.markets || ['US', 'UK', 'AU'];
  if (key === 'statuses') return seed.statuses || ['上新', '上升', '下降', '下架', '在售', '热销'];
  if (key === 'shipsNow') return ['是', '否'];
  return (seed.filter_options && seed.filter_options[key]) || [];
}

function renderMs(key, label) {
  const selected = filters[key] || [];
  const opts = optionList(key);
  const items = opts
    .map((opt) => {
      const on = selected.includes(opt);
      return `<label class="zf-ms__opt"><input type="checkbox" data-ms-opt="${esc(key)}" value="${esc(opt)}" ${on ? 'checked' : ''}/><span>${esc(opt)}</span></label>`;
    })
    .join('');
  return `<div class="zf-ms" data-ms="${esc(key)}">
    <button type="button" class="zf-ms__btn" data-ms-toggle="${esc(key)}"><span class="zf-ms__name">${esc(label)}</span><span class="zf-ms__val">${esc(msLabel(selected))}</span></button>
    <div class="zf-ms__menu" hidden>
      <button type="button" class="zf-ms__clear" data-ms-clear="${esc(key)}">全部（不限）</button>
      ${items || '<p class="zf-ms__empty">暂无选项</p>'}
    </div>
  </div>`;
}

function selectedChips() {
  const chips = [];
  const sites = seed.sites || [];
  if ((filters.weeks || []).length) chips.push(['weeks', '周次', filters.weeks.join('、')]);
  if ((filters.categories || []).length) chips.push(['categories', '品类', filters.categories.join('、')]);
  if ((filters.markets || []).length) chips.push(['markets', '市场', filters.markets.join('、')]);
  if ((filters.statuses || []).length) chips.push(['statuses', '状态', filters.statuses.join('、')]);
  if ((filters.shipsNow || []).length) chips.push(['shipsNow', 'Ships Now', filters.shipsNow.join('、')]);
  if (filters.sites.length && filters.sites.length < sites.length) {
    chips.push(['sites', '站点', filters.sites.join('、')]);
  }
  DESIGN_DIMS.forEach((d) => {
    if ((filters[d.key] || []).length) chips.push([d.key, d.label, filters[d.key].join('、')]);
  });
  return chips;
}

function renderChipRow() {
  const chips = selectedChips();
  const html = `<div class="zf-row zf-row--chips" data-chip-row>
      <div class="zf-label">已选</div>
      <div class="filter-selected-row">${
        chips.length
          ? chips
              .map(
                ([key, label, val]) =>
                  `<button type="button" class="chip chip--removable" data-clear-dim="${esc(key)}">${esc(label)} · ${esc(val)} ×</button>`
              )
              .join('')
          : '<span class="muted-note">尚未收窄筛选</span>'
      }</div>
    </div>`;
  const row = filtersEl.querySelector('[data-chip-row]');
  if (row) row.outerHTML = html;
  else filtersEl.insertAdjacentHTML('beforeend', html);
  bindChipClears();
}

function bindChipClears() {
  filtersEl.querySelectorAll('[data-clear-dim]').forEach((el) => {
    el.addEventListener('click', () => {
      const key = el.getAttribute('data-clear-dim');
      if (key === 'sites') filters.sites = (seed.sites || []).slice();
      else if (key === 'categories') {
        filters.categories = ['AT'];
        loadMon();
        return;
      } else filters[key] = [];
      renderFilters();
      bindFilters();
      renderGrid();
    });
  });
}

function renderFilters() {
  const sites = seed.sites || [];
  const picked = filters.sites.length ? filters.sites : sites;
  const siteChecks = sites
    .map((name) => {
      const on = picked.includes(name);
      const own = name === 'Azazie' ? ' site-check--own' : '';
      return `<label class="site-check${own}"><input type="checkbox" data-site-check="${esc(name)}" ${on ? 'checked' : ''}/><span>${esc(name)}</span></label>`;
    })
    .join('');
  filtersEl.innerHTML = `
    <div class="zf-row">
      <div class="zf-label">基础筛选</div>
      <div class="zf-body zf-body--sites">
        <div class="zf-body zf-body--ms">
          ${renderMs('weeks', '周次')}
          ${renderMs('categories', '品类')}
          ${renderMs('markets', '市场')}
          ${renderMs('statuses', '状态')}
          ${renderMs('shipsNow', 'Ships Now')}
        </div>
        <button type="button" class="btn-refresh btn-reset" id="btn-reset-mon">重置</button>
      </div>
    </div>
    <div class="zf-row">
      <div class="zf-label">站点</div>
      <div class="zf-body"><div class="site-check-inline">${siteChecks || '<span class="muted-note">暂无站点</span>'}</div></div>
    </div>
    <div class="zf-row">
      <div class="zf-label">设计细节</div>
      <div class="zf-body zf-body--ms">
        ${DESIGN_DIMS.map((d) => renderMs(d.key, d.label)).join('')}
      </div>
    </div>`;
  renderChipRow();
}

function applyFilters(products) {
  const sites = filters.sites.length ? filters.sites : seed.sites || [];
  return products.filter((p) => {
    if (filters.weeks.length && !matchesMulti(filters.weeks, p.week)) return false;
    if (filters.categories.length && !matchesMulti(filters.categories, p.category_line)) return false;
    if (filters.markets.length && !matchesMulti(filters.markets, p.markets || [])) return false;
    if (filters.statuses.length && !matchesMulti(filters.statuses, p.status_label || p.badge)) return false;
    if (filters.shipsNow.length) {
      const flag = p.ships_now ? '是' : '否';
      if (!filters.shipsNow.includes(flag)) return false;
    }
    if (!sites.includes(p.site)) return false;
    for (const dim of DESIGN_DIMS) {
      const selected = filters[dim.key] || [];
      if (selected.length && !matchesMulti(selected, p[dim.key])) return false;
    }
    return true;
  });
}

function statusClass(label) {
  if (label === '上新') return 'is-new';
  if (label === '上升' || label === '热销') return 'is-up';
  if (label === '下降' || label === '下架') return 'is-down';
  return 'is-on';
}

function goFusion(p) {
  try {
    sessionStorage.setItem('bloom_monitor_fusion_pick', JSON.stringify(p));
  } catch (err) {
    /* ignore quota */
  }
  const qs = new URLSearchParams({
    competitor_id: p.id || '',
    category: p.category_line || filters.categories[0] || 'AT',
    from: 'monitor',
  });
  if (p.week) qs.set('week', p.week);
  window.location.href = '/gap-fusion.html?' + qs.toString();
}

function pdpUrl(p) {
  const url = String(p.product_url || p.source_url || p.url || '').trim();
  return /^https?:\/\//i.test(url) ? url : '';
}

function cardHtml(p) {
  const img = p.image_url || '';
  const delisted = p.lifecycle === 'Delisted' || p.status === 'delisted' || p.status_label === '下架';
  const own = p.pool === 'own' || p.site === 'Azazie';
  const href = pdpUrl(p);
  const rankBit = own
    ? p.hot_rank
      ? `热销 #${esc(p.hot_rank)} · 销量 ${esc(p.sales_volume ?? '—')}`
      : `列表序 ${esc(p.rank ?? '—')}`
    : `列表序 ${esc(p.rank ?? '—')}`;
  const price =
    p.price != null
      ? `<span class="sku-card__price">$${esc(p.price)}${p.compare_at ? ` <s>$${esc(p.compare_at)}</s>` : ''}</span>`
      : '';
  const attrs = [p.color, p.fabric, p.length].filter(Boolean).join(' · ');
  const body = `
    <div class="sku-card__media">${img ? `<img src="${esc(img)}" alt="" loading="lazy" />` : '<div class="sku-card__ph">无主图</div>'}
      <span class="sku-badge ${statusClass(p.status_label)}">${esc(p.status_label || p.badge || '在售')}</span>
      ${p.discount_label ? `<span class="sku-off">${esc(p.discount_label)}</span>` : ''}
      <span class="sku-stock ${p.ships_now ? 'is-yes' : 'is-no'}">${p.ships_now ? '现货 · Ships Now' : '非现货'}</span>
    </div>
    <h3 class="sku-card__title">${esc(p.title || p.id)}</h3>
    <p class="sku-card__meta">${esc(p.site || '')} · ${esc(p.category_line || '')} · ${rankBit}${attrs ? ` · ${esc(attrs)}` : ''}</p>
    ${price}`;
  const linked = href
    ? `<a class="sku-card__pdp" href="${esc(href)}" target="_blank" rel="noopener noreferrer" title="打开商品页">${body}</a>`
    : body;
  return `<article class="sku-card${delisted ? ' is-delisted' : ''}${own ? ' is-own' : ''}${href ? ' is-linked' : ''}" data-product-id="${esc(p.id || '')}">
    ${linked}
    ${delisted ? '<p class="muted-note">下架款可看不可提交</p>' : `<button type="button" class="sku-card__btn" data-fusion>爆款合成</button>`}
  </article>`;
}

function renderGrid() {
  const rows = applyFilters(seed.products || []);
  const cats = (filters.categories.length ? filters.categories : seed.categories || []).join('/');
  const week = (filters.weeks[0] || seed.week || '—');
  metaEl.textContent = `${rows.length} 条 · ${week} · ${cats}`;
  gridEl.innerHTML = rows.map(cardHtml).join('') || '<p class="empty-state">当前筛选无商品。站点全不勾选、或设计细节过窄都会得到空集。</p>';
  gridEl.querySelectorAll('[data-fusion]').forEach((btn) => {
    btn.addEventListener('click', (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const id = btn.closest('[data-product-id]')?.getAttribute('data-product-id');
      const product = (seed.products || []).find((p) => p.id === id);
      if (product) goFusion(product);
    });
  });
}

function closeMenus(except) {
  filtersEl.querySelectorAll('.zf-ms__menu').forEach((menu) => {
    if (menu !== except) menu.hidden = true;
  });
}

function bindFilters() {
  filtersEl.querySelectorAll('[data-ms-toggle]').forEach((btn) => {
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const menu = btn.parentElement.querySelector('.zf-ms__menu');
      const open = menu.hidden;
      closeMenus(menu);
      menu.hidden = !open;
    });
  });
  filtersEl.querySelectorAll('[data-ms-opt]').forEach((el) => {
    el.addEventListener('change', () => {
      const key = el.getAttribute('data-ms-opt');
      const value = el.value;
      const prevCats = filters.categories.slice();
      filters[key] = toggleValue(filters[key] || [], value, el.checked);
      if (key === 'categories') {
        const next = filters.categories.length ? filters.categories : ['AT'];
        filters.categories = next;
        if (next.slice().sort().join(',') !== prevCats.slice().sort().join(',')) {
          loadMon();
          return;
        }
      }
      const valEl = filtersEl.querySelector(`[data-ms="${key}"] .zf-ms__val`);
      if (valEl) valEl.textContent = msLabel(filters[key]);
      renderChipRow();
      renderGrid();
    });
  });
  filtersEl.querySelectorAll('[data-ms-clear]').forEach((el) => {
    el.addEventListener('click', () => {
      const key = el.getAttribute('data-ms-clear');
      filters[key] = [];
      if (key === 'categories') {
        filters.categories = ['AT'];
        loadMon();
        return;
      }
      renderFilters();
      bindFilters();
      renderGrid();
    });
  });
  filtersEl.querySelectorAll('[data-site-check]').forEach((el) => {
    el.addEventListener('change', () => {
      filters.sites = Array.from(filtersEl.querySelectorAll('[data-site-check]:checked')).map((x) =>
        x.getAttribute('data-site-check')
      );
      renderChipRow();
      renderGrid();
    });
  });
  const reset = document.getElementById('btn-reset-mon');
  if (reset) reset.addEventListener('click', () => resetFilters(true));
}

function resetFilters(render) {
  filters.weeks = seed.week ? [seed.week] : [];
  filters.categories = seed.categories && seed.categories.length ? seed.categories.slice() : ['AT'];
  filters.markets = [];
  filters.statuses = [];
  filters.shipsNow = [];
  filters.sites = (seed.sites || []).slice();
  DESIGN_DIMS.forEach((d) => {
    filters[d.key] = [];
  });
  if (render) {
    renderFilters();
    bindFilters();
    renderGrid();
  }
}

async function loadMon() {
  const cats = (filters.categories.length ? filters.categories : ['AT']).join(',');
  warnEl.classList.add('hidden');
  metaEl.textContent = '加载中…';
  const res = await fetch('/api/monitor/seed?category=' + encodeURIComponent(cats));
  seed = await res.json();
  subEl.textContent = `周次 ${seed.week || '—'} · ${seed.rank_semantics_note || ''}`;
  const warnings = seed.data_warnings || [];
  warnEl.classList.toggle('hidden', !warnings.length);
  warnEl.textContent = warnings.join(' · ');
  filters.weeks = seed.week ? [seed.week] : [];
  filters.sites = (seed.sites || []).slice();
  renderFilters();
  bindFilters();
  renderGrid();
}

document.getElementById('btn-refresh').addEventListener('click', () => {
  loadMon().catch((err) => {
    warnEl.classList.remove('hidden');
    warnEl.textContent = err.message || '监控加载失败';
  });
});

document.addEventListener('click', (ev) => {
  if (!ev.target.closest('.zf-ms')) closeMenus();
});

loadMon().catch((err) => {
  warnEl.classList.remove('hidden');
  warnEl.textContent = err.message || '监控加载失败';
});
