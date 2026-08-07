from __future__ import annotations

from utils import formal_precontact_usd_dependency_closure as closure


def _input() -> dict:
    return closure.build_input(
        v7_config_sha256="a" * 64,
        fixed_mount_profile_sha256="b" * 64,
        approved_runtime_mdl_dependencies=[],
        entries=[
            {
                "role": "fixed_mount_filter_overlay",
                "path": "assets/filter.usda",
                "sha256": "c" * 64,
            },
            {
                "role": "hidden_cube_overlay",
                "path": "assets/hidden.usda",
                "sha256": "d" * 64,
            },
            {
                "role": "local_franka",
                "path": "assets/Franka.usd",
                "sha256": "e" * 64,
            },
            {
                "role": "local_scene",
                "path": "assets/scene.usda",
                "sha256": "f" * 64,
            },
        ],
    )


def test_dependency_manifest_binds_sorted_repo_local_closure():
    input_record = _input()
    manifest = closure.build_manifest(
        input_record=input_record,
        files=[
            {"path": "assets/Franka.usd", "byte_count": 2, "sha256": "e" * 64},
            {"path": "assets/filter.usda", "byte_count": 3, "sha256": "c" * 64},
            {"path": "assets/hidden.usda", "byte_count": 4, "sha256": "d" * 64},
            {"path": "assets/scene.usda", "byte_count": 5, "sha256": "f" * 64},
            {"path": "assets/sub/binary.usd", "byte_count": 6, "sha256": "0" * 64},
        ],
        unresolved=[],
    )

    rebound = closure.rebind_manifest(manifest, expected_input=input_record)

    assert rebound["status"] == closure.PASS
    assert [record["path"] for record in rebound["files"]] == [
        "assets/Franka.usd",
        "assets/filter.usda",
        "assets/hidden.usda",
        "assets/scene.usda",
        "assets/sub/binary.usd",
    ]


def test_dependency_manifest_rejects_unresolved_or_broadened_input():
    input_record = _input()
    manifest = closure.build_manifest(
        input_record=input_record,
        files=[
            {"path": "assets/Franka.usd", "byte_count": 2, "sha256": "e" * 64},
            {"path": "assets/filter.usda", "byte_count": 3, "sha256": "c" * 64},
            {"path": "assets/hidden.usda", "byte_count": 4, "sha256": "d" * 64},
            {"path": "assets/scene.usda", "byte_count": 5, "sha256": "f" * 64},
        ],
        unresolved=["omniverse://unresolved.usd"],
    )

    assert manifest["status"] == closure.NO_GO
    try:
        closure.rebind_manifest(manifest, expected_input=input_record)
    except ValueError as exc:
        assert str(exc) == "formal_usd_dependency_closure_manifest_not_pass"
    else:
        raise AssertionError("unresolved manifest unexpectedly rebound")


def test_dependency_manifest_binds_declared_external_mdl_without_allowing_unknown_paths():
    input_record = closure.build_input(
        v7_config_sha256="a" * 64,
        fixed_mount_profile_sha256="b" * 64,
        approved_runtime_mdl_dependencies=[
            {
                "purpose": "kit_mdl_material_root",
                "path": "/runtime/OmniPBR.mdl",
                "sha256": "1" * 64,
            }
        ],
        entries=_input()["entries"],
    )
    manifest = closure.build_manifest(
        input_record=input_record,
        files=[
            {"path": "assets/Franka.usd", "byte_count": 2, "sha256": "e" * 64},
            {"path": "assets/filter.usda", "byte_count": 3, "sha256": "c" * 64},
            {"path": "assets/hidden.usda", "byte_count": 4, "sha256": "d" * 64},
            {"path": "assets/scene.usda", "byte_count": 5, "sha256": "f" * 64},
        ],
        approved_runtime_mdl_dependencies=[
            {
                "purpose": "kit_mdl_material_root",
                "path": "/runtime/OmniPBR.mdl",
                "byte_count": 6,
                "sha256": "1" * 64,
            }
        ],
        runtime_mdl_closure=[
            {
                "purpose": "kit_mdl_material_root",
                "path": "/runtime/OmniPBR.mdl",
                "byte_count": 6,
                "sha256": "1" * 64,
            },
            {
                "purpose": "kit_mdl_material_dependency",
                "path": "/runtime/OmniPBR_ClearCoat.mdl",
                "byte_count": 7,
                "sha256": "2" * 64,
            },
        ],
        runtime_mdl_builtin_modules=["::base", "::math"],
        unresolved=[],
    )

    rebound = closure.rebind_manifest(manifest, expected_input=input_record)

    assert rebound["approved_runtime_mdl_dependencies"][0]["path"] == "/runtime/OmniPBR.mdl"
    assert [record["path"] for record in rebound["runtime_mdl_closure"]] == [
        "/runtime/OmniPBR.mdl",
        "/runtime/OmniPBR_ClearCoat.mdl",
    ]

    try:
        closure.build_manifest(
            input_record=input_record,
            files=[
                {"path": "assets/Franka.usd", "byte_count": 2, "sha256": "e" * 64},
                {"path": "assets/filter.usda", "byte_count": 3, "sha256": "c" * 64},
                {"path": "assets/hidden.usda", "byte_count": 4, "sha256": "d" * 64},
                {"path": "assets/scene.usda", "byte_count": 5, "sha256": "f" * 64},
            ],
            approved_runtime_mdl_dependencies=[
                {
                    "purpose": "kit_mdl_material_root",
                    "path": "/runtime/OmniPBR.mdl",
                    "byte_count": 6,
                    "sha256": "1" * 64,
                }
            ],
            unresolved=[],
        )
    except ValueError as exc:
        assert str(exc) == "formal_usd_dependency_closure_manifest_invalid"
    else:
        raise AssertionError("runtime MDL root unexpectedly accepted without its closure")


def test_preflight_binding_requires_repo_local_run_and_complete_hash_chain():
    binding = closure.build_preflight_binding(
        preflight_run_dir="artifacts/runs/formal-usd-dependency-preflight-001",
        input_sha256="1" * 64,
        closure_manifest_sha256="2" * 64,
        closure_file_sha256="3" * 64,
        preflight_report_sha256="4" * 64,
        preflight_run_manifest_sha256="5" * 64,
        preflight_runtime_receipt_sha256="6" * 64,
    )

    assert closure.validate_preflight_binding(binding) == binding

    invalid = dict(binding)
    invalid["preflight_run_dir"] = "/tmp/closure"
    try:
        closure.validate_preflight_binding(invalid)
    except ValueError as exc:
        assert str(exc) == "formal_usd_dependency_preflight_binding_invalid"
    else:
        raise AssertionError("absolute preflight directory unexpectedly accepted")
