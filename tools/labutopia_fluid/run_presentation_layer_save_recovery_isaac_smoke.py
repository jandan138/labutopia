#!/usr/bin/env python3
"""Isaac 4.1 smoke for the presentation-layer save recovery lifecycle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-json", default=None)
    args = parser.parse_args()

    from isaacsim import SimulationApp

    app = SimulationApp({"headless": True})
    root = Path(tempfile.mkdtemp(prefix="labutopia-004-isaac-smoke-", dir="/tmp"))
    try:
        from pxr import Usd, UsdGeom

        from tools.labutopia_fluid import run_real_beaker_omniglass_replay as replay

        source = root / "source.usda"
        source_stage = Usd.Stage.CreateNew(str(source))
        UsdGeom.Xform.Define(source_stage, "/World")
        UsdGeom.Cube.Define(source_stage, "/World/SourceTable")
        source_stage.GetRootLayer().Save()
        source_bytes = source.read_bytes()
        del source_stage

        previous_umask = os.umask(0o077)
        try:
            stage = Usd.Stage.Open(str(source))
            session = replay.snapshot_session_layer(stage)
            presentation_path = root / "presentation.usda"
            presentation = replay.begin_candidate_presentation_layer(
                stage,
                presentation_path,
            )
            presentation_mode_before_save = stat.S_IMODE(
                presentation_path.stat().st_mode
            )
            UsdGeom.Sphere.Define(
                stage,
                "/World/CompletedPBD/PresentationSurface",
            )
            stage.GetRootLayer().SetPermissionToEdit(False)
            stage.GetRootLayer().SetPermissionToSave(False)

            exported = replay.export_static_candidate_entry(
                stage,
                presentation_layer=presentation,
                session_layer_baseline=session,
                source_usd_path=source,
                expected_source_sha256=hashlib.sha256(source_bytes).hexdigest(),
                expected_presentation_path=presentation_path,
                static_usd_path=root / "static.usda",
                required_presentation_prim_path=(
                    "/World/CompletedPBD/PresentationSurface"
                ),
                required_source_prim_path="/World/SourceTable",
            )
            recovery = (
                replay.validate_presentation_layer_export_permission_recovery_contract(
                    exported["presentation_layer_export_permission_recovery"]
                )
            )
            static_path = Path(exported["static_entry_path"])
            capture = Usd.Stage.Open(str(static_path))
            frame = replay.begin_disposable_capture_frame_layer(
                capture,
                candidate_id="OMNI_REF_FINE",
            )
            locked = replay.lock_capture_persistent_layers(
                capture,
                frame_layer=frame,
                expected_baseline=exported["capture_persistent_layer_baseline"],
            )
            verified = replay.verify_capture_persistent_layers_unchanged(
                capture,
                locked,
            )
        finally:
            os.umask(previous_umask)
        result = {
            "baseline_verified": locked["expected_baseline_verified"],
            "capture_verified": verified["verified"],
            "persistent_layer_count": verified["persistent_layer_count"],
            "presentation_mode_before_save": oct(presentation_mode_before_save),
            "presentation_mode_after_save": oct(
                stat.S_IMODE(presentation_path.stat().st_mode)
            ),
            "static_mode_after_save": oct(
                stat.S_IMODE(static_path.stat().st_mode)
            ),
            "recovery_status": recovery["status"],
            "recovery_attempted": recovery["recovery_attempted"],
            "set_edit_attempted": recovery["set_edit_attempted"],
            "set_save_attempted": recovery["set_save_attempted"],
            "relock_succeeded": recovery["relock_succeeded"],
            "save_attempted": recovery["save_attempted"],
            "save_succeeded": recovery["save_succeeded"],
            "source_locked_after_save": recovery["source_permissions"][
                "after_relock"
            ]
            == {"permission_to_edit": False, "permission_to_save": False},
            "source_unchanged": source.read_bytes() == source_bytes,
        }
        expected = {
            "baseline_verified": True,
            "capture_verified": True,
            "persistent_layer_count": 3,
            "presentation_mode_before_save": "0o600",
            "presentation_mode_after_save": "0o600",
            "static_mode_after_save": "0o600",
            "recovery_status": "PASS",
            "recovery_attempted": False,
            "set_edit_attempted": False,
            "set_save_attempted": False,
            "relock_succeeded": True,
            "save_attempted": True,
            "save_succeeded": True,
            "source_locked_after_save": True,
            "source_unchanged": True,
        }
        if result != expected:
            raise RuntimeError(f"isaac_smoke_result_mismatch:{result}")
        if args.result_json is not None:
            target = Path(args.result_json).expanduser().resolve()
            if target.exists() or target.is_symlink():
                raise FileExistsError(target)
            target.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print("LABUTOPIA_SMOKE=" + json.dumps(result, sort_keys=True), flush=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
