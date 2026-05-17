from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from nnunetv2.gui.config import GuiConfig
from nnunetv2.gui.server import create_app


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nnUNetv2_gui",
        description="Launch the nnU-Net experiment & dataset manager.",
    )
    p.add_argument("--host", default="127.0.0.1",
                   help="Bind host (default: 127.0.0.1). Non-loopback requires --token.")
    p.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    p.add_argument("--token", default=None,
                   help="Bearer token required for non-loopback binds.")
    p.add_argument("--raw", type=Path, default=None,
                   help="Override $nnUNet_raw")
    p.add_argument("--preprocessed", type=Path, default=None,
                   help="Override $nnUNet_preprocessed")
    p.add_argument("--results", type=Path, default=None,
                   help="Override $nnUNet_results")
    p.add_argument("--open", action="store_true",
                   help="Open the GUI in the default browser after startup.")
    return p


def _make_app_from_args(args: argparse.Namespace) -> FastAPI:
    cfg = GuiConfig.from_env_and_args(
        host=args.host,
        port=args.port,
        token=args.token,
        raw_override=args.raw,
        preprocessed_override=args.preprocessed,
        results_override=args.results,
    )
    return create_app(cfg)


def main(argv: list[str] | None = None) -> int:
    import uvicorn

    args = build_parser().parse_args(argv)
    app = _make_app_from_args(args)
    if args.open:
        url = f"http://{args.host}:{args.port}"
        webbrowser.open(url)

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
