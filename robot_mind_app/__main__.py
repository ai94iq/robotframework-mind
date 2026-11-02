"""Starts Robot Framework Mind.

    python -m robot_mind_app                       open the window
    python -m robot_mind_app --theme dark          start in a theme (system, light, dark) without saving it
    python -m robot_mind_app --self-check REPORT   build the window offscreen, write a report, exit 0 when sound
    python -m robot_mind_app --screenshots DIR     light and dark screenshots plus review.html, for a visual review
"""
import argparse
import html
import os
import sys


def parse(argv):
    parser = argparse.ArgumentParser(prog="robot_mind_app", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--theme", choices=("system", "light", "dark"))
    parser.add_argument("--self-check", metavar="REPORT")
    parser.add_argument("--screenshots", metavar="DIR")
    return parser.parse_args(argv)


def self_check(report):
    """What a packaged bundle must prove without a display: Qt, SVG icons and the window load in both themes."""
    from PySide6.QtCore import QSettings
    from . import __version__
    from .window import MainWindow
    lines, ok = [f"version: {__version__}"], True
    try:
        window = MainWindow(settings=QSettings(os.path.join(os.path.dirname(os.path.abspath(report)),
                                                            "self-check.ini"), QSettings.Format.IniFormat))
        for mode in ("light", "dark"):
            window.set_theme(mode)
            lines.append(f"theme {mode}: ok")
        lines.append(f"icon sizes: {sorted(s.width() for s in window.windowIcon().availableSizes())}")
    except Exception as err:          # the report says why; the exit code says that it failed
        lines.append(f"error: {type(err).__name__}: {err}")
        ok = False
    with open(report, "w", encoding="utf-8") as out:
        out.write("\n".join(lines) + "\n")
    return 0 if ok else 1


def screenshots(folder):
    """Grabs the window in light and dark into one HTML page, so a review sees both themes side by side."""
    from PySide6.QtCore import QSettings
    from .window import MainWindow
    os.makedirs(folder, exist_ok=True)
    window = MainWindow(settings=QSettings(os.path.join(folder, "screens.ini"), QSettings.Format.IniFormat))
    window.show()
    shots = []
    for mode in ("light", "dark"):
        window.set_theme(mode)
        window.repaint()
        name = f"{mode}.png"
        window.grab().save(os.path.join(folder, name))
        shots.append(f'<figure><img src="{name}" alt="{mode} theme"><figcaption>{mode}</figcaption></figure>')
    page = os.path.join(folder, "review.html")
    with open(page, "w", encoding="utf-8") as out:
        out.write("<!doctype html><meta charset=utf-8><title>%s screens</title><style>body{font:14px sans-serif;"
                  "margin:16px}img{max-width:100%%;border:1px solid #ccc}</style>%s"
                  % (html.escape("Robot Framework Mind"), "".join(shots)))
    return page


def main(argv=None):
    args = parse(sys.argv[1:] if argv is None else argv)
    if args.self_check:           # no display needed; --screenshots needs one, offscreen Qt has no fonts
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 is missing: pip install -e .[gui]", file=sys.stderr)
        return 2
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Robot Framework Mind")
    if args.self_check:
        return self_check(args.self_check)
    if args.screenshots:
        print(screenshots(args.screenshots))
        return 0
    from .window import MainWindow
    from .worker import start, stop
    window = MainWindow()
    if args.theme:
        window.set_theme(args.theme, save=False)
    thread = start(window.worker)
    window.show()
    code = app.exec()
    stop(thread)
    return code


if __name__ == "__main__":
    sys.exit(main())
