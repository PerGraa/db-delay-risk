"""Parse `claude -p --output-format stream-json --verbose` output into what the checks need."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

MCP_PREFIX = "mcp__db-delay-risk__"


@dataclass
class ToolCall:
    tool: str
    args: dict[str, Any]
    result: dict[str, Any] | None = None
    is_error: bool = False


@dataclass
class Transcript:
    calls: list[ToolCall] = field(default_factory=list)
    answer: str = ""
    cost_usd: float = 0.0
    turns: int = 0
    is_error: bool = False
    tokens: dict[str, int] = field(default_factory=dict)
    duration_s: float = 0.0

    @classmethod
    def parse(cls, text: str) -> Transcript:
        t = cls()
        by_id: dict[str, ToolCall] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue  # the CLI may print warnings around the JSON lines
            event = json.loads(line)
            if event.get("type") == "result":
                t.answer = event.get("result") or ""
                t.cost_usd = float(event.get("total_cost_usd") or 0)
                t.turns = int(event.get("num_turns") or 0)
                t.is_error = bool(event.get("is_error"))
                t.duration_s = float(event.get("duration_ms") or 0) / 1000
                usage = event.get("usage") or {}
                t.tokens = {
                    "input": int(usage.get("input_tokens") or 0),
                    "output": int(usage.get("output_tokens") or 0),
                    "cache_read": int(usage.get("cache_read_input_tokens") or 0),
                    "cache_write": int(usage.get("cache_creation_input_tokens") or 0),
                }
                continue
            message = event.get("message")
            if not isinstance(message, dict):
                continue
            for block in message.get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    call = ToolCall(
                        tool=block["name"].removeprefix(MCP_PREFIX), args=block.get("input") or {}
                    )
                    by_id[block["id"]] = call
                    t.calls.append(call)
                elif block.get("type") == "tool_result" and block.get("tool_use_id") in by_id:
                    call = by_id[block["tool_use_id"]]
                    call.is_error = bool(block.get("is_error"))
                    call.result = _json_or_none(block.get("content"))
        return t

    def all_route_options(self) -> list[dict[str, Any]]:
        """Options from every successful route_options call (comparison questions make several)."""
        return [
            o
            for call in self.calls
            if call.tool == "route_options" and call.result and "options" in call.result
            for o in call.result["options"]
        ]

    def route_options(self) -> list[dict[str, Any]]:
        """Options from the last successful route_options call, or [] if there was none."""
        for call in reversed(self.calls):
            if call.tool == "route_options" and call.result and "options" in call.result:
                return list(call.result["options"])
        return []


def _json_or_none(content: Any) -> dict[str, Any] | None:
    if isinstance(content, list):  # [{"type": "text", "text": "..."}]
        content = "".join(c.get("text", "") for c in content if isinstance(c, dict))
    if not isinstance(content, str):
        return None
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
