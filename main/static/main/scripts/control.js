// Control dashboard UI (WebSocket bridge to DeviceControlConsumer)
(function () {
  const wsUrl = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/device_control/`;
  const state = {
    devices: new Map(),
    selected: null,
  };

  const listEl = document.getElementById("control-device-list");
  const listEmptyEl = document.getElementById("control-device-empty");
  const countEl = document.getElementById("control-device-count");
  const detailName = document.getElementById("control-detail-name");
  const detailId = document.getElementById("control-detail-id");
  const detailStatus = document.getElementById("control-detail-status");
  const detailMode = document.getElementById("control-detail-mode");
  const detailLastStatus = document.getElementById("control-detail-last-status");
  const detailLastEvent = document.getElementById("control-detail-last-event");
  const logEl = document.getElementById("control-log");
  const clearLogBtn = document.getElementById("control-log-clear");
  const commandButtons = document.querySelectorAll("[data-command]");

  let ws;
  let reconnectTimer;

  function log(message, variant = "info") {
    if (!logEl) return;
    const entry = document.createElement("div");
    entry.className = `log-entry log-${variant}`;
    entry.innerHTML = `<small class="text-muted">${new Date().toLocaleTimeString()}</small> ${message}`;
    logEl.appendChild(entry);
    while (logEl.children.length > 200) {
      logEl.removeChild(logEl.firstChild);
    }
    logEl.scrollTop = logEl.scrollHeight;
  }

  function ensureDevice(id, patch = {}) {
    if (!state.devices.has(id)) {
      state.devices.set(id, {
        id,
        name: `Device #${id}`,
        mode: "—",
        status: "offline",
        lastStatus: null,
        lastEvent: null,
      });
    }
    if (patch && typeof patch === "object") {
      Object.assign(state.devices.get(id), patch);
    }
    return state.devices.get(id);
  }

  function renderList() {
    if (!listEl) return;
    listEl.innerHTML = "";
    const devices = Array.from(state.devices.values()).sort((a, b) =>
      a.name.localeCompare(b.name, "ru")
    );
    if (devices.length === 0) {
      if (listEmptyEl) listEmptyEl.classList.remove("d-none");
      countEl.textContent = "0";
      return;
    }
    if (listEmptyEl) listEmptyEl.classList.add("d-none");
    countEl.textContent = String(devices.length);

    devices.forEach((device) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `list-group-item list-group-item-action d-flex justify-content-between align-items-center ${
        device.id === state.selected ? "active" : ""
      }`;
      btn.dataset.deviceId = device.id;
      const badgeClass =
        device.status === "online"
          ? "bg-success"
          : device.status === "warning"
          ? "bg-warning"
          : "bg-secondary";
      btn.innerHTML = `<span class="text-truncate">${device.name}</span>
        <span class="badge ${badgeClass}">${device.status || "offline"}</span>`;
      listEl.appendChild(btn);
    });
  }

  function renderDetails() {
    if (!state.selected || !state.devices.has(state.selected)) {
      detailName.textContent = "Устройство не выбрано";
      detailId.textContent = "—";
      detailStatus.textContent = "offline";
      detailStatus.className = "badge bg-secondary";
      detailMode.textContent = "—";
      detailLastStatus.textContent = "—";
      detailLastEvent.textContent = "—";
      return;
    }
    const device = state.devices.get(state.selected);
    detailName.textContent = device.name;
    detailId.textContent = `ID: ${device.id}`;
    detailMode.textContent = device.mode || "—";
    detailStatus.textContent = device.status || "offline";
    detailStatus.className =
      "badge " +
      (device.status === "online"
        ? "bg-success"
        : device.status === "warning"
        ? "bg-warning text-dark"
        : "bg-secondary");
    detailLastStatus.textContent =
      device.lastStatus || "Статус не получен";
    detailLastEvent.textContent =
      device.lastEvent || "Событий пока не было";
  }

  function selectDevice(id) {
    state.selected = id;
    renderList();
    renderDetails();
  }

  function connectWs() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    ws = new WebSocket(wsUrl);
    ws.onopen = () => {
      log("Канал управления подключен");
      ws.send(JSON.stringify({ type: "ui_subscribe" }));
    };
    ws.onclose = () => {
      log("Канал управления отключён", "warn");
      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(connectWs, 2000);
    };
    ws.onerror = (evt) => {
      log(`Ошибка WS: ${evt?.message || "unknown"}`, "error");
    };
    ws.onmessage = ({ data }) => {
      try {
        const msg = JSON.parse(data);
        handleMessage(msg);
      } catch (err) {
        log("Невозможно разобрать сообщение канала", "error");
      }
    };
  }

  function handleMessage(msg) {
    const type = msg?.type;
    switch (type) {
      case "devices_snapshot":
        (msg.items || []).forEach((item) => {
          ensureDevice(Number(item.device_id), {
            name: item.device_name || `Device #${item.device_id}`,
            mode: item.mode || "—",
            status: "online",
          });
        });
        if (!state.selected && state.devices.size) {
          state.selected = Array.from(state.devices.keys())[0];
        }
        renderList();
        renderDetails();
        break;
      case "device_online":
        ensureDevice(Number(msg.device_id), {
          name: msg.device_name || `Device #${msg.device_id}`,
          status: "online",
          mode: msg.mode || "—",
        });
        renderList();
        renderDetails();
        log(`Устройство #${msg.device_id} онлайн`);
        break;
      case "device_offline":
        ensureDevice(Number(msg.device_id), { status: "offline" });
        renderList();
        renderDetails();
        log(`Устройство #${msg.device_id} офлайн`, "warn");
        break;
      case "status":
        {
          const device = ensureDevice(Number(msg.device_id));
          const pretty = JSON.stringify(msg.payload, null, 2);
          device.lastStatus = pretty;
          device.status = "online";
          renderDetails();
          log(`Статус #${device.id}: ${msg.payload?.mode || ""}`);
        }
        break;
      case "inference_event":
        {
          const device = ensureDevice(Number(msg.device_id));
          device.lastEvent = `${msg.event || "event"} (${msg.mode || "-"})`;
          device.status = "online";
          renderDetails();
          log(
            `Событие #${device.id}: ${msg.event || ""} (${msg.mode || "-"})`,
            msg.event === "error" ? "error" : "info"
          );
        }
        break;
      case "mode_changed":
        ensureDevice(Number(msg.device_id), { mode: msg.mode || "—" });
        renderDetails();
        log(`Режим #${msg.device_id} → ${msg.mode}`);
        break;
      case "run_ack":
        log(`Команда run_inference выполнена (режим ${msg.mode || "-"})`);
        break;
      case "command_response":
        log(
          `Команда ${msg.command} для #${msg.device_id} ${
            msg.success ? "отправлена" : "не доставлена"
          }`,
          msg.success ? "info" : "error"
        );
        break;
      case "error":
        log(`Ошибка: ${msg.message}`, "error");
        break;
      default:
        log(`Получено сообщение: ${type || "unknown"}`);
    }
  }

  function sendCommand(command, params) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      log("Канал управления не готов", "warn");
      return;
    }
    if (!state.selected) {
      log("Сначала выберите устройство", "warn");
      return;
    }
    ws.send(
      JSON.stringify({
        type: "command",
        device_id: state.selected,
        command,
        params,
      })
    );
  }

  function bindEvents() {
    if (listEl) {
      listEl.addEventListener("click", (event) => {
        const target = event.target.closest("[data-device-id]");
        if (!target) return;
        selectDevice(Number(target.dataset.deviceId));
      });
    }
    commandButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const command = btn.dataset.command;
        const mode = btn.dataset.mode;
        const params = {};
        if (mode) params.mode = mode;
        sendCommand(command, params);
      });
    });
    if (clearLogBtn) {
      clearLogBtn.addEventListener("click", () => {
        logEl.innerHTML = "";
      });
    }
  }

  bindEvents();
  renderList();
  renderDetails();
  connectWs();
})();
