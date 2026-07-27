const statusIndicator = document.getElementById('connection-status');
let ws = null;
let pollingInterval = null;

function renderZone(zoneData) {
    if (zoneData.zone_id !== 'main_floor') return;

    // Both cameras show the zone level aggregated state
    const cap = zoneData.capacity_max;
    const present = zoneData.current_occupancy;
    const remaining = zoneData.remaining_capacity;
    const entered = zoneData.entered_today;
    const exited = zoneData.exited_today;

    // Update Cam 1 stats
    document.getElementById('c1-cap').textContent = cap;
    document.getElementById('c1-present').textContent = present;
    document.getElementById('c1-remaining').textContent = remaining;
    document.getElementById('c1-entered').textContent = entered;
    document.getElementById('c1-exited').textContent = exited;

    // Update Cam 2 stats
    document.getElementById('c2-cap').textContent = cap;
    document.getElementById('c2-present').textContent = present;
    document.getElementById('c2-remaining').textContent = remaining;
    document.getElementById('c2-entered').textContent = entered;
    document.getElementById('c2-exited').textContent = exited;

    // Update summary bottom bar
    document.getElementById('s-c1-present').textContent = present;
    document.getElementById('s-c1-remaining').textContent = remaining;
    document.getElementById('s-c2-present').textContent = present;
    document.getElementById('s-c2-remaining').textContent = remaining;
    
    document.getElementById('s-total-occupancy').textContent = 'total ' + present;
    document.getElementById('s-total-entered').textContent = 'entered ' + entered;
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
