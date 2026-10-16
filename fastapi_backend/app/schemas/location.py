from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class LocationResponse(BaseModel):
    location_id: int
    location_name: str
    latitude: Decimal
    longitude: Decimal
    radius_meters: int
    org_id: int

    model_config = {"from_attributes": True}


class LocationCreateRequest(BaseModel):
    location_name: str = Field(min_length=1, max_length=255)
    latitude: Decimal = Field(..., ge=Decimal("-90"), le=Decimal("90"))
    longitude: Decimal = Field(..., ge=Decimal("-180"), le=Decimal("180"))
    radius_meters: int = Field(default=100, ge=10, le=5000)


class LocationUpdateRequest(BaseModel):
    location_name: str | None = Field(default=None, min_length=1, max_length=255)
    latitude: Decimal | None = Field(
        default=None,
        ge=Decimal("-90"),
        le=Decimal("90"),
    )
    longitude: Decimal | None = Field(
        default=None,
        ge=Decimal("-180"),
        le=Decimal("180"),
    )
    radius_meters: int | None = Field(
        default=None,
        ge=10,
        le=5000,
    )