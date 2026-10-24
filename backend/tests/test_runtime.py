def test_request_id_is_generated_and_returned(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert len(response.headers["x-request-id"]) >= 16


def test_safe_request_id_is_preserved(client):
    response = client.get(
        "/api/health",
        headers={"X-Request-ID": "review-request-123"},
    )

    assert response.headers["x-request-id"] == "review-request-123"


def test_unsafe_request_id_is_replaced(client):
    response = client.get(
        "/api/health",
        headers={"X-Request-ID": "bad value\nwith newline"},
    )

    assert response.headers["x-request-id"] != "bad value\nwith newline"
