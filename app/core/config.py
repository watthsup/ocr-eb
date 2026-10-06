"""Application settings (pydantic-settings, `.env` driven)."""

from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    APP_NAME: str = "Group Insurance IDP API"
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    PORT: int = 8000

    # 1. OCR engine: Azure Document Intelligence (prebuilt-layout). Mock fallback when unset.
    AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT: Optional[str] = None
    AZURE_DOCUMENT_INTELLIGENCE_KEY: Optional[str] = None
    AZURE_DOCUMENT_INTELLIGENCE_MODEL_ID: str = "prebuilt-layout"
    OCR_CACHE_DIR: str = ".cache/ocr"  # content-hash cache so prompt iteration never re-pays OCR
    OCR_MAX_IMAGE_EDGE_PX: int = 4000

    # 2. LLM (structured outputs). Mock fallback when no key.
    LLM_PROVIDER: Literal["openai", "azure_foundry"] = "openai"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-5.4-mini"
    OPENAI_TEMPERATURE: Optional[float] = None  # ignored for reasoning models (gpt-5*, o*)
    OPENAI_REASONING_EFFORT: Optional[str] = "low"  # minimal|low|medium|high (reasoning models only)
    LLM_MAX_OUTPUT_TOKENS: int = 64000
    LLM_TIMEOUT_SECONDS: float = 300.0

    AZURE_FOUNDRY_ENDPOINT: Optional[str] = None
    AZURE_FOUNDRY_API_KEY: Optional[str] = None
    AZURE_FOUNDRY_DEPLOYMENT_NAME: str = "gpt-4o-mini"
    AZURE_FOUNDRY_API_VERSION: str = "2024-08-01-preview"

    # 3. Dynamic target schema (BA-owned CSV)
    FIELD_CATALOG_PATH: str = "example_data/expected_fields/expected_field_list.csv"

    # 4. Extraction strategy
    SHARD_STRATEGY: Literal["auto", "single", "per_section"] = "auto"
    SHARD_TOKEN_BUDGET: int = 24000  # approx. tokens of document context per LLM call before forcing a split
    SINGLE_SHARD_TOKEN_LIMIT: int = 6000  # below this a multi-section benefit table is still extracted in one call
    MAX_PARALLEL_SHARDS: int = 4
    CENSUS_TABULAR_MODE: bool = True  # header-mapping + pandas rows instead of LLM row extraction

    # 5. Upload limits
    MAX_UPLOAD_SIZE_MB: int = 60
    MAX_FILES_PER_DOCUMENT: int = 60

    @property
    def ocr_enabled(self) -> bool:
        return bool(self.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and self.AZURE_DOCUMENT_INTELLIGENCE_KEY
                    and "placeholder" not in self.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT)

    @property
    def llm_enabled(self) -> bool:
        if self.LLM_PROVIDER == "azure_foundry":
            return bool(self.AZURE_FOUNDRY_ENDPOINT and self.AZURE_FOUNDRY_API_KEY
                        and "placeholder" not in (self.AZURE_FOUNDRY_ENDPOINT or ""))
        return bool(self.OPENAI_API_KEY and not self.OPENAI_API_KEY.startswith("sk-placeholder"))

    @property
    def llm_model_name(self) -> str:
        return self.AZURE_FOUNDRY_DEPLOYMENT_NAME if self.LLM_PROVIDER == "azure_foundry" else self.OPENAI_MODEL


settings = Settings()
