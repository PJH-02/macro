# Why `manual-run` produced all-zero industry scores

## Conclusion

The all-zero values in `industry_scores.csv` are **not primarily a scoring-engine bug**.  
They come from the fact that the documented `manual-run` path uses the **default manual macro state configuration**, and that default is **all zeros**.

Because all five channel states are neutral (`G=0, IC=0, FC=0, ED=0, FX=0`), the stage-1 scoring path contributes `0` for every channel, for every industry. As a result:

- `base_score = 0`
- `overlay_adjustment = 0`
- `final_score = 0`

for every industry row.

---

## Evidence

### 1) The default manual channel states are all zero

In `config/default.yaml`, the `stage1.manual_channel_states` defaults are:

- `G: 0`
- `IC: 0`
- `FC: 0`
- `ED: 0`
- `FX: 0`

Evidence:

- `config/default.yaml:23-35`

This means that if `manual-run` is executed **without** explicit channel overrides and **without** a custom config that changes those values, the run starts from a fully neutral macro regime.

---

### 2) `manual-run` uses those manual defaults unless you override them

`run_manual()` passes `channel_states` through to `run_pipeline_context()`. If no overrides are provided, `_resolve_macro_states()` falls back to the configured manual channel states.

Evidence:

- `src/macro_screener/pipeline/runner.py:132-159`
- `src/macro_screener/pipeline/runner.py:705-723`

Specifically:

1. If `channel_states is not None`, overrides are merged and used.
2. If `use_demo_inputs` is `False` and production-live mode is not active, the code uses `_load_configured_or_persisted_macro_states(...)`.
3. That path resolves to `config.stage1.manual_channel_states`.

So a plain `manual-run` with no overrides uses the all-zero defaults from the config.

---

### 3) The stage-1 scoring logic turns zero channel states into zero contributions

In the rank-table scoring path, `_weighted_ranked_contributions()` skips a channel entirely when its state is `0`.

Evidence:

- `src/macro_screener/stage1/ranking.py:55-77`

Important lines:

- `state = channel_states[channel]`
- `if state == 0: continue`

When **all** channels are `0`, every channel is skipped, and the contribution map remains:

```python
{channel: 0.0 for channel in CHANNELS}
```

Then `summarize_weighted_contributions()` sums those values:

- `base_score = sum(contributions.values())`
- negative/positive totals are also zero

Evidence:

- `src/macro_screener/stage1/base_score.py:62-68`

Finally, `compute_stage1_result()` sets:

- `base_score`
- `overlay_adjustment`
- `final_score = base_score + overlay_adjustment`

Evidence:

- `src/macro_screener/stage1/ranking.py:98-140`

Because the contribution map is all zeros and there is no nonzero overlay in this path, every industry's `final_score` becomes `0.0`.

---

### 4) The README manual-run example contributes to the confusion

The README example for manual execution does **not** provide any `--channel-state` overrides.

Evidence:

- `README.md:296-302`

Documented example:

```bash
python3 -m macro_screener.cli manual-run \
  --output-dir ./out \
  --run-id manual-prod-run
```

This example implies “manual-run” should produce a meaningful scored result by itself, but in reality it uses the neutral default manual state configuration unless the user explicitly overrides it or supplies a config with nonzero manual states.

So the README usage is part of **why the user sees all zeros**, even though the immediate mechanical cause is the all-zero default configuration.

---

## Root cause summary

The zero scores are caused by **three linked conditions**:

1. **Default configuration problem**
   - Manual channel states default to all zero.

2. **Execution path behavior**
   - `manual-run` uses those defaults when the user does not pass channel overrides.

3. **Scoring logic behavior**
   - Stage-1 scoring skips channels whose state is `0`, so all-zero inputs produce all-zero output for every industry.

---

## What this is *not*

This is **not** evidence that:

- the CSV writer is broken
- the ranking engine randomly zeroed valid scores
- the export path corrupted the values after computation

The values are already zero before export because the run is being evaluated under a fully neutral manual macro state.

---

## Secondary note

This investigation focused on **why `industry_scores.csv` is all zero**.

There may be separate issues affecting stage-2 stock output in some runs, but those are **not required** to explain the all-zero industry-score file. The all-zero industry file is already fully explained by the neutral manual-state path above.
