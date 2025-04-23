function updateModelDescription(model) {
    const descBlock = document.getElementById('model-description');
    const descriptions = {
    cnn: `
        <h5 class="text-primary mb-1">CNN — 1-D Convolutional Net</h5>
        <p class="mb-1">Две 1-D&nbsp;свёртки по&nbsp;64 фильтра +&nbsp;BatchNorm/Dropout, затем свёртка 128&nbsp;фильтров, MaxPool &amp; GlobalAveragePooling.</p>
        <p class="mb-1">Создана для извлечения локальных паттернов в потоках сетевых пакетов и даёт баланс между точностью и скоростью на Raspberry Pi.</p>
        <p> Расчётная время обучения на раунд — 4 минут 10 секунд.</p>
        `,
        
    dnn: `
        <h5 class="text-primary mb-1">DNN — 64-64-32 Fully-Connected</h5>
        <p class="mb-1">Три полносвязных слоя (64 → 64 → 32) c ReLU, лёгкая по параметрам и быстрее всех обучается на CPU.</p>
        <p class="mb-0">Подходит, когда признаки уже «плоские» и главная цель — низкие задержки инференса на edge-устройстве.</p>
        <p> Расчётная время обучения на раунд —   30 секунд.</p>`,

    cnn_bilstm: `
        <h5 class="text-primary mb-1">CNN + BiLSTM — Hybrid</h5>
        <p class="mb-1">Свёртки 32 → 64 фильтра для локальных признаков, далее двунаправленные LSTM (64&nbsp;→ 16) для учёта долгосрочных зависимостей.</p>
        <p class="mb-1">Лучше всего ловит сложные аномалии в трафике, когда порядок пакетов критичен; цена — самая тяжёлая модель и дольше всего учится.</p>
        <p> Расчётная время обучения на раунд —   9 минут 18 секунд.</p>`
};


    descBlock.innerHTML = descriptions[model] || '<p class="text-danger">Нет описания для выбранной модели.</p>';
}
const TrainingProgressChart = (() => {
    let chart = null;

    function init(roundsMax = 10) {
        const ctx = document.getElementById('training-progress-chart').getContext('2d');
        const labels = Array.from({ length: roundsMax }, (_, i) => i + 1);
        const data = {
            labels,
            datasets: [{
                label: 'Точность по раундам',
                data: [],
                fill: false,
                borderColor: 'rgba(54, 162, 235, 1)',
                backgroundColor: 'rgba(54, 162, 235, 0.2)',
                tension: 0.2,
                pointRadius: 3
            }]
        };
        chart = new Chart(ctx, {
            type: 'line',
            data: data,
            options: {
                responsive: true,
                animation: false,
                scales: {
                    x: {
                        title: {
                            display: true,
                            text: 'Раунд'
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'Точность'
                        },
                        beginAtZero: true,
                        suggestedMax: 1
                    }
                }
            }
        });
    }

    function addAccuracyPoint(round, accuracy) {
        if (!chart) return;
        chart.data.datasets[0].data[round - 1] = accuracy;
        chart.update();
    }

    function reset(roundsMax) {
        if (!chart) return;
        chart.data.labels = Array.from({ length: roundsMax }, (_, i) => i + 1);
        chart.data.datasets[0].data = [];
        chart.update();
    }

    function updateRounds(roundsMax) {
        if (!chart) return;
        chart.data.labels = Array.from({ length: roundsMax }, (_, i) => i + 1);
        chart.update();
    }
    return {
        init,
        addAccuracyPoint,
        reset,
        updateRounds
    };
})();
TrainingProgressChart.init(10);