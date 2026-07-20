from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from pharma_api.api.dependencies import DBSession, require_permission
from pharma_api.application.auth.types import AuthContext
from pharma_api.infrastructure.db.models.rbac import Permission
from pharma_api.schemas.rbac import PermissionResponse

router = APIRouter(prefix="/permissions", tags=["permissions"])
Reader = Annotated[AuthContext, Depends(require_permission("role.read"))]


@router.get("", response_model=list[PermissionResponse])
async def get_permissions(session: DBSession, auth: Reader) -> list[PermissionResponse]:
    permissions = (
        await session.scalars(
            select(Permission)
            .where(Permission.key.in_(auth.permission_keys))
            .order_by(Permission.key)
        )
    ).all()
    return [PermissionResponse.model_validate(permission) for permission in permissions]
