"""maintain skill: CLAUDE.md yer tutucu deseni sablondaki yer tutuculari yakalar, meşru <kind>/<title> kullanimini yakalamaz."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def skill_pattern():
    text = (ROOT / "src/skills/maintain/SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"pattern `([^`]+)`", text)
    assert m, "SKILL.md icinde 'pattern `...`' bulunamadi"
    return re.compile(m.group(1))


class MaintainPlaceholderPattern(unittest.TestCase):
    def test_catches_every_placeholder_kind_in_the_template(self):
        pat = skill_pattern()
        for token in ["<Project name>", "<One paragraph: what this is>", "<cmd>", "<dir>/", "<role>",
                      "<Naming, error handling>", "<Add real mistakes>"]:
            self.assertTrue(pat.search(token), token)

    def test_flags_the_unfilled_template(self):
        template = (ROOT / "src/templates/project/CLAUDE.md").read_text(encoding="utf-8")
        self.assertTrue(skill_pattern().search(template))

    def test_does_not_flag_legit_angle_brackets(self):
        line = 'Create docs with `python3 tools/docs.py new <kind> "<title>"`, never by hand.'
        self.assertIsNone(skill_pattern().search(line))


if __name__ == "__main__":
    unittest.main()
