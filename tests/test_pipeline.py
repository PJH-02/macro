from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from macro_screener.mvp import (
    DEFAULT_DEMO_RUN_ID,
    build_backtest_stub_plan,
    run_backtest_stub,
    run_demo,
    run_scheduled_stub,
)


class PipelinePublicationTests(unittest.TestCase):
    def test_demo_run_publishes_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_demo(tmpdir)
            latest = result["latest"]
            latest_path = Path(tmpdir) / "data" / "snapshots" / "latest.json"
            snapshot_path = Path(latest["snapshot_json"])
            stock_parquet = Path(latest["stock_parquet"])
            industry_parquet = Path(latest["industry_parquet"])
            database_path = Path(tmpdir) / "data" / "snapshots" / "mvp.sqlite"

            self.assertTrue(latest_path.exists())
            self.assertTrue(snapshot_path.exists())
            self.assertTrue(stock_parquet.exists())
            self.assertTrue(industry_parquet.exists())
            self.assertTrue(database_path.exists())

            latest_payload = json.loads(latest_path.read_text(encoding="utf-8"))
            snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(latest_payload["run_id"], DEFAULT_DEMO_RUN_ID)
            self.assertEqual(snapshot_payload["status"], "published")
            self.assertEqual(pd.read_parquet(stock_parquet).iloc[0]["rank"], 1)
            self.assertEqual(pd.read_parquet(industry_parquet).iloc[0]["rank"], 1)

            connection = sqlite3.connect(database_path)
            try:
                rows = connection.execute("SELECT run_id, status FROM snapshots").fetchall()
            finally:
                connection.close()
            self.assertEqual(rows, [(DEFAULT_DEMO_RUN_ID, "published")])

    def test_publish_is_immutable_for_duplicate_run_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_demo(tmpdir, run_id="duplicate-run")
            with self.assertRaisesRegex(FileExistsError, "duplicate-run"):
                run_demo(tmpdir, run_id="duplicate-run")

    def test_scheduled_stub_uses_documented_window_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_scheduled_stub(tmpdir, trading_date="2026-03-23", run_type="pre_open")

            self.assertEqual(result["context"]["run_id"], "2026-03-23-pre_open")
            self.assertEqual(result["context"]["as_of_timestamp"], "2026-03-23T08:30:00+09:00")
            self.assertEqual(result["context"]["input_cutoff"], "2026-03-20T18:00:00+09:00")
            self.assertEqual(result["snapshot"]["run_type"], "pre_open")

    def test_backtest_stub_skips_weekends_and_uses_isolated_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = build_backtest_stub_plan(start_date="2026-03-20", end_date="2026-03-23")
            result = run_backtest_stub(tmpdir, start_date="2026-03-20", end_date="2026-03-23")

            self.assertEqual([item["trading_date"] for item in plan], ["2026-03-20", "2026-03-23"])
            self.assertEqual(result["trading_dates"], ["2026-03-20", "2026-03-23"])
            self.assertEqual(
                [run["run_id"] for run in result["runs"]],
                ["2026-03-20-post_close", "2026-03-23-post_close"],
            )
            self.assertTrue(
                result["output_dir"].endswith("backtest/2026-03-20_2026-03-23_post_close")
            )

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
                    "cli-demo-run",
                ],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["snapshot"]["run_id"], "cli-demo-run")
            self.assertTrue((Path(tmpdir) / "data" / "snapshots" / "latest.json").exists())

    def test_cli_backtest_stub_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            completed = subprocess.run(
                [
                    "python3",
                    "-m",
                    "macro_screener.cli",
                    "backtest-stub",
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


if __name__ == "__main__":
    unittest.main()
