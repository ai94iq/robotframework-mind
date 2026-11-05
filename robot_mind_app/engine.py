"""Adapter from the desktop UI to the robot_mind query facade."""
from pathlib import Path

from robot_mind import Entry, Hit, default_cache, find_repos, in_scope, load_index, lookup, to_hits
from robot_mind_app import graph as _graph


def _entries(root, cache_dir, scope) -> list[Entry]:
    return in_scope(load_index(Path(root), cache_dir or default_cache()), scope)


def query(root, command: str, term: str, cache_dir=None, scope=None) -> list[Hit]:
    """Hits for one lookup; scope limits it to some folders (posix, relative to root), None means all."""
    return to_hits(lookup(_entries(root, cache_dir, scope), command, term))


def graph(root, command: str, term: str, cache_dir=None, scope=None) -> _graph.Graph:
    entries = _entries(root, cache_dir, scope)
    matches = [entry for entry, _line in lookup(entries, command, term)]
    return _graph.focus(entries, matches)


def repos(root) -> list[str]:
    return find_repos(Path(root))
