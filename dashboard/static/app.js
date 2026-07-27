const statusIndicator = document.getElementById('connection-status');
let ws = null;
let pollingInterval = null;

function renderZone(zoneData) {
    if (zoneData.zone_id !== 'main_floor') return;

    // Doorway stats
    document.getElementById('door-in').textContent = zoneData.entered_today;
    document.getElementById('door-out').textContent = zoneData.exited_today;
    
    // Net is occupancy (entry/exit based)
    const net = zoneData.entered_today - zoneData.exited_today;
    const netEl = document.getElementById('door-net');
    netEl.textContent = (net >= 0 ? '+' : '') + net;
    netEl.style.color = net >= 0 ? '#E9EBF0' : '#F0553F'; // Optional styling for negative

    // Room stats
    const sit = zoneData.sitting_count;
    const stand = zoneData.standing_count;
    const totalPosture = sit + stand;
    
    document.getElementById('room-sit').textContent = sit;
    document.getElementById('room-stand').textContent = stand;

    const sitPct = totalPosture === 0 ? 0 : Math.round((sit / totalPosture) * 100);
    const standPct = totalPosture === 0 ? 0 : Math.round((stand / totalPosture) * 100);
    
    document.getElementById('bar-sit').style.width = sitPct + '%';
    document.getElementById('bar-stand').style.width = standPct + '%';
    
    document.getElementById('lbl-sit').textContent = 'sit ' + sitPct + '%';
    document.getElementById('lbl-stand').textContent = 'stand ' + standPct + '%';

    // Global Zone stats (Bottom summary)
    document.getElementById('total-occupancy').textContent = zoneData.current_occupancy;
    document.getElementById('capacity-max').textContent = '/' + zoneData.capacity_max;
    
    document.getElementById('total-remaining').textContent = zoneData.remaining_capacity;
    document.getElementById('total-entered').textContent = zoneData.entered_today;
    document.getElementById('total-exited').textContent = zoneData.exited_today;

    // Gauge calculation
    // Circle circumference is approx 201 (2 * PI * r where r=32 -> 2 * 3.14 * 32 = 201.06)
    const utilPct = zoneData.utilization_pct;
    const offset = 201 - (201 * Math.min(utilPct, 100) / 100);
    const ring = document.getElementById('util-ring');
    ring.style.strokeDashoffset = offset;

    let utilColor = '#3ECF8E'; // Comfortable
    let utilText = 'Comfortable · ' + utilPct + '%';
    let utilBg = 'rgba(62,207,142,0.14)';
    
    if (utilPct >= 90) {
        utilColor = '#F0553F'; // At capacity
        utilText = 'At capacity · ' + utilPct + '%';
        utilBg = 'rgba(240,85,63,0.14)';
    } else if (utilPct >= 70) {
        utilColor = '#F2B84B'; // Busy
        utilText = 'Busy · ' + utilPct + '%';
        utilBg = 'rgba(242,184,75,0.14)';
    }

    ring.style.stroke = utilColor;
    
    const badge = document.getElementById('util-badge');
    badge.textContent = utilText;
    badge.style.color = utilColor;
    badge.style.backgroundColor = utilBg;
}

function handleInitialState(data) {
    if (data.main_floor) {
        renderZone(data.main_floor);
    }
}

async function fetchStatus() {
    try {
        const response = await fetch('/status');
        if (response.ok) {
            const data = await response.json();
            handleInitialState(data);
            statusIndicator.textContent = "Polling";
            statusIndicator.style.color = "#F2B84B";
        }
    } catch (e) {
        statusIndicator.textContent = "Offline";
        statusIndicator.style.color = "#F0553F";
    }
}

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/live`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        statusIndicator.textContent = "Live";
        statusIndicator.style.color = "#3ECF8E";
        if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
        }
    };
    
    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "initial_state") {
            handleInitialState(msg.data);
        } else if (msg.type === "zone_update") {
            renderZone(msg.data);
        }
    };
    
    ws.onclose = () => {
        statusIndicator.textContent = "Reconnecting...";
        statusIndicator.style.color = "#F0553F";
        if (!pollingInterval) {
            pollingInterval = setInterval(fetchStatus, 3000);
            fetchStatus();
        }
        setTimeout(connectWebSocket, 5000);
    };
}

connectWebSocket();
