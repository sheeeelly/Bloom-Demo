/* 开类目薄壳 */
(function () {
  const nameEl = document.getElementById('nc-name');
  const urlEl = document.getElementById('nc-url');
  const anchorEl = document.getElementById('nc-anchor');
  const notesEl = document.getElementById('nc-notes');
  const statusEl = document.getElementById('nc-status');
  const listEl = document.getElementById('nc-list');
  const btn = document.getElementById('btn-nc-submit');

  function esc(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  async function refresh() {
    const res = await fetch('/api/new-category');
    const data = await res.json();
    const rows = data.submissions || [];
    if (!rows.length) {
      listEl.innerHTML = '<p class="panel__hint">暂无记录</p>';
      return;
    }
    listEl.innerHTML = rows
      .map(function (r) {
        return (
          '<div class="nc-row">' +
          '<div class="nc-row__title">' +
          esc(r.category_name) +
          '</div>' +
          '<a class="result-meta__link" href="' +
          esc(r.competitor_site_url) +
          '" target="_blank" rel="noopener">' +
          esc(r.competitor_site_url) +
          '</a>' +
          '<div class="panel__hint">' +
          esc(r.most_popular_hint) +
          ' · ' +
          esc(r.created_at) +
          '</div>' +
          (r.notes ? '<div class="panel__hint">' + esc(r.notes) + '</div>' : '') +
          '</div>'
        );
      })
      .join('');
  }

  btn.addEventListener('click', async function () {
    statusEl.textContent = '提交中…';
    try {
      const res = await fetch('/api/new-category', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          category_name: nameEl.value,
          competitor_site_url: urlEl.value,
          most_popular_hint: anchorEl.value,
          notes: notesEl.value,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      statusEl.textContent = data.submission.message || '已记录';
      nameEl.value = '';
      urlEl.value = '';
      notesEl.value = '';
      await refresh();
    } catch (err) {
      statusEl.textContent = '失败：' + err.message;
    }
  });

  refresh();
})();
