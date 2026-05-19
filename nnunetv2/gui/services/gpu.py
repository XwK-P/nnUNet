"""GPU info via pynvml; degrades to [] if pynvml is unavailable or fails."""
from __future__ import annotations


def gpu_info() -> list[dict]:
    try:
        import pynvml  # type: ignore[import-untyped]
    except Exception:
        return []
    try:
        pynvml.nvmlInit()
    except Exception:
        return []
    try:
        out: list[dict] = []
        try:
            count = pynvml.nvmlDeviceGetCount()
        except Exception:
            return []
        for i in range(count):
            try:
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(h)
                if isinstance(name, bytes):
                    name = name.decode("utf-8", errors="replace")
                mem = pynvml.nvmlDeviceGetMemoryInfo(h)
                util = pynvml.nvmlDeviceGetUtilizationRates(h)
                out.append({
                    "index": i,
                    "name": name,
                    "memory_total_mb": int(mem.total / 1024 / 1024),
                    "memory_used_mb": int(mem.used / 1024 / 1024),
                    "util_pct": int(util.gpu),
                })
            except Exception:
                continue
        return out
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
