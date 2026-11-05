"""Editor choices: what is offered and the command each one stores."""
import unittest

from robot_mind_app import editors


class EditorTests(unittest.TestCase):
    def test_offers_only_what_is_installed(self):
        found = editors.available(has_url=lambda scheme: scheme == "vscode", exists=lambda path: False)
        self.assertEqual([e.label for e in found], ["VS Code", "System default app"])

    def test_installed_program_uses_its_path(self):
        found = editors.available(has_url=lambda scheme: False, exists=lambda path: "notepad++" in path.lower())
        npp = next(e for e in found if e.label == "Notepad++")
        self.assertIn("-n{line}", npp.command)
        self.assertTrue(npp.command.startswith('"'), "path is quoted, it has spaces")

    def test_label_names_the_stored_choice(self):
        self.assertEqual(editors.label_for("vscode"), "VS Code")
        self.assertEqual(editors.label_for('"C:/tools/ed.exe" {file}'), "ed.exe")

    def test_other_program_opens_the_file(self):
        self.assertEqual(editors.program_command("C:/tools/ed.exe"), '"C:/tools/ed.exe" {file}')


if __name__ == "__main__":
    unittest.main()
