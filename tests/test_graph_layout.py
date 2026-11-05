"""Force layout and communities: plain graphs with known shapes."""
import math
import unittest

from robot_mind_app import graph_layout as gl
from robot_mind_app.graph import Edge, Graph, Node


def make(edges, focus=("a",)):
    names = sorted({n for e in edges for n in e} | set(focus))
    nodes = {n: Node(n, n.upper(), "keyword") for n in names}
    return Graph(nodes, [Edge(s, d, "call") for s, d in edges], list(focus))


TWO_TRIANGLES = make([("a", "b"), ("b", "c"), ("c", "a"), ("x", "y"), ("y", "z"), ("z", "x"), ("a", "hub"),
                      ("b", "hub"), ("c", "hub"), ("hub", "d"), ("hub", "e")],     # hub: the best linked node
                     focus=("a", "x"))                                            # every node reachable, as in a search


def dist(pos, a, b):
    return math.dist(pos[a], pos[b])


class LayoutTests(unittest.TestCase):
    def test_every_node_gets_a_position(self):
        pos = gl.layout(TWO_TRIANGLES)
        self.assertEqual(set(pos), set(TWO_TRIANGLES.nodes))

    def test_same_graph_same_picture(self):
        self.assertEqual(gl.layout(TWO_TRIANGLES), gl.layout(TWO_TRIANGLES))

    def test_linked_nodes_sit_closer(self):
        pos = gl.layout(TWO_TRIANGLES)
        self.assertLess(dist(pos, "a", "b"), dist(pos, "a", "y"))

    def test_single_node_is_centred(self):
        self.assertEqual(gl.layout(make([], focus=("a",))), {"a": (0.0, 0.0)})


FILES = {"a": "repo-a/tests/a.robot", "b": "repo-a/tests/b.robot", "c": "group/repo-b/r.resource",
         "x": "", "y": "docs/x.robot", "z": "top.robot"}


def placed():
    g = make([("a", "b"), ("b", "c"), ("c", "x"), ("x", "y"), ("y", "z")])
    return Graph({n: Node(n, n, "keyword", FILES[n]) for n in g.nodes}, g.edges, g.focus)


class CommunityTests(unittest.TestCase):
    def test_repo_names_the_community(self):
        group, names = gl.communities(placed(), ["group/repo-b", "repo-a"])
        self.assertEqual(names[group["a"]], "repo-a", "first repo")
        self.assertEqual(names[group["c"]], "repo-b", "nested repo, last segment")

    def test_folder_outside_repos(self):
        group, names = gl.communities(placed(), [])
        self.assertEqual(names[group["y"]], "docs", "top folder")
        self.assertEqual(names[group["z"]], "(root)", "file at the root")
        self.assertEqual(names[group["x"]], "endpoints", "no file")

    def test_biggest_community_is_first(self):
        group, names = gl.communities(placed(), ["group/repo-b", "repo-a"])
        self.assertEqual(names[0], "repo-a")


class DrawingTests(unittest.TestCase):
    def test_drawing_trims_and_counts(self):
        drawing = gl.plan(TWO_TRIANGLES, limit=4)
        self.assertEqual(len(drawing.graph.nodes), 4, "trimmed")
        self.assertEqual(drawing.total, 9, "total before the cap")
        self.assertEqual(set(drawing.pos), set(drawing.graph.nodes), "positions")


if __name__ == "__main__":
    unittest.main()
