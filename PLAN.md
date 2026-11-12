# Implementation plan

## Completed in this milestone

- Restructure the repository for a backend/frontend architecture.
- Build the source preparation path through portable Markdown and validation reports.
- Preserve reproducible legal/content chunking source with local-only generated outputs.
- Support DOC, DOCX, and XLSX Office sources without treating generated Markdown as input.
- Keep source documents and generated artifacts outside Git.

## Deferred milestones

1. Manual fidelity validation for primary documents, appendices, and forms.
2. Refine the restored chunk design after the validation gate passes.
3. Qdrant hybrid retrieval and document profiles.
4. Neo4j legal graph and relation audit.
5. Evidence allocation, generation, session persistence, and API.
6. React frontend, Docker Compose stack, tracing, and baseline evaluation.
