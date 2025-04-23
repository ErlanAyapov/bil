
const labels = {
  0: "Benign",
  1: "Non DDoS",
  2: "DDoS icmp flood",
  3: "DDoS UDP flood",
  4: "DDoS TCP flood",
  5: "DDoS PSHACK",
  6: "DDoS Syn flood",
  7: "DDoS RSTFN flood",
  8: "DDoS Synonymousip flood",
  9: "DDoS ICMP fragmentation",
  10: "DDoS UDP fragmentation",
  11: "DDoS ACK Fragmentation",
};

const backgroundColors = [
  '#008080', '#3cb44b', '#ffe119', '#4363d8', '#f58231',
  '#911eb4', '#46f0f0', '#f032e6', '#bcf60c', '#fabebe',
  '#e6194b', '#e6beff'
];
const borderColors = backgroundColors.map(color => color.replace(')', ', 1)').replace('rgb', 'rgba'));

const TrafficBarChart = (() => {

  let chart;

  function init(initialCounts = []) {
    const ctx = document.getElementById("traffic-chart").getContext("2d");

    chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: Object.values(labels),
        datasets: [{
          label: 'Traffic Type Counts',
          data: initialCounts,
          backgroundColor: backgroundColors.map(c => c + '80'),
          borderColor: borderColors,
          borderWidth: 2,
          borderRadius: Number.MAX_VALUE,
          borderSkipped: false
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: {
            display: false
          },
          title: {
            display: true,
            text: 'DDoS Traffic Type Distribution (with Colors)'
          }
        },
        scales: {
          x: {
            title: {
              display: true,
              text: 'Traffic Type'
            },
            ticks: {
              autoSkip: false,
              maxRotation: 45,
              minRotation: 45
            }
          },
          y: {
            beginAtZero: true,
            title: {
              display: true,
              text: 'Count'
            }
          }
        }
      }
    });
  }

  function update(newCounts = []) {
    if (!chart) {
      init(newCounts); // auto-init if not initialized
    } else {
      chart.data.datasets[0].data = newCounts;
      chart.update();
    }
  }

  return {
    init,
    update
  };
})();
 
const TrafficRadarChart = (() => {
  const labels = {
    0: "Benign",
    1: "Non DDoS",
    2: "DDoS icmp flood",
    3: "DDoS UDP flood",
    4: "DDoS TCP flood",
    5: "DDoS PSHACK",
    6: "DDoS Syn flood",
    7: "DDoS RSTFN flood",
    8: "DDoS Synonymousip flood",
    9: "DDoS ICMP fragmentation",
    10: "DDoS UDP fragmentation",
    11: "DDoS ACK Fragmentation",
  };

  const radarColor = 'rgba(75, 192, 192, 0.2)';
  const radarBorderColor = 'rgba(75, 192, 192, 1)';

  let chart;

  function init(initialData = []) {
    const ctx = document.getElementById("traffic-by-radar").getContext("2d");

    chart = new Chart(ctx, {
      type: 'radar',
      data: {
        labels: Object.values(labels),
        datasets: [{
          label: 'Traffic Type Count',
          data: initialData,
          backgroundColor: radarColor,
          borderColor: radarBorderColor,
          pointBackgroundColor: radarBorderColor,
          pointBorderColor: '#fff',
          pointHoverBackgroundColor: '#fff',
          pointHoverBorderColor: radarBorderColor
        }]
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            position: 'top'
          },
          title: {
            display: true,
            text: 'Radar Chart of Traffic Types'
          }
        },
        scales: {
          r: {
            angleLines: {
              display: true
            },
            suggestedMin: 0,
            suggestedMax: 100
          }
        }
      }
    });
  }

  function update(newData = []) {
    if (!chart) {
      init(newData); // fallback init
    } else {
      chart.data.datasets[0].data = newData;
      chart.update();
    }
  }

  return {
    init,
    update
  };
})();

const ActiveUsersMap = (() => {
    let chart, countriesTopo, tableBody;
  
    /* ----------  init  ---------- */
    async function init(opts) {
      tableBody = document.querySelector(opts.tableBodySelector);
  
      /* 1. topojson */
      const topo = await fetch('https://unpkg.com/world-atlas/countries-50m.json')
                          .then(r => r.json());
      countriesTopo = ChartGeo.topojson
                     .feature(topo, topo.objects.countries)
                     .features.filter(f => f.properties.name !== 'Antarctica');
  
      /* 2. карта */
      chart = new Chart(
        document.getElementById(opts.canvasId).getContext('2d'),
        makeChartConfig([], topo)
      );
  
      /* 3. первичная заливка */
      update(opts.initialData || {});
    }
  
    /* ----------  update  ---------- */
    function update(stats) {
      const data = countriesTopo.map(f => ({
        feature: f,
        value  : stats[f.properties.name] || 0
      }));
      chart.data.datasets[0].data = data;
      chart.update();                      // перерисовать
  
      /* таблица */
      tableBody.innerHTML = Object.entries(stats)
        .sort((a,b) => b[1]-a[1])
        .map(([c,v]) => `<tr><td>${c}</td><td class="text-end">${v}</td></tr>`)
        .join('');
    }
  
    /* ----------  конфиг  ---------- */
    function makeChartConfig(initial, topo) {
      return {
        type : 'choropleth',
        data : { datasets:[{
          data      : initial,
          outline   : ChartGeo.topojson.mesh(topo, topo.objects.countries, (a,b)=>a===b),
          backgroundColor: ctx =>
              ctx.raw && ctx.raw.value > 0 ? 'rgba(54,162,235,.8)' : 'rgba(255,255,255,.05)',
          borderColor:'#444', borderWidth:.2,
        }]},
        options:{
          responsive:true, maintainAspectRatio:false,
          
  
          /* ==== интерактивность ==== */
          plugins:{
            legend : { display:false },
            tooltip:{ enabled:true,
              callbacks:{
                label: ctx =>
                  `${ctx.raw.feature.properties.name}: ${ctx.raw.value}`
              }
            }
          },
          hover:{
            mode:'nearest', intersect:true,
            onHover(_, els){
              chart.canvas.style.cursor = els.length ? 'pointer' : 'default';
            }
          },
  
          scales:{
            projection:{ axis:'x', projection:'mercator', padding:0 }
          }
        }
      };
    }
  
    return { init, update };
  })();

const TrafficRegionChart = (() => {
    let chart;
  
    const defaultColors = [
      '#ff6384', '#36a2eb', '#ffce56', '#4bc0c0', '#9966ff',
      '#ff9f40', '#c9cbcf', '#ff6666', '#66ff66', '#6666ff'
    ];
  
    function init(regionLabels = [], regionData = [], regionColors = defaultColors) {
      const ctx = document.getElementById("traffic-by-region").getContext("2d");
  
      chart = new Chart(ctx, {
        type: 'doughnut',
        data: {
          labels: regionLabels,
          datasets: [{
            label: 'Traffic by Region',
            data: regionData,
            backgroundColor: regionColors,
            borderColor: '#ffffff',
            borderWidth: 2
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          aspectRatio: 2.5,
          plugins: {
            legend: {
              position: 'right'
            },
            title: {
              display: true,
              text: 'Traffic Distribution by Region (Countries)'
            },
            tooltip: {
              callbacks: {
                label: function(context) {
                  const label = context.label || '';
                  const value = context.parsed || 0;
                  return `${label}: ${value} events`;
                }
              }
            }
          }
        }
      });
    }
  
    function update(regionStats = {}) {
      if (!chart) {
        const labels = Object.keys(regionStats);
        const data = Object.values(regionStats);
        init(labels, data); // fallback
        return;
      }
  
      chart.data.labels = Object.keys(regionStats);
      chart.data.datasets[0].data = Object.values(regionStats);
      chart.update();
    }
  
    return {
      init,
      update
    };
})();

document.addEventListener('DOMContentLoaded', () => {
    ActiveUsersMap.init({
      canvasId:'active-users-map',
      tableBodySelector:'#active-users-table tbody' 
    });
    const initialCounts = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
    TrafficBarChart.init(initialCounts);
    TrafficRadarChart.init(initialCounts);
    TrafficRegionChart.init();

});