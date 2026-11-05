"""Where each node goes and which community it joins: a seeded force layout and label propagation, pure Python."""
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass

from .graph import Graph, trim

SPACING = 60.0             # px a linked pair settles at, roughly
ITERATIONS = 160


@dataclass(frozen=True, slots=True)
class Drawing:
    graph: Graph                           # what gets drawn, already trimmed
    total: int                             # nodes before the cap
    pos: dict[str, tuple[float, float]]
    group: dict[str, int]                  # node id to community, 0 the biggest
    names: list[str]                       # community name by number


def neighbors(g: Graph) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for ed in g.edges:
        if ed.src != ed.dst:
            out[ed.src].add(ed.dst)
            out[ed.dst].add(ed.src)
    return out


def _forces(ids, pos, links, k):
    """Push every pair apart, pull linked pairs together, and draw everything gently to the centre."""
    disp = {nid: [0.0, 0.0] for nid in ids}
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            dx, dy = pos[a][0] - pos[b][0], pos[a][1] - pos[b][1]
            d2 = max(dx * dx + dy * dy, 0.01)
            push = k * k / d2
            disp[a][0] += dx * push; disp[a][1] += dy * push
            disp[b][0] -= dx * push; disp[b][1] -= dy * push
    for a, b in links:
        dx, dy = pos[a][0] - pos[b][0], pos[a][1] - pos[b][1]
        pull = math.hypot(dx, dy) / k
        disp[a][0] -= dx * pull; disp[a][1] -= dy * pull
        disp[b][0] += dx * pull; disp[b][1] += dy * pull
    for nid in ids:
        disp[nid][0] -= pos[nid][0] * 0.05
        disp[nid][1] -= pos[nid][1] * 0.05
    return disp


def layout(g: Graph, seed: int = 7) -> dict[str, tuple[float, float]]:
    """Fruchterman-Reingold with a fixed seed, so one search always draws the same picture."""
    ids = list(g.nodes)
    if len(ids) == 1:
        return {ids[0]: (0.0, 0.0)}
    rng = random.Random(seed)
    spread = SPACING * math.sqrt(len(ids))
    pos = {nid: [rng.uniform(-spread, spread), rng.uniform(-spread, spread)] for nid in ids}
    links = [(ed.src, ed.dst) for ed in g.edges if ed.src != ed.dst]
    for step in range(ITERATIONS):
        heat = spread * (1 - step / ITERATIONS) / 4 + 1
        for nid, (dx, dy) in _forces(ids, pos, links, SPACING).items():
            length = math.hypot(dx, dy) or 1.0
            move = min(length, heat) / length
            pos[nid][0] += dx * move
            pos[nid][1] += dy * move
    return {nid: (round(x, 2), round(y, 2)) for nid, (x, y) in pos.items()}


ENDPOINTS = "endpoints"


def home(file: str, repos: list[str]) -> str:
    """Where a node lives: its repo when the root holds several, else its top folder; endpoints have no file."""
    if not file:
        return ENDPOINTS
    repo = next((r for r in repos if file.startswith(r.rstrip("/") + "/")), None)
    if repo:
        return repo.rsplit("/", 1)[-1]
    return file.split("/", 1)[0] if "/" in file else "(root)"


def communities(g: Graph, repos: list[str]) -> tuple[dict[str, int], list[str]]:
    """Node id to community number (0 the biggest) and the community names: one per repo or folder."""
    where = {nid: home(node.file, repos) for nid, node in g.nodes.items()}
    sizes = Counter(where.values())
    names = sorted(sizes, key=lambda name: (-sizes[name], name))
    number = {name: i for i, name in enumerate(names)}
    return {nid: number[name] for nid, name in where.items()}, names


def plan(g: Graph, limit: int, repos: list[str] = ()) -> Drawing:
    """Everything the view needs, computed off the UI thread."""
    shown = trim(g, limit)
    group, names = communities(shown, list(repos))
    return Drawing(shown, len(g.nodes), layout(shown), group, names)
