const statusIndicator = document.getElementById('connection-status');
let ws = null;
let pollingInterval = null;
let seekDragging = {}; // track which sliders are being dragged

function toggleMode() {
    document.documentElement.classList.toggle('light');
    const isLight = document.documentElement.classList.contains('light');
    document.getElementById('mode-label').textContent = isLight ? 'Light' : 'Dark';
}

function renderZone(zoneData) {
    if (zoneData.zone_id !== 'main_floor') return;

    // Both cameras show the zone level aggregated state
    const cap = zoneData.capacity_max;
    const present = zoneData.current_occupancy;
    const remaining = zoneData.remaining_capacity;
    const entered = zoneData.entered_today;
    const exited = zoneData.exited_today;

    // Loop through cameras to update their specific stats
    if (zoneData.cameras) {
        zoneData.cameras.forEach(cam => {
            let prefix = null;
            if (cam.camera_id === 'cam_door_1') prefix = 'c1';
            else if (cam.camera_id === 'cam_room_1') prefix = 'c2';

            if (prefix) {
                // Update common stats for both roles
                const elCap = document.getElementById(`${prefix}-cap`);
                const elPresent = document.getElementById(`${prefix}-present`);
                const elRemaining = document.getElementById(`${prefix}-remaining`);
                
                if (elCap) elCap.textContent = cap;
                if (elPresent) elPresent.textContent = present;
                if (elRemaining) elRemaining.textContent = remaining;

                // Update role-specific stats
                // Update all stats unconditionally per user request
                const elEntered = document.getElementById(`${prefix}-entered`);
                const elExited = document.getElementById(`${prefix}-exited`);
                if (elEntered) elEntered.textContent = cam.entered_today || 0;
                if (elExited) elExited.textContent = cam.exited_today || 0;
                
                const elSitting = document.getElementById(`${prefix}-sitting`);
                const elStanding = document.getElementById(`${prefix}-standing`);
                if (elSitting) elSitting.textContent = cam.sitting || 0;
                if (elStanding) elStanding.textContent = cam.standing || 0;
            }
        });
    }

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

// Poll /cameras to update per-camera stale indicators
async function fetchCameraStatus() {
    try {
        const response = await fetch('/cameras');
        if (response.ok) {
            const cameras = await response.json();
            cameras.forEach(cam => {
                let indicatorId = null;
                if (cam.camera_id === 'cam_door_1') indicatorId = 'cam1-live';
                else if (cam.camera_id === 'cam_room_1') indicatorId = 'cam2-live';
                
                if (indicatorId) {
                    const indicator = document.getElementById(indicatorId);
                    if (indicator) {
                        if (cam.is_stale) {
                            indicator.innerHTML = '<i></i>Stale';
                            indicator.style.color = '#F2B84B'; // amber
                            indicator.querySelector('i').style.background = '#F2B84B';
                            indicator.querySelector('i').style.animation = 'none';
                        } else {
                            indicator.innerHTML = '<i></i>Live';
                            indicator.style.color = 'var(--green)';
                            indicator.querySelector('i').style.background = 'var(--green)';
                            indicator.querySelector('i').style.animation = 'pulse 1.8s infinite';
                        }
                    }
                }
            });
        }
    } catch(e) {}
}

setInterval(fetchCameraStatus, 5000);
fetchCameraStatus();

connectWebSocket();

// --- Multi-file Upload Logic --- lock role per slot
document.getElementById('video-files').addEventListener('change', (e) => {
  const container = document.getElementById('role-assign');
  container.innerHTML = '';
  const roles = ['both', 'both'];
  const roleLabels = ['All Features (CAM 1)', 'All Features (CAM 2)'];
  [...e.target.files].forEach((file, i) => {
    const role = roles[i] || 'entry_exit';
    const label = roleLabels[i] || `Role for file ${i+1}`;
    container.innerHTML += `
      <div style="display:flex; align-items:center; gap:10px;">
        <span style="font-family:'JetBrains Mono',monospace; font-size:12px;">${file.name}</span>
        <span style="background:var(--chip-amber-bg); color:var(--amber); font-family:'JetBrains Mono',monospace; font-size:11px; padding:3px 10px; border-radius:6px;">${label}</span>
        <input type="hidden" id="role-${i}" value="${role}">
      </div>`;
  });
});

async function uploadCameras() {
  const fileInput = document.getElementById('video-files');
  const files = fileInput.files;
  
  if (files.length === 0) {
      alert("Please select at least one video file.");
      return;
  }
  
  const formData = new FormData();

  for (let i = 0; i < files.length; i++) {
    formData.append('files', files[i]);
    formData.append('roles', document.getElementById(`role-${i}`).value);
  }

  try {
      const res = await fetch('/upload-cameras', { method: 'POST', body: formData });
      const result = await res.json();
      
      alert(`✅ Added ${result.cameras_added.length} camera(s). Processing started — check the dashboard for live updates!`);
  } catch (error) {
      alert(`Error uploading cameras: ${error}`);
  }
}

async function deleteCamera(cameraId) {
    if (!confirm(`Are you sure you want to delete ${cameraId}?`)) return;
    try {
        const res = await fetch(`/cameras/${cameraId}`, { method: 'DELETE' });
        if (res.ok) {
            alert('Camera deleted successfully.');
            window.location.reload();
        } else {
            alert('Failed to delete camera.');
        }
    } catch (error) {
        alert(`Error: ${error}`);
    }
}

async function togglePlay(cameraId, btnElement) {
    const isPaused = btnElement.innerText.trim() === '▶';
    const action = isPaused ? 'resume' : 'pause';
    try {
        const res = await fetch(`/cameras/${cameraId}/${action}`, { method: 'POST' });
        if (res.ok) {
            btnElement.innerText = isPaused ? '⏸' : '▶';
            btnElement.title = isPaused ? 'Pause' : 'Play';
        }
    } catch (e) {
        console.error("Playback toggle failed", e);
    }
}

async function restartCamera(cameraId) {
    // Resume if paused, then seek to 0
    const btn = document.querySelector(`[onclick="togglePlay('${cameraId}', this)"]`);
    if (btn && btn.innerText.trim() === '▶') {
        await togglePlay(cameraId, btn);
    }
    await seekVideo(cameraId, 0);
    const slider = document.getElementById(`seek-${cameraId}`);
    if (slider) slider.value = 0;
}

async function seekVideo(cameraId, percent) {
    try {
        await fetch(`/cameras/${cameraId}/seek?percent=${percent}`, { method: 'POST' });
    } catch (e) {
        console.error("Seek failed", e);
    }
}

// Auto-sync seek slider with actual video position
async function syncSeekBars() {
    for (const camId of ['cam_door_1', 'cam_room_1']) {
        const slider = document.getElementById(`seek-${camId}`);
        if (!slider || seekDragging[camId]) continue;
        try {
            const res = await fetch(`/cameras/${camId}/position`);
            if (res.ok) {
                const data = await res.json();
                slider.value = data.percent;
            }
        } catch (e) {}
    }
}
setInterval(syncSeekBars, 1000);

// Mark slider as dragging while user interacts
document.querySelectorAll('.seek-bar').forEach(slider => {
    slider.addEventListener('mousedown', () => {
        const id = slider.id.replace('seek-', '');
        seekDragging[id] = true;
    });
    slider.addEventListener('mouseup', () => {
        const id = slider.id.replace('seek-', '');
        setTimeout(() => { seekDragging[id] = false; }, 500);
    });
});
