# Legal GraphRAG

This repository is being rebuilt as a Legal GraphRAG system for Vietnamese legal
documents. Markdown preparation and chunk generation are reproducible local phases.
Embedding and indexing remain deferred.

## Current scope

```text
Hugging Face Office sources
  → extraction + normalization
  → local Markdown + validation evidence
  → local legal/content chunks
```

Shared source packages accept only `.doc`, `.docx`, and `.xlsx`. Generated Markdown is
never rediscovered as a source. Legacy DOC files are
converted to hash-addressed DOCX derivatives and checked against Word structural metrics.
XLSX forms are read without flattening sheets, merged ranges, formulas, or validations.

## Repository layout

```text
backend/app/core/          settings
backend/app/ingestion/     extraction, normalization, parsing, and chunk source
backend/tests/             extraction, rendering, parser, and chunk tests
scripts/                   corpus sync, Markdown preparation, local chunk generation
data/source_packages/      ignored Hugging Face source tree
data/derived/conversions/  ignored DOC conversion cache
data/derived/markdown/     ignored portable Markdown views and assets
data/derived/chunks/       ignored generated chunks and hierarchy
data/artifacts/            ignored blocks, reports, and validation queue
data/runtime/              ignored database/container volumes
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
uv run python scripts/generate_chunks.py
uv run pytest
```

The Hugging Face dataset contains source Office files only. Sync, DOC conversion,
Markdown, chunks, database indexes, and container volumes stay local and are
ignored by Git. Output locations are configurable through `SOURCE_PACKAGES_DIR`,
`CONVERTED_DOCS_DIR`, `MARKDOWN_OUTPUT_DIR`, `CHUNKS_OUTPUT_DIR`,
`INGEST_ARTIFACTS_DIR`, and `LOCAL_RUNTIME_DIR`.

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

`scripts/generate_chunks.py` is a separate downstream phase. It refuses to run unless the
current source IDs exist in the Markdown-preparation manifest. Primary legal documents use
the legal hierarchy parser; appendices and forms use content windows linked to their parent
document. The generated `chunks.jsonl`, `hierarchy.json`, manifests, and reports live only
under `data/derived/chunks/` and are never committed.

## Shared-code/local-data rule

GitHub contains source code, tests, configuration examples, lockfiles, and runbooks.
Hugging Face contains immutable Office source documents. Each clone recreates all derived
state locally using repository-relative paths:

```text
data/source_packages/   Hugging Face snapshot
data/derived/           conversions, Markdown, chunks
data/artifacts/         extraction/validation evidence
data/runtime/           Qdrant, Neo4j, SQLite, object storage, other container volumes
```

Future Docker Compose files must bind or name volumes beneath `data/runtime/`; no teammate
commits a database, index, container volume, generated Markdown, or generated chunk file.

Qdrant, Neo4j, SQLite, and their container bootstrap are not implemented yet. When added,
their reproducible source/configuration is committed, while state remains under the ignored
`data/runtime/` directory.
