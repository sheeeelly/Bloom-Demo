/* ─── AZ Bloom — result.js ────────────────────────────── */
/* 结果页：爆款合成 / 设计款共用轮询与展示。 */

const loadingEl = document.getElementById('loading-state');
const pendingEl = document.getElementById('pending-state');
const pendingMessageEl = document.getElementById('pending-message');
const errorEl = document.getElementById('error-state');
const contentEl = document.getElementById('result-content');
const panoramaSectionEl = document.getElementById('panorama-section');
const panoramaWrapEl = document.getElementById('panorama-wrap');
const imageGridEl = document.getElementById('image-grid');
const compareStripEl = document.getElementById('compare-strip');
const compareAzImagesEl = document.getElementById('compare-az-images');
const compareCompImagesEl = document.getElementById('compare-comp-images');
const compareAiThumbsEl = document.getElementById('compare-ai-thumbs');
const compareAzTitleEl = document.getElementById('compare-az-title');
const compareCompTitleEl = document.getElementById('compare-comp-title');
const compareCompCardEl = document.getElementById('compare-comp-card');
const reportDocsSectionEl = document.getElementById('report-docs-section');
const reportDocsEl = document.getElementById('report-docs');
const reportSummaryEl = document.getElementById('report-summary');
const attrsSectionEl = document.getElementById('attrs-section');
const productAttributesEl = document.getElementById('product-attributes');
const azUrlEl = document.getElementById('result-az-url');
const competitorTitleEl = document.getElementById('result-competitor-title');
const resultKindEl = document.getElementById('result-kind');
const metaAzRowEl = document.getElementById('meta-az-row');
const metaCompetitorRowEl = document.getElementById('meta-competitor-row');
const metaSourceRowEl = document.getElementById('meta-source-row');
const resultSourceUrlEl = document.getElementById('result-source-url');
const metaTitleLabelEl = document.getElementById('meta-title-label');
const pageTitleEl = document.getElementById('result-page-title');
const pageSubEl = document.getElementById('result-page-sub');
const pageBackEl = document.getElementById('page-back');
const navSynthesisEl = document.getElementById('nav-synthesis');
const navDesignEl = document.getElementById('nav-design');
const btnDownloadEl = document.getElementById('btn-download');
const generatedAttrsSectionEl = document.getElementById('generated-attrs-section');
const generatedAttrsHintEl = document.getElementById('generated-attrs-hint');
const generatedAttrsGridEl = document.getElementById('generated-attrs-grid');
const similarSectionEl = document.getElementById('similar-peers-section');
const similarHintEl = document.getElementById('similar-peers-hint');
const similarLoadingEl = document.getElementById('similar-peers-loading');
const similarGridEl = document.getElementById('similar-peers-grid');
const similarEmptyEl = document.getElementById('similar-peers-empty');
const btnSimilarRefreshEl = document.getElementById('btn-similar-refresh');
const similarTaskBadgeEl = document.getElementById('similar-task-badge');

let currentTaskId = '';
let similarPeersLoaded = false;

const POLL_INTERVAL_MS = 3000;
const POLL_TIMEOUT_MS = 35 * 60 * 1000;
let pollStartedAt = 0;

function resultKindLabel(data) {
  const kind = (data && data.kind) || 'hot_synthesis';
  if (kind === 'design') return '趋势改造';
  return '双爆款合成';
}

const VISIBLE_REPORT_KEYS_SYNTHESIS = ['报告2', '报告4', '报告5', '报告6', '报告7'];

function getResultId() {
  const params = new URLSearchParams(window.location.search);
  return params.get('id');
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function renderReportHtml(markdown) {
  const lines = String(markdown || '').split('\n');
  const html = [];
  let inList = false;
  let inCode = false;

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.trim().startsWith('```')) {
      if (inCode) {
        html.push('</code></pre>');
        inCode = false;
      } else {
        if (inList) {
          html.push('</ul>');
          inList = false;
        }
        html.push('<pre class="result-code"><code>');
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      html.push(`${escapeHtml(line)}\n`);
      continue;
    }
    if (!line.trim()) {
      if (inList) {
        html.push('</ul>');
        inList = false;
      }
      continue;
    }
    if (line.startsWith('## ')) {
      if (inList) {
        html.push('</ul>');
        inList = false;
      }
      html.push(`<h2 class="text-base font-bold mt-4 mb-2">${escapeHtml(line.slice(3))}</h2>`);
      continue;
    }
    if (line.startsWith('# ')) {
      if (inList) {
        html.push('</ul>');
        inList = false;
      }
      html.push(`<h1 class="text-lg font-bold mb-3">${escapeHtml(line.slice(2))}</h1>`);
      continue;
    }
    if (line.startsWith('- ')) {
      if (!inList) {
        html.push('<ul class="list-disc pl-5 space-y-1 text-gray-700">');
        inList = true;
      }
      html.push(`<li>${escapeHtml(line.slice(2))}</li>`);
      continue;
    }
    if (inList) {
      html.push('</ul>');
      inList = false;
    }
    html.push(`<p class="text-gray-700 leading-relaxed mb-2">${escapeHtml(line)}</p>`);
  }
  if (inList) html.push('</ul>');
  if (inCode) html.push('</code></pre>');
  return html.join('');
}

function renderPanorama(panorama) {
  if (!panorama || !panorama.url) {
    panoramaSectionEl.classList.add('hidden');
    panoramaWrapEl.innerHTML = '';
    return;
  }
  panoramaWrapEl.innerHTML = `
    <div class="result-panorama-card">
      <img src="${escapeHtml(panorama.url)}" alt="${escapeHtml(panorama.label || '全景图')}" loading="lazy" />
      <div class="result-panorama-card__label">${escapeHtml(panorama.label || '全景图')}</div>
    </div>
  `;
  panoramaSectionEl.classList.remove('hidden');
}

function renderReportDocs(docs, kind) {
  const allowed =
    kind === 'design'
      ? null
      : VISIBLE_REPORT_KEYS_SYNTHESIS;
  const visibleDocs = Array.isArray(docs)
    ? docs.filter((doc) => (allowed ? allowed.includes(doc.key) : true))
    : [];
  if (visibleDocs.length === 0) {
    reportDocsSectionEl.classList.add('hidden');
    reportDocsEl.innerHTML = '';
    return;
  }
  reportDocsEl.innerHTML = '';
  visibleDocs.forEach((doc) => {
    const item = document.createElement('details');
    item.className = 'result-report-doc';
    item.innerHTML = `
      <summary class="result-report-doc__summary">
        <span class="result-report-doc__key">${escapeHtml(doc.key)}</span>
        <span class="result-report-doc__title">${escapeHtml(doc.title)}</span>
        <svg class="result-report-doc__chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M6 9l6 6 6-6" />
        </svg>
      </summary>
      <div class="result-report-doc__body">${renderReportHtml(doc.content)}</div>
    `;
    reportDocsEl.appendChild(item);
  });
  reportDocsSectionEl.classList.remove('hidden');
}

function renderImages(images) {
  imageGridEl.innerHTML = '';
  images.forEach((item, index) => {
    const card = document.createElement('div');
    card.className = 'result-image-card';
    card.innerHTML = `
      <img src="${escapeHtml(item.url)}" alt="${escapeHtml(item.label || `生成图 ${index + 1}`)}" loading="lazy" />
      <div class="result-image-card__label">${escapeHtml(item.label || `图 ${index + 1}`)}</div>
    `;
    imageGridEl.appendChild(card);
  });
}

function renderImageStrip(container, urls, emptyText) {
  container.innerHTML = '';
  const list = (urls || []).filter(Boolean);
  container.classList.remove(
    'result-compare-card__thumbs--solo',
    'result-compare-card__thumbs--duo',
    'result-compare-card__thumbs--trio'
  );
  if (list.length === 0) {
    container.innerHTML = `<div class="result-compare-empty">${escapeHtml(emptyText || '暂无图片')}</div>`;
    return;
  }
  if (list.length === 1) container.classList.add('result-compare-card__thumbs--solo');
  else if (list.length === 2) container.classList.add('result-compare-card__thumbs--duo');
  else if (list.length === 3) container.classList.add('result-compare-card__thumbs--trio');
  list.slice(0, 8).forEach((url, index) => {
    const a = document.createElement('a');
    a.className = 'result-compare-grid-thumb';
    a.href = url;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.innerHTML = `<img src="${escapeHtml(url)}" alt="图 ${index + 1}" loading="lazy" />`;
    container.appendChild(a);
  });
}

function renderCompareStrip(data, kind) {
  if (!compareStripEl) return;

  if (kind === 'design') {
    compareAzTitleEl.textContent = '上传参考图';
    renderImageStrip(compareAzImagesEl, data.source_image_url ? [data.source_image_url] : [], '暂无参考图');
    if (compareCompCardEl) compareCompCardEl.classList.add('hidden');
    compareStripEl.classList.add('result-compare-strip--design');
  } else {
    compareAzTitleEl.textContent = 'AZ 爆款商品图';
    compareCompTitleEl.textContent = '竞品爆款商品图';
    const azUrls = Array.isArray(data.az_product_image_urls) ? data.az_product_image_urls : [];
    let compUrls = Array.isArray(data.competitor_detail_images) ? data.competitor_detail_images : [];
    if (compUrls.length === 0 && data.competitor_product_image_url) {
      compUrls = [data.competitor_product_image_url];
    }
    renderImageStrip(compareAzImagesEl, azUrls, '暂无 AZ 图（合成时未确认拉取）');
    renderImageStrip(compareCompImagesEl, compUrls, '暂无竞品图');
    if (compareCompCardEl) compareCompCardEl.classList.remove('hidden');
    compareStripEl.classList.remove('result-compare-strip--design');
  }

  compareAiThumbsEl.innerHTML = '';
  const images = Array.isArray(data.images) ? data.images : [];
  if (images.length === 0) {
    compareAiThumbsEl.innerHTML = '<div class="result-compare-empty">暂无生成图</div>';
  } else {
    images.forEach((item, index) => {
      const wrap = document.createElement('div');
      wrap.className = 'result-compare-grid-thumb';
      wrap.innerHTML = `<img src="${escapeHtml(item.url)}" alt="${escapeHtml(item.label || `AI ${index + 1}`)}" loading="lazy" />`;
      compareAiThumbsEl.appendChild(wrap);
    });
  }

  compareStripEl.classList.remove('hidden');
}

function showError(message) {
  loadingEl.classList.add('hidden');
  pendingEl.classList.add('hidden');
  contentEl.classList.add('hidden');
  errorEl.textContent = message;
  errorEl.classList.remove('hidden');
}

function showPending(message) {
  loadingEl.classList.add('hidden');
  errorEl.classList.add('hidden');
  contentEl.classList.add('hidden');
  pendingMessageEl.textContent = message || '正在生成中...';
  pendingEl.classList.remove('hidden');
}

function applyKindChrome(data) {
  const kind = (data && data.kind) || 'hot_synthesis';
  const isDesign = kind === 'design';
  resultKindEl.textContent = resultKindLabel(data);
  pageTitleEl.textContent = isDesign ? '趋势改造结果' : '双爆款合成结果';
  pageSubEl.textContent = isDesign
    ? '多视图 + 产品设计报告 + 产品属性'
    : '8张生成图 · 分析报告';
  pageBackEl.href = isDesign ? '/design.html' : '/gap-fusion.html';
  navSynthesisEl?.classList.toggle('active', !isDesign);
  navDesignEl?.classList.toggle('active', isDesign);
  if (typeof window.mountBloomSidebar === 'function') {
    window.mountBloomSidebar(
      isDesign ? 'design' : 'hot',
      isDesign ? '趋势改造结果' : '双爆款合成结果'
    );
  }
  metaAzRowEl.classList.toggle('hidden', isDesign);
  metaSourceRowEl.classList.toggle('hidden', !isDesign);
  metaTitleLabelEl.textContent = isDesign ? '款名：' : '竞品爆款：';
}

function renderSucceeded(data) {
  const kind = data.kind || 'hot_synthesis';
  applyKindChrome(data);

  if (kind === 'design') {
    competitorTitleEl.textContent =
      (data.product_attributes && data.product_attributes.design_name_zh) ||
      data.competitor_product_title ||
      data.id;
    if (data.source_image_url) {
      resultSourceUrlEl.href = data.source_image_url;
    }
    if (data.product_attributes && Object.keys(data.product_attributes).length) {
      productAttributesEl.textContent = JSON.stringify(data.product_attributes, null, 2);
      attrsSectionEl.classList.remove('hidden');
    } else {
      attrsSectionEl.classList.add('hidden');
    }
  } else {
    azUrlEl.href = data.az_product_url || '#';
    azUrlEl.textContent = data.az_product_url || '—';
    competitorTitleEl.textContent = data.competitor_product_title || data.competitor_product_id;
    attrsSectionEl.classList.add('hidden');
  }

  reportSummaryEl.innerHTML = renderReportHtml(data.report_markdown || '');
  renderCompareStrip(data, kind);
  // 有对照条时，全景区默认隐藏，避免与「AI 缩略图」重复；无 panorama 也无妨
  if (data.panorama_image && data.panorama_image.url && kind !== 'hot_synthesis') {
    renderPanorama(data.panorama_image);
  } else {
    panoramaSectionEl.classList.add('hidden');
    panoramaWrapEl.innerHTML = '';
  }
  renderImages(data.images || []);
  if (kind === 'hot_synthesis') {
    imageGridEl.classList.add('result-image-grid--scroll');
  } else {
    imageGridEl.classList.remove('result-image-grid--scroll');
  }
  renderReportDocs(data.report_docs, kind);

  btnDownloadEl.disabled = false;
  btnDownloadEl.onclick = () => {
    window.location.href = `/api/synthesis/${encodeURIComponent(data.id)}/download`;
  };

  loadingEl.classList.add('hidden');
  pendingEl.classList.add('hidden');
  errorEl.classList.add('hidden');
  contentEl.classList.remove('hidden');

  currentTaskId = data.id;
  loadGeneratedAttributes(data.id);
  loadSimilarPeers(data.id, false);
}

function renderGeneratedAttributes(payload) {
  if (!generatedAttrsSectionEl) return;
  generatedAttrsSectionEl.classList.remove('hidden');
  generatedAttrsHintEl.textContent = payload.hint || '';
  generatedAttrsHintEl.classList.toggle('is-empty', payload.status === 'empty');
  generatedAttrsGridEl.innerHTML = '';

  const attrs = Array.isArray(payload.attributes) ? payload.attributes : [];
  if (attrs.length === 0) {
    generatedAttrsGridEl.innerHTML =
      '<div class="generated-attr-empty">报告中暂无可用结构化属性</div>';
    return;
  }

  attrs.forEach((attr) => {
    const card = document.createElement('div');
    card.className = 'generated-attr-card';
    card.innerHTML = `
      <div class="generated-attr-card__label">${escapeHtml(attr.label || attr.key)}</div>
      <div class="generated-attr-card__value">${escapeHtml(attr.value || '—')}</div>
    `;
    generatedAttrsGridEl.appendChild(card);
  });
}

async function loadGeneratedAttributes(taskId) {
  if (!generatedAttrsSectionEl || !taskId) return;
  generatedAttrsSectionEl.classList.remove('hidden');
  generatedAttrsHintEl.textContent = '正在从合成报告解析新款属性...';
  try {
    const res = await fetch(`/api/synthesis/${encodeURIComponent(taskId)}/generated-attributes`);
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      generatedAttrsHintEl.textContent = errBody.detail || `属性解析失败（HTTP ${res.status}）`;
      generatedAttrsHintEl.classList.add('is-empty');
      return;
    }
    renderGeneratedAttributes(await res.json());
  } catch (err) {
    console.error('生成款属性解析失败', err);
    generatedAttrsHintEl.textContent = '属性解析网络异常';
    generatedAttrsHintEl.classList.add('is-empty');
  }
}

function riskClass(risk) {
  if (risk === 'high') return 'peer-risk--high';
  if (risk === 'medium') return 'peer-risk--medium';
  if (risk === 'low') return 'peer-risk--low';
  return 'peer-risk--unknown';
}

function syncSimilarTaskBadge(payload) {
  if (!similarTaskBadgeEl) return;
  const marked = Array.isArray(payload.excluded_goods_ids)
    ? payload.excluded_goods_ids.length > 0
    : (payload.peers || []).some((p) => p.excluded);
  similarTaskBadgeEl.classList.toggle('hidden', !marked);
}

function renderSimilarPeers(payload) {
  if (!similarSectionEl) return;
  similarSectionEl.classList.remove('hidden');
  similarHintEl.textContent = payload.hint || '';
  similarHintEl.classList.toggle('is-degraded', payload.source === 'demo_fallback');
  syncSimilarTaskBadge(payload);

  similarGridEl.innerHTML = '';
  const peers = Array.isArray(payload.peers) ? payload.peers : [];
  if (peers.length === 0) {
    similarEmptyEl.classList.remove('hidden');
    return;
  }
  similarEmptyEl.classList.add('hidden');

  peers.forEach((peer) => {
    const card = document.createElement('article');
    card.className = `similar-peer-card${peer.excluded ? ' is-marked' : ''}`;
    card.dataset.goodsId = peer.goods_id || '';

    const attrsHtml = Object.entries(peer.attributes || {})
      .slice(0, 4)
      .map(([k, vals]) => {
        const label = ({ silhouette: '版型', neckline: '领型', fabric: '面料', dress_length: '裙长', color_family: '色彩', features: '特征' })[k] || k;
        return `<span class="peer-attr">${escapeHtml(label)} ${(vals || []).slice(0, 2).map(escapeHtml).join('/')}</span>`;
      })
      .join('');

    const matchedHtml = (peer.matched_attributes || [])
      .slice(0, 4)
      .map((m) => `<span class="peer-match">${escapeHtml(m)}</span>`)
      .join('');

    const priceText = peer.price == null || peer.price === '' ? '' : `$${peer.price}`;
    const markLabel = peer.excluded ? '取消标记' : '标记相似款';

    card.innerHTML = `
      <a class="similar-peer-card__media" href="${escapeHtml(peer.url || '#')}" target="_blank" rel="noopener noreferrer">
        <img src="${escapeHtml(peer.image_url || '')}" alt="${escapeHtml(peer.name || '相似款')}" loading="lazy" onerror="this.style.opacity=0.25" />
      </a>
      <div class="similar-peer-card__body">
        <div class="similar-peer-card__top">
          <span class="peer-risk ${riskClass(peer.overlap_risk)}">${escapeHtml(peer.overlap_label || peer.overlap_risk || '未知')}</span>
          ${priceText ? `<span class="peer-price">${escapeHtml(priceText)}</span>` : ''}
        </div>
        <a class="similar-peer-card__title" href="${escapeHtml(peer.url || '#')}" target="_blank" rel="noopener noreferrer">${escapeHtml(peer.name || peer.goods_id || '未命名')}</a>
        <div class="peer-attrs">${attrsHtml || '<span class="peer-attr">属性待补</span>'}</div>
        <div class="peer-matches">${matchedHtml}</div>
        <div class="similar-peer-card__foot">
          <button type="button" class="btn-mark-similar${peer.excluded ? ' is-on' : ''}" data-marked="${peer.excluded ? '1' : '0'}">${markLabel}</button>
          <span class="peer-gid">ID ${escapeHtml(peer.goods_id || '—')}</span>
        </div>
      </div>
    `;

    const btn = card.querySelector('.btn-mark-similar');
    btn?.addEventListener('click', async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const nextMarked = btn.dataset.marked !== '1';
      btn.disabled = true;
      try {
        const res = await fetch(`/api/synthesis/${encodeURIComponent(currentTaskId)}/similar-peers/mark`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ goods_id: peer.goods_id, excluded: nextMarked }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        await loadSimilarPeers(currentTaskId, false);
      } catch (err) {
        console.error('标记相似款失败', err);
        btn.disabled = false;
      }
    });

    similarGridEl.appendChild(card);
  });
}

async function loadSimilarPeers(taskId, refresh) {
  if (!similarSectionEl || !taskId) return;
  similarSectionEl.classList.remove('hidden');
  similarLoadingEl.classList.remove('hidden');
  similarEmptyEl.classList.add('hidden');
  if (btnSimilarRefreshEl) btnSimilarRefreshEl.disabled = true;

  try {
    const qs = refresh ? '?refresh=true' : '';
    const res = await fetch(`/api/synthesis/${encodeURIComponent(taskId)}/similar-peers${qs}`);
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      similarHintEl.textContent = errBody.detail || `相似款召回失败（HTTP ${res.status}）`;
      similarGridEl.innerHTML = '';
      similarEmptyEl.classList.remove('hidden');
      return;
    }
    const payload = await res.json();
    renderSimilarPeers(payload);
    similarPeersLoaded = true;
  } catch (err) {
    console.error('相似款召回失败', err);
    similarHintEl.textContent = '相似款召回网络异常，可稍后点「重新召回」';
    similarEmptyEl.classList.remove('hidden');
  } finally {
    similarLoadingEl.classList.add('hidden');
    if (btnSimilarRefreshEl) btnSimilarRefreshEl.disabled = false;
  }
}

if (btnSimilarRefreshEl) {
  btnSimilarRefreshEl.addEventListener('click', () => {
    if (currentTaskId) loadSimilarPeers(currentTaskId, true);
  });
}

async function pollResult(id) {
  if (Date.now() - pollStartedAt > POLL_TIMEOUT_MS) {
    showError('生成时间过长，请稍后在历史生成中查看，或返回重新发起');
    return;
  }

  let res;
  try {
    res = await fetch(`/api/synthesis/${encodeURIComponent(id)}`);
  } catch (err) {
    console.error('查询结果失败：', err);
    setTimeout(() => pollResult(id), POLL_INTERVAL_MS);
    return;
  }

  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    showError(errBody.detail || `加载失败（HTTP ${res.status}）`);
    return;
  }

  const data = await res.json();
  switch (data.status) {
    case 'succeeded':
      renderSucceeded(data);
      return;
    case 'failed':
      showError(data.error_message ? `生成失败：${data.error_message}` : '生成失败，请返回重新发起');
      return;
    case 'pending':
    case 'running':
    default:
      showPending(data.progress_message);
      setTimeout(() => pollResult(id), POLL_INTERVAL_MS);
  }
}

function loadResult() {
  const id = getResultId();
  if (!id) {
    showError('缺少结果 ID，请从爆款合成或设计款页重新发起');
    return;
  }
  pollStartedAt = Date.now();
  pollResult(id);
}

loadResult();
