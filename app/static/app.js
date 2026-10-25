/* ─── AZ Bloom — app.js ────────────────────────────── */
/* 爆款合成页：加载竞品爆款列表，单选 + AZ URL，人为干预 Prompt，调用一键合成。 */

const FALLBACK_DIMENSIONS = [
  {
    key: 'silhouette',
    label: '廓形 / 版型',
    options: [
      { value: 'A-Line', label: 'A-Line 公主线', source: 'az' },
      { value: 'Column', label: 'Column 直筒', source: 'az' },
      { value: 'Fit and Flare', label: 'Fit and Flare 收腰伞摆', source: 'az' },
      { value: 'Mermaid', label: 'Mermaid 鱼尾', source: 'az' },
    ],
  },
  {
    key: 'neckline_shoulder',
    label: '领口 / 肩型',
    options: [
      { value: 'V-Neck', label: 'V-Neck V领', source: 'az' },
      { value: 'Sweetheart', label: 'Sweetheart 心形领', source: 'az' },
      { value: 'Strapless', label: 'Strapless 抹胸', source: 'both' },
      { value: 'One Shoulder', label: 'One Shoulder 单肩', source: 'both' },
      { value: 'Square Neckline', label: 'Square 方领', source: 'both' },
    ],
  },
  {
    key: 'sleeve',
    label: '袖型',
    options: [
      { value: 'Sleeveless', label: '无袖', source: 'az' },
      { value: 'Spaghetti Straps', label: '细肩带', source: 'both' },
      { value: 'Long Sleeve', label: '长袖', source: 'az' },
    ],
  },
  {
    key: 'waist',
    label: '腰线 / 腰臀',
    options: [
      { value: 'Natural Waist', label: '自然腰', source: 'az' },
      { value: 'Corset Bodice', label: '胸衣 / 鱼骨收腰', source: 'competitor' },
      { value: 'Dropped Waist', label: '落腰 Dropped', source: 'competitor' },
    ],
  },
  {
    key: 'skirt_hem',
    label: '裙摆 / 下摆',
    options: [
      { value: 'Layered Hem', label: '层叠裙摆', source: 'az' },
      { value: 'Thigh High Split', label: '高开叉', source: 'competitor' },
      { value: 'High-Low Hem', label: '前短后长', source: 'az' },
    ],
  },
  {
    key: 'length',
    label: '衣长 / 裙长',
    options: [
      { value: 'Midi', label: 'Midi 及小腿', source: 'both' },
      { value: 'Maxi', label: 'Maxi 及地', source: 'both' },
      { value: 'Floor Length', label: 'Floor Length 拖地', source: 'az' },
    ],
  },
  {
    key: 'fabric',
    label: '面料 / 质感',
    options: [
      { value: 'Chiffon', label: 'Chiffon 雪纺', source: 'both' },
      { value: 'Satin', label: 'Satin 缎面', source: 'both' },
      { value: 'Crepe', label: 'Crepe 绉缎', source: 'both' },
      { value: 'Lace', label: 'Lace 蕾丝', source: 'both' },
    ],
  },
  {
    key: 'color_print',
    label: '色彩 / 印花',
    options: [
      { value: 'Solid Color', label: '纯色', source: 'az' },
      { value: 'Floral Print', label: '碎花印花', source: 'az' },
      { value: 'Keep AZ Colorway', label: '保留 AZ 现有配色', source: 'az' },
    ],
  },
];

const SOURCE_LABEL = { az: 'AZ', competitor: '竞品', both: 'AZ+竞品' };

const categorySelectEl = document.getElementById('category-select');
const targetUrlEl = document.getElementById('target-url');
const updatedAtEl = document.getElementById('updated-at');
const productGridEl = document.getElementById('product-grid');
const emptyStateEl = document.getElementById('empty-state');
const azUrlEl = document.getElementById('az-url');
const selectedHintEl = document.getElementById('selected-hint');
const btnSynthesizeEl = document.getElementById('btn-synthesize');
const synthErrorEl = document.getElementById('synth-error');

/** @type {string} */
let activeCategoryId = 'AT';

const btnAzConfirmEl = document.getElementById('btn-az-confirm');
const azGalleryErrorEl = document.getElementById('az-gallery-error');
const azGalleryPanelEl = document.getElementById('az-gallery-panel');
const azGalleryMetaEl = document.getElementById('az-gallery-meta');
const azGalleryLoadingEl = document.getElementById('az-gallery-loading');
const azGalleryGroupsEl = document.getElementById('az-gallery-groups');

const interventionElementsEl = document.getElementById('intervention-elements');
const interventionNoteEl = document.getElementById('intervention-note');
const interventionPromptEl = document.getElementById('intervention-prompt');
const btnBuildPromptEl = document.getElementById('btn-build-prompt');
const btnFillCompetitorEl = document.getElementById('btn-fill-from-competitor');
const interventionHintEl = document.getElementById('intervention-hint');
const promptStatusEl = document.getElementById('prompt-status');
const stepBuildEl = document.getElementById('step-build');
const stepReadyEl = document.getElementById('step-ready');

/** @type {string|null} */
let selectedProductId = null;
/** @type {Map<string, object>} */
const productMap = new Map();
let azGalleryImageUrls = [];
let azGalleryFetchedForUrl = '';
let toastTimer = null;
const toastEl = document.getElementById('toast');

/** @type {Array<object>} */
let interventionDimensions = FALLBACK_DIMENSIONS;
/** 是否已通过「一键生成完整 Prompt」得到可用入参 */
let promptReady = false;

function formatUpdatedAt(isoString) {
  if (!isoString) return '';
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return isoString;
  return `更新于 ${date.toLocaleString('zh-CN', { hour12: false })}`;
}

const CURRENCY_SYMBOLS = { USD: '$', AUD: 'AU$', CNY: '¥', EUR: '€', GBP: '£' };

function formatPrice(price, currency) {
  if (price == null || Number(price) === 0) return '价格待补';
  const symbol = CURRENCY_SYMBOLS[currency] || `${currency} `;
  return `${symbol}${Number(price).toFixed(2)}`;
}

function applyAzPrefill(product) {
  if (!product) return;
  const azUrl = (product.az_product_url || '').trim();
  const azImages = Array.isArray(product.az_product_image_urls)
    ? product.az_product_image_urls.filter(Boolean)
    : [];
  if (azUrl) {
    azUrlEl.value = azUrl;
  }
  if (azUrl && azImages.length) {
    azGalleryImageUrls = azImages.slice(0, 8);
    azGalleryFetchedForUrl = azUrl;
    azGalleryPanelEl.classList.remove('hidden');
    azGalleryLoadingEl.classList.add('hidden');
    hideAzGalleryError();
    azGalleryMetaEl.textContent = `来自 inputs.json · 共 ${azGalleryImageUrls.length} 张（可再点确认从商城拉取）`;
    renderAzGallery(azImages.map((url) => ({ url, color: '' })));
  } else if (azUrl) {
    clearAzGalleryState();
  }
  syncSynthesizeState();
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function getInterventionSelections() {
  /** @type {Record<string, string>} */
  const selections = {};
  interventionElementsEl.querySelectorAll('select[data-dim-key]').forEach((sel) => {
    const key = sel.dataset.dimKey;
    const value = sel.value.trim();
    if (key && value) selections[key] = value;
  });
  return selections;
}

function hasInterventionInput() {
  return Object.keys(getInterventionSelections()).length > 0 || Boolean(interventionNoteEl.value.trim());
}

function invalidatePrompt(reason) {
  if (!promptReady && !interventionPromptEl.value.trim()) {
    syncInterventionUi(reason);
    return;
  }
  promptReady = false;
  interventionPromptEl.readOnly = true;
  if (interventionPromptEl.value.trim()) {
    // 保留旧文案便于对照，但标记失效，需重新生成
  }
  syncInterventionUi(reason || '属性或简述已变更，请重新生成完整 Prompt');
}

function syncInterventionUi(message) {
  const hasInput = hasInterventionInput();
  btnBuildPromptEl.disabled = !hasInput;
  btnFillCompetitorEl.disabled = !selectedProductId;

  if (interventionHintEl) {
    interventionHintEl.textContent =
      message ||
      (hasInput
        ? '已选干预内容 · 可生成 Prompt，或不生成直接一键合成'
        : '可不填，直接选竞品后一键合成；填写后可生成 Prompt 指导生成');
  }

  if (promptStatusEl) {
    if (promptReady && interventionPromptEl.value.trim()) {
      promptStatusEl.textContent = '已生成 · 将作为合成入参（可微调）';
      promptStatusEl.className = 'prompt-status is-ready';
    } else if (hasInput) {
      promptStatusEl.textContent = '未生成 Prompt · 仍可直接合成';
      promptStatusEl.className = 'prompt-status';
    } else {
      promptStatusEl.textContent = '未使用 · 可直接一键合成';
      promptStatusEl.className = 'prompt-status';
    }
  }

  document.querySelectorAll('.intervention-step').forEach((el) => el.classList.remove('is-active', 'is-done'));
  const step1 = document.querySelector('.intervention-step[data-step="1"]');
  if (promptReady) {
    step1?.classList.add('is-done');
    stepBuildEl?.classList.add('is-done');
    stepReadyEl?.classList.add('is-active');
  } else if (hasInput) {
    step1?.classList.add('is-done');
    stepBuildEl?.classList.add('is-active');
  } else {
    // 无干预时，直接把「一键合成」标为当前可走路径
    step1?.classList.add('is-done');
    stepBuildEl?.classList.add('is-done');
    stepReadyEl?.classList.add('is-active');
  }

  syncSynthesizeState();
}

function sourceBadge(source) {
  const key = source || 'both';
  return `<span class="opt-source opt-source--${escapeHtml(key)}">${escapeHtml(SOURCE_LABEL[key] || key)}</span>`;
}

function shortDimLabel(label) {
  const map = {
    '廓形 / 版型': '版型',
    '领口 / 肩型': '领型',
    '袖型': '袖型',
    '腰线 / 腰臀': '腰线',
    '裙摆 / 下摆': '裙摆',
    '衣长 / 裙长': '裙长',
    '面料 / 质感': '面料',
    '色彩 / 印花': '色彩',
  };
  return map[label] || String(label).split(/[\/·]/)[0].trim();
}

function renderInterventionDimensions(dimensions) {
  interventionDimensions = dimensions;
  interventionElementsEl.innerHTML = '';
  dimensions.forEach((dim) => {
    const wrap = document.createElement('div');
    wrap.className = 'intervention-select';
    const shortLabel = shortDimLabel(dim.label);
    const optionsHtml = [
      `<option value="">—</option>`,
      ...(dim.options || []).map(
        (opt) =>
          `<option value="${escapeHtml(opt.value)}" title="${escapeHtml(opt.label)}">${escapeHtml(opt.value)}</option>`
      ),
    ].join('');
    wrap.innerHTML = `
      <label class="intervention-select__label" for="dim-${escapeHtml(dim.key)}" title="${escapeHtml(dim.label)}">${escapeHtml(shortLabel)}</label>
      <select id="dim-${escapeHtml(dim.key)}" class="field-input intervention-select__control" data-dim-key="${escapeHtml(dim.key)}">
        ${optionsHtml}
      </select>
    `;
    const select = wrap.querySelector('select');
    select.addEventListener('change', () => invalidatePrompt());
    interventionElementsEl.appendChild(wrap);
  });
  syncInterventionUi();
}

async function loadInterventionOptions() {
  try {
    const res = await fetch('/api/synthesis/options');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const dims = Array.isArray(data.dimensions) ? data.dimensions : FALLBACK_DIMENSIONS;
    renderInterventionDimensions(dims);
  } catch (err) {
    console.warn('加载干预选项失败，使用本地兜底：', err);
    renderInterventionDimensions(FALLBACK_DIMENSIONS);
  }
}

function matchOptionValue(dimKey, rawValue) {
  if (!rawValue) return '';
  const dim = interventionDimensions.find((d) => d.key === dimKey);
  if (!dim) return '';
  const text = String(rawValue).trim();
  const exact = (dim.options || []).find(
    (o) => o.value.toLowerCase() === text.toLowerCase() || o.label.toLowerCase() === text.toLowerCase()
  );
  if (exact) return exact.value;
  const fuzzy = (dim.options || []).find(
    (o) =>
      text.toLowerCase().includes(o.value.toLowerCase()) ||
      o.value.toLowerCase().includes(text.toLowerCase().split(/[\/·]/)[0].trim())
  );
  return fuzzy ? fuzzy.value : '';
}

function applyCompetitorAttributes(product) {
  if (!product) return;
  const mapping = [
    ['silhouette', product.silhouette],
    ['neckline_shoulder', product.neckline],
    ['fabric', product.fabric],
    ['length', product.length],
    ['color_print', product.color_name ? 'Solid Color' : ''],
  ];
  // 从 aesthetic_tag 推断腰线 / 裙摆
  const tag = product.aesthetic_tag || '';
  if (/Corset/i.test(tag)) mapping.push(['waist', 'Corset Bodice']);
  if (/Dropped/i.test(tag)) mapping.push(['waist', 'Dropped Waist']);
  if (/Split/i.test(tag)) mapping.push(['skirt_hem', 'Thigh High Split']);
  if (/Flared/i.test(tag)) mapping.push(['skirt_hem', 'Godet Panels']);
  if (/Pleated/i.test(tag)) mapping.push(['skirt_hem', 'Pleated Skirt']);

  let filled = 0;
  mapping.forEach(([key, raw]) => {
    const matched = matchOptionValue(key, raw);
    const sel = interventionElementsEl.querySelector(`select[data-dim-key="${key}"]`);
    if (sel && matched) {
      sel.value = matched;
      filled += 1;
    }
  });
  invalidatePrompt(filled ? `已预填 ${filled} 项竞品属性，请生成完整 Prompt` : '该竞品暂无足够属性可预填');
  showToast(filled ? `已用竞品属性预填 ${filled} 项` : '该竞品缺少可匹配属性');
}

async function handleBuildPrompt() {
  hideSynthError();
  if (!hasInterventionInput()) {
    showSynthError('请至少选择一项属性下拉，或填写自然语言简述');
    return;
  }

  btnBuildPromptEl.disabled = true;
  btnBuildPromptEl.textContent = '生成中...';
  try {
    const selections = getInterventionSelections();
    const res = await fetch('/api/synthesis/build-prompt', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        selections,
        note: interventionNoteEl.value.trim(),
      }),
    });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.detail || `生成 Prompt 失败（HTTP ${res.status}）`);
    }
    const data = await res.json();
    interventionPromptEl.value = data.prompt || '';
    interventionPromptEl.readOnly = false;
    promptReady = Boolean(interventionPromptEl.value.trim());
    showToast('完整 Prompt 已生成，可作为合成入参（可微调）');
  } catch (err) {
    console.error(err);
    showSynthError(err.message || '生成 Prompt 失败');
  } finally {
    btnBuildPromptEl.innerHTML = '一键生成完整 Prompt';
    syncInterventionUi();
  }
}

function syncSynthesizeState() {
  const azOk = Boolean(azUrlEl.value.trim());
  const productOk = Boolean(selectedProductId);
  // 人为干预可选：只要 AZ URL + 已选竞品即可合成
  btnSynthesizeEl.disabled = !(azOk && productOk);

  if (selectedProductId) {
    const product = productMap.get(selectedProductId);
    selectedHintEl.textContent = product ? `已选：${product.title}` : '已选择 1 个竞品爆款';
    selectedHintEl.className = 'section-bar__hint is-selected';
  } else {
    selectedHintEl.textContent = '请选择 1 个竞品爆款';
    selectedHintEl.className = 'section-bar__hint';
  }

  if (btnFillCompetitorEl) btnFillCompetitorEl.disabled = !selectedProductId;
}

function selectProduct(productId) {
  if (selectedProductId === productId) {
    selectedProductId = null;
  } else {
    selectedProductId = productId;
  }

  productGridEl.querySelectorAll('.product-card').forEach((card) => {
    const isSelected = card.dataset.productId === selectedProductId;
    card.classList.toggle('product-card--selected', isSelected);
    card.setAttribute('aria-checked', String(isSelected));
    const radio = card.querySelector('.product-card__radio');
    if (radio) radio.checked = isSelected;
  });

  if (selectedProductId) {
    applyAzPrefill(productMap.get(selectedProductId));
  }

  syncSynthesizeState();
  hideSynthError();
  if (btnFillCompetitorEl) btnFillCompetitorEl.disabled = !selectedProductId;
}

function renderProductCard(product) {
  const card = document.createElement('div');
  card.className = 'product-card';
  card.dataset.productId = product.id;
  card.setAttribute('role', 'radio');
  card.setAttribute('aria-checked', 'false');
  card.tabIndex = 0;

  const metaParts = [];
  if (product.rank != null) metaParts.push(`人气榜 No.${product.rank}`);
  if (product.fabric) metaParts.push(product.fabric);

  card.innerHTML = `
    <div class="product-card__select">
      <input class="product-card__radio" type="radio" name="competitor-product" value="${escapeHtml(product.id)}" />
    </div>
    <img class="product-card__image" src="${escapeHtml(product.image_url)}" alt="${escapeHtml(product.title)}" loading="lazy" />
    <div class="product-card__body">
      <div class="product-card__title" title="${escapeHtml(product.title)}">${escapeHtml(product.title)}</div>
      <div class="product-card__price">${formatPrice(product.price, product.currency)}</div>
      <div class="product-card__meta">${escapeHtml(product.source_site)}${metaParts.length ? ' · ' + escapeHtml(metaParts.join(' · ')) : ''}</div>
      <a class="product-card__link" href="${escapeHtml(product.source_url)}" target="_blank" rel="noopener noreferrer">
        查看原页 →
      </a>
    </div>
  `;

  card.addEventListener('click', (event) => {
    if (event.target.closest('a')) return;
    selectProduct(product.id);
    card.setAttribute('aria-checked', String(selectedProductId === product.id));
  });

  card.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      selectProduct(product.id);
      card.setAttribute('aria-checked', String(selectedProductId === product.id));
    }
  });

  return card;
}

function hideSynthError() {
  synthErrorEl.classList.add('hidden');
  synthErrorEl.textContent = '';
}

function showSynthError(message) {
  synthErrorEl.textContent = message;
  synthErrorEl.classList.remove('hidden');
}

function showToast(message, durationMs = 2600) {
  if (!toastEl) return;
  toastEl.textContent = message;
  toastEl.classList.remove('hidden');
  requestAnimationFrame(() => toastEl.classList.add('is-visible'));
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastEl.classList.remove('is-visible');
    setTimeout(() => toastEl.classList.add('hidden'), 220);
  }, durationMs);
}

function hasAzGalleryImages() {
  const azUrl = azUrlEl.value.trim();
  return Boolean(azUrl) && azUrl === azGalleryFetchedForUrl && azGalleryImageUrls.length > 0;
}

function clearAzGalleryState() {
  azGalleryImageUrls = [];
  azGalleryFetchedForUrl = '';
  azGalleryPanelEl.classList.add('hidden');
  azGalleryGroupsEl.innerHTML = '';
  azGalleryMetaEl.textContent = '';
  hideAzGalleryError();
}

async function loadCategories() {
  if (!categorySelectEl) return;
  try {
    const res = await fetch('/api/selection/categories');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const cats = Array.isArray(data.categories) ? data.categories : [];
    categorySelectEl.innerHTML = cats
      .map((c) => {
        const count = c.item_count != null ? `（${c.item_count}）` : '';
        return `<option value="${escapeHtml(c.id)}">${escapeHtml(c.label || c.id)}${escapeHtml(count)}</option>`;
      })
      .join('');
    if (!cats.some((c) => c.id === activeCategoryId) && cats[0]) {
      activeCategoryId = cats[0].id;
    }
    categorySelectEl.value = activeCategoryId;
  } catch (err) {
    console.warn('加载品类失败：', err);
    categorySelectEl.innerHTML = '<option value="AT">Atelier / Formal</option>';
  }
}

async function loadSelection(categoryId) {
  const cat = (categoryId || activeCategoryId || '').trim();
  activeCategoryId = cat;
  try {
    const qs = cat ? `?category=${encodeURIComponent(cat)}` : '';
    const res = await fetch(`/api/selection${qs}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    targetUrlEl.value = data.target_url || '';
    const label = data.category_label || cat;
    updatedAtEl.textContent = label
      ? `${label}${data.updated_at ? ' · ' + formatUpdatedAt(data.updated_at) : ''}`
      : formatUpdatedAt(data.updated_at);

    productGridEl.innerHTML = '';
    productMap.clear();
    selectedProductId = null;
    clearAzGalleryState();
    azUrlEl.value = '';

    if (!data.products || data.products.length === 0) {
      emptyStateEl.textContent =
        cat === 'AT'
          ? 'AT 种子数据为空，请检查 data/seed_products.json'
          : `品类 ${label || cat} 暂无商品，请在 data/gallery/inputs.json 追加 items`;
      emptyStateEl.classList.remove('hidden');
      syncSynthesizeState();
      return;
    }

    emptyStateEl.classList.add('hidden');
    data.products.forEach((product) => {
      productMap.set(product.id, product);
      productGridEl.appendChild(renderProductCard(product));
    });

    // AT：页面级默认 AZ（上一版 Liorah）；其它品类靠商品卡自带 az_* 预填
    if (data.default_az_product_url) {
      applyAzPrefill({
        az_product_url: data.default_az_product_url,
        az_product_image_urls: data.default_az_product_image_urls || [],
      });
    }

    const first = data.products[0];
    if (first) {
      selectProduct(first.id);
    } else {
      syncSynthesizeState();
    }
  } catch (err) {
    console.error('加载选品数据失败：', err);
    targetUrlEl.value = '';
    targetUrlEl.placeholder = '加载失败，请稍后重试或手动输入';
    emptyStateEl.textContent = '数据加载失败，请检查后端服务是否正常';
    emptyStateEl.classList.remove('hidden');
    syncSynthesizeState();
  }
}

async function handleSynthesize() {
  hideSynthError();

  const azUrl = azUrlEl.value.trim();
  if (!azUrl) {
    showSynthError('请填写 AZ 爆款商品 URL');
    return;
  }
  if (!selectedProductId) {
    showSynthError('请单选 1 个竞品爆款商品');
    return;
  }
  if (!hasAzGalleryImages()) {
    showToast('请先点击「确认」，获取 AZ 爆款商品图片列表');
    btnAzConfirmEl?.focus();
    return;
  }

  const product = productMap.get(selectedProductId);
  if (!product) {
    showSynthError('所选竞品商品无效，请重新选择');
    return;
  }

  btnSynthesizeEl.disabled = true;
  btnSynthesizeEl.textContent = '合成中...';

  try {
    const res = await fetch('/api/synthesis', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        az_product_url: azUrl,
        az_product_image_urls: azGalleryImageUrls.slice(0, 8),
        competitor_product_id: selectedProductId,
        competitor_product_title: product.title,
        competitor_product_image_url: product.image_url,
        competitor_detail_images: Array.isArray(product.detail_images) ? product.detail_images : [],
        competitor_source_url: product.source_url,
        competitor_source_site: product.source_site,
        intervention_selections: getInterventionSelections(),
        intervention_elements: Object.keys(getInterventionSelections()),
        intervention_note: interventionNoteEl.value.trim(),
        intervention_prompt: interventionPromptEl.value.trim(),
      }),
    });

    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.detail || `合成失败（HTTP ${res.status}）`);
    }

    const data = await res.json();
    window.location.href = `/result.html?id=${encodeURIComponent(data.id)}`;
  } catch (err) {
    console.error('一键合成失败：', err);
    showSynthError(err.message || '一键合成失败，请稍后重试');
    btnSynthesizeEl.textContent = '一键合成';
    syncSynthesizeState();
  }
}

function hideAzGalleryError() {
  azGalleryErrorEl.classList.add('hidden');
  azGalleryErrorEl.textContent = '';
}

function showAzGalleryError(message) {
  azGalleryErrorEl.textContent = message;
  azGalleryErrorEl.classList.remove('hidden');
}

function renderAzGallery(images) {
  azGalleryGroupsEl.innerHTML = '';
  if (!images || images.length === 0) {
    azGalleryGroupsEl.innerHTML = '<div class="empty-state">未获取到图片</div>';
    return;
  }
  azGalleryGroupsEl.innerHTML = images
    .map(
      (img) => `
      <a class="az-gallery-thumb" href="${escapeHtml(img.url)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(img.color || '')}">
        <img src="${escapeHtml(img.url)}" alt="${escapeHtml(img.color || '')}" loading="lazy" />
      </a>
    `
    )
    .join('');
}

async function handleAzConfirm() {
  hideAzGalleryError();
  const azUrl = azUrlEl.value.trim();
  if (!azUrl) {
    showAzGalleryError('请先填写 AZ 爆款商品 URL');
    return;
  }

  btnAzConfirmEl.disabled = true;
  btnAzConfirmEl.textContent = '获取中...';
  azGalleryPanelEl.classList.remove('hidden');
  azGalleryGroupsEl.innerHTML = '';
  azGalleryMetaEl.textContent = '';
  azGalleryLoadingEl.classList.remove('hidden');
  azGalleryImageUrls = [];
  azGalleryFetchedForUrl = '';

  try {
    const res = await fetch(`/api/az-product-images?url=${encodeURIComponent(azUrl)}`);
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      throw new Error(data.error || data.detail || `获取商品图片失败（HTTP ${res.status}）`);
    }
    const images = Array.isArray(data.images) ? data.images : [];
    azGalleryImageUrls = images.map((img) => img.url).filter(Boolean);
    if (azGalleryImageUrls.length === 0) {
      throw new Error('未获取到 AZ 商品图片，请检查链接后重试');
    }
    azGalleryFetchedForUrl = azUrl;
    azGalleryMetaEl.textContent = `商品 ID：${data.goods_id || '—'} · 颜色：${data.color_key || '—'} · 共 ${data.image_count} 张`;
    renderAzGallery(images);
  } catch (err) {
    console.error('获取 AZ 商品图片失败：', err);
    showAzGalleryError(err.message || '获取商品图片失败，请稍后重试');
    azGalleryPanelEl.classList.add('hidden');
    azGalleryImageUrls = [];
    azGalleryFetchedForUrl = '';
  } finally {
    azGalleryLoadingEl.classList.add('hidden');
    btnAzConfirmEl.disabled = false;
    btnAzConfirmEl.textContent = '确认';
  }
}

azUrlEl.addEventListener('input', () => {
  hideSynthError();
  if (azGalleryFetchedForUrl && azUrlEl.value.trim() !== azGalleryFetchedForUrl) {
    clearAzGalleryState();
  }
  syncSynthesizeState();
});
btnSynthesizeEl.addEventListener('click', handleSynthesize);
btnAzConfirmEl.addEventListener('click', handleAzConfirm);
btnBuildPromptEl.addEventListener('click', handleBuildPrompt);
btnFillCompetitorEl?.addEventListener('click', () => {
  if (!selectedProductId) {
    showToast('请先选择竞品');
    return;
  }
  applyCompetitorAttributes(productMap.get(selectedProductId));
});
interventionNoteEl.addEventListener('input', () => invalidatePrompt());
interventionPromptEl.addEventListener('input', () => {
  // 生成后允许微调；只要仍有内容就保持 ready
  promptReady = Boolean(interventionPromptEl.value.trim());
  syncInterventionUi();
});
categorySelectEl?.addEventListener('change', () => {
  activeCategoryId = categorySelectEl.value;
  loadSelection(activeCategoryId);
});

loadInterventionOptions();
loadCategories().then(() => loadSelection(activeCategoryId));
