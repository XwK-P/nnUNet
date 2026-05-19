from __future__ import annotations


def test_gpu_info_returns_list(client):
    r = client.get("/api/system/gpu")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    # Cannot assert non-empty on CI (no GPU); only that the shape is correct.
    for g in body:
        assert {"index", "name", "memory_total_mb", "memory_used_mb", "util_pct"} <= set(g)


def test_gpu_info_no_pynvml_returns_empty(client, monkeypatch):
    import sys
    # Force the inner `import pynvml` to ImportError, regardless of whether
    # pynvml is installed in this environment.
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pynvml":
            raise ImportError("forced for test")
        return real_import(name, globals, locals, fromlist, level)

    # Patch builtins.__import__ so the local import inside gpu_info raises.
    import builtins
    monkeypatch.setattr(builtins, "__import__", fake_import)
    r = client.get("/api/system/gpu")
    assert r.status_code == 200
    assert r.json() == []


def test_gpu_info_nvml_init_failure_returns_empty(client, monkeypatch):
    # If pynvml is present but nvmlInit raises (e.g. no driver), return [].
    import sys
    import types

    fake_mod = types.SimpleNamespace()

    def _raise():
        raise RuntimeError("nvml init fail")

    fake_mod.nvmlInit = _raise
    fake_mod.nvmlShutdown = lambda: None
    monkeypatch.setitem(sys.modules, "pynvml", fake_mod)

    r = client.get("/api/system/gpu")
    assert r.status_code == 200
    assert r.json() == []
