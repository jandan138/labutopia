from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from tools.labutopia_fluid import run_formal_precontact_event0_replay as runner


REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE = REPO_ROOT / "config/formal_precontact_fixed_mount_filter_v1.json"


def test_fixed_mount_replay_requires_a_dependency_preflight_run():
    with TemporaryDirectory(dir="/tmp/opencode") as directory:
        out_dir = Path(directory) / "formal"
        try:
            runner.parse_args(
                [
                    "--out-dir",
                    str(out_dir),
                    "--snapshot-v2",
                    "--fixed-mount-profile",
                    str(PROFILE),
                ]
            )
        except SystemExit:
            return
        raise AssertionError("fixed-mount replay unexpectedly accepted no preflight run")


def test_fixed_mount_replay_accepts_a_dependency_preflight_run():
    with TemporaryDirectory(dir="/tmp/opencode") as directory:
        root = Path(directory)
        preflight = root / "preflight"
        preflight.mkdir()

        args = runner.parse_args(
            [
                "--out-dir",
                str(root / "formal"),
                "--snapshot-v2",
                "--fixed-mount-profile",
                str(PROFILE),
                "--usd-dependency-preflight-dir",
                str(preflight),
            ]
        )

        assert args.usd_dependency_preflight_dir == preflight.resolve()
