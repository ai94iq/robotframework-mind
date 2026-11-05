"""Build a call/use graph over a Robot Framework repo, focused on a lookup."""
from collections import defaultdict, deque
from collections.abc import Iterator
from dataclasses import dataclass, field

from robot_mind import Entry, norm, var_refs


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    label: str
    kind: str          # test | keyword | var | endpoint
    file: str = ""
    line: int = 0


@dataclass(frozen=True, slots=True)
class Edge:
    src: str
    dst: str
    kind: str          # call | uses | hits


@dataclass(frozen=True, slots=True)
class Graph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    focus: list[str] = field(default_factory=list)


def _node_id(entry: Entry) -> str | None:
    if entry.kind == "test":
        return f"test:{entry.file}:{entry.line}"
    if entry.kind == "keyword":
        return f"kw:{norm(entry.name)}"
    if entry.kind == "var":
        refs = var_refs(entry.name)
        return f"var:{refs[0]}" if refs else None
    return None


def _endpoints(entry: Entry) -> list[str]:
    """Endpoints named by op: tags, such as op:GET /api/items."""
    return [tag[3:].strip() for tag in entry.tags if tag.lower().startswith("op:")]


def _endpoint_id(endpoint: str) -> str:
    return f"ep:{norm(endpoint)}"


def _nodes(entries: list[Entry]) -> dict[str, Node]:
    nodes: dict[str, Node] = {}
    for e in entries:
        nid = _node_id(e)
        if nid is None:
            continue
        nodes.setdefault(nid, Node(nid, e.name, e.kind, e.file, e.line))
        for endpoint in _endpoints(e):
            eid = _endpoint_id(endpoint)
            nodes.setdefault(eid, Node(eid, endpoint, "endpoint"))
    return nodes


def _links(entry: Entry) -> Iterator[tuple[str, str]]:
    """(target id, edge kind) for every call, variable use and endpoint of an entry."""
    for name, _line in entry.calls:
        yield f"kw:{norm(name)}", "call"
    for ref in entry.refs:
        yield f"var:{ref}", "uses"
    for endpoint in _endpoints(entry):
        yield _endpoint_id(endpoint), "hits"


def _edges(entries: list[Entry], nodes: dict[str, Node]) -> list[Edge]:
    """Edges between known nodes, once each, in index order."""
    edges: dict[Edge, None] = {}
    for e in entries:
        src = _node_id(e)
        if src is None:
            continue
        for dst, kind in _links(e):
            if dst in nodes:
                edges.setdefault(Edge(src, dst, kind))
    return list(edges)


def _neighborhood(edges: list[Edge], start: list[str], depth: int) -> set[str]:
    adjacent: dict[str, set[str]] = defaultdict(set)
    for ed in edges:
        adjacent[ed.src].add(ed.dst)
        adjacent[ed.dst].add(ed.src)
    keep, frontier = set(start), set(start)
    for _ in range(depth):
        frontier = {other for node in frontier for other in adjacent[node]} - keep
        keep |= frontier
    return keep


def focus(entries: list[Entry], matches: list[Entry], depth: int = 1) -> Graph:
    """The graph within depth links of the matched entries; empty when none is a node."""
    nodes = _nodes(entries)
    start = list(dict.fromkeys(nid for nid in map(_node_id, matches) if nid in nodes))
    if not start:
        return Graph()
    edges = _edges(entries, nodes)
    keep = _neighborhood(edges, start, depth)
    return _subgraph(Graph(nodes, edges, start), keep)


def _subgraph(g: Graph, keep: set[str]) -> Graph:
    return Graph({nid: n for nid, n in g.nodes.items() if nid in keep},
                 [ed for ed in g.edges if ed.src in keep and ed.dst in keep],
                 [nid for nid in g.focus if nid in keep])


def layers(g: Graph) -> dict[str, int]:
    """Signed link distance from the focus: callers go negative, what the focus calls or uses positive."""
    steps: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for ed in g.edges:
        steps[ed.src].append((ed.dst, 1))
        steps[ed.dst].append((ed.src, -1))
    layer = dict.fromkeys(g.focus, 0)
    queue = deque(g.focus)
    while queue:
        nid = queue.popleft()
        for other, step in steps[nid]:
            if other not in layer:
                layer[other] = layer[nid] + step
                queue.append(other)
    return layer


def trim(g: Graph, limit: int) -> Graph:
    """At most limit nodes, nearest to the focus first; the graph itself when it already fits."""
    if len(g.nodes) <= limit:
        return g
    layer = layers(g)
    nearest = sorted(g.nodes, key=lambda nid: abs(layer[nid]))
    return _subgraph(g, set(nearest[:limit]))
