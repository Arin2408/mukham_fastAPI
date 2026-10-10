from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db


router = APIRouter()


@router.get("/health/db")
def database_health(
    db: Session = Depends(get_db),
):
    result = db.execute(
        text("SELECT 1")
    ).scalar()

    return {
        "status": "ok",
        "database": result == 1,
    }