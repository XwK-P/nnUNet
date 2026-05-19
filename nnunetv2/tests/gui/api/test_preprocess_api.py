from __future__ import annotations


def test_preprocess_dry_run_returns_argv(populated_client):
    r = populated_client.post(
        "/api/preprocess?dry_run=true",
        json={"dataset_id": 27, "verify_dataset_integrity": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["argv"][:2] == ["nnUNetv2_plan_and_preprocess", "-d"]
    assert "27" in body["argv"]
    assert "--verify_dataset_integrity" in body["argv"]
    assert body["cli"].startswith("nnUNetv2_plan_and_preprocess")
    assert "job_id" not in body  # dry-run doesn't enqueue


def test_preprocess_enqueue_creates_job(populated_client, monkeypatch):
    # Avoid spawning the real `nnUNetv2_plan_and_preprocess` (slow);
    # patch the renderer to a short sleep instead.
    import sys
    fake_argv = [sys.executable, "-m", "nnunetv2.tests.gui.helpers.sleep_helper", "0.05", "0"]
    monkeypatch.setattr(
        "nnunetv2.gui.routers.preprocess.render_preprocess",
        lambda req: fake_argv,
    )
    r = populated_client.post("/api/preprocess", json={"dataset_id": 27})
    assert r.status_code == 201
    body = r.json()
    assert "job_id" in body
    assert body["argv"] == fake_argv


def test_preprocess_validation_error(populated_client):
    r = populated_client.post("/api/preprocess", json={})
    assert r.status_code == 422  # FastAPI validation


def test_preprocess_with_planner_dry_run(populated_client):
    r = populated_client.post(
        "/api/preprocess?dry_run=true",
        json={"dataset_id": 27, "planner": "nnUNetPlannerResEncL"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "-pl" in body["argv"] and "nnUNetPlannerResEncL" in body["argv"]
