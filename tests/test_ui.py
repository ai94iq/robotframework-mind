"""UI invariants: theme tokens, contrast, and the offscreen self-check."""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


class ThemeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_both_themes_have_the_same_tokens(self):
        from robot_mind_app.theme import THEMES
        self.assertEqual(set(THEMES["light"]), set(THEMES["dark"]))

    def test_text_has_enough_contrast(self):
        from robot_mind_app.theme import THEMES, contrast
        for name, t in THEMES.items():
            with self.subTest(theme=name):
                self.assertGreaterEqual(contrast(t["ink"], t["panel"]), 7)


class SelfCheckTest(unittest.TestCase):
    def test_self_check_writes_a_sound_report(self):
        from robot_mind_app.__main__ import main
        report = os.path.join(tempfile.mkdtemp(), "r.txt")
        self.assertEqual(main(["--self-check", report]), 0)
        with open(report, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("theme dark: ok", text)
        self.assertNotIn("error", text)


if __name__ == "__main__":
    unittest.main()
