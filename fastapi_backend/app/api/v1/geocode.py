from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.dependencies.auth import get_current_organisation
from app.models.user import User
from app.services.geocoding_service import search_places


router = APIRouter()


class Place(BaseModel):
    name: str
    latitude: float
    longitude: float


# GET /api/v1/geocode/search?q=...
# Admins placing an office on the map. One search per tap (never
# search-as-you-type), sent to OpenStreetMap from here, not from phones.
@router.get(
    "/geocode/search",
    response_model=list[Place],
)
def geocode_search(
    q: str = Query(min_length=3, max_length=200),
    current_user: User = Depends(get_current_organisation),
):
    return search_places(q.strip())
