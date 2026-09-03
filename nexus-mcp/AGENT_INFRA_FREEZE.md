# Nexus Agent Infrastructure Freeze

Status: FROZEN
Freeze baseline: 2026-09-03
Regression baseline commit: 29e63a77b0974277c919864d366709f65000236b

## Frozen surface

Do not change without an explicit unfreeze decision:

- Hermes is the single v0 agent runtime.
- Nexus exposes exactly five MCP tools:
  1. `inspect_campaign`
  2. `resolve_mapping`
  3. `request_compile`
  4. `run_qa`
  5. `prepare_package`
- Hermes may call only the Nexus MCP tool surface.
- Deterministic Nexus code owns IDs, compile output, QA status, package gating, and CSV column order.
- `run_qa` is fail-closed and cannot be overridden by the agent.
- `prepare_package` may return a package only after deterministic QA PASS.
- `nexus_trafficking.csv` uses the frozen 14-column order.
- No browser, shell, web-search, publishing, DV360 write, CM360 write, or external platform write is part of the agent contract.

## Frozen regression

`nexus-mcp/e2e_acceptance_test.py` must remain green:

1. Original `CRT-004.size = 1920x1080` -> `BLOCKED`.
2. BLOCKED run produces no trafficking artifact.
3. Correct only `CRT-004.size` to `1920x1920`.
4. All six activation IDs and build-row IDs remain unchanged.
5. Deterministic QA returns `PASS`.
6. Package returns `READY_FOR_APPROVAL`.
7. In-memory `nexus_trafficking.csv` contains exactly 14 frozen columns and 6 rows.
8. Hermes discovers exactly 5 tools and completes the corrected inspect -> mapping -> compile -> QA -> package chain.

## Next implementation objective

ONE REAL XLSX -> CANONICAL CAMPAIGN INPUT

Scope for the next change only:

- Accept one real `.xlsx` media-plan file.
- Parse workbook values into the existing canonical Campaign / Audience / Creative / Activation structure.
- Preserve source-row evidence.
- Preserve the existing stable identity and 1:N rules.
- Feed that canonical result into the already-frozen Nexus agent/compiler path.

Explicitly do not change the five MCP schemas, Hermes runtime choice, compile logic, QA logic, package logic, CSV contract, UI, or platform integrations while implementing XLSX ingestion.
