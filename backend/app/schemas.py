from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


TOOL_NAME_PATTERN = r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$"
SYSTEM_CODE_PATTERN = r"^[a-z][a-z0-9_-]{1,49}$"


class BusinessSystemPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(pattern=SYSTEM_CODE_PATTERN)
    description: str = Field(default="", max_length=2000)
    enabled: bool = True


class BusinessSystemRead(BusinessSystemPayload):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tool_count: int = 0
    created_at: datetime
    updated_at: datetime


class ToolPayload(BaseModel):
    business_system_id: int
    name: str = Field(pattern=TOOL_NAME_PATTERN)
    description: str = Field(min_length=1, max_length=4000)
    endpoint_url: str = Field(min_length=1, max_length=1000)
    http_method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "POST"
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    input_schema: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )
    output_schema: dict[str, Any] | None = None
    static_headers: dict[str, str] = Field(default_factory=dict)
    auth_type: Literal["none", "basic", "bearer", "api_key"] = "none"
    auth_header_name: str = Field(default="Authorization", max_length=100)
    auth_username: str | None = Field(default=None, max_length=200)
    auth_secret: str | None = Field(default=None, max_length=4000)
    enabled: bool = True

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("端点地址必须是有效的 http 或 https URL")
        if parsed.username or parsed.password:
            raise ValueError("端点地址不能包含用户名或密码")
        return value

    @field_validator("input_schema")
    @classmethod
    def validate_input_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        Draft202012Validator.check_schema(value)
        if value.get("type") != "object":
            raise ValueError("入参 Schema 顶层 type 必须是 object")
        return value

    @field_validator("output_schema")
    @classmethod
    def validate_output_schema(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value:
            Draft202012Validator.check_schema(value)
            if value.get("type") != "object":
                raise ValueError("出参 Schema 顶层 type 必须是 object，以便作为 MCP structuredContent 返回")
        return value

    @field_validator("static_headers")
    @classmethod
    def validate_static_headers(cls, value: dict[str, str]) -> dict[str, str]:
        lowered = {name.lower() for name in value}
        if "host" in lowered or "content-length" in lowered:
            raise ValueError("静态 Header 不能设置 Host 或 Content-Length")
        return value

    @model_validator(mode="after")
    def validate_auth_fields(self) -> "ToolPayload":
        if self.auth_type != "none" and not self.auth_header_name.strip():
            raise ValueError("启用认证时必须指定 Header 名称")
        if self.auth_type == "basic" and not (self.auth_username or "").strip():
            raise ValueError("Basic 认证必须填写用户名")
        return self


class ToolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_system_id: int
    business_system_name: str
    name: str
    description: str
    endpoint_url: str
    http_method: str
    timeout_seconds: int
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    static_headers: dict[str, str]
    auth_type: str
    auth_header_name: str
    auth_username: str | None
    auth_secret_configured: bool
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ToolTestRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class StatusPayload(BaseModel):
    enabled: bool


class ToolExecutionRead(BaseModel):
    success: bool
    http_status: int | None
    duration_ms: int
    data: Any = None
    error: str | None = None


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tool_id: int | None
    tool_name: str
    source: str
    success: bool
    http_status: int | None
    duration_ms: int
    argument_keys: list[str]
    error_message: str | None
    created_at: datetime

