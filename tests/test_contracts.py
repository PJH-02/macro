from __future__ import annotations

import unittest

from macro_screener.contracts import IndustryScore, Snapshot, Stage1Result, StockScore


class ContractSerializationTests(unittest.TestCase):
    def test_stage1_result_to_dict_contains_required_fields(self) -> None:
        industry = IndustryScore(
            industry_code="AUTO",
            industry_name="Automobiles",
            base_score=2.0,
            overlay_adjustment=0.2,
            final_score=2.2,
            negative_penalty=0.0,
            positive_contribution=2.0,
            rank=1,
        )
        result = Stage1Result(
            run_id="run-1",
            run_type="manual",
            as_of_timestamp="2026-03-21T08:30:00+09:00",
            channel_states={"G": 1, "IC": 0, "FC": 0, "ED": 1, "FX": 0},
            industry_scores=[industry],
            config_version="mvp-1",
            warnings=["demo-warning"],
        )

        payload = result.to_dict()

        self.assertEqual(payload["run_id"], "run-1")
        self.assertEqual(payload["run_type"], "manual")
        self.assertEqual(payload["config_version"], "mvp-1")
        self.assertEqual(payload["warnings"], ["demo-warning"])
        self.assertEqual(payload["industry_scores"][0]["industry_code"], "AUTO")

    def test_snapshot_to_dict_contains_stage_outputs(self) -> None:
        industry = IndustryScore(
            industry_code="AUTO",
            industry_name="Automobiles",
            base_score=2.0,
            overlay_adjustment=0.2,
            final_score=2.2,
            negative_penalty=0.0,
            positive_contribution=2.0,
            rank=1,
        )
        stock = StockScore(
            stock_code="000270",
            stock_name="Kia",
            industry_code="AUTO",
            final_score=1.25,
            rank=1,
            raw_dart_score=0.9,
            raw_industry_score=2.2,
            normalized_dart_score=1.0,
            normalized_industry_score=0.714286,
            normalized_financial_score=0.0,
            risk_flags=[],
            block_breakdown={"supply_contract": 0.9},
        )
        snapshot = Snapshot(
            run_id="run-1",
            run_type="manual",
            as_of_timestamp="2026-03-21T08:30:00+09:00",
            input_cutoff="2026-03-20T18:00:00+09:00",
            published_at="2026-03-21T08:30:00+09:00",
            status="published",
            industry_scores=[industry],
            stock_scores=[stock],
            warnings=[],
        )

        payload = snapshot.to_dict()

        self.assertEqual(payload["run_id"], "run-1")
        self.assertEqual(payload["status"], "published")
        self.assertEqual(payload["industry_scores"][0]["rank"], 1)
        self.assertEqual(payload["stock_scores"][0]["stock_code"], "000270")


if __name__ == "__main__":
    unittest.main()
