from datetime import date

from pydantic import BaseModel

from app.schemas.department import DepartmentLeaderboardResponse


class RoleCount(BaseModel):
    name: str
    count: int


class DayPresence(BaseModel):
    date: date
    # Employees who checked in at least once that day
    present: int
    # present / current number of employees, 0-100
    percent: float


class DashboardSummaryResponse(BaseModel):
    total_employees: int
    active_shifts: int
    office_locations: int
    # Average department punctuality score, 0-100
    attendance_score: int
    # Employees per designation, most common first
    roles: list[RoleCount]
    # The last 7 days, oldest first, today last
    weekly_attendance: list[DayPresence]
    leaderboard: list[DepartmentLeaderboardResponse]
