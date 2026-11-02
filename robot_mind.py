"""robotframework-mind: exact lookups over a Robot Framework test repo, for people and scripts.

Indexes tests (tags, docs, calls), user keywords (args, first doc line, calls),
variables (values), suite/test fixtures and the JSON files under docs/, then
answers short questions with one line per hit and its file:line.

Usage: python robot_mind.py [--root DIR] <ticket|kw|callers|tag|find> TERM [--limit N]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROBOT_EXTS = {".robot", ".resource"}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "results", "__pycache__", "graphify-out"}
JSON_DIR = "docs"
JSON_MAX_BYTES = 5_000_000
VALUE_WIDTH = 160
JSON_WIDTH = 300
CACHE_VERSION = 1


@dataclass
class Entry:
    kind: str                     # test | keyword | var | json | suite setup | test setup | ...
    name: str
    file: str                     # posix path relative to the root
    line: int = 0
    tags: list[str] = field(default_factory=list)
    args: str = ""
    doc: str = ""
    value: str = ""
    calls: list[list] = field(default_factory=list)   # [[keyword name, line], ...]
    refs: list[str] = field(default_factory=list)     # normalized variable names used in the body


def norm(name: str) -> str:
    """Robot matches keyword names case-, space- and underscore-insensitively."""
    return name.lower().replace(" ", "").replace("_", "")


VAR_REF = re.compile(r"[$@&%]\{([^}\[]+)")


def var_refs(text: str) -> list[str]:
    return [norm(m) for m in VAR_REF.findall(text)]


# ---------------------------------------------------------------- parsing

def parse_robot(path: Path, rel: str) -> list[Entry]:
    from robot.api import get_model, get_resource_model
    from robot.api.parsing import ModelVisitor

    model = (get_resource_model if path.suffix == ".resource" else get_model)(str(path))
    entries: list[Entry] = []
    file_tags: list[str] = []
    default_tags: list[str] = []

    class Visitor(ModelVisitor):
        scope: Entry | None = None

        def _body(self, node, entry):
            entries.append(entry)
            prev, self.scope = self.scope, entry
            self.generic_visit(node)
            self.scope = prev

        def visit_TestCase(self, node):
            if node.name:
                self._body(node, Entry("test", node.name, rel, node.lineno))

        def visit_Keyword(self, node):
            if node.name:
                self._body(node, Entry("keyword", node.name, rel, node.lineno))

        def visit_Tags(self, node):
            if self.scope:
                self.scope.tags.extend(node.values)

        def visit_TestTags(self, node):
            file_tags.extend(node.values)

        visit_ForceTags = visit_TestTags

        def visit_DefaultTags(self, node):
            default_tags.extend(node.values)

        def visit_Documentation(self, node):
            if self.scope:
                self.scope.doc = node.value.split("\n")[0].strip()
                self.scope.refs.extend(r for r in var_refs(node.value) if r not in self.scope.refs)

        def visit_Arguments(self, node):
            if self.scope:
                self.scope.args = ", ".join(node.values)

        def visit_Variable(self, node):
            if node.name:
                entries.append(Entry("var", node.name, rel, node.lineno, value=" ".join(node.value)))

        def visit_Var(self, node):
            if node.name:
                entries.append(Entry("var", node.name, rel, node.lineno, value=" ".join(node.value)))

        def visit_KeywordCall(self, node):
            if self.scope and node.keyword:
                self.scope.calls.append([node.keyword, node.lineno])
                self.scope.refs.extend(r for r in var_refs(" ".join(node.args)) if r not in self.scope.refs)

        def _scoped_fixture(self, node):
            if self.scope and node.name:
                self.scope.calls.append([node.name, node.lineno])

        visit_Setup = visit_Teardown = _scoped_fixture

        def _file_fixture(self, node, kind):
            if node.name:
                entries.append(Entry(kind, "", rel, node.lineno, calls=[[node.name, node.lineno]]))

        def visit_SuiteSetup(self, node):
            self._file_fixture(node, "suite setup")

        def visit_SuiteTeardown(self, node):
            self._file_fixture(node, "suite teardown")

        def visit_TestSetup(self, node):
            self._file_fixture(node, "test setup")

        def visit_TestTeardown(self, node):
            self._file_fixture(node, "test teardown")

    Visitor().visit(model)
    for e in entries:
        if e.kind == "test":
            if not e.tags:
                e.tags.extend(t for t in default_tags if t not in e.tags)
            e.tags.extend(t for t in file_tags if t not in e.tags)
    return entries


def flatten(value, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        out: list[str] = []
        for k, v in value.items():
            out.extend(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
        return out
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, list) else str(value)
    return [f"{prefix}={text}" if prefix else text]


def parse_json(path: Path, rel: str) -> list[Entry]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return [Entry("json", path.stem, rel, value=" ".join(flatten(data)))]
    entries = []
    for top, section in data.items():
        if isinstance(section, dict) and all(isinstance(v, dict) for v in section.values()):
            entries += [Entry("json", f"{top}.{k}", rel, value=" ".join(flatten(v))) for k, v in section.items()]
        else:
            entries.append(Entry("json", str(top), rel, value=" ".join(flatten(section))))
    return entries


def parse_file(path: Path, rel: str) -> list[Entry]:
    try:
        return parse_json(path, rel) if path.suffix == ".json" else parse_robot(path, rel)
    except Exception as exc:  # one broken file must not hide the rest of the index
        return [Entry("error", type(exc).__name__, rel, value=str(exc)[:VALUE_WIDTH])]


# ---------------------------------------------------------------- index + cache

def git_files(repo: Path) -> list[Path] | None:
    """Tracked and untracked-but-not-ignored files of the repo holding `repo`; None outside git."""
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                             cwd=repo, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return [repo / p for p in out.decode("utf-8").split("\0") if p]


def candidate_files(root: Path) -> list[Path]:
    """One repo: its git files. A folder of repos: each nested repo by its own git rules,
    plus the loose files around them."""
    inside = git_files(root)
    if inside is not None:
        return inside
    found: list[Path] = []
    repos: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        if (here / ".git").exists() and here != root:
            repos.append(here)
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        found += [here / name for name in filenames]
    with ThreadPoolExecutor(max_workers=8) as pool:   # git calls are I/O bound
        for files in pool.map(git_files, repos):
            found += files or []
    return found


def source_files(root: Path) -> list[Path]:
    def wanted(path: Path) -> bool:
        if path.suffix in ROBOT_EXTS:
            return path.is_file()
        return (path.suffix == ".json" and JSON_DIR in path.relative_to(root).parts[:-1]
                and path.is_file() and path.stat().st_size <= JSON_MAX_BYTES)
    return sorted(p for p in candidate_files(root) if wanted(p))


def load_index(root: Path, cache_dir: Path) -> list[Entry]:
    """Per-file cache keyed by mtime and size; only changed files are parsed again."""
    root = root.resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / (hashlib.sha1(str(root).encode()).hexdigest()[:16] + ".json")
    try:
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if cached.get("version") != CACHE_VERSION:
            cached = {}
    except (OSError, ValueError):
        cached = {}
    old_files = cached.get("files", {})
    files, changed = {}, False
    for path in source_files(root):
        rel = path.relative_to(root).as_posix()
        st = path.stat()
        stamp = [st.st_mtime_ns, st.st_size]
        hit = old_files.get(rel)
        if hit and hit["stamp"] == stamp:
            files[rel] = hit
        else:
            files[rel] = {"stamp": stamp, "entries": [asdict(e) for e in parse_file(path, rel)]}
            changed = True
    if changed or set(files) != set(old_files):
        tmp = cache_file.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": CACHE_VERSION, "root": str(root), "files": files}), encoding="utf-8")
        tmp.replace(cache_file)
    return [Entry(**e) for f in files.values() for e in f["entries"]]


# ---------------------------------------------------------------- queries

def q_ticket(entries, term):
    t = term.lower()
    return [e for e in entries if e.kind in ("test", "keyword")
            and (any(t in tag.lower() for tag in e.tags) or t in e.name.lower() or t in e.doc.lower())]


def q_kw(entries, term):
    exact = [e for e in entries if e.kind == "keyword" and norm(e.name) == norm(term)]
    return exact or [e for e in entries if e.kind == "keyword" and norm(term) in norm(e.name)]


def q_callers(entries, term):
    target = norm(term)
    exact = [(e, line) for e in entries for name, line in e.calls if norm(name) == target]
    return exact or [(e, line) for e in entries for name, line in e.calls if target in norm(name)]


def q_tag(entries, term):
    t = term.lower()
    match = (lambda tag: tag.lower().startswith(t[:-1])) if t.endswith("*") else (lambda tag: tag.lower() == t)
    return [e for e in entries if any(match(tag) for tag in e.tags)]


def find_rank(e: Entry, t: str) -> int | None:
    """0 exact name, 1 name contains, 2 tag contains, 3 doc/args/value contains, None no hit."""
    tiers = [[e.name.lower()] if e.name.lower() == t else [], [e.name.lower()],
             [tag.lower() for tag in e.tags], [e.doc.lower(), e.args.lower(), e.value.lower()]]
    return next((rank for rank, texts in enumerate(tiers) if any(t in text for text in texts)), None)


def q_find(entries, term):
    t = term.lower()
    ranked = sorted(((r, i, e) for i, e in enumerate(entries)
                     if e.kind != "error" and (r := find_rank(e, t)) is not None),
                    key=lambda x: (x[0], x[1]))
    hits = [e for _, _, e in ranked]
    hit_ids = {id(e) for e in hits}
    used = {ref for e in hits if e.kind == "var" for ref in var_refs(e.name)}
    users = [e for e in entries if id(e) not in hit_ids and used.intersection(e.refs)]
    return hits + users


def clip(text: str, width: int) -> str:
    return text if len(text) <= width else text[:width] + "..."


SUFFIX = {
    "test": lambda e: f"  [{' '.join(e.tags)}]" if e.tags else "",
    "keyword": lambda e: (f"  ({e.args})" if e.args else "") + (f"  - {e.doc}" if e.doc else ""),
    "var": lambda e: "  = " + clip(e.value, VALUE_WIDTH),
    "error": lambda e: "  = " + clip(e.value, VALUE_WIDTH),
    "json": lambda e: "  = " + clip(e.value, JSON_WIDTH),
}


def fmt(e: Entry, line: int | None = None) -> str:
    """One line per hit; a call-site line (callers) prints the location only."""
    at = line or e.line
    loc = f"{e.file}:{at}" if at else e.file
    head = "  ".join(part for part in (e.kind, e.name, loc) if part)
    return head if line else head + SUFFIX.get(e.kind, lambda _: "")(e)


def run(argv: list[str], root: Path | None = None, cache_dir: Path | None = None) -> str:
    p = argparse.ArgumentParser(prog="robot_mind", description=__doc__.split("\n")[0])
    p.add_argument("--root", type=Path, default=root or Path.cwd())
    p.add_argument("command", choices=["ticket", "kw", "callers", "tag", "find"])
    p.add_argument("term")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true", help="print hits as a JSON array")
    a = p.parse_args(argv)
    entries = load_index(a.root, cache_dir or Path.home() / ".cache" / "robotframework-mind")
    if a.command == "callers":
        hits = [(e, line) for e, line in q_callers(entries, a.term)]
    else:
        query = {"ticket": q_ticket, "kw": q_kw, "tag": q_tag, "find": q_find}[a.command]
        hits = [(e, None) for e in query(entries, a.term)]
    if a.json:
        out = [asdict(e) | ({"call_line": line} if line else {}) for e, line in hits[: a.limit]]
        return json.dumps(out, ensure_ascii=False)
    lines = [fmt(e, line) for e, line in hits]
    if not lines:
        return "no match"
    extra = len(lines) - a.limit
    out = lines[: a.limit] + ([f"({extra} more, raise --limit)"] if extra > 0 else [])
    return "\n".join(out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(run(sys.argv[1:]))
