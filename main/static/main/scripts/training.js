// training.js — UI helpers for the training dashboard (polished)
(function (window, document) {
  // ---------- UX: описания моделей ----------
  const descriptions = {
    cnn: `
      <h5 class="text-primary mb-1">CNN — 1D Convolutional Net</h5>
      <p class="mb-1">Два блока 1D-свёрток по 64 фильтра, BatchNorm и Dropout, затем слой на 128 фильтров, MaxPool и GlobalAveragePooling.</p>
      <p class="mb-1">Подходит для инференса на edge-устройствах (Jetson, Raspberry Pi) с ограниченными ресурсами.</p>
      <p class="mb-0">Рекомендуем запускать на 4–10 устройств в раунде.</p>
    `,
    dnn: `
      <h5 class="text-primary mb-1">DNN — 64×64×32 Fully Connected</h5>
      <p class="mb-1">Три плотных слоя 64–64–32 с ReLU — лёгкая по памяти модель для CPU-клиентов.</p>
      <p class="mb-0">Компромисс между скоростью и качеством, хорошо подходит для быстрой проверки гипотез.</p>
    `,
    cnn_bilstm: `
      <h5 class="text-primary mb-1">CNN + BiLSTM — гибрид</h5>
      <p class="mb-1">Свёрточные блоки 32/64 фильтра + двунаправленные LSTM (64 и 16 нейронов) с Dropout.</p>
      <p class="mb-0">Максимальное качество, но выше требования к RAM и времени обучения.</p>
    `,
  };

  function updateModelDescription(model) {
    const block = document.getElementById("model-description");
    if (!block) return;
    block.innerHTML = descriptions[model] || '<p class="text-muted mb-0 text-center">Выберите модель, чтобы увидеть описание.</p>';
  }

  // ---------- Utils: время/лог ----------
  function timestamp() {
    return new Date().toLocaleTimeString();
  }

  function log(message) {
    const box = document.querySelector("#training-logs .alert");
    if (!box) return;
    const row = document.createElement("div");
    row.innerHTML = `<span class="text-muted">${timestamp()}</span> — ${message}`;
    box.appendChild(row);
    box.scrollTop = box.scrollHeight;
  }

  // ---------- HiDPI / Canvas Utils ----------
  function fitCanvasToPixelRatio(canvas) {
    if (!canvas) return false;
    const pr = Math.max(1, Math.floor(window.devicePixelRatio || 1));
    const rect = canvas.getBoundingClientRect();
    // Если элемент скрыт, getBoundingClientRect может вернуть 0
    const cssW = Math.max(1, Math.round(rect.width));
    const cssH = Math.max(1, Math.round(rect.height));
    const w = cssW * pr;
    const h = cssH * pr;
    let changed = false;
    if (canvas.width !== w) { canvas.width = w; changed = true; }
    if (canvas.height !== h) { canvas.height = h; changed = true; }
    const ctx = canvas.getContext("2d");
    if (ctx) ctx.setTransform(pr, 0, 0, pr, 0, 0);
    return changed;
  }

  function debounce(fn, ms) {
    let t = null;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  }

  // ---------- Chart.js глобалочки (необязательно, но делает всё ровнее) ----------
  if (window.Chart) {
    Chart.defaults.animation = false;
    Chart.defaults.responsive = true;
    Chart.defaults.maintainAspectRatio = false; // мы управляем высотой через CSS
    Chart.defaults.font.family = `Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif`;
    Chart.defaults.elements.point.radius = 3;
    Chart.defaults.plugins.legend.display = false;
    Chart.defaults.layout = Chart.defaults.layout || {};
    Chart.defaults.layout.padding = 8;
  }

  // ---------- Точность по раундам ----------
  const TrainingProgressChart = (() => {
    let chart = null;
    let canvas = null;

    function _ensureCanvas() {
      canvas = document.getElementById("training-progress-chart");
      return canvas && canvas.getContext("2d") ? canvas : null;
    }

    function _buildLabels(roundsMax) {
      return Array.from({ length: roundsMax }, (_, i) => i + 1);
    }

    function init(roundsMax = 10) {
      const cv = _ensureCanvas();
      if (!cv) return;
      fitCanvasToPixelRatio(cv);

      const ctx = cv.getContext("2d");
      // Уничтожаем предыдущий график, если был
      if (cv._chartInstance) {
        cv._chartInstance.destroy();
        cv._chartInstance = null;
      }

      chart = new Chart(ctx, {
        type: "line",
        data: {
          labels: _buildLabels(roundsMax),
          datasets: [{
            label: "Точность по раундам",
            data: [],
            fill: false,
            borderColor: "rgba(54, 162, 235, 1)",
            backgroundColor: "rgba(54, 162, 235, 0.2)",
            tension: 0.2,
          }],
        },
        options: {
          scales: {
            x: { title: { display: true, text: "Раунд" } },
            y: {
              title: { display: true, text: "Точность" },
              beginAtZero: true,
              suggestedMax: 1,
              ticks: { callback: v => (typeof v === "number" ? v.toFixed(1) : v) }
            },
          },
        },
      });
      cv._chartInstance = chart;
    }

    function addAccuracyPoint(round, accuracy) {
      if (!chart || !round) return;
      const idx = Math.max(0, round - 1);
      chart.data.datasets[0].data[idx] = accuracy ?? 0;
      chart.update("none");
    }

    function reset(roundsMax = 10) {
      if (!chart) return;
      chart.data.labels = _buildLabels(roundsMax);
      chart.data.datasets[0].data = [];
      chart.update("none");
    }

    function updateRounds(roundsMax = 10) {
      if (!chart) return;
      const newLabels = _buildLabels(roundsMax);
      const data = chart.data.datasets[0].data;
      // Обрезаем/не дополняем массив — новые точки придут из stream
      if (data.length > newLabels.length) data.length = newLabels.length;
      chart.data.labels = newLabels;
      chart.update("none");
    }

    function resize() {
      const cv = _ensureCanvas();
      if (!cv) return;
      const changed = fitCanvasToPixelRatio(cv);
      if (changed && cv._chartInstance) cv._chartInstance.update("none");
    }

    return { init, addAccuracyPoint, reset, updateRounds, resize };
  })();

  // ---------- Loss по раундам ----------
  const TrainingLossChart = (() => {
    let chart = null;
    let canvas = null;

    function _ensureCanvas() {
      canvas = document.getElementById("train-loss");
      return canvas && canvas.getContext("2d") ? canvas : null;
    }

    function _buildLabels(roundsMax) {
      return Array.from({ length: roundsMax }, (_, i) => i + 1);
    }

    function init(roundsMax = 10) {
      const cv = _ensureCanvas();
      if (!cv) return;
      fitCanvasToPixelRatio(cv);

      const ctx = cv.getContext("2d");
      if (cv._chartInstance) {
        cv._chartInstance.destroy();
        cv._chartInstance = null;
      }

      chart = new Chart(ctx, {
        type: "line",
        data: {
          labels: _buildLabels(roundsMax),
          datasets: [{
            label: "Функция потерь",
            data: [],
            fill: false,
            borderColor: "rgba(255, 99, 132, 1)",
            backgroundColor: "rgba(255, 99, 132, 0.2)",
            tension: 0.2,
          }],
        },
        options: {
          scales: {
            x: { title: { display: true, text: "Раунд" } },
            y: {
              title: { display: true, text: "Loss" },
              beginAtZero: true,
            },
          },
        },
      });
      cv._chartInstance = chart;
    }

    function addLossPoint(round, loss) {
      if (!chart || !round) return;
      const idx = Math.max(0, round - 1);
      chart.data.datasets[0].data[idx] = (loss ?? null);
      chart.update("none");
    }

    function reset(roundsMax = 10) {
      if (!chart) return;
      chart.data.labels = _buildLabels(roundsMax);
      chart.data.datasets[0].data = [];
      chart.update("none");
    }

    function updateRounds(roundsMax = 10) {
      if (!chart) return;
      const newLabels = _buildLabels(roundsMax);
      const data = chart.data.datasets[0].data;
      if (data.length > newLabels.length) data.length = newLabels.length;
      chart.data.labels = newLabels;
      chart.update("none");
    }

    function resize() {
      const cv = _ensureCanvas();
      if (!cv) return;
      const changed = fitCanvasToPixelRatio(cv);
      if (changed && cv._chartInstance) cv._chartInstance.update("none");
    }

    return { init, addLossPoint, reset, updateRounds, resize };
  })();

  // ---------- Матрица ошибок (кастомный Canvas) ----------
  // ---------- Матрица ошибок (фикс HiDPI + адаптивные подписи) ----------
const ConfusionHeatmap = (() => {
  let canvas = null;
  let ctx = null;
  let labels = [];
  let matrix = [];
  let maxVal = 1;

  // Отступы и минимальные размеры
  const padding = { top: 44, right: 22, bottom: 52, left: 64 };
  const cellMinSize = 18;

  function _ensureCanvas() {
    canvas = document.getElementById("confusion-heatmap");
    if (!canvas) return null;
    ctx = canvas.getContext("2d");
    return canvas;
  }

  function clone2D(arr2d) {
    return (arr2d || []).map(row => (row || []).slice());
  }

  function computeMax(arr2d) {
    let m = 0;
    for (const row of arr2d || []) for (const v of row || []) m = Math.max(m, +v || 0);
    return Math.max(m, 1e-6);
  }

  // плавный градиент от синего к оранжевому
  function colorFor(v) {
    const t = Math.max(0, Math.min(1, v / maxVal));
    const start = [80, 160, 220];
    const end = [255, 90, 20];
    const r = Math.round(start[0] + (end[0] - start[0]) * t);
    const g = Math.round(start[1] + (end[1] - start[1]) * t);
    const b = Math.round(start[2] + (end[2] - start[2]) * t);
    return `rgb(${r},${g},${b})`;
  }

  function drawGrid(x0, y0, w, h, n) {
    ctx.strokeStyle = "rgba(0,0,0,0.15)";
    for (let i = 0; i <= n; i++) {
      const y = y0 + i * (h / n);
      ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + w, y); ctx.stroke();
    }
    for (let j = 0; j <= n; j++) {
      const x = x0 + j * (w / n);
      ctx.beginPath(); ctx.moveTo(x, y0); ctx.lineTo(x, y0 + h); ctx.stroke();
    }
  }

  function drawLegend(x, y, w, h) {
    for (let i = 0; i < w; i++) {
      const t = i / Math.max(1, (w - 1));
      ctx.fillStyle = colorFor(t * maxVal);
      ctx.fillRect(x + i, y, 1, h);
    }
    ctx.strokeStyle = "rgba(0,0,0,0.3)";
    ctx.strokeRect(x, y, w, h);

    ctx.fillStyle = "#444";
    ctx.font = "11px Arial";
    ctx.textAlign = "left";  ctx.fillText("0", x, y + h + 12);
    ctx.textAlign = "right"; ctx.fillText(String(Math.round(maxVal)), x + w, y + h + 12);
    ctx.textAlign = "center";ctx.fillText("Количество объектов", x + w / 2, y + h + 28);
  }

  function draw() {
    if (!ctx || !canvas) return;

    // 1) подгоняем буфер под HiDPI
    fitCanvasToPixelRatio(canvas);

    // 2) работаем в CSS-пикселях (после setTransform единица == CSS px)
    const rect = canvas.getBoundingClientRect();
    const cssW = Math.max(1, Math.round(rect.width));
    const cssH = Math.max(1, Math.round(rect.height));

    ctx.clearRect(0, 0, cssW, cssH);

    const n = matrix.length || labels.length || 0;
    if (!n) {
      ctx.fillStyle = "#666";
      ctx.font = "14px Arial";
      ctx.textAlign = "center";
      ctx.fillText("Пока нет данных для матрицы", cssW / 2, cssH / 2);
      return;
    }

    // 3) вычисляем область сетки
    const legendH = 16 + 28; // сама легенда + подписи
    const gridAreaW = cssW - padding.left - padding.right;
    const gridAreaH = cssH - padding.top - padding.bottom - legendH;

    const cellSize = Math.max(cellMinSize, Math.min(gridAreaW / n, gridAreaH / n));
    const gridW = cellSize * n;
    const gridH = cellSize * n;
    const x0 = padding.left + (gridAreaW - gridW) / 2;
    const y0 = padding.top + (gridAreaH - gridH) / 2;

    // 4) адаптивные шрифты
    const valueFontPx  = Math.max(9, Math.min(Math.floor(cellSize * 0.42), 13));
    const labelFontPx  = Math.max(9, Math.min(Math.floor(cellSize * 0.32), 12));
    const showValues   = cellSize >= 16;

    // 5) заголовок
    ctx.fillStyle = "#222";
    ctx.font = "bold 14px Arial";
    ctx.textAlign = "center";
    ctx.fillText("Confusion Matrix", cssW / 2, 20);

    // 6) ячейки + значения
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = `${valueFontPx}px Arial`;
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        const v = +((matrix[i] && matrix[i][j]) || 0);
        const x = x0 + j * cellSize;
        const y = y0 + i * cellSize;
        ctx.fillStyle = colorFor(v);
        ctx.fillRect(x, y, cellSize, cellSize);
        ctx.strokeStyle = "rgba(0,0,0,0.08)";
        ctx.strokeRect(x, y, cellSize, cellSize);

        if (showValues) {
          ctx.fillStyle = v / maxVal > 0.55 ? "#fff" : "#111";
          ctx.fillText(String(v), x + cellSize / 2, y + cellSize / 2);
        }
      }
    }

    // 7) подписи осей
    ctx.fillStyle = "#444";
    ctx.font = "bold 12px Arial";
    ctx.fillText("Predicted", x0 + gridW / 2, y0 - 12);
    ctx.save();
    ctx.translate(x0 - 48, y0 + gridH / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText("True", 0, 0);
    ctx.restore();

    // 8) подписи классов — прореживаем
    ctx.fillStyle = "#333";
    ctx.font = `${labelFontPx}px Arial`;

    // шаг так, чтобы было ~ до 12 подписей на ось
    const maxLabelsPerAxis = Math.max(6, Math.min(12, Math.floor(gridW / 60)));
    const step = Math.max(1, Math.ceil(n / maxLabelsPerAxis));

    // Y (слева)
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (let i = 0; i < n; i += step) {
      const y = y0 + i * cellSize + cellSize / 2;
      const txt = labels[i] != null ? String(labels[i]) : String(i);
      ctx.fillText(txt, x0 - 8, y);
    }

    // X (снизу) — чуть повернём
    ctx.textAlign = "center";
    for (let j = 0; j < n; j += step) {
      const x = x0 + j * cellSize + cellSize / 2;
      const txt = labels[j] != null ? String(labels[j]) : String(j);
      ctx.save();
      ctx.translate(x, y0 + gridH + 16);
      ctx.rotate(-Math.PI / 6); // -30° (мягче, чем -45°)
      ctx.fillText(txt, 0, 0);
      ctx.restore();
    }

    // сетка и легенда
    drawGrid(x0, y0, gridW, gridH, n);
    drawLegend(x0, y0 + gridH + 22, Math.min(220, gridW), 12);
  }

  function init(initLabels = [], initMatrix = []) {
    if (!_ensureCanvas()) return;
    labels = Array.isArray(initLabels) ? [...initLabels] : [];
    matrix = clone2D(initMatrix);
    maxVal = computeMax(matrix);
    draw();
  }

  function setData(newLabels = [], newMatrix = []) {
    labels = Array.isArray(newLabels) ? [...newLabels] : [];
    matrix = clone2D(newMatrix);
    maxVal = computeMax(matrix);
    draw();
  }

  function setLabels(newLabels = []) {
    labels = Array.isArray(newLabels) ? [...newLabels] : [];
    draw();
  }

  function setMatrix(newMatrix = []) {
    matrix = clone2D(newMatrix);
    maxVal = computeMax(matrix);
    draw();
  }

  function updateCell(i, j, value) {
    if (!matrix?.length || !matrix[i]) return;
    matrix[i][j] = value;
    maxVal = Math.max(maxVal, +value || 0);
    draw();
  }

  function clear() {
    if (!_ensureCanvas()) return;
    const rect = canvas.getBoundingClientRect();
    ctx.clearRect(0, 0, rect.width, rect.height);
    labels = [];
    matrix = [];
    maxVal = 1;
  }

  function resize() {
    if (!_ensureCanvas()) return;
    // fitCanvasToPixelRatio вызывается в draw(), но дернём для гарантии
    const changed = fitCanvasToPixelRatio(canvas);
    if (changed) draw();
  }

  return { init, setData, setLabels, setMatrix, updateCell, clear, resize, draw };
})();


  // ---------- Старт обучения ----------
  function startTraining() {
    const modelEl = document.getElementById("model");
    const roundsEl = document.getElementById("rounds");
    if (!modelEl || !roundsEl) return;
    const model = modelEl.value;
    const rounds = Number(roundsEl.value) || 10;
    if (!model || !window.wsUi || window.wsUi.readyState !== WebSocket.OPEN) {
      log("Невозможно запустить обучение — нет подключения или модель не выбрана.");
      return;
    }

    window.wsUi.send(JSON.stringify({ type: "start_training", model, rounds }));
    const btn = document.getElementById("start-btn");
    if (btn) btn.disabled = true;

    TrainingProgressChart.reset(rounds);
    TrainingLossChart.reset(rounds);
    ConfusionHeatmap.clear();
    log(`Старт обучения: ${model.toUpperCase()}, раундов ${rounds}`);
  }

  // ---------- WebSocket UI канал ----------
  const wsUi = new WebSocket(`${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/train_model/`);
  window.wsUi = wsUi;

  wsUi.onopen = () => {
    log("UI WebSocket подключён");
    wsUi.send(JSON.stringify({ type: "ui_sync" }));
  };

  wsUi.onclose = () => log("UI WebSocket отключён");
  wsUi.onerror = (err) => log(`Ошибка WebSocket: ${err?.message || "unknown"}`);

  wsUi.onmessage = ({ data }) => {
    let message = {};
    try { message = JSON.parse(data || "{}"); } catch (_) { return; }

    switch (message.type) {
      case "full_subscribers":
        (message.items || []).forEach((it) =>
          log(`Устройство подключено: ${it.device_name || `device#${it.device_id}`}`));
        break;

      case "train_log":
        if (message.text) log(message.text);
        break;

      case "global_weights":
        if (message.round) TrainingProgressChart.addAccuracyPoint(message.round, message.accuracy ?? 0);
        log(`Получены глобальные веса (раунд ${message.round ?? "?"})`);
        if (Array.isArray(message.confusion)) {
          ConfusionHeatmap.setMatrix(message.confusion);
          if (Array.isArray(message.classes)) ConfusionHeatmap.setLabels(message.classes);
        }
        break;

      case "train_loss":
        if (message.round) TrainingLossChart.addLossPoint(message.round, message.loss ?? null);
        log(`Loss на раунде ${message.round}: ${message.loss ?? "—"}`);
        break;

      case "confusion_matrix":
        if (Array.isArray(message.labels)) ConfusionHeatmap.setLabels(message.labels);
        if (Array.isArray(message.matrix)) ConfusionHeatmap.setMatrix(message.matrix);
        log("Обновлена матрица ошибок");
        break;

      case "confusion_update":
        ConfusionHeatmap.updateCell(message.i, message.j, message.value);
        break;

      case "training_complete":
        {
          const btn = document.getElementById("start-btn");
          if (btn) btn.disabled = false;
          log("Обучение завершено");
          if (Array.isArray(message.labels)) ConfusionHeatmap.setLabels(message.labels);
          if (Array.isArray(message.matrix)) ConfusionHeatmap.setMatrix(message.matrix);
        }
        break;

      case "subscribe":
        log(`Подключился клиент: ${message.device_name || "неизвестно"}`);
        break;

      case "start_training":
        log(`Сервер начал раунд ${message.round ?? 0}`);
        break;

      default:
        log(`Получено сообщение: ${message.type || "неизвестно"}`);
    }
  };

  // ---------- Bootstrap ----------
  function bootstrap() {
    const roundsInput = document.getElementById("rounds");
    if (roundsInput) {
      roundsInput.addEventListener("input", (e) => {
        document.getElementById("rounds-value").textContent = e.target.value;
      });
      roundsInput.addEventListener("change", (e) => {
        const val = Number(e.target.value) || 10;
        TrainingProgressChart.updateRounds(val);
        TrainingLossChart.updateRounds(val);
      });
    }

    const initialRounds = Number(roundsInput?.value) || 10;
    TrainingProgressChart.init(initialRounds);
    TrainingLossChart.init(initialRounds);
    ConfusionHeatmap.init([], []);
    updateModelDescription(document.getElementById("model")?.value);

    // Resize handling for crisp charts
    const onResize = debounce(() => {
      TrainingProgressChart.resize();
      TrainingLossChart.resize();
      ConfusionHeatmap.resize();
    }, 120);
    window.addEventListener("resize", onResize);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrap);
  } else {
    bootstrap();
  }

  // ---------- Экспорт в window ----------
  window.startTraining = startTraining;
  window.updateModelDescription = updateModelDescription;
  window.TrainingProgressChart = TrainingProgressChart;
  window.TrainingLossChart = TrainingLossChart;
  window.ConfusionHeatmap = ConfusionHeatmap;
  window.trainingLog = log;
})(window, document);
