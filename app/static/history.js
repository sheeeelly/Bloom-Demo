/* ─── AZ Bloom — history.js ───────────────────────────── */
/* 历史生成：爆款合成 + 设计款，带类型标签。 */

const loadingEl = document.getElementById('loading-state');
const errorEl = document.getElementById('error-state');
const emptyEl = document.getElementById('empty-state');
const listEl = document.getElementById('history-list');
const btnRefreshEl = document.getElementById('btn-refresh');

const STATUS_LABELS = {
  pending: '排队中',
  running: '生成中',
  succeeded: '已完成',
  failed: '失败',
};

function kindLabel(item) {
  const kind = item.kind || 'hot_synthesis';
  if (kind === 'design') return '趋势改造';
  return '双爆款合成';
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatTime(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function truncateUrl(url, maxLen = 46) {
  if (!url) return '—';
  return url.length > maxLen ? `${url.slice(0, maxLen)}…` : url;
}

function showState(state) {
  loadingEl.classList.toggle('hidden', state !== 'loading');
  errorEl.classList.toggle('hidden', state !== 'error');
  emptyEl.classList.toggle('hidden', state !== 'empty');
  listEl.classList.toggle('hidden', state !== 'list');
}

function renderList(items) {
  listEl.innerHTML = '';
  items.forEach((item) => {
    const status = item.status || 'pending';
    const kind = item.kind || 'hot_synthesis';
    const isDesign = kind === 'design';
    const title = item.title || item.competitor_product_title || item.id;
    const thumb = item.thumbnail_url || item.source_image_url || item.competitor_product_image_url || '';
    const meta = isDesign
      ? `参考图开款 · 图片 ${item.image_count || 0} 张`
      : `AZ：${truncateUrl(item.az_product_url)} · ${item.competitor_source_site || '—'} · 图片 ${item.image_count || 0} 张`;

    const similarMarked =
      item.marked_as_similar_style ||
      item.eligible_for_planning_pool === false ||
      (Array.isArray(item.marked_similar_goods_ids) && item.marked_similar_goods_ids.length > 0);
    const similarBadge = similarMarked
      ? `<span class="similar-style-badge" title="已标记相似款，不进入选品企划池">相似款</span>`
      : '';

    const row = document.createElement('a');
    row.href = `/result.html?id=${encodeURIComponent(item.id)}`;
    row.className = `history-row${similarMarked ? ' history-row--similar' : ''}`;
    row.innerHTML = `
      <img class="history-row__thumb" src="${escapeHtml(thumb)}" alt="" loading="lazy" />
      <div class="history-row__body">
        <div class="history-row__title-row">
          <span class="kind-badge kind-badge--${escapeHtml(kind)}">${escapeHtml(kindLabel(item))}</span>
          ${similarBadge}
          <div class="history-row__title">${escapeHtml(title)}</div>
        </div>
        <div class="history-row__meta">${escapeHtml(meta)}${similarMarked ? ' · 不进企划池' : ''}</div>
      </div>
      <div class="history-row__side">
        <span class="status-badge status-badge--${escapeHtml(status)}">${escapeHtml(STATUS_LABELS[status] || status)}</span>
        <span class="history-row__time">${escapeHtml(formatTime(item.created_at))}</span>
      </div>
    `;
    listEl.appendChild(row);
  });
}

async function loadHistory() {
  showState('loading');
  let res;
  try {
    res = await fetch('/api/synthesis');
  } catch (err) {
    console.error('加载历史记录失败：', err);
    errorEl.textContent = '加载历史记录失败，请检查网络后重试';
    showState('error');
    return;
  }

  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    errorEl.textContent = errBody.detail || `加载失败（HTTP ${res.status}）`;
    showState('error');
    return;
  }

  const data = await res.json();
  const items = Array.isArray(data.items) ? data.items : [];
  if (items.length === 0) {
    showState('empty');
    return;
  }
  renderList(items);
  showState('list');
}

btnRefreshEl.addEventListener('click', loadHistory);
loadHistory();
