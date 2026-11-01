# Legal GraphRAG

This repository is being rebuilt as a Legal GraphRAG system for Vietnamese legal
documents. The active implementation milestone stops at Markdown preparation and data
validation. Parsing, chunking, embedding, and indexing are disabled for now.

## Current scope

```text
source packages → extraction → normalization → Markdown view → manual validation
```

Shared source packages accept only `.doc`, `.docx`, and `.xlsx`. Generated Markdown is
never rediscovered as a source. Legacy DOC files are
converted to hash-addressed DOCX derivatives and checked against Word structural metrics.
XLSX forms are read without flattening sheets, merged ranges, formulas, or validations.

## Repository layout

```text
backend/app/core/          settings
backend/app/ingestion/     extraction, normalization, and deferred parser prototypes
backend/tests/             extraction and rendering unit tests
scripts/                   corpus sync and Markdown preparation
data/source_packages/      ignored Hugging Face source tree
data/derived/conversions/  ignored DOC conversion cache
data/derived/markdown/     ignored portable Markdown views and assets
data/artifacts/            ignored blocks, reports, and validation queue
docs/                      architecture notes
```

Future modules for Qdrant, Neo4j, API, frontend, sessions, tracing, and evaluation
are intentionally deferred until ingestion is validated.

## Setup

Use Python 3.11 or newer with `uv`, then create the local configuration:

```powershell
Copy-Item .env.example .env
uv sync --extra dev
```

Set `HF_TOKEN` and `HF_REPO_ID` in `.env` only if you need to sync the private shared
corpus. Neither source documents nor generated artifacts are committed.

## Preparation commands

```powershell
uv sync --extra dev
uv run python scripts/sync_source_documents.py
uv run python scripts/ingest_documents.py
uv run pytest
```

The Hugging Face dataset contains source Office files only. Sync, DOC conversion,
Markdown generation and future chunks/database indexes stay local and are
ignored by Git. Output locations are configurable through `SOURCE_PACKAGES_DIR`,
`CONVERTED_DOCS_DIR`, `MARKDOWN_OUTPUT_DIR`, and `INGEST_ARTIFACTS_DIR`.

`scripts/ingest_documents.py` generates Markdown by default. Use `--markdown-dir` to
choose another local directory, or `--no-markdown` when only structured artifacts are
needed. Markdown paths mirror the Hugging Face hierarchy and contain no machine-specific
absolute paths.

The source catalog identifies one primary legal document in each package and links every
appendix/form to it. The current command writes `blocks.jsonl`, `report.json`, Markdown,
assets, and `validation_summary.json`; it does not write hierarchy or chunks. Every source
is marked `requires_review`. In particular, the two legacy review workbooks cover only the
31 primary documents and are not evidence that appendices/forms were extracted correctly.

Artifact directories use source IDs derived from relative paths and hashes, so repeated
filenames cannot overwrite one another. A package is rejected when its primary document
is absent, preventing an isolated form from being treated as an independently validated
legal source.

Qdrant, Neo4j, SQLite, and their local container bootstrap are not implemented in this
milestone yet. When added, their volumes must follow the same rule: local and ignored,
with reproducible rebuild commands committed to the repository.
