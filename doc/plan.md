# Implementation Plan: Macro Regime-Based Two-Stage Screening System (MVP)

> Purpose: define the final implementation-ready delivery order, current-state gap analysis, file-touch guidance, verification gates, and documentation consolidation path for the MVP.

## 1. Final authority and doc-set consolidation

The final human-facing markdown set is:
1. `doc/strategy.md`
2. `doc/prd.md`
3. `doc/plan.md`
4. `doc/open-questions.md`

This plan assumes that the following historical inputs were fully absorbed during consolidation and are no longer part of the final human-facing doc set:
- `doc/mvp-doc-clarifications-us-focused.md`
- `doc/requirements.md`
- `.omc/plans/open-questions.md`
- `.omc/plans/elaborated-implementation-plan.md`

Authority order for execution:
1. preserve the MVP boundary from `doc/strategy.md`
2. implement against the detailed product/data-contract requirements in `doc/prd.md`
3. sequence and verify work according to `doc/plan.md`
4. treat `doc/open-questions.md` as the only surviving unresolved-question list

**Execution gate (2026-03-22):** only Phase 1 grounding work may continue for now. Phases 2a-6 stay blocked until `doc/open-questions.md` reaches zero material implementation blockers and one concrete versioned Stage 1 sector-rank-table / channel-weight artifact is frozen.

## 2. Grounded current-state evidence

The repo already has a real package/runtime skeleton. The remaining final-stage gap is not project scaffolding; it is the mismatch between current implementation behavior and the now-frozen final documentation posture.

### 2.1 What the codebase already has
- scheduled/manual/backtest seams already exist in `src/macro_screener/pipeline/runner.py`, `src/macro_screener/pipeline/scheduler.py`, `src/macro_screener/backtest/engine.py`, and `src/macro_screener/cli.py`
- SQLite already has operational tables for snapshots, published windows, ingestion watermarks, and channel-state snapshots in `src/macro_screener/db/store.py`
- `src/macro_screener/contracts.py` is already effectively a compatibility shim over `src/macro_screener/models/contracts.py`
- Stage 2 already implements disclosure classification, decay, normalization, and ranking
- `StockScore` already uses `block_scores` as the canonical block-breakdown shape, so no further `block_breakdown` migration is needed
- the older DB-path split and top-level contract-test filename collision were largely resolved at the source-file level; only cleanup-level confirmation may still remain

### 2.2 What still mismatches the final doc stance
- Stage 1 still uses symmetric exposure × state scoring rather than rank-derived priors (`src/macro_screener/stage1/base_score.py`, `src/macro_screener/stage1/ranking.py`)
- `ChannelState` still lacks the full final metadata contract (`src/macro_screener/models/contracts.py`)
- macro ingestion still centers on manual or last-known channel-state behavior (`src/macro_screener/data/macro_client.py`)
- KRX ingestion still relies on local/demo loaders and keyword heuristics rather than the final KRX + local-CSV authority model (`src/macro_screener/data/krx_client.py`)
- DART ingestion still centers on `list.json` plus weak watermark fallback rather than a structured monotone disclosure cursor with full metadata (`src/macro_screener/data/dart_client.py`)
- current docs still need final-stage consolidation around Korea + US-only external macro, full sector-rank tables, local CSV authority, and cleanup of redundant markdown

### 2.3 Final framing correction from the last clarification pass
The final-stage implementation posture is:
- **Korea + US-only external macro**, not broad multi-country runtime coverage
- **actual realized official data first**, not projection-heavy or broad aggregate sources
- **local CSV authority** for common-stock filtering and industry taxonomy
- **simple channel combination** inside each channel
- **full ordered sector-rank tables + rank-to-score transform** for Stage 1
- **PIT-safe DART + macro metadata** for both live and replay paths

## 3. Decisions already settled and carried forward

These points are no longer open and should not be re-litigated during implementation:
- KRX official endpoints are the primary market/universe source
- `stock_classification.csv` is the authoritative common-stock filter and stock-to-industry mapping input
- if needed, a derived `industry_master.csv` is generated from the local classification CSV
- DART half-life defaults are:
  - `supply_contract = 20`
  - `treasury_stock = 10`
  - `facility_investment = 60`
  - `dilutive_financing = 60`
  - `correction_cancellation_withdrawal = 10`
  - `governance_risk = 120`
- normalization uses cross-sectional z-scores; zero variance maps to `0`; `lambda` is applied after normalization
- current runtime baseline keeps the Stage 2 industry contribution weight config-owned and currently set to `0.35`
- the fast-overlay trigger baseline remains `5%` versus the latest workday close unless a later explicit config/version change replaces it
- the Korea holiday calendar remains a hardcoded MVP list behind the project calendar helper
- backtest may process independent replay dates in parallel
- DART API keys come from environment/secret sources; local development already resolves this through `.env`

## 4. RALPLAN-DR summary

### Principles
1. Freeze the final data contracts and scoring semantics before widening adapter work.
2. Preserve the MVP boundary while consolidating the doc set into one authoritative surface.
3. Prefer Korea + US realized data over broad global or projection-heavy alternatives.
4. Preserve PIT safety and degraded-mode visibility in every implementation phase.
5. Delete redundant markdown only after the surviving docs fully subsume its substance.

### Top decision drivers
1. **Scope correction:** the US-focused clarification supersedes the older broad-global provider framing.
2. **Implementation readiness:** executors need file-specific guidance for the still-open schema, scoring, adapter, and replay gaps.
3. **Doc sprawl reduction:** historical corrective markdown must be folded into the final strategy/prd/plan/open-questions set.

### Viable options
| Option | Summary | Pros | Cons |
|---|---|---|---|
| A. Consolidate into one final doc set and implement against it **(chosen)** | rewrite/expand the main docs, create one final open-questions file, and retire redundant markdown | lowest long-term ambiguity; best execution handoff | requires careful merging so detail is not lost |
| B. Keep historical inputs beside final docs | preserve requirements/clarifications/elaborated notes as references | less destructive; easier raw audit trail | leaves competing authority and contradicts the final-stage cleanup goal |
| C. Minimal patching only | lightly tweak main docs and keep the old notes | smallest edit surface | does not satisfy the request that final plan/prd absorb the current markdown guidance |

## 5. ADR

### Decision
Adopt Option A. The final implementation is executed from a consolidated doc set centered on `doc/strategy.md`, `doc/prd.md`, `doc/plan.md`, and `doc/open-questions.md`, with Korea + US-only external macro, local CSV authority, simple channel combination, and full sector-rank tables treated as the final MVP posture.

### Drivers
- the US-focused clarification materially changes the runtime/provider scope
- the existing code already has enough scaffolding that the remaining work is mostly contract, scoring, adapter, PIT, and cleanup hardening
- redundant markdown should not survive once its substance is merged into the final doc set

### Alternatives considered
- **retain broad BIS/OECD/IMF runtime adapters:** rejected because the final clarification narrows MVP runtime scope to Korea + US only
- **retain historical corrective markdown as live references:** rejected because that keeps doc authority fragmented

### Why chosen
This creates a stable implementation handoff surface, keeps the still-useful details from historical notes, and removes ambiguity about what the final stage should actually build.

### Consequences
- `doc/prd.md` becomes the single authoritative source for provider scope, exact Korea/US series roster, local CSV authority, channel semantics, rank-table scoring, and degraded-mode requirements
- `doc/plan.md` becomes the single authoritative source for file-touch guidance, migration ordering, verification gates, staffing, and markdown cleanup
- `doc/open-questions.md` replaces older planning open-question files

## 6. Locked implementation defaults carried forward from existing docs

The following runtime/document defaults are treated as fixed for final-stage planning unless explicitly changed in a later versioned config/docs change:
- DART half-life defaults listed in Section 3
- fast-overlay baseline trigger threshold: `5%` versus the latest workday close
- normalization: cross-sectional z-score, zero variance → `0`, lambda after normalization
- current runtime baseline Stage 2 industry contribution weight: `0.35`
- hardcoded Korea holiday list for MVP
- support for parallel processing of independent replay dates

## 7. Phase plan

### Phase 1 — Final contract and taxonomy freeze
**Goal:** freeze the provider/runtime contract, Korea+US series roster, taxonomy authority, and historical doc consolidation rules before further implementation diverges.

**Primary work:**
- freeze the final MVP provider roster: KRX, DART, ECOS, KOSIS, local classification CSV, US macro adapter layer via FRED/ALFRED or equivalent official-source routing
- freeze the exact Korea/US core series roster by channel
- freeze the source-priority rule (official actual > topic dataset actual > WEO reference/backfill)
- freeze local CSV authority and the derived industry-master generation rule
- freeze the Stage 1 sector-rank-table schema and rank-to-score transform as the canonical scoring representation
- consolidate the surviving human-facing docs and identify which markdown files become redundant

**Likely implementation surfaces:**
- `doc/strategy.md`
- `doc/prd.md`
- `doc/plan.md`
- `doc/open-questions.md` (new)
- `README.md` if doc references or high-level wording need cleanup

**Acceptance criteria:**
- no final doc treats BIS/OECD/IMF as mandatory MVP runtime adapters
- Korea + US-only external-macro scope is explicit everywhere
- the local CSV authority rule and derived industry-master rule are explicit
- the final doc set is clear and historical corrective docs are marked for removal

**Verification:**
- doc review confirms the provider roster, series roster, local authority rules, and source-priority rules are consistent across strategy/prd/plan
- at least one validated request/response fixture or sample contract example exists per provider family before Phase 3 scales up

### Phase 2a — ChannelState schema expansion and combination-contract widening
**Goal:** align the runtime contract with the final PRD before changing the Stage 1 scoring formula.

**Primary work:**
- add missing ChannelState fields: `as_of_timestamp`, `input_cutoff`, `source_version`, `fallback_mode`, `warning_flags`
- rename `source` to `source_name` with backward-compatible deserialization
- widen macro-load results so adapters can produce full ChannelState metadata rather than a thin state-only payload
- add any missing per-channel explanation fields needed by Stage 1 output
- formalize the simple channel-combination rule in runtime/config terms
- if necessary, bump schema version and add migration handling for stored channel-state payloads

**Specific file touch guidance:**
| File | Required change |
|---|---|
| `src/macro_screener/models/contracts.py` | expand `ChannelState`; preserve backward-compatible serialization; add any per-channel output-explanation support |
| `src/macro_screener/data/macro_client.py` | widen `MacroLoadResult` or equivalent payload to carry full metadata |
| `src/macro_screener/stage1/channel_state.py` | build full ChannelState records with metadata |
| `src/macro_screener/pipeline/runner.py` | propagate renamed/source metadata consistently |
| `src/macro_screener/db/store.py` | migrate schema/version handling for expanded channel-state payloads if required |

**Acceptance criteria:**
- ChannelState can represent the full PRD-required metadata contract
- old serialized payloads still deserialize cleanly
- the runtime can distinguish neutral from missing/fallback cases without guessing

**Verification:**
- contract tests cover old/new serialization paths
- existing tests still pass before Phase 2b begins

### Phase 2b — Stage 1 scoring migration to rank-derived priors
**Goal:** replace symmetric exposure multiplication with the final full sector-rank-table model.

**Primary work:**
- replace exposure-only scoring with weighted rank-derived scoring from full sector-rank tables
- implement the deterministic rank-to-score transform
- keep `z_c = 0` contribution at zero
- preserve overlays as additive and separate from the structural Stage 1 base score
- propagate per-channel contribution breakdowns into Stage 1 outputs
- formalize the equal-weight default in config

**Specific file touch guidance:**
| File | Required change |
|---|---|
| `src/macro_screener/stage1/base_score.py` | replace symmetric exposure logic with rank-derived score lookup |
| `src/macro_screener/stage1/ranking.py` | consume sector-rank tables and emit contribution breakdowns |
| `src/macro_screener/config/types.py` | define canonical sector-rank-table and channel-weight config shape |
| `src/macro_screener/config/defaults.py` | add default rank tables, weights, overlay defaults, and any transform defaults |
| `src/macro_screener/stage1/overlay.py` | verify additive overlay behavior remains explicit |

**Acceptance criteria:**
- Stage 1 scores come from rank tables, not exposure multiplication
- per-channel contribution breakdown is persisted in Stage 1 output
- `+1` and `-1` are not forced into mirror-image reverse orderings
- the middle sector band maps to neutral as documented

**Verification:**
- Stage 1 tests cover deterministic ranking, tie-breaks, neutral handling, per-channel contribution output, and overlay coexistence
- config tests validate the sector-rank-table schema and equal-weight defaults

### Phase 3 — Provider adapter implementation
**Goal:** implement the final MVP adapter roster and stop planning around non-MVP broad-global adapters.

**Primary work:**
- implement KRX Open API adapter behavior for universe master and overlays, joined to the authoritative local classification CSV
- implement DART incremental ingestion with monotone disclosure cursoring, detail resolution, and amendment-safe behavior
- implement Korea macro adapters for ECOS and KOSIS
- implement US macro adapter behavior through FRED/ALFRED or equivalent official-source routing
- keep manual/stub macro override support and last-known fallback support for degraded runs
- do **not** treat BIS/OECD/IMF broad adapters as MVP runtime targets

**Specific file touch guidance:**
| File | Required change |
|---|---|
| `src/macro_screener/data/krx_client.py` | live KRX retrieval + local CSV join + authoritative common-stock filtering |
| `src/macro_screener/data/dart_client.py` | corp-code sync, cursor migration, detail pulls, amendment-safe handling |
| `src/macro_screener/data/macro_client.py` | ECOS/KOSIS + US macro adapter boundary; fallback metadata propagation |
| `src/macro_screener/config/types.py` / `defaults.py` | provider-specific configuration and source metadata |
| `tests/fixtures/` | provider-family fixtures for KRX, DART, Korea macro, US macro |

**Acceptance criteria:**
- scheduled/manual runs can ingest real KRX and DART payloads through explicit contracts
- Korea/US macro adapters align with the fixed per-channel series roster
- local CSV remains authoritative for common-stock filtering and taxonomy
- no Phase 3 task assumes BIS/OECD/IMF MVP runtime adapters

**Verification:**
- adapter tests cover KRX normalization/filtering, DART cursor advancement, Korea/US series metadata persistence, and fallback propagation

### Phase 4 — PIT-safe watermark and replay hardening
**Goal:** make live and historical paths share the same release-aware, amendment-safe model.

**Primary work:**
- replace weak DART watermark behavior with structured monotone cursor metadata
- persist observation date, release date, retrieval timestamp, and transformation metadata for Korea and US series
- decide between ALFRED vintages and persisted release snapshots for pre-go-live historical backfill
- ensure historical replay never consumes future DART amendments or future macro releases
- keep `run_id` attempt-unique and separate from scheduled business-window identity

**Specific file touch guidance:**
| File | Required change |
|---|---|
| `src/macro_screener/data/dart_client.py` | structured cursor + retry/source metadata |
| `src/macro_screener/data/macro_client.py` | release/vintage-aware metadata persistence |
| `src/macro_screener/backtest/engine.py` | cutoff-safe replay ingestion |
| `src/macro_screener/backtest/snapshot_store.py` | replay namespace isolation |
| `src/macro_screener/db/store.py` | richer watermark/release metadata persistence |
| `src/macro_screener/pipeline/runner.py` | consistent cutoff propagation into all ingestion calls |

**Acceptance criteria:**
- page number is never the durable DART cursor
- replay uses only historically visible Korea/US macro releases
- DART amendments do not leak backward
- replay outputs stay isolated from live output namespaces

**Verification:**
- backtest tests cover no-look-ahead, amendment non-leakage, and replay reproducibility
- watermark tests cover retries, cutoff metadata, and repeated-run stability

### Phase 5 — Scheduler recovery and degraded-mode hardening
**Goal:** make scheduled/manual production runs operationally robust.

**Primary work:**
- remove silent demo-path dependence from scheduled execution
- implement missed-run recovery and duplicate-window skipping
- persist degraded-mode warnings for stale DART, missing Korea/US macro responses, last-known fallback, and publication failures
- keep Stage 1-only incomplete publication when Stage 2 fails after Stage 1 succeeds
- preserve immutable latest-pointer behavior for published windows

**Specific file touch guidance:**
| File | Required change |
|---|---|
| `src/macro_screener/pipeline/runner.py` | explicit production path and warning propagation |
| `src/macro_screener/pipeline/scheduler.py` | missed-run detection and duplicate-window skip rules |
| `src/macro_screener/pipeline/runtime.py` | idempotent bootstrap for final runtime directories/state |
| `src/macro_screener/pipeline/publisher.py` | verify incomplete publication + latest-pointer behavior |
| `src/macro_screener/cli.py` | explicit non-demo manual path + deprecated demo wrapper handling |
| `src/macro_screener/db/store.py` | publication dedupe and fallback-state persistence verification |

**Acceptance criteria:**
- scheduled and manual runs no longer rely on hidden demo-only behavior
- duplicate-window recovery never overwrites a published window
- operators can see which fallbacks were used and why
- warning/cutoff/fallback metadata is persisted alongside the run outcome

**Verification:**
- pipeline tests cover scheduled success, duplicate recovery skip, Stage 2 failure → incomplete publication, warning propagation, and latest-pointer integrity
- CLI smoke tests cover scheduled/manual production paths

### Phase 6 — Residual cleanup and final markdown cleanup
**Goal:** finish supporting cleanup only after the final contract and runtime model are stable.

**Primary work:**
- converge any remaining contract duplication around the canonical model layer
- clean stale wrappers/imports and final schema/version details
- remove redundant markdown inputs and drafts
- create/keep only the final open-questions file
- clean broken doc references in README if needed

**Specific file touch guidance:**
| File | Required change |
|---|---|
| `src/macro_screener/contracts.py` | keep as thin shim or retire when import sites are fully migrated |
| `src/macro_screener/models/contracts.py` | final field audit against the PRD |
| `src/macro_screener/db/store.py` | final schema/version cleanup |
| `README.md` | doc reference cleanup if stale links remain |
| project markdown files | delete drafts/historical notes that are fully subsumed |

**Acceptance criteria:**
- one authoritative human-facing doc set remains
- no final doc references retired historical markdown inputs as active authorities
- contract/DB cleanup does not reopen settled provider or scoring semantics
- final docs remain aligned with the delivered MVP boundary

**Verification:**
- final regression suite passes for config, Stage 1, Stage 2, pipeline, and backtest coverage
- final doc review confirms the surviving markdown set is self-sufficient

## 8. Markdown cleanup outcome

### Keep
- `README.md`
- `doc/strategy.md`
- `doc/prd.md`
- `doc/plan.md`
- `doc/open-questions.md`

### Retired during consolidation
- `doc/mvp-doc-clarifications-us-focused.md`
- `doc/requirements.md`
- `.omc/plans/open-questions.md`
- `.omc/plans/elaborated-implementation-plan.md`

## 9. Cross-phase risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| broad-global provider assumptions survive into execution | wrong Phase 3 scope and wasted adapter work | freeze Korea + US-only external scope in final docs before further implementation |
| missing/stale inputs are still coerced to neutral | false signal quality and hidden degraded runs | enforce the full ChannelState metadata contract in Phase 2a |
| local CSV authority is treated as optional | unstable universe filtering and taxonomy drift | freeze CSV + derived industry-master authority in Phase 1 and implement KRX+CSV join in Phase 3 |
| Stage 1 keeps the old favored-list or exposure-symmetric model | ranking behavior stays under-specified or incorrect | freeze full ordered sector-rank tables + rank-to-score transform in PRD and implement in Phase 2b |
| replay uses future DART or macro data | invalid historical evidence | implement structured DART cursoring and release/vintage-aware Korea/US macro metadata in Phase 4 |
| doc sprawl persists after the final stage | execution ambiguity and stale references | delete redundant markdown in Phase 6 after consolidation |

## 10. Execution staffing guidance

### Sequential Ralph staffing
1. **Phase 1** — `writer` / `planner` tighten surviving docs and provider fixtures; `critic` validates scope and authority.
2. **Phase 2a** — `architect` reviews ChannelState/schema changes; `executor` implements contract expansion; `test-engineer` verifies backward compatibility.
3. **Phase 2b** — `executor` implements Stage 1 rank-table scoring; `test-engineer` expands Stage 1 coverage.
4. **Phase 3** — `executor` lane A handles KRX + CSV and DART; `executor` lane B handles ECOS/KOSIS and US macro adapter work.
5. **Phase 4** — `executor` hardens PIT/replay; `test-engineer` adds replay coverage.
6. **Phase 5** — `executor` hardens scheduler/recovery/publisher/CLI; `test-engineer` expands pipeline coverage.
7. **Phase 6** — `executor` performs cleanup; `verifier` performs final regression and doc-consistency sign-off.

### Parallel team staffing
- **Lane A — contracts/config:** `models/contracts.py`, config schema/defaults, doc contract lock
- **Lane B — Stage 1 scoring:** `stage1/*`, sector-rank tables, overlay coexistence
- **Lane C — provider adapters:** `data/krx_client.py`, `data/dart_client.py`, `data/macro_client.py`
- **Lane D — pipeline/backtest:** `pipeline/*`, `backtest/*`, `db/store.py`
- **Lane E — tests/verification:** fixtures, unit/integration/backtest coverage, final evidence pass

## 11. Verification strategy

### Unit coverage
- channel-state validation, metadata propagation, and serialization compatibility
- rank-table scoring, neutral handling, and tie-break logic
- provider normalization and filter rules
- watermark persistence and fallback metadata
- contract serialization / schema bootstrap

### Integration coverage
- scheduled and manual production runs
- DART incremental ingestion and stale fallback behavior
- Korea/US macro release-aware ingestion and last-known fallback behavior
- immutable publication and duplicate-window recovery

### Backtest coverage
- no look-ahead leakage
- DART correction/amendment non-leakage
- replay reproducibility from stored metadata
- isolation of replay outputs from live snapshots

### Documentation / contract checks
- `doc/strategy.md`, `doc/prd.md`, `doc/plan.md`, and `doc/open-questions.md` remain mutually consistent
- provider roster, series roster, simple channel-combination rule, rank-table scoring model, and degraded-mode rules are explicit and consistent
- no removed markdown file contains unique substantive guidance absent from the surviving docs

## 12. Exit criteria

This plan is ready for execution when:
- the final doc set is consolidated and self-sufficient
- the external data contract is explicit and unambiguous
- the Stage 1 macro-state, combination, and rank-table model are frozen
- provider adapters are scoped by explicit normalization, cursor, release, and local-authority rules
- PIT-safe replay and degraded-mode visibility are part of the core plan rather than deferred notes
- residual contract/DB cleanup is bounded supporting work
- no new public API, portfolio optimizer, or execution engine has been introduced
