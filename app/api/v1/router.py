from fastapi import APIRouter

from app.api.v1.endpoints import catalog, documents

api_router = APIRouter()
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
api_router.include_router(catalog.router, prefix="/catalog", tags=["Field catalog"])
