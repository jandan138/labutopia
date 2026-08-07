#!/usr/bin/env python3
"""Attest Isaac 6.0.1 and run the experimental RTX render bridge."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main(argv: Sequence[str] | None = None) -> int:
    from tools.labutopia_fluid import attest_experimental_fluid_runtime as attestation
    from tools.labutopia_fluid import run_isaac601_newton_render_bridge as bridge
    from tools.labutopia_fluid.run_isaac601_wcsph_attested_child import (
        _lock_record,
        _write_fresh_json,
    )

    parser = bridge.build_parser()
    parser.add_argument("--lock-manifest", type=Path, required=True)
    parser.add_argument("--runtime-receipt", type=Path, required=True)
    parser.add_argument("--child-failure", type=Path, required=True)
    args = parser.parse_args(argv)
    bridge._apply_render_profile(args)
    application: Any | None = None
    try:
        receipt = attestation._base_receipt("isaacsim601_wcsph_r1")
        driver = attestation._isaac_driver_preflight(
            allow_unvalidated_driver=args.allow_unvalidated_driver
        )
        receipt["driver_preflight"] = driver
        application = attestation._attest_isaac(
            receipt,
            allow_unvalidated_driver=args.allow_unvalidated_driver,
            width=args.width,
            height=args.height,
            renderer=args.renderer,
            minimal_shading_mode=args.minimal_shading_mode,
        )
        receipt["capabilities"] = {
            "physics": {
                "status": "passed",
                "claim": "isaac_kit_newton_warp_same_process_available",
            },
            "rtx": {
                "status": (
                    "passed"
                    if driver["isaac601_rtx_supported"]
                    else "unvalidated_override_enabled"
                    if args.allow_unvalidated_driver
                    else "blocked_driver"
                ),
                "blocker": (
                    None
                    if driver["isaac601_rtx_supported"]
                    or args.allow_unvalidated_driver
                    else "isaac601_rtx_driver_unsupported"
                ),
                "formal_evidence_eligible": False,
            },
        }
        receipt["environment_lock"] = _lock_record(args.lock_manifest)
        receipt["status"] = "passed"
        receipt["content_sha256"] = attestation._canonical_sha256(receipt)
        receipt_path = args.runtime_receipt.resolve()
        _write_fresh_json(receipt_path, receipt)
        bridge.run(
            args,
            application=application,
            runtime_record={
                "lane": "experimental_isaac601_unvalidated_driver_rtx",
                "receipt_path": str(receipt_path),
                "receipt_sha256": bridge._sha256_file(receipt_path),
                "receipt_content_sha256": receipt["content_sha256"],
                "formal_evidence_eligible": False,
            },
        )
        return 0
    except BaseException as error:
        failure = {
            "schema": "labutopia.isaac601_rtx_render_child_failure.v1",
            "status": "blocked_or_failed_experimental_runtime",
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
            "executable": sys.executable,
            "prefix": sys.prefix,
            "allow_unvalidated_driver": bool(
                getattr(args, "allow_unvalidated_driver", False)
            ),
        }
        try:
            _write_fresh_json(args.child_failure.resolve(), failure)
        except Exception:
            print(json.dumps(failure, sort_keys=True), flush=True)
        return 2
    finally:
        if application is not None:
            application.close()


if __name__ == "__main__":
    raise SystemExit(main())
