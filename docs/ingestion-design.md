# DOCX ingestion design for the 31-document corpus

## Decision

The repository-relative Office source is canonical. A legacy DOC remains immutable and
its verified DOCX conversion is a derived extraction input. The legacy Markdown is
evidence for regression testing, not an intermediate format in the production path.
Markdown cannot faithfully represent
merged cells, positioned images, OLE attachments, footnote links, or run-level subscript
and superscript semantics without extra sidecar data.

Markdown preparation and chunk generation are separate commands. Chunk source is versioned,
but generated hierarchies/chunks remain local and are not proof of validated legal truth.
The project does not yet write Qdrant, Neo4j, or SQLite.

Folder packages preserve the relationship between a circular and its appendices/forms.
Identity uses the full repository-relative path plus the source hash, never the basename.
This is required because multiple circulars contain forms with the same filename but
different legal parentage and potentially different content.

## Corpus audit

The local mock corpus contains 31 DOCX files, 31 legacy Markdown files with locator
sidecars, and two review workbooks. Inspection of the DOCX packages found:

- 27,491 paragraphs and 291 tables;
- 1,475 horizontal merges and 425 vertical merges;
- 64 media files, 15 embedded OLE objects, and 15 embedded package attachments;
- 23 footnote references across three documents;
- 423 superscript and 145 subscript runs;
- no native Word OMML formula objects.

The formulas called out as missing by the reviewers are primarily raster images or legacy
OLE content. The missing appendices/forms are often embedded `Package` objects. Therefore,
reading only `Paragraph.text` and `cell.text` can never be complete.

The review workbooks and direct OOXML checks identify four distinct problem classes:

1. **Extraction loss**: formula images, footnotes, attachments, and some tables disappear.
2. **Structural loss**: merged cells become duplicated columns and every first row is
   incorrectly assumed to be a table header.
3. **Parser errors**: provisions quoted by an amending document (for example inserted
   Điều 29b or Điều 44a/44b) become false source-level articles.
4. **Source-data anomalies**: examples such as `D ³ 25%` and duplicate point labels are
   already present in the DOCX. They must be flagged, not silently corrected.

One missing heading was caused by decomposed Unicode (`Điều 71`). NFC normalization is
therefore mandatory before legal-heading recognition.

## Data model

Each DOCX is transformed into an ordered block stream:

- `paragraph`: text plus bold/italic/subscript/superscript spans and footnote references;
- `table`: logical cells with row/column coordinates and row/column spans;
- `image`: preserved media with a stable asset ID;
- `formula`: preserved formula image plus a review-required placeholder;
- `attachment`: raw OLE object and, when possible, its unpacked native payload.

Every block has a stable ID and an OOXML locator. Binary assets are stored separately and
referenced by ID; binary data is never embedded in block/report JSON.

## Legal parsing rules

Parsing runs over normalized structured blocks, not generated Markdown.

- Source provisions and quoted/amended provisions have separate `scope` values.
- An amendment cue such as “bổ sung ... như sau” becomes active only when the following
  quoted block starts. This prevents an unrelated later article from remaining in the
  amended scope.
- Stable node IDs use the document fingerprint, semantic parent path, provision kind,
  label, scope, and sibling occurrence. They do not depend on mutable line numbers.
- Sequence validators report duplicate/out-of-order points and article gaps. They never
  rewrite legal text.

## Chunk contract

A chunk contains the leaf provision text plus necessary parent context, source/amended
scope, semantic labels, source block IDs, asset IDs, and source order range. Tables,
formula placeholders, footnotes, and attachment references remain attached to the legal
provision that owns them.

Formula OCR output must not be used as authoritative text until reviewed. For now, formula
images are preserved and produce an explicit `formula_image_requires_transcription`
warning. Extracted OLE payloads similarly produce a notice because recursive ingestion of
the attached DOCX/PDF/XLSX is a separate next step.

XLSX form workbooks are routed separately from legal provisions. The reader records sheet
names, populated cells, merged ranges, formulas, data validations, and images. Formula
expressions remain metadata and are not evaluated or embedded as legal conclusions.

## Markdown view

Markdown is generated only as a local derived view. It is never fed back into extraction
or treated as a replacement for the original Office file or structured block JSON. Paths
mirror the Hugging Face source hierarchy and all media links are relative, so another
developer can regenerate the same layout in a different clone location.

DOCX tables use embedded HTML when row/column spans are present. XLSX sheets use an
explicit coordinate/value/formula table so sparse cells and formulas are not mistaken for
a simple rectangular text table.

## Artifact layout

```text
data/artifacts/
  manifest.json
  <package-id>/
    <source-id>/
      blocks.jsonl
      report.json
      assets/
  validation_summary.json

data/derived/markdown/
  <source-relative-path>.md
  <source-parent>/_assets/<source-id>/

data/derived/chunks/
  manifest.json
  <package-id>/<source-id>/
    chunks.jsonl
    hierarchy.json
    report.json
```

The report records extraction counts and lossy or ambiguous cases, but a successful run
means only that extraction completed. It is not proof of visual or semantic fidelity.
All sources remain `requires_review`; appendices and forms explicitly record that no
reference validation set currently exists.
