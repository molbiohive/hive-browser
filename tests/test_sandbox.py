"""Tests for sandbox: ResultCache, safe_exec, and SandboxRunner."""

import pytest

from hive.sandbox.cache import ResultCache
from hive.sandbox.exec import safe_exec
from hive.sandbox.runner import SandboxRunner


# ── ResultCache ──


class TestResultCache:
    def test_store_and_get(self):
        cache = ResultCache()
        rows = [{"id": 1, "name": "GFP"}]
        handle = cache.store(rows, "search", {"query": "GFP"})
        assert handle == "r0"
        assert cache.get("r0") == rows

    def test_sequential_handles(self):
        cache = ResultCache()
        h0 = cache.store([{"a": 1}], "search")
        h1 = cache.store([{"b": 2}], "blast")
        h2 = cache.store([{"c": 3}], "parts")
        assert (h0, h1, h2) == ("r0", "r1", "r2")

    def test_get_missing(self):
        cache = ResultCache()
        assert cache.get("r0") is None
        assert cache.get("r99") is None
        assert cache.get("invalid") is None

    def test_describe(self):
        cache = ResultCache()
        cache.store([{"sid": 1, "name": "GFP", "size": 720}], "search", {"query": "GFP"})
        desc = cache.describe("r0")
        assert "r0:" in desc
        assert "1 rows" in desc
        assert "search" in desc
        assert "sid" in desc

    def test_describe_all(self):
        cache = ResultCache()
        cache.store([{"a": 1}], "search")
        cache.store([{"b": 2}], "blast")
        text = cache.describe_all()
        assert "r0:" in text
        assert "r1:" in text
        assert text.count("\n") == 1  # two lines, one newline

    def test_namespace(self):
        cache = ResultCache()
        rows0 = [{"x": 1}]
        rows1 = [{"y": 2}]
        cache.store(rows0, "search")
        cache.store(rows1, "blast")
        ns = cache.namespace()
        assert ns["r0"] is rows0
        assert ns["r1"] is rows1
        assert len(ns) == 2

    def test_contains(self):
        cache = ResultCache()
        cache.store([{"a": 1}], "search")
        assert "r0" in cache
        assert "r1" not in cache
        assert "invalid" not in cache

    def test_len(self):
        cache = ResultCache()
        assert len(cache) == 0
        cache.store([{"a": 1}], "search")
        assert len(cache) == 1
        cache.store([{"b": 2}], "blast")
        assert len(cache) == 2

    def test_describe_missing_handle(self):
        cache = ResultCache()
        assert cache.describe("r0") == ""

    def test_column_names_capped(self):
        """Columns beyond max_cols show '...'."""
        cache = ResultCache()
        row = {f"col{i}": i for i in range(12)}
        cache.store([row], "wide_tool")
        desc = cache.describe("r0")
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
        """Variables from cache namespace are accessible."""
        result = safe_exec(
            'result = len(r0) + len(r1)',
            {"r0": [1, 2, 3], "r1": [4, 5]},
        )
        assert result["status"] == "ok"
        assert result["result"] == 5


# ── SandboxRunner ──


class TestSandboxRunner:
    def test_tool_schema_includes_cache(self):
        cache = ResultCache()
        cache.store([{"sid": 1, "name": "GFP"}], "search")
        runner = SandboxRunner(cache)
        schema = runner.tool_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "python"
        assert "r0:" in schema["function"]["description"]
        assert "search" in schema["function"]["description"]

    def test_execute_dispatches(self):
        cache = ResultCache()
        data = [{"id": 1}, {"id": 2}, {"id": 3}]
        cache.store(data, "search")
        runner = SandboxRunner(cache)
        result = runner.execute('result = [r["id"] for r in r0]')
        assert result["status"] == "ok"
        assert result["result"] == [1, 2, 3]

    def test_summary_for_llm_ok(self):
        cache = ResultCache()
        runner = SandboxRunner(cache)
        result = {"status": "ok", "result": [1, 2, 3], "stdout": "", "type": "list"}
        summary = runner.summary_for_llm(result)
        assert "result = " in summary
        assert "[1, 2, 3]" in summary

    def test_summary_for_llm_error(self):
        cache = ResultCache()
        runner = SandboxRunner(cache)
        result = {"status": "error", "error": "NameError: x", "stdout": ""}
        summary = runner.summary_for_llm(result)
        assert "Error:" in summary
        assert "NameError" in summary

    def test_summary_for_llm_with_stdout(self):
        cache = ResultCache()
        runner = SandboxRunner(cache)
        result = {"status": "ok", "result": 42, "stdout": "debug\n", "type": "scalar"}
        summary = runner.summary_for_llm(result)
        assert "result = 42" in summary
        assert "stdout: debug" in summary

    def test_summary_for_llm_truncates(self):
        cache = ResultCache()
        runner = SandboxRunner(cache)
        big_list = list(range(1000))
        result = {"status": "ok", "result": big_list, "stdout": "", "type": "list"}
        summary = runner.summary_for_llm(result, token_limit=10)
        assert len(summary) <= 10 * 4 + 50  # some overhead for "result = " prefix

    def test_tool_schema_empty_cache(self):
        cache = ResultCache()
        runner = SandboxRunner(cache)
        schema = runner.tool_schema()
        assert schema["function"]["name"] == "python"
        # Description still valid, just no cache entries listed
        assert "result" in schema["function"]["description"]
