import base64
import ipaddress
import json
import socket
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from jsonschema import Draft202012Validator, ValidationError

from app.config import get_settings
from app.models import ToolConfig
from app.security import secret_cipher


@dataclass(slots=True)
class ExecutionResult:
    success: bool
    http_status: int | None
    duration_ms: int
    data: Any = None
    error: str | None = None


class ToolExecutor:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport
        self._settings = get_settings()

    async def execute(self, tool: ToolConfig, arguments: dict[str, Any]) -> ExecutionResult:
        started_at = time.perf_counter()
        try:
            Draft202012Validator(tool.input_schema).validate(arguments)
            self._validate_target(tool.endpoint_url)
            headers = self._build_headers(tool)
            request_kwargs: dict[str, Any] = {"headers": headers}
            if tool.http_method in {"GET", "DELETE"}:
                request_kwargs["params"] = arguments
            else:
                request_kwargs["json"] = arguments

            async with httpx.AsyncClient(
                timeout=tool.timeout_seconds,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                response = await client.request(tool.http_method, tool.endpoint_url, **request_kwargs)

            data = self._decode_response(response)
            if response.is_error:
                return self._result(
                    started_at,
                    success=False,
                    http_status=response.status_code,
                    data=data,
                    error=f"目标接口返回 HTTP {response.status_code}",
                )

            if tool.output_schema:
                Draft202012Validator(tool.output_schema).validate(data)

            return self._result(
                started_at,
                success=True,
                http_status=response.status_code,
                data=data,
            )
        except ValidationError as exc:
            path = ".".join(str(item) for item in exc.absolute_path) or "根节点"
            return self._result(started_at, False, None, error=f"Schema 校验失败（{path}）：{exc.message}")
        except httpx.TimeoutException:
            return self._result(started_at, False, None, error="目标接口调用超时")
        except httpx.HTTPError as exc:
            return self._result(started_at, False, None, error=f"目标接口请求失败：{exc}")
        except Exception as exc:
            return self._result(started_at, False, None, error=str(exc))

    def _build_headers(self, tool: ToolConfig) -> dict[str, str]:
        headers = dict(tool.static_headers or {})
        if tool.auth_type == "none":
            return headers

        if not tool.auth_secret_ciphertext:
            raise RuntimeError("工具尚未配置认证密钥")

        secret = secret_cipher.decrypt(tool.auth_secret_ciphertext)
        header_name = tool.auth_header_name
        if tool.auth_type == "basic":
            raw = f"{tool.auth_username or ''}:{secret}".encode("utf-8")
            headers[header_name] = f"Basic {base64.b64encode(raw).decode('ascii')}"
        elif tool.auth_type == "bearer":
            headers[header_name] = f"Bearer {secret}"
        elif tool.auth_type == "api_key":
            headers[header_name] = secret
        else:
            raise RuntimeError(f"不支持的认证类型：{tool.auth_type}")
        return headers

    def _validate_target(self, endpoint_url: str) -> None:
        parsed = urlparse(endpoint_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise RuntimeError("目标地址必须是有效的 http 或 https URL")

        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
                raise RuntimeError("目标地址解析到不允许访问的本地或链路地址")
            if ip.is_private and not self._settings.allow_private_targets:
                raise RuntimeError("当前配置禁止访问私有网络地址")

    @staticmethod
    def _decode_response(response: httpx.Response) -> Any:
        content_type = response.headers.get("content-type", "").lower()
        if "json" in content_type:
            return response.json()
        text = response.text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    @staticmethod
    def _result(
        started_at: float,
        success: bool,
        http_status: int | None,
        data: Any = None,
        error: str | None = None,
    ) -> ExecutionResult:
        return ExecutionResult(
            success=success,
            http_status=http_status,
            duration_ms=max(0, round((time.perf_counter() - started_at) * 1000)),
            data=data,
            error=error,
        )


tool_executor = ToolExecutor()

