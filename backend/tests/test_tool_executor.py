from types import SimpleNamespace

import httpx
import pytest

from app.security import secret_cipher
from app.services.tool_executor import ToolExecutor


@pytest.mark.asyncio
async def test_executor_injects_api_key_and_validates_response(monkeypatch: pytest.MonkeyPatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-API-Key"] == "secret-value"
        assert request.headers["X-Tenant"] == "demo"
        assert request.read() == b'{"id":"100"}'
        return httpx.Response(200, json={"name": "demo"})

    executor = ToolExecutor(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(executor, "_validate_target", lambda endpoint_url: None)
    tool = SimpleNamespace(
        input_schema={
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
        output_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        endpoint_url="https://example.com/test",
        http_method="POST",
        timeout_seconds=5,
        static_headers={"X-Tenant": "demo"},
        auth_type="api_key",
        auth_header_name="X-API-Key",
        auth_username=None,
        auth_secret_ciphertext=secret_cipher.encrypt("secret-value"),
    )

    result = await executor.execute(tool, {"id": "100"})

    assert result.success is True
    assert result.http_status == 200
    assert result.data == {"name": "demo"}

