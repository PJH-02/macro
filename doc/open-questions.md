# Open Questions for Final MVP Implementation Kickoff

> Purpose: preserve only the real remaining implementation questions after the final documentation consolidation.

## 1. Questions already resolved in the final doc set

The following are **no longer open** and should not be re-opened unless a later explicit product decision changes them:
- MVP external macro scope = **Korea + US-only external macro**
- KRX security-type ambiguity is operationally resolved by the authoritative local classification CSV
- the MVP provider roster no longer includes mandatory BIS/OECD/IMF runtime adapters
- Stage 1 uses **full ordered sector-rank tables**, not coarse favored/disfavored lists
- channel combination inside each channel uses the **simple arithmetic mean** plus a channel-specific neutral band
- KRX official endpoints remain the primary market/universe source
- DART API keys come from environment/secret sources
- Korea holiday handling stays hardcoded for MVP
- normalization uses cross-sectional z-scores with lambda applied after normalization
- DART half-life defaults and the fast-overlay `5%` baseline are already fixed for the final-stage baseline
- backtest may process independent dates in parallel

## 2. Remaining open questions only

### Q1. What is the exact raw transform for each fixed series?
Examples:
- YoY
- QoQ annualized
- moving-average slope
- spread change
- level relative to threshold

This must be frozen per series for the final implementation config.

### Q2. What is the neutral band `tau_c` for each channel?
Need exact values for mapping the combined simple-average signal back into `{-1, 0, +1}`.

### Q3. Which US `ED` proxy is final?
Choose one:
- US real imports of goods YoY
- US real goods consumption YoY

### Q4. Is ALFRED required for historical backfill before live collection starts?
If yes, document vintage handling explicitly.
If no, document the historical limitation and rely on persisted release snapshots from go-live onward.

### Q5. What is the final industry taxonomy file name, schema, refresh process, and ownership?
The final docs must freeze:
- file path
- required columns
- refresh process
- ownership

## 3. Exit condition for this file

This file should shrink to zero open questions before full production implementation begins.
