"""Dynamic field catalog endpoints — inspect or hot-swap the BA-owned CSV."""

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.services.field_catalog import FieldCatalog, get_catalog, set_catalog
from app.services.pipeline_service import get_pipeline_service

router = APIRouter()


@router.get("")
async def read_catalog():
    return get_catalog().public()


@router.post("")
async def replace_catalog(file: UploadFile = File(...)):
    text = (await file.read()).decode("utf-8-sig", errors="replace")
    try:
        catalog = FieldCatalog.from_csv_text(text, source=file.filename or "upload.csv")
    except Exception as exc:
        raise HTTPException(400, f"Could not parse catalog CSV: {exc}")
    if not catalog.specs:
        raise HTTPException(400, "Catalog CSV produced zero fields — check the 'Doc Group' and 'Field Code' columns")
    set_catalog(catalog)
    # propagate to already-built services
    pipeline = get_pipeline_service()
    pipeline.services.extraction.catalog = catalog
    pipeline.services.normalization.catalog = catalog
    return catalog.public()
