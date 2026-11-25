def test_health_is_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_reports_version(client):
    response = client.get("/health")
    assert response.json()["version"] == "dev"


def test_list_documents(client):
    response = client.get("/v1/documents")
    assert response.status_code == 200
    assert response.json()["total"] == 3


def test_list_response_shape(client):
    data = client.get("/v1/documents").json()
    assert set(data.keys()) == {"items", "total", "filters"}


def test_limit(client):
    response = client.get("/v1/documents?limit=1")
    assert len(response.json()["items"]) == 1


def test_offset(client):
    response = client.get("/v1/documents?offset=1")
    assert len(response.json()["items"]) == 2


def test_search_alpha(client):
    response = client.get("/v1/documents?q=Alpha")
    assert response.json()["total"] == 1


def test_search_case_insensitive(client):
    response = client.get("/v1/documents?q=alpha")
    assert response.json()["total"] == 1


def test_search_no_match(client):
    response = client.get("/v1/documents?q=unknown")
    assert response.json()["total"] == 0


def test_year_filter(client):
    response = client.get("/v1/documents?year=2024")
    assert response.json()["total"] == 1


def test_filter_no_match(client):
    response = client.get("/v1/documents?year=2030")
    assert response.json()["total"] == 0


def test_multiple_filters(client):
    response = client.get("/v1/documents?year=2023&id=001")
    assert response.json()["total"] == 1


def test_invalid_filter(client):
    response = client.get("/v1/documents?Bad-Name=1")
    assert response.status_code == 400


def test_invalid_limit(client):
    response = client.get("/v1/documents?limit=0")
    assert response.status_code == 422


def test_invalid_offset(client):
    response = client.get("/v1/documents?offset=-1")
    assert response.status_code == 422


def test_get_existing_document(client):
    response = client.get("/v1/documents/001")
    assert response.status_code == 200
    assert response.json()["title"] == "Alpha guideline"


def test_get_missing_document(client):
    response = client.get("/v1/documents/999")
    assert response.status_code == 404


def test_chat_non_streaming(client):
    response = client.post(
        "/v1/chat",
        json={"message": "What is GlucoLit?", "stream": False},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "GlucoLit test answer"
    assert "usage" in response.json()


def test_chat_streaming(client):
    response = client.post(
        "/v1/chat",
        json={"message": "Hello", "stream": True},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "GlucoLit " in response.text
    assert '"delta": "test "' in response.text
    assert '"delta": "answer "' in response.text
    assert "event: done" in response.text


def test_chat_empty_message(client):
    response = client.post(
        "/v1/chat",
        json={"message": "", "stream": False},
    )

    assert response.status_code == 422


def test_usage_endpoint(client):
    response = client.get("/v1/usage")

    assert response.status_code == 200
    data = response.json()
    assert data["calls"] == 2
    assert data["total_cost_inr"] == 0.0123
    assert len(data["days"]) == 1


def test_usage_custom_days(client):
    response = client.get("/v1/usage?days=30")

    assert response.status_code == 200


def test_usage_invalid_days(client):
    response = client.get("/v1/usage?days=100")

    assert response.status_code == 422
