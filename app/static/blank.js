/* 空白开款薄壳：品类 + 特征 checklist */
(function () {
  const FEATURES = {
    BD: [
      '可搭配多场景婚礼（白天/晚宴）',
      '版型以 A-Line / 修身友好为主',
      '裙长以 Floor / Maxi 为主',
      '面料垂感清晰（雪纺/绉纱等）',
      '领型可量产（避免过高定制）',
      '配色可系列化（多色 SKU）',
    ],
    AT: [
      '正式场合廓形清晰',
      '面料质感偏高级（缎/绉/蕾丝）',
      '腰线与裙摆层次可解释',
      '领型/袖型有设计记忆点',
      '适合 Atelier 价带表达',
      '避免与现有 Top 爆款过度同质',
    ],
    Prom: [
      '舞台感 / 拍照友好',
      '开叉或层叠等年轻化元素可选',
      '高饱和或金属光泽可接受',
      '鱼尾 / Fit&Flare 常见',
      '细节（绑带、亮片）可量产',
      '避免礼服婚纱化过重',
    ],
    MOB: [
      '年龄友好剪裁（遮盖/修饰）',
      '可配外套 / 袖型选项',
      '茶长或及地皆可',
      '颜色偏优雅中性或雾感',
      '面料不易透、易打理',
      '领型保守但有气质',
    ],
    Wedding: [
      '新娘主视觉：白/象牙/柔彩',
      '裙摆体积与头纱兼容',
      '胸衣结构可解释',
      '面料以缎/薄纱/蕾丝为主',
      '拖尾或层叠逻辑清晰',
      '细节精致但可供应链复刻',
    ],
  };

  const catEl = document.getElementById('blank-category');
  const listEl = document.getElementById('blank-checklist');
  const statusEl = document.getElementById('blank-status');
  const fileEl = document.getElementById('blank-fabric');
  const fileNameEl = document.getElementById('blank-fabric-name');
  const btnValidate = document.getElementById('btn-blank-validate');

  Object.keys(FEATURES).forEach(function (id) {
    const opt = document.createElement('option');
    opt.value = id;
    opt.textContent = id;
    catEl.appendChild(opt);
  });

  function renderChecklist() {
    const feats = FEATURES[catEl.value] || [];
    listEl.innerHTML = feats
      .map(function (f, i) {
        return (
          '<label class="blank-check">' +
          '<input type="checkbox" data-i="' +
          i +
          '" />' +
          '<span>' +
          f +
          '</span></label>'
        );
      })
      .join('');
  }

  catEl.addEventListener('change', renderChecklist);
  fileEl.addEventListener('change', function () {
    fileNameEl.textContent = fileEl.files[0] ? fileEl.files[0].name : '未选择文件';
  });

  btnValidate.addEventListener('click', function () {
    const checked = listEl.querySelectorAll('input[type=checkbox]:checked').length;
    const need = 3;
    if (checked < need) {
      statusEl.textContent =
        '特征闸未过：请至少勾选 ' + need + ' 条「' + catEl.value + '」重点特征后再走开款。';
      statusEl.classList.add('is-warn');
      return;
    }
    statusEl.classList.remove('is-warn');
    statusEl.textContent =
      '特征闸通过（' +
      checked +
      '/' +
      (FEATURES[catEl.value] || []).length +
      '）。可进入设计款开款流；本期壳页不强制真出图。';
  });

  renderChecklist();
})();
