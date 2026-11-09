"""Third review of tools/dockerw.py: --mount is parsed as CSV by Docker, so validation must parse it the same way.

Only a fake docker binary is used; nothing here starts a container.
"""
import unittest

from test_dockerw_review2 import Base


class TestMountCsv(Base):
    def refused(self, spec):
        with self.assertRaises(self.mod.Refused, msg=spec):
            self.mod.scan(["--mount", spec], self.root, self.root)

    def allowed(self, spec):
        self.mod.scan(["--mount", spec], self.root, self.root)

    def test_quoted_key_value_pair(self):
        self.refused('type=bind,"source=/etc",target=/x')

    def test_quoted_pair_after_type(self):
        self.refused('type=bind,"source=/etc"')

    def test_quoted_value_only(self):
        self.refused('type=bind,source="/etc"')

    def test_quoted_type_field(self):
        self.refused('"type=bind",source=/etc')

    def test_quoted_field_with_comma_cannot_hide_source(self):
        self.refused('type=bind,source=/etc,"x=1,source=/ok"')

    def test_doubled_quote_escape(self):
        self.refused('type=bind,"source=""/etc"""')

    def test_unterminated_quote_is_rejected(self):
        self.refused('type=bind,source="/etc')

    def test_stray_quote_in_bare_field_is_rejected(self):
        self.refused('type=bind,sou"rce=/etc')

    def test_multiline_value_is_rejected(self):
        self.refused('type=bind,source=/ok\nsource=/etc')

    def test_quoted_source_inside_project_still_allowed(self):
        self.allowed(f'type=bind,"source={self.root}/data",target=/x')

    def test_plain_source_inside_project_still_allowed(self):
        self.allowed(f"type=bind,source={self.root}/data,target=/x")


if __name__ == "__main__":
    unittest.main()
