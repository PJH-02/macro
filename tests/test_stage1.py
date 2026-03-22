from __future__ import annotations

import unittest

from macro_screener.models import RunType
from macro_screener.mvp import compute_stage1_result
from macro_screener.stage1.base_score import rank_to_score


class Stage1RankingTests(unittest.TestCase):
    def test_rank_to_score_maps_edges_and_middle_band(self) -> None:
        self.assertEqual(rank_to_score(1, 5), 1.0)
        self.assertEqual(rank_to_score(2, 5), 0.5)
        self.assertEqual(rank_to_score(3, 5), 0.0)
        self.assertEqual(rank_to_score(4, 5), -0.5)
        self.assertEqual(rank_to_score(5, 5), -1.0)
        self.assertEqual(rank_to_score(2, 4), 0.0)
        self.assertEqual(rank_to_score(3, 4), 0.0)

    def test_stage1_uses_documented_tie_breakers(self) -> None:
        channel_states = {"G": 1, "IC": 1, "FC": 0, "ED": 0, "FX": 0}
        exposures = [
            {
                "industry_code": "A",
                "industry_name": "Alpha",
                "exposures": {"G": 1, "IC": -1, "FC": 0, "ED": 0, "FX": 0},
            },
            {
                "industry_code": "B",
                "industry_name": "Bravo",
                "exposures": {"G": 1, "IC": 0, "FC": 0, "ED": 0, "FX": 0},
            },
            {
                "industry_code": "C",
                "industry_name": "Charlie",
                "exposures": {"G": 1, "IC": 0, "FC": 0, "ED": 0, "FX": 0},
            },
        ]

        result = compute_stage1_result(channel_states=channel_states, exposures=exposures)

        self.assertEqual([score.industry_code for score in result.industry_scores], ["B", "C", "A"])
        self.assertEqual([score.rank for score in result.industry_scores], [1, 2, 3])
        self.assertEqual(result.industry_scores[0].negative_penalty, 0.0)
        self.assertEqual(result.industry_scores[2].negative_penalty, 1.0)
        self.assertEqual(result.channel_states[0].channel, "G")
        self.assertEqual(result.run_type, RunType.MANUAL)

    def test_missing_channel_states_raise_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing channel states"):
            compute_stage1_result(
                channel_states={"G": 1},
                exposures=[
                    {
                        "industry_code": "A",
                        "industry_name": "Alpha",
                        "exposures": {"G": 1},
                    }
                ],
            )

    def test_stage1_uses_rank_table_prior_scoring_when_provided(self) -> None:
        channel_states = {"G": 1, "IC": -1, "FC": 0, "ED": 0, "FX": 0}
        exposures = [
            {"industry_code": "A", "industry_name": "Alpha", "exposures": {}},
            {"industry_code": "B", "industry_name": "Bravo", "exposures": {}},
            {"industry_code": "C", "industry_name": "Charlie", "exposures": {}},
        ]
        sector_rank_tables = {
            "G": {"pos": ["B", "C", "A"], "neg": ["A", "C", "B"]},
            "IC": {"pos": ["A", "B", "C"], "neg": ["C", "A", "B"]},
            "FC": {"pos": ["A", "B", "C"], "neg": ["C", "B", "A"]},
            "ED": {"pos": ["A", "B", "C"], "neg": ["C", "B", "A"]},
            "FX": {"pos": ["A", "B", "C"], "neg": ["C", "B", "A"]},
        }

        result = compute_stage1_result(
            channel_states=channel_states,
            exposures=exposures,
            sector_rank_tables=sector_rank_tables,
            channel_weights={"G": 1.0, "IC": 1.0, "FC": 1.0, "ED": 1.0, "FX": 1.0},
        )

        self.assertEqual([score.industry_code for score in result.industry_scores], ["C", "B", "A"])
        self.assertEqual(result.industry_scores[0].base_score, 1.0)
        self.assertEqual(result.industry_scores[0].channel_contributions["G"], 0.0)
        self.assertEqual(result.industry_scores[0].channel_contributions["IC"], 1.0)
        self.assertEqual(result.industry_scores[1].channel_contributions["G"], 1.0)
        self.assertEqual(result.industry_scores[1].channel_contributions["IC"], -1.0)
        self.assertEqual(result.industry_scores[1].base_score, 0.0)

    def test_rank_table_scoring_requires_industry_presence(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing from G/pos rank table"):
            compute_stage1_result(
                channel_states={"G": 1, "IC": 0, "FC": 0, "ED": 0, "FX": 0},
                exposures=[{"industry_code": "A", "industry_name": "Alpha", "exposures": {}}],
                sector_rank_tables={
                    "G": {"pos": ["B"], "neg": ["B"]},
                    "IC": {"pos": ["A"], "neg": ["A"]},
                    "FC": {"pos": ["A"], "neg": ["A"]},
                    "ED": {"pos": ["A"], "neg": ["A"]},
                    "FX": {"pos": ["A"], "neg": ["A"]},
                },
                channel_weights={"G": 1.0, "IC": 1.0, "FC": 1.0, "ED": 1.0, "FX": 1.0},
            )


if __name__ == "__main__":
    unittest.main()
