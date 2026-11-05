from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import AuditLog, BusinessSystem, ToolConfig
from app.schemas import (
    AuditLogRead,
    BusinessSystemPayload,
    BusinessSystemRead,
    StatusPayload,
    ToolExecutionRead,
    ToolPayload,
    ToolRead,
    ToolTestRequest,
)
from app.security import require_admin, secret_cipher
from app.services.tool_executor import tool_executor


router = APIRouter(
    prefix="/api",
    dependencies=[Depends(require_admin)],
)

DbSession = Annotated[Session, Depends(get_db)]


def _system_read(system: BusinessSystem, tool_count: int) -> BusinessSystemRead:
    return BusinessSystemRead(
        id=system.id,
        name=system.name,
        code=system.code,
        description=system.description,
        enabled=system.enabled,
        tool_count=tool_count,
        created_at=system.created_at,
        updated_at=system.updated_at,
    )


def _tool_read(tool: ToolConfig) -> ToolRead:
    return ToolRead(
        id=tool.id,
        business_system_id=tool.business_system_id,
        business_system_name=tool.business_system.name,
        name=tool.name,
        description=tool.description,
        endpoint_url=tool.endpoint_url,
        http_method=tool.http_method,
        timeout_seconds=tool.timeout_seconds,
        input_schema=tool.input_schema,
        output_schema=tool.output_schema,
        static_headers=tool.static_headers or {},
        auth_type=tool.auth_type,
        auth_header_name=tool.auth_header_name,
        auth_username=tool.auth_username,
        auth_secret_configured=bool(tool.auth_secret_ciphertext),
        enabled=tool.enabled,
        created_at=tool.created_at,
        updated_at=tool.updated_at,
    )


def _get_system(db: Session, system_id: int) -> BusinessSystem:
    system = db.get(BusinessSystem, system_id)
    if system is None:
        raise HTTPException(status_code=404, detail="业务系统不存在")
    return system


def _get_tool(db: Session, tool_id: int) -> ToolConfig:
    tool = db.scalar(
        select(ToolConfig)
        .where(ToolConfig.id == tool_id)
        .options(selectinload(ToolConfig.business_system))
    )
    if tool is None:
        raise HTTPException(status_code=404, detail="工具不存在")
    return tool


def _commit(db: Session, duplicate_message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=duplicate_message) from exc


@router.get("/systems", response_model=list[BusinessSystemRead])
def list_systems(db: DbSession) -> list[BusinessSystemRead]:
    rows = db.execute(
        select(BusinessSystem, func.count(ToolConfig.id))
        .outerjoin(ToolConfig, ToolConfig.business_system_id == BusinessSystem.id)
        .group_by(BusinessSystem.id)
        .order_by(BusinessSystem.id.desc())
    ).all()
    return [_system_read(system, tool_count) for system, tool_count in rows]


@router.post("/systems", response_model=BusinessSystemRead, status_code=status.HTTP_201_CREATED)
def create_system(payload: BusinessSystemPayload, db: DbSession) -> BusinessSystemRead:
    system = BusinessSystem(**payload.model_dump())
    db.add(system)
    _commit(db, "业务系统名称或编码已存在")
    db.refresh(system)
    return _system_read(system, 0)


@router.put("/systems/{system_id}", response_model=BusinessSystemRead)
def update_system(system_id: int, payload: BusinessSystemPayload, db: DbSession) -> BusinessSystemRead:
    system = _get_system(db, system_id)
    for field, value in payload.model_dump().items():
        setattr(system, field, value)
    _commit(db, "业务系统名称或编码已存在")
    tool_count = db.scalar(select(func.count()).select_from(ToolConfig).where(ToolConfig.business_system_id == system.id))
    return _system_read(system, int(tool_count or 0))


@router.patch("/systems/{system_id}/status", response_model=BusinessSystemRead)
def update_system_status(system_id: int, payload: StatusPayload, db: DbSession) -> BusinessSystemRead:
    system = _get_system(db, system_id)
    system.enabled = payload.enabled
    db.commit()
    tool_count = db.scalar(select(func.count()).select_from(ToolConfig).where(ToolConfig.business_system_id == system.id))
    return _system_read(system, int(tool_count or 0))


@router.delete("/systems/{system_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_system(system_id: int, db: DbSession) -> None:
    system = _get_system(db, system_id)
    tool_count = db.scalar(select(func.count()).select_from(ToolConfig).where(ToolConfig.business_system_id == system.id))
    if tool_count:
        raise HTTPException(status_code=409, detail="请先删除该业务系统下的工具")
    db.delete(system)
    db.commit()


@router.get("/tools", response_model=list[ToolRead])
def list_tools(db: DbSession) -> list[ToolRead]:
    tools = db.scalars(
        select(ToolConfig)
        .options(selectinload(ToolConfig.business_system))
        .order_by(ToolConfig.id.desc())
    ).all()
    return [_tool_read(tool) for tool in tools]


def _apply_tool_payload(tool: ToolConfig, payload: ToolPayload, *, creating: bool) -> None:
    values = payload.model_dump(exclude={"auth_secret"})
    previous_auth_type = tool.auth_type
    for field, value in values.items():
        setattr(tool, field, value)

    if payload.auth_type == "none":
        tool.auth_secret_ciphertext = None
        tool.auth_username = None
        return

    if payload.auth_secret:
        tool.auth_secret_ciphertext = secret_cipher.encrypt(payload.auth_secret)
    elif creating or previous_auth_type != payload.auth_type or not tool.auth_secret_ciphertext:
        raise HTTPException(status_code=422, detail="启用或切换认证类型时必须填写认证密钥")


@router.post("/tools", response_model=ToolRead, status_code=status.HTTP_201_CREATED)
def create_tool(payload: ToolPayload, db: DbSession) -> ToolRead:
    _get_system(db, payload.business_system_id)
    tool = ToolConfig(
        business_system_id=payload.business_system_id,
        name=payload.name,
        description=payload.description,
        endpoint_url=payload.endpoint_url,
        input_schema=payload.input_schema,
    )
    _apply_tool_payload(tool, payload, creating=True)
    db.add(tool)
    _commit(db, "工具名称已存在")
    return _tool_read(_get_tool(db, tool.id))


@router.put("/tools/{tool_id}", response_model=ToolRead)
def update_tool(tool_id: int, payload: ToolPayload, db: DbSession) -> ToolRead:
    tool = _get_tool(db, tool_id)
    _get_system(db, payload.business_system_id)
    _apply_tool_payload(tool, payload, creating=False)
    _commit(db, "工具名称已存在")
    return _tool_read(_get_tool(db, tool.id))


@router.patch("/tools/{tool_id}/status", response_model=ToolRead)
def update_tool_status(tool_id: int, payload: StatusPayload, db: DbSession) -> ToolRead:
    tool = _get_tool(db, tool_id)
    tool.enabled = payload.enabled
    db.commit()
    return _tool_read(tool)


@router.delete("/tools/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tool(tool_id: int, db: DbSession) -> None:
    tool = _get_tool(db, tool_id)
    db.delete(tool)
    db.commit()


@router.post("/tools/{tool_id}/test", response_model=ToolExecutionRead)
async def test_tool(tool_id: int, payload: ToolTestRequest, db: DbSession) -> ToolExecutionRead:
    tool = _get_tool(db, tool_id)
    result = await tool_executor.execute(tool, payload.arguments)
    db.add(
        AuditLog(
            tool_id=tool.id,
            tool_name=tool.name,
            source="console_test",
            success=result.success,
            http_status=result.http_status,
            duration_ms=result.duration_ms,
            argument_keys=sorted(payload.arguments.keys()),
            error_message=result.error,
        )
    )
    db.commit()
    return ToolExecutionRead(
        success=result.success,
        http_status=result.http_status,
        duration_ms=result.duration_ms,
        data=result.data,
        error=result.error,
    )


@router.get("/audit-logs", response_model=list[AuditLogRead])
def list_audit_logs(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)).all())

