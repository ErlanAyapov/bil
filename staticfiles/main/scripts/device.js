const activeDevices = {};
const devices = [];


function buildCountryStats() {
    const stats = {};
    for (const [country, devices] of Object.entries(activeDevices)) {
        stats[country] = devices.length;
    }
    return stats;
}
function buildTrafficStats() {
    const trafficCounts = new Array(12).fill(0); // 12 типов трафика

    for (const devices of Object.values(activeDevices)) {
        for (const device of devices) {
            const t = parseInt(device.traffic);
            if (!isNaN(t) && t >= 0 && t < trafficCounts.length) {
                trafficCounts[t] += 1;
            }
        }
    }

    return trafficCounts;
}


// Класс для описания устройства
class Device {
    constructor(id, device_token, name, type, traffic, status, confidence, country) {
        this.id = id;
        this.name = name;
        this.type = type;
        this.traffic = traffic;
        this.status = status;
        this.confidence = confidence;
        this.device_token = device_token;
        this.country = country;
    }

    getInfo() {
        return `Device Name: ${this.name}, Device Type: ${this.type}`;
    }

    setTraffic(traffic, confidence) {
        this.traffic = traffic;
        this.confidence = confidence;

        // Инициализируем массив, если страны ещё нет
        if (!(this.country in activeDevices)) {
            activeDevices[this.country] = [];
        }

        // Проверяем, есть ли устройство с таким же ID уже в массиве
        const isAlreadyPresent = activeDevices[this.country].some(device => device.id === this.id);

        // Если нет — добавляем
        if (!isAlreadyPresent) {
            activeDevices[this.country].push(this);
        }
        const stats = buildCountryStats();
        ActiveUsersMap.update(stats);

        const trafficStats = buildTrafficStats();
        TrafficBarChart.update(trafficStats);
        TrafficRadarChart.update(trafficStats);
        TrafficRegionChart.update(stats);

    }

    setConfidence(confidence) {
        this.confidence = confidence;
    }
}


setTimeout(() => {
    dev1.setTraffic(50, 0.88); // ActiveUsersMap.update() вызовется автоматически
}, 3000);
