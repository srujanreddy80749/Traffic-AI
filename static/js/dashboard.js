/**
 * dashboard.js — Traffic Dashboard Map & Chart
 * Uses Leaflet.js for the map and Chart.js for the congestion bar chart.
 */

let dashMap = null;
let congestionChart = null;
let edgePolylines = [];
let nodeMarkers = [];

// ── Map Initialization ─────────────────────────────────────────────────────

function initDashMap() {
  if (dashMap) return;
  dashMap = L.map('map', {
    center: [51.505, -0.090],
    zoom: 13,
    zoomControl: true,
    attributionControl: true
  });

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 18
  }).addTo(dashMap);
}

// ── Load Network Status ────────────────────────────────────────────────────

async function loadNetworkStatus() {
  const weather  = document.getElementById('weatherSel').value;
  const accident = document.getElementById('accidentSel').value;

  document.getElementById('mapLoader').classList.add('active');

  try {
    const res = await fetch(`/api/network-status?weather=${weather}&accident_edge=${accident}`);
    const data = await res.json();

    updateStats(data);
    updateMap(data);
    updateEdgeTable(data.edges);
    updateCongestionChart(data.edges);
  } catch (err) {
    console.error('Failed to load network status:', err);
  } finally {
    document.getElementById('mapLoader').classList.remove('active');
  }
}

// ── Update Statistics ──────────────────────────────────────────────────────

function updateStats(data) {
  const edges = data.edges;
  const low    = edges.filter(e => e.congestion_level === 'Low').length;
  const med    = edges.filter(e => e.congestion_level === 'Medium').length;
  const high   = edges.filter(e => e.congestion_level === 'High').length;
  const avgT   = (edges.reduce((s, e) => s + e.current_time, 0) / edges.length).toFixed(1);

  document.getElementById('statLow').textContent  = low;
  document.getElementById('statMed').textContent  = med;
  document.getElementById('statHigh').textContent = high;
  document.getElementById('statAvgTime').textContent = avgT;
}

// ── Update Map ─────────────────────────────────────────────────────────────

function updateMap(data) {
  initDashMap();

  // Clear previous
  edgePolylines.forEach(p => dashMap.removeLayer(p));
  nodeMarkers.forEach(m => dashMap.removeLayer(m));
  edgePolylines = [];
  nodeMarkers = [];

  const colorMap = { Low: '#10b981', Medium: '#f59e0b', High: '#ef4444' };

  // Draw edges as polylines
  data.edges.forEach(e => {
    const color = e.congestion_color || colorMap[e.congestion_level] || '#6b7280';
    const weight = e.congestion_level === 'High' ? 6 : (e.congestion_level === 'Medium' ? 4 : 3);

    const poly = L.polyline(
      [[e.from_lat, e.from_lon], [e.to_lat, e.to_lon]],
      { color, weight, opacity: 0.85 }
    ).addTo(dashMap);

    poly.bindPopup(`
      <div style="font-family:Inter,sans-serif; min-width:180px;">
        <strong>${e.from_name} → ${e.to_name}</strong><br>
        <span style="color:${color};">● ${e.congestion_level} Congestion</span><br>
        Vehicles: ${e.current_vehicles} / ${e.capacity}<br>
        Travel time: ${e.current_time.toFixed(1)} min<br>
        Congestion: ${(e.congestion_ratio*100).toFixed(0)}%
        ${e.has_accident ? '<br><span style="color:#ef4444;">⚠️ Accident/Closure</span>' : ''}
      </div>
    `);

    edgePolylines.push(poly);
  });

  // Draw nodes
  data.nodes.forEach(n => {
    const marker = L.circleMarker([n.lat, n.lon], {
      radius: 8, fillColor: '#3b82f6', color: '#fff',
      weight: 2, opacity: 1, fillOpacity: 0.9
    }).addTo(dashMap);

    marker.bindTooltip(`<strong>${n.id}</strong> – ${n.name}`,
      { permanent: false, direction: 'top', className: 'leaflet-tooltip-dark' });

    nodeMarkers.push(marker);
  });
}

// ── Update Edge Table ──────────────────────────────────────────────────────

function updateEdgeTable(edges) {
  const tbody = document.getElementById('edgeTableBody');
  tbody.innerHTML = edges.map(e => `
    <tr>
      <td style="font-weight:600;">${e.from_name}<br><span class="text-xs text-muted">→ ${e.to_name}</span></td>
      <td>${e.current_vehicles}</td>
      <td>${e.capacity}</td>
      <td>${e.current_time.toFixed(1)}</td>
      <td>
        <span class="badge badge-${e.congestion_level.toLowerCase()}">
          ${e.congestion_level}
        </span>
        ${e.has_accident ? '<span class="badge badge-high" style="margin-left:4px;">⚠️</span>' : ''}
      </td>
    </tr>
  `).join('');
}

// ── Congestion Bar Chart ───────────────────────────────────────────────────

function updateCongestionChart(edges) {
  const ctx = document.getElementById('congestionChart').getContext('2d');

  const labels = edges.map(e => `${e.from}-${e.to}`);
  const values = edges.map(e => (e.congestion_ratio * 100).toFixed(1));
  const colors = edges.map(e =>
    e.congestion_level === 'High'   ? 'rgba(239,68,68,0.75)'  :
    e.congestion_level === 'Medium' ? 'rgba(245,158,11,0.75)' :
                                      'rgba(16,185,129,0.75)'
  );

  if (congestionChart) {
    congestionChart.data.labels = labels;
    congestionChart.data.datasets[0].data = values;
    congestionChart.data.datasets[0].backgroundColor = colors;
    congestionChart.update();
    return;
  }

  congestionChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Congestion (%)',
        data: values,
        backgroundColor: colors,
        borderRadius: 4
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.parsed.y}% congested`
          }
        }
      },
      scales: {
        x: {
          ticks: { color: '#8892aa', font: { size: 11 } },
          grid:  { color: 'rgba(255,255,255,0.05)' }
        },
        y: {
          min: 0, max: 150,
          ticks: { color: '#8892aa', callback: v => v + '%' },
          grid:  { color: 'rgba(255,255,255,0.05)' }
        }
      }
    }
  });
}

// ── Auto-load on page ready ────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadNetworkStatus();
});
