"""Guard tests for the --gui mode of run_integration_test.sh.

A previous version of the script ran the health probe inside a plain for
loop with no success bookkeeping, so a GUI that never became healthy
(missing dep, port collision, crash-on-start) silently fell through into
the training stage and produced a passing run. These tests pin the
"fail-fast when GUI health probe never becomes ready" behavior.
"""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "integration_tests" / "run_integration_test.sh"


def _make_stub(stub_dir: Path, name: str, body: str) -> None:
    stub = stub_dir / name
    stub.write_text(body)
    stub.chmod(0o755)


def test_gui_mode_exits_nonzero_when_health_probe_never_ready(tmp_path):
    """With a stub `nnUNetv2_gui` that exits immediately, the health
    probe loop must exhaust without success and the script must exit
    non-zero — never reaching `nnUNetv2_train`.
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    # GUI binary "boots" but immediately exits 0 -> no HTTP server, so
    # /api/system/healthz never returns 200 within the probe window.
    _make_stub(
        stub_dir,
        "nnUNetv2_gui",
        "#!/usr/bin/env bash\nexit 0\n",
    )
    # If the train stub ever runs, leave a tombstone so the assertion can
    # surface the regression with a useful diagnostic.
    train_marker = tmp_path / "train_ran"
    _make_stub(
        stub_dir,
        "nnUNetv2_train",
        textwrap.dedent(
            f"""
            #!/usr/bin/env bash
            touch '{train_marker}'
            exit 0
            """
        ).strip()
        + "\n",
    )

    env = os.environ.copy()
    env["PATH"] = f"{stub_dir}{os.pathsep}{env.get('PATH', '')}"
    env.setdefault("nnUNet_results", str(tmp_path / "results"))

    # Bound script wallclock — the script's own probe loop is ~15s.
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--gui", "999"],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert proc.returncode != 0, (
        "script must exit non-zero when GUI health probe never succeeds; "
        f"stdout=\n{proc.stdout}\nstderr=\n{proc.stderr}"
    )
    assert "FAIL" in proc.stdout, (
        f"expected FAIL diagnostic in stdout; got:\n{proc.stdout}"
    )
    assert not train_marker.exists(), (
        "training stage must not be reached when GUI never becomes healthy"
    )
