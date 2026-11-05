import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import session_scope
from app.models import AuditLog, BusinessSystem, ToolConfig
from app.services.tool_executor import tool_executor
from mcp.server import Server, ServerRequestContext
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)


async def list_tools(
    ctx: ServerRequestContext,
    params: PaginatedRequestParams | None,
) -> ListToolsResult:
    del ctx, params
    with session_scope() as db:
        tools = db.scalars(
            select(ToolConfig)
            .join(BusinessSystem)
            .where(ToolConfig.enabled.is_(True), BusinessSystem.enabled.is_(True))
            .order_by(ToolConfig.name)
        ).all()
        return ListToolsResult(
            tools=[
                Tool(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                    output_schema=tool.output_schema,
                )
                for tool in tools
            ]
        )


async def call_tool(
    ctx: ServerRequestContext,
    params: CallToolRequestParams,
) -> CallToolResult:
    del ctx
    arguments = params.arguments or {}
    with session_scope() as db:
        tool = db.scalar(
            select(ToolConfig)
            .options(selectinload(ToolConfig.business_system))
            .where(ToolConfig.name == params.name)
        )
        if tool is None or not tool.enabled or not tool.business_system.enabled:
            return _error_result(f"工具不存在或已停用：{params.name}")

        result = await tool_executor.execute(tool, arguments)
        db.add(
            AuditLog(
                tool_id=tool.id,
                tool_name=tool.name,
                source="mcp",
                success=result.success,
                http_status=result.http_status,
                duration_ms=result.duration_ms,
                argument_keys=sorted(arguments.keys()),
                error_message=result.error,
            )
        )

        if not result.success:
            return _error_result(result.error or "工具调用失败", result.data)

        text = _to_text(result.data)
        structured_content = result.data if isinstance(result.data, dict) else None
        return CallToolResult(
            content=[TextContent(type="text", text=text)],
            structured_content=structured_content,
            is_error=False,
        )


def _error_result(message: str, data: Any = None) -> CallToolResult:
    detail = message if data is None else f"{message}\n{_to_text(data)}"
    return CallToolResult(
        content=[TextContent(type="text", text=detail)],
        is_error=True,
    )


def _to_text(data: Any) -> str:
    if isinstance(data, str):
        return data
    return json.dumps(data, ensure_ascii=False, indent=2)


mcp_server = Server(
    "enterprise-mcp-gateway",
    version="0.1.0",
    on_list_tools=list_tools,
    on_call_tool=call_tool,
)

