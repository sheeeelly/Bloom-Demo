const treeEl = document.getElementById('insp-tree');
const gridEl = document.getElementById('lib-grid');
const headingEl = document.getElementById('lib-heading');
const statsEl = document.getElementById('lib-stats');
const tabsEl = document.getElementById('lib-tabs');

let currentSet = 'local:all';
let treeData = null;

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function shortId(id) {
  return String(id || '').slice(0, 8);
}

const STATUS_LABELS = {
  pending: '排队中',
  running: '生成中',
  succeeded: '已完成',
  failed: '失败',
  new: '上新',
  go: '可跟',
  cautious: '谨慎',
};

function renderTree() {
  if (!treeData) return;
  const groups = treeData.groups || [];
  treeEl.innerHTML = groups
    .map((g) => {
      const kids = (g.children || [])
        .map(
          (c) => `<button type="button" class="insp-node${c.id === currentSet ? ' is-on' : ''}" data-set="${esc(c.id)}">
            <span>${esc(c.label)}</span><em>${esc(c.count ?? '')}</em>
          </button>`
        )
        .join('');
      return `<div class="insp-group"><div class="insp-group__label">${esc(g.label)}</div>${kids}</div>`;
    })
    .join('');
  const counts = treeData.counts || {};
  statsEl.innerHTML = [
    ['当前成品', counts.all || 0],
    ['生成中', counts.generating || 0],
    ['已完成', counts.succeeded || 0],
    ['失败', counts.failed || 0],
  ]
    .map(([k, v]) => `<div class="stat-card"><div class="stat-card__value">${esc(v)}</div><div class="stat-card__label">${esc(k)}</div></div>`)
    .join('');
}

function cardHtml(item) {
  const kind = item.card_kind || 'task';
  const img = item.image_url
    ? `<img src="${esc(item.image_url)}" alt="" loading="lazy" />`
    : `<div class="lib-card__ph">${kind === 'fashion' ? '趋势' : '无图'}</div>`;
  const status = item.status || '';
  const href = item.href || '#';
  const cta = item.cta || (kind === 'task' ? '查看结果' : '打开');
  const fail = status === 'failed' ? ' is-failed' : '';
  return `<a class="lib-card${fail}" href="${esc(href)}">
    <div class="lib-card__media">${img}
      <span class="sku-badge">${esc(STATUS_LABELS[status] || status || kind)}</span>
    </div>
    <h3>${esc(item.title || item.id)}</h3>
    <p>${esc(item.subtitle || item.site || item.kind || '')}${item.created_at ? ' · ' + esc(String(item.created_at).slice(0, 16).replace('T', ' ')) : ''}</p>
    ${item.error_message ? `<p class="lib-card__err">${esc(item.error_message)}</p>` : ''}
    <span class="lib-card__cta">${esc(cta)} · ${esc(shortId(item.id))}</span>
  </a>`;
}

async function loadItems(setId) {
  currentSet = setId || 'local:all';
  const res = await fetch('/api/library/items?set=' + encodeURIComponent(currentSet));
  const data = await res.json();
  headingEl.textContent = data.title || currentSet;
  const items = data.items || [];
  gridEl.innerHTML = items.map(cardHtml).join('') || '<p class="empty-state">此灵感集暂无内容</p>';
  renderTree();
  const isLocal = currentSet.startsWith('local');
  tabsEl.classList.toggle('is-disabled', !isLocal);
}

async function loadTree() {
  const res = await fetch('/api/library/tree');
  treeData = await res.json();
  renderTree();
}

treeEl.addEventListener('click', (ev) => {
  const btn = ev.target.closest('[data-set]');
  if (!btn) return;
  loadItems(btn.getAttribute('data-set')).catch(console.error);
});

tabsEl.addEventListener('click', (ev) => {
  const btn = ev.target.closest('[data-tab]');
  if (!btn || !currentSet.startsWith('local')) return;
  tabsEl.querySelectorAll('button').forEach((b) => b.classList.toggle('is-on', b === btn));
  const tab = btn.getAttribute('data-tab');
  const map = { all: 'local:all', generating: 'local:generating', succeeded: 'local:succeeded', failed: 'local:failed' };
  loadItems(map[tab] || 'local:all').catch(console.error);
});

document.getElementById('btn-refresh').addEventListener('click', async () => {
  await loadTree();
  await loadItems(currentSet);
});

const params = new URLSearchParams(location.search);
if (params.get('id')) {
  currentSet = 'local:all';
}
loadTree()
  .then(() => loadItems(params.get('set') || currentSet))
  .catch((err) => {
    gridEl.innerHTML = `<p class="empty-state">${esc(err.message || '成品库加载失败')}</p>`;
  });
