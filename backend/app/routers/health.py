from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.response import success
from app.deps.db import get_db
from app.schemas.common import HealthData, ReadinessData, ResponseEnvelope

router = APIRouter(tags=["health"])

_VERSION = "0.1.0"


@router.get("/health", response_model=ResponseEnvelope[HealthData])
def health() -> ResponseEnvelope[HealthData]:
    return success(HealthData(status="ok", version=_VERSION))


@router.get("/readiness", response_model=ResponseEnvelope[ReadinessData])
def readiness(db: Session = Depends(get_db)) -> ResponseEnvelope[ReadinessData]:
    checks: dict[str, str] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"failed: {e}"
    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return success(ReadinessData(status=overall, checks=checks))
