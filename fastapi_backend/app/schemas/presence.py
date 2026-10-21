from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PresenceRegionResponse(BaseModel):
    attendance_id: int
    latitude: float
    longitude: float
    radius_meters: int


class PresenceEventRequest(BaseModel):
    event: Literal["exit", "enter", "on", "off"]
    occurred_at: datetime


class PresenceEventResponse(BaseModel):
    recorded: bool


class PresenceEventOut(BaseModel):
    event: Literal["exit", "enter"]
    at: datetime
