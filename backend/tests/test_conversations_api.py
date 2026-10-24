def test_conversation_crud_round_trip(auth_client):
    created = auth_client.post("/api/conversations", json={})
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    renamed = auth_client.patch(
        f"/api/conversations/{conversation_id}",
        json={"title": "东煌纪养成对比"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "东煌纪养成对比"

    listed_response = auth_client.get("/api/conversations")
    assert listed_response.status_code == 200
    listed = listed_response.json()
    assert listed[0]["id"] == conversation_id

    assert auth_client.delete(f"/api/conversations/{conversation_id}").status_code == 204
    assert auth_client.get(f"/api/conversations/{conversation_id}").status_code == 404


def test_conversation_title_rejects_blank_value(auth_client):
    created = auth_client.post("/api/conversations", json={}).json()

    response = auth_client.patch(
        f"/api/conversations/{created['id']}",
        json={"title": "   "},
    )

    assert response.status_code == 422


def test_catalog_requires_auth_and_health_is_public(client, auth_client):
    assert client.get("/api/catalog").status_code == 401
    catalog = auth_client.get("/api/catalog")
    health = client.get("/api/health")

    assert catalog.status_code == 200
    assert catalog.json()["documents"] == 4
    assert health.status_code == 200
    assert health.json()["index"]["status"] in {"ready", "legacy"}
