"""Geographic helpers."""
import math

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def travel_minutes(dist_km: float, speed_kmph: float) -> float:
    """Travel time in minutes at a constant speed."""
    return dist_km / speed_kmph * 60.0 if speed_kmph > 0 else float("inf")


def area_cell(lat: float, lng: float, size_deg: float = 0.05) -> str:
    """Coarse grid cell id (~5 km) used for prediction and for hiding exact addresses."""
    return f"{math.floor(lat / size_deg)}_{math.floor(lng / size_deg)}"
