/* 方案三 · 季节灵感企划 → POST /api/design（无杂志爬图；文本主导） */

const btnStartEl = document.getElementById('btn-design-start');
const errorEl = document.getElementById('design-error');
const toastEl = document.getElementById('toast');
const clusterEl = document.getElementById('cluster-chips');
const metaEl = document.getElementById('nybfw-meta');
const categorySeg = document.getElementById('category-seg');
const pantoneSeg = document.getElementById('pantone-seg');
const promptDesignEl = document.getElementById('prompt-design');
const promptAnalysisEl = document.getElementById('prompt-analysis');
const inspUrlEl = document.getElementById('insp-url');
const inspFileEl = document.getElementById('insp-file');
const inspPreviewEl = document.getElementById('insp-preview');
const inspHintEl = document.getElementById('insp-source-hint');
const btnInspUrlEl = document.getElementById('btn-insp-url');
const btnSourcesEl = document.getElementById('btn-sources');
const sourcesPopEl = document.getElementById('sources-popover');
const sourcesListEl = document.getElementById('sources-list');

let packFile = 'spring_2026_rtw.manual.json';
let pack = null;
/** @type {{kind:'url'|'file', url?:string, file?:File, preview:string}[]} */
let inspirationItems = [];
/** @type {Record<string, string>} */
let defaultPackByCategory = {
  AT: 'spring_2026_rtw.manual.json',
  BD: 'spring_2026_rtw.manual.json',
  MOB: 'spring_2026_rtw.manual.json',
  Prom: 'spring_2026_rtw.manual.json',
  Wedding: 'wedding_spring_2026.manual.json',
};
/** @type {Set<string>} */
let selectedClusters = new Set();
let category = 'AT';
let pantoneEnabled = false;
let toastTimer = null;
let previewTimer = null;

function showToast(message, durationMs = 2600, asHtml = false) {
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

function canStart() {
  return selectedClusters.size > 0 && !!(promptDesignEl.value || '').trim();
}

function refreshStart() {
  btnStartEl.disabled = !canStart();
}

function renderCategories(categories) {
  categorySeg.innerHTML = categories
    .map(
      (c) =>
        `<button type="button" class="seg__btn${c === category ? ' is-active' : ''}" data-cat="${c}">${c === 'Wedding' ? 'Wedding · 婚纱' : c}</button>`
    )
    .join('');
  categorySeg.querySelectorAll('.seg__btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      category = btn.getAttribute('data-cat') || 'AT';
      categorySeg.querySelectorAll('.seg__btn').forEach((b) => b.classList.remove('is-active'));
      btn.classList.add('is-active');
      await loadPackForCategory(category, true);
    });
  });
}

function escapeHtml(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function clusterChipLabel(cluster) {
  const zh = String(cluster.label_zh || '').trim();
  const en = String(cluster.label || cluster.label_en || cluster.cluster_id || '').trim();
  if (zh && en && zh.toLowerCase() !== en.toLowerCase()) {
    return (
      `<span class="intervention-chip__zh">${escapeHtml(zh)}</span>` +
      `<span class="intervention-chip__en">${escapeHtml(en)}</span>`
    );
  }
  return `<span class="intervention-chip__zh">${escapeHtml(zh || en)}</span>`;
}

function closeSourcesPop() {
  if (!sourcesPopEl || !btnSourcesEl) return;
  sourcesPopEl.classList.add('hidden');
  btnSourcesEl.setAttribute('aria-expanded', 'false');
}

function renderSources() {
  if (!sourcesListEl || !btnSourcesEl) return;
  const sources = (pack && pack.sources) || [];
  if (!sources.length) {
    sourcesListEl.innerHTML = '<li class="design-sources__empty">当前灵感包未配置来源网站</li>';
    btnSourcesEl.disabled = true;
    closeSourcesPop();
    return;
  }
  btnSourcesEl.disabled = false;
  sourcesListEl.innerHTML = sources
    .map((s) => {
      const name = s.name || s.title || '来源';
      const url = s.url || '';
      const note = s.note || s.title || '';
      const link = url
        ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(name)}</a>`
        : `<span>${escapeHtml(name)}</span>`;
      const meta = note ? `<span class="design-sources__meta">${escapeHtml(note)}</span>` : '';
      return `<li>${link}${meta}</li>`;
    })
    .join('');
}

function updateMeta() {
  if (!pack || !metaEl) return;
  const kind = pack.pack_kind === 'wedding' ? '婚纱独立包' : '成衣/裙装包';
  const season = pack.season_label || pack.season_id || 'Season';
  const n = (pack.trend_clusters || []).length;
  metaEl.innerHTML =
    `<span class="design-meta-pill design-meta-pill--accent">${escapeHtml(season)}</span>` +
    `<span class="design-meta-pill">${escapeHtml(kind)}</span>` +
    `<span class="design-meta-pill">Vogue 人工 · 无爬图</span>` +
    `<span class="design-meta-pill">${n} clusters</span>`;
  renderSources();
}

async function loadPackForCategory(cat, notify = false) {
  packFile = defaultPackByCategory[cat] || defaultPackByCategory.AT;
  selectedClusters = new Set();

  const packRes = await fetch('/api/design/packs/' + encodeURIComponent(packFile));
  if (!packRes.ok) throw new Error('加载灵感包失败');
  const packData = await packRes.json();
  pack = packData.pack;
  updateMeta();
  const clusters = pack.trend_clusters || [];
  clusters.slice(0, Math.min(3, clusters.length)).forEach((c) => selectedClusters.add(c.cluster_id));
  renderClusters();
  refreshStart();
  await refreshPromptPreview();
  if (notify) {
    showToast(cat === 'Wedding' ? '已切换到婚纱独立灵感包' : '已切换到成衣 SS26 灵感包');
  }
}

function renderClusters() {
  if (!pack) return;
  const clusters = pack.trend_clusters || [];
  clusterEl.innerHTML = clusters
    .map((c) => {
      const checked = selectedClusters.has(c.cluster_id);
      return (
        `<label class="intervention-chip">` +
        `<input type="checkbox" value="${escapeHtml(c.cluster_id)}" ${checked ? 'checked' : ''}/>` +
        `<span>${clusterChipLabel(c)}</span>` +
        `</label>`
      );
    })
    .join('');
  clusterEl.querySelectorAll('input').forEach((input) => {
    input.addEventListener('change', () => {
      if (input.checked) selectedClusters.add(input.value);
      else selectedClusters.delete(input.value);
      refreshStart();
      schedulePreview();
    });
  });
}

btnSourcesEl?.addEventListener('click', (ev) => {
  ev.stopPropagation();
  if (!sourcesPopEl || btnSourcesEl.disabled) return;
  const open = sourcesPopEl.classList.contains('hidden');
  if (open) {
    sourcesPopEl.classList.remove('hidden');
    btnSourcesEl.setAttribute('aria-expanded', 'true');
  } else {
    closeSourcesPop();
  }
});

document.addEventListener('click', (ev) => {
  if (!sourcesPopEl || sourcesPopEl.classList.contains('hidden')) return;
  const root = document.getElementById('design-sources');
  if (root && !root.contains(ev.target)) closeSourcesPop();
});

document.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape') closeSourcesPop();
});

async function schedulePreview() {
  if (previewTimer) clearTimeout(previewTimer);
  previewTimer = setTimeout(() => refreshPromptPreview(), 280);
}

async function refreshPromptPreview() {
  try {
    const res = await fetch('/api/design/preview-prompt', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pack_file: packFile,
        category,
        cluster_ids: Array.from(selectedClusters),
        pantone_enabled: pantoneEnabled,
      }),
    });
    if (!res.ok) throw new Error('preview failed');
    const data = await res.json();
    promptDesignEl.value = data.design_prompt_append || '';
    promptAnalysisEl.value = data.analysis_prompt_append || '';
    refreshStart();
  } catch (err) {
    promptDesignEl.value = '预览失败：' + (err.message || err);
  }
}

pantoneSeg.querySelectorAll('.seg__btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    pantoneEnabled = btn.getAttribute('data-pantone') === '1';
    pantoneSeg.querySelectorAll('.seg__btn').forEach((b) => b.classList.remove('is-active'));
    btn.classList.add('is-active');
    if (pantoneEnabled) showToast('潘通叠加为二期能力；Prompt 仍会标注色向可选');
    schedulePreview();
  });
});

promptDesignEl.addEventListener('input', () => {
  refreshStart();
});

function renderInspirationPreview() {
  if (!inspPreviewEl) return;
  if (!inspirationItems.length) {
    inspPreviewEl.innerHTML = '<p class="insp-preview__empty">尚未添加灵感图</p>';
    if (inspHintEl) {
      inspHintEl.textContent = '未选择灵感图时，开款将使用技术占位图（文本 Prompt 主导）。';
    }
    return;
  }
  inspPreviewEl.innerHTML = inspirationItems
    .map(
      (item, idx) =>
        `<div class="insp-preview__item">` +
        `<img src="${item.preview}" alt="灵感图 ${idx + 1}" />` +
        `<button type="button" data-idx="${idx}">移除</button>` +
        `</div>`
    )
    .join('');
  inspPreviewEl.querySelectorAll('button').forEach((btn) => {
    btn.addEventListener('click', () => {
      const idx = Number(btn.getAttribute('data-idx'));
      const removed = inspirationItems[idx];
      if (removed && removed.kind === 'url' && removed.preview.startsWith('blob:')) {
        URL.revokeObjectURL(removed.preview);
      }
      if (removed && removed.kind === 'file' && removed.preview.startsWith('blob:')) {
        URL.revokeObjectURL(removed.preview);
      }
      inspirationItems.splice(idx, 1);
      renderInspirationPreview();
    });
  });
  if (inspHintEl) {
    inspHintEl.textContent = `已添加 ${inspirationItems.length} 张灵感图，开款时使用第一张作为参考图。`;
  }
}

btnInspUrlEl?.addEventListener('click', () => {
  const url = (inspUrlEl?.value || '').trim();
  if (!url) {
    showToast('请先粘贴图片链接');
    return;
  }
  inspirationItems = [{ kind: 'url', url, preview: url }];
  renderInspirationPreview();
  showToast('已添加链接灵感图');
});

inspFileEl?.addEventListener('change', () => {
  const file = inspFileEl.files && inspFileEl.files[0];
  if (!file) return;
  const preview = URL.createObjectURL(file);
  inspirationItems = [{ kind: 'file', file, preview }];
  renderInspirationPreview();
  showToast('已上传灵感图');
});

async function bootstrap() {
  const params = new URLSearchParams(location.search);
  const listRes = await fetch('/api/design/packs');
  const listData = await listRes.json();
  if (listData.default_pack_by_category) {
    defaultPackByCategory = listData.default_pack_by_category;
  }
  renderCategories(listData.categories || ['AT', 'Wedding', 'BD', 'MOB', 'Prom']);
  if (params.get('pack')) {
    packFile = params.get('pack');
  }
  await loadPackForCategory(category, false);
  if (params.get('pack')) {
    packFile = params.get('pack');
    const packRes = await fetch('/api/design/packs/' + encodeURIComponent(packFile));
    if (packRes.ok) {
      const packData = await packRes.json();
      pack = packData.pack;
      updateMeta();
      const want = params.get('cluster');
      if (want) selectedClusters = new Set([want]);
      renderClusters();
      await refreshPromptPreview();
    }
  }
  renderInspirationPreview();
}

async function handleStart() {
  hideError();
  if (!canStart()) {
    showError('请至少勾选 1 个趋势芯片，并确认下方提示词非空');
    return;
  }
  btnStartEl.disabled = true;
  btnStartEl.textContent = '生成中...';
  try {
    const form = new FormData();
    form.append('pack_file', packFile);
    form.append('category', category);
    form.append('cluster_ids', Array.from(selectedClusters).join(','));
    form.append('pantone_enabled', pantoneEnabled ? 'true' : 'false');
    form.append('design_prompt_override', promptDesignEl.value.trim());
    form.append('analysis_prompt_override', promptAnalysisEl.value.trim());
    const first = inspirationItems[0];
    if (first?.kind === 'file' && first.file) {
      form.append('file', first.file, first.file.name || 'inspiration.jpg');
    } else if (first?.kind === 'url' && first.url) {
      form.append('inspiration_url', first.url);
    }
    const res = await fetch('/api/design', { method: 'POST', body: form });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.detail || `设计失败（HTTP ${res.status}）`);
    }
    const data = await res.json();
    const shortId = String(data.id || '').slice(0, 8);
    showToast(
      `新款已进入成品库 · <a href="/library.html?id=${encodeURIComponent(data.id)}">${shortId}</a> · 趋势改造`,
      8000,
      true
    );
    btnStartEl.textContent = '生成新款';
    refreshStart();
  } catch (err) {
    console.error(err);
    showError(err.message || '设计失败');
    showToast(err.message || '设计失败');
    btnStartEl.textContent = '生成新款';
    refreshStart();
  }
}

btnStartEl.addEventListener('click', handleStart);
bootstrap().catch((err) => {
  showError('加载灵感包失败：' + (err.message || err));
});
