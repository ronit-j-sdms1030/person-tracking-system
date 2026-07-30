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

let cam1TrendChart = null;
let cam2TrendChart = null;
let maxPeakHeadcount = 0;

function createSingleChart(canvasId, color, bgColor) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Present Headcount',
                data: [],
                borderColor: color,
                backgroundColor: bgColor,
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
            plugins: { legend: { display: false } }
        }
    });
}

function initTrendCharts() {
    if (!cam1TrendChart) cam1TrendChart = createSingleChart('cam1TrendChart', '#3ECF8E', 'rgba(62, 207, 142, 0.12)');
    if (!cam2TrendChart) cam2TrendChart = createSingleChart('cam2TrendChart', '#38BDF8', 'rgba(56, 189, 248, 0.12)');
}

let lastRecordedMinute = null;
let cam1Samples = [];
let cam2Samples = [];
let totalHeadcountSum = 0;
let totalSampleCount = 0;
let peakTimeRecorded = "--:--";

function updateTrendCharts(c1Count, c2Count, totalPresent, cap) {
    initTrendCharts();
    
    const now = new Date();
    const minuteStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    cam1Samples.push(c1Count);
    cam2Samples.push(c2Count);
    totalHeadcountSum += totalPresent;
    totalSampleCount++;
    
    if (totalPresent > maxPeakHeadcount) {
        maxPeakHeadcount = totalPresent;
        peakTimeRecorded = minuteStr;
        const peakEl = document.getElementById('peak-headcount-val');
        if (peakEl) peakEl.textContent = maxPeakHeadcount;
        const peakTimeEl = document.getElementById('peak-time-val');
        if (peakTimeEl) peakTimeEl.textContent = peakTimeRecorded;
    }

    const avgHeadcount = (totalHeadcountSum / Math.max(1, totalSampleCount)).toFixed(1);
    const avgEl = document.getElementById('avg-headcount-val');
    if (avgEl) avgEl.textContent = avgHeadcount;

    if (cap && cap > 0) {
        const utilPct = Math.min(100, Math.round((totalPresent / cap) * 100));
        const utilEl = document.getElementById('utilization-rate-val');
        if (utilEl) utilEl.textContent = `${utilPct}%`;
    }

    if (lastRecordedMinute !== minuteStr) {
        lastRecordedMinute = minuteStr;
        
        const c1Avg = Math.round(cam1Samples.reduce((a, b) => a + b, 0) / Math.max(1, cam1Samples.length));
        const c2Avg = Math.round(cam2Samples.reduce((a, b) => a + b, 0) / Math.max(1, cam2Samples.length));
        cam1Samples = [];
        cam2Samples = [];
        
        if (cam1TrendChart) {
            if (cam1TrendChart.data.labels.length > 30) {
                cam1TrendChart.data.labels.shift();
                cam1TrendChart.data.datasets[0].data.shift();
            }
            cam1TrendChart.data.labels.push(minuteStr);
            cam1TrendChart.data.datasets[0].data.push(c1Avg);
            cam1TrendChart.update('none');
        }

        if (cam2TrendChart) {
            if (cam2TrendChart.data.labels.length > 30) {
                cam2TrendChart.data.labels.shift();
                cam2TrendChart.data.datasets[0].data.shift();
            }
            cam2TrendChart.data.labels.push(minuteStr);
            cam2TrendChart.data.datasets[0].data.push(c2Avg);
            cam2TrendChart.update('none');
        }
    }
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

    let c1Count = 0;
    let c2Count = 0;

    if (zoneData.cameras) {
        zoneData.cameras.forEach(cam => {
            if (cam.camera_id === 'cam_door_1') c1Count = cam.current_occupancy || 0;
            else if (cam.camera_id === 'cam_room_1') c2Count = cam.current_occupancy || 0;
        });
    }

    updateTrendCharts(c1Count, c2Count, present, cap);

    // Loop through cameras to update their specific stats
    if (zoneData.cameras) {
        zoneData.cameras.forEach((cam, idx) => {
            const prefix = `c${idx + 1}`;

            if (prefix) {
                // Update distinct stats specifically for this camera feed
                const camPresent = cam.current_occupancy !== undefined ? cam.current_occupancy : present;
                const camRemain = Math.max(0, cap - camPresent);

                const elCap = document.getElementById(`${prefix}-cap`);
                const elPresent = document.getElementById(`${prefix}-present`);
                const elRemaining = document.getElementById(`${prefix}-remaining`);
                
                if (elCap) elCap.textContent = cap;
                if (elPresent) elPresent.textContent = camPresent;
                if (elRemaining) elRemaining.textContent = camRemain;

                // Update summary bar elements for this specific camera
                const sumPresent = document.getElementById(`s-${prefix}-present`);
                const sumRemaining = document.getElementById(`s-${prefix}-remaining`);
                if (sumPresent) sumPresent.textContent = camPresent;
                if (sumRemaining) sumRemaining.textContent = camRemain;
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

let currentRenderedCameras = [];

function buildCameraCards(cameraList) {
    if (!cameraList || cameraList.length === 0) return;
    
    const camIds = cameraList.map(c => typeof c === 'string' ? c : c.camera_id);
    
    if (JSON.stringify(camIds) === JSON.stringify(currentRenderedCameras)) return;
    currentRenderedCameras = camIds;

    const grid = document.getElementById('cam-grid');
    if (!grid) return;

    let html = '';
    camIds.forEach((camId, i) => {
        const num = i + 1;
        html += `
        <div class="cam-card" data-cam="${num}">
          <div class="cam-video-col">
            <div class="cam-head">
              <div class="header" style="display:flex; justify-content:space-between; align-items:center; width:100%;">
                <h2 style="margin:0; font-family:'Space Grotesk',sans-serif; font-size:15px; display:flex; align-items:center; gap:8px;">CAM ${num} <span class="tag" style="font-size:11px; color:var(--muted); font-family:'JetBrains Mono',monospace;">(${camId})</span></h2>
                <div style="display:flex; align-items:center; gap:12px;">
                  <button onclick="deleteCamera('${camId}')" style="background:none; border:none; color:var(--red); cursor:pointer; font-size:16px;" title="Delete Feed">🗑️</button>
                  <div class="status-indicator" id="cam${num}-live" style="display:flex; align-items:center; gap:6px; font-size:11px; color:var(--green); font-family:'JetBrains Mono',monospace;">
                    <i style="width:6px;height:6px;border-radius:50%;background:var(--green);animation:pulse 1.8s infinite;"></i>
                    <span>Live</span>
                  </div>
                </div>
              </div>
            </div>
            <div class="video-panel">
              <div class="caption-tag">${camId} view</div>
              <img id="vid-${camId}" src="/video_feed/${camId}" data-src="/video_feed/${camId}" onerror="this.style.display='none'" onload="this.style.display='block'" style="width:100%; height:100%; object-fit:cover; display:none;" alt="CAM ${num} feed">
              <div class="playback-controls">
                <button onclick="togglePlay('${camId}', this)" class="ctrl-btn" title="Pause">⏸</button>
                <input type="range" class="seek-bar" id="seek-${camId}" min="0" max="100" value="0" oninput="seekVideo('${camId}', this.value)" title="Scrub Timeline">
                <button onclick="restartCamera('${camId}')" class="ctrl-btn" title="Restart">↺</button>
              </div>
            </div>
          </div>
          <div class="stats-col">
            <div class="stat-grid">
              <div class="chip" style="--chip-bg:var(--chip-blue-bg); --chip-color:var(--blue);"><div class="num" id="c${num}-cap">0</div><div class="lbl">Total cap.</div></div>
              <div class="chip" style="--chip-bg:var(--chip-green-bg); --chip-color:var(--green);"><div class="num" id="c${num}-present">0</div><div class="lbl">Present</div></div>
              <div class="chip" style="--chip-bg:var(--chip-amber-bg); --chip-color:var(--amber);"><div class="num" id="c${num}-remaining">0</div><div class="lbl">Remaining</div></div>
              <div class="chip c${num}-posture" style="--chip-bg:var(--chip-purple-bg); --chip-color:var(--purple);"><div class="num"><span id="c${num}-sitting">0</span><span style="font-size:13px; opacity:0.75; font-weight:500;">/<span id="c${num}-sitting-max">15</span></span></div><div class="lbl">Sitting (<span id="c${num}-sitting-rem">15</span> rem)</div></div>
            </div>
          </div>
        </div>`;
    });

    grid.innerHTML = html;

    grid.querySelectorAll('.seek-bar').forEach(slider => {
        slider.addEventListener('mousedown', () => {
            const id = slider.id.replace('seek-', '');
            seekDragging[id] = true;
        });
        slider.addEventListener('mouseup', () => {
            const id = slider.id.replace('seek-', '');
            setTimeout(() => { seekDragging[id] = false; }, 500);
        });
    });

    revealDashboardPanels(camIds.length);
}

function handleInitialState(data) {
    if (data.main_floor) {
        if (data.main_floor.cameras && data.main_floor.cameras.length > 0) {
            buildCameraCards(data.main_floor.cameras);
        }
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
            if (cameras && cameras.length > 0) {
                buildCameraCards(cameras);
            }
            cameras.forEach((cam, idx) => {
                let indicatorId = `cam${idx + 1}-live`;
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

  const uploadBtn = document.querySelector('.upload-panel button');
  if (uploadBtn) {
      uploadBtn.disabled = true;
      uploadBtn.textContent = "⏳ Uploading Video Feeds...";
  }

  try {
      const res = await fetch('/upload-cameras', { method: 'POST', body: formData });
      if (!res.ok) throw new Error(`Server returned HTTP ${res.status}`);
      const result = await res.json();
      
      alert(`✅ Successfully added ${result.cameras_added.length} camera feed(s)! Processing started.`);
      
      // Refresh video stream feeds
      setTimeout(() => {
          const v1 = document.getElementById('vid-cam_door_1');
          const v2 = document.getElementById('vid-cam_room_1');
          if (v1 && v1.dataset.src) v1.src = v1.dataset.src + "?t=" + new Date().getTime();
          if (v2 && v2.dataset.src) v2.src = v2.dataset.src + "?t=" + new Date().getTime();
      }, 500);
  } catch (error) {
      alert(`⚠️ Video Upload Notice: ${error.message || error}`);
  } finally {
      if (uploadBtn) {
          uploadBtn.disabled = false;
          uploadBtn.textContent = "Upload & Add";
      }
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

// --- Initial Camera Setup Wizard Logic ---
let wizardSelectedCount = 2;

function openCameraSetupWizard() {
    const wizard = document.getElementById('initial-setup-wizard');
    if (wizard) {
        wizard.style.display = 'block';
        wizard.scrollIntoView({ behavior: 'smooth' });
    }

    const selectBar = document.getElementById('cam-select-bar');
    const grid = document.getElementById('cam-grid');
    const summary = document.getElementById('summary-bar');
    const analytics = document.getElementById('analytics-panel');
    const seating = document.querySelector('.seating-plan-panel');
    const graphPanel = document.querySelector('.graph-panel');

    if (selectBar) selectBar.style.display = 'none';
    if (grid) grid.style.display = 'none';
    if (summary) summary.style.display = 'none';
    if (analytics) analytics.style.display = 'none';
    if (seating) seating.style.display = 'none';
    if (graphPanel) graphPanel.style.display = 'none';
}

function configureWizardSlots(count) {
    wizardSelectedCount = count;
    const badge = document.getElementById('wizard-slot-count-badge');
    const container = document.getElementById('wizard-slot-container');
    const inputsDiv = document.getElementById('wizard-slot-inputs');
    
    if (badge) badge.textContent = count;
    if (container) container.style.display = 'block';
    
    let html = '';
    for (let i = 1; i <= count; i++) {
        const slotName = i === 1 ? 'cam_door_1' : (i === 2 ? 'cam_room_1' : `cam_slot_${i}`);
        html += `
            <div style="background:var(--panel); border:1px solid var(--panel-border); border-radius:10px; padding:12px 14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:13px; color:var(--text);">Camera ${i} Slot</span>
                    <span style="font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--muted); font-weight:500;">(${slotName})</span>
                </div>
                <input type="file" id="wizard-file-${i}" accept="video/*" style="font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--text);">
            </div>`;
    }
    if (inputsDiv) inputsDiv.innerHTML = html;
}

async function submitWizardCameras() {
    const formData = new FormData();
    let fileAdded = false;
    
    for (let i = 1; i <= wizardSelectedCount; i++) {
        const fileInput = document.getElementById(`wizard-file-${i}`);
        if (fileInput && fileInput.files.length > 0) {
            const slotName = i === 1 ? 'cam_door_1' : (i === 2 ? 'cam_room_1' : `cam_slot_${i}`);
            formData.append('files', fileInput.files[0]);
            formData.append('roles', 'both');
            formData.append('slots', slotName);
            fileAdded = true;
        }
    }
    
    const capInput = document.getElementById('wizard-capacity-input');
    if (capInput && capInput.value) {
        formData.append('capacity', parseInt(capInput.value));
    }
    
    if (!fileAdded) {
        alert("Please choose a video file for your camera slots or click '⚡ Launch Sample Feeds'!");
        return;
    }
    
    const launchBtn = document.getElementById('wizard-launch-btn');
    if (launchBtn) {
        launchBtn.disabled = true;
        launchBtn.textContent = "⏳ Setting Up Cameras...";
    }
    
    try {
        const res = await fetch('/upload-cameras', { method: 'POST', body: formData });
        if (res.ok) {
            const result = await res.json();
            alert(`✅ Successfully configured and launched ${result.cameras_added.length} camera feed(s)!`);
            if (result.cameras_added) buildCameraCards(result.cameras_added);
            selectCam('both', document.querySelectorAll('.cam-select button')[wizardSelectedCount]);
        }
    } catch(e) {
        alert(`Notice: ${e}`);
    } finally {
        if (launchBtn) {
            launchBtn.disabled = false;
            launchBtn.textContent = "🚀 Confirm & Launch Cameras";
        }
    }
}

function revealDashboardPanels(cameraCount) {
    const wizard = document.getElementById('initial-setup-wizard');
    if (wizard) wizard.style.display = 'none';

    const selectBar = document.getElementById('cam-select-bar');
    const grid = document.getElementById('cam-grid');
    const summary = document.getElementById('summary-bar');
    const analytics = document.getElementById('analytics-panel');
    
    if (selectBar) selectBar.style.display = 'flex';
    if (grid) grid.style.display = 'grid';
    if (summary) summary.style.display = 'flex';
    if (analytics) analytics.style.display = 'block';

    // Build single-camera view navigation buttons for all configured cameras
    const selectDiv = document.getElementById('cam-select');
    if (selectDiv) {
        let navHTML = '';
        const count = cameraCount || 2;
        for (let i = 1; i <= count; i++) {
            navHTML += `<button class="${i === 1 ? 'active' : ''}" onclick="selectCam('${i}', this)">Cam ${i}</button>`;
        }
        navHTML += `<button onclick="selectCam('both', this)">Both / Grid (Pairs)</button>`;
        selectDiv.innerHTML = navHTML;
    }
}

function launchDemoSampleFeeds() {
    revealDashboardPanels(2);
    selectCam('both', document.querySelectorAll('.cam-select button')[2]);
}
