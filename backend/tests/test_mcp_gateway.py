from typing import Any

import pytest
from mcp import Client

from app.database import session_scope
from app.mcp_gateway import mcp_server
from app.models import BusinessSystem, ToolConfig
from app.services.tool_executor import ExecutionResult


class FakeExecutor:
    async def execute(self, tool: ToolConfig, arguments: dict[str, Any]) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            http_status=200,
            duration_ms=5,
            data={"echo": arguments["value"], "tool": tool.name},
        )


def seed_tool() -> None:
    with session_scope() as db:
        system = BusinessSystem(name="测试系统", code="test_system", enabled=True)
        db.add(system)
        db.flush()
        db.add(
            ToolConfig(
                business_system_id=system.id,
                name="echo_value",
                description="回显输入",
                endpoint_url="https://example.com/echo",
                http_method="POST",
                input_schema={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "echo": {"type": "string"},
                        "tool": {"type": "string"},
                    },
                    "required": ["echo", "tool"],
                },
                static_headers={},
                auth_type="none",
                auth_header_name="Authorization",
                enabled=True,
            )
        )


@pytest.mark.asyncio
async def test_database_tools_are_exposed_and_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    seed_tool()
    monkeypatch.setattr("app.mcp_gateway.tool_executor", FakeExecutor())

    async with Client(mcp_server) as client:
        listed = await client.list_tools()
        assert [tool.name for tool in listed.tools] == ["echo_value"]
        assert listed.tools[0].input_schema["required"] == ["value"]

        result = await client.call_tool("echo_value", {"value": "hello"})
        assert result.is_error is False
        assert result.structured_content == {"echo": "hello", "tool": "echo_value"}

