from pathlib import Path
import unittest

from project_brain.generators.prd_scorer import PRDCompletenessScorer


class PRDScorerTest(unittest.TestCase):
    def test_sample_prd_scores_100(self) -> None:
        score = PRDCompletenessScorer().score_file(Path("tests/fixtures/sample_prd.md"))

        self.assertEqual(score.total, 100)
        self.assertTrue(score.can_proceed)


if __name__ == "__main__":
    unittest.main()

