# Repository instructions

## Public boundary

- Treat the repository, its full Git history, CI logs, build artifacts, and GitHub Pages output as public.
- Keep published content under `content/research/`. Do not add journals, trades, positions, account data, broker exports, entry or exit prices, stop levels, targets, P&L, or personal decision records.
- Keep secrets in ignored local environment files. Never commit API keys, tokens, credentials, account identifiers, or private filesystem paths.
- Before every push, run `make check`, `make render`, and `git diff --check`. Inspect `_site/` with `scripts/check-site.ts` before deployment.

## Content and computation

- Markdown owns report prose, formulas, tables, citations, and conclusions.
- Python owns data retrieval, statistics, and versioned Plotly snapshots.
- A normal site build must not fetch data, rerun analysis, or change report conclusions.
- Preserve unrelated report prose, sources, data snapshots, and user edits.
