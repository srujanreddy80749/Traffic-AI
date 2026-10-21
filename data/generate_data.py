"""
Synthetic Traffic Dataset Generator
====================================
Generates a realistic synthetic traffic dataset for training the ML model.
This dataset is NOT real-world data. It is documented as synthetic.
Source: Procedurally generated using domain-knowledge-based rules.
"""

import pandas as pd
import numpy as np
import os

np.random.seed(42)

def generate_traffic_data(n_samples=5000):
    """
    Generate synthetic traffic records with realistic correlations.
    
    Features:
        hour         - Hour of day (0-23)
        day_of_week  - 0=Monday ... 6=Sunday
        vehicle_count- Number of vehicles on road segment (0-500)
        weather      - 0=Clear, 1=Rain, 2=Fog, 3=Snow
        accident     - 0=None, 1=Accident/closure present
        road_capacity- Max vehicle capacity of road segment (100-600)
        
    Targets:
        traffic_level  - 0=Low, 1=Medium, 2=High
        travel_time_min- Estimated travel time in minutes (1-120)
    """
    hours = np.random.randint(0, 24, n_samples)
    days = np.random.randint(0, 7, n_samples)
    weather = np.random.choice([0, 1, 2, 3], n_samples, p=[0.65, 0.20, 0.10, 0.05])
    accident = np.random.choice([0, 1], n_samples, p=[0.92, 0.08])
    road_capacity = np.random.choice([100, 200, 300, 400, 500, 600], n_samples)

    # Rush hours: 7-9 AM and 5-8 PM on weekdays
    peak_factor = np.where(
        ((hours >= 7) & (hours <= 9) & (days < 5)) |
        ((hours >= 17) & (hours <= 20) & (days < 5)),
        1.8, 1.0
    )
    # Weekend factor
    weekend_factor = np.where(days >= 5, 0.65, 1.0)
    # Night factor
    night_factor = np.where((hours >= 23) | (hours <= 5), 0.35, 1.0)

    base_demand = road_capacity * 0.45
    vehicle_count = np.clip(
        base_demand * peak_factor * weekend_factor * night_factor +
        np.random.normal(0, road_capacity * 0.08, n_samples),
        10, road_capacity * 1.1
    ).astype(int)

    # Weather increases travel time
    weather_delay = {0: 1.0, 1: 1.25, 2: 1.40, 3: 1.60}
    weather_mult = np.array([weather_delay[w] for w in weather])

    # Accident significantly delays travel
    accident_mult = np.where(accident == 1, 2.2, 1.0)

    # Base travel time depends on congestion ratio
    congestion_ratio = vehicle_count / road_capacity
    base_time = 5 + (congestion_ratio ** 1.6) * 90  # minutes

    travel_time = np.clip(
        base_time * weather_mult * accident_mult + np.random.normal(0, 2, n_samples),
        1, 120
    )

    # Traffic level classification
    traffic_level = np.select(
        [congestion_ratio < 0.4, congestion_ratio < 0.75],
        [0, 1],
        default=2
    )

    df = pd.DataFrame({
        'hour': hours,
        'day_of_week': days,
        'vehicle_count': vehicle_count,
        'weather': weather,
        'accident': accident,
        'road_capacity': road_capacity,
        'congestion_ratio': np.round(congestion_ratio, 3),
        'traffic_level': traffic_level,
        'travel_time_min': np.round(travel_time, 1)
    })
    return df


if __name__ == '__main__':
    df = generate_traffic_data(5000)
    out_path = os.path.join(os.path.dirname(__file__), 'traffic_data.csv')
    df.to_csv(out_path, index=False)
    print(f"Generated {len(df)} records -> {out_path}")
    print(df.describe())
    print("\nTraffic level distribution:")
    print(df['traffic_level'].value_counts().sort_index()
          .rename({0: 'Low', 1: 'Medium', 2: 'High'}))
