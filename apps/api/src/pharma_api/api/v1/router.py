from fastapi import APIRouter

from pharma_api.api.v1.audit_events import router as audit_events_router
from pharma_api.api.v1.auth import router as auth_router
from pharma_api.api.v1.branches import router as branches_router
from pharma_api.api.v1.companies import router as companies_router
from pharma_api.api.v1.economic_groups import router as economic_groups_router
from pharma_api.api.v1.health import router as health_router
from pharma_api.api.v1.invitations import router as invitations_router
from pharma_api.api.v1.me import router as me_router
from pharma_api.api.v1.memberships import router as memberships_router
from pharma_api.api.v1.onboarding import router as onboarding_router
from pharma_api.api.v1.permissions import router as permissions_router
from pharma_api.api.v1.platform import router as platform_router
from pharma_api.api.v1.roles import router as roles_router
from pharma_api.api.v1.sessions import router as sessions_router
from pharma_api.api.v1.teams import router as teams_router
from pharma_api.api.v1.tenants import router as tenants_router
from pharma_api.api.v1.users import router as users_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(sessions_router)
api_router.include_router(me_router)
api_router.include_router(onboarding_router)
api_router.include_router(tenants_router)
api_router.include_router(economic_groups_router)
api_router.include_router(companies_router)
api_router.include_router(branches_router)
api_router.include_router(users_router)
api_router.include_router(memberships_router)
api_router.include_router(teams_router)
api_router.include_router(invitations_router)
api_router.include_router(roles_router)
api_router.include_router(permissions_router)
api_router.include_router(audit_events_router)
api_router.include_router(platform_router)
