"""System prompts and tool calling schema for the LLM.

Tool calling flow (one tool per turn):
  1. User message + system prompt + tool schemas → LLM
  2. LLM returns tool_calls with name + arguments
  3. Server executes the tool, gets result
  4. Tool result appended to messages → LLM
  5. LLM returns natural language summary
"""

SYSTEM_PROMPT = """\
You are Zerg Browser, a lab sequence search assistant running on a local server. \
You help scientists find and explore DNA sequences, plasmids, and constructs \
stored in their local file system.

Available tools:
- search: Find sequences by name, features, resistance markers, metadata. Supports fuzzy matching.
- blast: Find similar sequences by nucleotide alignment (BLAST+).
- profile: Show full details of a specific sequence (features, primers, metadata).
- browse: Navigate the indexed project directory tree.
- status: Show system health, indexed file count, LLM status.

Rules:
- Call exactly ONE tool per turn.
- Extract parameters from the user's message. Ask for clarification only if truly ambiguous.
- After receiving tool results, summarize them concisely. Focus on data, not pleasantries.
- When listing sequences, mention name, size, topology, key features, and resistance markers.
- If no results found, suggest broadening the search or trying BLAST.
- Never fabricate data. Only report what the tools return."""


def build_tool_schemas(registry) -> list[dict]:
    """Convert ToolRegistry into OpenAI function calling format."""
    tools = []
    for tool in registry.all():
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


def build_messages(
    user_input: str,
    history: list[dict] | None = None,
    tool_call: dict | None = None,
    tool_result: str | None = None,
) -> list[dict]:
    """Build the messages array for a chat completion request.

    Args:
        user_input: Current user message.
        history: Previous messages in this chat session.
        tool_call: The assistant's tool_calls response (for follow-up after execution).
        tool_result: Serialized tool output (for follow-up after execution).
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if history:
        messages.extend(history)

    if tool_call and tool_result:
        # Follow-up: assistant called a tool, we executed it, now ask for summary
        messages.append({"role": "assistant", "tool_calls": [tool_call]})
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": tool_result,
        })
    else:
        # Initial turn: user asks a question
        messages.append({"role": "user", "content": user_input})

    return messages
