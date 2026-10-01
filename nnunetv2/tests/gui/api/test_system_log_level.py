from __future__ import annotations


def test_get_log_level_default(client):
    r = client.get("/api/system/log_level")
    assert r.status_code == 200
    body = r.json()
    assert body["level"] in ("DEBUG", "INFO", "WARNING", "ERROR")


def test_put_log_level_round_trip(client):
    r = client.put("/api/system/log_level", json={"level": "DEBUG"})
    assert r.status_code == 200
    assert client.get("/api/system/log_level").json()["level"] == "DEBUG"


def test_put_log_level_rejects_unknown(client):
    r = client.put("/api/system/log_level", json={"level": "BANANAS"})
    assert r.status_code == 400
