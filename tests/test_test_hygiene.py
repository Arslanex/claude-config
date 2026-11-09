import re
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ALL_SCRIPTS = sorted([*TESTS.glob("*.sh"), *TESTS.glob("live/*.sh")])


class TestHygiene(unittest.TestCase):
    def test_scripts_with_mktemp_abort_when_it_fails(self):
        for f in ALL_SCRIPTS:
            text = f.read_text()
            if "mktemp" in text:
                self.assertRegex(text, r'\[ -d "\$\w+" \].*exit 1', f.name)

    def test_scripts_that_use_git_work_in_a_temp_dir(self):
        for f in ALL_SCRIPTS:
            text = f.read_text()
            if re.search(r"(^|[;&(]\s*)git (init|commit|add)", text, re.M):
                self.assertIn("mktemp", text, f.name)


if __name__ == "__main__":
    unittest.main()
