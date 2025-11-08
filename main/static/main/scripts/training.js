// training.js — UI helpers for the training dashboard
(function (window, document) {
  const descriptions = {
    cnn: `
      <h5 class="text-primary mb-1">CNN — 1D Convolutional Net</h5>
      <p class="mb-1">Два блока 1D-сверток по 64 фильтра, BatchNorm и Dropout, затем слой на 128 фильтров, MaxPool и GlobalAveragePooling.</p>
      <p class="mb-1">Подходит для оперативного инференса на edge-устройствах (Jetson, Raspberry Pi) с ограниченными ресурсами.</p>
      <p class="mb-0">Рекомендуем запускать на 4–10 устройств в раунде.</p>
    `,
    dnn: `
      <h5 class="text-primary mb-1">DNN — 64×64×32 Fully Connected</h5>
      <p class="mb-1">Три плотных слоя 64–64–32 с ReLU, лёгкая по памяти модель для CPU-клиентов.</p>
      <p class="mb-0">Компромисс между скоростью и качеством, хорошо подходит для быстрой проверки гипотез.</p>
    `,
    cnn_bilstm: `
      <h5 class="text-primary mb-1">CNN + BiLSTM — гибрид</h5>
      <p class="mb-1">Сверточные блоки 32/64 фильтра + двунаправленные LSTM (64 и 16 нейронов) с Dropout.</p>
      <p class="mb-0">Максимальное качество, но выше требования к RAM и времени обучения.</p>
    `,
  };

  function updateModelDescription(model) {
    const block = document.getElementById("model-description");
    if (!block) return;
    block.innerHTML = descriptions[model] || '<p class="text-muted mb-0 text-center">Выберите модель, чтобы увидеть описание.</p>';
  }

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

  const TrainingProgressChart = (() => {
    let chart = null;

    function init(roundsMax = 10) {
      const ctx = document.getElementById("training-progress-chart")?.getContext("2d");
      if (!ctx) return;
      const labels = Array.from({ length: roundsMax }, (_, i) => i + 1);
      chart = new Chart(ctx, {
        type: "line",
        data: {
          labels,
          datasets: [{
            label: "Точность по раундам",
            data: [],
            fill: false,
            borderColor: "rgba(54, 162, 235, 1)",
            backgroundColor: "rgba(54, 162, 235, 0.2)",
            tension: 0.2,
            pointRadius: 3,
          }],
        },
        options: {
          responsive: true,
          animation: false,
          scales: {
            x: { title: { display: true, text: "Раунд" } },
            y: {
              title: { display: true, text: "Точность" },
              beginAtZero: true,
              suggestedMax: 1,
            },
          },
        },
      });
    }

    function addAccuracyPoint(round, accuracy) {
      if (!chart || !round) return;
      chart.data.datasets[0].data[round - 1] = accuracy ?? 0;
      chart.update();
    }

    function reset(roundsMax = 10) {
      if (!chart) return;
      chart.data.labels = Array.from({ length: roundsMax }, (_, i) => i + 1);
      chart.data.datasets[0].data = [];
      chart.update();
    }

    function updateRounds(roundsMax = 10) {
      if (!chart) return;
      chart.data.labels = Array.from({ length: roundsMax }, (_, i) => i + 1);
      chart.update();
    }

    return { init, addAccuracyPoint, reset, updateRounds };
  })();

  const TrainingLossChart = (() => {
    let chart = null;

    function init(roundsMax = 10) {
      const ctx = document.getElementById("train-loss")?.getContext("2d");
      if (!ctx) return;
      const labels = Array.from({ length: roundsMax }, (_, i) => i + 1);
      chart = new Chart(ctx, {
        type: "line",
        data: {
          labels,
          datasets: [{
            label: "Функция потерь",
            data: [],
            fill: false,
            borderColor: "rgba(255, 99, 132, 1)",
            backgroundColor: "rgba(255, 99, 132, 0.2)",
            tension: 0.2,
            pointRadius: 3,
          }],
        },
        options: {
          responsive: true,
          animation: false,
          scales: {
            x: { title: { display: true, text: "Раунд" } },
            y: { title: { display: true, text: "Loss" }, beginAtZero: true },
          },
        },
      });
    }

    function addLossPoint(round, loss) {
      if (!chart || !round) return;
      chart.data.datasets[0].data[round - 1] = loss ?? null;
      chart.update();
    }

    function reset(roundsMax = 10) {
      if (!chart) return;
      chart.data.labels = Array.from({ length: roundsMax }, (_, i) => i + 1);
      chart.data.datasets[0].data = [];
      chart.update();
    }

    function updateRounds(roundsMax = 10) {
      if (!chart) return;
      chart.data.labels = Array.from({ length: roundsMax }, (_, i) => i + 1);
      chart.update();
    }

    return { init, addLossPoint, reset, updateRounds };
  })();

  const ConfusionHeatmap = (() => {
    let canvas = null;
    let ctx = null;
    let labels = [];
    let matrix = [];
    let maxVal = 1;
    const padding = { top: 40, right: 20, bottom: 40, left: 60 };
    const cellMinSize = 24;
    const fontMain = "12px Arial";
    const fontSmall = "11px Arial";

    function init(initLabels = [], initMatrix = []) {
      canvas = document.getElementById("confusion-heatmap");
      if (!canvas) return;
      ctx = canvas.getContext("2d");
      setData(initLabels, initMatrix);
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
      maxVal = Math.max(maxVal, value || 0);
      draw();
    }

    function clear() {
      if (!ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      labels = [];
      matrix = [];
      maxVal = 1;
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
        const t = i / (w - 1);
        ctx.fillStyle = colorFor(t * maxVal);
        ctx.fillRect(x + i, y, 1, h);
      }
      ctx.strokeStyle = "rgba(0,0,0,0.3)";
      ctx.strokeRect(x, y, w, h);
      ctx.fillStyle = "#444";
      ctx.font = fontSmall;
      ctx.textAlign = "left";
      ctx.fillText("0", x, y + h + 12);
      ctx.textAlign = "right";
      ctx.fillText(String(Math.round(maxVal)), x + w, y + h + 12);
      ctx.textAlign = "center";
      ctx.fillText("Количество объектов", x + w / 2, y + h + 28);
    }

    function draw() {
      if (!ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const n = matrix.length || labels.length || 0;
      if (!n) {
        ctx.fillStyle = "#666";
        ctx.font = "14px Arial";
        ctx.textAlign = "center";
        ctx.fillText("Пока нет данных для матрицы", canvas.width / 2, canvas.height / 2);
        return;
      }

      const gridAreaW = canvas.width - padding.left - padding.right;
      const gridAreaH = canvas.height - padding.top - padding.bottom - 40;
      const cellSize = Math.max(cellMinSize, Math.min(gridAreaW / n, gridAreaH / n));
      const gridW = cellSize * n;
      const gridH = cellSize * n;
      const x0 = padding.left + (gridAreaW - gridW) / 2;
      const y0 = padding.top + (gridAreaH - gridH) / 2;

      ctx.fillStyle = "#222";
      ctx.font = "bold 14px Arial";
      ctx.textAlign = "center";
      ctx.fillText("Confusion Matrix", canvas.width / 2, 20);

      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.font = fontMain;
      for (let i = 0; i < n; i++) {
        for (let j = 0; j < n; j++) {
          const v = +((matrix[i] && matrix[i][j]) || 0);
          const x = x0 + j * cellSize;
          const y = y0 + i * cellSize;
          ctx.fillStyle = colorFor(v);
          ctx.fillRect(x, y, cellSize, cellSize);
          ctx.strokeStyle = "rgba(0,0,0,0.08)";
          ctx.strokeRect(x, y, cellSize, cellSize);
          ctx.fillStyle = v / maxVal > 0.45 ? "#fff" : "#111";
          ctx.fillText(String(v), x + cellSize / 2, y + cellSize / 2);
        }
      }

      ctx.fillStyle = "#444";
      ctx.font = "bold 12px Arial";
      ctx.fillText("Predicted", x0 + gridW / 2, y0 - 10);
      ctx.save();
      ctx.translate(x0 - 50, y0 + gridH / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.fillText("True", 0, 0);
      ctx.restore();

      ctx.fillStyle = "#333";
      ctx.font = fontSmall;
      ctx.textAlign = "right";
      for (let i = 0; i < n; i++) {
        const y = y0 + i * cellSize + cellSize / 2;
        ctx.fillText(labels[i] != null ? String(labels[i]) : String(i), x0 - 8, y);
      }
      ctx.textAlign = "center";
      for (let j = 0; j < n; j++) {
        const x = x0 + j * cellSize + cellSize / 2;
        ctx.save();
        ctx.translate(x, y0 + gridH + 14);
        ctx.rotate(-Math.PI / 4);
        ctx.fillText(labels[j] != null ? String(labels[j]) : String(j), 0, 0);
        ctx.restore();
      }

      drawGrid(x0, y0, gridW, gridH, n);
      drawLegend(x0, y0 + gridH + 20, Math.min(200, gridW), 10);
    }

    return { init, setData, setLabels, setMatrix, updateCell, clear };
  })();

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
    document.getElementById("start-btn").disabled = true;
    TrainingProgressChart.reset(rounds);
    TrainingLossChart.reset(rounds);
    ConfusionHeatmap.clear();
    log(`Старт обучения: ${model.toUpperCase()}, раундов ${rounds}`);
  }

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
    try {
      message = JSON.parse(data || "{}");
    } catch (_) {
      return;
    }

    switch (message.type) {
      case "full_subscribers":
        (message.items || []).forEach((it) => log(`Устройство подключено: ${it.device_name || `device#${it.device_id}`}`));
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
        document.getElementById("start-btn").disabled = false;
        log("Обучение завершено");
        if (Array.isArray(message.labels)) ConfusionHeatmap.setLabels(message.labels);
        if (Array.isArray(message.matrix)) ConfusionHeatmap.setMatrix(message.matrix);
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
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrap);
  } else {
    bootstrap();
  }

  window.startTraining = startTraining;
  window.updateModelDescription = updateModelDescription;
  window.TrainingProgressChart = TrainingProgressChart;
  window.TrainingLossChart = TrainingLossChart;
  window.ConfusionHeatmap = ConfusionHeatmap;
  window.trainingLog = log;
})(window, document);
