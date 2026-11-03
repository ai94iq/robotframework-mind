"""Entry point of the desktop bundles (PyInstaller): the same as python -m robot_mind_app."""
import sys

from robot_mind_app.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
