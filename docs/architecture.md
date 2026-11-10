# Architecture: ingestion milestone

The repository now exposes preparation and chunking as separate reproducible phases:

```text
Hugging Face source tree
  → package catalog + immutable relative-path identity
  → materialize source (.doc → verified DOCX derivative)
  → format reader (DOCX/text/XLSX)
  → role router
      primary legal text → Markdown + extraction report → manual review
      appendix/form      → Markdown + extraction report → manual review
  → portable local Markdown view + source locators + assets
  → audit report
  → explicit local chunk command
      primary legal text → legal hierarchy → provision chunks
      appendix/form      → parent-linked content chunks
```

`data/source_packages/`, `data/derived/`, `data/artifacts/`, and `data/runtime/` are
intentionally ignored.
Hugging Face can
be used as a private, read-only corpus distribution channel through
`scripts/sync_source_documents.py`. Qdrant, Neo4j, session storage, API, generation,
and frontend are deliberately not implemented yet.

The local command accepts an explicit mock corpus without changing shared settings:

```powershell
python scripts/ingest_documents.py `
  --source-dir data_old/source_docs `
  --output-dir data/artifacts `
  --docx-only
```

`data_old/` and `ingestion_old/` are local comparison inputs and are ignored by Git.
See `docs/ingestion-design.md` for the corpus audit and fidelity rules.

## Source identity and routing

The catalog accepts either a snapshot root containing `Bidding_Law/` or the
`Bidding_Law/` directory itself. In a package folder, the file whose normalized document
code matches the folder code is the primary legal text. Other descendants are classified
as appendices, Word forms, Excel form workbooks, or supplemental files. Temporary Office
files beginning with `~$` are ignored.

The original DOC/XLSX file is always authoritative. DOCX conversions and extracted JSON
are derived data. XLSX formula text is preserved as metadata; cached or calculated formula
values are not treated as authoritative legal facts.

Markdown is a local inspection and interchange view, not the authoritative parser input.
It mirrors source-relative paths under `data/derived/markdown/`, copies referenced assets
beside the Markdown, preserves merged DOCX tables as HTML, and exposes XLSX coordinates,
formulas, validations, and merged ranges. No generated path depends on a developer's
absolute workspace location.

## Reproducible local bootstrap

After cloning, a teammate runs:

```powershell
uv sync --extra dev
uv run python scripts/sync_source_documents.py
uv run python scripts/ingest_documents.py
uv run python scripts/generate_chunks.py
```

This reconstructs ignored local source snapshots, conversions, Markdown, extraction
artifacts, and chunks. Hugging Face remains the source-only store. Future vector/graph
indexes and container volumes live below `data/runtime/` and must be reconstructed by
committed source/configuration rather than committed as state.
