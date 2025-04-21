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
    const allLogs = [];  // Сохраняем все логи

    const logBlock = document.querySelector('.logs');
    const downloadBtn = document.createElement('button');
    downloadBtn.innerText = "📥 Скачать CSV отчет";
    downloadBtn.style.margin = '10px';
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
                prediction_label
            } = data;

            const row = document.getElementById(`device-row-${id}`);
            if (row) {
                const statusCell = row.cells[1];
                const trafficCell = row.cells[4];
                const confidenceCell = row.cells[5];

                if (statusCell) {
                    statusCell.innerText = status === 'danger' ? 'Опасен' : 'Активен';
                    statusCell.classList.toggle('text-danger', status === 'danger');
                    statusCell.classList.toggle('text-success', status === 'safe');
                }

                if (trafficCell) {
                    trafficCell.innerText = prediction_label + " (" + prediction + ")";
                }

                if (confidenceCell) {
                    confidenceCell.innerText = (parseFloat(confidence) * 100).toFixed(1) + "%";
                }
            } else {
                console.warn(`❗ Устройство с ID ${id} не найдено`);
            }

            const now = new Date().toLocaleString();

            // Добавляем лог в массив
            allLogs.push({
                date: now,
                device_id: id,
                prediction_label,
                confidence
            });

            if (logBlock) {
                // Удаляем лишние, если их больше 50
                while (logBlock.children.length >= maxLogs) {
                    logBlock.removeChild(logBlock.firstChild);
                }

                const logEntry = document.createElement('div');
                logEntry.innerHTML =
                    `<span>Дата: ${now}</span><br>` +
                    `<span>Устройство: ${id}</span><br>` +
                    `<span>Трафик: ${prediction_label}</span><br>` +
                    `<span>Вероятность: ${(parseFloat(confidence) * 100).toFixed(1)}%</span><hr>`;
                logBlock.appendChild(logEntry);

                // Автоскролл вниз
                logBlock.scrollTop = logBlock.scrollHeight;
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
