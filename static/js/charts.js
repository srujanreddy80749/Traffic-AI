/**
 * charts.js — Prediction, Simulation & Comparison Charts
 * Handles all Chart.js charts and API calls for the prediction,
 * simulation, and comparison pages.
 */

// ══════════════════════════════════════════════════════════════
//   PREDICTION PAGE
// ══════════════════════════════════════════════════════════════

let horizonChart = null;

async function runPrediction() {
  const hour     = parseInt(document.getElementById('predHour').value);
  const dow      = parseInt(document.getElementById('predDay').value);
  const vehicles = parseInt(document.getElementById('predVehicles').value);
  const capacity = parseInt(document.getElementById('predCapacity').value);
  const weather  = parseInt(document.getElementById('predWeather').value);
  const accident = parseInt(document.getElementById('predAccident').value);

  const btn = document.getElementById('predBtn');
  btn.disabled = true; btn.textContent = '⏳ Predicting…';

  try {
    const res = await fetch('/api/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hour, day_of_week: dow, vehicle_count: vehicles,
                              weather, accident, road_capacity: capacity })
    });
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    displayPrediction(data);
  } catch (err) {
    alert('Prediction failed: ' + err.message);
  } finally {
    btn.disabled = false; btn.textContent = '🤖 Predict Traffic';
  }
}

function displayPrediction(d) {
  // Show cards
  document.getElementById('predPlaceholder').style.display  = 'none';
  document.getElementById('predResultCard').style.display   = 'block';
  document.getElementById('horizonCard').style.display      = 'block';
  document.getElementById('horizonChartCard').style.display = 'block';

  // Traffic level
  const colorMap = { Low: '#10b981', Medium: '#f59e0b', High: '#ef4444' };
  const emojiMap = { Low: '🟢', Medium: '🟡', High: '🔴' };
  const color = colorMap[d.traffic_level] || '#6b7280';

  document.getElementById('trafficLevelBig').style.color = color;
  document.getElementById('trafficLevelBig').textContent = emojiMap[d.traffic_level] + ' ' + d.traffic_level;

  // Confidence
  const confPct = Math.round(d.confidence * 100);
  document.getElementById('confPct').textContent = confPct + '%';
  document.getElementById('confBarFill').style.width = confPct + '%';

  document.getElementById('predTime').textContent      = d.travel_time_min;
  document.getElementById('predCongestion').textContent = d.congestion_ratio.toFixed(2);

  // Horizon cards
  const horizonGrid = document.getElementById('horizonGrid');
  horizonGrid.innerHTML = d.horizon_forecasts.map(h => `
    <div style="text-align:center; border:1px solid var(--border);
                border-radius:var(--radius-sm); padding:0.8rem;">
      <div class="text-xs text-muted">+${h.minutes_ahead} min</div>
      <div style="font-size:1.6rem; margin:0.3rem 0;">
        ${{ Low:'🟢', Medium:'🟡', High:'🔴' }[h.traffic_level]}
      </div>
      <div style="font-weight:700;">${h.traffic_level}</div>
      <div class="text-xs text-muted">${h.travel_time_min} min</div>
    </div>
  `).join('');

  // Horizon chart
  renderHorizonChart(d);
}

function renderHorizonChart(d) {
  const ctx = document.getElementById('horizonChart').getContext('2d');
  const labels = ['Now', '+15 min', '+30 min', '+60 min'];
  const values = [d.travel_time_min, ...d.horizon_forecasts.map(h => h.travel_time_min)];
  const colors = [
    colorForLevel(d.traffic_level),
    ...d.horizon_forecasts.map(h => colorForLevel(h.traffic_level))
  ];

  if (horizonChart) { horizonChart.destroy(); }

  horizonChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Predicted Travel Time (min)',
        data: values,
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59,130,246,0.1)',
        borderWidth: 2,
        pointBackgroundColor: colors,
        pointRadius: 6,
        tension: 0.3,
        fill: true
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { labels: { color: '#8892aa' } }
      },
      scales: {
        x: { ticks: { color: '#8892aa' }, grid: { color: 'rgba(255,255,255,0.05)' } },
        y: { ticks: { color: '#8892aa', callback: v => v + ' min' },
             grid: { color: 'rgba(255,255,255,0.05)' } }
      }
    }
  });
}

function colorForLevel(level) {
  return { Low: '#10b981', Medium: '#f59e0b', High: '#ef4444' }[level] || '#6b7280';
}

// Load model metrics when prediction page loads
async function loadMetrics() {
  const el = document.getElementById('metricsContent');
  if (!el) return;
  try {
    const res = await fetch('/api/metrics');
    const m = await res.json();
    el.innerHTML = `
      <div class="grid-2" style="gap:0.75rem;">
        <div style="border:1px solid var(--border); border-radius:var(--radius-sm); padding:0.75rem;">
          <div class="text-xs text-muted mb-1">CLASSIFIER (Traffic Level)</div>
          <div style="font-size:0.85rem;">
            Accuracy: <strong>${(m.classification.accuracy*100).toFixed(1)}%</strong><br>
            F1 (weighted): <strong>${(m.classification.f1_weighted*100).toFixed(1)}%</strong>
          </div>
        </div>
        <div style="border:1px solid var(--border); border-radius:var(--radius-sm); padding:0.75rem;">
          <div class="text-xs text-muted mb-1">REGRESSOR (Travel Time)</div>
          <div style="font-size:0.85rem;">
            MAE: <strong>${m.regression.mae} min</strong><br>
            R²: <strong>${m.regression.r2}</strong>
          </div>
        </div>
      </div>
      <div class="text-xs text-muted mt-1">
        Trained on ${m.training_samples} synthetic records · Tested on ${m.test_samples} records
      </div>
    `;
  } catch {}
}

// ══════════════════════════════════════════════════════════════
//   SIMULATION PAGE
// ══════════════════════════════════════════════════════════════

let simCompareChart = null;
let timeSeriesChart = null;

function setStrategy(value, btn) {
  document.getElementById('simStrategy').value = value;
  document.querySelectorAll('.tabs .tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

function setSimVehicleMode(mode) {
  const modeIn = document.getElementById('simVehicleMode');
  if (modeIn) modeIn.value = mode;

  ['simModeAmbulance', 'simModeDelivery', 'simModeCommute'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active');
  });

  const activeBtn = document.getElementById(
    mode === 'ambulance' ? 'simModeAmbulance' : (mode === 'delivery' ? 'simModeDelivery' : 'simModeCommute')
  );
  if (activeBtn) activeBtn.classList.add('active');

  const modeTag = document.getElementById('simModeTag');
  if (modeTag) {
    if (mode === 'ambulance') {
      modeTag.className = 'badge badge-high';
      modeTag.textContent = '🚑 Emergency Priority Protocol Active';
    } else if (mode === 'delivery') {
      modeTag.className = 'badge badge-medium';
      modeTag.textContent = '🛵 Quick Delivery SLA Priority';
    } else {
      modeTag.className = 'badge badge-low';
      modeTag.textContent = '🚗 Commuter Community Routing';
    }
  }
}

async function runSimulation() {
  const mode = document.getElementById('simVehicleMode') ? document.getElementById('simVehicleMode').value : 'commute';
  const params = {
    n_vehicles:       parseInt(document.getElementById('simVehicles').value),
    demand_rate:      parseFloat(document.getElementById('simDemand').value),
    weather:          parseInt(document.getElementById('simWeather').value),
    accident_edge:    document.getElementById('simAccident').value || null,
    sim_duration_min: parseInt(document.getElementById('simDuration').value),
    hour:             parseInt(document.getElementById('simHour').value),
    day_of_week:      0,
    strategy:         document.getElementById('simStrategy').value,
    vehicle_mode:     mode
  };

  const btn = document.getElementById('simBtn');
  btn.disabled = true; btn.textContent = '⏳ Running…';
  document.getElementById('simStatus').style.display = 'flex';
  document.getElementById('simPlaceholder').style.display = 'none';
  document.getElementById('simResults').style.display = 'none';
  document.getElementById('timeSeriesCard').style.display = 'none';

  try {
    const res = await fetch('/api/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params)
    });
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    displaySimResults(data);
  } catch (err) {
    alert('Simulation error: ' + err.message);
  } finally {
    btn.disabled = false; btn.textContent = '▶ Run Simulation';
    document.getElementById('simStatus').style.display = 'none';
  }
}

function displaySimResults(data) {
  document.getElementById('simResults').style.display = 'block';
  document.getElementById('timeSeriesCard').style.display = 'block';

  const summary = data.summary;
  const statsGrid = document.getElementById('simStatsGrid');

  const metrics = [
    { label: 'Avg Travel Time', key: 'avg_travel_time', unit: 'min', icon: '⏱️', color: 'blue' },
    { label: 'Avg Waiting Time', key: 'avg_waiting_time', unit: 'min', icon: '⏳', color: 'orange' },
    { label: 'Network Delay', key: 'total_network_delay', unit: 'min', icon: '🌐', color: 'red' },
    { label: 'Max Congestion', key: 'max_congestion', unit: '', icon: '🔴', color: 'purple' }
  ];

  const strategies = Object.keys(summary);

  statsGrid.innerHTML = metrics.map(m => {
    const vals = strategies.map(s => ({ s, v: summary[s]?.[m.key] ?? '–' }));
    return `
      <div class="stat-card" style="flex-direction:column; gap:0.5rem;">
        <div class="flex items-center gap-1" style="align-self:flex-start;">
          <div class="stat-icon ${m.color}">${m.icon}</div>
          <div style="font-size:0.8rem; color:var(--text-muted);">${m.label}</div>
        </div>
        ${vals.map(({ s, v }) => `
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <span class="badge badge-${s === 'baseline' ? 'medium' : 'low'}" style="font-size:0.65rem;">
              ${s === 'baseline' ? '⚡ Baseline' : '🧠 Proposed'}
            </span>
            <span style="font-weight:800;">${v} ${m.unit}</span>
          </div>
        `).join('')}
      </div>
    `;
  }).join('');

  // Comparison bar chart
  renderSimCompareChart(summary, strategies);

  // Time series
  renderTimeSeriesChart(data.results, strategies);
}

function renderSimCompareChart(summary, strategies) {
  const ctx = document.getElementById('simCompareChart').getContext('2d');
  const metrics = ['avg_travel_time', 'avg_waiting_time', 'total_network_delay'];
  const labels   = ['Avg Travel Time', 'Avg Waiting Time', 'Network Delay'];

  const datasets = strategies.map((s, i) => ({
    label: s === 'baseline' ? '⚡ Baseline' : '🧠 Proposed',
    data: metrics.map(m => summary[s]?.[m] ?? 0),
    backgroundColor: s === 'baseline'
      ? 'rgba(245,158,11,0.7)' : 'rgba(16,185,129,0.7)',
    borderRadius: 4
  }));

  if (simCompareChart) { simCompareChart.destroy(); }

  simCompareChart = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets },
    options: {
      responsive: true,
      plugins: {
        legend: { labels: { color: '#8892aa' } }
      },
      scales: {
        x: { ticks: { color: '#8892aa' }, grid: { color: 'rgba(255,255,255,0.05)' } },
        y: { ticks: { color: '#8892aa', callback: v => v + ' min' },
             grid: { color: 'rgba(255,255,255,0.05)' } }
      }
    }
  });
}

function renderTimeSeriesChart(results, strategies) {
  const ctx = document.getElementById('timeSeriesChart').getContext('2d');

  const datasets = strategies.map(s => {
    const ts = results[s]?.time_series || [];
    return {
      label: s === 'baseline' ? '⚡ Baseline' : '🧠 Proposed',
      data: ts.map(p => ({ x: p.minute, y: p.avg_congestion })),
      borderColor: s === 'baseline' ? '#f59e0b' : '#10b981',
      backgroundColor: 'transparent',
      borderWidth: 2, tension: 0.3, pointRadius: 2
    };
  });

  if (timeSeriesChart) { timeSeriesChart.destroy(); }

  timeSeriesChart = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: '#8892aa' } } },
      scales: {
        x: {
          type: 'linear', title: { display: true, text: 'Minute', color: '#8892aa' },
          ticks: { color: '#8892aa' }, grid: { color: 'rgba(255,255,255,0.05)' }
        },
        y: {
          title: { display: true, text: 'Avg Congestion Ratio', color: '#8892aa' },
          ticks: { color: '#8892aa' }, grid: { color: 'rgba(255,255,255,0.05)' }
        }
      }
    }
  });
}

// ══════════════════════════════════════════════════════════════
//   COMPARISON PAGE
// ══════════════════════════════════════════════════════════════

let travelTimeChart = null, networkDelayChart = null,
    waitTimeChart = null, maxCongChart = null, featureChart = null;

async function loadComparison() {
  const btn = document.getElementById('loadBtn');
  btn.disabled = true;
  document.getElementById('loadStatus').style.display = 'flex';

  try {
    const [scRes, mRes] = await Promise.all([
      fetch('/api/comparison-scenarios'),
      fetch('/api/metrics')
    ]);
    const scData = await scRes.json();
    const metrics = await mRes.json();

    displayComparison(scData.scenarios);
    displayMLMetrics(metrics);
    displayFeatureImportance(metrics.feature_importance);
  } catch (err) {
    alert('Failed to load comparison: ' + err.message);
  } finally {
    btn.disabled = false;
    document.getElementById('loadStatus').style.display = 'none';
  }
}

function displayComparison(scenarios) {
  document.getElementById('summaryStats').style.display = 'grid';
  document.getElementById('chartsArea').style.display   = 'grid';
  document.getElementById('detailTableCard').style.display = 'block';
  document.getElementById('mlMetricsCard').style.display   = 'block';
  document.getElementById('featureCard').style.display     = 'block';

  const labels = scenarios.map(s => s.label.replace('\n', ' '));

  // Win count
  let wins = 0, losses = 0, ties = 0;
  scenarios.forEach(s => {
    const diff = (s.baseline_avg_travel_time || 0) - (s.proposed_avg_travel_time || 0);
    if (diff > 0.5) wins++;
    else if (diff < -0.5) losses++;
    else ties++;
  });
  document.getElementById('cmpWins').textContent   = wins;
  document.getElementById('cmpLosses').textContent = losses;
  document.getElementById('cmpTies').textContent   = ties;

  // Charts
  const chartDefs = [
    { id: 'travelTimeChart', chartVar: 'travelTimeChart', key: 'avg_travel_time', label: 'Avg Travel Time (min)' },
    { id: 'networkDelayChart', chartVar: 'networkDelayChart', key: 'total_network_delay', label: 'Network Delay (min)' },
    { id: 'waitTimeChart', chartVar: 'waitTimeChart', key: 'avg_waiting_time', label: 'Avg Waiting Time (min)' },
    { id: 'maxCongChart', chartVar: 'maxCongChart', key: 'max_congestion', label: 'Max Congestion Ratio' }
  ];

  chartDefs.forEach(cd => {
    const ctx = document.getElementById(cd.id).getContext('2d');
    const blData = scenarios.map(s => s[`baseline_${cd.key}`] || 0);
    const prData = scenarios.map(s => s[`proposed_${cd.key}`] || 0);
    const chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: '⚡ Baseline', data: blData, backgroundColor: 'rgba(245,158,11,0.7)', borderRadius: 4 },
          { label: '🧠 Proposed', data: prData, backgroundColor: 'rgba(16,185,129,0.7)', borderRadius: 4 }
        ]
      },
      options: {
        responsive: true,
        plugins: { legend: { labels: { color: '#8892aa' } } },
        scales: {
          x: { ticks: { color: '#8892aa', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.05)' } },
          y: { ticks: { color: '#8892aa' }, grid: { color: 'rgba(255,255,255,0.05)' } }
        }
      }
    });
  });

  // Detail table
  const tbody = document.getElementById('detailBody');
  tbody.innerHTML = scenarios.map(s => {
    const btTime = s.baseline_avg_travel_time || 0;
    const prTime = s.proposed_avg_travel_time || 0;
    const btDel  = s.baseline_total_network_delay || 0;
    const prDel  = s.proposed_total_network_delay || 0;
    const btCong = s.baseline_max_congestion || 0;
    const prCong = s.proposed_max_congestion || 0;
    const diff = btTime - prTime;
    const winner = diff > 0.5 ? '🧠 Proposed' : (diff < -0.5 ? '⚡ Baseline' : '🤝 Tie');
    const wColor = diff > 0.5 ? '#10b981' : (diff < -0.5 ? '#f59e0b' : '#6b7280');

    const better = (bl, pr, lowerBetter=true) => {
      const best = lowerBetter ? Math.min(bl, pr) : Math.max(bl, pr);
      return best === bl ? ['', 'color:var(--accent-green)'] : ['color:var(--accent-green)', ''];
    };
    const [blTimeStyle, prTimeStyle] = better(btTime, prTime);
    const [blDelStyle,  prDelStyle]  = better(btDel, prDel);

    return `
      <tr>
        <td style="font-weight:600; font-size:0.82rem;">${s.label.replace('\n', ' ')}</td>
        <td>${s.params?.weather_name || '–'}</td>
        <td>${s.params?.n_vehicles || '–'}</td>
        <td style="${blTimeStyle}">${btTime.toFixed(1)}</td>
        <td style="${prTimeStyle}">${prTime.toFixed(1)}</td>
        <td style="${blDelStyle}">${btDel.toFixed(1)}</td>
        <td style="${prDelStyle}">${prDel.toFixed(1)}</td>
        <td>${btCong.toFixed(2)}</td>
        <td>${prCong.toFixed(2)}</td>
        <td style="font-weight:700; color:${wColor};">${winner}</td>
      </tr>
    `;
  }).join('');
}

function displayMLMetrics(m) {
  document.getElementById('clfMetrics').innerHTML = `
    <table style="font-size:0.82rem;">
      <tr><td style="color:var(--text-muted); padding:0.3rem 0.5rem;">Accuracy</td>
          <td><strong>${(m.classification.accuracy*100).toFixed(2)}%</strong></td></tr>
      <tr><td style="color:var(--text-muted); padding:0.3rem 0.5rem;">F1-Score (weighted)</td>
          <td><strong>${(m.classification.f1_weighted*100).toFixed(2)}%</strong></td></tr>
      <tr><td style="color:var(--text-muted); padding:0.3rem 0.5rem;">Classes</td>
          <td>${m.classification.classes.join(', ')}</td></tr>
      <tr><td style="color:var(--text-muted); padding:0.3rem 0.5rem;">Train samples</td>
          <td>${m.training_samples}</td></tr>
    </table>`;

  document.getElementById('regMetrics').innerHTML = `
    <table style="font-size:0.82rem;">
      <tr><td style="color:var(--text-muted); padding:0.3rem 0.5rem;">MAE</td>
          <td><strong>${m.regression.mae} min</strong></td></tr>
      <tr><td style="color:var(--text-muted); padding:0.3rem 0.5rem;">RMSE</td>
          <td><strong>${m.regression.rmse} min</strong></td></tr>
      <tr><td style="color:var(--text-muted); padding:0.3rem 0.5rem;">R² Score</td>
          <td><strong>${m.regression.r2}</strong></td></tr>
      <tr><td style="color:var(--text-muted); padding:0.3rem 0.5rem;">Test samples</td>
          <td>${m.test_samples}</td></tr>
    </table>`;
}

function displayFeatureImportance(fi) {
  if (!fi) return;
  const ctx = document.getElementById('featureChart').getContext('2d');
  const labels = Object.keys(fi);
  const values = Object.values(fi).map(v => (v * 100).toFixed(1));

  featureChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Importance (%)',
        data: values,
        backgroundColor: 'rgba(59,130,246,0.7)',
        borderRadius: 4
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#8892aa', callback: v => v + '%' },
             grid: { color: 'rgba(255,255,255,0.05)' } },
        y: { ticks: { color: '#8892aa' }, grid: { color: 'rgba(255,255,255,0.05)' } }
      }
    }
  });
}

// ── Auto-init ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Prediction page
  if (document.getElementById('predHour')) {
    loadMetrics();
  }

  // Simulation page: Check URL parameters passed from /predict or /routes
  if (document.getElementById('simVehicles')) {
    const params = new URLSearchParams(window.location.search);
    const qCorridor = params.get('corridor');
    const qMode     = params.get('mode');
    const qVehicles = params.get('vehicles');
    const qHour     = params.get('hour');
    const qWeather  = params.get('weather');

    if (qCorridor) {
      const banner = document.getElementById('simCorridorBanner');
      const label  = document.getElementById('simCorridorLabel');
      if (banner && label) {
        label.textContent = qCorridor;
        banner.style.display = 'block';
      }
    }

    if (qMode && ['ambulance', 'delivery', 'commute'].includes(qMode)) {
      setSimVehicleMode(qMode);
    }

    if (qVehicles && document.getElementById('simVehicles')) {
      const v = Math.min(Math.max(parseInt(qVehicles), 10), 500);
      document.getElementById('simVehicles').value = v;
      document.getElementById('nVehVal').textContent = v;
    }

    if (qHour && document.getElementById('simHour')) {
      document.getElementById('simHour').value = qHour;
    }

    if (qWeather && document.getElementById('simWeather')) {
      document.getElementById('simWeather').value = qWeather;
    }

    if (qCorridor || qMode || qVehicles) {
      setTimeout(() => {
        runSimulation();
      }, 350);
    }
  }
});
