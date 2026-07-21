from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE = REPO_ROOT / "tools/labutopia_fluid/profiles/isaac41_g0_property_query_experimental.kit"
FORMAL_PREFIX = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310"
)


def test_experimental_g0_property_query_profile_is_pinned_and_fabric_extension_free():
    profile = tomllib.loads(PROFILE.read_text(encoding="utf-8"))

    assert profile["package"]["version"] == "4.1.0"
    assert profile["dependencies"] == {
        "omni.usd": {"version": "1.11.2+106", "exact": True},
        "omni.timeline": {"version": "1.0.10", "exact": True},
        "omni.kit.usd.layers": {"version": "2.1.31", "exact": True},
        "omni.kit.loop-isaac": {"version": "1.2.0", "exact": True},
        "omni.physx": {"version": "106.0.20", "exact": True},
        "omni.physx.stageupdate": {"version": "106.0.20", "exact": True},
    }
    assert "omni.physx.fabric" not in profile["dependencies"]
    assert "omni.physxfabric" not in profile["dependencies"]
    assert all(
        "renderer" not in name
        and "viewport" not in name
        and "replicator" not in name
        for name in profile["dependencies"]
    )

    settings = profile["settings"]
    assert settings["app"]["extensions"]["registryEnabled"] is False
    assert settings["app"]["window"]["hideUi"] is True
    assert settings["app"]["exts"]["folders"] == [
        str(FORMAL_PREFIX / "lib/python3.10/site-packages/isaacsim/exts"),
        str(FORMAL_PREFIX / "lib/python3.10/site-packages/isaacsim/extscache"),
        str(FORMAL_PREFIX / "lib/python3.10/site-packages/isaacsim/extsPhysics"),
        str(FORMAL_PREFIX / "lib/python3.10/site-packages/isaacsim/extsUser"),
        str(FORMAL_PREFIX / "lib/python3.10/site-packages/isaacsim/kit/exts"),
    ]
