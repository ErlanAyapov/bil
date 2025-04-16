fetch('https://unpkg.com/world-atlas/countries-50m.json')
    .then((r) => r.json())
    .then((data) => {
      const countries = ChartGeo.topojson.feature(data, data.objects.countries).features;

      new Chart(document.getElementById("chart").getContext("2d"), {
        type: 'choropleth',
        data: {
          labels: countries.map((d) => d.properties.name),
            datasets: [{
            label: 'Countries',
            data: countries.filter((d) => d.properties.name !== 'Antarctica')
              .map((d) => ({
              feature: d,
              value: 0
              }))
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          showOutline: false,
          showGraticule: false,
          plugins: {
            legend: { display: false }
          },
          scales: {
            projection: {
              axis: 'x',
              projection: 'mercator',
              display: false,
              // Увеличиваем масштаб
              scale: 500 // Увеличьте значение для большего масштаба
            }
          }
        }
    });
});
 
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
