from fastapi.testclient import TestClient


ADMIN_HEADERS = {"Authorization": "Bearer test-admin-key"}


def test_tool_configuration_crud_and_secret_redaction(api_client: TestClient) -> None:
    unauthorized = api_client.get("/api/systems")
    assert unauthorized.status_code == 401

    system_response = api_client.post(
        "/api/systems",
        headers=ADMIN_HEADERS,
        json={
            "name": "订单中心",
            "code": "order_center",
            "description": "订单查询与处理",
            "enabled": True,
        },
    )
    assert system_response.status_code == 201
    system_id = system_response.json()["id"]

    tool_response = api_client.post(
        "/api/tools",
        headers=ADMIN_HEADERS,
        json={
            "business_system_id": system_id,
            "name": "order_query",
            "description": "根据订单号查询订单",
            "endpoint_url": "https://example.com/orders/query",
            "http_method": "POST",
            "timeout_seconds": 10,
            "input_schema": {
                "type": "object",
                "properties": {"order_no": {"type": "string"}},
                "required": ["order_no"],
            },
            "output_schema": {
                "type": "object",
                "properties": {"status": {"type": "string"}},
            },
            "static_headers": {"X-Tenant": "demo"},
            "auth_type": "api_key",
            "auth_header_name": "X-API-Key",
            "auth_secret": "top-secret",
            "enabled": True,
        },
    )
    assert tool_response.status_code == 201, tool_response.text
    body = tool_response.json()
    assert body["name"] == "order_query"
    assert body["auth_secret_configured"] is True
    assert "auth_secret" not in body
    assert "auth_secret_ciphertext" not in body

    listed = api_client.get("/api/tools", headers=ADMIN_HEADERS)
    assert listed.status_code == 200
    assert [item["name"] for item in listed.json()] == ["order_query"]


def test_mcp_endpoint_requires_its_own_bearer_token(api_client: TestClient) -> None:
    response = api_client.post("/mcp", json={})
    assert response.status_code == 401

