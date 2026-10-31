from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration needed by the ingestion-only first milestone."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    hf_token: str | None = Field(default=None, validation_alias=AliasChoices("HF_TOKEN"))
    hf_repo_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("HF_REPO_ID", "REPO_ID"),
    )
    source_docs_dir: Path = Field(
        default=Path("data/source_packages"),
        validation_alias=AliasChoices("SOURCE_PACKAGES_DIR", "SOURCE_DOCS_DIR"),
    )
    converted_docs_dir: Path = Field(
        default=Path("data/derived/conversions"),
        validation_alias=AliasChoices("CONVERTED_DOCS_DIR"),
    )
    markdown_output_dir: Path = Field(
        default=Path("data/derived/markdown"),
        validation_alias=AliasChoices("MARKDOWN_OUTPUT_DIR"),
    )
    ingest_artifacts_dir: Path = Field(
        default=Path("data/artifacts"),
        validation_alias=AliasChoices("INGEST_ARTIFACTS_DIR"),
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
