from __future__ import annotations


def test_env_returns_known_vars(client, monkeypatch):
    monkeypatch.setenv("nnUNet_raw", "/tmp/raw")
    monkeypatch.setenv("nnUNet_preprocessed", "/tmp/pre")
    monkeypatch.setenv("nnUNet_results", "/tmp/res")
    monkeypatch.setenv("nnUNet_n_proc_DA", "8")

    r = client.get("/api/system/env")
    assert r.status_code == 200
    body = r.json()
    names = {v["name"] for v in body["vars"]}
    assert {"nnUNet_raw", "nnUNet_preprocessed", "nnUNet_results"} <= names
    raw = [v for v in body["vars"] if v["name"] == "nnUNet_raw"][0]
    assert raw["value"] == "/tmp/raw"
    assert raw["editable"] is True


def test_env_omits_unrelated_vars(client, monkeypatch):
    monkeypatch.setenv("SOME_SECRET", "shhh")
    r = client.get("/api/system/env")
    names = {v["name"] for v in r.json()["vars"]}
    assert "SOME_SECRET" not in names


def test_env_marks_unset_var_with_null_value(client, monkeypatch):
    monkeypatch.delenv("nnUNet_tb_logdir", raising=False)
    r = client.get("/api/system/env")
    by = {v["name"]: v for v in r.json()["vars"]}
    if "nnUNet_tb_logdir" in by:  # allowlist controls presence
        assert by["nnUNet_tb_logdir"]["value"] is None
