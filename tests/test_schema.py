import json
import tempfile
from pathlib import Path
import unittest

from project_brain.brain.manager import BrainManager
from project_brain.generators.prd_parser import PRDParser


class SchemaTest(unittest.TestCase):
    def test_brain_round_trip(self) -> None:
        brain = PRDParser().parse_file(Path("tests/fixtures/sample_prd.md"))
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "PROJECT_BRAIN.json"
            BrainManager(path).save(brain)
            loaded = BrainManager(path).load()

        self.assertEqual(loaded.meta.project_name, "Sample Porter")
        self.assertEqual(json.loads(loaded.model_dump_json(by_alias=True))["meta"]["entry_point"], "prd")


if __name__ == "__main__":
    unittest.main()

