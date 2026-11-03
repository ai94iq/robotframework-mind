"""Builds the desktop bundle for this platform, checks it, and packs it for a GitHub release. Run exactly:

    python packaging/build_bundle.py OUT_DIR

Steps: the build tools at pinned versions, this project, PyInstaller with packaging/app.spec, then the
bundle's own --self-check (it must exit 0 and report both themes and a working query), then the pack:
robotframework-mind-<version>-windows-x64.exe, -linux-x64.tar.gz or -macos-<arch>.dmg in OUT_DIR.
"""
import argparse
import ast
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "robotframework-mind"
TOOLS = ["pyinstaller==6.22.3", "pillow==13.0.0"]     # pinned for repeatable bundles; bump to the latest on purpose


def version():
    tree = ast.parse(open(os.path.join(ROOT, "robot_mind_app", "__init__.py"), encoding="utf-8").read())
    return next(n.value.value for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "__version__")


def pip(*args):
    subprocess.run([sys.executable, "-m", "pip", *args], check=True)


def executable():
    if sys.platform == "win32":
        return os.path.join(ROOT, "dist", f"{NAME}.exe")
    if sys.platform == "darwin":
        return os.path.join(ROOT, "dist", f"{NAME}.app", "Contents", "MacOS", NAME)
    return os.path.join(ROOT, "dist", NAME, NAME)


def self_check():
    """Runs the built bundle headless: a broken bundle fails here, not on a user's machine."""
    with tempfile.TemporaryDirectory() as work:
        report = os.path.join(work, "self-check.txt")
        code = subprocess.run([executable(), "--self-check", report],
                              env=dict(os.environ, QT_QPA_PLATFORM="offscreen")).returncode
        text = open(report, encoding="utf-8").read() if os.path.exists(report) else ""
    print(text)
    if code or "theme dark: ok" not in text or "query: 1 hit" not in text:
        raise SystemExit(f"The bundle failed its self-check (exit {code}).")


def pack(out):
    os.makedirs(out, exist_ok=True)
    stem = f"{NAME}-{version()}"
    if sys.platform == "win32":
        target = os.path.join(out, f"{stem}-windows-x64.exe")
        shutil.copy(executable(), target)
    elif sys.platform == "darwin":
        arch = "arm64" if platform.machine() == "arm64" else "x64"
        target = os.path.join(out, f"{stem}-macos-{arch}.dmg")
        subprocess.run(["hdiutil", "create", "-volname", "Robot Framework Mind", "-srcfolder",
                        os.path.join(ROOT, "dist", f"{NAME}.app"), "-ov", "-format", "UDZO", target], check=True)
    else:
        target = os.path.join(out, f"{stem}-linux-x64.tar.gz")
        with tarfile.open(target, "w:gz") as tar:
            tar.add(os.path.join(ROOT, "dist", NAME), arcname=f"{stem}-linux-x64")
    print(f"{target}: {os.path.getsize(target) / 2 ** 20:.0f} MB")
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out")
    args = parser.parse_args(argv)
    pip("install", "-q", *TOOLS)
    pip("install", "-q", f"{ROOT}[gui]")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--log-level", "WARN",
                    os.path.join(ROOT, "packaging", "app.spec")], check=True, cwd=ROOT)
    self_check()
    pack(os.path.abspath(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
