// Augment training page to render confusion matrix from WS messages
(function(){
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

  function drawHeatmap(matrix) {
    const canvas = document.getElementById('confusion-heatmap');
    if (!canvas || !Array.isArray(matrix) || !matrix.length) return;
    const ctx = canvas.getContext('2d');
    const rows = matrix.length;
    const cols = matrix[0].length;
    const W = canvas.width = canvas.clientWidth || canvas.width;
    const H = canvas.height;
    const cellW = Math.max(1, Math.floor(W / cols));
    const cellH = Math.max(1, Math.floor(H / rows));
    // find max for normalization
    let max = 0;
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) max = Math.max(max, Number(matrix[r][c]||0));
    const pad = 0.5;
    ctx.clearRect(0,0,W,H);
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const v = Number(matrix[r][c]||0);
        const t = max > 0 ? v / max : 0;
        // teal-ish gradient
        const color = `rgba(0,128,128,${0.08 + 0.92*t})`;
        ctx.fillStyle = color;
        ctx.fillRect(Math.floor(c*cellW+pad), Math.floor(r*cellH+pad), Math.ceil(cellW-2*pad), Math.ceil(cellH-2*pad));
      }
    }
  }

  function renderConfusionMatrix(matrix, classes = [], support = []) {
    const container = ensureConfusionContainer();
    if (!container) return;
    // draw heatmap if canvas exists
    drawHeatmap(matrix);
    const table = container.querySelector('#confusion-table');
    const thead = table.querySelector('thead');
    const tbody = table.querySelector('tbody');
    const cls = (Array.isArray(classes) && classes.length) ? classes : (Array.isArray(matrix) && matrix[0] ? matrix[0].map((_, i) => i) : []);
    const formatValue = (val) => {
      const num = Number(val);
      return Number.isFinite(num) ? num.toFixed(3) : "0.000";
    };

    let headHtml = '<tr><th></th>' + cls.map(c => `<th class="text-center">${c}</th>`).join('') + '<th class="text-center">Σ</th></tr>';
    thead.innerHTML = headHtml;
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

  // Hook WS onmessage if available
  function hook() {
    if (!window.wsUi) return;
    const prev = wsUi.onmessage;
    wsUi.onmessage = function(ev){
      if (typeof prev === 'function') {
        try { prev.call(wsUi, ev); } catch(e) { /* noop */ }
      }
      try {
        const m = JSON.parse(ev.data);
        if (m && m.type === 'global_weights' && Array.isArray(m.confusion)) {
          renderConfusionMatrix(m.confusion, m.classes || [], m.support || []);
        }
      } catch(e) { /* noop */ }
    };
  }

  window.renderConfusionMatrix = renderConfusionMatrix;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', hook);
  } else {
    hook();
  }
})();
