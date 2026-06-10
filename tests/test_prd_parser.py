from pathlib import Path
import unittest

from project_brain.generators.prd_parser import PRDParser


class PRDParserTest(unittest.TestCase):
    def test_parse_sample_prd(self) -> None:
        brain = PRDParser().parse_file(Path("tests/fixtures/sample_prd.md"))

        self.assertEqual(brain.meta.project_name, "Sample Porter")
        self.assertEqual(brain.meta.package_name, "com.example.sampleporter")
        self.assertEqual(len(brain.user_roles), 2)
        self.assertEqual(len(brain.screens), 2)
        self.assertEqual(brain.screens[0].viewmodel, "HomeViewModel")
        self.assertEqual(len(brain.firestore_schema.collections), 1)


if __name__ == "__main__":
    unittest.main()

