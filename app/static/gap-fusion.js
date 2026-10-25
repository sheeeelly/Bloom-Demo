/* 爆款合成（方案四）· 竞品周报爆点 × AZ 周热销爆点 → 同维互斥 → V13 */

const weekSelect = document.getElementById('week-select');
const catSelect = document.getElementById('cat-select');
const siteFiltersEl = document.getElementById('site-filters');
const commonGapsEl = document.getElementById('common-gaps');
const azGapsEl = document.getElementById('az-gaps');
const alignedGapRowsEl = document.getElementById('aligned-gap-rows');
const competitorGridEl = document.getElementById('competitor-grid');
const azGridEl = document.getElementById('az-grid');
const compCountEl = document.getElementById('comp-count');
const azCountEl = document.getElementById('az-count');
const selectedHintEl = document.getElementById('selected-hint');
const azSelectedHintEl = document.getElementById('az-selected-hint');
const promptEl = document.getElementById('fusion-prompt');
const workflowNoteEl = document.getElementById('workflow-note');
const prepStatusEl = document.getElementById('prep-status');
const btnEl = document.getElementById('btn-gap-start');
const errorEl = document.getElementById('gap-error');
const toastEl = document.getElementById('toast');
const mutexToastEl = document.getElementById('mutex-toast');
const v13CountEl = document.getElementById('v13-count');
const v13NoticeEl = document.getElementById('v13-notice');
const v13CompSummaryEl = document.getElementById('v13-comp-summary');
const v13AzSummaryEl = document.getElementById('v13-az-summary');
const v13CompKeywordsEl = document.getElementById('v13-comp-keywords');
const v13AzKeywordsEl = document.getElementById('v13-az-keywords');
const btnV13Analyze = document.getElementById('btn-v13-analyze');
const btnV13Confirm = document.getElementById('btn-v13-confirm');
const btnV13Skip = document.getElementById('btn-v13-skip');
const btnPickComp = document.getElementById('btn-pick-comp');
const btnPickAz = document.getElementById('btn-pick-az');
const pickModalEl = document.getElementById('pick-modal');
const pickTitleEl = document.getElementById('pick-title');
const pickFiltersEl = document.getElementById('pick-filters');
const pickGridEl = document.getElementById('pick-grid');
const pickMetaEl = document.getElementById('pick-meta');
const pickConfirmEl = document.getElementById('pick-confirm');

const V13_CAT_TO_DIM = {
  silhouette: 'silhouette',
  neckline_shoulder: 'neckline',
  fabric: 'fabric',
  color: 'colorFamily',
  surface_detail: 'features',
  waist_hip: 'waistline',
  hem: 'dressLength',
  construction: 'features',
  commercial_selling_point: 'features',
};

const DIM_ORDER = [
  'silhouette',
  'neckline',
  'waistline',
  'fabric',
  'dressLength',
  'colorFamily',
  'features',
  'sleeve',
];

const MAX_CHIPS = 12;

let seed = null;
/** @type {Array<object>} */
let dimensions = [];
/** @type {any|null} */
let selectedCompetitor = null;
let monitorPinnedProduct = null;
/** @type {any|null} */
let selectedAz = null;
/** @type {Array<object>} */
let azProducts = [];
/** @type {Map<string, Array<object>>} */
const hotspotCache = new Map();
let toastTimer = null;
let previewTimer = null;
/** @type {{ points: Array<object>, competitor_summary: string, product_summary: string, status?: string } | null} */
let v13Selection = null;
/** @type {Set<string>} */
let v13SelectedIds = new Set();
/** confirmed | skipped | '' */
let v13SelectionState = '';
let v13Analyzing = false;
/** @type {string|null} */
let v13LastPointId = null;
let lastSubmitSig = '';
let lastSubmitAt = 0;

const PICK_DIMS = [
  { key: 'fabric', label: '面料' },
  { key: 'silhouette', label: '廓形' },
  { key: 'neckline', label: '领型' },
  { key: 'length', label: '裙长' },
  { key: 'color', label: '颜色' },
  { key: 'pattern', label: '图案' },
  { key: 'sleeve', label: '袖长' },
];
/** @type {'comp'|'az'} */
let pickMode = 'comp';
/** @type {any|null} */
let pickCatalog = null;
let pickCatalogCat = '';
let pickSelectedId = '';
let pickFilters = emptyPickFilters();

function emptyPickFilters() {
  return {
    weeks: [],
    categories: [],
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
}

function showToast(message, durationMs = 2400, asHtml = false) {
  if (!toastEl) return;
  if (asHtml) toastEl.innerHTML = message;
  else toastEl.textContent = message;
  toastEl.classList.remove('hidden');
  requestAnimationFrame(() => toastEl.classList.add('is-visible'));
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastEl.classList.remove('is-visible');
    setTimeout(() => toastEl.classList.add('hidden'), 220);
  }, durationMs);
}

function hideError() {
  errorEl.classList.add('hidden');
  errorEl.textContent = '';
}

function showError(message) {
  errorEl.textContent = message;
  errorEl.classList.remove('hidden');
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function statusLabel(status) {
  if (status === 'rising') return '上升';
  if (status === 'new') return '上新';
  return status || '';
}

function syncStart() {
  const readyPair = !!(selectedCompetitor && selectedAz);
  btnEl.disabled = !readyPair || v13Analyzing;
  if (prepStatusEl) {
    if (v13Analyzing) prepStatusEl.textContent = '后台分析中';
    else if (readyPair) prepStatusEl.textContent = '可创建合成任务';
    else prepStatusEl.textContent = '待选齐';
  }
}

function resetV13Selection(_message) {
  v13Selection = null;
  v13SelectedIds = new Set();
  v13SelectionState = '';
  v13LastPointId = null;
  if (promptEl) {
    promptEl.textContent = '一键合成时后台自动生成工作流 Prompt…';
  }
  syncStart();
}

/** 同侧同维只保留一个 checked（板内/卡内单选） */
function enforceSinglePerDim(points, preferValue) {
  const prefer = String(preferValue || '').trim().toLowerCase();
  const winnerIdx = new Map();
  (points || []).forEach((p, idx) => {
    if (!p.checked) return;
    const dim = p.dim || 'features';
    const value = String(p.value || p.label || '').trim().toLowerCase();
    if (!winnerIdx.has(dim)) {
      winnerIdx.set(dim, idx);
      return;
    }
    const prev = winnerIdx.get(dim);
    const prevVal = String(points[prev].value || points[prev].label || '')
      .trim()
      .toLowerCase();
    if (prefer && value === prefer && prevVal !== prefer) {
      winnerIdx.set(dim, idx);
    }
  });
  const winners = new Set(winnerIdx.values());
  return (points || []).map((p, idx) => {
    if (!p.checked) return { ...p };
    if (winners.has(idx)) return { ...p, checked: true };
    return { ...p, checked: false };
  });
}

function v13PointDim(point) {
  const dim = String(point.dim || '').trim();
  if (dim) return dim;
  const cat = String(point.category || '').trim();
  return V13_CAT_TO_DIM[cat] || cat || 'features';
}

/** 设计点同维互斥：后勾优先；冲突时取消对侧同维 */
function applyV13KeywordMutex(lastPointId) {
  if (!v13Selection || !lastPointId || !v13SelectedIds.has(lastPointId)) return [];
  const points = v13Selection.points || [];
  const byId = new Map(points.map((p) => [p.id, p]));
  const last = byId.get(lastPointId);
  if (!last) return [];
  const dim = v13PointDim(last);
  const lastSrc = last.source === 'product' ? 'product' : 'competitor';
  const notices = [];
  for (const pid of [...v13SelectedIds]) {
    if (pid === lastPointId) continue;
    const p = byId.get(pid);
    if (!p) continue;
    if (v13PointDim(p) !== dim) continue;
    const src = p.source === 'product' ? 'product' : 'competitor';
    if (src === lastSrc) continue;
    v13SelectedIds.delete(pid);
    notices.push(`同维互斥：${dim} 保留${lastSrc === 'product' ? '本品' : '竞品'}设计点`);
  }
  return notices;
}

function v13CountText() {
  if (!v13Selection) return '未分析';
  const points = v13Selection.points || [];
  let c = 0;
  let p = 0;
  for (const point of points) {
    if (!v13SelectedIds.has(point.id)) continue;
    if (point.source === 'competitor') c += 1;
    if (point.source === 'product') p += 1;
  }
  return `竞品 ${c}｜本品 ${p}`;
}

function renderV13Keywords() {
  if (!v13Selection) return;
  const points = v13Selection.points || [];
  if (v13CompKeywordsEl) v13CompKeywordsEl.innerHTML = '';
  if (v13AzKeywordsEl) v13AzKeywordsEl.innerHTML = '';
  for (const point of points) {
    const btn = document.createElement('button');
    btn.type = 'button';
    const on = v13SelectedIds.has(point.id);
    const src = point.source === 'product' ? 'product' : 'competitor';
    btn.className = `v13-keyword v13-keyword--${src}${on ? ' is-on' : ''}`;
    btn.textContent = `${on ? '✓ ' : ''}${point.keyword || point.title || point.id}`;
    btn.title = [point.description, point.design_value, point.risk_note].filter(Boolean).join('\n');
    btn.addEventListener('click', () => {
      if (v13SelectedIds.has(point.id)) {
        v13SelectedIds.delete(point.id);
      } else {
        v13SelectedIds.add(point.id);
        v13LastPointId = point.id;
        const notices = applyV13KeywordMutex(point.id);
        if (notices.length) showMutexNotices(notices);
      }
      v13SelectionState = '';
      if (v13CountEl) v13CountEl.textContent = v13CountText();
      if (v13NoticeEl) v13NoticeEl.textContent = '两边至少各选1个，数量不限';
      renderV13Keywords();
      syncStart();
    });
    const host = src === 'competitor' ? v13CompKeywordsEl : v13AzKeywordsEl;
    if (host) host.appendChild(btn);
  }
  if (v13CountEl) v13CountEl.textContent = v13CountText();
}

function selectedDesignPointsPayload() {
  if (!v13Selection || v13SelectionState === 'skipped') return [];
  return (v13Selection.points || []).filter((p) => v13SelectedIds.has(p.id));
}

async function analyzeDesignPoints({ silent = false } = {}) {
  if (!selectedCompetitor || !selectedAz) {
    showError('请先选择外部竞品与 AZ 热卖款');
    return;
  }
  if (v13Analyzing) return;
  hideError();
  v13Analyzing = true;
  v13SelectionState = '';
  syncStart();
  if (v13NoticeEl) {
    v13NoticeEl.textContent = '正在上传竞品/本品入参并启动 AI 分析…';
  }
  if (v13CountEl) v13CountEl.textContent = '分析中';
  const body = {
    competitor_image_urls:
      selectedCompetitor.detail_images && selectedCompetitor.detail_images.length
        ? selectedCompetitor.detail_images.slice(0, 8)
        : [selectedCompetitor.image_url].filter(Boolean),
    product_image_urls: [selectedAz.image_url].filter(Boolean),
    competitor_title: selectedCompetitor.title || '',
    product_title: selectedAz.title || '',
    competitor_hotspots: resolveHotspots(
      selectedCompetitor,
      `comp:${selectedCompetitor.id}`,
      'comp'
    ),
    product_hotspots: resolveHotspots(selectedAz, `az:${selectedAz.id}`, 'az'),
  };
  try {
    const res = await fetch('/api/gap-fusion/analyze-design-points', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `分析失败（HTTP ${res.status}）`);
    const selection = data.selection || {};
    v13Selection = {
      points: selection.points || [],
      competitor_summary: selection.competitor_summary || (data.competitor && data.competitor.summary) || '',
      product_summary: selection.product_summary || (data.product && data.product.summary) || '',
      status: `${data.competitor?.status || ''}/${data.product?.status || ''}`,
    };
    v13SelectedIds = new Set(selection.selected_point_ids || []);
    if (v13CompSummaryEl) v13CompSummaryEl.textContent = v13Selection.competitor_summary || '';
    if (v13AzSummaryEl) v13AzSummaryEl.textContent = v13Selection.product_summary || '';
    renderV13Keywords();
    if (v13NoticeEl) {
      v13NoticeEl.textContent = v13Selection.points.length
        ? '两边至少各选1个，数量不限'
        : '未返回设计点，可跳过或重试分析';
    }
    if (!silent) showToast('分析完成，请多选设计点后确认生成提示词');
  } catch (err) {
    resetV13Selection('分析失败，可点击右上角「开始分析」重试');
    showError(err.message || '设计点分析失败');
    if (!silent) showToast(err.message || '设计点分析失败');
  } finally {
    v13Analyzing = false;
    syncStart();
  }
}

async function confirmDesignPoints({ skip = false } = {}) {
  if (!v13Selection) {
    showError('请先分析设计点');
    return;
  }
  hideError();
  const body = {
    points: v13Selection.points || [],
    selected_point_ids: [...v13SelectedIds],
    competitor_summary: v13Selection.competitor_summary || '',
    product_summary: v13Selection.product_summary || '',
    skip,
    last_point_id: skip ? null : v13LastPointId,
  };
  try {
    const res = await fetch('/api/gap-fusion/confirm-design-points', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `确认失败（HTTP ${res.status}）`);
    v13SelectionState = skip ? 'skipped' : 'confirmed';
    if (!skip) {
      v13SelectedIds = new Set(data.selected_point_ids || []);
      if (data.mutex_notices && data.mutex_notices.length) {
        showMutexNotices(data.mutex_notices);
      }
      renderV13Keywords();
    }
    if (v13NoticeEl) {
      v13NoticeEl.textContent = skip
        ? '已跳过设计点，正在生成工作流 Prompt…'
        : '已确认设计点，正在生成工作流 Prompt…';
    }
    if (v13CountEl) v13CountEl.textContent = skip ? '已跳过' : v13CountText();
    syncStart();
    await refreshPrompt();
    showToast(skip ? '已生成 Prompt（跳过选点）' : '提示词已生成，将自动写入工作流');
  } catch (err) {
    showError(err.message || '确认失败');
    showToast(err.message || '确认失败');
  }
}

function activeSites() {
  return Array.from(siteFiltersEl.querySelectorAll('input:checked')).map((el) => el.value);
}

function boardRoot() {
  return alignedGapRowsEl || commonGapsEl;
}

function trendValues() {
  return Array.from(boardRoot().querySelectorAll('input[data-trend="1"]:checked')).map(
    (el) => el.value
  );
}

function trendLabels() {
  return Array.from(boardRoot().querySelectorAll('input[data-trend="1"]:checked')).map((el) => {
    const label = el.closest('label')?.querySelector('span')?.textContent || el.value;
    return String(label).replace(/\s·[\d.]+$/, '').trim();
  });
}

function azTrendValues() {
  return Array.from(boardRoot().querySelectorAll('input[data-az-trend="1"]:checked')).map(
    (el) => el.value
  );
}

function azTrendLabels() {
  return Array.from(boardRoot().querySelectorAll('input[data-az-trend="1"]:checked')).map((el) => {
    const label = el.closest('label')?.querySelector('span')?.textContent || el.value;
    return String(label).replace(/\s·[\d.]+$/, '').trim();
  });
}

function collectCheckedHotspotPayload(scope) {
  return collectCardPoints(scope)
    .filter((p) => p.checked && !p.disabled)
    .map((p) => ({ dim: p.dim, value: p.value, label: p.label }));
}

function showMutexNotices(notices) {
  const text = (notices || []).filter(Boolean).join('；');
  if (!mutexToastEl) {
    if (text) showToast(text);
    return;
  }
  if (!text) {
    mutexToastEl.classList.add('hidden');
    mutexToastEl.textContent = '';
    return;
  }
  mutexToastEl.textContent = text;
  mutexToastEl.classList.remove('hidden');
  showToast(text);
}

function norm(text) {
  return String(text || '')
    .trim()
    .toLowerCase()
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ');
}

/** 非 8 维服装属性：运营向标签，不进卡内爆点 */
const BLOCKED_HOTSPOT_VALUES = new Set(['size inclusive', 'white studio clear']);
const BLOCKED_HOTSPOT_LABELS = ['尺码包容', '白棚电商'];

function isBlockedHotspot(p) {
  const value = norm(p.value || p.key || '');
  const label = String(p.label || '');
  if (BLOCKED_HOTSPOT_VALUES.has(value)) return true;
  return BLOCKED_HOTSPOT_LABELS.some((s) => label.includes(s));
}

function hitsTrendSet(p, values) {
  const trendSet = new Set((values || []).map(norm));
  if (!trendSet.size) return false;
  const value = norm(p.value || p.key || '');
  const label = norm(p.label || '');
  if (value && trendSet.has(value)) return true;
  if (label && trendSet.has(label)) return true;
  return [...trendSet].some(
    (t) => (value && (label.includes(t) || t.includes(value) || value.includes(t))) || (label && label.includes(t))
  );
}

function hitsCheckedTrends(p) {
  return hitsTrendSet(p, trendValues());
}

function hitsCheckedAzTrends(p) {
  return hitsTrendSet(p, azTrendValues());
}

function firstNonEmptyPoints(...lists) {
  for (const list of lists) {
    if (Array.isArray(list) && list.length) return list;
  }
  return [];
}

function fallbackHotspots(product) {
  const fields = [
    ['silhouette', product.silhouette],
    ['neckline', product.neckline],
    ['waistline', product.waistline],
    ['fabric', product.fabric || product.fabric_name],
    ['dressLength', product.dressLength || product.dress_length || product.length],
    ['colorFamily', product.colorFamily || product.color_family || product.color || product.color_name],
    ['features', product.features || product.pattern || product.aesthetic_tag],
    ['sleeve', product.sleeve],
  ];
  const out = [];
  fields.forEach(([dim, raw]) => {
    const values = Array.isArray(raw) ? raw : String(raw || '').split(/[/|,，;]+/);
    values.forEach((item) => {
      const value = String(item || '').trim();
      if (!value) return;
      out.push({ dim, value, label: value, default_checked: true });
    });
  });
  return out;
}

/**
 * scope=comp：∩ 板 A
 * scope=az：∩ 板 B；板 B 无勾选时降级 default_checked
 */
function resolveHotspots(product, cacheKey, scope = 'comp') {
  if (cacheKey && hotspotCache.has(cacheKey)) {
    return hotspotCache.get(cacheKey).filter((p) => !isBlockedHotspot(p)).slice(0, MAX_CHIPS);
  }
  const raw = (product.hotspot_points || product.anchor_points || []).filter(
    (p) => !isBlockedHotspot(p)
  );
  const source = raw.length ? raw : fallbackHotspots(product).filter((p) => !isBlockedHotspot(p));
  const mapped = source.slice(0, MAX_CHIPS).map((p) => {
    const value = p.value || p.key || p.label;
    const label = p.label || value;
    let checked;
    if (Object.prototype.hasOwnProperty.call(p, 'checked') && cacheKey) {
      checked = !!p.checked;
    } else if (scope === 'az') {
      const azVals = azTrendValues();
      checked = azVals.length ? hitsCheckedAzTrends(p) : p.default_checked !== false;
    } else {
      checked = hitsCheckedTrends(p);
    }
    return { ...p, value, label, checked, disabled: !!p.disabled };
  });
  return enforceSinglePerDim(mapped);
}

function clearCompetitorHotspotCache() {
  for (const key of [...hotspotCache.keys()]) {
    if (key.startsWith('comp:')) hotspotCache.delete(key);
  }
}

function clearAzHotspotCache() {
  for (const key of [...hotspotCache.keys()]) {
    if (key.startsWith('az:')) hotspotCache.delete(key);
  }
}

function pointKey(p) {
  return `${p.dim || 'features'}:${p.value || p.key || p.label || ''}`;
}

function mergeMutexFlags(existing, incoming) {
  const prev = Array.isArray(existing) ? existing : [];
  const next = Array.isArray(incoming) ? incoming : [];
  const byKey = new Map(next.map((p) => [pointKey(p), p]));
  if (!prev.length) return next.map((p) => ({ ...p }));
  return prev.map((p) => {
    const hit = byKey.get(pointKey(p));
    if (!hit) return { ...p, disabled: false };
    return {
      ...p,
      checked: !!hit.checked,
      disabled: !!hit.disabled,
      mutex_cleared: !!hit.mutex_cleared,
    };
  });
}

function lockOpposingDims(selfPoints, otherPoints) {
  const locked = new Set(
    (otherPoints || []).filter((p) => p.checked).map((p) => p.dim || 'features')
  );
  return (selfPoints || []).map((p) => {
    const dim = p.dim || 'features';
    const disabled = locked.has(dim);
    return { ...p, disabled, checked: disabled ? false : !!p.checked };
  });
}

function applyLocalMutex(lastSide) {
  if (!selectedCompetitor || !selectedAz) {
    if (selectedCompetitor) {
      selectedCompetitor = {
        ...selectedCompetitor,
        hotspot_points: (selectedCompetitor.hotspot_points || []).map((p) => ({
          ...p,
          disabled: false,
        })),
      };
      hotspotCache.set(`comp:${selectedCompetitor.id}`, selectedCompetitor.hotspot_points);
    }
    if (selectedAz) {
      selectedAz = {
        ...selectedAz,
        hotspot_points: (selectedAz.hotspot_points || []).map((p) => ({ ...p, disabled: false })),
      };
      hotspotCache.set(`az:${selectedAz.id}`, selectedAz.hotspot_points);
    }
    return [];
  }
  const notices = [];
  if (lastSide === 'az') {
    const before = (selectedCompetitor.hotspot_points || []).filter((p) => p.checked).length;
    selectedCompetitor = {
      ...selectedCompetitor,
      hotspot_points: lockOpposingDims(selectedCompetitor.hotspot_points, selectedAz.hotspot_points),
    };
    selectedAz = {
      ...selectedAz,
      hotspot_points: (selectedAz.hotspot_points || []).map((p) => ({ ...p, disabled: false })),
    };
    const lockedDims = [
      ...new Set(
        (selectedAz.hotspot_points || []).filter((p) => p.checked).map((p) => p.dim || 'features')
      ),
    ];
    if (lockedDims.length && before) {
      notices.push(`同维互斥：${lockedDims.join('、')} 已在 AZ 侧勾选，竞品同维改为不可选`);
    }
  } else {
    const before = (selectedAz.hotspot_points || []).filter((p) => p.checked).length;
    selectedAz = {
      ...selectedAz,
      hotspot_points: lockOpposingDims(selectedAz.hotspot_points, selectedCompetitor.hotspot_points),
    };
    selectedCompetitor = {
      ...selectedCompetitor,
      hotspot_points: (selectedCompetitor.hotspot_points || []).map((p) => ({
        ...p,
        disabled: false,
      })),
    };
    const lockedDims = [
      ...new Set(
        (selectedCompetitor.hotspot_points || [])
          .filter((p) => p.checked)
          .map((p) => p.dim || 'features')
      ),
    ];
    if (lockedDims.length && before) {
      notices.push(`同维互斥：${lockedDims.join('、')} 已在竞品侧勾选，AZ 同维改为不可选`);
    }
  }
  hotspotCache.set(`comp:${selectedCompetitor.id}`, selectedCompetitor.hotspot_points);
  hotspotCache.set(`az:${selectedAz.id}`, selectedAz.hotspot_points);
  return notices;
}

function cachePoints(scope) {
  const product = scope === 'comp' ? selectedCompetitor : selectedAz;
  if (!product) return [];
  const key = `${scope}:${product.id}`;
  if (hotspotCache.has(key)) return hotspotCache.get(key);
  return product.hotspot_points || [];
}

function collectCardPoints(scope) {
  const catalog = cachePoints(scope);
  const root = scope === 'comp' ? competitorGridEl : azGridEl;
  const card = root && root.querySelector('.hot-card.is-selected');
  if (!card) return catalog.map((p) => ({ ...p }));
  const fromDom = Array.from(card.querySelectorAll('input[data-point="1"]')).map((el) => ({
    dim: el.getAttribute('data-dim') || 'features',
    value: el.value,
    label: el.getAttribute('data-label') || el.value,
    checked: el.checked,
    disabled: el.disabled,
  }));
  return mergeMutexFlags(catalog, fromDom);
}

async function runCardMutex(lastSide) {
  if (selectedCompetitor) {
    selectedCompetitor = { ...selectedCompetitor, hotspot_points: collectCardPoints('comp') };
    hotspotCache.set(`comp:${selectedCompetitor.id}`, selectedCompetitor.hotspot_points);
  }
  if (selectedAz) {
    selectedAz = { ...selectedAz, hotspot_points: collectCardPoints('az') };
    hotspotCache.set(`az:${selectedAz.id}`, selectedAz.hotspot_points);
  }
  const notices = applyLocalMutex(lastSide);
  const body = {
    competitor_points: cachePoints('comp'),
    az_points: cachePoints('az'),
    last_side: lastSide,
  };
  if (body.competitor_points.length || body.az_points.length) {
    try {
      const res = await fetch('/api/gap-fusion/mutex-hotspots', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        if (selectedCompetitor && Array.isArray(data.hotspot_points) && data.hotspot_points.length) {
          selectedCompetitor = {
            ...selectedCompetitor,
            hotspot_points: mergeMutexFlags(selectedCompetitor.hotspot_points, data.hotspot_points),
          };
          hotspotCache.set(`comp:${selectedCompetitor.id}`, selectedCompetitor.hotspot_points);
        }
        if (selectedAz && Array.isArray(data.anchor_points) && data.anchor_points.length) {
          selectedAz = {
            ...selectedAz,
            hotspot_points: mergeMutexFlags(selectedAz.hotspot_points, data.anchor_points),
          };
          hotspotCache.set(`az:${selectedAz.id}`, selectedAz.hotspot_points);
        }
        showMutexNotices(data.mutex_notices && data.mutex_notices.length ? data.mutex_notices : notices);
      } else {
        showMutexNotices(notices);
      }
    } catch (err) {
      console.warn('mutex failed', err);
      showMutexNotices(notices);
    }
  } else {
    showMutexNotices(notices);
  }
  renderCompetitorGrid();
  renderAzGrid();
}

function chipsHtml(product, selected, scope) {
  const points = resolveHotspots(product, selected ? `${scope}:${product.id}` : '', scope);
  if (!points.length) {
    return `<div class="hot-card__chips hot-card__chips--empty">暂无爆点属性</div>`;
  }
  return (
    `<div class="hot-card__chips" data-chip-scope="${escapeHtml(scope)}">` +
    points
      .map((p) => {
        const dim = p.dim || 'features';
        const value = p.value || p.key || p.label;
        const label = p.label || value;
        const locked = !!(p.disabled || p.mutex_locked);
        const checked = p.checked && !locked ? 'checked' : '';
        const disabled = !selected || locked ? 'disabled' : '';
        const extra = `${p.checked && !locked ? ' is-on' : ''}${selected ? '' : ' is-muted'}${locked ? ' is-mutex' : ''}`;
        return (
          `<label class="hot-chip${extra}" data-stop="1" title="${locked ? '对侧已勾选同维，不可选' : escapeHtml(label)}">` +
          `<input type="checkbox" data-point="1" data-dim="${escapeHtml(dim)}" data-label="${escapeHtml(label)}" value="${escapeHtml(value)}" ${checked} ${disabled}/>` +
          `<span>${escapeHtml(label)}</span>` +
          `</label>`
        );
      })
      .join('') +
    `</div>`
  );
}

function checkedPointDisplays(scope) {
  const root = scope === 'comp' ? competitorGridEl : azGridEl;
  const card = root.querySelector('.hot-card.is-selected');
  if (!card) return [];
  return Array.from(card.querySelectorAll('input[data-point="1"]:checked')).map((el) => {
    const dim = el.getAttribute('data-dim') || '';
    const label = el.getAttribute('data-label') || el.value;
    return dim ? `${dim}:${label}` : label;
  });
}

function groupByDim(items) {
  const byDim = new Map();
  DIM_ORDER.forEach((d) => byDim.set(d, []));
  (items || []).forEach((item) => {
    const dim = item.dim || 'features';
    if (!byDim.has(dim)) byDim.set(dim, []);
    byDim.get(dim).push(item);
  });
  return byDim;
}

/** 同维默认只勾一个：在 default_checked=true 的项里取分最高 */
function pickDefaultCheckedValues(items, scoreKey) {
  const byDim = groupByDim(items);
  const allowed = new Set();
  byDim.forEach((opts, dim) => {
    const pool = (opts || []).filter((x) => x.default_checked === true);
    if (!pool.length) return;
    pool.sort(
      (a, b) => Number(b[scoreKey] || b.count || 0) - Number(a[scoreKey] || a.count || 0)
    );
    const value = pool[0].value || pool[0].key || pool[0].label;
    if (value) allowed.add(`${dim}::${value}`);
  });
  return allowed;
}

function chipsForBoardSide(opts, dim, dataAttr, scoreKey, allowedDefaults) {
  if (!opts.length) {
    return `<span class="trend-align-row__empty">—</span>`;
  }
  return (
    `<div class="chip-row chip-row--design">` +
    opts
      .map((item) => {
        const value = item.value || item.key || item.label;
        const label = item.label || value;
        const metric =
          item[scoreKey] != null
            ? ` ·${item[scoreKey]}`
            : item.count != null
              ? ` ·${item.count}`
              : '';
        const checked = allowedDefaults.has(`${dim}::${value}`) ? 'checked' : '';
        return (
          `<label class="intervention-chip">` +
          `<input type="checkbox" ${dataAttr}="1" data-dim="${escapeHtml(dim)}" value="${escapeHtml(value)}" ${checked}/>` +
          `<span>${escapeHtml(label)}${metric}</span>` +
          `</label>`
        );
      })
      .join('') +
    `</div>`
  );
}

function enforceBoardSingleSelect(input, dataAttr) {
  if (!input.checked) return;
  const dim = input.getAttribute('data-dim') || '';
  const root = input.closest('.trend-align-row') || boardRoot();
  root.querySelectorAll(`input[${dataAttr}="1"]`).forEach((el) => {
    if (el === input) return;
    if ((el.getAttribute('data-dim') || '') === dim) el.checked = false;
  });
}

function renderTrendBoard() {
  const compItems = seed.trend_hotspots || seed.common_gap_attributes || [];
  const azItems = seed.az_trend_hotspots || [];
  const compByDim = groupByDim(compItems);
  const azByDim = groupByDim(azItems);
  const compDefaults = pickDefaultCheckedValues(compItems, 'count');
  const azDefaults = pickDefaultCheckedValues(azItems, 'score');

  const dims = DIM_ORDER.filter(
    (dim) => (compByDim.get(dim) || []).length || (azByDim.get(dim) || []).length
  );
  const rowsHtml = dims
    .map((dim) => {
      const dimMeta = dimensions.find((d) => d.key === dim);
      const title = dimMeta ? String(dimMeta.label || dim).split('·').pop().trim() : dim;
      return (
        `<div class="trend-align-row" data-dim-row="${escapeHtml(dim)}">` +
        `<div class="trend-align-row__label">${escapeHtml(title)}</div>` +
        `<div class="trend-align-row__comp">${chipsForBoardSide(compByDim.get(dim) || [], dim, 'data-trend', 'count', compDefaults)}</div>` +
        `<div class="trend-align-row__az">${chipsForBoardSide(azByDim.get(dim) || [], dim, 'data-az-trend', 'score', azDefaults)}</div>` +
        `</div>`
      );
    })
    .join('');

  if (alignedGapRowsEl) {
    alignedGapRowsEl.innerHTML = rowsHtml || '<p class="panel__hint">暂无爆点</p>';
  }

  boardRoot().querySelectorAll('input[data-trend="1"]').forEach((input) => {
    input.addEventListener('change', async () => {
      enforceBoardSingleSelect(input, 'data-trend');
      clearCompetitorHotspotCache();
      if (selectedCompetitor) {
        const points = resolveHotspots(selectedCompetitor, '', 'comp');
        selectedCompetitor = { ...selectedCompetitor, hotspot_points: points };
        hotspotCache.set(`comp:${selectedCompetitor.id}`, points);
      }
      renderCompetitorGrid();
      await runCardMutex('az');
    });
  });

  boardRoot().querySelectorAll('input[data-az-trend="1"]').forEach((input) => {
    input.addEventListener('change', async () => {
      enforceBoardSingleSelect(input, 'data-az-trend');
      clearAzHotspotCache();
      if (selectedAz) {
        const points = resolveHotspots(selectedAz, '', 'az');
        selectedAz = { ...selectedAz, hotspot_points: points };
        hotspotCache.set(`az:${selectedAz.id}`, points);
      }
      renderAzGrid();
      await runCardMutex('az');
    });
  });
}

function productCardHtml(p, selected, opts = {}) {
  const rankText =
    p.rank_delta != null
      ? `#${p.rank} ↑ +${p.rank_delta}`
      : p.rank != null
        ? `#${p.rank}${opts.rankSuffix || ''}`
        : '';
  const site = p.site || p.category_line || opts.siteFallback || '';
  const price =
    p.price != null
      ? `$${p.price}` + (p.compare_at ? ` <s>$${p.compare_at}</s>` : '')
      : p.sales_volume != null
        ? `销量 ${p.sales_volume}`
        : '';
  const scope = opts.scope || 'comp';
  const imgCount = p.image_count != null ? p.image_count : p.detail_images ? p.detail_images.length : p.image_url ? 1 : 0;
  const imgNote =
    imgCount >= 3 ? `${imgCount} 图` : imgCount === 1 ? '主图1张·可补详图' : '无图·保留URL';
  return (
    `<article class="hot-card hot-card--wide${selected ? ' is-selected' : ''}" data-id="${escapeHtml(p.id)}">` +
    `<div class="hot-card__top">` +
    `<label class="hot-card__check"><input type="radio" name="${opts.radioName || 'comp'}" value="${escapeHtml(p.id)}" ${selected ? 'checked' : ''}/></label>` +
    (p.status
      ? `<span class="hot-card__badge hot-card__badge--${escapeHtml(p.status)}">${escapeHtml(statusLabel(p.status))}</span>`
      : '') +
    (p.discount_label ? `<span class="hot-card__off">${escapeHtml(p.discount_label)}</span>` : '') +
    `<img class="hot-card__img" src="${escapeHtml(p.image_url || '')}" alt="" loading="lazy" />` +
    `</div>` +
    `<div class="hot-card__body">` +
    `<div class="hot-card__site">${escapeHtml(site)} · ${escapeHtml(imgNote)}</div>` +
    `<div class="hot-card__title">${escapeHtml(p.title || p.name || '')}</div>` +
    `<div class="hot-card__attrs">${escapeHtml((p.attrs_display || []).join(' · '))}</div>` +
    (price ? `<div class="hot-card__price">${price}</div>` : '') +
    (rankText
      ? `<div class="hot-card__meta">${escapeHtml(rankText)}${p.reviews != null ? ` · 评论 ${p.reviews}` : ''}${p.ships_now ? ' · 现货' : ''}</div>`
      : '') +
    (p.product_url || p.source_url
      ? `<div class="hot-card__meta"><a href="${escapeHtml(p.product_url || p.source_url)}" target="_blank" rel="noopener" data-stop="1">商品链接</a></div>`
      : '') +
    chipsHtml(p, selected, scope) +
    `</div></article>`
  );
}

function bindGrid(root, onSelect) {
  root.querySelectorAll('.hot-card').forEach((card) => {
    card.addEventListener('click', (ev) => {
      if (ev.target.closest('[data-stop="1"]')) return;
      const id = card.getAttribute('data-id');
      if (id) onSelect(id);
    });
  });
  root.querySelectorAll('.hot-card.is-selected input[data-point="1"]').forEach((input) => {
    input.addEventListener('change', async () => {
      if (input.disabled) return;
      const card = input.closest('.hot-card');
      const scope = card?.querySelector('.hot-card__chips')?.getAttribute('data-chip-scope') || '';
      const id = card?.getAttribute('data-id');
      // 卡内同维单选
      if (input.checked && card) {
        const dim = input.getAttribute('data-dim') || '';
        card.querySelectorAll('input[data-point="1"]').forEach((el) => {
          if (el !== input && (el.getAttribute('data-dim') || '') === dim) {
            el.checked = false;
            el.closest('.hot-chip')?.classList.remove('is-on');
          }
        });
      }
      if (id && scope) {
        const catalog = cachePoints(scope);
        const fromDom = Array.from(card.querySelectorAll('input[data-point="1"]')).map((el) => ({
          dim: el.getAttribute('data-dim') || 'features',
          value: el.value,
          label: el.getAttribute('data-label') || el.value,
          checked: el.checked,
          disabled: el.disabled,
        }));
        let points = enforceSinglePerDim(
          mergeMutexFlags(catalog, fromDom),
          input.checked ? input.value : ''
        );
        card.querySelectorAll('input[data-point="1"]').forEach((el) => {
          const dim = el.getAttribute('data-dim') || 'features';
          const hit = points.find((p) => (p.dim || 'features') === dim && p.value === el.value);
          const on = !!(hit && hit.checked && !hit.disabled);
          el.checked = on;
          el.disabled = !!(hit && hit.disabled);
          el.closest('.hot-chip')?.classList.toggle('is-on', on);
          el.closest('.hot-chip')?.classList.toggle('is-mutex', !!(hit && hit.disabled));
        });
        hotspotCache.set(`${scope}:${id}`, points);
        if (scope === 'comp' && selectedCompetitor) {
          selectedCompetitor = { ...selectedCompetitor, hotspot_points: points };
        }
        if (scope === 'az' && selectedAz) {
          selectedAz = { ...selectedAz, hotspot_points: points };
        }
      }
      input.closest('.hot-chip')?.classList.toggle('is-on', input.checked);
      await runCardMutex(scope === 'az' ? 'az' : 'competitor');
    });
  });
}

function filteredProducts() {
  const week = weekSelect.value;
  const cat = catSelect.value;
  const sites = new Set(activeSites());
  const list = (seed.competitor_products || []).filter((p) => {
    if (week && p.week && p.week !== week) return false;
    if (cat !== '全部' && p.category_line && p.category_line !== cat) return false;
    if (sites.size && p.site && !sites.has(p.site)) return false;
    return true;
  });
  const pinned = selectedCompetitor || monitorPinnedProduct;
  if (pinned && pinned.id && !list.some((p) => p.id === pinned.id)) {
    list.unshift(pinned);
  }
  return list;
}

function asFusionCard(p) {
  const attrs = p.attrs_display && p.attrs_display.length
    ? p.attrs_display
    : [p.color, p.fabric, p.length || p.dressLength].filter(Boolean);
  return {
    ...p,
    attrs_display: attrs,
    product_url: p.product_url || p.url || p.source_url || '',
    source_url: p.source_url || p.product_url || p.url || '',
    image_url: p.image_url || p.main_image_url || '',
  };
}

function isOwnProduct(p) {
  return p.pool === 'own' || p.site === 'Azazie';
}

function renderCompetitorGrid() {
  if (compCountEl) {
    compCountEl.textContent = selectedCompetitor ? '已选 1 款 · 请勾要保留的属性' : '从竞品商品库选 1 款';
  }
  if (!selectedCompetitor) {
    competitorGridEl.innerHTML =
      '<div class="fusion-slot__empty">尚未选择竞品款。点下方按钮从竞品商品库挑一款，作为板 A 的外形来源。</div>';
    return;
  }
  competitorGridEl.innerHTML = productCardHtml(selectedCompetitor, true, {
    radioName: 'comp',
    scope: 'comp',
  });
  bindGrid(competitorGridEl, () => {});
}

function renderAzGrid() {
  if (azCountEl) {
    azCountEl.textContent = selectedAz ? '已选 1 款 · 请勾要保留的属性' : '从内部商品库选 1 款';
  }
  if (!selectedAz) {
    azGridEl.innerHTML =
      '<div class="fusion-slot__empty">尚未选择 AZ 热卖款。点下方按钮从内部商品库挑一款，作为板 B 的骨架。</div>';
    return;
  }
  azGridEl.innerHTML = productCardHtml(selectedAz, true, {
    radioName: 'az',
    siteFallback: 'Azazie',
    rankSuffix: ' · 热销',
    scope: 'az',
  });
  bindGrid(azGridEl, () => {});
}

function pickOptionList(key) {
  const cat = pickCatalog || {};
  if (key === 'weeks') return cat.weeks || [];
  if (key === 'categories') return ['AT', 'BD'];
  if (key === 'markets') return cat.markets || ['US', 'UK', 'AU'];
  if (key === 'statuses') return cat.statuses || ['上新', '上升', '下降', '下架', '在售', '热销'];
  if (key === 'shipsNow') return ['是', '否'];
  return (cat.filter_options && cat.filter_options[key]) || [];
}

function pickMsLabel(selected) {
  if (!selected.length) return '全部';
  if (selected.length === 1) return selected[0];
  return `${selected[0]} +${selected.length - 1}`;
}

function pickMatchesMulti(selected, value) {
  if (!selected.length) return true;
  const values = Array.isArray(value) ? value : [value];
  const set = new Set(values.map((v) => String(v || '').toLowerCase()).filter(Boolean));
  return selected.some((s) => set.has(String(s).toLowerCase()));
}

function pickToggle(list, value, on) {
  const next = (list || []).filter((x) => x !== value);
  if (on) next.push(value);
  return next;
}

function renderPickMs(key, label) {
  const selected = pickFilters[key] || [];
  const items = pickOptionList(key)
    .map((opt) => {
      const on = selected.includes(opt);
      return `<label class="zf-ms__opt"><input type="checkbox" data-pick-ms-opt="${escapeHtml(key)}" value="${escapeHtml(opt)}" ${on ? 'checked' : ''}/><span>${escapeHtml(opt)}</span></label>`;
    })
    .join('');
  return `<div class="zf-ms" data-ms="${escapeHtml(key)}">
    <button type="button" class="zf-ms__btn" data-pick-ms-toggle="${escapeHtml(key)}"><span class="zf-ms__name">${escapeHtml(label)}</span><span class="zf-ms__val">${escapeHtml(pickMsLabel(selected))}</span></button>
    <div class="zf-ms__menu" hidden>
      <button type="button" class="zf-ms__clear" data-pick-ms-clear="${escapeHtml(key)}">全部（不限）</button>
      ${items || '<p class="zf-ms__empty">暂无选项</p>'}
    </div>
  </div>`;
}

function pickSiteOptions() {
  const sites = pickCatalog && pickCatalog.sites ? pickCatalog.sites.slice() : [];
  if (pickMode === 'az') return sites.filter((s) => s === 'Azazie');
  return sites.filter((s) => s !== 'Azazie');
}

function pickSelectedChips() {
  const chips = [];
  const sites = pickSiteOptions();
  if ((pickFilters.weeks || []).length) chips.push(['weeks', '周次', pickFilters.weeks.join('、')]);
  if ((pickFilters.categories || []).length) chips.push(['categories', '品类', pickFilters.categories.join('、')]);
  if ((pickFilters.markets || []).length) chips.push(['markets', '市场', pickFilters.markets.join('、')]);
  if ((pickFilters.statuses || []).length) chips.push(['statuses', '状态', pickFilters.statuses.join('、')]);
  if ((pickFilters.shipsNow || []).length) chips.push(['shipsNow', 'Ships Now', pickFilters.shipsNow.join('、')]);
  if (pickFilters.sites.length && pickFilters.sites.length < sites.length) {
    chips.push(['sites', '站点', pickFilters.sites.join('、')]);
  }
  PICK_DIMS.forEach((d) => {
    if ((pickFilters[d.key] || []).length) chips.push([d.key, d.label, pickFilters[d.key].join('、')]);
  });
  return chips;
}

function renderPickChipRow() {
  if (!pickFiltersEl) return;
  const chips = pickSelectedChips();
  const html = `<div class="zf-row zf-row--chips" data-pick-chip-row>
      <div class="zf-label">已选</div>
      <div class="filter-selected-row">${
        chips.length
          ? chips
              .map(
                ([key, label, val]) =>
                  `<button type="button" class="chip chip--removable" data-pick-clear-dim="${escapeHtml(key)}">${escapeHtml(label)} · ${escapeHtml(val)} ×</button>`
              )
              .join('')
          : '<span class="muted-note">尚未收窄筛选</span>'
      }</div>
    </div>`;
  const row = pickFiltersEl.querySelector('[data-pick-chip-row]');
  if (row) row.outerHTML = html;
  else pickFiltersEl.insertAdjacentHTML('beforeend', html);
  pickFiltersEl.querySelectorAll('[data-pick-clear-dim]').forEach((el) => {
    el.addEventListener('click', () => {
      const key = el.getAttribute('data-pick-clear-dim');
      if (key === 'sites') pickFilters.sites = pickSiteOptions().slice();
      else if (key === 'categories') pickFilters.categories = [catSelect.value === '全部' ? 'AT' : catSelect.value];
      else pickFilters[key] = [];
      renderPickFilters();
      renderPickGrid();
    });
  });
}

function renderPickFilters() {
  if (!pickFiltersEl) return;
  const sites = pickSiteOptions();
  const picked = pickFilters.sites.length ? pickFilters.sites : sites;
  const siteChecks = sites
    .map((name) => {
      const on = picked.includes(name);
      const own = name === 'Azazie' ? ' site-check--own' : '';
      return `<label class="site-check${own}"><input type="checkbox" data-pick-site="${escapeHtml(name)}" ${on ? 'checked' : ''}/><span>${escapeHtml(name)}</span></label>`;
    })
    .join('');
  pickFiltersEl.innerHTML = `
    <div class="zf-row">
      <div class="zf-label">基础筛选</div>
      <div class="zf-body zf-body--sites">
        <div class="zf-body zf-body--ms">
          ${renderPickMs('weeks', '周次')}
          ${renderPickMs('categories', '品类')}
          ${renderPickMs('markets', '市场')}
          ${renderPickMs('statuses', '状态')}
          ${renderPickMs('shipsNow', 'Ships Now')}
        </div>
        <button type="button" class="btn-refresh btn-reset" id="btn-reset-pick">重置</button>
      </div>
    </div>
    <div class="zf-row">
      <div class="zf-label">站点</div>
      <div class="zf-body"><div class="site-check-inline">${siteChecks || '<span class="muted-note">暂无站点</span>'}</div></div>
    </div>
    <div class="zf-row">
      <div class="zf-label">设计细节</div>
      <div class="zf-body zf-body--ms">
        ${PICK_DIMS.map((d) => renderPickMs(d.key, d.label)).join('')}
      </div>
    </div>`;
  renderPickChipRow();
  bindPickFilters();
}

function closePickMenus(except) {
  if (!pickFiltersEl) return;
  pickFiltersEl.querySelectorAll('.zf-ms__menu').forEach((menu) => {
    if (menu !== except) menu.hidden = true;
  });
}

function bindPickFilters() {
  pickFiltersEl.querySelectorAll('[data-pick-ms-toggle]').forEach((btn) => {
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const menu = btn.parentElement.querySelector('.zf-ms__menu');
      const open = menu.hidden;
      closePickMenus(menu);
      menu.hidden = !open;
    });
  });
  pickFiltersEl.querySelectorAll('[data-pick-ms-opt]').forEach((el) => {
    el.addEventListener('change', () => {
      const key = el.getAttribute('data-pick-ms-opt');
      pickFilters[key] = pickToggle(pickFilters[key] || [], el.value, el.checked);
      const valEl = pickFiltersEl.querySelector(`[data-ms="${key}"] .zf-ms__val`);
      if (valEl) valEl.textContent = pickMsLabel(pickFilters[key]);
      renderPickChipRow();
      renderPickGrid();
    });
  });
  pickFiltersEl.querySelectorAll('[data-pick-ms-clear]').forEach((el) => {
    el.addEventListener('click', () => {
      const key = el.getAttribute('data-pick-ms-clear');
      pickFilters[key] = key === 'categories' ? [catSelect.value === '全部' ? 'AT' : catSelect.value] : [];
      renderPickFilters();
      renderPickGrid();
    });
  });
  pickFiltersEl.querySelectorAll('[data-pick-site]').forEach((el) => {
    el.addEventListener('change', () => {
      pickFilters.sites = Array.from(pickFiltersEl.querySelectorAll('[data-pick-site]:checked')).map((x) =>
        x.getAttribute('data-pick-site')
      );
      renderPickChipRow();
      renderPickGrid();
    });
  });
  const reset = document.getElementById('btn-reset-pick');
  if (reset) {
    reset.addEventListener('click', () => {
      resetPickFilters();
      renderPickFilters();
      renderPickGrid();
    });
  }
}

function resetPickFilters() {
  const cat = catSelect.value === '全部' ? 'AT' : catSelect.value;
  const week = weekSelect.value || (pickCatalog && pickCatalog.week) || '';
  pickFilters = emptyPickFilters();
  pickFilters.categories = [cat];
  if (week) pickFilters.weeks = [week];
  pickFilters.sites = pickSiteOptions().slice();
}

function pickPoolProducts() {
  const raw = (pickCatalog && pickCatalog.products) || [];
  const merged = raw.slice();
  if (pickMode === 'comp') {
    (seed && seed.competitor_products ? seed.competitor_products : []).forEach((p) => {
      if (p && p.id && !merged.some((x) => x.id === p.id) && !isOwnProduct(p)) merged.push(p);
    });
    if (
      monitorPinnedProduct &&
      !merged.some((x) => x.id === monitorPinnedProduct.id) &&
      !isOwnProduct(monitorPinnedProduct)
    ) {
      merged.unshift(monitorPinnedProduct);
    }
    return merged.filter((p) => !isOwnProduct(p));
  }
  (azProducts || []).forEach((p) => {
    if (p && p.id && !merged.some((x) => x.id === p.id)) {
      merged.push({ ...p, site: p.site || 'Azazie', pool: p.pool || 'own' });
    }
  });
  if (selectedAz && !merged.some((x) => x.id === selectedAz.id)) merged.unshift(selectedAz);
  return merged.filter(
    (p) => isOwnProduct(p) || p.site === 'Azazie' || (azProducts || []).some((x) => x.id === p.id)
  );
}

function applyPickFilters(products) {
  const sites = pickFilters.sites.length ? pickFilters.sites : pickSiteOptions();
  return products.filter((p) => {
    if (pickFilters.weeks.length && p.week && !pickMatchesMulti(pickFilters.weeks, p.week)) return false;
    if (pickFilters.categories.length && p.category_line && !pickMatchesMulti(pickFilters.categories, p.category_line)) {
      return false;
    }
    if (pickFilters.markets.length && !pickMatchesMulti(pickFilters.markets, p.markets || [])) return false;
    if (
      pickFilters.statuses.length &&
      !pickMatchesMulti(pickFilters.statuses, p.status_label || p.badge || statusLabel(p.status))
    ) {
      return false;
    }
    if (pickFilters.shipsNow.length) {
      const flag = p.ships_now ? '是' : '否';
      if (!pickFilters.shipsNow.includes(flag)) return false;
    }
    if (sites.length && p.site && !sites.includes(p.site)) return false;
    for (const dim of PICK_DIMS) {
      const selected = pickFilters[dim.key] || [];
      if (selected.length && !pickMatchesMulti(selected, p[dim.key])) return false;
    }
    return true;
  });
}

function pickStatusClass(label) {
  if (label === '上新' || label === 'new') return 'is-new';
  if (label === '上升' || label === '热销' || label === 'rising') return 'is-up';
  if (label === '下降' || label === '下架') return 'is-down';
  return 'is-on';
}

function pickCardHtml(p) {
  const img = p.image_url || p.main_image_url || '';
  const own = isOwnProduct(p);
  const status = p.status_label || p.badge || statusLabel(p.status) || '在售';
  const rankBit = own
    ? p.hot_rank
      ? `热销 #${escapeHtml(p.hot_rank)} · 销量 ${escapeHtml(p.sales_volume ?? '—')}`
      : p.rank != null
        ? `热销 #${escapeHtml(p.rank)}`
        : ''
    : p.rank != null
      ? `列表序 ${escapeHtml(p.rank)}`
      : '';
  const price =
    p.price != null
      ? `<span class="sku-card__price">$${escapeHtml(p.price)}${p.compare_at ? ` <s>$${escapeHtml(p.compare_at)}</s>` : ''}</span>`
      : '';
  const attrs = [p.color, p.fabric, p.length].filter(Boolean).join(' · ');
  const checked = pickSelectedId === p.id ? 'checked' : '';
  return `<article class="sku-card sku-card--pick${own ? ' is-own' : ''}${pickSelectedId === p.id ? ' is-picked' : ''}" data-pick-id="${escapeHtml(p.id || '')}">
    <div class="sku-card__media">${img ? `<img src="${escapeHtml(img)}" alt="" loading="lazy" />` : '<div class="sku-card__ph">无主图</div>'}
      <label class="sku-card__tick" data-pick-tick="1"><input type="checkbox" ${checked} /></label>
      <span class="sku-badge ${pickStatusClass(status)}">${escapeHtml(status)}</span>
      ${p.discount_label ? `<span class="sku-off">${escapeHtml(p.discount_label)}</span>` : ''}
      <span class="sku-stock ${p.ships_now ? 'is-yes' : 'is-no'}">${p.ships_now ? '现货 · Ships Now' : '非现货'}</span>
    </div>
    <h3 class="sku-card__title">${escapeHtml(p.title || p.id)}</h3>
    <p class="sku-card__meta">${escapeHtml(p.site || (own ? 'Azazie' : ''))} · ${escapeHtml(p.category_line || '')}${rankBit ? ` · ${rankBit}` : ''}${attrs ? ` · ${escapeHtml(attrs)}` : ''}</p>
    ${price}
  </article>`;
}

function renderPickGrid() {
  if (!pickGridEl) return;
  const rows = applyPickFilters(pickPoolProducts());
  if (pickMetaEl) pickMetaEl.textContent = `${rows.length} 款可选 · 右上角勾选 1 款`;
  pickGridEl.innerHTML =
    rows.map(pickCardHtml).join('') || '<p class="empty-state">当前筛选无商品。放宽站点或设计细节后再试。</p>';
  pickGridEl.querySelectorAll('[data-pick-id]').forEach((card) => {
    card.addEventListener('click', (ev) => {
      const id = card.getAttribute('data-pick-id');
      if (ev.target.closest('[data-pick-tick]')) {
        pickSelectedId = pickSelectedId === id ? '' : id;
      } else {
        pickSelectedId = id;
      }
      renderPickGrid();
      syncPickConfirm();
    });
  });
  syncPickConfirm();
}

function syncPickConfirm() {
  if (pickConfirmEl) pickConfirmEl.disabled = !pickSelectedId;
}

function findPickProduct(id) {
  return pickPoolProducts().find((p) => p.id === id) || null;
}

async function ensurePickCatalog() {
  const cat = catSelect.value === '全部' ? 'AT' : catSelect.value;
  if (pickCatalog && pickCatalogCat === cat) return pickCatalog;
  const qs = new URLSearchParams({ category: cat });
  if (weekSelect.value) qs.set('week', weekSelect.value);
  const res = await fetch('/api/monitor/seed?' + qs.toString());
  pickCatalog = await res.json();
  pickCatalogCat = cat;
  return pickCatalog;
}

function closePicker() {
  if (!pickModalEl) return;
  pickModalEl.classList.add('hidden');
  document.body.classList.remove('pick-modal-open');
  closePickMenus();
}

async function openPicker(mode) {
  pickMode = mode;
  pickSelectedId =
    mode === 'comp' ? (selectedCompetitor && selectedCompetitor.id) || '' : (selectedAz && selectedAz.id) || '';
  if (pickTitleEl) {
    pickTitleEl.textContent = mode === 'comp' ? '从竞品商品库选择' : '从内部商品库选择';
  }
  await ensurePickCatalog();
  resetPickFilters();
  renderPickFilters();
  renderPickGrid();
  pickModalEl.classList.remove('hidden');
  document.body.classList.add('pick-modal-open');
}

async function confirmPick() {
  const product = findPickProduct(pickSelectedId);
  if (!product) return;
  const card = asFusionCard(product);
  closePicker();
  if (pickMode === 'comp') {
    const keepAz = selectedAz;
    pinMonitorProduct(card);
    await selectCompetitor(card.id, true, { skipAzDefault: true, pinned: card });
    if (keepAz) await selectAz(keepAz.id, false, { pinned: keepAz });
  } else {
    if (!azProducts.some((p) => p.id === card.id)) azProducts = [card, ...azProducts];
    await selectAz(card.id, true, { pinned: card });
  }
}

async function loadAzHot() {
  const cat = catSelect.value === '全部' ? 'AT' : catSelect.value;
  try {
    const res = await fetch('/api/gap-fusion/az-hot?category=' + encodeURIComponent(cat));
    if (!res.ok) throw new Error('az-hot failed');
    const data = await res.json();
    azProducts = data.products || [];
  } catch (err) {
    azProducts = seed.az_reference_candidates || [];
  }
  if (selectedAz && !azProducts.some((p) => p.id === selectedAz.id)) {
    selectedAz = null;
    azSelectedHintEl.textContent = '未选 AZ';
    azSelectedHintEl.title = '';
  }
  renderAzGrid();
}

async function selectCompetitor(competitorId, notify, opts = {}) {
  hideError();
  const skipAz = !!opts.skipAzDefault;
  const pinned = opts.pinned || monitorPinnedProduct;
  try {
    const res = await fetch('/api/gap-fusion/select-competitor', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        competitor_id: competitorId,
        az_id: skipAz ? null : selectedAz ? selectedAz.id : null,
        category: catSelect.value === '全部' ? 'AT' : catSelect.value,
        trend_values: trendValues(),
        az_trend_values: azTrendValues(),
        pinned_product: pinned || null,
        skip_az_default: skipAz,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || '自动勾选失败');
    }
    const data = await res.json();
    const prevAz = selectedAz;
    const incomingComp = firstNonEmptyPoints(
      data.competitor && data.competitor.hotspot_points,
      data.hotspot_points,
      fallbackHotspots(data.competitor || pinned || {})
    );
    selectedCompetitor = {
      ...(pinned || data.competitor),
      ...data.competitor,
      hotspot_points: incomingComp,
    };
    hotspotCache.set(`comp:${selectedCompetitor.id}`, selectedCompetitor.hotspot_points);
    if (prevAz && skipAz) {
      selectedAz = prevAz;
    } else if (data.az_reference && !skipAz) {
      const sameAz = prevAz && prevAz.id === data.az_reference.id;
      selectedAz = {
        ...(sameAz ? prevAz : data.az_reference),
        hotspot_points: sameAz
          ? mergeMutexFlags(
              prevAz.hotspot_points,
              firstNonEmptyPoints(data.anchor_points, data.az_reference.hotspot_points)
            )
          : firstNonEmptyPoints(
              data.anchor_points,
              data.az_reference.hotspot_points,
              fallbackHotspots(data.az_reference)
            ),
      };
      hotspotCache.set(`az:${selectedAz.id}`, selectedAz.hotspot_points);
    }
    if (data.az_hot_products) azProducts = data.az_hot_products;
    const localNotices = applyLocalMutex('competitor');
    renderCompetitorGrid();
    renderAzGrid();
    showMutexNotices(
      data.mutex_notices && data.mutex_notices.length ? data.mutex_notices : localNotices
    );
    selectedHintEl.textContent = '已选竞品';
    selectedHintEl.title = selectedCompetitor.title || '';
    if (selectedAz && !skipAz) {
      azSelectedHintEl.textContent = '已选 AZ';
      azSelectedHintEl.title = selectedAz.title || '';
    }
    resetV13Selection(
      selectedAz
        ? '已换竞品，请点击右上角「开始分析」。'
        : '已选竞品。请勾要保留的属性，再选自有商品后合成。'
    );
    syncStart();
    if (notify) showToast('已选竞品 · 已按板 A 联动（同维互斥后）');
  } catch (err) {
    showError(err.message || '选择失败');
  }
}

async function selectAz(azId, notify, opts = {}) {
  hideError();
  const prevComp = selectedCompetitor;
  const prevAz = selectedAz;
  try {
    const res = await fetch('/api/gap-fusion/select-az', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        az_id: azId,
        competitor_id: prevComp ? prevComp.id : null,
        category: catSelect.value === '全部' ? 'AT' : catSelect.value,
        trend_values: trendValues(),
        az_trend_values: azTrendValues(),
        pinned_product: opts.pinned || null,
        pinned_competitor: prevComp || null,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || '选择 AZ 失败');
    }
    const data = await res.json();
    const sameAz = prevAz && String(prevAz.id) === String(azId);
    if (sameAz) {
      selectedAz = {
        ...prevAz,
        hotspot_points: prevAz.hotspot_points || [],
      };
    } else {
      const azCatalog = firstNonEmptyPoints(
        opts.pinned && opts.pinned.hotspot_points,
        data.az_reference && data.az_reference.hotspot_points,
        fallbackHotspots(data.az_reference || opts.pinned || {})
      );
      selectedAz = {
        ...(opts.pinned || data.az_reference),
        ...data.az_reference,
        hotspot_points: mergeMutexFlags(azCatalog, data.anchor_points || []),
      };
    }
    hotspotCache.set(`az:${selectedAz.id}`, selectedAz.hotspot_points);
    if (data.az_hot_products) azProducts = data.az_hot_products;
    if (prevComp) {
      selectedCompetitor = {
        ...prevComp,
        hotspot_points: (prevComp.hotspot_points || []).map((p) => ({ ...p })),
      };
      hotspotCache.set(`comp:${selectedCompetitor.id}`, selectedCompetitor.hotspot_points);
    } else if (data.competitor) {
      selectedCompetitor = {
        ...data.competitor,
        hotspot_points: firstNonEmptyPoints(
          data.competitor.hotspot_points,
          data.hotspot_points,
          fallbackHotspots(data.competitor)
        ),
      };
      hotspotCache.set(`comp:${selectedCompetitor.id}`, selectedCompetitor.hotspot_points);
    }
    const localNotices = applyLocalMutex('az');
    renderAzGrid();
    renderCompetitorGrid();
    showMutexNotices(
      data.mutex_notices && data.mutex_notices.length ? data.mutex_notices : localNotices
    );
    azSelectedHintEl.textContent = '已选 AZ';
    azSelectedHintEl.title = selectedAz.title || '';
    resetV13Selection(
      selectedCompetitor
        ? '已换 AZ，请点击右上角「开始分析」。'
        : '已选 AZ，请再选竞品后点击「开始分析」。'
    );
    syncStart();
    if (notify) showToast('已选 AZ · 已按板 B 联动（同维互斥后）');
  } catch (err) {
    showError(err.message || '选择失败');
  }
}

async function schedulePreview() {
  if (previewTimer) clearTimeout(previewTimer);
  previewTimer = setTimeout(refreshPrompt, 220);
}

async function refreshPrompt() {
  /* Prompt 对用户隐藏：一键合成时后台生成 */
}

async function autoAnalyzeDesignPoints() {
  const matchComp = collectCheckedHotspotPayload('comp');
  const matchAz = collectCheckedHotspotPayload('az');
  const body = {
    competitor_image_urls:
      selectedCompetitor.detail_images && selectedCompetitor.detail_images.length
        ? selectedCompetitor.detail_images.slice(0, 8)
        : [selectedCompetitor.image_url].filter(Boolean),
    product_image_urls: [selectedAz.image_url].filter(Boolean),
    competitor_title: selectedCompetitor.title || '',
    product_title: selectedAz.title || '',
    competitor_hotspots: resolveHotspots(
      selectedCompetitor,
      `comp:${selectedCompetitor.id}`,
      'comp'
    ),
    product_hotspots: resolveHotspots(selectedAz, `az:${selectedAz.id}`, 'az'),
    auto_select: true,
    match_competitor_hotspots: matchComp,
    match_product_hotspots: matchAz,
  };
  const res = await fetch('/api/gap-fusion/analyze-design-points', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `设计点分析失败（HTTP ${res.status}）`);
  const selection = data.selection || {};
  v13Selection = {
    points: selection.points || [],
    competitor_summary: selection.competitor_summary || '',
    product_summary: selection.product_summary || '',
  };
  v13SelectedIds = new Set(selection.selected_point_ids || []);
  v13SelectionState = selection.selection_state === 'confirmed' ? 'confirmed' : 'confirmed';
  return selection.selected_points || (v13Selection.points || []).filter((p) =>
    v13SelectedIds.has(p.id)
  );
}

async function handleStart() {
  hideError();
  if (!selectedCompetitor || !selectedAz) {
    showError('请先选择外部竞品与 AZ 热卖款');
    return;
  }
  const sig = `${selectedAz.product_url || selectedAz.url || ''}|${selectedCompetitor.id}`;
  if (sig === lastSubmitSig && Date.now() - lastSubmitAt < 3000) {
    if (!window.confirm('3 秒内已提交过同一对款，仍要再提交？')) return;
  }
  btnEl.disabled = true;
  v13Analyzing = true;
  syncStart();
  btnEl.textContent = '分析设计点中…';
  let selectedPoints = [];
  try {
    selectedPoints = await autoAnalyzeDesignPoints();
    showToast('已按爆点语义自动对齐设计点');
  } catch (err) {
    // 分析失败仍允许跳过设计点提交，避免卡死
    console.warn(err);
    showToast('设计点分析失败，将跳过设计点继续合成');
    v13SelectionState = 'skipped';
    selectedPoints = [];
  }

  btnEl.textContent = '提交中…';
  const payload = {
    gap_tags: trendLabels(),
    az_gap_tags: azTrendLabels(),
    competitor_points: checkedPointDisplays('comp'),
    az_points: checkedPointDisplays('az'),
    selected_design_points: selectedPoints,
    skip_design_selection: v13SelectionState === 'skipped' || !selectedPoints.length,
    week_label: selectedCompetitor.week || weekSelect.value,
    extra_note: '',
    competitor_product_id: selectedCompetitor.id,
    competitor_product_title: selectedCompetitor.title,
    competitor_product_image_url: selectedCompetitor.image_url,
    competitor_detail_images:
      selectedCompetitor.detail_images && selectedCompetitor.detail_images.length
        ? selectedCompetitor.detail_images
        : [selectedCompetitor.image_url].filter(Boolean),
    competitor_source_url: selectedCompetitor.source_url || selectedCompetitor.product_url || '',
    competitor_source_site: 'weekly_gap_scheme4',
    az_product_url: selectedAz.product_url || selectedAz.url || '',
    az_product_image_urls: [selectedAz.image_url],
    az_title: selectedAz.title,
  };
  try {
    const res = await fetch('/api/gap-fusion', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.detail || `提交失败（HTTP ${res.status}）`);
    }
    const data = await res.json();
    const shortId = String(data.id || '').slice(0, 8);
    const sig = `${payload.az_product_url}|${payload.competitor_product_id}`;
    lastSubmitSig = sig;
    lastSubmitAt = Date.now();
    showToast(
      `新款已进入成品库 · <a href="/library.html?id=${encodeURIComponent(data.id)}">${shortId}</a> · 双爆款合成`,
      8000,
      true
    );
    selectedCompetitor = null;
    selectedAz = null;
    selectedHintEl.textContent = '未选竞品';
    azSelectedHintEl.textContent = '未选 AZ';
    resetV13Selection();
    renderCompetitorGrid();
    renderAzGrid();
    v13Analyzing = false;
    btnEl.disabled = false;
    btnEl.textContent = '生成新款';
    syncStart();
  } catch (err) {
    showError(err.message || '提交失败');
    showToast(err.message || '提交失败');
    v13Analyzing = false;
    btnEl.disabled = false;
    btnEl.textContent = '生成新款';
  }
}

async function reloadSeed({ keepSelection = false } = {}) {
  const cat = catSelect.value === '全部' ? 'AT' : catSelect.value;
  const week = weekSelect.value || '';
  const qs = new URLSearchParams({ category: cat });
  if (week) qs.set('week', week);
  const res = await fetch('/api/gap-fusion/seed?' + qs.toString());
  const data = await res.json();
  seed = data.seed || {};
  dimensions = (data.dimensions && data.dimensions.dimensions) || [];
  const src = data.sources || {};
  const crawlerNote = src.crawler && src.crawler.image_note ? src.crawler.image_note : '';
  const azNote = src.az_hot && src.az_hot.note ? src.az_hot.note : '';
  if (workflowNoteEl) {
    workflowNoteEl.textContent = [
      data.workflow && data.workflow.note,
      src.data_source ? `数据源=${src.data_source}` : '',
      crawlerNote,
      azNote,
    ]
      .filter(Boolean)
      .join(' · ');
  }
  const weeks = seed.weeks || [];
  const prevWeek = weekSelect.value;
  weekSelect.innerHTML = weeks
    .map(
      (w) =>
        `<option value="${escapeHtml(w)}" ${w === (prevWeek || seed.default_week) ? 'selected' : ''}>${escapeHtml(w)}</option>`
    )
    .join('');
  siteFiltersEl.innerHTML = (seed.sites || [])
    .map(
      (s) =>
        `<label class="hot-site-chip"><input type="checkbox" value="${escapeHtml(s)}" checked/> ${escapeHtml(s)}</label>`
    )
    .join('');
  if (!keepSelection) {
    selectedCompetitor = null;
    selectedAz = null;
    hotspotCache.clear();
    selectedHintEl.textContent = '未选竞品';
    azSelectedHintEl.textContent = '未选 AZ';
    resetV13Selection();
  }
  pickCatalog = null;
  pickCatalogCat = '';
  renderTrendBoard();
  renderCompetitorGrid();
  await loadAzHot();
  syncStart();
  return data;
}

function readMonitorPick() {
  try {
    const raw = sessionStorage.getItem('bloom_monitor_fusion_pick');
    if (!raw) return null;
    const p = JSON.parse(raw);
    return p && p.id ? p : null;
  } catch (err) {
    return null;
  }
}

function pinMonitorProduct(p) {
  if (!p || !p.id || !seed) return;
  monitorPinnedProduct = p;
  const list = seed.competitor_products || [];
  if (!list.some((x) => x.id === p.id)) {
    seed.competitor_products = [p, ...list];
  }
  if (p.site) {
    const sites = seed.sites || [];
    if (!sites.includes(p.site)) seed.sites = [...sites, p.site];
    if (siteFiltersEl) {
      const exists = Array.from(siteFiltersEl.querySelectorAll('input[type="checkbox"]')).some(
        (el) => el.value === p.site
      );
      if (!exists) {
        siteFiltersEl.insertAdjacentHTML(
          'beforeend',
          `<label class="hot-site-chip"><input type="checkbox" value="${escapeHtml(p.site)}" checked/> ${escapeHtml(p.site)}</label>`
        );
      }
    }
  }
}

async function bootstrap() {
  btnEl.addEventListener('click', handleStart);
  if (btnV13Analyze) {
    btnV13Analyze.addEventListener('click', () => analyzeDesignPoints({ silent: false }));
  }
  if (btnV13Confirm) btnV13Confirm.addEventListener('click', () => confirmDesignPoints({ skip: false }));
  if (btnV13Skip) btnV13Skip.addEventListener('click', () => confirmDesignPoints({ skip: true }));
  if (btnPickComp) btnPickComp.addEventListener('click', () => openPicker('comp'));
  if (btnPickAz) btnPickAz.addEventListener('click', () => openPicker('az'));
  if (pickConfirmEl) pickConfirmEl.addEventListener('click', () => confirmPick());
  if (pickModalEl) {
    pickModalEl.querySelectorAll('[data-pick-close="1"]').forEach((el) => {
      el.addEventListener('click', closePicker);
    });
  }
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape' && pickModalEl && !pickModalEl.classList.contains('hidden')) closePicker();
  });
  document.addEventListener('click', (ev) => {
    if (!pickModalEl || pickModalEl.classList.contains('hidden')) return;
    if (!ev.target.closest('.zf-ms')) closePickMenus();
  });
  weekSelect.addEventListener('change', async () => {
    await reloadSeed({ keepSelection: false });
  });
  catSelect.addEventListener('change', async () => {
    await reloadSeed({ keepSelection: false });
  });
  if (siteFiltersEl) siteFiltersEl.addEventListener('change', () => renderCompetitorGrid());

  const params = new URLSearchParams(location.search);
  const fromMonitor = params.get('from') === 'monitor';
  const wantComp = params.get('competitor_id');
  const wantAz = params.get('az_url');
  const wantCat = params.get('category');
  const wantWeek = params.get('week');
  if (wantCat && Array.from(catSelect.options).some((o) => o.value === wantCat)) {
    catSelect.value = wantCat;
  }

  await reloadSeed({ keepSelection: false });
  if (wantWeek && Array.from(weekSelect.options).some((o) => o.value === wantWeek)) {
    weekSelect.value = wantWeek;
  }

  const pick = fromMonitor ? readMonitorPick() : null;
  if (pick) pinMonitorProduct(pick);

  const preferred = wantComp
    ? (seed.competitor_products || []).find((p) => p.id === wantComp) ||
      pick ||
      (seed.competitor_products || []).find((p) => p.id === wantComp)
    : fromMonitor
      ? pick
      : null;
  if (wantComp && !preferred) {
    showToast('未找到指定竞品，请从竞品商品库选择');
  }
  if (preferred) {
    await selectCompetitor(preferred.id, false, {
      skipAzDefault: true,
      pinned: pick || preferred,
    });
    if (fromMonitor) {
      showToast('已从货盘带入该款为竞品 · 请勾要保留的属性，再从内部商品库选自有款');
      competitorGridEl?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }
  if (wantAz) {
    const azMatch = azProducts.find((p) => (p.product_url || p.url) === wantAz);
    if (azMatch) await selectAz(azMatch.id, false, { pinned: azMatch });
  }
}

bootstrap().catch((err) => showError('加载失败：' + (err.message || err)));
