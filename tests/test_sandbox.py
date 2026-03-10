"""Tests for sandbox: Workspace, safe_exec, and SandboxRunner."""

import pytest

from hive.sandbox.exec import safe_exec
from hive.sandbox.runner import SandboxRunner
from hive.sandbox.workspace import Workspace


# ── Workspace ──


class TestWorkspace:
    def test_store_and_get(self):
        ws = Workspace()
        rows = [{"id": 1, "name": "GFP"}]
        handle = ws.store("results", rows, "search", {"query": "GFP"})
        assert handle == "r0"
        assert ws.get("r0") == rows

    def test_sequential_handles(self):
        ws = Workspace()
        h0 = ws.store("results", [{"a": 1}], "search")
        h1 = ws.store("hits", [{"b": 2}], "blast")
        h2 = ws.store("parts", [{"c": 3}], "parts")
        assert (h0, h1, h2) == ("r0", "r1", "r2")

    def test_get_missing(self):
        ws = Workspace()
        assert ws.get("r0") is None
        assert ws.get("r99") is None
        assert ws.get("invalid") is None

    def test_describe_list_dict(self):
        ws = Workspace()
        ws.store("results", [{"sid": 1, "name": "GFP", "size": 720}], "search", {"query": "GFP"})
        desc = ws.describe("r0")
        assert "r0:" in desc
        assert "results" in desc
        assert "list[dict]" in desc
        assert "1 rows" in desc
        assert "search" in desc
        assert "sid" in desc

    def test_describe_string(self):
        ws = Workspace()
        ws.store("sequence_data", "ATGC" * 100, "profile")
        desc = ws.describe("r0")
        assert "str" in desc
        assert "400 chars" in desc
        assert "profile" in desc

    def test_describe_list_int(self):
        ws = Workspace()
        ws.store("fragments", [4521, 2100, 800], "digest")
        desc = ws.describe("r0")
        assert "list[int]" in desc
        assert "3 items" in desc

    def test_describe_dict(self):
        ws = Workspace()
        ws.store("gel_data", {"lanes": [], "gelType": "agarose", "stain": "ethidium"}, "digest")
        desc = ws.describe("r0")
        assert "dict" in desc
        assert "3 keys" in desc

    def test_describe_all(self):
        ws = Workspace()
        ws.store("results", [{"a": 1}], "search")
        ws.store("sequence_data", "ATGC" * 100, "profile")
        text = ws.describe_all()
        assert "r0:" in text
        assert "r1:" in text
        assert text.count("\n") == 1  # two lines, one newline

    def test_namespace(self):
        ws = Workspace()
        rows0 = [{"x": 1}]
        seq = "ATGCATGC"
        ws.store("results", rows0, "search")
        ws.store("sequence_data", seq, "profile")
        ns = ws.namespace()
        assert ns["r0"] is rows0
        assert ns["r1"] is seq
        assert len(ns) == 2

    def test_find_by_field(self):
        ws = Workspace()
        ws.store("sequence_data", "ATGC" * 100, "profile")
        ws.store("results", [{"a": 1}], "search")
        # Should find the string by field name
        found = ws.find_by_field("sequence_data", min_length=10)
        assert found == "ATGC" * 100

    def test_find_by_field_min_length(self):
        ws = Workspace()
        ws.store("sequence_data", "ATG", "profile")
        # Too short
        assert ws.find_by_field("sequence_data", min_length=100) is None
        # No min_length requirement
        assert ws.find_by_field("sequence_data") == "ATG"

    def test_find_by_field_most_recent(self):
        ws = Workspace()
        ws.store("sequence_data", "FIRST", "profile")
        ws.store("sequence_data", "SECOND", "profile")
        assert ws.find_by_field("sequence_data") == "SECOND"

    def test_find_by_field_skips_non_strings(self):
        ws = Workspace()
        ws.store("sequence", {"sid": 1, "name": "GFP"}, "search")
        # Dict with matching field name should NOT be returned
        assert ws.find_by_field("sequence") is None
        # But a string with the same field name should be found
        ws.store("sequence", "ATGCATGC", "profile")
        assert ws.find_by_field("sequence") == "ATGCATGC"

    def test_find_by_field_not_found(self):
        ws = Workspace()
        ws.store("results", [{"a": 1}], "search")
        assert ws.find_by_field("sequence_data") is None

    def test_contains(self):
        ws = Workspace()
        ws.store("results", [{"a": 1}], "search")
        assert "r0" in ws
        assert "r1" not in ws
        assert "invalid" not in ws

    def test_len(self):
        ws = Workspace()
        assert len(ws) == 0
        ws.store("results", [{"a": 1}], "search")
        assert len(ws) == 1
        ws.store("hits", [{"b": 2}], "blast")
        assert len(ws) == 2

    def test_describe_missing_handle(self):
        ws = Workspace()
        assert ws.describe("r0") == ""

    def test_column_names_capped(self):
        """Columns beyond max_cols show '...'."""
        ws = Workspace()
        row = {f"col{i}": i for i in range(12)}
        ws.store("results", [row], "wide_tool")
        desc = ws.describe("r0")
        assert "..." in desc


# ── safe_exec ──


class TestSafeExec:
    def test_filter_list(self):
        data = [{"name": "GFP", "size": 720}, {"name": "RFP", "size": 680}]
        result = safe_exec(
            'result = [r for r in data if r["size"] > 700]',
            {"data": data},
        )
        assert result["status"] == "ok"
        assert len(result["result"]) == 1
        assert result["result"][0]["name"] == "GFP"

    def test_aggregation(self):
        data = [{"v": 10}, {"v": 20}, {"v": 30}]
        result = safe_exec('result = sum(r["v"] for r in data)', {"data": data})
        assert result["status"] == "ok"
        assert result["result"] == 60

    def test_sorted_result(self):
        data = [{"n": "C"}, {"n": "A"}, {"n": "B"}]
        result = safe_exec(
            'result = sorted(data, key=lambda r: r["n"])',
            {"data": data},
        )
        assert result["status"] == "ok"
        assert [r["n"] for r in result["result"]] == ["A", "B", "C"]

    def test_comprehension(self):
        data = [{"id": 1}, {"id": 2}, {"id": 3}]
        result = safe_exec('result = [r["id"] for r in data]', {"data": data})
        assert result["status"] == "ok"
        assert result["result"] == [1, 2, 3]

    def test_must_assign_result(self):
        result = safe_exec("x = 42")
        assert result["status"] == "error"
        assert "result" in result["error"]

    def test_empty_code(self):
        result = safe_exec("")
        assert result["status"] == "error"
        assert "Empty" in result["error"]

    def test_whitespace_only(self):
        result = safe_exec("   \n  ")
        assert result["status"] == "error"
        assert "Empty" in result["error"]

    def test_import_blocked(self):
        result = safe_exec("import os\nresult = 1")
        assert result["status"] == "error"
        assert "Blocked" in result["error"]

    def test_open_blocked(self):
        result = safe_exec('result = open("/etc/passwd")')
        assert result["status"] == "error"
        assert "Blocked" in result["error"]

    def test_exec_blocked(self):
        result = safe_exec('exec("x=1")\nresult = 1')
        assert result["status"] == "error"
        assert "Blocked" in result["error"]

    def test_eval_blocked(self):
        result = safe_exec('result = eval("1+1")')
        assert result["status"] == "error"
        assert "Blocked" in result["error"]

    def test_dunder_import_blocked(self):
        result = safe_exec('result = __import__("os")')
        assert result["status"] == "error"
        assert "Blocked" in result["error"]

    def test_syntax_error(self):
        result = safe_exec("result = [")
        assert result["status"] == "error"
        assert "SyntaxError" in result["error"]

    def test_runtime_error(self):
        result = safe_exec('result = 1 / 0')
        assert result["status"] == "error"
        assert "ZeroDivisionError" in result["error"]

    def test_name_error(self):
        result = safe_exec("result = undefined_var")
        assert result["status"] == "error"
        assert "NameError" in result["error"]

    def test_type_classification_list(self):
        result = safe_exec("result = [1, 2, 3]")
        assert result["type"] == "list"

    def test_type_classification_dict(self):
        result = safe_exec('result = {"key": "val"}')
        assert result["type"] == "dict"

    def test_type_classification_scalar(self):
        result = safe_exec("result = 42")
        assert result["type"] == "scalar"

    def test_stdout_capture(self):
        result = safe_exec('print("hello")\nresult = 1')
        assert result["status"] == "ok"
        assert result["stdout"] == "hello\n"
        assert result["result"] == 1

    def test_stdout_on_error(self):
        result = safe_exec('print("before")\nresult = 1 / 0')
        assert result["status"] == "error"
        assert "before" in result["stdout"]

    def test_builtins_available(self):
        """Core builtins (len, sum, min, max, etc.) work."""
        result = safe_exec("result = len([1, 2, 3])")
        assert result["result"] == 3

        result = safe_exec("result = max(1, 5, 3)")
        assert result["result"] == 5

        result = safe_exec("result = list(range(3))")
        assert result["result"] == [0, 1, 2]

    def test_no_variables(self):
        """Code can run without any injected variables."""
        result = safe_exec("result = sum(range(10))")
        assert result["status"] == "ok"
        assert result["result"] == 45

    def test_cached_variables_in_scope(self):
        """Variables from workspace namespace are accessible."""
        result = safe_exec(
            'result = len(r0) + len(r1)',
            {"r0": [1, 2, 3], "r1": [4, 5]},
        )
        assert result["status"] == "ok"
        assert result["result"] == 5


# ── SandboxRunner ──


class TestSandboxRunner:
    def test_tool_schema_includes_workspace(self):
        ws = Workspace()
        ws.store("results", [{"sid": 1, "name": "GFP"}], "search")
        runner = SandboxRunner(ws)
        schema = runner.tool_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "python"
        assert "r0:" in schema["function"]["description"]
        assert "search" in schema["function"]["description"]

    def test_execute_dispatches(self):
        ws = Workspace()
        data = [{"id": 1}, {"id": 2}, {"id": 3}]
        ws.store("results", data, "search")
        runner = SandboxRunner(ws)
        result = runner.execute('result = [r["id"] for r in r0]')
        assert result["status"] == "ok"
        assert result["result"] == [1, 2, 3]

    def test_execute_with_string_handle(self):
        ws = Workspace()
        ws.store("sequence_data", "ATGCATGC", "profile")
        runner = SandboxRunner(ws)
        result = runner.execute('result = len(r0)')
        assert result["status"] == "ok"
        assert result["result"] == 8

    def test_summary_for_llm_ok(self):
        ws = Workspace()
        runner = SandboxRunner(ws)
        result = {"status": "ok", "result": [1, 2, 3], "stdout": "", "type": "list"}
        summary = runner.summary_for_llm(result)
        assert "result = " in summary
        assert "[1, 2, 3]" in summary

    def test_summary_for_llm_error(self):
        ws = Workspace()
        runner = SandboxRunner(ws)
        result = {"status": "error", "error": "NameError: x", "stdout": ""}
        summary = runner.summary_for_llm(result)
        assert "Error:" in summary
        assert "NameError" in summary

    def test_summary_for_llm_with_stdout(self):
        ws = Workspace()
        runner = SandboxRunner(ws)
        result = {"status": "ok", "result": 42, "stdout": "debug\n", "type": "scalar"}
        summary = runner.summary_for_llm(result)
        assert "result = 42" in summary
        assert "stdout: debug" in summary

    def test_summary_for_llm_truncates(self):
        ws = Workspace()
        runner = SandboxRunner(ws)
        big_list = list(range(1000))
        result = {"status": "ok", "result": big_list, "stdout": "", "type": "list"}
        summary = runner.summary_for_llm(result, token_limit=10)
        assert len(summary) <= 10 * 4 + 50  # some overhead for "result = " prefix

    def test_tool_schema_empty_workspace(self):
        ws = Workspace()
        runner = SandboxRunner(ws)
        schema = runner.tool_schema()
        assert schema["function"]["name"] == "python"
        # Description still valid, just no workspace entries listed
        assert "result" in schema["function"]["description"]
