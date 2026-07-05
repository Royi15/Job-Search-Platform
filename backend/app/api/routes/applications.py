from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser
from app.models import Application, ApplicationEvent, JobAlert
from app.schemas.application import (
    ApplicationCreate,
    ApplicationEventOut,
    ApplicationMove,
    ApplicationOut,
    ApplicationUpdate,
)

router = APIRouter(prefix="/applications", tags=["applications"])


async def _owned_application(db, user_id: int, app_id: int) -> Application:
    application = await db.scalar(
        select(Application).where(
            Application.id == app_id, Application.user_id == user_id
        )
    )
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    return application


async def _next_sort_order(db, user_id: int, status_value) -> float:
    """Place new cards at the bottom of their column."""
    current_max = await db.scalar(
        select(func.max(Application.sort_order)).where(
            Application.user_id == user_id, Application.status == status_value
        )
    )
    return (current_max or 0) + 1000


@router.get("", response_model=list[ApplicationOut])
async def list_applications(user: CurrentUser, db: DB):
    """All cards; the frontend groups them into Kanban columns by status."""
    result = await db.scalars(
        select(Application)
        .where(Application.user_id == user.id)
        .order_by(Application.status, Application.sort_order)
    )
    return result.all()


@router.post("", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
async def create_application(body: ApplicationCreate, user: CurrentUser, db: DB):
    data = body.model_dump(exclude_unset=True)
    application = Application(
        user_id=user.id,
        sort_order=await _next_sort_order(db, user.id, body.status),
        **data,
    )
    db.add(application)
    await db.flush()
    db.add(ApplicationEvent(application_id=application.id, to_status=body.status))
    await db.commit()
    await db.refresh(application)
    return application


@router.post(
    "/from-alert/{alert_id}",
    response_model=ApplicationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_from_alert(alert_id: int, user: CurrentUser, db: DB):
    """'Applied ✅' on a job alert — copies the job into a Kanban card."""
    alert = await db.scalar(
        select(JobAlert).where(JobAlert.id == alert_id, JobAlert.user_id == user.id)
    )
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")

    existing = await db.scalar(
        select(Application.id).where(
            Application.user_id == user.id, Application.job_id == alert.job_id
        )
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Job is already on your board")

    job = alert.job
    application = Application(
        user_id=user.id,
        job_id=job.id,
        company=job.company or "Unknown",
        title=job.title,
        url=job.url,
        sort_order=await _next_sort_order(db, user.id, "applied"),
    )
    db.add(application)
    await db.flush()
    db.add(ApplicationEvent(application_id=application.id, to_status="applied"))
    alert.dismissed = True
    await db.commit()
    await db.refresh(application)
    return application


@router.post("/{app_id}/move", response_model=ApplicationOut)
async def move_application(app_id: int, body: ApplicationMove, user: CurrentUser, db: DB):
    """Drag & drop: change column and/or position. Records status history."""
    application = await _owned_application(db, user.id, app_id)
    if application.status != body.status:
        db.add(
            ApplicationEvent(
                application_id=application.id,
                from_status=application.status,
                to_status=body.status,
            )
        )
    application.status = body.status
    application.sort_order = body.sort_order
    await db.commit()
    await db.refresh(application)
    return application


@router.patch("/{app_id}", response_model=ApplicationOut)
async def update_application(app_id: int, body: ApplicationUpdate, user: CurrentUser, db: DB):
    application = await _owned_application(db, user.id, app_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(application, field, value)
    await db.commit()
    await db.refresh(application)
    return application


@router.get("/{app_id}/events", response_model=list[ApplicationEventOut])
async def application_history(app_id: int, user: CurrentUser, db: DB):
    await _owned_application(db, user.id, app_id)
    result = await db.scalars(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == app_id)
        .order_by(ApplicationEvent.changed_at)
    )
    return result.all()


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(app_id: int, user: CurrentUser, db: DB) -> None:
    application = await _owned_application(db, user.id, app_id)
    await db.delete(application)
    await db.commit()
