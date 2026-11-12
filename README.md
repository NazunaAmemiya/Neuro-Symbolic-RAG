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

## Teammate bootstrap: clone to review-ready data

The full legacy `.doc` audit path requires Windows, PowerShell, and Microsoft Word. Word
is used to create hash-addressed `.docx` derivatives and to compare structural metrics
before and after conversion. The command fails rather than silently selecting a different
converter when Word is unavailable. Install Git, Python 3.11, and `uv`, then run:

```powershell
git clone https://github.com/NazunaAmemiya/Neuro-Symbolic-RAG.git
Set-Location Neuro-Symbolic-RAG
git pull --ff-only

Copy-Item .env.example .env
notepad .env
```

Set the Hugging Face dataset in `.env`. Add `HF_TOKEN` only when the dataset requires
authentication; never commit the token:

```dotenv
HF_REPO_ID=AmemiyaNazuna/Bidding_Law
HF_TOKEN=
```

Create the environment, download the source-only corpus, and generate fresh unreviewed
local inspection data:

```powershell
uv sync --python 3.11 --extra dev
uv run python scripts/sync_source_documents.py
uv run python scripts/ingest_documents.py

uv run python scripts/audit_hf_coverage.py
uv run python scripts/audit_markdown_fidelity.py
uv run python scripts/audit_xlsx_fidelity.py
uv run python scripts/audit_formulas.py
uv run pytest
```

At this point the clone is ready for an independent review. Do **not** run
`curate_formula_reviews.py` before inspecting the formulas: that command reproduces the
existing transcriptions and is not evidence that the current reviewer checked them.
Open the local review material with:

```powershell
explorer data\source_packages
explorer data\derived\conversions
explorer data\derived\markdown
explorer data\artifacts

Get-ChildItem data\derived\conversions -Recurse -Filter *.conversion.json
Get-Content data\artifacts\validation_summary.json
```

Review the authoritative Office source against the converted DOCX, Markdown, assets, and
artifact report. `report.json` records `metadata.converted_docx`, which maps each original
`.doc` to its hash-addressed local conversion. The main local outputs are:

```text
data/source_packages/       Hugging Face Office sources
data/derived/conversions/   DOCX conversions and *.conversion.json reports
data/derived/markdown/      Markdown views and copied media
data/artifacts/             blocks.jsonl, report.json, manifests, review queue
data/derived/*audit*.json   structural audit reports
```

All of these paths are ignored by Git. Re-running the commands from the same immutable
source hashes recreates them locally.

## After visual review: reviewed formulas and chunks

After the reviewer has compared the formulas with the original Office pages, reproduce
the source-hash-bound review registry, regenerate the reviewed views, and chunk them:

```powershell
uv run python scripts/curate_formula_reviews.py
uv run python scripts/ingest_documents.py --formula-reviews data/derived/formula_reviews.json
uv run python scripts/audit_formulas.py --formula-reviews data/derived/formula_reviews.json
uv run python scripts/generate_chunks.py --formula-reviews data/derived/formula_reviews.json
uv run python scripts/audit_chunks.py
uv run pytest
```

The final chunk audit must report `failed_documents: 0` before downstream embedding or
indexing. A passing structural audit still does not replace legal/visual human approval.

The Hugging Face dataset contains source Office files only. Sync, DOC conversion,
Markdown, chunks, database indexes, and container volumes stay local and are
ignored by Git. Output locations are configurable through `SOURCE_PACKAGES_DIR`,
`CONVERTED_DOCS_DIR`, `MARKDOWN_OUTPUT_DIR`, `CHUNKS_OUTPUT_DIR`,
`INGEST_ARTIFACTS_DIR`, and `LOCAL_RUNTIME_DIR`.

`scripts/ingest_documents.py` generates Markdown by default. Use `--markdown-dir` to
choose another local directory, or `--no-markdown` when only structured artifacts are
needed. Markdown paths mirror the Hugging Face hierarchy and contain no machine-specific
absolute paths.

OMML equations are retained with source locators and an unverified LaTeX candidate.
Formula images retain their original bytes; WMF/EMF also get a PNG preview on Windows.
For optional **local** image formula OCR, use Python 3.11 and run
`uv sync --python 3.11 --extra dev --extra formula-ocr`, then
`uv run python scripts/ingest_documents.py --formula-ocr pix2tex`. The model may download
weights on first use. OCR text is stored only as an unverified candidate; check it against
the original DOCX before using it for retrieval. The default command runs without OCR.
`scripts/audit_formulas.py` writes an ignored local review queue to
`data/derived/formula_audit.json`. Its byte checks do not establish semantic correctness.
After checking an expression against the original image, put its LaTeX in a local
`data/derived/formula_reviews.json` review file with the source and media SHA-256 hashes,
`status: "reviewed_visual"`, and a reviewer name. Pass
`--formula-reviews data/derived/formula_reviews.json` to both ingestion and formula audit.
An edited DOCX or image gets a new hash, so its older review cannot be applied. The
review file is local derived data and is ignored by Git.
`scripts/curate_formula_reviews.py` is the reproducible registry for expressions that have
been visually checked in this corpus; it writes only the ignored review file and binds each
record to the exact source and media hashes. Re-run the final ingestion command after it so
the reviewed transcription is represented in the local Markdown and audit artifacts.

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
Run it only after Markdown, tables, and formulas have been reviewed.
Tables and formula blocks are emitted as standalone chunks with source locators, structure,
assets, and review metadata. XLSX chunks retain formulas and cached values. No table is
silently filtered as letterhead or boilerplate; classification can be added only with an
explicitly audited rule.

Run `scripts/audit_markdown_fidelity.py` before considering generated Markdown for
chunking. It compares source hashes and DOCX body table counts, checks rendered table
counts and image links, and compares copied media bytes with the Office package. A passing
result proves structural coverage for the inspected files, not visual or semantic
equivalence. The audit now also fails if any local `.doc`, `.docx`, or `.xlsx` source is
absent from the preparation manifest. `scripts/audit_formulas.py` handles DOCX only and
reports skipped `.doc`/`.xlsx` files explicitly. Compare the synced source inventory with
the current Hugging Face revision before claiming full corpus coverage.
`scripts/audit_xlsx_fidelity.py` separately checks workbook sheets, non-empty cells,
formulas, cached formula results, merges, data validations, hidden rows/columns, and
packaged media against the source workbook. `scripts/audit_chunks.py` then requires every
prepared block to appear in exactly one chunk, verifies table/formula metadata and text,
checks XLSX formulas and cached values, and confirms appendix/form linkage. A passing chunk
audit proves exact preservation of prepared artifacts, not semantic legal correctness.

`scripts/audit_hf_coverage.py` reads the current Hugging Face file list without downloading
it again. It exits with an error when any Office source path is absent from the synced local
directory or the preparation manifest. It checks path coverage; the Markdown and formula
audits check copied content and extraction details separately.

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
