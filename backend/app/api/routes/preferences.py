from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.models import SearchPreference
from app.schemas.preference import PreferenceCreate, PreferenceOut, PreferenceUpdate

router = APIRouter(prefix="/preferences", tags=["preferences"])


async def _owned_pref(db, user_id: int, pref_id: int) -> SearchPreference:
    pref = await db.scalar(
        select(SearchPreference).where(
            SearchPreference.id == pref_id, SearchPreference.user_id == user_id
        )
    )
    if pref is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Preference not found")
    return pref


@router.get("", response_model=list[PreferenceOut])
async def list_preferences(user: CurrentUser, db: DB):
    result = await db.scalars(
        select(SearchPreference)
        .where(SearchPreference.user_id == user.id)
        .order_by(SearchPreference.created_at)
    )
    return result.all()


@router.post("", response_model=PreferenceOut, status_code=status.HTTP_201_CREATED)
async def create_preference(body: PreferenceCreate, user: CurrentUser, db: DB):
    pref = SearchPreference(user_id=user.id, **body.model_dump())
    db.add(pref)
    await db.commit()
    await db.refresh(pref)
    return pref


@router.patch("/{pref_id}", response_model=PreferenceOut)
async def update_preference(pref_id: int, body: PreferenceUpdate, user: CurrentUser, db: DB):
    pref = await _owned_pref(db, user.id, pref_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(pref, field, value)
    await db.commit()
    await db.refresh(pref)
    return pref


@router.delete("/{pref_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preference(pref_id: int, user: CurrentUser, db: DB) -> None:
    pref = await _owned_pref(db, user.id, pref_id)
    await db.delete(pref)
    await db.commit()
