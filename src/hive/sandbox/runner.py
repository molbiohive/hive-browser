"""SandboxRunner -- orchestrates workspace + exec, provides tool schema."""

from __future__ import annotations

import json
from typing import Any

from hive.sandbox.exec import safe_exec
from hive.sandbox.workspace import Workspace


class SandboxRunner:
    """Execution orchestrator for the built-in python sandbox.

    Not a Tool -- this is a server-side runtime capability injected
    by the router alongside regular tool schemas.
    """

    def __init__(self, workspace: Workspace):
        self.workspace = workspace

    def tool_schema(self) -> dict:
        """OpenAI-format function schema with dynamic workspace description."""
        desc = (
            "Execute Python on cached data. Variables in scope:\n"
            + self.workspace.describe_all()
            + "\nMust assign to `result`."
        )
        return {
            "type": "function",
            "function": {
                "name": "python",
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python code. Assign output to `result`.",
                        },
                    },
                    "required": ["code"],
                },
            },
        }

    def execute(self, code: str) -> dict[str, Any]:
        """Run *code* with all workspace handles as variables."""
        variables = self.workspace.namespace()
        return safe_exec(code, variables)

    def summary_for_llm(self, result: dict[str, Any], token_limit: int = 500) -> str:
        """Compact result summary for LLM context."""
        if result["status"] == "error":
            parts = [f"Error: {result['error']}"]
            if result.get("stdout"):
                parts.append(f"stdout: {result['stdout'].rstrip()}")
            return "\n".join(parts)

        value = result["result"]
        stdout = result.get("stdout", "")
        max_chars = token_limit * 4

        # Format the result value
        if isinstance(value, (list, dict)):
            text = json.dumps(value, default=str)
            if len(text) > max_chars:
                text = text[:max_chars - 3] + "..."
        else:
            text = str(value)

        parts = [f"result = {text}"]
        if stdout:
            parts.append(f"stdout: {stdout.rstrip()}")
        return "\n".join(parts)
