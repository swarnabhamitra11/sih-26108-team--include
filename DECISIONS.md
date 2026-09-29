# Decisions & Limitations

## Known Limitations

1. **Multilingual search**: Translation is only supported via optional LLM translation (`LLM_API_KEY`), as the local embedding model and Postgres FTS are English-specific without a dedicated cross-lingual reranker.
2. **Confidence threshold tuning**: `CONFIDENCE_THRESHOLD` is set to 0.69, based on analysis of cosine similarity where the best score for a gibberish query was compared against the lowest top‑1 cosine among representative real queries, establishing a clear separation.
3. **Dataset scope**: The database currently holds 32 seed standards across Cement, Steel, and Cables extracted from BIS Know Your Standard; independent domain-expert verification remains pending (`verification_status` is predominantly `'entered'`).
4. **Certification & QCO rules**: Certification rules table is currently sparsely populated; all standards without explicitly loaded QCO rules default safely to `status: "needs_review"` with note `"No QCO data loaded"`.
5. **Category classification**: `category` values are stored as free text rather than an enforced SQL enum constraint.
6. **Seed importer gaps**: `scripts/import_seed.py` has minor validation gaps: `product_group` validation is case-sensitive, `category` is unconstrained, and `relation_type` is not strictly required by the importer validator.
7. **Local-only deployment**: Configured for local workstation use with Docker Compose and localhost ports (PostgreSQL on port `5433` to prevent conflicts with native Windows services).
8. **Graph & completeness scoring**: No full transitive graph traversal or automated specification-completeness scoring is implemented; relationships are currently reported up to 1-hop bidirectional depth.
9. **Advisory nature**: All AI and keyword recommendations are purely advisory and require human engineer review before incorporation into production tenders or designs.
10. **Host environment runtime**: Node.js is not installed on the current host system, so Next.js frontend code is scaffolded in `frontend/` ready for `npm install && npm run dev` once Node.js 18+ is available or within a container.

## Next Steps

1. Install Node.js 18+ on the deployment host to launch the Next.js frontend service.
2. Populate the `certification_rules` table with Quality Control Orders (QCO) gazette notifications for mandatory BIS certification.
3. Transition from fallback embeddings to a locally cached sentence transformer model with offline SSL certificate trust.
4. Expand benchmark evaluation suite using the `benchmark_rows` and `benchmark_expected` tables.
