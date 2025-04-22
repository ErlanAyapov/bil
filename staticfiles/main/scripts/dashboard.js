// fetch('https://unpkg.com/world-atlas/countries-50m.json')
//     .then((r) => r.json())
//     .then((data) => {
//       const countries = ChartGeo.topojson.feature(data, data.objects.countries).features;

//       new Chart(document.getElementById("chart").getContext("2d"), {
//         type: 'choropleth',
//         data: {
//           labels: countries.map((d) => d.properties.name),
//             datasets: [{
//             label: 'Countries',
//             data: countries.filter((d) => d.properties.name !== 'Antarctica')
//               .map((d) => ({
//               feature: d,
//               value: 0
//               }))
//           }]
//         },
//         options: {
//           responsive: true,
//           maintainAspectRatio: true,
//           showOutline: false,
//           showGraticule: false,
//           plugins: {
//             legend: { display: false }
//           },
//           scales: {
//             projection: {
//               axis: 'x',
//               projection: 'mercator',
//               display: false,
//               // Увеличиваем масштаб
//               scale: 500 // Увеличьте значение для большего масштаба
//             }
//           }
//         }
//     });
// });
 
new Chart(document.getElementById("traffic-chart").getContext("2d"), {
    type: 'line',
    data: {
        labels: Array.from({ length: 30 }, (_, i) => {
            const date = new Date();
            date.setDate(date.getDate() - (29 - i));
            return date.toISOString().split('T')[0]; // Format as YYYY-MM-DD
        }),
        datasets: [{
            label: 'Traffic Sources',
            data: Array(30).fill(0).map(() => Math.floor(Math.random() * 11)), // Example data
            borderColor: 'rgba(54, 235, 205, 0.81)',
            backgroundColor: 'rgba(54, 235, 205, 0.2)',
            fill: true
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
            legend: {
                display: false // Remove legend
            }
        },
        scales: {
            x: {
                display: false // Remove x-axis
            },
            y: {
                title: {
                    display: false,
                    text: 'Attack Type'
                },
                ticks: {
                    callback: function(value) {
                        const attackTypes = {
                            0: 'Benign',
                            1: 'Non-DDoS',
                            3: 'DDoS'
                        };
                        return attackTypes[value] || value;
                    }
                },
                beginAtZero: true
            }
        }
    }
});

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
  
  /* ----------  bootstrap  ---------- */
  document.addEventListener('DOMContentLoaded', () => {
    ActiveUsersMap.init({
      canvasId:'active-users-map',
      tableBodySelector:'#active-users-table tbody' 
    });
  
    // setTimeout(()=>ActiveUsersMap.update({}), 100);
  });
  