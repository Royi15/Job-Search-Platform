from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.models import JobAlert
from app.schemas.job import AlertOut

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
async def list_alerts(user: CurrentUser, db: DB, include_dismissed: bool = False):
    query = (
        select(JobAlert)
        .where(JobAlert.user_id == user.id)
        .order_by(JobAlert.matched_at.desc())
        .limit(200)
    )
    if not include_dismissed:
        query = query.where(JobAlert.dismissed.is_(False))
    result = await db.scalars(query)
    return result.unique().all()


@router.post("/{alert_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_alert(alert_id: int, user: CurrentUser, db: DB) -> None:
    alert = await db.scalar(
        select(JobAlert).where(JobAlert.id == alert_id, JobAlert.user_id == user.id)
    )
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    alert.dismissed = True
    await db.commit()
