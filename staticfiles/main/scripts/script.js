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
    // Подключение к WebSocket
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/device_status/`);

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

            // Обновляем таблицу (можно доработать, если нужно более сложное отображение)
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

            // Можно также обновить блок логов (правый блок)
            const logBlock = document.querySelector('.logs');
            if (logBlock && selectedDeviceId === id) {
                logBlock.innerHTML =
                    `<span>Дата: ${new Date().toLocaleString()}</span><br>` +
                    `<span>Трафик: ${prediction_label}</span><br>` +
                    `<span>Вероятность: ${confidence}</span>`;
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
