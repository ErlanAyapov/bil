let selectedDeviceId = localStorage.getItem('selectedDeviceId');

function selectDevice(rowId) {
    const selectedRow = document.getElementById(rowId);
    if (!selectedRow) return;

    // Удаляем класс "selected" у всех строк
    document.querySelectorAll('.device-tr').forEach(row => {
        row.classList.remove('selected');
    });

    // Добавляем класс "selected" к выбранной строке
    selectedRow.classList.add('selected');

    const deviceId = selectedRow.getAttribute("data-device-id");
    localStorage.setItem('selectedDeviceId', deviceId);
    selectedDeviceId = deviceId;
}
document.addEventListener("DOMContentLoaded", () => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/device_status/`);

    const maxLogs = 50;
    const allLogs = [];

    const logBlock = document.querySelector('.logs');
    const downloadBtn = document.createElement('button');
    downloadBtn.innerText = "📥 Скачать CSV отчет";
    downloadBtn.style.margin = '10px';
    downloadBtn.style.width = '100%';
    downloadBtn.style.color = '#fff';
    downloadBtn.style.backgroundColor = '#3570ab';
    downloadBtn.classList.add('btn');
    downloadBtn.addEventListener('click', () => {
        if (allLogs.length === 0) return;

        const headers = ['Дата', 'Устройство', 'Трафик', 'Вероятность'];
        const csvRows = [headers.join(',')];

        allLogs.forEach(log => {
            csvRows.push([
                `"${log.date}"`,
                `"${log.device_id}"`,
                `"${log.prediction_label}"`,
                `"${(parseFloat(log.confidence) * 100).toFixed(1)}%"`
            ].join(','));
        });

        const csvContent = csvRows.join('\n');
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = 'device_logs.csv';
        a.click();
        URL.revokeObjectURL(url);
    });

    if (logBlock) logBlock.parentElement.insertBefore(downloadBtn, logBlock);

    ws.onopen = () => {
        console.log('✅ Соединение WebSocket установлено');
    };

    ws.onmessage = function (event) {
        try {
            const data = JSON.parse(event.data);
            console.log("📡 Получены данные от WebSocket:", data);

            const {
                device_token,
                status,
                device_id: id,
                prediction,
                confidence,
                prediction_label,
                ip_data
            } = data;

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

                const device = new Device(
                    id,
                    device_token,
                    "Устройство #" + id,
                    "Датчик",
                    prediction,
                    status,
                    confidence,
                    ip_data.country || "Unknown"
                );
                device.setTraffic(prediction, confidence);

                if (statusCell) {
                    statusCell.innerText = status === 'danger' ? 'Опасен' : 'Активен';
                    statusCell.classList.toggle('text-danger', status === 'danger');
                    statusCell.classList.toggle('text-success', status === 'safe');
                }
                if (countryCell) {
                    countryCell.innerText = `${ip_data.country}, ${ip_data.city}` || '-';
                }
                if (geoCell) {
                    geoCell.innerText = `${ip_data.lat}, ${ip_data.lon}` || '-';
                }
                if (trafficCell) {
                    trafficCell.innerText = prediction_label + " (" + prediction + ")";
                }
                if (typeCell) {
                    typeCell.innerText = 'Датчик';
                }
                if (timezoneCell) {
                    timezoneCell.innerText = ip_data.timezone || '-';
                }
                if (operatorCell) {
                    operatorCell.innerText = ip_data.org || '-';
                }

                if (confidenceCell) {
                    confidenceCell.innerText = (parseFloat(confidence) * 100).toFixed(1) + "%";
                }
            } else {
                console.warn(`❗ Устройство с ID ${id} не найдено`);
            }

            const now = new Date().toLocaleString();

            allLogs.push({
                date: now,
                device_id: id,
                prediction_label,
                confidence
            });

            if (logBlock) {
                const logEntry = document.createElement('div');
                logEntry.innerHTML =
                    `<span>Дата: ${now}</span><br>` +
                    `<span>Устройство: ${id -120}</span><br>` +
                    `<span>Трафик: ${prediction_label}</span><br>` +
                    `<span>Вероятность: ${(parseFloat(confidence) * 100).toFixed(1)}%</span><hr>`;

                logBlock.appendChild(logEntry); // ➕ добавляем в конец (вниз)

                while (logBlock.children.length > maxLogs) {
                    logBlock.removeChild(logBlock.firstChild); // ❌ удаляем сверху
                }

                logBlock.scrollTop = logBlock.scrollHeight; // 📜 автоскролл вниз
            }

        } catch (error) {
            console.error("❌ Ошибка парсинга JSON:", error);
        }
    };

    ws.onerror = function (error) {
        console.error("❌ Ошибка WebSocket:", error);
    };

    ws.onclose = function (event) {
        console.log("🔌 WebSocket соединение закрыто:", event);
        document.querySelectorAll('.device-tr').forEach(row => {
            row.cells[1].innerText = '-';
            row.cells[4].innerText = '-';
            row.cells[5].innerText = '-';
        });
    };
});
