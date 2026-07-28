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
                if (cam.role === 'entry_exit' || cam.role === 'both') {
                    const elEntered = document.getElementById(`${prefix}-entered`);
                    const elExited = document.getElementById(`${prefix}-exited`);
                    if (elEntered) elEntered.textContent = cam.entered_today;
                    if (elExited) elExited.textContent = cam.exited_today;
                }
                
                if (cam.role === 'posture' || cam.role === 'both') {
                    const elSitting = document.getElementById(`${prefix}-sitting`);
                    const elStanding = document.getElementById(`${prefix}-standing`);
                    if (elSitting) elSitting.textContent = cam.sitting;
                    if (elStanding) elStanding.textContent = cam.standing;
                }
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

// --- Multi-file Upload Logic ---
document.getElementById('video-files').addEventListener('change', (e) => {
  const container = document.getElementById('role-assign');
  container.innerHTML = '';
  [...e.target.files].forEach((file, i) => {
    container.innerHTML += `
      <div style="display:flex; align-items:center; gap:10px;">
        <span style="font-family:'JetBrains Mono',monospace; font-size:12px;">${file.name}</span>
        <select id="role-${i}" style="background:var(--panel-2); color:var(--text); border:1px solid var(--panel-border); padding:4px 8px; border-radius:6px; font-family:'Inter',sans-serif;">
          <option value="entry_exit">Entry/Exit</option>
          <option value="posture">Posture</option>
        </select>
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
    formData.append('camera_ids', `cam_upload_${i + 1}`);
  }

  try {
      const res = await fetch('/upload-cameras', { method: 'POST', body: formData });
      const result = await res.json();
      alert(`Added ${result.cameras_added.length} camera(s). Restart the pipeline to pick them up.`);
  } catch (error) {
      alert(`Error uploading cameras: ${error}`);
  }
}
