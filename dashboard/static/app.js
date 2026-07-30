const statusIndicator = document.getElementById('connection-status');
let ws = null;
let pollingInterval = null;
let seekDragging = {}; // track which sliders are being dragged

function toggleMode() {
    document.documentElement.classList.toggle('light');
    const isLight = document.documentElement.classList.contains('light');
    document.getElementById('mode-label').textContent = isLight ? 'Light' : 'Dark';
}

function syncTotalCap() {
    const sitVal = parseInt(document.getElementById('sitting-cap-input').value) || 0;
    const standVal = parseInt(document.getElementById('standing-cap-input').value) || 0;
    const totalEl = document.getElementById('total-cap-input');
    if (totalEl) totalEl.value = sitVal + standVal;
}

let trendChart = null;
let maxPeakHeadcount = 0;

function initTrendChart() {
    const ctx = document.getElementById('occupancyTrendChart');
    if (!ctx) return;
    
    trendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Present Headcount',
                data: [],
                borderColor: '#3ECF8E',
                backgroundColor: 'rgba(62, 207, 142, 0.12)',
                borderWidth: 2.5,
                fill: true,
                tension: 0.35,
                pointRadius: 3,
                pointHoverRadius: 5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#8890A0', font: { family: 'JetBrains Mono', size: 10 } }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#8890A0', font: { family: 'JetBrains Mono', size: 10 } }
                }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}

function updateTrendChart(present) {
    if (!trendChart) initTrendChart();
    if (!trendChart) return;
    
    if (present > maxPeakHeadcount) {
        maxPeakHeadcount = present;
        const peakEl = document.getElementById('peak-headcount-val');
        if (peakEl) peakEl.textContent = maxPeakHeadcount;
    }
    
    const nowStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    
    if (trendChart.data.labels.length > 25) {
        trendChart.data.labels.shift();
        trendChart.data.datasets[0].data.shift();
    }
    
    trendChart.data.labels.push(nowStr);
    trendChart.data.datasets[0].data.push(present);
    trendChart.update('none');
}

function renderZone(zoneData) {
    if (zoneData.zone_id !== 'main_floor') return;
    window.lastZoneData = zoneData;

    // Both cameras show the zone level aggregated state
    const cap = zoneData.capacity_max;
    const present = zoneData.current_occupancy;
    const remaining = zoneData.remaining_capacity;
    const entered = zoneData.entered_today;
    const exited = zoneData.exited_today;

    updateTrendChart(present);

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

                // Update posture stats from zoneData
                const elSitting = document.getElementById(`${prefix}-sitting`);
                const elStanding = document.getElementById(`${prefix}-standing`);
                if (elSitting) elSitting.textContent = zoneData.sitting_count !== undefined ? zoneData.sitting_count : (cam.sitting || 0);
                if (elStanding) elStanding.textContent = zoneData.standing_count !== undefined ? zoneData.standing_count : (cam.standing || 0);
            }
        });
    }

    const sittingMax = zoneData.capacity_sitting_max || 15;
    const standingMax = zoneData.capacity_standing_max || 10;
    const sittingRem = zoneData.remaining_sitting_capacity !== undefined ? zoneData.remaining_sitting_capacity : Math.max(0, sittingMax - (zoneData.sitting_count || 0));
    const standingRem = zoneData.remaining_standing_capacity !== undefined ? zoneData.remaining_standing_capacity : Math.max(0, standingMax - (zoneData.standing_count || 0));

    for (const prefix of ['c1', 'c2']) {
        const elSittingMax = document.getElementById(`${prefix}-sitting-max`);
        const elSittingRem = document.getElementById(`${prefix}-sitting-rem`);
        const elStandingMax = document.getElementById(`${prefix}-standing-max`);
        const elStandingRem = document.getElementById(`${prefix}-standing-rem`);
        
        if (elSittingMax) elSittingMax.textContent = sittingMax;
        if (elSittingRem) elSittingRem.textContent = sittingRem;
        if (elStandingMax) elStandingMax.textContent = standingMax;
        if (elStandingRem) elStandingRem.textContent = standingRem;
    }

    // Update summary bottom bar
    document.getElementById('s-c1-present').textContent = present;
    document.getElementById('s-c1-remaining').textContent = remaining;
    document.getElementById('s-c2-present').textContent = present;
    document.getElementById('s-c2-remaining').textContent = remaining;
    
    document.getElementById('s-total-occupancy').textContent = 'total ' + present;
    document.getElementById('s-total-entered').textContent = 'entered ' + entered;

    // Render Interactive Seating Plan Map
    const seatGrid = document.getElementById('seat-grid');
    const seatSummary = document.getElementById('seat-plan-summary');
    const seatProgressBar = document.getElementById('seat-progress-bar');
    
    if (seatGrid) {
        const sittingCount = zoneData.sitting_count || 0;
        const totalSeats = sittingMax;
        const pct = Math.round(Math.min(100, (sittingCount / totalSeats) * 100));
        
        if (seatSummary) seatSummary.textContent = `${sittingCount} / ${totalSeats} Seats Occupied (${pct}%)`;
        if (seatProgressBar) seatProgressBar.style.width = `${pct}%`;
        
        // Detect active video scene type to dynamically adapt seating layout map
        const activeCard = document.querySelector('.cam-card:not([style*="display: none"])');
        const activeCamTag = activeCard ? activeCard.querySelector('.caption-tag') : null;
        const activeCamText = activeCamTag ? activeCamTag.textContent.toLowerCase() : '';
        const activeVidSrc = activeCard && activeCard.querySelector('img') ? (activeCard.querySelector('img').src || '').toLowerCase() : '';

        let zones = [];
        if (activeVidSrc.includes('bus') || activeCamText.includes('bus')) {
            const sideCap = Math.max(1, Math.floor(totalSeats * 0.4));
            zones = [
                { name: "🚌 Left Aisle Seats", prefix: "L-Seat", count: sideCap },
                { name: "🚌 Right Aisle Seats", prefix: "R-Seat", count: sideCap },
                { name: "🚌 Rear Bench Seats", prefix: "Rear", count: Math.max(0, totalSeats - 2 * sideCap) }
            ];
        } else if (activeVidSrc.includes('university') || activeVidSrc.includes('lecture') || activeCamText.includes('classroom')) {
            const rowCap = Math.max(1, Math.floor(totalSeats * 0.35));
            zones = [
                { name: "🎓 Front Tier Row", prefix: "Front", count: rowCap },
                { name: "🎓 Middle Tier Row", prefix: "Mid", count: rowCap },
                { name: "🎓 Back Tier Row", prefix: "Back", count: Math.max(0, totalSeats - 2 * rowCap) }
            ];
        } else if (activeVidSrc.includes('metro') || activeCamText.includes('metro')) {
            const benchCap = Math.max(1, Math.floor(totalSeats * 0.5));
            zones = [
                { name: "🚆 Bench A (Left)", prefix: "BenchA", count: benchCap },
                { name: "🚆 Bench B (Right)", prefix: "BenchB", count: Math.max(0, totalSeats - benchCap) }
            ];
        } else {
            zones = [
                { name: "🛋️ Main Lounge Sofa", prefix: "Sofa", count: 3 },
                { name: "🪑 Foreground Lounge Chairs", prefix: "Chair", count: 2 },
                { name: "💻 Workstation Desks", prefix: "Desk", count: Math.max(0, totalSeats - 5) }
            ];
        }

        let seatCounter = 1;
        let layoutHTML = '';

        zones.forEach(z => {
            if (z.count <= 0) return;
            layoutHTML += `
                <div style="grid-column: 1 / -1; margin-top:8px; margin-bottom:2px;">
                    <div style="font-family:'Space Grotesk',sans-serif; font-size:12.5px; font-weight:700; color:var(--text); opacity:0.9;">${z.name}</div>
                </div>`;
                
            for (let k = 1; k <= z.count; k++) {
                const currentSeatIdx = seatCounter;
                const isOccupied = currentSeatIdx <= sittingCount;
                const seatLabel = `${z.prefix}-${k}`;
                seatCounter++;

                if (isOccupied) {
                    layoutHTML += `
                        <div class="seat-block occupied" style="background:linear-gradient(135deg, rgba(168,85,247,0.22), rgba(99,102,241,0.18)); border:1px solid rgba(168,85,247,0.7); border-radius:10px; padding:12px 8px; text-align:center; box-shadow:0 4px 14px rgba(168,85,247,0.18); transition:all 0.3s ease;">
                            <div style="font-family:'Space Grotesk',sans-serif; font-size:12px; font-weight:700; color:#E9D5FF; letter-spacing:0.02em;">${seatLabel}</div>
                            <div style="display:inline-flex; align-items:center; gap:4px; margin-top:5px; background:rgba(168,85,247,0.3); border:1px solid rgba(168,85,247,0.5); border-radius:12px; padding:2px 8px;">
                                <span style="width:5px; height:5px; border-radius:50%; background:#C084FC; display:inline-block;"></span>
                                <span style="font-family:'JetBrains Mono',monospace; font-size:8px; font-weight:700; color:#F3E8FF; text-transform:uppercase;">BUSY</span>
                            </div>
                        </div>`;
                } else {
                    layoutHTML += `
                        <div class="seat-block vacant" style="background:var(--panel-2); border:1px solid var(--panel-border); border-radius:10px; padding:12px 8px; text-align:center; transition:all 0.3s ease;">
                            <div style="font-family:'Space Grotesk',sans-serif; font-size:12px; font-weight:600; color:var(--muted); letter-spacing:0.02em;">${seatLabel}</div>
                            <div style="display:inline-flex; align-items:center; gap:4px; margin-top:5px; background:rgba(255,255,255,0.04); border:1px solid var(--panel-border); border-radius:12px; padding:2px 8px;">
                                <span style="width:5px; height:5px; border-radius:50%; background:var(--muted); opacity:0.5; display:inline-block;"></span>
                                <span style="font-family:'JetBrains Mono',monospace; font-size:8px; font-weight:600; color:var(--muted); text-transform:uppercase;">OPEN</span>
                            </div>
                        </div>`;
                }
            }
        });

        seatGrid.innerHTML = layoutHTML;
    }
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

function syncTotalCap() {
  const sit = parseInt(document.getElementById('sitting-cap-input').value) || 0;
  const stand = parseInt(document.getElementById('standing-cap-input').value) || 0;
  document.getElementById('total-cap-input').value = sit + stand;
}

// --- Multi-file Upload Logic --- lock role per slot
document.getElementById('video-files').addEventListener('change', (e) => {
  const container = document.getElementById('role-assign');
  container.innerHTML = '';
  [...e.target.files].forEach((file, i) => {
    // Default to Camera 1 for first file, Camera 2 for second file
    const defaultSlot = (i === 0) ? 'cam_door_1' : 'cam_room_1';
    container.innerHTML += `
      <div style="display:flex; align-items:center; gap:10px; margin-bottom:8px;">
        <span style="font-family:'JetBrains Mono',monospace; font-size:12px; min-width:120px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${file.name}</span>
        <select id="slot-${i}" style="background:var(--panel-2); color:var(--text); border:1px solid var(--panel-border); padding:4px 8px; border-radius:6px; font-family:'JetBrains Mono',monospace; font-size:11px;">
          <option value="cam_door_1" ${defaultSlot === 'cam_door_1' ? 'selected' : ''}>Assign to Camera 1</option>
          <option value="cam_room_1" ${defaultSlot === 'cam_room_1' ? 'selected' : ''}>Assign to Camera 2</option>
        </select>
        <span style="background:var(--chip-amber-bg); color:var(--amber); font-family:'JetBrains Mono',monospace; font-size:11px; padding:3px 10px; border-radius:6px;">All Features</span>
        <input type="hidden" id="role-${i}" value="both">
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
    formData.append('slots', document.getElementById(`slot-${i}`).value);
  }

  const totalCapEl = document.getElementById('total-cap-input');
  const sittingCapEl = document.getElementById('sitting-cap-input');
  const standingCapEl = document.getElementById('standing-cap-input');

  if (totalCapEl && totalCapEl.value) {
      formData.append('capacity', parseInt(totalCapEl.value));
  }
  if (sittingCapEl && sittingCapEl.value) {
      formData.append('capacity_sitting', parseInt(sittingCapEl.value));
  }
  if (standingCapEl && standingCapEl.value) {
      formData.append('capacity_standing', parseInt(standingCapEl.value));
  }

  try {
      const res = await fetch('/upload-cameras', { method: 'POST', body: formData });
      const result = await res.json();
      
      alert(`✅ Added ${result.cameras_added.length} camera(s). Processing started — check the dashboard for live updates!`);
      
      // Refresh video streams to ensure they reconnect after a stale upload
      setTimeout(() => {
          document.getElementById('vid-cam_door_1').src = document.getElementById('vid-cam_door_1').dataset.src + "?t=" + new Date().getTime();
          document.getElementById('vid-cam_room_1').src = document.getElementById('vid-cam_room_1').dataset.src + "?t=" + new Date().getTime();
      }, 500);
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

async function resetData() {
    if (!confirm("Are you sure you want to hard reset all cameras and metrics?")) return;
    try {
        const res = await fetch('/reset', { method: 'POST' });
        if (res.ok) {
            window.location.reload();
        }
    } catch (e) {
        console.error("Reset failed", e);
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
