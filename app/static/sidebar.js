/* Shared sidebar for Bloom. Two studios first. */
(function () {
  const ICONS = {
    dash: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6',
    monitor:
      'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z',
    synth:
      'M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z',
    design:
      'M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z',
    library:
      'M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10',
    history:
      'M12 8v4l2.5 2.5M21 12a9 9 0 11-9-9 9 9 0 019 9z',
  };

  const LAST_WB_KEY = 'bloom_last_workbench';

  const NAV = [
    { id: 'studio', href: '/', label: '作品', icon: 'dash' },
    { id: 'hot', href: '/gap-fusion.html', label: '双爆款合成', icon: 'synth' },
    { id: 'design', href: '/design.html', label: '趋势改造', icon: 'design' },
    { id: 'library', href: '/library.html', label: '成品库', icon: 'library' },
  ];

  function itemHtml(item, active, extraClass) {
    const cls =
      (item.id === active ? 'nav-item active' : 'nav-item') +
      (extraClass ? ' ' + extraClass : '');
    return (
      '<a href="' +
      item.href +
      '" class="' +
      cls +
      '" data-view="' +
      item.id +
      '">' +
      '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">' +
      '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="' +
      ICONS[item.icon] +
      '" />' +
      '</svg>' +
      item.label +
      '</a>'
    );
  }

  window.bloomRememberWorkbench = function (id) {
    try {
      localStorage.setItem(LAST_WB_KEY, id === 'design' ? 'design' : 'hot');
    } catch (err) {
      /* ignore */
    }
  };

  window.bloomLastWorkbenchHref = function () {
    try {
      return localStorage.getItem(LAST_WB_KEY) === 'design' ? '/design.html' : '/gap-fusion.html';
    } catch (err) {
      return '/gap-fusion.html';
    }
  };

  window.mountBloomSidebar = function (active, footText) {
    const host = document.getElementById('bloom-sidebar');
    if (!host) return;
    if (active === 'hot' || active === 'design') {
      window.bloomRememberWorkbench(active);
    }
    if (active === 'history') active = 'library';
    const foot = footText || 'Bloom · 视觉与创意';
    const parts = ['<div class="sidebar__group">工作室</div>'];
    NAV.forEach(function (item) {
      const childIds = (item.children || []).map(function (c) {
        return c.id;
      });
      const parentActive = item.id === active || childIds.indexOf(active) !== -1;
      parts.push(itemHtml(item, parentActive ? item.id : active, item.children ? 'nav-item--parent' : ''));
      if (item.children) {
        item.children.forEach(function (child) {
          parts.push(itemHtml(child, active, 'nav-item--child'));
        });
      }
    });
    host.innerHTML =
      '<div class="sidebar__brand">' +
      '<div class="sidebar__eyebrow">Fashion AI</div>' +
      '<div class="sidebar__title">Bloom</div>' +
      '</div>' +
      '<nav class="sidebar__nav">' +
      parts.join('') +
      '</nav>' +
      '<div class="sidebar__foot">' +
      foot +
      '</div>';
  };
})();
