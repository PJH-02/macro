from __future__ import annotations

import unittest

from macro_screener.models import RunType
from macro_screener.mvp import compute_stage1_result


class Stage1RankingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
