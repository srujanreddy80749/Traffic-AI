"""
India Traffic & Route Recommendation Service
============================================
Provides real-world location geocoding, driving route geometry (OSRM / OpenStreetMap),
vehicle count estimation, traffic congestion modeling (BPR), and AI alternate route suggestions
for any city, highway, or corridor across India.
"""

import json
import math
import random
import urllib.parse
import urllib.request
from typing import Dict, Any, List, Tuple
from services.prediction import predict_traffic

# Pre-cached popular Indian high-traffic corridors for instant zero-latency loading
INDIAN_CORRIDORS = [
    {
        "id": "blr_silkboard_whitefield",
        "city": "Bengaluru",
        "title": "Silk Board Junction ➔ Whitefield ITPL",
        "origin_name": "Central Silk Board, Bengaluru",
        "origin_coords": [12.9176, 77.6238],
        "dest_name": "ITPL Main Road, Whitefield, Bengaluru",
        "dest_coords": [12.9855, 77.7317],
        "bottleneck_name": "Marathahalli / Bellandur Outer Ring Road",
        "typical_vehicles_peak": 2600,
        "capacity": 2200,
    },
    {
        "id": "blr_ecity_mgroad",
        "city": "Bengaluru",
        "title": "Electronic City ➔ MG Road",
        "origin_name": "Electronic City Phase 1, Bengaluru",
        "origin_coords": [12.8452, 77.6602],
        "dest_name": "MG Road Metro, Bengaluru",
        "dest_coords": [12.9756, 77.6066],
        "bottleneck_name": "Hosur Road Toll / Madiwala Checkpost",
        "typical_vehicles_peak": 2800,
        "capacity": 2400,
    },
    {
        "id": "mum_bkc_andheri",
        "city": "Mumbai",
        "title": "Bandra Kurla Complex (BKC) ➔ Andheri East",
        "origin_name": "BKC Diamond District, Mumbai",
        "origin_coords": [19.0657, 72.8687],
        "dest_name": "Chhatrapati Shivaji Maharaj Terminus / Andheri East, Mumbai",
        "dest_coords": [19.1197, 72.8468],
        "bottleneck_name": "Western Express Highway (Kalanagar Junction)",
        "typical_vehicles_peak": 3200,
        "capacity": 2600,
    },
    {
        "id": "del_cp_cybercity",
        "city": "Delhi NCR",
        "title": "Connaught Place ➔ DLF Cyber City (Gurugram)",
        "origin_name": "Connaught Place Inner Circle, New Delhi",
        "origin_coords": [28.6304, 77.2177],
        "dest_name": "DLF Cyber City, Gurugram, Haryana",
        "dest_coords": [28.4950, 77.0895],
        "bottleneck_name": "NH-48 Sirhaul Border / Mahipalpur Underpass",
        "typical_vehicles_peak": 3500,
        "capacity": 2800,
    },
    {
        "id": "del_noida_aiims",
        "city": "Delhi NCR",
        "title": "Noida Sector 18 ➔ AIIMS Ring Road",
        "origin_name": "Sector 18 Atta Market, Noida",
        "origin_coords": [28.5708, 77.3260],
        "dest_name": "AIIMS Ansari Nagar, Ring Road, New Delhi",
        "dest_coords": [28.5672, 77.2100],
        "bottleneck_name": "DND Flyway & Ashram Chowk Underpass",
        "typical_vehicles_peak": 3100,
        "capacity": 2500,
    },
    {
        "id": "chn_guindy_omr",
        "city": "Chennai",
        "title": "Guindy Kathipara ➔ OMR IT Corridor",
        "origin_name": "Kathipara Junction, Guindy, Chennai",
        "origin_coords": [13.0067, 80.2033],
        "dest_name": "Tidel Park / OMR Thoraipakkam, Chennai",
        "dest_coords": [12.9698, 80.2435],
        "bottleneck_name": "Madhya Kailash & Thiruvanmiyur Signal",
        "typical_vehicles_peak": 2700,
        "capacity": 2100,
    },
    {
        "id": "hyd_hitec_gachibowli",
        "city": "Hyderabad",
        "title": "Hitec City Cyber Towers ➔ Mehdipatnam",
        "origin_name": "Cyber Towers, Hitec City, Hyderabad",
        "origin_coords": [17.4504, 78.3808],
        "dest_name": "Mehdipatnam Junction, Hyderabad",
        "dest_coords": [17.3916, 78.4419],
        "bottleneck_name": "Tolichowki Flyover & Gachibowli ORR Junction",
        "typical_vehicles_peak": 2900,
        "capacity": 2300,
    },
    {
        "id": "pune_hinjawadi_shivaji",
        "city": "Pune",
        "title": "Hinjawadi IT Park ➔ Shivajinagar",
        "origin_name": "Hinjawadi Phase 1, Pune",
        "origin_coords": [18.5913, 73.7389],
        "dest_name": "Shivajinagar Bus Station, Pune",
        "dest_coords": [18.5314, 73.8446],
        "bottleneck_name": "Wakad Bridge & University Road Flyover",
        "typical_vehicles_peak": 2500,
        "capacity": 2000,
    },
    {
        "id": "kol_howrah_saltlake",
        "city": "Kolkata",
        "title": "Howrah Station ➔ Salt Lake Sector V",
        "origin_name": "Howrah Railway Station, Howrah",
        "origin_coords": [22.5830, 88.3426],
        "dest_name": "Sector V Electronics Complex, Salt Lake, Kolkata",
        "dest_coords": [22.5735, 88.4331],
        "bottleneck_name": "Maa Flyover & EM Bypass Junction",
        "typical_vehicles_peak": 2600,
        "capacity": 2100,
    }
]

# Fast in-memory cache for common landmark searches in India
FAST_GEOCODE_CACHE = {
    # Hyderabad & Telangana (Top Priority)
    "hyderabad": {"name": "Hyderabad City Center, Telangana", "lat": 17.3850, "lon": 78.4867},
    "secunderabad": {"name": "Secunderabad Railway Station, Telangana", "lat": 17.4399, "lon": 78.4983},
    "hitec city": {"name": "Cyber Towers, Hitec City, Hyderabad", "lat": 17.4504, "lon": 78.3808},
    "cyber towers": {"name": "Cyber Towers, Hitec City, Hyderabad", "lat": 17.4504, "lon": 78.3808},
    "gachibowli": {"name": "Gachibowli ORR Junction, Hyderabad", "lat": 17.4401, "lon": 78.3489},
    "kukatpally": {"name": "Kukatpally Housing Board (KPHB), Hyderabad", "lat": 17.4875, "lon": 78.3953},
    "kphb": {"name": "KPHB Colony, Kukatpally, Hyderabad", "lat": 17.4938, "lon": 78.3995},
    "madhapur": {"name": "Madhapur IT Zone, Hyderabad", "lat": 17.4483, "lon": 78.3915},
    "kondapur": {"name": "Kondapur Botanical Garden, Hyderabad", "lat": 17.4699, "lon": 78.3578},
    "banjara hills": {"name": "Banjara Hills Road No 1, Hyderabad", "lat": 17.4156, "lon": 78.4487},
    "jubilee hills": {"name": "Jubilee Hills Checkpost, Hyderabad", "lat": 17.4319, "lon": 78.4073},
    "ameerpet": {"name": "Ameerpet Metro Junction, Hyderabad", "lat": 17.4375, "lon": 78.4482},
    "begumpet": {"name": "Begumpet Airport Road, Hyderabad", "lat": 17.4448, "lon": 78.4682},
    "mehdipatnam": {"name": "Mehdipatnam Bus Stand, Hyderabad", "lat": 17.3916, "lon": 78.4419},
    "charminar": {"name": "Charminar Old City, Hyderabad", "lat": 17.3616, "lon": 78.4747},
    "dilsukhnagar": {"name": "Dilsukhnagar Metro, Hyderabad", "lat": 17.3688, "lon": 78.5247},
    "lb nagar": {"name": "LB Nagar Ring Road, Hyderabad", "lat": 17.3457, "lon": 78.5522},
    "uppal": {"name": "Uppal Ring Road, Hyderabad", "lat": 17.4018, "lon": 78.5602},
    "shamshabad": {"name": "Rajiv Gandhi International Airport (RGIA), Hyderabad", "lat": 17.2403, "lon": 78.4294},
    "miyapur": {"name": "Miyapur Metro Station, Hyderabad", "lat": 17.4968, "lon": 78.3614},
    "somajiguda": {"name": "Somajiguda Raj Bhavan Road, Hyderabad", "lat": 17.4239, "lon": 78.4589},
    "panjagutta": {"name": "Panjagutta Junction, Hyderabad", "lat": 17.4285, "lon": 78.4519},
    "warangal": {"name": "Warangal Fort / City, Telangana", "lat": 17.9689, "lon": 79.5941},

    # Bengaluru
    "silk board": {"name": "Central Silk Board, Bengaluru", "lat": 12.9176, "lon": 77.6238},
    "whitefield": {"name": "ITPL Main Road, Whitefield, Bengaluru", "lat": 12.9855, "lon": 77.7317},
    "electronic city": {"name": "Electronic City Phase 1, Bengaluru", "lat": 12.8452, "lon": 77.6602},
    "mg road": {"name": "MG Road Metro, Bengaluru", "lat": 12.9756, "lon": 77.6066},
    "bangalore": {"name": "Bengaluru City Center, Karnataka", "lat": 12.9716, "lon": 77.5946},
    "bengaluru": {"name": "Bengaluru City Center, Karnataka", "lat": 12.9716, "lon": 77.5946},
    "koramangala": {"name": "Koramangala Sony World Junction, Bengaluru", "lat": 12.9352, "lon": 77.6245},
    "indiranagar": {"name": "Indiranagar 100ft Road, Bengaluru", "lat": 12.9784, "lon": 77.6408},
    "marathahalli": {"name": "Marathahalli Bridge, Bengaluru", "lat": 12.9591, "lon": 77.7011},
    "hebbal": {"name": "Hebbal Flyover, Bengaluru", "lat": 13.0358, "lon": 77.5970},
    "hsr layout": {"name": "HSR Layout BDA Complex, Bengaluru", "lat": 12.9121, "lon": 77.6446},
    "jayanagar": {"name": "Jayanagar 4th Block, Bengaluru", "lat": 12.9299, "lon": 77.5824},
    "btm layout": {"name": "BTM Layout Ring Road, Bengaluru", "lat": 12.9166, "lon": 77.6101},
    "majestic": {"name": "KSR Bengaluru Majestic Station", "lat": 12.9772, "lon": 77.5708},
    "bellandur": {"name": "Bellandur EcoSpace, Bengaluru", "lat": 12.9260, "lon": 77.6762},
    "yelahanka": {"name": "Yelahanka Old Town, Bengaluru", "lat": 13.1007, "lon": 77.5963},
    "rajajinagar": {"name": "Rajajinagar Metro, Bengaluru", "lat": 12.9982, "lon": 77.5530},
    "mysore": {"name": "Mysore Palace, Mysuru, Karnataka", "lat": 12.3051, "lon": 76.6551},
    "mysuru": {"name": "Mysuru City, Karnataka", "lat": 12.2958, "lon": 76.6394},
    
    # Mumbai & MMR
    "mumbai": {"name": "Mumbai City Center, Maharashtra", "lat": 18.9388, "lon": 72.8354},
    "bkc": {"name": "Bandra Kurla Complex (BKC), Mumbai", "lat": 19.0657, "lon": 72.8687},
    "andheri": {"name": "Andheri East Station, Mumbai", "lat": 19.1197, "lon": 72.8468},
    "andheri west": {"name": "Andheri West Lokhandwala, Mumbai", "lat": 19.1363, "lon": 72.8277},
    "bandra": {"name": "Bandra West Linking Road, Mumbai", "lat": 19.0596, "lon": 72.8295},
    "marine drive": {"name": "Marine Drive Promenade, Mumbai", "lat": 18.9432, "lon": 72.8230},
    "dadar": {"name": "Dadar TT Circle, Mumbai", "lat": 19.0178, "lon": 72.8478},
    "borivali": {"name": "Borivali West, Mumbai", "lat": 19.2307, "lon": 72.8567},
    "thane": {"name": "Thane Station Area, Maharashtra", "lat": 19.2183, "lon": 72.9781},
    "navi mumbai": {"name": "Vashi Highway, Navi Mumbai", "lat": 19.0771, "lon": 72.9986},
    "vashi": {"name": "Vashi Plaza, Navi Mumbai", "lat": 19.0771, "lon": 72.9986},
    "powai": {"name": "Powai Hiranandani, Mumbai", "lat": 19.1197, "lon": 72.9051},
    "colaba": {"name": "Gateway of India, Colaba, Mumbai", "lat": 18.9220, "lon": 72.8347},

    # Delhi NCR
    "delhi": {"name": "New Delhi Central, Delhi", "lat": 28.6139, "lon": 77.2090},
    "new delhi": {"name": "New Delhi Railway Station", "lat": 28.6429, "lon": 77.2195},
    "connaught place": {"name": "Connaught Place, New Delhi", "lat": 28.6304, "lon": 77.2177},
    "cyber city": {"name": "DLF Cyber City, Gurugram", "lat": 28.4950, "lon": 77.0895},
    "gurgaon": {"name": "Gurugram (Gurgaon), Haryana", "lat": 28.4595, "lon": 77.0266},
    "gurugram": {"name": "Gurugram (Gurgaon), Haryana", "lat": 28.4595, "lon": 77.0266},
    "noida": {"name": "Sector 18 Atta Market, Noida, Uttar Pradesh", "lat": 28.5708, "lon": 77.3260},
    "noida sector 18": {"name": "Sector 18, Noida", "lat": 28.5708, "lon": 77.3260},
    "aiims": {"name": "AIIMS Ring Road, New Delhi", "lat": 28.5672, "lon": 77.2100},
    "dwarka": {"name": "Dwarka Sector 21, New Delhi", "lat": 28.5524, "lon": 77.0583},
    "ghaziabad": {"name": "Ghaziabad Old Bus Stand, Uttar Pradesh", "lat": 28.6692, "lon": 77.4538},
    "faridabad": {"name": "Bata Chowk, Faridabad, Haryana", "lat": 28.4089, "lon": 77.3178},

    # Chennai & Tamil Nadu
    "chennai": {"name": "Chennai Central Railway Station, Tamil Nadu", "lat": 13.0827, "lon": 80.2707},
    "guindy": {"name": "Kathipara Junction, Guindy, Chennai", "lat": 13.0067, "lon": 80.2033},
    "tidel park": {"name": "Tidel Park, OMR, Chennai", "lat": 12.9892, "lon": 80.2472},
    "omr": {"name": "Old Mahabalipuram Road (OMR), Chennai", "lat": 12.9698, "lon": 80.2435},
    "velachery": {"name": "Velachery Main Road, Chennai", "lat": 12.9759, "lon": 80.2212},
    "anna nagar": {"name": "Anna Nagar Roundtana, Chennai", "lat": 13.0878, "lon": 80.2137},
    "t nagar": {"name": "T Nagar Panagal Park, Chennai", "lat": 13.0418, "lon": 80.2341},
    "coimbatore": {"name": "Gandhipuram, Coimbatore, Tamil Nadu", "lat": 11.0168, "lon": 76.9558},
    "madurai": {"name": "Meenakshi Amman Temple, Madurai, Tamil Nadu", "lat": 9.9195, "lon": 78.1193},

    # Pune
    "pune": {"name": "Pune Railway Station, Maharashtra", "lat": 18.5204, "lon": 73.8567},
    "hinjawadi": {"name": "Hinjawadi Phase 1 IT Park, Pune", "lat": 18.5913, "lon": 73.7389},
    "shivajinagar": {"name": "Shivajinagar Bus Station, Pune", "lat": 18.5314, "lon": 73.8446},
    "kothrud": {"name": "Kothrud, Pune", "lat": 18.5074, "lon": 73.8077},
    "viman nagar": {"name": "Viman Nagar Phoenix Mall, Pune", "lat": 18.5679, "lon": 73.9143},
    "wakad": {"name": "Wakad Bridge, Pune", "lat": 18.5987, "lon": 73.7688},
    "baner": {"name": "Baner Highway, Pune", "lat": 18.5590, "lon": 73.7868},
    "hadapsar": {"name": "Magarpatta City, Hadapsar, Pune", "lat": 18.5089, "lon": 73.9260},

    # Kolkata
    "kolkata": {"name": "Kolkata City Center, West Bengal", "lat": 22.5726, "lon": 88.3639},
    "howrah": {"name": "Howrah Railway Station, Kolkata", "lat": 22.5830, "lon": 88.3426},
    "howrah station": {"name": "Howrah Railway Station, Kolkata", "lat": 22.5830, "lon": 88.3426},
    "salt lake": {"name": "Sector V, Salt Lake, Kolkata", "lat": 22.5735, "lon": 88.4331},
    "new town": {"name": "New Town Rajarhat, Kolkata", "lat": 22.5867, "lon": 88.4754},

    # Andhra Pradesh
    "visakhapatnam": {"name": "RK Beach, Visakhapatnam, Andhra Pradesh", "lat": 17.6868, "lon": 83.2185},
    "vizag": {"name": "Visakhapatnam (Vizag), Andhra Pradesh", "lat": 17.6868, "lon": 83.2185},
    "vijayawada": {"name": "Pandit Nehru Bus Station, Vijayawada, AP", "lat": 16.5062, "lon": 80.6480},
    "guntur": {"name": "Guntur Bus Station, Andhra Pradesh", "lat": 16.3067, "lon": 80.4365},
    "tirupati": {"name": "Tirupati Alipiri / Bus Stand, Andhra Pradesh", "lat": 13.6288, "lon": 79.4192},

    # Other Major Indian Hubs
    "ahmedabad": {"name": "SG Highway, Ahmedabad, Gujarat", "lat": 23.0225, "lon": 72.5714},
    "surat": {"name": "Surat Textile Market, Gujarat", "lat": 21.1702, "lon": 72.8311},
    "vadodara": {"name": "Alkapuri, Vadodara, Gujarat", "lat": 22.3072, "lon": 73.1812},
    "jaipur": {"name": "MI Road / Pink City, Jaipur, Rajasthan", "lat": 26.9124, "lon": 75.7873},
    "lucknow": {"name": "Hazratganj, Lucknow, Uttar Pradesh", "lat": 26.8467, "lon": 80.9462},
    "kanpur": {"name": "Kanpur Central, Uttar Pradesh", "lat": 26.4499, "lon": 80.3319},
    "chandigarh": {"name": "Sector 17, Chandigarh", "lat": 30.7333, "lon": 76.7794},
    "kochi": {"name": "MG Road / Marine Drive, Kochi, Kerala", "lat": 9.9312, "lon": 76.2673},
    "thiruvananthapuram": {"name": "Thampanoor, Thiruvananthapuram, Kerala", "lat": 8.5241, "lon": 76.9366},
    "indore": {"name": "Rajwada, Indore, Madhya Pradesh", "lat": 22.7196, "lon": 75.8577},
    "bhopal": {"name": "MP Nagar, Bhopal, Madhya Pradesh", "lat": 23.2599, "lon": 77.4126},
    "nagpur": {"name": "Zero Mile Stone, Nagpur, Maharashtra", "lat": 21.1458, "lon": 79.0882},
    "patna": {"name": "Gandhi Maidan, Patna, Bihar", "lat": 25.5941, "lon": 85.1376},
    "bhubaneswar": {"name": "Master Canteen, Bhubaneswar, Odisha", "lat": 20.2961, "lon": 85.8245},
    "guwahati": {"name": "Paltan Bazaar, Guwahati, Assam", "lat": 26.1445, "lon": 91.7362},
    "agra": {"name": "Taj Mahal Area, Agra, Uttar Pradesh", "lat": 27.1751, "lon": 78.0421},
    "varanasi": {"name": "Godowlia Chowk, Varanasi, Uttar Pradesh", "lat": 25.3176, "lon": 82.9739},
}


def geocode_india(query: str) -> List[Dict[str, Any]]:
    """
    Search for locations across India using multi-tier resolution:
    1. Fast offline landmark cache with priority for specific areas over generic city names.
    2. Komoot Photon API (free OpenStreetMap geocoder, fast, no rate-limit blocking).
    3. OpenStreetMap Nominatim API with countrycodes=in.
    4. Smart city fallback to ensure geocoordinates remain accurately anchored.
    """
    clean_q = query.strip().lower()
    if not clean_q:
        return []

    # Broad city names to avoid premature matching if user typed a specific locality (e.g. 'BKC, Mumbai')
    BROAD_CITIES = {
        "mumbai", "delhi", "new delhi", "bengaluru", "bangalore",
        "hyderabad", "chennai", "kolkata", "pune"
    }

    # Step 1A: Check specific non-metro landmark keys first (longest key first)
    non_city_keys = sorted([k for k in FAST_GEOCODE_CACHE if k not in BROAD_CITIES], key=len, reverse=True)
    for key in non_city_keys:
        if key in clean_q or (len(clean_q) >= 4 and clean_q in key):
            cached = FAST_GEOCODE_CACHE[key]
            return [{
                "display_name": cached["name"],
                "lat": cached["lat"],
                "lon": cached["lon"],
                "type": "landmark"
            }]

    # Step 1B: Exact match on any key in cache
    if clean_q in FAST_GEOCODE_CACHE:
        cached = FAST_GEOCODE_CACHE[clean_q]
        return [{
            "display_name": cached["name"],
            "lat": cached["lat"],
            "lon": cached["lon"],
            "type": "landmark"
        }]

    # Step 1C: Check broad city names only if no specific locality matched
    for key in BROAD_CITIES:
        if key in clean_q:
            cached = FAST_GEOCODE_CACHE[key]
            return [{
                "display_name": cached["name"],
                "lat": cached["lat"],
                "lon": cached["lon"],
                "type": "city_center"
            }]

    # 2. Try Komoot Photon (Fast, reliable, free OSM geocoder)
    try:
        url = f"https://photon.komoot.io/api/?q={urllib.parse.quote(query)}&limit=5"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "TrafficAI-IndiaNavigator/2.0 (academic-tool)"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("features"):
                results = []
                for feat in data["features"]:
                    props = feat.get("properties", {})
                    coords = feat["geometry"]["coordinates"] # [lon, lat]
                    name_parts = [props.get("name", "")]
                    if props.get("city"): name_parts.append(props["city"])
                    if props.get("state"): name_parts.append(props["state"])
                    if props.get("country"): name_parts.append(props["country"])
                    display_name = ", ".join([p for p in name_parts if p]) or query
                    results.append({
                        "display_name": display_name,
                        "lat": float(coords[1]),
                        "lon": float(coords[0]),
                        "type": props.get("osm_value", "location")
                    })
                if results:
                    return results
    except Exception as e:
        pass

    # 3. Query Nominatim API with countrycodes=in
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://nominatim.openstreetmap.org/search?q={encoded}&countrycodes=in&format=json&limit=5"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "TrafficAI-IndiaNavigator/2.0 (academic-research-tool)"}
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            results = []
            for item in data:
                results.append({
                    "display_name": item.get("display_name", ""),
                    "lat": float(item["lat"]),
                    "lon": float(item["lon"]),
                    "type": item.get("type", "location")
                })
            if results:
                return results
    except Exception as e:
        pass

    # 4. Fallback search against known cities
    for city_key, cached in FAST_GEOCODE_CACHE.items():
        if city_key in clean_q:
            return [{
                "display_name": f"{query.title()} ({cached['name']})",
                "lat": cached["lat"],
                "lon": cached["lon"],
                "type": "city_landmark"
            }]

    # 5. Safe default to Hyderabad center if query completely unresolved
    return [{
        "display_name": f"{query.title()}, India",
        "lat": 17.3850,
        "lon": 78.4867,
        "type": "approximate"
    }]


def _fetch_osrm_route(coords: List[Tuple[float, float]], alternatives: bool = True) -> Dict[str, Any]:
    """
    Fetch realistic driving route geometry from OSRM.
    coords is list of (lat, lon).
    Returns raw OSRM json.
    """
    # OSRM expects lon,lat;lon,lat
    coord_str = ";".join([f"{lon:.5f},{lat:.5f}" for lat, lon in coords])
    alt_param = "true" if alternatives else "false"
    url = f"https://router.project-osrm.org/route/v1/driving/{coord_str}?overview=full&geometries=geojson&alternatives={alt_param}&steps=true&annotations=distance,duration"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "TrafficAI-IndiaRouting/1.0 (academic-research-tool)"}
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("code") == "Ok" and "routes" in data:
                return data
    except Exception as e:
        print(f"[OSRM Error] {e}")

    return {}


def _generate_synthetic_corridor_route(
    start_lat: float, start_lon: float,
    end_lat: float, end_lon: float,
    is_alternate: bool = False
) -> Dict[str, Any]:
    """
    Robust fallback route generator if external OSRM service is unreachable.
    Creates realistic multi-waypoint road arc paths with slight detour for alternate route.
    """
    steps = 18
    coordinates = []
    
    # Calculate mid-point and perpendicular offset for detour
    mid_lat = (start_lat + end_lat) / 2
    mid_lon = (start_lon + end_lon) / 2
    d_lat = end_lat - start_lat
    d_lon = end_lon - start_lon
    
    # Perpendicular unit vector
    length = math.sqrt(d_lat**2 + d_lon**2) or 0.01
    perp_lat = -d_lon / length
    perp_lon = d_lat / length
    
    # Detour offset magnitude (alternate route bows out by 15-25% to bypass central bottleneck)
    curvature = 0.28 if is_alternate else 0.05
    offset_dist = length * curvature

    for i in range(steps + 1):
        t = i / steps
        # Parabolic arc
        arc = 4 * t * (1 - t)
        lat = start_lat + t * d_lat + arc * offset_dist * perp_lat
        lon = start_lon + t * d_lon + arc * offset_dist * perp_lon
        coordinates.append([lon, lat])

    straight_km = length * 111.0  # approximate km per degree
    distance_meters = straight_km * (1.25 if is_alternate else 1.1) * 1000.0
    duration_seconds = (distance_meters / 1000.0) / 45.0 * 3600.0  # ~45 km/h base

    return {
        "geometry": {"coordinates": coordinates, "type": "LineString"},
        "distance": distance_meters,
        "duration": duration_seconds
    }


def analyze_india_traffic_and_routes(
    origin_name: str,
    dest_name: str,
    origin_coords: List[float],
    dest_coords: List[float],
    hour: int = 8,
    day_of_week: int = 0,
    weather: int = 0,
    accident_corridor: str = None,
    n_diverted_vehicles: int = 150,
    vehicle_mode: str = 'commute'
) -> Dict[str, Any]:
    """
    Full pipeline:
    1. Obtains primary route and alternate detour route across India.
    2. Calculates vehicle volume, capacity, and density along each road segment.
    3. Identifies traffic bottlenecks and congestion hotspots.
    4. Computes BPR congestion delay and ML future travel time.
    5. Recommends the congestion-aware alternate route with clear AI explanations.
    """
    start_lat, start_lon = origin_coords
    end_lat, end_lon = dest_coords

    # 1. Fetch real routes from OSRM
    osrm_data = _fetch_osrm_route([(start_lat, start_lon), (end_lat, end_lon)], alternatives=True)
    routes_found = osrm_data.get("routes", [])

    primary_route_raw = None
    alternate_route_raw = None

    if len(routes_found) >= 2:
        primary_route_raw = routes_found[0]
        alternate_route_raw = routes_found[1]
    elif len(routes_found) == 1:
        primary_route_raw = routes_found[0]
        # Generate alternate bypass route using waypoint detour
        mid_lat = (start_lat + end_lat) / 2
        mid_lon = (start_lon + end_lon) / 2
        d_lat = end_lat - start_lat
        d_lon = end_lon - start_lon
        detour_lat = mid_lat - (d_lon * 0.25)
        detour_lon = mid_lon + (d_lat * 0.25)
        
        alt_osrm = _fetch_osrm_route([(start_lat, start_lon), (detour_lat, detour_lon), (end_lat, end_lon)], alternatives=False)
        if alt_osrm.get("routes"):
            alternate_route_raw = alt_osrm["routes"][0]
        else:
            alternate_route_raw = _generate_synthetic_corridor_route(start_lat, start_lon, end_lat, end_lon, is_alternate=True)
    else:
        # Fallback if offline
        primary_route_raw = _generate_synthetic_corridor_route(start_lat, start_lon, end_lat, end_lon, is_alternate=False)
        alternate_route_raw = _generate_synthetic_corridor_route(start_lat, start_lon, end_lat, end_lon, is_alternate=True)

    # 2. Time-of-day traffic surge factors for Indian Metros
    # Peak Morning & Evening: Heavy Gridlock (8-11 AM, 5-9 PM)
    # Afternoon Low Window: Low Traffic (1-3:30 PM)
    # Late Night: Free Flow Low Traffic (10 PM - 5 AM)
    # Other hours: Moderate Traffic Flow
    if (8 <= hour <= 11) or (17 <= hour <= 21):
        traffic_multiplier = 1.60
        is_rush_hour = True
    elif (13 <= hour <= 15) or (22 <= hour or hour <= 5):
        traffic_multiplier = 0.60
        is_rush_hour = False
    else:
        traffic_multiplier = 0.95
        is_rush_hour = False

    # Weather factor: Monsoon/Rain (1) adds +30% waterlogging friction in India
    weather_factor = {0: 1.0, 1: 1.35, 2: 1.25, 3: 1.50}.get(weather, 1.0)
    
    # Weekend vs Weekday
    is_weekend = (day_of_week >= 5)
    if is_weekend:
        traffic_multiplier *= 0.85

    # 3. Process Primary Route (The heavily trafficked direct path)
    primary_dist_km = round(primary_route_raw["distance"] / 1000.0, 1)
    primary_freeflow_min = round(primary_route_raw["duration"] / 60.0, 1)

    # Base vehicle load on primary arterial
    # Typical arterial in Indian metro has capacity of ~2,400 veh/hr
    prim_capacity = 2400
    prim_base_vehicles = int(2100 * traffic_multiplier * (1.15 if is_rush_hour else 0.9))

    # Accident / bottleneck penalty
    has_incident_on_primary = bool(accident_corridor and accident_corridor.lower() != "none")
    if has_incident_on_primary:
        prim_base_vehicles = int(prim_base_vehicles * 1.25)
        prim_capacity = int(prim_capacity * 0.65)  # 35% lane capacity drop

    prim_ratio = prim_base_vehicles / max(prim_capacity, 1)
    # BPR travel time: t(v) = t0 * (1 + 0.15 * (v/c)^4)
    prim_bpr_time = round(primary_freeflow_min * (1.0 + 0.15 * (prim_ratio ** 4) * weather_factor), 1)
    prim_speed_kmh = round(primary_dist_km / (prim_bpr_time / 60.0), 1) if prim_bpr_time > 0 else 30.0

    # 4. Process Alternate Route 1 (Primary AI Bypass)
    alt_dist_km = round(alternate_route_raw["distance"] / 1000.0, 1)
    if alt_dist_km <= primary_dist_km * 0.95:
        alt_dist_km = round(primary_dist_km * 1.15, 1)
    
    alt_freeflow_min = round(alt_dist_km / 48.0 * 60.0, 1)
    alt_capacity = 2200
    alt_base_vehicles = int(1050 * traffic_multiplier * 0.72)

    alt_new_vehicles = alt_base_vehicles + n_diverted_vehicles
    alt_ratio_before = alt_base_vehicles / max(alt_capacity, 1)
    alt_ratio_after = alt_new_vehicles / max(alt_capacity, 1)
    
    alt_bpr_time_before = alt_freeflow_min * (1.0 + 0.15 * (alt_ratio_before ** 4) * weather_factor)
    alt_bpr_time_after = round(alt_freeflow_min * (1.0 + 0.15 * (alt_ratio_after ** 4) * weather_factor), 1)
    alt_speed_kmh = round(alt_dist_km / (alt_bpr_time_after / 60.0), 1) if alt_bpr_time_after > 0 else 42.0

    rerouting_impact_min = round(max(alt_bpr_time_after - alt_bpr_time_before, 0.4), 1)
    time_saved_min = round(prim_bpr_time - alt_bpr_time_after, 1)

    # 4B. Process Alternate Route 2 (Secondary Ring Road / Highway Bypass)
    sec_alt_raw = _generate_synthetic_corridor_route(start_lat, start_lon, end_lat, end_lon, is_alternate=True)
    sec_dist_km = round(primary_dist_km * 1.24, 1)
    sec_bpr_time = round(max(alt_bpr_time_after * 1.12, primary_freeflow_min * 1.2), 1)
    sec_time_saved = round(max(prim_bpr_time - sec_bpr_time, 0), 1)
    sec_speed_kmh = round(sec_dist_km / (sec_bpr_time / 60.0), 1) if sec_bpr_time > 0 else 38.0

    # Calculate exact arrival times (ETAs) based on departure hour
    dep_total_mins = hour * 60
    arr_direct_mins = int(dep_total_mins + prim_bpr_time)
    arr_alt_mins = int(dep_total_mins + alt_bpr_time_after)
    arr_sec_mins = int(dep_total_mins + sec_bpr_time)

    def _fmt_clock(total_m):
        m = total_m % (24 * 60)
        h = m // 60
        mn = m % 60
        p = "AM" if h < 12 else "PM"
        dh = h if 1 <= h <= 12 else (12 if h == 0 else h - 12)
        return f"{dh:02d}:{mn:02d} {p}"

    eta_direct = _fmt_clock(arr_direct_mins)
    eta_alternate = _fmt_clock(arr_alt_mins)
    eta_secondary = _fmt_clock(arr_sec_mins)

    # 5. Segment breakdown & Hotspot Detection
    # Generate 5 segment intervals for each route with coordinates, color, and vehicle counts
    prim_segments = _create_route_segments(
        primary_route_raw["geometry"]["coordinates"],
        total_vehicles=prim_base_vehicles,
        capacity=prim_capacity,
        base_speed=prim_speed_kmh,
        is_primary=True,
        has_incident=has_incident_on_primary
    )

    alt_segments = _create_route_segments(
        alternate_route_raw["geometry"]["coordinates"],
        total_vehicles=alt_new_vehicles,
        capacity=alt_capacity,
        base_speed=alt_speed_kmh,
        is_primary=False,
        has_incident=False
    )

    # 6. ML Model Inference for the corridor
    ml_pred = predict_traffic(
        hour=hour,
        day_of_week=day_of_week,
        vehicle_count=min(prim_base_vehicles, 5000),
        weather=weather,
        accident=1 if has_incident_on_primary else 0,
        road_capacity=prim_capacity
    )
    if ml_pred.get("traffic_level") == "High":
        ml_pred["traffic_level"] = "Heavy"
    elif ml_pred.get("traffic_level") == "Medium":
        ml_pred["traffic_level"] = "Moderate"

    # 7. Hotspot Bottleneck description
    bottleneck_info = {
        "location": f"Main Corridor Midsection between {origin_name.split(',')[0]} and {dest_name.split(',')[0]}",
        "current_vehicles": prim_base_vehicles,
        "capacity": prim_capacity,
        "congestion_level": "Heavy" if prim_ratio >= 0.85 else ("Moderate" if prim_ratio >= 0.6 else "Low"),
        "congestion_ratio": round(prim_ratio, 2),
        "speed_kmh": prim_speed_kmh,
        "delay_minutes": round(prim_bpr_time - primary_freeflow_min, 1)
    }

    # 8. Compute 24-hour traffic timeline to find exact heavy vs low traffic times
    timeline_analysis = _compute_24h_traffic_timeline(
        freeflow_min=primary_freeflow_min,
        capacity=prim_capacity,
        weather_factor=weather_factor,
        is_weekend=is_weekend,
        has_incident=has_incident_on_primary
    )

    is_traffic_heavy = (prim_ratio >= 0.85)
    is_traffic_low = (prim_ratio < 0.60)

    # 9. Clear AI Explanation for the user
    period = "AM" if hour < 12 else "PM"
    disp_h = hour if 1 <= hour <= 12 else (12 if hour == 0 else hour - 12)
    selected_time_str = f"{disp_h:02d}:00 {period}"

    if vehicle_mode == 'ambulance':
        if is_traffic_heavy:
            recommendation = "🚨 Emergency Green Corridor Alert — Hospital Bypass Activated"
            explanation = (
                f"🚑 EMERGENCY MEDICAL PRIORITY at {selected_time_str}: Primary arterial to hospital has SEVERE GRIDLOCK "
                f"with {prim_base_vehicles:,} queued vehicles (speed: {prim_speed_kmh} km/h, estimated transit: {prim_bpr_time} mins). "
                f"Diverting onto the Emergency Green Bypass reaches hospital in only {alt_bpr_time_after} mins "
                f"(⚡ Saves ~{time_saved_min} life-saving minutes!). Signal preemption & zero-friction clearance recommended."
            )
        elif is_traffic_low:
            recommendation = "🟢 Emergency Corridor Clear — Direct Transit Optimal"
            explanation = (
                f"🚑 Emergency transit route at {selected_time_str} is FREE-FLOW ({prim_base_vehicles:,} vehicles, speed {prim_speed_kmh} km/h). "
                f"Direct hospital transit time is only {prim_bpr_time} mins. Direct corridor is fastest."
            )
        else:
            recommendation = "🟡 Moderate Flow — Alternate Bypass Monitored"
            explanation = (
                f"🚑 Direct hospital corridor has moderate commuter traffic ({prim_base_vehicles:,} vehicles, {prim_bpr_time} mins). "
                f"Green bypass is on standby taking {alt_bpr_time_after} mins."
            )
    elif vehicle_mode == 'delivery':
        if is_traffic_heavy:
            recommendation = "🛵 Peak Delivery Gridlock — Express Detour Recommended"
            explanation = (
                f"🛵 SWIGGY/ZOMATO RUSH HOUR at {selected_time_str}: Direct road is choked with {prim_base_vehicles:,} vehicles "
                f"({prim_bpr_time} mins travel time). Taking the Express Delivery Bypass delivers order in only {alt_bpr_time_after} mins "
                f"(⚡ Saves ~{time_saved_min} mins — beat customer delivery deadline!)."
            )
        elif is_traffic_low:
            recommendation = "🟢 Fast Delivery Express Window"
            explanation = (
                f"🛵 Direct delivery corridor at {selected_time_str} is smooth ({prim_base_vehicles:,} vehicles). "
                f"Delivery transit takes only {prim_bpr_time} mins. No detour needed."
            )
        else:
            recommendation = "🟡 Moderate Delivery Flow"
            explanation = (
                f"🛵 Normal delivery conditions ({prim_base_vehicles:,} vehicles, {prim_bpr_time} mins). Bypass takes {alt_bpr_time_after} mins."
            )
    else:
        if is_traffic_heavy:
            recommendation = "Heavy Traffic Detected — Alternate Route Recommended"
            explanation = (
                f"At your selected departure time ({selected_time_str}), traffic is HEAVY along the primary route "
                f"with {prim_base_vehicles:,} queued vehicles (speed: {prim_speed_kmh} km/h, delay: +{round(prim_bpr_time - primary_freeflow_min, 1)} mins). "
                f"Suggested Alternate Route takes {alt_bpr_time_after} mins (saves ~{time_saved_min} mins faster!). "
                f"💡 Low-Traffic Tip: If you travel during low traffic hours ({timeline_analysis['low_traffic_window'].split('&')[0].strip()}), "
                f"your direct commute will only take {timeline_analysis['best_low_traffic_time_min']} mins (saving {timeline_analysis['low_traffic_savings_min']} mins)!"
            )
        elif is_traffic_low:
            recommendation = "Traffic is Low — Direct Route is Fast & Optimal"
            explanation = (
                f"At your selected departure time ({selected_time_str}), traffic is LOW along the primary corridor "
                f"({prim_base_vehicles:,} vehicles, speed: {prim_speed_kmh} km/h). "
                f"You will reach your destination in only {prim_bpr_time} mins at near free-flow speed. "
                f"No alternate detour is required since roads are running smoothly."
            )
        else:
            recommendation = "Moderate Traffic Flow"
            explanation = (
                f"At your selected departure time ({selected_time_str}), traffic is MODERATE ({prim_base_vehicles:,} vehicles). "
                f"Direct travel time is {prim_bpr_time} mins. Alternate bypass takes {alt_bpr_time_after} mins."
            )

    return {
        "status": "success",
        "origin": {"name": origin_name, "lat": start_lat, "lon": start_lon},
        "destination": {"name": dest_name, "lat": end_lat, "lon": end_lon},
        "traffic_context": {
            "hour": hour,
            "hour_label": selected_time_str,
            "day_of_week": day_of_week,
            "weather": weather,
            "is_rush_hour": is_rush_hour,
            "is_heavy": is_traffic_heavy,
            "is_low": is_traffic_low,
            "traffic_level": "Heavy" if is_traffic_heavy else ("Low" if is_traffic_low else "Moderate"),
            "accident": has_incident_on_primary,
            "vehicle_mode": vehicle_mode
        },
        "timing_analysis": {
            "is_selected_hour_heavy": is_traffic_heavy,
            "is_selected_hour_low": is_traffic_low,
            "heavy_traffic_window": timeline_analysis["heavy_traffic_window"],
            "low_traffic_window": timeline_analysis["low_traffic_window"],
            "best_low_traffic_time_min": timeline_analysis["best_low_traffic_time_min"],
            "worst_heavy_traffic_time_min": timeline_analysis["worst_heavy_traffic_time_min"],
            "low_traffic_savings_min": timeline_analysis["low_traffic_savings_min"],
            "timeline": timeline_analysis["timeline"]
        },
        "baseline_route": {
            "name": "Standard Direct Route (Heaviest Traffic)",
            "distance_km": primary_dist_km,
            "freeflow_time_min": primary_freeflow_min,
            "current_travel_time_min": prim_bpr_time,
            "average_speed_kmh": prim_speed_kmh,
            "vehicle_count": prim_base_vehicles,
            "road_capacity": prim_capacity,
            "congestion_level": "Heavy" if prim_ratio >= 0.85 else ("Moderate" if prim_ratio >= 0.6 else "Low"),
            "segments": prim_segments,
            "geometry": primary_route_raw["geometry"]
        },
        "alternate_route": {
            "name": "AI Congestion-Aware Alternate Route",
            "distance_km": alt_dist_km,
            "freeflow_time_min": alt_freeflow_min,
            "current_travel_time_min": alt_bpr_time_after,
            "average_speed_kmh": alt_speed_kmh,
            "vehicle_count": alt_new_vehicles,
            "road_capacity": alt_capacity,
            "congestion_level": "Low" if alt_ratio_after < 0.6 else "Medium",
            "marginal_network_impact_min": rerouting_impact_min,
            "time_saved_min": max(time_saved_min, 0),
            "segments": alt_segments,
            "geometry": alternate_route_raw["geometry"]
        },
        "secondary_alternate_route": {
            "name": "Secondary Bypass (Ring Road Corridor)",
            "distance_km": sec_dist_km,
            "current_travel_time_min": sec_bpr_time,
            "average_speed_kmh": sec_speed_kmh,
            "time_saved_min": sec_time_saved,
            "congestion_level": "Low",
            "geometry": sec_alt_raw["geometry"]
        },
        "eta": {
            "departure": selected_time_str,
            "direct": eta_direct,
            "alternate": eta_alternate,
            "secondary": eta_secondary,
            "time_saved_display": f"{int(time_saved_min)} mins earlier"
        },
        "bottleneck": bottleneck_info,
        "ml_forecast": ml_pred,
        "recommendation": recommendation,
        "ai_explanation": explanation
    }


def _compute_24h_traffic_timeline(
    freeflow_min: float,
    capacity: int,
    weather_factor: float,
    is_weekend: bool,
    has_incident: bool
) -> Dict[str, Any]:
    """
    Computes hour-by-hour traffic volume and travel times across all 24 hours of the day.
    Identifies exact peak heavy traffic windows and best low-traffic travel windows.
    """
    timeline = []
    min_time = 999.0
    best_hour = 14
    max_time = 0.0
    worst_hour = 9

    for h in range(24):
        if (8 <= h <= 11) or (17 <= h <= 21):
            mult = 1.60
            is_rush = True
        elif (13 <= h <= 15) or (22 <= h or h <= 5):
            mult = 0.60
            is_rush = False
        else:
            mult = 0.95
            is_rush = False

        if is_weekend:
            mult *= 0.85

        base_v = int(2100 * mult * (1.15 if is_rush else 0.9))
        cap = capacity
        if has_incident and (7 <= h <= 21):
            base_v = int(base_v * 1.25)
            cap = int(cap * 0.65)

        ratio = base_v / max(cap, 1)
        travel_time = round(freeflow_min * (1.0 + 0.15 * (ratio ** 4) * weather_factor), 1)

        if travel_time < min_time:
            min_time = travel_time
            best_hour = h
        if travel_time > max_time:
            max_time = travel_time
            worst_hour = h

        if ratio >= 0.85:
            level = "Heavy"
            color = "#ef4444"
        elif ratio >= 0.6:
            level = "Moderate"
            color = "#f59e0b"
        else:
            level = "Low"
            color = "#10b981"

        period = "AM" if h < 12 else "PM"
        disp_h = h if 1 <= h <= 12 else (12 if h == 0 else h - 12)
        hour_label = f"{disp_h:02d}:00 {period}"

        timeline.append({
            "hour": h,
            "hour_label": hour_label,
            "travel_time_min": travel_time,
            "vehicle_count": base_v,
            "congestion_level": level,
            "color": color,
            "is_heavy": (level == "Heavy"),
            "is_low": (level == "Low")
        })

    heavy_window_desc = "08:00 AM – 11:30 AM (Morning Peak) & 05:30 PM – 09:00 PM (Evening Peak)"
    low_window_desc = "12:30 PM – 03:30 PM (Afternoon Flow) & 09:30 PM – 06:00 AM (Free Flow)"

    return {
        "timeline": timeline,
        "heavy_traffic_window": heavy_window_desc,
        "low_traffic_window": low_window_desc,
        "best_low_traffic_hour": best_hour,
        "best_low_traffic_time_min": min_time,
        "worst_heavy_traffic_time_min": max_time,
        "low_traffic_savings_min": round(max(max_time - min_time, 0), 1)
    }



def _create_route_segments(
    coordinates: List[List[float]],
    total_vehicles: int,
    capacity: int,
    base_speed: float,
    is_primary: bool,
    has_incident: bool
) -> List[Dict[str, Any]]:
    """
    Subdivides route coordinates into 4-5 visual chunks with realistic color codes and vehicle counts.
    Coordinates in OSRM are [lon, lat].
    """
    n_pts = len(coordinates)
    if n_pts < 2:
        return []

    num_segments = min(5, max(3, n_pts // 8))
    step = n_pts / num_segments
    segments = []

    for i in range(num_segments):
        start_idx = int(i * step)
        end_idx = int((i + 1) * step) if i < num_segments - 1 else n_pts - 1
        chunk_coords = [[lat, lon] for lon, lat in coordinates[start_idx:end_idx + 1]]

        # Center segment of primary route gets the worst congestion / bottleneck
        is_bottleneck_segment = is_primary and (i == num_segments // 2 or (has_incident and i == 1))
        
        if is_bottleneck_segment:
            veh_count = int(total_vehicles * random.uniform(1.15, 1.35))
            seg_color = "#ef4444"  # Red (Severe)
            seg_level = "Severe Congestion"
            speed = round(base_speed * 0.45, 1)
        elif is_primary:
            veh_count = int(total_vehicles * random.uniform(0.85, 1.05))
            seg_color = "#f59e0b" if veh_count >= capacity * 0.75 else "#10b981"
            seg_level = "Moderate Traffic" if seg_color == "#f59e0b" else "Smooth Flow"
            speed = round(base_speed * 0.85, 1)
        else:
            # Alternate route is largely smooth bypass
            veh_count = int(total_vehicles * random.uniform(0.8, 1.0))
            seg_color = "#10b981"  # Emerald Green
            seg_level = "Smooth Bypass"
            speed = round(base_speed * 1.05, 1)

        segments.append({
            "segment_id": i + 1,
            "coords": chunk_coords,
            "vehicles_on_segment": veh_count,
            "speed_kmh": speed,
            "color": seg_color,
            "status": seg_level
        })

    return segments
