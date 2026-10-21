"""
Routing Service — Congestion-Aware Route Recommendation
=========================================================
Implements a small road network using NetworkX and compares two strategies:

  A. BASELINE   : Dijkstra on current estimated travel time (fastest now)
  B. PROPOSED   : Shortest path using PREDICTED future travel time +
                  estimated impact of adding vehicles to that route
                  (congestion-cost model documented below)

Network:
  8 named nodes (intersections / places) with 14 directed edges.
  Each edge has: base_time (min), capacity, and current_vehicles.

Congestion-cost model (BPR function — Bureau of Public Roads):
  travel_time(v) = free_flow_time * (1 + alpha * (v/capacity)^beta)
  alpha=0.15, beta=4  — standard BPR parameters.

Rerouting impact:
  When N_extra vehicles are added to an alternative route, each edge on
  that route gets N_extra more vehicles. The updated travel time is
  recalculated with the BPR formula, then summed across the path.
"""

import networkx as nx
import numpy as np
from services.prediction import predict_traffic, LABEL_MAP, COLOR_MAP

# BPR parameters (Bureau of Public Roads)
BPR_ALPHA = 0.15
BPR_BETA  = 4.0

# ─────────────────────────── Road Network ────────────────────────────────────

def _bpr(free_flow: float, vehicles: float, capacity: float) -> float:
    """Bureau of Public Roads travel-time function."""
    ratio = vehicles / max(capacity, 1)
    return free_flow * (1 + BPR_ALPHA * (ratio ** BPR_BETA))


NODES = {
    'A': {'name': 'City Centre',      'lat': 51.505,  'lon': -0.090},
    'B': {'name': 'North Junction',   'lat': 51.515,  'lon': -0.085},
    'C': {'name': 'East Gateway',     'lat': 51.508,  'lon': -0.070},
    'D': {'name': 'South Ring',       'lat': 51.495,  'lon': -0.080},
    'E': {'name': 'West Bypass',      'lat': 51.503,  'lon': -0.108},
    'F': {'name': 'Airport Link',     'lat': 51.520,  'lon': -0.100},
    'G': {'name': 'Riverside Road',   'lat': 51.498,  'lon': -0.060},
    'H': {'name': 'Industrial Zone',  'lat': 51.490,  'lon': -0.095},
}

# (from, to, free_flow_min, capacity_veh/hr, current_vehicles)
EDGES_RAW = [
    ('A','B', 6,  400, 280),
    ('A','C', 9,  350, 310),
    ('A','E', 8,  300, 150),
    ('A','D', 7,  300, 260),
    ('B','F', 5,  350, 200),
    ('B','C', 7,  300, 200),
    ('C','G', 6,  250, 180),
    ('D','H', 8,  300, 200),
    ('D','G', 10, 200, 120),
    ('E','F', 9,  250, 100),
    ('E','H', 11, 200,  80),
    ('F','G', 8,  350, 220),
    ('G','H', 6,  200, 150),  # reversed also
    ('H','G', 6,  200, 140),
]


def build_graph(weather: int = 0, accident_edge: str = None) -> nx.DiGraph:
    """
    Build the road-network graph.
    weather: 0=Clear,1=Rain,2=Fog,3=Snow
    accident_edge: edge key like 'A-B' that has an accident
    """
    weather_mult = {0: 1.0, 1: 1.20, 2: 1.35, 3: 1.55}[weather]
    G = nx.DiGraph()

    for node_id, attrs in NODES.items():
        G.add_node(node_id, **attrs)

    for u, v, ff, cap, curr_veh in EDGES_RAW:
        acc = 1.0
        if accident_edge and accident_edge in (f'{u}-{v}', f'{v}-{u}'):
            acc = 2.5   # accident roughly doubles+ travel time
        curr_time = _bpr(ff * weather_mult * acc, curr_veh, cap)
        congestion_ratio = curr_veh / cap

        G.add_edge(u, v,
                   free_flow=ff,
                   capacity=cap,
                   current_vehicles=curr_veh,
                   current_time=round(curr_time, 2),
                   congestion_ratio=round(congestion_ratio, 3),
                   has_accident=(accident_edge in (f'{u}-{v}', f'{v}-{u}')) if accident_edge else False,
                   weather_mult=weather_mult,
                   acc_mult=acc
                   )
        # Add reverse edge with slightly different load
        rev_veh = max(10, int(curr_veh * 0.75))
        rev_time = _bpr(ff * weather_mult, rev_veh, cap)
        if not G.has_edge(v, u):
            G.add_edge(v, u,
                       free_flow=ff,
                       capacity=cap,
                       current_vehicles=rev_veh,
                       current_time=round(rev_time, 2),
                       congestion_ratio=round(rev_veh/cap, 3),
                       has_accident=False,
                       weather_mult=weather_mult,
                       acc_mult=1.0
                       )
    return G


def _path_info(G: nx.DiGraph, path: list, extra_vehicles: int = 0) -> dict:
    """Aggregate edge data along a path, optionally adding extra vehicles."""
    total_time = 0.0
    edges_info = []
    for u, v in zip(path[:-1], path[1:]):
        e = G[u][v]
        veh = e['current_vehicles'] + extra_vehicles
        t   = _bpr(e['free_flow'] * e['weather_mult'] * e['acc_mult'], veh, e['capacity'])
        cr  = round(veh / e['capacity'], 3)
        level = 'Low' if cr < 0.4 else ('Medium' if cr < 0.75 else 'High')
        total_time += t
        edges_info.append({
            'from': u, 'to': v,
            'from_name': NODES[u]['name'], 'to_name': NODES[v]['name'],
            'travel_time': round(t, 2),
            'current_vehicles': veh,
            'capacity': e['capacity'],
            'congestion_ratio': cr,
            'congestion_level': level,
            'congestion_color': COLOR_MAP[level],
            'has_accident': e['has_accident']
        })
    return {'path': path, 'total_time': round(total_time, 2), 'edges': edges_info}


# ─────────────────────────── Route Recommendation ────────────────────────────

def recommend_routes(source: str, target: str,
                     hour: int = 8, day_of_week: int = 0,
                     weather: int = 0, accident_edge: str = None,
                     n_vehicles_rerouting: int = 50,
                     vehicle_mode: str = 'commute'):
    """
    Find routes and compare BASELINE vs PROPOSED strategies.

    Returns a dict with:
      - all_routes : up to 3 simple paths
      - baseline   : route chosen by baseline
      - proposed   : route chosen by proposed method
      - explanation: text explaining proposed choice
    """
    if source not in NODES or target not in NODES:
        return {'error': f'Unknown node. Valid nodes: {list(NODES.keys())}'}

    G = build_graph(weather=weather, accident_edge=accident_edge)

    # Find up to 3 simple paths
    try:
        all_simple = list(nx.simple_paths.all_simple_paths(G, source, target, cutoff=6))
    except nx.NetworkXNoPath:
        return {'error': f'No path from {source} to {target}'}

    if not all_simple:
        return {'error': f'No path from {source} to {target}'}

    # Limit to 3 shortest by hop count
    all_simple.sort(key=len)
    all_simple = all_simple[:4]

    # ── Build current-time paths ──────────────────────────────────────────────
    routes = []
    for path in all_simple:
        info = _path_info(G, path, extra_vehicles=0)
        info['path_str'] = ' → '.join(NODES[n]['name'] for n in path)
        info['node_ids'] = path
        # Get coords for map
        info['coords'] = [{'lat': NODES[n]['lat'], 'lon': NODES[n]['lon']} for n in path]
        routes.append(info)

    # ── STRATEGY A: BASELINE ──────────────────────────────────────────────────
    baseline_route = min(routes, key=lambda r: r['total_time'])

    # ── STRATEGY B: PROPOSED ─────────────────────────────────────────────────
    # Step 1: Predict future travel times on each edge using ML model
    future_routes = []
    for r in routes:
        future_total = 0.0
        for e in r['edges']:
            pred = predict_traffic(
                hour=hour, day_of_week=day_of_week,
                vehicle_count=e['current_vehicles'],
                weather=weather,
                accident=int(e['has_accident']),
                road_capacity=e['capacity']
            )
            future_total += pred['travel_time_min']
        future_routes.append({'path': r, 'future_time': round(future_total, 2)})

    # Determine mission impact weight gamma
    if vehicle_mode == 'ambulance':
        gamma = 0.0  # Emergency ambulance: 0 penalty for downstream delay; patient arrival time is top priority
        mission_prefix = "🚑 [Emergency Ambulance Priority] "
    elif vehicle_mode == 'delivery':
        gamma = 0.25 # Quick delivery: moderate penalty, prioritizing driver speed
        mission_prefix = "🛵 [Quick Delivery Express] "
    else:
        gamma = 0.50 # General commuter: balances individual time with community delay
        mission_prefix = "🚗 [City Commuter Flow] "

    # Step 2: Estimate impact of diverting n_vehicles to each route
    impact_routes = []
    for fr in future_routes:
        path = fr['path']['node_ids']
        impacted = _path_info(G, path, extra_vehicles=n_vehicles_rerouting)
        net_impact = impacted['total_time'] - fr['path']['total_time']
        composite_score = fr['future_time'] + gamma * max(net_impact, 0)
        impact_routes.append({
            'path': fr['path'],
            'future_time': fr['future_time'],
            'network_impact': round(net_impact, 2),
            'composite_score': round(composite_score, 2)
        })

    proposed_best = min(impact_routes, key=lambda r: r['composite_score'])
    proposed_route = proposed_best['path']

    # ── Explanation ───────────────────────────────────────────────────────────
    bl_name  = baseline_route['path_str']
    pr_name  = proposed_route['path_str']
    bl_time  = baseline_route['total_time']
    pr_fut   = proposed_best['future_time']
    pr_imp   = proposed_best['network_impact']

    if bl_name == pr_name:
        explanation = (
            f"{mission_prefix}Both strategies agree: '{bl_name}' is optimal. "
            f"Current travel time is {bl_time} min. "
            f"Its predicted future travel time ({pr_fut} min) remains the lowest, "
            f"and adding {n_vehicles_rerouting} extra vehicles increases network "
            f"delay by only {pr_imp} min — the least among all alternatives."
        )
    else:
        explanation = (
            f"{mission_prefix}The baseline recommends '{bl_name}' (fastest now: {bl_time} min), "
            f"but the proposed method recommends '{pr_name}'. "
            f"Predicted future travel time on '{pr_name}' is {pr_fut} min, "
            f"and diverting {n_vehicles_rerouting} vehicles adds only {pr_imp} min "
            f"of additional delay across the network — lower impact than '{bl_name}'."
        )

    # Edge data for map rendering (all routes with congestion colours)
    all_edges_map = {}
    for u, v, data in G.edges(data=True):
        key = f'{u}-{v}'
        cr = data['congestion_ratio']
        level = 'Low' if cr < 0.4 else ('Medium' if cr < 0.75 else 'High')
        all_edges_map[key] = {
            'from': u, 'to': v,
            'from_lat': NODES[u]['lat'], 'from_lon': NODES[u]['lon'],
            'to_lat':   NODES[v]['lat'], 'to_lon':   NODES[v]['lon'],
            'current_time': data['current_time'],
            'congestion_ratio': cr,
            'congestion_level': level,
            'congestion_color': COLOR_MAP[level],
            'has_accident': data['has_accident']
        }

    return {
        'source': source,
        'target': target,
        'source_name': NODES[source]['name'],
        'target_name': NODES[target]['name'],
        'all_routes':  routes,
        'baseline':    baseline_route,
        'proposed': {
            'path': proposed_route,
            'future_time': proposed_best['future_time'],
            'network_impact': proposed_best['network_impact'],
            'composite_score': proposed_best['composite_score']
        },
        'explanation': explanation,
        'all_edges_map': all_edges_map,
        'nodes': NODES,
        'n_vehicles_rerouting': n_vehicles_rerouting,
        'parameters': {
            'hour': hour, 'day_of_week': day_of_week,
            'weather': weather, 'accident_edge': accident_edge,
            'bpr_alpha': BPR_ALPHA, 'bpr_beta': BPR_BETA
        },
        'data_note': ('Road network is synthetic for demonstration. '
                      'Travel times use the BPR model, not live traffic data.')
    }


def get_nodes():
    return NODES


def get_network_status(weather: int = 0, accident_edge: str = None):
    """Return all edges with current congestion for dashboard map."""
    G = build_graph(weather=weather, accident_edge=accident_edge)
    edges = []
    for u, v, data in G.edges(data=True):
        cr = data['congestion_ratio']
        level = 'Low' if cr < 0.4 else ('Medium' if cr < 0.75 else 'High')
        edges.append({
            'from': u, 'to': v,
            'from_name': NODES[u]['name'], 'to_name': NODES[v]['name'],
            'from_lat': NODES[u]['lat'], 'from_lon': NODES[u]['lon'],
            'to_lat':   NODES[v]['lat'], 'to_lon':   NODES[v]['lon'],
            'current_time': data['current_time'],
            'current_vehicles': data['current_vehicles'],
            'capacity': data['capacity'],
            'congestion_ratio': cr,
            'congestion_level': level,
            'congestion_color': COLOR_MAP[level],
            'has_accident': data['has_accident']
        })
    nodes_list = [{'id': k, **v} for k, v in NODES.items()]
    return {'edges': edges, 'nodes': nodes_list}
