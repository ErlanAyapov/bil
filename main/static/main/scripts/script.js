let selectedDeviceId = localStorage.getItem("selectedDeviceId");

function selectDevice(rowId) {
  const selectedRow = document.getElementById(rowId);
  if (!selectedRow) return;

  document.querySelectorAll(".device-tr").forEach((row) => row.classList.remove("selected"));
  selectedRow.classList.add("selected");

  const deviceId = selectedRow.getAttribute("data-device-id");
  localStorage.setItem("selectedDeviceId", deviceId);
  selectedDeviceId = deviceId;
}

document.addEventListener("DOMContentLoaded", () => {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${window.location.host}/ws/device_status/`);

  const maxLogs = 50;
  const allLogs = [];
  const logBlock = document.querySelector(".logs");

  const downloadBtn = document.createElement("button");
  downloadBtn.innerText = "Скачать CSV журнал";
  downloadBtn.className = "btn btn-primary w-100 mb-2";
  downloadBtn.addEventListener("click", () => {
    if (!allLogs.length) return;
    const headers = ["Время", "ID устройства", "Предсказание", "Достоверность"];
    const rows = [headers.join(",")];
    allLogs.forEach((log) => {
      rows.push(
        [
          `"${log.date}"`,
          `"${log.device_id}"`,
          `"${log.prediction_label}"`,
          `"${(parseFloat(log.confidence) * 100).toFixed(1)}%"`,
        ].join(",")
      );
    });
    const blob = new Blob([rows.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "device_logs.csv";
    a.click();
    URL.revokeObjectURL(url);
  });
  if (logBlock?.parentElement) {
    logBlock.parentElement.insertBefore(downloadBtn, logBlock);
  }

  ws.onopen = () => console.log("[Monitor] WS connected");

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      const {
        device_token,
        status,
        device_id: id,
        prediction,
        confidence,
        prediction_label,
      } = data;

      const ipData = data.ip_data || {};
      const ipCountry = ipData.country || "Unknown";
      const ipCity = ipData.city || "";
      const ipLat = ipData.lat ?? ipData.latitude;
      const ipLon = ipData.lon ?? ipData.longitude;
      const ipTimezone = ipData.timezone || "-";
      const ipOperator = ipData.org || ipData.isp || "-";
      const ipAddress = ipData.ip || ipData.query || "-";

      const row = document.getElementById(`device-row-${id}`);
      if (row) {
        const statusCell = row.cells[1];
        const gatewayCell = row.cells[2];
        const countryCell = row.cells[3];
        const geoCell = row.cells[4];
        const operatorCell = row.cells[5];
        const typeCell = row.cells[6];
        const timezoneCell = row.cells[7];
        const trafficCell = row.cells[8];
        const confidenceCell = row.cells[9];

        const device = typeof Device === "function"
          ? new Device(
              id,
              device_token,
              `Устройство #${id}`,
              "Датчик",
              prediction,
              status,
              confidence,
              ipCountry
            )
          : null;
        device?.setTraffic?.(prediction, confidence);

        if (statusCell) {
          statusCell.innerText = status === "danger" ? "Опасно" : "Активен";
          statusCell.classList.toggle("text-danger", status === "danger");
          statusCell.classList.toggle("text-success", status === "safe");
        }
        if (gatewayCell) gatewayCell.innerText = ipAddress;
        if (countryCell) {
          const loc = ipCity ? `${ipCountry}, ${ipCity}` : ipCountry;
          countryCell.innerText = loc;
        }
        if (geoCell) geoCell.innerText = ipLat != null && ipLon != null ? `${ipLat}, ${ipLon}` : "-";
        if (operatorCell) operatorCell.innerText = ipOperator;
        if (typeCell) typeCell.innerText = "Датчик";
        if (timezoneCell) timezoneCell.innerText = ipTimezone;
        if (trafficCell) trafficCell.innerText = `${prediction_label} (${prediction})`;
        if (confidenceCell)
          confidenceCell.innerText = `${(parseFloat(confidence) * 100).toFixed(1)}%`;
      } else {
        console.warn(`[Monitor] row for device ${id} not found`);
      }

      const now = new Date().toLocaleString();
      allLogs.push({
        date: now,
        device_id: id,
        prediction_label,
        confidence,
      });
      if (logBlock) {
        const logEntry = document.createElement("div");
        logEntry.innerHTML = `
          <span>Время: ${now}</span><br/>
          <span>Устройство: ${id}</span><br/>
          <span>Событие: ${prediction_label}</span><br/>
          <span>Достоверность: ${(parseFloat(confidence) * 100).toFixed(1)}%</span>
          <hr/>
        `;
        logBlock.appendChild(logEntry);
        while (logBlock.children.length > maxLogs) {
          logBlock.removeChild(logBlock.firstChild);
        }
        logBlock.scrollTop = logBlock.scrollHeight;
      }
    } catch (error) {
      console.error("[Monitor] failed to parse message", error);
    }
  };

  ws.onerror = (error) => console.error("[Monitor] WS error", error);
  ws.onclose = (event) => {
    console.log("[Monitor] WS closed", event.code, event.reason);
    document.querySelectorAll(".device-tr").forEach((row) => {
      row.cells[1].innerText = "-";
      row.cells[4].innerText = "-";
      row.cells[5].innerText = "-";
    });
  };
});
