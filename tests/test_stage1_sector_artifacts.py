from __future__ import annotations

import json
from pathlib import Path

from macro_screener.data import KRXClient, build_grouped_sector_rank_table_compat_artifact
from macro_screener.stage1 import compute_stage1_result


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_stage1_final_sector_list_comes_from_macro_sector_exposure_artifact() -> None:
    exposure_path = _repo_root() / "config" / "macro_sector_exposure.v2.json"
    exposure_result = KRXClient(exposure_matrix_path=exposure_path).load_exposures_result()

    assert exposure_result.warnings == []

    stage1_result = compute_stage1_result(
        channel_states={"G": 0, "IC": 0, "FC": 0, "ED": 0, "FX": 0},
        exposures=exposure_result.rows,
        overlay_adjustments={},
    )

    payload = json.loads(exposure_path.read_text(encoding="utf-8"))
    expected_sectors = {
        sector_name
        for sector_scores in payload["sector_exposure"].values()
        for sector_name in sector_scores
    }

    assert {score.industry_name for score in stage1_result.industry_scores} == expected_sectors


def test_stage1_rank_table_compat_artifact_matches_macro_sector_exposure_sector_list() -> None:
    compat_path = _repo_root() / "config" / "stage1_sector_rank_tables.v1.json"
    compat_payload = json.loads(compat_path.read_text(encoding="utf-8"))
    expected_payload = build_grouped_sector_rank_table_compat_artifact()

    assert compat_payload["artifact_version"] == expected_payload["artifact_version"]
    assert compat_payload["artifact_status"] == expected_payload["artifact_status"]
    assert compat_payload["source_artifact_path"] == expected_payload["source_artifact_path"]
    assert compat_payload["sector_rank_tables"] == expected_payload["sector_rank_tables"]
