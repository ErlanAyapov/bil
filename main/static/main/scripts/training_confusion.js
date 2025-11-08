// Unified confusion matrix renderer. Provides window.ConfusionHeatmap for training.js
(function(){
  let canvas = null;
  let ctx = null;
  let labels = [];
  let matrix = [];
  let support = [];
  const padding = { top: 40, right: 20, bottom: 40, left: 60 };
  const cellMinSize = 24;
  const fontMain = "12px Arial";
  const fontSmall = "11px Arial";

  function ensureConfusionContainer() {
    let container = document.getElementById('confusion-container');
    if (!container) {
      const host = document.querySelector('.bg-white.rounded.shadow-sm.p-4.flex-grow-1');
      if (!host) return null;
      const hr = document.createElement('hr');
      hr.className = 'my-3';
      host.appendChild(hr);
      const title = document.createElement('h6');
      title.textContent = 'Confusion Matrix (по классам)';
      title.className = 'text-center';
      host.appendChild(title);
      container = document.createElement('div');
      container.id = 'confusion-container';
      container.className = 'table-responsive';
      container.innerHTML = '<table id="confusion-table" class="table table-sm table-bordered align-middle"><thead></thead><tbody></tbody></table>';
      host.appendChild(container);
    }
    return container;
  }

  function ensureCanvas(){
    if (!canvas) {
      canvas = document.getElementById('confusion-heatmap');
      if (canvas) {
        if (!canvas.width) canvas.width = canvas.clientWidth || 600;
        if (!canvas.height) canvas.height = canvas.clientHeight || 300;
        ctx = canvas.getContext('2d');
      }
    }
    return canvas && ctx;
  }

  function clone2D(arr2d) {
    return (arr2d || []).map(row => (row || []).slice());
  }

  function computeMax(arr2d) {
    let m = 0;
    for (const row of arr2d || []) {
      for (const v of row || []) m = Math.max(m, +v || 0);
    }
    return Math.max(m, 1e-6);
  }

  function formatValue(val) {
    const num = Number(val);
    return Number.isFinite(num) ? num.toFixed(3) : '0.000';
  }

  function colorFor(v, maxVal) {
    const t = Math.max(0, Math.min(1, v / maxVal));
    const start = [80, 160, 220];
    const end = [255, 90, 20];
    const r = Math.round(start[0] + (end[0] - start[0]) * t);
    const g = Math.round(start[1] + (end[1] - start[1]) * t);
    const b = Math.round(start[2] + (end[2] - start[2]) * t);
    return `rgb(${r},${g},${b})`;
  }

  function drawHeatmap() {
    if (!ensureCanvas()) return;
    const rows = matrix.length;
    const cols = rows ? matrix[0].length : 0;
    if (!rows || !cols) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#666';
      ctx.font = '14px Arial';
      ctx.textAlign = 'center';
      ctx.fillText('Пока нет данных для матрицы', canvas.width / 2, canvas.height / 2);
      return;
    }

    const maxVal = computeMax(matrix);
    const W = canvas.width = canvas.clientWidth || canvas.width;
    const H = canvas.height;
    const cellW = Math.max(1, Math.floor((W - padding.left - padding.right) / cols));
    const cellH = Math.max(1, Math.floor((H - padding.top - padding.bottom - 40) / rows));
    const gridW = cellW * cols;
    const gridH = cellH * rows;
    const x0 = padding.left + ( (W - padding.left - padding.right) - gridW ) / 2;
    const y0 = padding.top + ( (H - padding.top - padding.bottom - 40) - gridH ) / 2;

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = '#222';
    ctx.font = 'bold 14px Arial';
    ctx.textAlign = 'center';
    ctx.fillText('Confusion Matrix', W / 2, 20);

    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = fontMain;
    for (let i = 0; i < rows; i++) {
      for (let j = 0; j < cols; j++) {
        const v = +((matrix[i] && matrix[i][j]) || 0);
        const x = x0 + j * cellW;
        const y = y0 + i * cellH;
        ctx.fillStyle = colorFor(v, maxVal);
        ctx.fillRect(x, y, cellW, cellH);
        ctx.strokeStyle = 'rgba(0,0,0,0.08)';
        ctx.strokeRect(x, y, cellW, cellH);
        ctx.fillStyle = v / maxVal > 0.45 ? '#fff' : '#111';
        ctx.fillText(formatValue(v), x + cellW / 2, y + cellH / 2);
      }
    }

    ctx.fillStyle = '#444';
    ctx.font = 'bold 12px Arial';
    ctx.fillText('Predicted', x0 + gridW / 2, y0 - 10);
    ctx.save();
    ctx.translate(x0 - 40, y0 + gridH / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText('True', 0, 0);
    ctx.restore();

    ctx.fillStyle = '#333';
    ctx.font = fontSmall;
    ctx.textAlign = 'right';
    for (let i = 0; i < rows; i++) {
      const y = y0 + i * cellH + cellH / 2;
      ctx.fillText(labels[i] != null ? String(labels[i]) : String(i), x0 - 8, y);
    }
    ctx.textAlign = 'center';
    for (let j = 0; j < cols; j++) {
      const x = x0 + j * cellW + cellW / 2;
      ctx.save();
      ctx.translate(x, y0 + gridH + 14);
      ctx.rotate(-Math.PI / 4);
      ctx.fillText(labels[j] != null ? String(labels[j]) : String(j), 0, 0);
      ctx.restore();
    }
  }

  function renderTable() {
    const container = ensureConfusionContainer();
    if (!container) return;
    const table = container.querySelector('#confusion-table');
    if (!table) return;
    const thead = table.querySelector('thead');
    const tbody = table.querySelector('tbody');
    const cls = (Array.isArray(labels) && labels.length)
      ? labels
      : (Array.isArray(matrix) && matrix[0] ? matrix[0].map((_, i) => i) : []);

    let headHtml = '<tr><th></th>' + cls.map(c => `<th class="text-center">${c}</th>`).join('') + '<th class="text-center">Σ</th></tr>';
    thead.innerHTML = headHtml;

    if (!matrix.length) {
      tbody.innerHTML = '<tr><td colspan="100%" class="text-center text-muted">Нет данных</td></tr>';
      return;
    }

    let bodyHtml = '';
    for (let i = 0; i < matrix.length; i++) {
      const row = matrix[i] || [];
      const sum = row.reduce((a,b)=>a+Number(b||0),0);
      bodyHtml += `<tr><th class="text-center">${cls[i] ?? i}</th>` +
        row.map(v => `<td class="text-end">${formatValue(v)}</td>`).join('') +
        `<td class="text-end fw-semibold">${formatValue(sum)}</td></tr>`;
    }
    if (Array.isArray(support) && support.length) {
      const total = support.reduce((a,b)=>a+Number(b||0),0);
      bodyHtml += '<tr><th>support</th>' + support.map(v => `<td class="text-end">${formatValue(v)}</td>`).join('') + `<td class="text-end fw-semibold">${formatValue(total)}</td></tr>`;
    }
    tbody.innerHTML = bodyHtml;
  }

  function render() {
    drawHeatmap();
    renderTable();
  }

  const api = {
    init(initLabels = [], initMatrix = [], initSupport = []) {
      labels = Array.isArray(initLabels) ? [...initLabels] : [];
      matrix = clone2D(initMatrix);
      support = Array.isArray(initSupport) ? [...initSupport] : [];
      render();
    },
    setLabels(newLabels = []) {
      labels = Array.isArray(newLabels) ? [...newLabels] : [];
      render();
    },
    setMatrix(newMatrix = []) {
      matrix = clone2D(newMatrix);
      render();
    },
    setSupport(newSupport = []) {
      support = Array.isArray(newSupport) ? [...newSupport] : [];
      render();
    },
    updateCell(i, j, value) {
      if (Array.isArray(matrix[i])) {
        matrix[i][j] = value;
        render();
      }
    },
    clear() {
      labels = [];
      matrix = [];
      support = [];
      if (ctx && canvas) ctx.clearRect(0, 0, canvas.width, canvas.height);
      const container = document.getElementById('confusion-container');
      const tbody = container?.querySelector('#confusion-table tbody');
      if (tbody) tbody.innerHTML = '<tr><td colspan="100%" class="text-center text-muted">Нет данных</td></tr>';
    }
  };

  function handleMessage(msg) {
    if (!msg) return;
    if (msg.type === 'global_weights' && Array.isArray(msg.confusion)) {
      api.setLabels(msg.classes || []);
      api.setMatrix(msg.confusion);
      api.setSupport(msg.support || []);
    } else if (msg.type === 'confusion_matrix' && Array.isArray(msg.matrix)) {
      api.setLabels(msg.labels || []);
      api.setMatrix(msg.matrix);
      if (Array.isArray(msg.support)) api.setSupport(msg.support);
    } else if (msg.type === 'training_complete' && Array.isArray(msg.matrix)) {
      api.setLabels(msg.labels || []);
      api.setMatrix(msg.matrix);
      if (Array.isArray(msg.support)) api.setSupport(msg.support);
    }
  }

  function hook() {
    if (!window.wsUi) return;
    const prev = wsUi.onmessage;
    wsUi.onmessage = function(ev) {
      if (typeof prev === 'function') {
        try { prev.call(wsUi, ev); } catch (e) { /* noop */ }
      }
      try {
        const msg = JSON.parse(ev.data);
        handleMessage(msg);
      } catch (e) { /* noop */ }
    };
  }

  window.ConfusionHeatmap = api;
  window.renderConfusionMatrix = (matrix, classes = [], supportData = []) => {
    api.setLabels(classes || []);
    api.setMatrix(matrix || []);
    api.setSupport(supportData || []);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', hook);
  } else {
    hook();
  }
})();
