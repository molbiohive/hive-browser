"""System prompts and tool calling schema for the LLM.

Tool calling flow (one tool per turn):
  1. User message + system prompt + tool schemas → LLM
  2. LLM returns tool_calls with name + arguments
  3. Server executes the tool, gets result
  4. Tool result appended to messages → LLM
  5. LLM returns natural language summary
"""

_SYSTEM_PROMPT_TEMPLATE = """\
You are Zerg Browser, a lab sequence search assistant. Scientists use you to find \
and explore DNA/RNA/protein sequences stored in their local file system.

## Available Tools
{tool_section}

## Parameter Guidelines
- **search**: Put the main keyword in `query` (e.g. "GFP", "ampicillin", "pUC19"). \
Leave `filters` empty unless the user explicitly asks to filter by topology or size. \
Do NOT add `feature_type` unless the user specifically requests it.
- **blast**: Use when the user provides a raw nucleotide sequence (ATGC...) or asks \
for sequence similarity. Put the sequence in `sequence`. Also accepts a sequence name \
to look up from the database.
- **profile**: Use when the user wants details about a specific sequence. Put the \
exact name in `name` (e.g. "BlueScribe-mEGFP").

## Rules
- Call exactly ONE tool per turn.
- Extract parameters from the user's message. Ask for clarification only if truly ambiguous.
- NEVER put nucleotide sequences in search `query` — use blast for sequence similarity.
- NEVER fabricate sequences, IDs, file paths, or data. Only report what tools return.
- NEVER output raw JSON or tool call objects in your response text.
- If no results found, suggest broadening the search or trying a different tool.

## Response Format
After a tool runs, write a 1-2 sentence natural language summary. The user sees a \
visual widget with the full data, so do NOT repeat individual results or table rows."""


def build_system_prompt(registry) -> str:
    """Generate the system prompt dynamically from the tool registry."""
    lines = []
    for t in registry.all():
        if not t.use_llm:
            continue
        schema = t.input_schema().model_json_schema()
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        param_parts = []
        for pname in props:
            mark = " *" if pname in required else ""
            param_parts.append(f"`{pname}`{mark}")
        params_str = " — params: " + ", ".join(param_parts) if param_parts else ""
        lines.append(f"- **{t.name}**: {t.description}{params_str}")
    return _SYSTEM_PROMPT_TEMPLATE.format(tool_section="\n".join(lines))


# Fallback for cases where registry isn't available
SYSTEM_PROMPT = _SYSTEM_PROMPT_TEMPLATE.format(tool_section="(tools loading...)")


def build_tool_schemas(registry) -> list[dict]:
    """Convert ToolRegistry into OpenAI function calling format (only LLM-visible tools)."""
    tools = []
    for tool in registry.all():
        if not tool.use_llm:
            continue
        schema = tool.input_schema().model_json_schema()
        # Remove pydantic metadata keys that LLMs don't need
        schema.pop("title", None)

        tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": schema,
            },
        })
    return tools
