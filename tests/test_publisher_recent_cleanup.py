from __future__ import annotations

import json
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

from macro_screener.config import load_config
from macro_screener.pipeline import build_demo_snapshot
from macro_screener.pipeline.publisher import publish_snapshot
from macro_screener.pipeline.runtime import bootstrap_runtime


def test_publish_snapshot_writes_human_and_machine_artifacts(tmp_path: Path) -> None:
    config = load_config(None)
    runtime = bootstrap_runtime(config, tmp_path)
    snapshot = build_demo_snapshot(run_id="publisher-cleanup-test")

    latest = publish_snapshot(
        snapshot,
        tmp_path,
        config=config,
        store=runtime.store,
    )

    latest_path = tmp_path / "data" / "snapshots" / "latest.json"
    latest_payload = json.loads(latest_path.read_text(encoding="utf-8"))
    screened_groups = json.loads(
        Path(latest["screened_stocks_by_industry_json"]).read_text(encoding="utf-8")
    )

    assert latest_path.exists()
    assert Path(latest["industry_parquet"]).exists()
    assert Path(latest["stock_parquet"]).exists()
    assert Path(latest["industry_csv"]).exists()
    assert Path(latest["screened_stock_csv"]).exists()
    assert Path(latest["screened_stocks_by_industry_json"]).exists()
    assert Path(latest["snapshot_json"]).exists()
    assert latest_payload["run_id"] == "publisher-cleanup-test"
    assert "industry_csv" in latest_payload
    assert "screened_stock_csv" in latest_payload
    assert "screened_stocks_by_industry_json" in latest_payload
    assert not pd.read_csv(latest["screened_stock_csv"]).empty
    assert screened_groups
    assert screened_groups[0]["stocks"]
