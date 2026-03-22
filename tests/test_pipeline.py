from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd  # type: ignore[import-untyped]

from macro_screener.config import load_config
from macro_screener.data.dart_client import DARTClient, DARTLoadResult
from macro_screener.data.macro_client import ManualMacroDataSource
from macro_screener.models import ChannelState
from macro_screener.mvp import (
    DEFAULT_DEMO_RUN_ID,
    build_backtest_plan,
    run_backtest_stub,
    run_demo,
    run_manual,
    run_scheduled_stub,
)
from macro_screener.pipeline.runtime import bootstrap_runtime


def _stub_live_dart_load_disclosures(
    _client: DARTClient,
    *,
    input_cutoff: str,
    retries: int,
    store: object | None = None,
    cache_path: Path | None = None,
    allow_stale: bool = True,
) -> DARTLoadResult:
    del _client, retries, store, cache_path, allow_stale
    return DARTLoadResult(
        disclosures=DARTClient(use_demo_fallback=True).load_demo_disclosures(),
        warnings=[],
        watermark=input_cutoff,
        source="live",
    )


def _write_runtime_override(
    directory: str | Path,
    *,
    allow_local_file_inputs_in_live_mode: bool,
) -> Path:
    config_path = Path(directory) / "runtime-override.yaml"
    config_path.write_text(
        (
            "runtime:\n"
            f"  allow_local_file_inputs_in_live_mode: "
            f"{str(allow_local_file_inputs_in_live_mode).lower()}\n"
        ),
        encoding="utf-8",
    )
    return config_path


class PipelinePublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        patcher = patch(
            "macro_screener.pipeline.runner.DARTClient.load_disclosures",
            new=_stub_live_dart_load_disclosures,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_manual_run_publishes_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_manual(tmpdir, run_id="manual-test-run")
            latest = result["latest"]
            latest_path = Path(tmpdir) / "data" / "snapshots" / "latest.json"
            snapshot_path = Path(latest["snapshot_json"])
            stock_parquet = Path(latest["stock_parquet"])
            industry_parquet = Path(latest["industry_parquet"])
            database_path = Path(tmpdir) / "data" / "macro_screener.sqlite3"

            self.assertTrue(latest_path.exists())
            self.assertTrue(snapshot_path.exists())
            self.assertTrue(stock_parquet.exists())
            self.assertTrue(industry_parquet.exists())
            self.assertTrue(database_path.exists())

            latest_payload = json.loads(latest_path.read_text(encoding="utf-8"))
            snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(latest_payload["run_id"], "manual-test-run")
            self.assertEqual(snapshot_payload["status"], "published")
            stock_rows = pd.read_parquet(stock_parquet)
            self.assertFalse(stock_rows.empty)
            self.assertEqual(stock_rows.iloc[0]["rank"], 1)
            self.assertEqual(pd.read_parquet(industry_parquet).iloc[0]["rank"], 1)

            connection = sqlite3.connect(database_path)
            try:
                rows = connection.execute("SELECT run_id, status FROM snapshots").fetchall()
            finally:
                connection.close()
            self.assertEqual(rows, [("manual-test-run", "published")])

    def test_manual_run_does_not_fallback_to_demo_stocks_when_artifact_codes_match(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_manual(tmpdir, run_id="artifact-stock-join-run")
            self.assertNotIn("stock_universe_unmapped_using_demo_stocks", result["warnings"])
            self.assertNotIn(
                "stage2_unmapped_stock_universe_publishing_stage1_only",
                result["warnings"],
            )
            self.assertTrue(result["snapshot"]["stock_scores"])

    def test_manual_run_uses_materialized_stage1_artifact_universe(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_manual(tmpdir, run_id="artifact-universe-run")
            industry_parquet = Path(result["latest"]["industry_parquet"])
            industry_scores = pd.read_parquet(industry_parquet)
            industry_master_rows = pd.read_csv(
                Path("data/reference/industry_master.csv"),
                dtype=str,
            ).fillna("")

            self.assertEqual(len(industry_scores), len(industry_master_rows))
            self.assertGreater(len(industry_scores), 3)

    def test_manual_run_persists_fallback_channel_state_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_config(None)
            registry = bootstrap_runtime(config, Path(tmpdir)).store
            registry.save_channel_states(
                run_id="seed-run",
                channel_states=[
                    ChannelState(
                        channel="G",
                        state=1,
                        effective_at=datetime.fromisoformat("2026-03-21T08:30:00+09:00"),
                    ),
                    ChannelState(
                        channel="IC",
                        state=0,
                        effective_at=datetime.fromisoformat("2026-03-21T08:30:00+09:00"),
                    ),
                    ChannelState(
                        channel="FC",
                        state=0,
                        effective_at=datetime.fromisoformat("2026-03-21T08:30:00+09:00"),
                    ),
                    ChannelState(
                        channel="ED",
                        state=1,
                        effective_at=datetime.fromisoformat("2026-03-21T08:30:00+09:00"),
                    ),
                    ChannelState(
                        channel="FX",
                        state=0,
                        effective_at=datetime.fromisoformat("2026-03-21T08:30:00+09:00"),
                    ),
                ],
                source="last_known",
                metadata={
                    "source_name": "last_known",
                    "source_version": "mvp-1",
                    "fallback_mode": "last_known_channel_states",
                    "as_of_timestamp": "2026-03-21T08:30:00+09:00",
                    "input_cutoff": "2026-03-21T08:25:00+09:00",
                    "warning_flags": ["macro_source_unavailable_using_last_known_channel_states"],
                    "confidence_by_channel": {"G": 0.7, "ED": 0.6},
                },
            )

            original_fetch = ManualMacroDataSource.fetch_channel_states

            def _raising_fetch(self: ManualMacroDataSource) -> object:
                if self.source_name == "manual_config":
                    raise ValueError("force persisted fallback")
                return original_fetch(self)

            with patch.object(ManualMacroDataSource, "fetch_channel_states", _raising_fetch):
                run_manual(tmpdir, run_id="persisted-fallback-run")

            snapshot = registry.load_last_channel_state_snapshot()
            assert snapshot is not None
            metadata = snapshot["metadata"]
            self.assertEqual(metadata["source_name"], "last_known")
            self.assertEqual(metadata["source_version"], "mvp-1")
            self.assertEqual(metadata["fallback_mode"], "last_known_channel_states")
            self.assertEqual(metadata["input_cutoff"], "2026-03-21T08:25:00+09:00")
            self.assertEqual(metadata["confidence_by_channel"]["G"], 0.7)
            self.assertIn(
                "macro_source_unavailable_using_last_known_channel_states",
                metadata["warning_flags"],
            )

    def test_publish_is_immutable_for_duplicate_run_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_demo(tmpdir, run_id="duplicate-run")
            with self.assertRaisesRegex(FileExistsError, "duplicate-run"):
                run_demo(tmpdir, run_id="duplicate-run")

    def test_scheduled_run_uses_window_defaults_and_attempt_unique_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_scheduled_stub(
                tmpdir,
                trading_date="2026-03-23",
                run_type="pre_open",
                attempted_at="2026-03-23T08:29:00+09:00",
            )

            self.assertTrue(result["context"]["run_id"].startswith("2026-03-23-pre_open-"))
            self.assertEqual(result["context"]["as_of_timestamp"], "2026-03-23T08:30:00+09:00")
            self.assertEqual(result["context"]["input_cutoff"], "2026-03-20T18:00:00+09:00")
            self.assertEqual(result["scheduled_window_key"]["trading_date"], "2026-03-23")
            self.assertEqual(result["scheduled_window_key"]["run_type"], "pre_open")
            self.assertEqual(result["snapshot"]["run_type"], "pre_open")

    def test_scheduled_duplicate_window_is_skipped_after_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            first = run_scheduled_stub(
                tmpdir,
                trading_date="2026-03-23",
                run_type="post_close",
                attempted_at="2026-03-23T15:46:00+09:00",
            )
            second = run_scheduled_stub(
                tmpdir,
                trading_date="2026-03-23",
                run_type="post_close",
                attempted_at="2026-03-23T15:47:00+09:00",
            )
            database_path = Path(tmpdir) / "data" / "macro_screener.sqlite3"

            self.assertEqual(first["snapshot"]["status"], "published")
            self.assertEqual(second["snapshot"]["status"], "duplicate")
            self.assertIn("duplicate_scheduled_window_skipped", second["warnings"])

            connection = sqlite3.connect(database_path)
            try:
                count = connection.execute("SELECT COUNT(*) FROM published_snapshots").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(count, 1)

    def test_scheduled_duplicate_window_keeps_existing_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            latest_path = Path(tmpdir) / "data" / "snapshots" / "latest.json"
            first = run_scheduled_stub(
                tmpdir,
                trading_date="2026-03-23",
                run_type="post_close",
                attempted_at="2026-03-23T15:46:00+09:00",
            )
            first_latest = json.loads(latest_path.read_text(encoding="utf-8"))

            second = run_scheduled_stub(
                tmpdir,
                trading_date="2026-03-23",
                run_type="post_close",
                attempted_at="2026-03-23T15:47:00+09:00",
            )
            second_latest = json.loads(latest_path.read_text(encoding="utf-8"))

            self.assertEqual(first["snapshot"]["status"], "published")
            self.assertEqual(second["snapshot"]["status"], "duplicate")
            self.assertEqual(second_latest, first_latest)
            self.assertEqual(second_latest["run_id"], first["snapshot"]["run_id"])

    def test_stage2_failure_publishes_incomplete_stage1_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            latest_path = Path(tmpdir) / "data" / "snapshots" / "latest.json"

            with patch(
                "macro_screener.pipeline.runner.compute_stock_scores",
                side_effect=RuntimeError("stage2 boom"),
            ):
                result = run_manual(tmpdir, run_id="stage1-only-run")

            latest_payload = json.loads(latest_path.read_text(encoding="utf-8"))
            snapshot_path = Path(latest_payload["snapshot_json"])
            snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
            stock_scores = pd.read_parquet(Path(latest_payload["stock_parquet"]))

            self.assertEqual(result["snapshot"]["status"], "incomplete")
            self.assertEqual(latest_payload["status"], "incomplete")
            self.assertEqual(snapshot_payload["status"], "incomplete")
            self.assertTrue(stock_scores.empty)
            self.assertTrue(snapshot_payload["industry_scores"])
            self.assertIn(
                "stage2_failed_publishing_stage1_only: stage2 boom",
                result["warnings"],
            )

    def test_backtest_run_skips_weekends_and_uses_isolated_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = build_backtest_plan(start_date="2026-03-20", end_date="2026-03-23")
            result = run_backtest_stub(tmpdir, start_date="2026-03-20", end_date="2026-03-23")

            self.assertEqual([item["trading_date"] for item in plan], ["2026-03-20", "2026-03-23"])
            self.assertEqual(result["trading_dates"], ["2026-03-20", "2026-03-23"])
            self.assertTrue(all(run["run_id"].startswith("backtest-") for run in result["runs"]))
            self.assertTrue(
                result["output_dir"].endswith("backtest/2026-03-20_2026-03-23_post_close")
            )
            self.assertTrue(
                (Path(result["output_dir"]) / "data" / "snapshots" / "latest.json").exists()
            )

    def test_backtest_pre_open_uses_previous_trading_day_cutoff(self) -> None:
        plan = build_backtest_plan(
            start_date="2026-03-23",
            end_date="2026-03-23",
            run_type="pre_open",
        )

        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["as_of_timestamp"], "2026-03-23T08:30:00+09:00")
        self.assertEqual(plan[0]["input_cutoff"], "2026-03-20T18:00:00+09:00")

    def test_backtest_batch_id_makes_run_ids_reproducible(self) -> None:
        plan = build_backtest_plan(
            start_date="2026-03-20",
            end_date="2026-03-23",
            batch_id="replay-batch",
        )

        self.assertEqual(
            [item["run_id"] for item in plan],
            [
                "replay-batch-2026-03-20-post_close",
                "replay-batch-2026-03-23-post_close",
            ],
        )

    def test_cli_manual_run_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = _write_runtime_override(
                tmpdir,
                allow_local_file_inputs_in_live_mode=True,
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            completed = subprocess.run(
                [
                    "python3",
                    "-m",
                    "macro_screener.cli",
                    "manual-run",
                    "--output-dir",
                    tmpdir,
                    "--config",
                    str(config_path),
                    "--run-id",
                    "cli-manual-run",
                    "--channel-state",
                    "G=1",
                    "--channel-state",
                    "ED=1",
                ],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["snapshot"]["run_id"], "cli-manual-run")
            self.assertTrue((Path(tmpdir) / "data" / "snapshots" / "latest.json").exists())

    def test_cli_demo_run_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            completed = subprocess.run(
                [
                    "python3",
                    "-m",
                    "macro_screener.cli",
                    "demo-run",
                    "--output-dir",
                    tmpdir,
                    "--run-id",
                    DEFAULT_DEMO_RUN_ID,
                ],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["snapshot"]["run_id"], DEFAULT_DEMO_RUN_ID)
            self.assertTrue((Path(tmpdir) / "data" / "snapshots" / "latest.json").exists())

    def test_cli_backtest_run_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            completed = subprocess.run(
                [
                    "python3",
                    "-m",
                    "macro_screener.cli",
                    "backtest-run",
                    "--output-dir",
                    tmpdir,
                    "--start-date",
                    "2026-03-20",
                    "--end-date",
                    "2026-03-23",
                ],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["trading_dates"], ["2026-03-20", "2026-03-23"])
            self.assertTrue(
                (Path(payload["output_dir"]) / "data" / "snapshots" / "latest.json").exists()
            )


class DartRuntimePolicyTests(unittest.TestCase):
    def test_manual_run_requires_live_dart_input_when_unconfigured(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"DART_API_KEY": ""}, clear=False):
                with self.assertRaisesRegex(RuntimeError, "DART_API_KEY"):
                    run_manual(tmpdir, run_id="missing-dart-live-run")

    def test_manual_run_marks_stale_dart_cache_as_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "data" / "cache" / "dart" / "latest.json"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps(
                    {
                        "source": "stale_cache",
                        "watermark": "2026-03-21T18:00:00+09:00",
                        "disclosures": [
                            {
                                "stock_code": "005930",
                                "event_code": "B01",
                                "title": "대규모 공급계약 체결",
                                "trading_days_elapsed": 1,
                                "accepted_at": "2026-03-20T18:00:00+09:00",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            class _FailingClient:
                def __init__(self, *args: object, **kwargs: object) -> None:
                    del args, kwargs

                def __enter__(self) -> "_FailingClient":
                    return self

                def __exit__(
                    self,
                    exc_type: object,
                    exc: object,
                    tb: object,
                ) -> bool:
                    del exc_type, exc, tb
                    return False

                def get(self, *args: object, **kwargs: object) -> object:
                    del args, kwargs
                    raise RuntimeError("simulated dart outage")

            with patch.dict(os.environ, {"DART_API_KEY": "test-key"}, clear=False):
                with patch("macro_screener.data.dart_client.httpx.Client", _FailingClient):
                    result = run_manual(tmpdir, run_id="stale-dart-cache-run")

            latest_path = Path(tmpdir) / "data" / "snapshots" / "latest.json"
            latest_payload = json.loads(latest_path.read_text(encoding="utf-8"))

            self.assertEqual(result["snapshot"]["status"], "incomplete")
            self.assertEqual(latest_payload["status"], "incomplete")
            self.assertIn("dart_source_degraded_stale_cache", result["warnings"])
            self.assertTrue(
                any(
                    warning.startswith("dart_api_failed_using_stale_cache:")
                    for warning in result["warnings"]
                )
            )


if __name__ == "__main__":
    unittest.main()
