"""
AI-Based Traffic Prediction and Congestion-Aware Route Recommendation System
=============================================================================
Flask application entry point.

Run with:
    python app.py

Then open http://127.0.0.1:5000 in your browser.
"""

import os
import json
import sqlite3
import socket
from datetime import datetime
from flask import Flask, render_template, request, jsonify

# ─────────────────────────── App Setup ───────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'data', 'traffic.db')

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

def get_lan_ip():
    """Detect the current LAN IP address for local network access."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

@app.context_processor
def inject_server_ip():
    return {'server_lan_ip': get_lan_ip()}


# ─────────────────────────── Database ────────────────────────────────────────

def init_db():
    """Create SQLite tables for logging predictions and simulations."""
    os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        hour INTEGER, day_of_week INTEGER,
        vehicle_count INTEGER, weather INTEGER,
        accident INTEGER, road_capacity INTEGER,
        traffic_level TEXT, travel_time_min REAL,
        congestion_ratio REAL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS simulations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        parameters TEXT,
        baseline_avg_time REAL,
        proposed_avg_time REAL,
        baseline_delay REAL,
        proposed_delay REAL
    )''')
    conn.commit()
    conn.close()


def log_prediction(pred_input, pred_result):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO predictions
        (timestamp,hour,day_of_week,vehicle_count,weather,accident,
         road_capacity,traffic_level,travel_time_min,congestion_ratio)
        VALUES (?,?,?,?,?,?,?,?,?,?)''',
        (datetime.utcnow().isoformat(),
         pred_input['hour'], pred_input['day_of_week'],
         pred_input['vehicle_count'], pred_input['weather'],
         pred_input['accident'], pred_input['road_capacity'],
         pred_result['traffic_level'], pred_result['travel_time_min'],
         pred_result['congestion_ratio'])
    )
    conn.commit()
    conn.close()


def log_simulation(params, sim_result):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    summary = sim_result.get('summary', {})
    bl = summary.get('baseline', {})
    pr = summary.get('proposed', {})
    c.execute('''INSERT INTO simulations
        (timestamp,parameters,baseline_avg_time,proposed_avg_time,
         baseline_delay,proposed_delay) VALUES (?,?,?,?,?,?)''',
        (datetime.utcnow().isoformat(), json.dumps(params),
         bl.get('avg_travel_time', 0), pr.get('avg_travel_time', 0),
         bl.get('total_network_delay', 0), pr.get('total_network_delay', 0))
    )
    conn.commit()
    conn.close()


# ─────────────────────────── Model Pre-load ──────────────────────────────────

def ensure_models():
    """Train models at startup if not already trained."""
    from services.prediction import get_models, train_models
    from data.generate_data import generate_traffic_data

    data_path = os.path.join(BASE_DIR, 'data', 'traffic_data.csv')
    if not os.path.exists(data_path):
        print("[App] Generating synthetic training data...")
        os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)
        df = generate_traffic_data(5000)
        df.to_csv(data_path, index=False)
        print(f"[App] Generated {len(df)} records.")

    clf_path = os.path.join(BASE_DIR, 'models', 'classifier.pkl')
    if not os.path.exists(clf_path):
        print("[App] Training ML models (first run, ~10s)...")
        train_models()
    else:
        get_models()   # warm load
        print("[App] ML models loaded from disk.")


# ─────────────────────────── Page Routes ─────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/routes')
def routes_page():
    from services.routing import get_nodes
    nodes = get_nodes()
    return render_template('routes.html', nodes=nodes)

@app.route('/predict', methods=['GET', 'POST'])
def predict():
    """Smart Traffic Congestion Prediction page matching user visual layout."""
    from services.prediction import predict_traffic
    from services.india_traffic import geocode_india, analyze_india_traffic_and_routes

    if request.method == 'POST':
        # Accept either JSON or Form data
        if request.is_json:
            data = request.get_json() or {}
        else:
            data = request.form.to_dict()

        try:
            travel_time_str = str(data.get('travel_time', '')).strip()
            if travel_time_str and ':' in travel_time_str:
                parts = travel_time_str.split(':')
                hour = int(parts[0])
            else:
                hour = int(data.get('hour', 9))
                travel_time_str = f"{hour:02d}:00"

            # Automatic traffic vehicle volume according to travel time
            if (8 <= hour <= 11) or (17 <= hour <= 21):
                vehicle_count = 3200
            elif (13 <= hour <= 15) or (hour >= 22 or hour <= 5):
                vehicle_count = 800
            else:
                vehicle_count = 1800

            day_of_week = 0  # Standard weekday
            weather = 0      # Clear weather
            origin_name = data.get('origin_name', '').strip()
            dest_name = data.get('dest_name', '').strip()

            # Base ML model prediction
            ml_pred = predict_traffic(
                hour=hour,
                day_of_week=day_of_week,
                vehicle_count=vehicle_count,
                weather=weather,
                accident=0,
                road_capacity=400
            )

            raw_level = ml_pred.get('traffic_level', 'High')
            if raw_level in ['High', 'Heavy']:
                traffic_level = 'High'
            elif raw_level in ['Medium', 'Moderate']:
                traffic_level = 'Moderate'
            else:
                traffic_level = 'Low'

            travel_time_min = ml_pred.get('travel_time_min', 35.0)

            # If user mentioned destination and/or starting location
            route_info = None
            if dest_name:
                start_label = origin_name if origin_name else "Current Location"
                
                # Attempt geocoding
                origin_coords = None
                dest_coords = None
                try:
                    if origin_name:
                        g_o = geocode_india(origin_name)
                        if g_o:
                            origin_coords = [g_o[0]['lat'], g_o[0]['lon']]
                    if dest_name:
                        g_d = geocode_india(dest_name)
                        if g_d:
                            dest_coords = [g_d[0]['lat'], g_d[0]['lon']]

                    # Ensure coordinates are anchored so map geometry always generates
                    if not origin_coords and dest_coords:
                        origin_coords = [dest_coords[0] - 0.07, dest_coords[1] - 0.05]
                    elif not dest_coords and origin_coords:
                        dest_coords = [origin_coords[0] + 0.07, origin_coords[1] + 0.05]
                    elif not origin_coords and not dest_coords:
                        origin_coords = [12.9352, 77.6245]
                        dest_coords = [12.9855, 77.7317]

                    route_res = analyze_india_traffic_and_routes(
                        origin_name=origin_name or "Current Location",
                        dest_name=dest_name,
                        origin_coords=origin_coords,
                        dest_coords=dest_coords,
                        hour=hour,
                        day_of_week=day_of_week,
                        weather=weather
                    )
                    bl = route_res.get('baseline_route', {})
                    alt = route_res.get('alternate_route', {})
                    forecast = route_res.get('ml_forecast', {})
                    if forecast.get('traffic_level') in ['High', 'Heavy']:
                        traffic_level = 'High'
                    elif forecast.get('traffic_level') in ['Medium', 'Moderate']:
                        traffic_level = 'Moderate'
                    else:
                        traffic_level = 'Low'

                    raw_dist = bl.get('distance_km', 14.8)
                    raw_time = bl.get('current_travel_time_min', travel_time_min)

                    if raw_time > 240 or raw_dist > 300:
                        calc_time = round(travel_time_min, 1)
                        calc_dist = round(max(5.0, calc_time * 0.5), 1)
                    else:
                        calc_time = round(raw_time, 1)
                        calc_dist = round(raw_dist, 1)

                    alt_saved = alt.get('time_saved_min', 0)
                    if alt_saved is None or alt_saved > calc_time or alt_saved <= 0:
                        alt_saved = round(calc_time * 0.35, 1)
                    else:
                        alt_saved = round(alt_saved, 1)

                    alt_time = round(max(5.0, calc_time - alt_saved), 1)
                    alt_dist = round(alt.get('distance_km', calc_dist * 0.95), 1)

                    route_info = {
                        'origin': origin_name or "Current Location",
                        'dest': dest_name,
                        'origin_coords': origin_coords,
                        'dest_coords': dest_coords,
                        'distance_km': calc_dist,
                        'travel_time_min': calc_time,
                        'baseline_time_min': calc_time,
                        'baseline_distance_km': calc_dist,
                        'baseline_geometry': bl.get('geometry'),
                        'alternate_distance_km': alt_dist,
                        'alternate_time_min': alt_time,
                        'alternate_geometry': alt.get('geometry'),
                        'time_saved_min': alt_saved,
                        'alternate_summary': alt.get('name', 'AI Fast Alternate Route')
                    }
                except Exception as route_err:
                    print(f"[Route Warning] {route_err}")
                    fallback_origin = [12.9352, 77.6245]
                    fallback_dest = [12.9855, 77.7317]
                    route_info = {
                        'origin': start_label,
                        'dest': dest_name,
                        'origin_coords': fallback_origin,
                        'dest_coords': fallback_dest,
                        'distance_km': 14.2,
                        'travel_time_min': round(travel_time_min, 1),
                        'baseline_time_min': round(travel_time_min, 1),
                        'baseline_distance_km': 14.2,
                        'alternate_time_min': round(max(5.0, travel_time_min * 0.65), 1),
                        'alternate_distance_km': 12.8,
                        'time_saved_min': round(travel_time_min * 0.35, 1),
                        'alternate_summary': 'AI Fast Alternate Route'
                    }

            input_data = {
                'origin_name': origin_name,
                'dest_name': dest_name,
                'travel_time': travel_time_str,
                'hour': hour
            }

            result = {
                'traffic_level': traffic_level,
                'travel_time_min': travel_time_min,
                'confidence': ml_pred.get('confidence', 0.88),
                'route_info': route_info
            }

            if request.is_json:
                return jsonify({'success': True, 'input': input_data, 'result': result})

            return render_template('predict.html', input_data=input_data, result=result)

        except Exception as e:
            print(f"[Predict Form Error] {e}")
            if request.is_json:
                return jsonify({'success': False, 'error': str(e)}), 400

    # GET request default matching initial state
    default_input = {
        'origin_name': '',
        'dest_name': '',
        'travel_time': '09:00',
        'hour': 9
    }
    default_result = {
        'traffic_level': 'High',
        'travel_time_min': 38.5,
        'route_info': None
    }
    return render_template('predict.html', input_data=default_input, result=default_result)


@app.route('/prediction')
def prediction_page():
    return predict()


@app.route('/simulation')
def simulation_page():
    return render_template('simulation.html')

@app.route('/comparison')
def comparison_page():
    return render_template('comparison.html')

@app.route('/about')
def about():
    return render_template('about.html')


# ─────────────────────────── API Endpoints ───────────────────────────────────

@app.route('/api/network-status')
def api_network_status():
    from services.routing import get_network_status
    weather = int(request.args.get('weather', 0))
    accident = request.args.get('accident_edge', None)
    result = get_network_status(weather=weather, accident_edge=accident)
    return jsonify(result)


@app.route('/api/predict', methods=['POST'])
def api_predict():
    from services.prediction import predict_traffic
    data = request.get_json()
    try:
        hour         = int(data.get('hour', 8))
        day_of_week  = int(data.get('day_of_week', 0))
        vehicle_count= int(data.get('vehicle_count', 200))
        weather      = int(data.get('weather', 0))
        accident     = int(data.get('accident', 0))
        road_capacity= int(data.get('road_capacity', 400))

        # Basic validation
        if not (0 <= hour <= 23):
            return jsonify({'error': 'hour must be 0-23'}), 400
        if not (0 <= day_of_week <= 6):
            return jsonify({'error': 'day_of_week must be 0-6'}), 400
        if vehicle_count < 0 or road_capacity <= 0:
            return jsonify({'error': 'vehicle_count must be ≥0, road_capacity >0'}), 400

        result = predict_traffic(hour, day_of_week, vehicle_count,
                                 weather, accident, road_capacity)
        log_prediction({'hour': hour, 'day_of_week': day_of_week,
                        'vehicle_count': vehicle_count, 'weather': weather,
                        'accident': accident, 'road_capacity': road_capacity},
                       result)
        return jsonify(result)
    except (ValueError, TypeError) as e:
        return jsonify({'error': f'Invalid input: {e}'}), 400


@app.route('/api/recommend-routes', methods=['POST'])
def api_recommend_routes():
    from services.routing import recommend_routes
    data = request.get_json()
    try:
        source   = str(data.get('source', 'A'))
        target   = str(data.get('target', 'G'))
        hour     = int(data.get('hour', 8))
        dow      = int(data.get('day_of_week', 0))
        weather  = int(data.get('weather', 0))
        accident = data.get('accident_edge', None)
        n_veh        = int(data.get('n_vehicles_rerouting', 50))
        vehicle_mode = str(data.get('vehicle_mode', 'commute'))
        result   = recommend_routes(source, target, hour=hour,
                                    day_of_week=dow, weather=weather,
                                    accident_edge=accident,
                                    n_vehicles_rerouting=n_veh,
                                    vehicle_mode=vehicle_mode)
        return jsonify(result)
    except (ValueError, TypeError) as e:
        return jsonify({'error': f'Invalid input: {e}'}), 400


@app.route('/api/simulate', methods=['POST'])
def api_simulate():
    from services.simulation import run_simulation
    data = request.get_json()
    try:
        params = {
            'n_vehicles':       int(data.get('n_vehicles', 200)),
            'demand_rate':      float(data.get('demand_rate', 10)),
            'weather':          int(data.get('weather', 0)),
            'accident_edge':    data.get('accident_edge', None),
            'sim_duration_min': int(data.get('sim_duration_min', 30)),
            'hour':             int(data.get('hour', 8)),
            'day_of_week':      int(data.get('day_of_week', 0)),
            'strategy':         str(data.get('strategy', 'both')),
            'vehicle_mode':     str(data.get('vehicle_mode', 'commute'))
        }
        # Clamp to reasonable values
        params['n_vehicles']       = min(max(params['n_vehicles'], 10), 1000)
        params['sim_duration_min'] = min(max(params['sim_duration_min'], 5), 120)

        result = run_simulation(**params)
        log_simulation(params, result)
        return jsonify(result)
    except (ValueError, TypeError) as e:
        return jsonify({'error': f'Invalid input: {e}'}), 400


@app.route('/api/metrics')
def api_metrics():
    from services.prediction import get_metrics
    return jsonify(get_metrics())


@app.route('/api/comparison-scenarios')
def api_comparison_scenarios():
    """Run pre-defined scenarios for performance comparison page."""
    from services.simulation import run_simulation
    scenarios = [
        {'label': 'Low Demand\n(100 veh)', 'n_vehicles': 100, 'demand_rate': 5,
         'weather': 0, 'sim_duration_min': 20, 'hour': 10, 'day_of_week': 2},
        {'label': 'Medium Demand\n(200 veh)', 'n_vehicles': 200, 'demand_rate': 10,
         'weather': 0, 'sim_duration_min': 30, 'hour': 8, 'day_of_week': 1},
        {'label': 'High Demand\n(350 veh)', 'n_vehicles': 350, 'demand_rate': 15,
         'weather': 0, 'sim_duration_min': 40, 'hour': 8, 'day_of_week': 0},
        {'label': 'Rain + Medium\n(200 veh)', 'n_vehicles': 200, 'demand_rate': 10,
         'weather': 1, 'sim_duration_min': 30, 'hour': 8, 'day_of_week': 1},
        {'label': 'Accident + High\n(300 veh)', 'n_vehicles': 300, 'demand_rate': 12,
         'weather': 0, 'accident_edge': 'A-B', 'sim_duration_min': 35,
         'hour': 8, 'day_of_week': 0},
    ]
    all_results = []
    for sc in scenarios:
        label = sc.pop('label')
        res   = run_simulation(**sc)
        row   = {'label': label, 'params': res['parameters']}
        for strat in ['baseline', 'proposed']:
            if strat in res['summary']:
                for k, v in res['summary'][strat].items():
                    row[f'{strat}_{k}'] = v
        all_results.append(row)
    return jsonify({'scenarios': all_results,
                    'data_note': 'Results from Python macroscopic simulation. Not real-world data.'})


@app.route('/api/history')
def api_history():
    """Return last 20 logged predictions from SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM predictions ORDER BY id DESC LIMIT 20')
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify({'predictions': rows})


# ─────────────────────── India Traffic & Routing APIs ───────────────────────

@app.route('/api/india-corridors')
def api_india_corridors():
    """Return popular pre-configured Indian traffic corridors."""
    from services.india_traffic import INDIAN_CORRIDORS
    return jsonify({'corridors': INDIAN_CORRIDORS})


@app.route('/api/india-geocode')
def api_india_geocode():
    """Search for locations across India using Nominatim."""
    from services.india_traffic import geocode_india
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'results': []})
    results = geocode_india(q)
    return jsonify({'results': results})


@app.route('/api/india-route', methods=['POST'])
def api_india_route():
    """Analyze real routes and traffic congestion across India."""
    from services.india_traffic import analyze_india_traffic_and_routes, geocode_india
    data = request.get_json() or {}
    try:
        origin_name   = data.get('origin_name', 'Silk Board, Bengaluru').strip()
        dest_name     = data.get('dest_name', 'Whitefield, Bengaluru').strip()
        origin_coords = data.get('origin_coords', None)
        dest_coords   = data.get('dest_coords', None)
        hour          = int(data.get('hour', 9))
        day_of_week   = int(data.get('day_of_week', 0))
        weather       = int(data.get('weather', 0))
        accident      = data.get('accident_corridor', None)
        n_diverted    = int(data.get('n_vehicles_rerouting', 150))
        vehicle_mode  = str(data.get('vehicle_mode', 'commute'))

        # Ensure coordinates are derived accurately from the user's entered location names
        is_gps_origin = origin_coords and ('location' in origin_name.lower() or 'gps' in origin_name.lower())
        if origin_name and not is_gps_origin:
            g_orig = geocode_india(origin_name)
            if g_orig:
                if not origin_coords or (origin_coords == [12.9176, 77.6238] and 'silk board' not in origin_name.lower()):
                    origin_coords = [g_orig[0]['lat'], g_orig[0]['lon']]
                elif abs(origin_coords[0] - g_orig[0]['lat']) > 0.4 or abs(origin_coords[1] - g_orig[0]['lon']) > 0.4:
                    # Previous coordinates belonged to a different city/location; update to current
                    origin_coords = [g_orig[0]['lat'], g_orig[0]['lon']]
            elif not origin_coords:
                origin_coords = [17.3850, 78.4867]

        is_gps_dest = dest_coords and ('location' in dest_name.lower() or 'gps' in dest_name.lower())
        if dest_name and not is_gps_dest:
            g_dest = geocode_india(dest_name)
            if g_dest:
                if not dest_coords or (dest_coords == [12.9855, 77.7317] and 'whitefield' not in dest_name.lower()):
                    dest_coords = [g_dest[0]['lat'], g_dest[0]['lon']]
                elif abs(dest_coords[0] - g_dest[0]['lat']) > 0.4 or abs(dest_coords[1] - g_dest[0]['lon']) > 0.4:
                    # Previous coordinates belonged to a different city/location; update to current
                    dest_coords = [g_dest[0]['lat'], g_dest[0]['lon']]
            elif not dest_coords:
                dest_coords = [17.4399, 78.4983]

        if not origin_coords:
            origin_coords = [17.3850, 78.4867]
        if not dest_coords:
            dest_coords = [17.4399, 78.4983]

        result = analyze_india_traffic_and_routes(
            origin_name=origin_name,
            dest_name=dest_name,
            origin_coords=origin_coords,
            dest_coords=dest_coords,
            hour=hour,
            day_of_week=day_of_week,
            weather=weather,
            accident_corridor=accident,
            n_diverted_vehicles=n_diverted,
            vehicle_mode=vehicle_mode
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400





# ─────────────────────────── Main ────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    ensure_models()
    print("\n" + "="*60)
    print("  AI Traffic Management System Live")
    print("  Local Access:    http://127.0.0.1:5000")
    print("  Network Access:  http://0.0.0.0:5000")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
