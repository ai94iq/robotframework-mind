"""Graph builder tests: nodes and edges from the fixture repo."""
import shutil
import tempfile
import unittest
from pathlib import Path

from robot_mind import load_index, lookup
from robot_mind_app import engine, graph

FIXTURE = Path(__file__).parent / "fixture"


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "repo"
        shutil.copytree(FIXTURE, self.root)
        self.cache = self.tmp / "cache"
        self.entries = load_index(self.root, self.cache)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def focus(self, command, term, depth=1):
        matches = [entry for entry, _line in lookup(self.entries, command, term)]
        return graph.focus(self.entries, matches, depth)

    def node(self, g, label):
        return next(n for n in g.nodes.values() if n.label == label)

    def test_ticket_links_called_keyword(self):
        g = self.focus("ticket", "PROJ-2120")
        test = self.node(g, "Change Zone NEW Lists Zones")
        kw = self.node(g, "Open Cases Page")
        self.assertIn(graph.Edge(test.id, kw.id, "call"), g.edges)
        self.assertEqual(g.focus, [test.id])

    def test_ticket_hits_its_endpoint(self):
        g = self.focus("ticket", "PROJ-2120")
        test = self.node(g, "Change Zone NEW Lists Zones")
        endpoint = self.node(g, "GET /api/zones/list")
        self.assertEqual(endpoint.kind, "endpoint")
        self.assertIn(graph.Edge(test.id, endpoint.id, "hits"), g.edges)

    def test_keyword_uses_its_variable(self):
        g = self.focus("kw", "Query Items")
        kw = self.node(g, "Query Items")
        var = self.node(g, "${ENDPOINT_ITEMS_QUERY}")
        self.assertIn(graph.Edge(kw.id, var.id, "uses"), g.edges)

    def test_callers_focus_the_caller(self):
        g = self.focus("callers", "Open Cases Page")
        callers = {g.nodes[nid].label for nid in g.focus}
        self.assertEqual(callers, {"Change Zone NEW Lists Zones", "Cases Page Opens For QC"})

    def test_depth_extends_the_reach(self):
        one = self.focus("ticket", "PROJ-2120", depth=1)
        three = self.focus("ticket", "PROJ-2120", depth=3)
        labels = lambda g: {n.label for n in g.nodes.values()}
        self.assertNotIn("Query Items", labels(one), "depth 1 stops at the called keyword")
        self.assertIn("Query Items", labels(three), "depth 3 follows the call chain")

    def test_default_depth_is_one(self):
        matches = [e for e, _ in lookup(self.entries, "ticket", "PROJ-2120")]
        self.assertEqual(graph.focus(self.entries, matches), self.focus("ticket", "PROJ-2120", 1))

    def test_edges_stay_inside_nodes(self):
        g = self.focus("kw", "Open Cases Page")
        outside = [e for e in g.edges if e.src not in g.nodes or e.dst not in g.nodes]
        self.assertEqual(outside, [])

    def test_repeated_call_is_one_edge(self):
        g = self.focus("find", "Cases Page Cleans Up")
        test = self.node(g, "Cases Page Cleans Up")
        kw = self.node(g, "Query Items")
        self.assertEqual(g.edges.count(graph.Edge(test.id, kw.id, "call")), 1)

    def test_no_match_is_empty(self):
        self.assertEqual(self.focus("ticket", "PROJ-9999"), graph.Graph({}, [], []))

    def test_layers_put_callers_left(self):
        g = self.focus("kw", "Query Items")
        layer = graph.layers(g)
        self.assertEqual(layer[self.node(g, "Query Items").id], 0, "focus")
        self.assertEqual(layer[self.node(g, "Open Authenticated Browser").id], -1, "caller")
        self.assertEqual(layer[self.node(g, "${ENDPOINT_ITEMS_QUERY}").id], 1, "used variable")

    def test_trim_keeps_the_nearest(self):
        g = self.focus("kw", "Query Items", depth=2)
        trimmed = graph.trim(g, 3)
        layer = graph.layers(g)
        self.assertEqual(len(trimmed.nodes), 3, "node count")
        self.assertTrue(all(abs(layer[nid]) <= 1 for nid in trimmed.nodes), "nearest kept")
        self.assertTrue(all(e.src in trimmed.nodes and e.dst in trimmed.nodes for e in trimmed.edges), "edges")

    def test_trim_under_limit_is_same(self):
        g = self.focus("ticket", "PROJ-2120")
        self.assertIs(graph.trim(g, 100), g)

    def test_engine_graph_matches_focus(self):
        g = engine.graph(self.root, "ticket", "PROJ-2120", cache_dir=self.cache)
        self.assertEqual(g, self.focus("ticket", "PROJ-2120"))


if __name__ == "__main__":
    unittest.main()
