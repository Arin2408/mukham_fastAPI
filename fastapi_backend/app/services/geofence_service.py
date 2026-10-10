from math import atan2, cos, radians, sin, sqrt

from app.models.location import Location


EARTH_RADIUS_METERS = 6_371_000


def validate_coordinates(
    latitude: float,
    longitude: float,
) -> None:
    if not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90")

    if not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180")


def calculate_distance_meters(
    latitude1: float,
    longitude1: float,
    latitude2: float,
    longitude2: float,
) -> float:
    """
    Calculate the distance between two GPS coordinates
    using the Haversine formula.
    """

    lat1 = radians(latitude1)
    lon1 = radians(longitude1)

    lat2 = radians(latitude2)
    lon2 = radians(longitude2)

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1)
        * cos(lat2)
        * sin(delta_lon / 2) ** 2
    )

    c = 2 * atan2(
        sqrt(a),
        sqrt(1 - a),
    )

    return EARTH_RADIUS_METERS * c


def check_geofence(
    latitude: float,
    longitude: float,
    location: Location,
) -> tuple[bool, float]:
    """
    Check whether the supplied coordinates are inside
    the office location's configured radius.

    Returns:
        (is_inside, distance_in_meters)
    """

    validate_coordinates(
        latitude=latitude,
        longitude=longitude,
    )

    distance = calculate_distance_meters(
        latitude1=latitude,
        longitude1=longitude,
        latitude2=float(location.latitude),
        longitude2=float(location.longitude),
    )

    is_inside = distance <= location.radius_meters

    return is_inside, distance