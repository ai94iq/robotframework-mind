"""Adapter from the desktop UI to the robot_mind query facade."""
from pathlib import Path

from robot_mind import Hit, query as _query


def query(root, command: str, term: str, cache_dir=None) -> list[Hit]:
    return _query(Path(root), command, term, cache_dir=cache_dir)
