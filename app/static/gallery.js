/* 品类效果页：读 /api/gallery 预渲染 manifest */
(function () {
  const tabsEl = document.getElementById('gallery-tabs');
  const gridEl = document.getElementById('gallery-grid');
  const emptyEl = document.getElementById('gallery-empty');
  const updatedEl = document.getElementById('gallery-updated');
  const disclaimerEl = document.getElementById('gallery-disclaimer');

  let categories = [];
  let activeId = '';

  function esc(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function renderTabs() {
    tabsEl.innerHTML = categories
      .map(function (c) {
        const count = (c.items || []).length;
        const active = c.id === activeId ? ' is-active' : '';
        return (
          '<button type="button" class="gallery-tab' +
          active +
          '" data-id="' +
          esc(c.id) +
          '">' +
          esc(c.label || c.id) +
          '<span class="gallery-tab__count">' +
          count +
          '</span></button>'
        );
      })
      .join('');
    tabsEl.querySelectorAll('.gallery-tab').forEach(function (btn) {
      btn.addEventListener('click', function () {
        activeId = btn.getAttribute('data-id');
        renderTabs();
        renderGrid();
      });
    });
  }

  function imgCell(url, label) {
    if (!url) {
      return '<div class="gallery-shot gallery-shot--empty">' + esc(label) + '</div>';
    }
    return (
      '<figure class="gallery-shot">' +
      '<img src="' +
      esc(url) +
      '" alt="' +
      esc(label) +
      '" loading="lazy" />' +
      '<figcaption>' +
      esc(label) +
      '</figcaption></figure>'
    );
  }

  function renderGrid() {
    const cat = categories.find(function (c) {
      return c.id === activeId;
    });
    const items = (cat && cat.items) || [];
    if (!items.length) {
      gridEl.innerHTML = '';
      emptyEl.classList.remove('hidden');
      return;
    }
    emptyEl.classList.add('hidden');
    gridEl.innerHTML = items
      .map(function (item) {
        const status = item.status || 'ready';
        const badge =
          status === 'ready'
            ? '<span class="chip">已生成</span>'
            : '<span class="chip chip--warn">失败/异常 · 仍展示</span>';
        const azIn = (item.az_input_images || [])[0] || '';
        const compIn =
          item.competitor_product_image_url ||
          (item.competitor_detail_images || [])[0] ||
          '';
        const results = item.result_images || [];
        const resultHtml = results.length
          ? results
              .slice(0, 4)
              .map(function (u, i) {
                return imgCell(u, '结果 ' + (i + 1));
              })
              .join('')
          : imgCell('', '无结果图');
        return (
          '<article class="gallery-card">' +
          '<div class="gallery-card__head">' +
          '<div><div class="gallery-card__title">' +
          esc(item.competitor_product_title || item.id) +
          '</div><div class="panel__hint">id=' +
          esc(item.id) +
          (item.synthesis_task_id ? ' · task=' + esc(item.synthesis_task_id) : '') +
          '</div></div>' +
          badge +
          '</div>' +
          (item.error_message
            ? '<p class="gallery-card__err">' + esc(item.error_message) + '</p>'
            : '') +
          '<div class="gallery-card__row">' +
          imgCell(compIn, '竞品输入') +
          imgCell(azIn, 'AZ 输入') +
          resultHtml +
          '</div></article>'
        );
      })
      .join('');
  }

  async function load() {
    const res = await fetch('/api/gallery');
    if (!res.ok) throw new Error('gallery api ' + res.status);
    const data = await res.json();
    categories = data.categories || [];
    activeId = categories[0] ? categories[0].id : '';
    disclaimerEl.textContent =
      data.disclaimer ||
      '预渲染结果如实展示（含好坏），供老板判断该裙装品类是否值得接入。';
    updatedEl.textContent = data.updated_at
      ? '更新于 ' + data.updated_at
      : '尚未预跑';
    renderTabs();
    renderGrid();
  }

  load().catch(function (err) {
    emptyEl.classList.remove('hidden');
    emptyEl.textContent = '加载失败：' + err.message;
  });
})();
