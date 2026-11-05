"""Persistent app state in QSettings: saved repos, query history, and the editor command."""
import shlex
from pathlib import PurePath
from urllib.parse import quote

from PySide6.QtCore import QSettings

VSCODE = "vscode"                      # open through VS Code's vscode:// link: no console, no shell
DEFAULT_EDITOR = VSCODE
SCRIPT_SUFFIXES = {".cmd", ".bat"}     # Windows runs these through cmd.exe, which re-reads the file name
MAX_REPOS = 20
MAX_HISTORY = 30


class AppSettings:
    def __init__(self, settings: QSettings):
        self.s = settings

    # ---------------------------------------------------------------- saved repos
    def repos(self) -> list[str]:
        value = self.s.value("repos", []) or []
        return [str(r) for r in value] if isinstance(value, (list, tuple)) else [str(value)]

    def add_repo(self, path: str):
        repos = [r for r in self.repos() if r != path]
        repos.insert(0, path)
        self.s.setValue("repos", repos[:MAX_REPOS])

    # ---------------------------------------------------------------- query history
    def history(self) -> list[tuple[str, str]]:
        value = self.s.value("history", []) or []
        if isinstance(value, str):
            value = [value]
        out = []
        for item in value:
            text = str(item)
            if "\t" in text:
                command, term = text.split("\t", 1)
                out.append((command, term))
        return out

    def add_history(self, command: str, term: str):
        items = [h for h in self.history() if h != (command, term)]
        items.insert(0, (command, term))
        self.s.setValue("history", [f"{c}\t{t}" for c, t in items[:MAX_HISTORY]])

    # ---------------------------------------------------------------- editor
    def editor_command(self) -> str:
        value = str(self.s.value("editor", DEFAULT_EDITOR) or "").strip()
        return value or DEFAULT_EDITOR

    def set_editor_command(self, command: str):
        self.s.setValue("editor", command)


def _unquote(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    return token


def _file_arg(file: str) -> str:
    """Prefix a name starting with '-' so it is not read as an option (S2)."""
    return "./" + file if file.startswith("-") else file


def editor_url(root: str, file: str, line: int, scheme: str = VSCODE) -> str:
    """The scheme://file link (vscode, cursor) that opens root/file at line."""
    path = PurePath(root, file).as_posix()
    return f"{scheme}://file/{quote(path, safe='/:')}:{line}"


def check_program(path: str) -> str:
    """The program itself, or ValueError for a .cmd or .bat launcher (it would open a console and pass the
    file name through cmd.exe)."""
    if PurePath(path).suffix.lower() in SCRIPT_SUFFIXES:
        raise ValueError(f"{PurePath(path).name} is a script; point the editor at its .exe instead")
    return path


def open_in_editor(file: str, line: int, command: str = DEFAULT_EDITOR) -> list[str]:
    """The argv that opens `file` at `line`; the caller runs it (no shell, so spaces in a path are safe)."""
    parts = [_unquote(part) for part in shlex.split(command, posix=False)]
    return [part.replace("{file}", _file_arg(file)).replace("{line}", str(line)) for part in parts]
