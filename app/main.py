"""FastAPI entrypoint — Group Insurance IDP (census / claims / benefit schedule extraction)."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.services.field_catalog import get_catalog
from app.services.pipeline_service import get_pipeline_service

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    catalog = get_catalog()
    get_pipeline_service()
    logger.info("Starting %s | OCR: %s | LLM: %s (%s) | catalog v%s (%d fields)", settings.APP_NAME,
                "azure-di" if settings.ocr_enabled else "MOCK", settings.LLM_PROVIDER,
                settings.llm_model_name if settings.llm_enabled else "MOCK", catalog.version, len(catalog.specs))
    yield


app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan,
              description="Intelligent Document Processing for group insurance: OCR (Azure DI) → triage → sharded LLM extraction "
                          "driven by a BA-owned field catalog → review & Excel export.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health", tags=["System"])
async def health():
    catalog = get_catalog()
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "ocr_engine": "azure_document_intelligence" if settings.ocr_enabled else "mock",
        "llm": {"provider": settings.LLM_PROVIDER, "model": settings.llm_model_name, "enabled": settings.llm_enabled},
        "catalog": {"version": catalog.version, "field_count": len(catalog.specs)},
    }


app.include_router(api_router, prefix="/api/v1")
