"""Tests for Workspace to_json(), from_json() round-trip."""

from hive.sandbox.workspace import Workspace


class TestWorkspaceToJson:
    def test_round_trip(self):
        ws = Workspace()
        ws.store("results", [{"id": 1, "name": "GFP"}], "search", {"q": "GFP"})
        ws.store("sequence", "ATCGATCG", "extract", {"sid": 1})

        data = ws.to_json()
        ws2 = Workspace.from_json(data)

        assert len(ws2) == len(ws)
        assert ws2.get("p0") == [{"id": 1, "name": "GFP"}]
        assert ws2.get("p1") == "ATCGATCG"

    def test_from_json_empty(self):
        ws = Workspace.from_json([])
        assert len(ws) == 0

    def test_handles_preserved(self):
        ws = Workspace()
        h0 = ws.store("a", [1, 2], "t1")
        h1 = ws.store("b", [3, 4], "t2")

        ws2 = Workspace.from_json(ws.to_json())
        assert ws2.get(h0) == [1, 2]
        assert ws2.get(h1) == [3, 4]
