"""Which editors Open can use on this machine, found without running anything, and the command each stores."""
import os
import sys
from dataclasses import dataclass
from pathlib import PurePath

URL_EDITORS = {"vscode": "VS Code", "cursor": "Cursor"}         # open through scheme://file/path:line
DEFAULT_APP = "default"                                        # the system's app for .robot files, no line jump
PROGRAMS = (                                                   # (label, install path, arguments)
    ("Notepad++", "{pf}/Notepad++/notepad++.exe", "-n{line} {file}"),
    ("Sublime Text", "{pf}/Sublime Text/sublime_text.exe", "{file}:{line}"),
)


@dataclass(frozen=True, slots=True)
class Editor:
    label: str
    command: str           # a URL_EDITORS key, DEFAULT_APP, or a program with {file} and {line}


def has_url_handler(scheme: str) -> bool:
    """Whether the OS opens scheme:// links: the registry on Windows; assumed elsewhere (VS Code registers it)."""
    if sys.platform != "win32":
        return scheme == "vscode"
    import winreg
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{scheme}\shell\open\command"))
        return True
    except OSError:
        return False


def _program_files() -> list[str]:
    return [os.environ[name].replace("\\", "/") for name in ("ProgramFiles", "ProgramFiles(x86)") if name in os.environ]


def available(has_url=has_url_handler, exists=os.path.exists) -> list[Editor]:
    found = [Editor(label, key) for key, label in URL_EDITORS.items() if has_url(key)]
    for label, template, args in PROGRAMS:
        path = next((p for p in (template.format(pf=pf) for pf in _program_files() or ["C:/Program Files"])
                     if exists(p)), None)
        if path:
            found.append(Editor(label, f'"{path}" {args}'))
    return found + [Editor("System default app", DEFAULT_APP)]


def program_command(path: str) -> str:
    """The command for a program picked by hand: it gets the file, there is no common way to pass a line."""
    return f'"{path}" {{file}}'


def label_for(command: str) -> str:
    if command in URL_EDITORS:
        return URL_EDITORS[command]
    if command == DEFAULT_APP:
        return "System default app"
    program = command.split('"')[1] if command.startswith('"') else command.split()[0]
    known = {PurePath(t).name.lower(): label for label, t, _ in PROGRAMS}
    return known.get(PurePath(program).name.lower(), PurePath(program).name)
