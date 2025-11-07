(() => {
  function fetchJSON(url) {
    return fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } }).then(r => r.json());
  }

  function renderLineChart(canvasId, labels, values, label, color) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    return new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label,
          data: values,
          fill: false,
          borderColor: color,
          backgroundColor: color,
          tension: 0.25,
          pointRadius: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: true } },
        scales: { x: { ticks: { autoSkip: true } }, y: { beginAtZero: true } }
      }
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    const id = window.DEVICE_ID;
    if (!id) return;
    fetchJSON(`/device/${id}/activity/`).then(data => {
      const perDay = data.per_day || { labels: [], values: [] };
      renderLineChart('device-activity-per-day', perDay.labels, perDay.values, 'События/день', 'rgba(54,162,235,1)');

      const rounds = data.rounds || { labels: [], accuracy: [], loss: [] };
      renderLineChart('device-rounds-accuracy', rounds.labels, rounds.accuracy, 'Точность (val_accuracy)', 'rgba(75,192,192,1)');
      renderLineChart('device-rounds-loss', rounds.labels, rounds.loss, 'Потери (val_loss)', 'rgba(255,99,132,1)');
    }).catch(err => console.error('Failed to load device activity', err));
  });
})();

