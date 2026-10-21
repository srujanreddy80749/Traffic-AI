"""
Traffic Simulation Service
============================
Python-based simulation (SUMO not used — see README for rationale).

Simulates traffic flow across the synthetic road network for a given
duration. Uses a discrete time-step model:
  - Each step represents 1 minute.
  - Vehicles enter the network according to a demand rate.
  - Road congestion is updated using the BPR function.
  - Baseline vs Proposed routing strategies are compared.

Output metrics (per scenario):
  - Average travel time (min)
  - Average waiting time (min)
  - Total network delay (vehicle-minutes above free-flow)
  - Max congestion ratio
  - Number of vehicles affected by congestion (ratio > 0.75)

NOTE: This is a simplified macroscopic simulation, NOT microscopic
      (no individual vehicle movement). Results are indicative only.
"""

import random
import copy
import numpy as np
from services.routing import build_graph, recommend_routes, NODES, _path_info, _bpr

random.seed(42)
np.random.seed(42)


WEATHER_NAMES = {0: 'Clear', 1: 'Rain', 2: 'Fog', 3: 'Snow'}
DAY_NAMES = {0:'Mon',1:'Tue',2:'Wed',3:'Thu',4:'Fri',5:'Sat',6:'Sun'}


def _edge_key(u, v):
    return f'{u}-{v}'


def run_simulation(
    n_vehicles:       int   = 200,
    demand_rate:      float = 10.0,   # vehicles entering per minute
    weather:          int   = 0,
    accident_edge:    str   = None,
    sim_duration_min: int   = 60,
    hour:             int   = 8,
    day_of_week:      int   = 0,
    strategy:         str   = 'both',  # 'baseline', 'proposed', 'both'
    vehicle_mode:     str   = 'commute'
) -> dict:
    """
    Run a macroscopic traffic simulation.
    
    Returns dict with 'baseline' and/or 'proposed' metric dicts,
    and a time-series for charting.
    """
    results = {}

    # Common graph for initial state
    G0 = build_graph(weather=weather, accident_edge=accident_edge)

    # OD pairs for simulation (random source/dest pairs)
    node_ids = list(NODES.keys())
    od_pairs = []
    for _ in range(n_vehicles):
        s = random.choice(node_ids)
        t = random.choice([x for x in node_ids if x != s])
        od_pairs.append((s, t))

    strategies_to_run = ['baseline', 'proposed'] if strategy == 'both' else [strategy]

    for strat in strategies_to_run:
        result = _simulate_strategy(
            G0, od_pairs, strat, n_vehicles, demand_rate, weather,
            accident_edge, sim_duration_min, hour, day_of_week,
            vehicle_mode=vehicle_mode
        )
        results[strat] = result

    # Summary comparison
    summary = {}
    for strat in strategies_to_run:
        r = results[strat]
        summary[strat] = {
            'avg_travel_time':  r['avg_travel_time'],
            'avg_waiting_time': r['avg_waiting_time'],
            'total_network_delay': r['total_network_delay'],
            'max_congestion':   r['max_congestion'],
            'vehicles_congested': r['vehicles_congested'],
            'vehicles_completed': r['vehicles_completed'],
            'vehicle_mode': vehicle_mode
        }

    return {
        'results':    results,
        'summary':    summary,
        'parameters': {
            'n_vehicles': n_vehicles,
            'demand_rate': demand_rate,
            'weather': weather,
            'weather_name': WEATHER_NAMES.get(weather, 'Unknown'),
            'accident_edge': accident_edge,
            'sim_duration_min': sim_duration_min,
            'hour': hour,
            'day_of_week': day_of_week,
            'day_name': DAY_NAMES.get(day_of_week, '?'),
            'vehicle_mode': vehicle_mode
        },
        'data_note': (
            'Python macroscopic simulation. NOT a SUMO or real-world simulation. '
            'Results are approximate and for educational/comparison purposes only.'
        )
    }


def _simulate_strategy(G0, od_pairs, strategy, n_vehicles, demand_rate,
                       weather, accident_edge, duration, hour, day_of_week,
                       vehicle_mode='commute'):
    """Simulate one strategy and collect metrics."""
    G = copy.deepcopy(G0)

    # edge_load: additional vehicles added by this simulation run
    edge_load = {_edge_key(u, v): 0 for u, v in G.edges()}

    travel_times   = []
    waiting_times  = []
    time_series    = []   # (minute, avg_congestion)
    completed      = 0
    congested_veh  = 0

    vehicles_per_step = max(1, int(demand_rate))

    for t in range(duration):
        step_veh = min(vehicles_per_step, n_vehicles - completed)
        if step_veh <= 0:
            break

        for _ in range(step_veh):
            if completed >= len(od_pairs):
                break
            s, tgt = od_pairs[completed]
            completed += 1

            # Choose route based on strategy
            if strategy == 'baseline':
                # Shortest current time path
                try:
                    path = nx_shortest(G, s, tgt)
                except Exception:
                    continue
            else:  # proposed
                # Use recommend_routes proposed path
                rec = recommend_routes(s, tgt, hour=hour, day_of_week=day_of_week,
                                       weather=weather, accident_edge=accident_edge,
                                       n_vehicles_rerouting=vehicles_per_step,
                                       vehicle_mode=vehicle_mode)
                if 'error' in rec:
                    continue
                path = rec['proposed']['path']['node_ids']

            # Calculate travel time on chosen path
            path_info = _path_info(G, path, extra_vehicles=0)
            tt = path_info['total_time']

            # Free-flow time
            ff_time = sum(G[u][v]['free_flow'] for u, v in zip(path[:-1], path[1:]))
            wait = max(0, tt - ff_time)

            travel_times.append(tt)
            waiting_times.append(wait)

            # Update edge loads (add vehicles to route)
            for u, v in zip(path[:-1], path[1:]):
                key = _edge_key(u, v)
                if key in edge_load:
                    edge_load[key] += 1
                    new_veh = G[u][v]['current_vehicles'] + edge_load[key]
                    new_time = _bpr(G[u][v]['free_flow'] * G[u][v]['weather_mult']
                                    * G[u][v]['acc_mult'], new_veh, G[u][v]['capacity'])
                    G[u][v]['current_time'] = new_time
                    G[u][v]['current_vehicles'] = new_veh
                    G[u][v]['congestion_ratio'] = min(new_veh / G[u][v]['capacity'], 2.0)

            cr_sum = G[u][v]['congestion_ratio']
            if cr_sum > 0.75:
                congested_veh += 1

        # Record snapshot
        avg_cr = np.mean([G[u][v]['congestion_ratio'] for u, v in G.edges()])
        time_series.append({'minute': t, 'avg_congestion': round(float(avg_cr), 3)})

    # Aggregate metrics
    if not travel_times:
        travel_times = [0]
    if not waiting_times:
        waiting_times = [0]

    all_ff = sum(G[u][v]['free_flow'] for u, v in G.edges())
    all_curr = sum(G[u][v]['current_time'] for u, v in G.edges())
    total_delay = max(0, all_curr - all_ff)
    max_cong = max(G[u][v]['congestion_ratio'] for u, v in G.edges())

    return {
        'avg_travel_time':    round(float(np.mean(travel_times)), 2),
        'avg_waiting_time':   round(float(np.mean(waiting_times)), 2),
        'total_network_delay': round(float(total_delay), 2),
        'max_congestion':     round(float(max_cong), 3),
        'vehicles_congested': congested_veh,
        'vehicles_completed': completed,
        'time_series':        time_series,
        'strategy':           strategy
    }


def nx_shortest(G, source, target):
    """Dijkstra on current_time weights."""
    import networkx as nx
    path = nx.dijkstra_path(G, source, target, weight='current_time')
    return path


def run_scenario_comparison(scenarios: list) -> dict:
    """
    Run multiple simulation scenarios and return comparison data.
    Each scenario is a dict of kwargs for run_simulation.
    Returns list of scenario results for chart rendering.
    """
    all_results = []
    for i, sc in enumerate(scenarios):
        label = sc.pop('label', f'Scenario {i+1}')
        res   = run_simulation(**sc)
        row   = {'label': label}
        for strat in ['baseline', 'proposed']:
            if strat in res['summary']:
                for k, v in res['summary'][strat].items():
                    row[f'{strat}_{k}'] = v
        row['parameters'] = res['parameters']
        all_results.append(row)
    return {'scenarios': all_results}
