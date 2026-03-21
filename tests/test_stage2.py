from __future__ import annotations

import unittest

from macro_screener.mvp import classify_disclosure, compute_stage1_result, compute_stock_scores


class Stage2ScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stage1_result = compute_stage1_result(
            channel_states={"G": 1, "IC": 0, "FC": 0, "ED": 1, "FX": 0},
            exposures=[
                {
                    "industry_code": "AUTO",
                    "industry_name": "Automobiles",
                    "exposures": {"G": 1, "IC": 0, "FC": 0, "ED": 1, "FX": 0},
                },
                {
                    "industry_code": "PHARMA",
                    "industry_name": "Pharmaceuticals",
                    "exposures": {"G": 0, "IC": 0, "FC": 0, "ED": 0, "FX": 0},
                },
            ],
        )
        self.stocks = [
            {"stock_code": "000270", "stock_name": "Kia", "industry_code": "AUTO"},
            {"stock_code": "000100", "stock_name": "Yuhan", "industry_code": "PHARMA"},
        ]

    def test_classification_uses_code_and_title_fallbacks(self) -> None:
        self.assertEqual(classify_disclosure("B01", "ignored"), "supply_contract")
        self.assertEqual(classify_disclosure(None, "시설투자 결정"), "facility_investment")
        self.assertEqual(classify_disclosure(None, "설명회 개최"), "neutral")

    def test_stock_ranking_uses_normalized_scores_and_tie_breakers(self) -> None:
        stock_scores, warnings = compute_stock_scores(
            stage1_result=self.stage1_result,
            stocks=self.stocks,
            disclosures=[
                {
                    "stock_code": "000270",
                    "event_code": "B01",
                    "title": "공급계약 체결",
                    "trading_days_elapsed": 0,
                },
                {
                    "stock_code": "000100",
                    "event_code": None,
                    "title": "설명회 개최",
                    "trading_days_elapsed": 0,
                },
            ],
        )

        self.assertEqual(stock_scores[0].stock_code, "000270")
        self.assertGreater(
            stock_scores[0].normalized_dart_score,
            stock_scores[1].normalized_dart_score,
        )
        self.assertAlmostEqual(stock_scores[1].normalized_financial_score, 0.0)
        self.assertIn("unknown_dart_classification_ratio", warnings[0])

    def test_zero_variance_normalization_returns_zero_components(self) -> None:
        stock_scores, warnings = compute_stock_scores(
            stage1_result=self.stage1_result,
            stocks=self.stocks,
            disclosures=[],
        )

        self.assertEqual(warnings, [])
        self.assertEqual([score.normalized_dart_score for score in stock_scores], [0.0, 0.0])


if __name__ == "__main__":
    unittest.main()
