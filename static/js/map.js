/**
 * map.js — All-India Traffic Navigator & Route Recommendation Engine
 * Handles real location geocoding, OSRM road geometry, traffic density rendering,
 * and AI alternate route suggestions across India.
 */

// Global State
let currentRouteMode = 'india';

// India Navigator State
let indiaMap = null;
let indiaLayers = [];
let selectedOriginCoords = [12.9176, 77.6238]; // Default: Central Silk Board, Bengaluru
let selectedDestCoords = [12.9855, 77.7317];   // Default: Whitefield ITPL, Bengaluru
let mapClickCounter = 0;

// Abstract Lab State
let routeMap = null;
let routeLayers = [];

// Vehicle Mission Mode (ambulance / delivery / commute)
let selectedRouteVehicleMode = 'commute';

function setRouteVehicleMode(mode) {
  selectedRouteVehicleMode = mode;
  ['routeModeAmbulance', 'routeModeDelivery', 'routeModeCommute'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.classList.remove('active', 'btn-primary');
      el.classList.add('btn-secondary');
    }
  });

  const activeBtn = document.getElementById(
    mode === 'ambulance' ? 'routeModeAmbulance' : (mode === 'delivery' ? 'routeModeDelivery' : 'routeModeCommute')
  );
  if (activeBtn) {
    activeBtn.classList.remove('btn-secondary');
    activeBtn.classList.add('active', 'btn-primary');
  }

  const findBtn = document.getElementById('indiaFindBtn');
  if (findBtn) {
    if (mode === 'ambulance') {
      findBtn.textContent = '🚑 Find Emergency Green Corridor (Clear Bottlenecks)';
    } else if (mode === 'delivery') {
      findBtn.textContent = '🛵 Find Express Delivery Bypass (Beat Deadline)';
    } else {
      findBtn.textContent = '🚦 Analyze Traffic & Recommend Alternate Route';
    }
  }

  analyzeIndiaRoutes();
}

// ────────────────────────── Mode Switching ──────────────────────────────────

function switchRouteMode(mode) {
  currentRouteMode = mode;
  const tabIndia = document.getElementById('tabBtnIndia');
  const tabLab   = document.getElementById('tabBtnLab');
  const secIndia = document.getElementById('indiaRouteSection');
  const secLab   = document.getElementById('labRouteSection');

  if (mode === 'india') {
    tabIndia.classList.add('active');
    tabLab.classList.remove('active');
    secIndia.style.display = 'block';
    secLab.style.display = 'none';
    setTimeout(() => {
      if (indiaMap) indiaMap.invalidateSize();
      else initIndiaMap();
    }, 100);
  } else {
    tabLab.classList.add('active');
    tabIndia.classList.remove('active');
    secLab.style.display = 'block';
    secIndia.style.display = 'none';
    setTimeout(() => {
      if (routeMap) routeMap.invalidateSize();
      else initRouteMap();
    }, 100);
  }
}

// ───────────────────── All-India Map Initialization ─────────────────────────

function initIndiaMap() {
  if (indiaMap) return;

  indiaMap = L.map('indiaRouteMap', {
    center: [12.95, 77.68], // Center around Bengaluru by default
    zoom: 12
  });

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors | OSRM Driving Engine',
    maxZoom: 18
  }).addTo(indiaMap);

  // Click on map to pick Start & End locations in India
  indiaMap.on('click', function(e) {
    const lat = parseFloat(e.latlng.lat.toFixed(5));
    const lon = parseFloat(e.latlng.lng.toFixed(5));

    if (mapClickCounter % 2 === 0) {
      selectedOriginCoords = [lat, lon];
      document.getElementById('indiaOriginInput').value = `Selected Point (${lat}, ${lon})`;
      document.getElementById('originCoordsBadge').textContent = `Coords: ${lat}, ${lon}`;
      showQuickNotification(`📍 Origin set to ${lat}, ${lon}`);
    } else {
      selectedDestCoords = [lat, lon];
      document.getElementById('indiaDestInput').value = `Selected Point (${lat}, ${lon})`;
      document.getElementById('destCoordsBadge').textContent = `Coords: ${lat}, ${lon}`;
      showQuickNotification(`🏁 Destination set to ${lat}, ${lon}`);
      // Auto analyze when both are clicked
      analyzeIndiaRoutes();
    }
    mapClickCounter++;
  });
}

function showQuickNotification(msg) {
  const existing = document.getElementById('mapToast');
  if (existing) existing.remove();
  const toast = document.createElement('div');
  toast.id = 'mapToast';
  toast.style.cssText = 'position:absolute; bottom:15px; left:50%; transform:translateX(-50%); background:rgba(15,23,42,0.9); color:#38bdf8; padding:6px 14px; border-radius:20px; font-size:0.8rem; font-weight:600; border:1px solid #38bdf8; z-index:1000; pointer-events:none; box-shadow:0 4px 12px rgba(0,0,0,0.5);';
  toast.textContent = msg;
  document.getElementById('indiaRouteMap').appendChild(toast);
  setTimeout(() => toast.remove(), 2500);
}

// ───────────────────── Load Corridor Presets ────────────────────────────────

async function loadCorridorChips() {
  try {
    const res = await fetch('/api/india-corridors');
    const data = await res.json();
    const list = document.getElementById('corridorChipsList');
    if (!list) return;

    list.innerHTML = data.corridors.map((c, i) => `
      <div class="corridor-chip ${i === 0 ? 'active' : ''}" 
           onclick="selectCorridor('${c.id}')" id="chip_${c.id}">
        <strong>${c.city}:</strong> ${c.title}
      </div>
    `).join('');

    window._INDIAN_CORRIDORS = data.corridors;
  } catch (err) {
    console.error('Failed to load Indian corridors:', err);
  }
}

function selectCorridor(corridorId) {
  if (!window._INDIAN_CORRIDORS) return;
  const c = window._INDIAN_CORRIDORS.find(item => item.id === corridorId);
  if (!c) return;

  // Highlight chip
  document.querySelectorAll('.corridor-chip').forEach(el => el.classList.remove('active'));
  const activeChip = document.getElementById('chip_' + corridorId);
  if (activeChip) activeChip.classList.add('active');

  // Update inputs
  document.getElementById('indiaOriginInput').value = c.origin_name;
  document.getElementById('indiaDestInput').value = c.dest_name;
  selectedOriginCoords = c.origin_coords;
  selectedDestCoords = c.dest_coords;

  document.getElementById('originCoordsBadge').textContent = `Coords: ${c.origin_coords.join(', ')}`;
  document.getElementById('destCoordsBadge').textContent = `Coords: ${c.dest_coords.join(', ')}`;

  // Run analysis immediately
  analyzeIndiaRoutes();
}

// ───────────────────── Location Search & Autocomplete ───────────────────────

async function searchLocation(targetType) {
  const inputId = targetType === 'origin' ? 'indiaOriginInput' : 'indiaDestInput';
  const autoId  = targetType === 'origin' ? 'originAutocomplete' : 'destAutocomplete';
  const query   = document.getElementById(inputId).value.trim();
  const autoBox = document.getElementById(autoId);

  if (!query) return;

  autoBox.innerHTML = '<div class="autocomplete-item text-muted">Searching Indian locations…</div>';
  autoBox.style.display = 'block';

  try {
    const res = await fetch(`/api/india-geocode?q=${encodeURIComponent(query)}`);
    const data = await res.json();

    if (!data.results || data.results.length === 0) {
      autoBox.innerHTML = '<div class="autocomplete-item text-muted">No locations found. Try specifying city name (e.g. "Connaught Place, Delhi").</div>';
      return;
    }

    autoBox.innerHTML = data.results.map(r => `
      <div class="autocomplete-item" onclick="chooseLocation('${targetType}', '${r.display_name.replace(/'/g, "\\'")}', ${r.lat}, ${r.lon})">
        📍 <strong>${r.display_name.split(',')[0]}</strong>
        <div class="text-xs text-muted" style="margin-top:2px;">${r.display_name}</div>
      </div>
    `).join('');
  } catch (err) {
    autoBox.innerHTML = `<div class="autocomplete-item text-muted">Search error: ${err.message}</div>`;
  }
}

function chooseLocation(targetType, name, lat, lon) {
  const inputId = targetType === 'origin' ? 'indiaOriginInput' : 'indiaDestInput';
  const autoId  = targetType === 'origin' ? 'originAutocomplete' : 'destAutocomplete';
  const badgeId = targetType === 'origin' ? 'originCoordsBadge' : 'destCoordsBadge';

  document.getElementById(inputId).value = name;
  document.getElementById(badgeId).textContent = `Coords: ${lat.toFixed(4)}, ${lon.toFixed(4)}`;
  document.getElementById(autoId).style.display = 'none';

  if (targetType === 'origin') {
    selectedOriginCoords = [lat, lon];
  } else {
    selectedDestCoords = [lat, lon];
  }

  if (indiaMap) {
    indiaMap.setView([lat, lon], 13);
  }
}

// Close autocomplete on click outside
document.addEventListener('click', function(e) {
  if (!e.target.closest('#originAutocomplete') && !e.target.closest('#indiaOriginInput')) {
    const el = document.getElementById('originAutocomplete');
    if (el) el.style.display = 'none';
  }
  if (!e.target.closest('#destAutocomplete') && !e.target.closest('#indiaDestInput')) {
    const el = document.getElementById('destAutocomplete');
    if (el) el.style.display = 'none';
  }
});

// ───────────────────── Analyze India Traffic & Recommend Routes ─────────────

async function analyzeIndiaRoutes() {
  initIndiaMap();

  const originName = document.getElementById('indiaOriginInput').value.trim() || 'Origin, India';
  const destName   = document.getElementById('indiaDestInput').value.trim() || 'Destination, India';
  const hour       = parseInt(document.getElementById('indiaHour').value);
  const dow        = parseInt(document.getElementById('indiaDay').value);
  const weather    = parseInt(document.getElementById('indiaWeather').value);
  const incident   = document.getElementById('indiaIncident').value;
  const nReroute   = parseInt(document.getElementById('indiaVehiclesReroute').value);

  const btn = document.getElementById('indiaFindBtn');
  btn.disabled = true;
  btn.textContent = '⏳ Fetching live road geometry & vehicle loads…';
  document.getElementById('indiaMapLoader').classList.add('active');
  document.getElementById('indiaResultsSection').style.display = 'none';
  document.getElementById('indiaExplanationBox').style.display = 'none';
  document.getElementById('indiaBottleneckCard').style.display = 'none';

  try {
    const res = await fetch('/api/india-route', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        origin_name: originName,
        dest_name: destName,
        origin_coords: selectedOriginCoords,
        dest_coords: selectedDestCoords,
        hour: hour,
        day_of_week: dow,
        weather: weather,
        accident_corridor: incident,
        n_vehicles_rerouting: nReroute,
        vehicle_mode: selectedRouteVehicleMode
      })
    });

    const data = await res.json();
    if (data.error) {
      alert('Error: ' + data.error);
      return;
    }

    renderIndiaRouteMap(data);
    renderIndiaRouteResults(data);
  } catch (err) {
    alert('Failed to analyze India route: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '🚦 Analyze Traffic & Recommend Alternate Route';
    document.getElementById('indiaMapLoader').classList.remove('active');
  }
}

// ───────────────────── Render India Map Visuals ─────────────────────────────

function renderIndiaRouteMap(data) {
  initIndiaMap();

  // Clear previous layers
  indiaLayers.forEach(l => indiaMap.removeLayer(l));
  indiaLayers = [];

  const baseline = data.baseline_route;
  const alternate = data.alternate_route;

  // 1. Draw Alternate Route FIRST (Underneath, in glowing emerald green)
  if (alternate && alternate.geometry && alternate.geometry.coordinates) {
    const altCoords = alternate.geometry.coordinates.map(pt => [pt[1], pt[0]]);
    
    // Outer glow
    const altGlow = L.polyline(altCoords, {
      color: '#10b981', weight: 8, opacity: 0.35
    }).addTo(indiaMap);
    indiaLayers.push(altGlow);

    // Main line
    const altLine = L.polyline(altCoords, {
      color: '#10b981', weight: 5, opacity: 0.95
    }).addTo(indiaMap);
    altLine.bindPopup(`
      <div style="font-family:sans-serif; min-width:180px;">
        <strong style="color:#10b981;">🧠 AI Alternate Route</strong><br>
        Distance: <strong>${alternate.distance_km} km</strong><br>
        Travel Time: <strong>${alternate.current_travel_time_min} mins</strong><br>
        Average Speed: <strong>${alternate.average_speed_kmh} km/h</strong><br>
        Vehicle Load: <strong>${alternate.vehicle_count.toLocaleString()} vehicles</strong><br>
        <span style="color:#10b981; font-weight:bold;">⚡ Saves ${alternate.time_saved_min} mins!</span>
      </div>
    `);
    indiaLayers.push(altLine);
  }

  // 2. Draw Primary / Baseline Route with segment-level congestion color-coding
  if (baseline && baseline.segments && baseline.segments.length > 0) {
    baseline.segments.forEach(seg => {
      const segLine = L.polyline(seg.coords, {
        color: seg.color, weight: 6, opacity: 0.88,
        dashArray: seg.color === '#ef4444' ? '6 4' : null
      }).addTo(indiaMap);

      segLine.bindPopup(`
        <div style="font-family:sans-serif; min-width:170px;">
          <strong style="color:${seg.color};">Stretch #${seg.segment_id}: ${seg.status}</strong><br>
          Vehicle Count: <strong>${seg.vehicles_on_segment.toLocaleString()} vehicles</strong><br>
          Estimated Speed: <strong>${seg.speed_kmh} km/h</strong><br>
          ${seg.color === '#ef4444' ? '<span style="color:#ef4444; font-weight:bold;">⚠️ Severe Bottleneck Delay</span>' : ''}
        </div>
      `);
      indiaLayers.push(segLine);
    });
  } else if (baseline && baseline.geometry) {
    const baseCoords = baseline.geometry.coordinates.map(pt => [pt[1], pt[0]]);
    const baseLine = L.polyline(baseCoords, {
      color: '#ef4444', weight: 5, opacity: 0.85
    }).addTo(indiaMap);
    indiaLayers.push(baseLine);
  }

  // 3. Add Origin Marker (Blue pin)
  const origMarker = L.circleMarker([data.origin.lat, data.origin.lon], {
    radius: 9, fillColor: '#38bdf8', color: '#fff', weight: 2.5, fillOpacity: 1
  }).addTo(indiaMap);
  origMarker.bindTooltip(`<strong>📍 Origin</strong><br>${data.origin.name}`, { permanent: true, direction: 'top' });
  indiaLayers.push(origMarker);

  // 4. Add Destination Marker (Red pin)
  const destMarker = L.circleMarker([data.destination.lat, data.destination.lon], {
    radius: 9, fillColor: '#ef4444', color: '#fff', weight: 2.5, fillOpacity: 1
  }).addTo(indiaMap);
  destMarker.bindTooltip(`<strong>🏁 Destination</strong><br>${data.destination.name}`, { permanent: true, direction: 'bottom' });
  indiaLayers.push(destMarker);

  // 5. Add Bottleneck Marker (Flashing orange/red icon on the worst traffic stretch)
  if (data.bottleneck && baseline.geometry && baseline.geometry.coordinates) {
    const pts = baseline.geometry.coordinates;
    const midPt = pts[Math.floor(pts.length / 2)];
    if (midPt) {
      const bottleneckMarker = L.marker([midPt[1], midPt[0]], {
        icon: L.divIcon({
          className: 'bottleneck-pulse-icon',
          html: `<div style="background:#ef4444; color:#fff; border-radius:50%; width:28px; height:28px; display:flex; align-items:center; justify-content:center; font-weight:bold; box-shadow:0 0 14px #ef4444; border:2px solid #fff; font-size:14px;">⚠️</div>`,
          iconSize: [28, 28]
        })
      }).addTo(indiaMap);
      bottleneckMarker.bindPopup(`
        <strong>⚠️ Traffic Bottleneck Zone</strong><br>
        ${data.bottleneck.location}<br>
        Volume: <strong>${data.bottleneck.current_vehicles.toLocaleString()} vehicles</strong><br>
        Speed: <strong>${data.bottleneck.speed_kmh} km/h</strong> (Delay: +${data.bottleneck.delay_minutes} min)
      `);
      indiaLayers.push(bottleneckMarker);
    }
  }

  // 6. Fit Bounds nicely
  const allPoints = [];
  if (baseline && baseline.geometry) {
    baseline.geometry.coordinates.forEach(c => allPoints.push([c[1], c[0]]));
  }
  if (alternate && alternate.geometry) {
    alternate.geometry.coordinates.forEach(c => allPoints.push([c[1], c[0]]));
  }
  if (allPoints.length > 0) {
    indiaMap.fitBounds(L.latLngBounds(allPoints), { padding: [40, 40] });
  }
}

// ───────────────────── Render Results & Cards ───────────────────────────────

function renderIndiaRouteResults(data) {
  const bl = data.baseline_route;
  const alt = data.alternate_route;

  // Baseline Card
  document.getElementById('indiaBaselineTime').textContent = `${bl.current_travel_time_min} mins`;
  document.getElementById('indiaBaselineDist').textContent = `${bl.distance_km} km (avg ${bl.average_speed_kmh} km/h)`;
  document.getElementById('indiaBaselineFreeflow').textContent = `Free-flow time: ${bl.freeflow_time_min} mins`;
  document.getElementById('indiaBaselineVehicles').textContent = `${bl.vehicle_count.toLocaleString()}`;

  const blBadge = document.getElementById('indiaBaselineBadge');
  blBadge.textContent = `${bl.congestion_level} Congestion`;
  blBadge.className = `traffic-stat-pill ${bl.congestion_level === 'High' ? 'pill-high' : 'pill-med'}`;

  // Alternate Card
  document.getElementById('indiaProposedTime').textContent = `${alt.current_travel_time_min} mins`;
  document.getElementById('indiaProposedDist').textContent = `${alt.distance_km} km (avg ${alt.average_speed_kmh} km/h)`;
  document.getElementById('indiaTimeSavedBadge').textContent = `⚡ Saves ~${alt.time_saved_min} mins!`;
  document.getElementById('indiaProposedImpact').textContent = `+${alt.marginal_network_impact_min} min`;

  // AI Explanation
  document.getElementById('indiaExplanationText').textContent = data.ai_explanation;
  document.getElementById('indiaExplanationBox').style.display = 'block';

  // Bottleneck Info Card
  if (data.bottleneck) {
    document.getElementById('bottleneckLocationText').textContent = `📍 ${data.bottleneck.location}`;
    document.getElementById('bottleneckVehicles').textContent = `${data.bottleneck.current_vehicles.toLocaleString()} veh`;
    document.getElementById('bottleneckSpeed').textContent = `${data.bottleneck.speed_kmh} km/h`;
    document.getElementById('bottleneckDelay').textContent = `+${data.bottleneck.delay_minutes} min`;
    document.getElementById('indiaBottleneckCard').style.display = 'block';
  }

  // Segment Table Breakdown
  const tbody = document.getElementById('indiaSegmentsBody');
  const allRows = [];

  if (bl.segments) {
    bl.segments.forEach(seg => {
      allRows.push(`
        <tr>
          <td><span style="color:#ef4444; font-weight:700;">Standard Corridor</span></td>
          <td>Stretch #${seg.segment_id}</td>
          <td><strong style="color:#f87171;">${seg.vehicles_on_segment.toLocaleString()}</strong></td>
          <td>${seg.speed_kmh} km/h</td>
          <td><span class="traffic-stat-pill ${seg.color === '#ef4444' ? 'pill-high' : (seg.color === '#f59e0b' ? 'pill-med' : 'pill-low')}">${seg.status}</span></td>
        </tr>
      `);
    });
  }

  if (alt.segments) {
    alt.segments.forEach(seg => {
      allRows.push(`
        <tr style="background:rgba(16,185,129,0.03);">
          <td><span style="color:#10b981; font-weight:700;">AI Alternate Corridor</span></td>
          <td>Stretch #${seg.segment_id}</td>
          <td><strong style="color:#34d399;">${seg.vehicles_on_segment.toLocaleString()}</strong></td>
          <td>${seg.speed_kmh} km/h</td>
          <td><span class="traffic-stat-pill pill-low">${seg.status}</span></td>
        </tr>
      `);
    });
  }

  tbody.innerHTML = allRows.join('');
  document.getElementById('indiaResultsSection').style.display = 'block';

  // Update deep-link to Simulation Lab
  const btnSim = document.getElementById('btnSimulateFromRoute');
  if (btnSim) {
    const originName = document.getElementById('indiaOriginInput').value.trim();
    const destName = document.getElementById('indiaDestInput').value.trim();
    const hour = parseInt(document.getElementById('indiaHour').value) || 9;
    const vCount = Math.min(bl.vehicle_count || 200, 500);
    btnSim.href = `/simulation?hour=${hour}&mode=${selectedRouteVehicleMode}&vehicles=${vCount}&corridor=${encodeURIComponent(originName + ' ➔ ' + destName)}`;
  }
}


// ────────────────────────────────────────────────────────────────────────────
// ABSTRACT LAB ROUTE LOGIC (Original 8-Node Graph)
// ────────────────────────────────────────────────────────────────────────────

function initRouteMap() {
  if (routeMap) return;
  routeMap = L.map('routeMap', {
    center: [51.505, -0.090],
    zoom: 13
  });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 18
  }).addTo(routeMap);
}

async function findRoutes() {
  const source   = document.getElementById('sourceNode').value;
  const target   = document.getElementById('targetNode').value;
  const hour     = parseInt(document.getElementById('routeHour').value);
  const dow      = parseInt(document.getElementById('routeDay').value);
  const weather  = parseInt(document.getElementById('routeWeather').value);
  const accident = document.getElementById('routeAccident').value;
  const nVeh     = parseInt(document.getElementById('nVehicles').value);

  if (source === target) {
    alert('Origin and destination must be different.');
    return;
  }

  const btn = document.getElementById('findBtn');
  btn.disabled = true;
  btn.textContent = '⏳ Calculating…';
  document.getElementById('routeMapLoader').classList.add('active');
  document.getElementById('routeResults').style.display = 'none';
  document.getElementById('explanationBox').style.display = 'none';

  try {
    const res = await fetch('/api/recommend-routes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source, target,
        hour, day_of_week: dow,
        weather,
        accident_edge: accident || null,
        n_vehicles_rerouting: nVeh
      })
    });

    const data = await res.json();
    if (data.error) {
      alert('Error: ' + data.error);
      return;
    }

    renderRouteMap(data);
    renderRouteResults(data);
  } catch (err) {
    alert('Failed to fetch routes: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '🔍 Find & Compare Graph Routes';
    document.getElementById('routeMapLoader').classList.remove('active');
  }
}

function renderRouteMap(data) {
  initRouteMap();

  routeLayers.forEach(l => routeMap.removeLayer(l));
  routeLayers = [];

  const nodes = data.nodes;

  Object.values(data.all_edges_map).forEach(e => {
    const poly = L.polyline(
      [[e.from_lat, e.from_lon], [e.to_lat, e.to_lon]],
      { color: e.congestion_color, weight: 2, opacity: 0.3, dashArray: '4 4' }
    ).addTo(routeMap);
    routeLayers.push(poly);
  });

  const baselinePath = data.baseline.path_str;
  const proposedPath = data.proposed.path.path_str;

  data.all_routes.forEach((route, i) => {
    let color   = '#8b5cf6';
    let weight  = 3;
    let opacity = 0.5;
    let dashArr = '6 4';

    if (route.path_str === proposedPath) {
      color = '#10b981'; weight = 6; opacity = 0.9; dashArr = null;
    } else if (route.path_str === baselinePath) {
      color = '#f59e0b'; weight = 5; opacity = 0.8; dashArr = '8 3';
    }

    const coords = route.coords.map(c => [c.lat, c.lon]);
    const poly = L.polyline(coords, {
      color, weight, opacity,
      dashArray: dashArr
    }).addTo(routeMap);

    poly.bindPopup(`
      <strong>Route ${i+1}</strong><br>
      ${route.path_str}<br>
      Travel time: <strong>${route.total_time} min</strong>
    `);
    routeLayers.push(poly);
  });

  Object.entries(nodes).forEach(([id, n]) => {
    const isSource = id === data.source;
    const isTarget = id === data.target;
    const color = isSource ? '#3b82f6' : (isTarget ? '#10b981' : '#6b7280');
    const radius = (isSource || isTarget) ? 10 : 7;

    const marker = L.circleMarker([n.lat, n.lon], {
      radius, fillColor: color, color: '#fff',
      weight: 2, fillOpacity: 0.9
    }).addTo(routeMap);

    marker.bindTooltip(
      `<strong>${id}</strong> – ${n.name}${isSource ? ' (Start)' : ''}${isTarget ? ' (End)' : ''}`,
      { permanent: isSource || isTarget, direction: 'top' }
    );
    routeLayers.push(marker);
  });

  if (data.all_routes.length > 0) {
    const allCoords = data.all_routes.flatMap(r => r.coords.map(c => [c.lat, c.lon]));
    routeMap.fitBounds(L.latLngBounds(allCoords), { padding: [30, 30] });
  }
}

function renderRouteResults(data) {
  document.getElementById('baselinePath').textContent = data.baseline.path_str;
  document.getElementById('baselineTime').textContent = data.baseline.total_time + ' min';

  const blCong = data.baseline.edges
    .map(e => e.congestion_level)
    .reduce((acc, l) => {
      acc[l] = (acc[l] || 0) + 1; return acc;
    }, {});
  const blWorst = blCong['High'] ? 'High' : (blCong['Medium'] ? 'Medium' : 'Low');
  document.getElementById('baselineCongestion').innerHTML =
    `<span class="badge badge-${blWorst.toLowerCase()}">${blWorst}</span>`;

  const pr = data.proposed;
  document.getElementById('proposedPath').textContent = pr.path.path_str;
  document.getElementById('proposedTime').textContent = pr.future_time + ' min (predicted)';
  document.getElementById('proposedImpact').innerHTML =
    `<span style="color:var(--accent-orange); font-size:1.4rem; font-weight:800;">
      +${pr.network_impact} min
    </span>`;

  const tbody = document.getElementById('allRoutesBody');
  tbody.innerHTML = data.all_routes.map((r, i) => {
    const isBaseline = r.path_str === data.baseline.path_str;
    const isProposed = r.path_str === data.proposed.path.path_str;
    return `
      <tr style="${isProposed ? 'background:rgba(16,185,129,0.05)' : ''}">
        <td>${i + 1}</td>
        <td style="font-size:0.8rem;">${r.path_str}</td>
        <td>${r.path.length - 1}</td>
        <td><strong>${r.total_time} min</strong></td>
        <td>${isBaseline ? '⚡ Yes' : ''}</td>
        <td>${isProposed ? '🧠 Yes' : ''}</td>
      </tr>
    `;
  }).join('');

  document.getElementById('explanationText').textContent = data.explanation;
  document.getElementById('explanationBox').style.display = 'block';
  document.getElementById('routeResults').style.display = 'block';
}

// ───────────────────── Auto-init on Page Load ───────────────────────────────

document.addEventListener('DOMContentLoaded', function() {
  if (document.getElementById('indiaRouteMap')) {
    initIndiaMap();
    loadCorridorChips();

    // Check URL parameters transferred from /predict
    const urlParams = new URLSearchParams(window.location.search);
    const qOrigin   = urlParams.get('origin');
    const qDest     = urlParams.get('dest');
    const qMode     = urlParams.get('mode');
    const qHour     = urlParams.get('hour');
    const qOrigLat  = parseFloat(urlParams.get('origLat'));
    const qOrigLon  = parseFloat(urlParams.get('origLon'));
    const qDestLat  = parseFloat(urlParams.get('destLat'));
    const qDestLon  = parseFloat(urlParams.get('destLon'));

    if (qMode && ['ambulance', 'delivery', 'commute'].includes(qMode)) {
      selectedRouteVehicleMode = qMode;
      ['routeModeAmbulance', 'routeModeDelivery', 'routeModeCommute'].forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.classList.remove('active', 'btn-primary'); el.classList.add('btn-secondary'); }
      });
      const aBtn = document.getElementById(
        qMode === 'ambulance' ? 'routeModeAmbulance' : (qMode === 'delivery' ? 'routeModeDelivery' : 'routeModeCommute')
      );
      if (aBtn) { aBtn.classList.remove('btn-secondary'); aBtn.classList.add('active', 'btn-primary'); }
    }

    if (qHour && document.getElementById('indiaHour')) {
      document.getElementById('indiaHour').value = qHour;
    }
    if (qOrigin && document.getElementById('indiaOriginInput')) {
      document.getElementById('indiaOriginInput').value = qOrigin;
    }
    if (qDest && document.getElementById('indiaDestInput')) {
      document.getElementById('indiaDestInput').value = qDest;
    }
    if (!isNaN(qOrigLat) && !isNaN(qOrigLon)) {
      selectedOriginCoords = [qOrigLat, qOrigLon];
      if (document.getElementById('originCoordsBadge')) {
        document.getElementById('originCoordsBadge').textContent = `Coords: ${qOrigLat.toFixed(4)}, ${qOrigLon.toFixed(4)}`;
      }
    }
    if (!isNaN(qDestLat) && !isNaN(qDestLon)) {
      selectedDestCoords = [qDestLat, qDestLon];
      if (document.getElementById('destCoordsBadge')) {
        document.getElementById('destCoordsBadge').textContent = `Coords: ${qDestLat.toFixed(4)}, ${qDestLon.toFixed(4)}`;
      }
    }

    // Automatically trigger analysis
    setTimeout(() => {
      analyzeIndiaRoutes();
    }, 400);
  }
});
