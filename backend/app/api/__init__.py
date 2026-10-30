from fastapi import APIRouter

from . import catalogs, dashboard, db_admin, exports, invoices, settings, tulip_live

api_router = APIRouter(prefix="/api")
api_router.include_router(dashboard.router)
api_router.include_router(invoices.router)
api_router.include_router(catalogs.router)
api_router.include_router(exports.router)
api_router.include_router(tulip_live.router)
api_router.include_router(settings.router)
api_router.include_router(db_admin.router)

__all__ = ["api_router"]
