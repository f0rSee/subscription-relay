from __future__ import annotations

from fastapi import APIRouter, Depends

from ..security import require_admin
from . import auth, dashboard, observability, profiles, settings, subscriptions

router = APIRouter(prefix="/api")
router.include_router(auth.router)

protected_router = APIRouter(dependencies=[Depends(require_admin)])
protected_router.include_router(dashboard.router)
protected_router.include_router(subscriptions.router)
protected_router.include_router(profiles.router)
protected_router.include_router(observability.router)
protected_router.include_router(settings.router)
router.include_router(protected_router)
