from pydantic import BaseModel, Field


class GeofenceCheckRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy: float | None = Field(
        default=None,
        ge=0,
    )


class GeofenceCheckResponse(BaseModel):
    inside: bool
    distance_meters: float
    allowed_radius_meters: int

    location_id: int
    location_name: str