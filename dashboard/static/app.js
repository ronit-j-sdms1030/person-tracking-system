const container = document.getElementById('zones-container');
const statusIndicator = document.getElementById('connection-status');
let ws = null;
let pollingInterval = null;

function renderZone(zoneData) {
    let card = document.getElementById(`zone-${zoneData.zone_id}`);
    if (!card) {
        card = document.createElement('div');
        card.id = `zone-${zoneData.zone_id}`;
        card.className = 'zone-card';
        container.appendChild(card);
    }
    
    const utilColor = zoneData.utilization_pct > 90 ? '#f44336' : (zoneData.utilization_pct > 75 ? '#ff9800' : '#4caf50');
    
    card.innerHTML = `
        <h2 class="zone-title">${zoneData.zone_id}</h2>
        <div class="metric"><span class="metric-label">Occupancy:</span><span class="metric-val">${zoneData.current_occupancy}</span></div>
        <div class="metric"><span class="metric-label">Capacity Max:</span><span class="metric-val">${zoneData.capacity_max}</span></div>
        <div class="metric"><span class="metric-label">Remaining:</span><span class="metric-val">${zoneData.remaining_capacity}</span></div>
        <div class="metric"><span class="metric-label">Entered Today:</span><span class="metric-val">${zoneData.entered_today}</span></div>
        <div class="metric"><span class="metric-label">Exited Today:</span><span class="metric-val">${zoneData.exited_today}</span></div>
        <div class="metric"><span class="metric-label">Sitting:</span><span class="metric-val">${zoneData.sitting_count}</span></div>
        <div class="metric"><span class="metric-label">Standing:</span><span class="metric-val">${zoneData.standing_count}</span></div>
        <div class="metric"><span class="metric-label">Utilization:</span><span class="metric-val">${zoneData.utilization_pct}%</span></div>
        <div class="util-bar-bg">
            <div class="util-bar-fill" style="width: ${Math.min(zoneData.utilization_pct, 100)}%; background-color: ${utilColor};"></div>
        </div>
    `;
}

function handleInitialState(data) {
    for (const [zoneId, zoneData] of Object.entries(data)) {
        renderZone(zoneData);
    }
}

async function fetchStatus() {
    try {
        const response = await fetch('/status');
        if (response.ok) {
            const data = await response.json();
            handleInitialState(data);
            statusIndicator.textContent = "Connected (Polling)";
            statusIndicator.style.color = "#ff9800";
        }
    } catch (e) {
        statusIndicator.textContent = "Disconnected";
        statusIndicator.style.color = "#f44336";
    }
}

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/live`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        statusIndicator.textContent = "Connected (WebSocket)";
        statusIndicator.style.color = "#4caf50";
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
        statusIndicator.textContent = "WebSocket dropped. Falling back to polling...";
        statusIndicator.style.color = "#f44336";
        if (!pollingInterval) {
            pollingInterval = setInterval(fetchStatus, 3000);
            fetchStatus(); // immediate fetch
        }
        // Try to reconnect WS after 5s
        setTimeout(connectWebSocket, 5000);
    };
}

// Start
connectWebSocket();
