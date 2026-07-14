from pathlib import Path

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _module():
    from tools.labutopia_fluid import run_interndata_surface_replay as replay

    return replay


def _tetra(scale=1.0, offset=(0.0, 0.0, 0.0)):
    vertices = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [scale, 0.0, 0.0],
            [0.0, scale, 0.0],
            [0.0, 0.0, scale],
        ],
        dtype=np.float32,
    )
    vertices += np.asarray(offset, dtype=np.float32)
    faces = np.asarray(
        [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], dtype=np.int32
    )
    normals = np.zeros_like(vertices)
    normals[:, 2] = 1.0
    return vertices, faces, normals


def _stage_with_legacy_liquid():
    from pxr import Sdf, Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    source = UsdGeom.Xform.Define(stage, "/World/beaker2")
    source.AddTransformOp()
    scope = UsdGeom.Xform.Define(stage, "/World/InternDataParityFluid")
    system = UsdGeom.Xform.Define(
        stage, "/World/InternDataParityFluid/ParticleSystem"
    ).GetPrim()
    system.CreateAttribute(
        "physxParticleIsosurface:isosurfaceEnabled",
        Sdf.ValueTypeNames.Bool,
        custom=True,
    ).Set(True)
    UsdGeom.Points.Define(stage, "/World/InternDataParityFluid/Particles")
    UsdGeom.Points.Define(stage, "/World/InternDataParityFluid/VisualParticles")
    UsdGeom.Points.Define(stage, "/World/ParticleSet")
    UsdGeom.Points.Define(stage, "/World/fluid")
    UsdGeom.Mesh.Define(
        stage,
        "/World/InternDataParityFluid/ParticleSystem/GeneratedIsosurface",
    )
    UsdGeom.Camera.Define(stage, "/World/InternDataParityCloseupCamera")
    assert scope
    return stage


def test_replay_contract_is_fixed_cache_only_and_5x_decimated():
    replay = _module()

    contract = replay.build_replay_contract()

    assert contract["surface_path"] == "/World/InternDataSurfaceReplay"
    assert contract["source_beaker_path"] == "/World/beaker2"
    assert contract["camera_paths"] == {
        "context": "/World/InternDataParityCamera",
        "closeup": "/World/InternDataParityCloseupCamera",
    }
    assert contract["legacy_liquid_paths"] == [
        "/World/InternDataParityFluid/Particles",
        "/World/InternDataParityFluid/VisualParticles",
        "/World/ParticleSet",
        "/World/fluid",
    ]
    assert contract["selected_steps"] == list(range(0, 691, 10))
    assert contract["frame_count"] == 70
    assert contract["width"] == 960
    assert contract["height"] == 540
    assert contract["video_fps"] == 15
    assert contract["physics_trace_hz"] == 30
    assert contract["frame_stride"] == 10
    assert contract["playback_speed_multiplier"] == pytest.approx(5.0)
    assert contract["physics_step_calls"] == 0
    assert contract["dynamic_authority"] == "mesh_cache_plus_replay_runner"
    assert contract["usd_delivery"] == "static_final_state_snapshot"


def test_public_intern_data_material_contract_is_exact_and_has_no_fallback():
    replay = _module()

    material = replay.build_surface_material_contract()

    assert material == {
        "schema_version": 1,
        "material_path": "/World/Looks/InternDataDerivedSurfaceWater",
        "shader_backend": "UsdPreviewSurface",
        "diffuse_color": [0.46, 0.82, 0.96],
        "emissive_color": [0.01, 0.025, 0.035],
        "metallic": pytest.approx(0.0),
        "roughness": pytest.approx(0.06),
        "opacity": pytest.approx(0.06),
        "ior": pytest.approx(1.333),
        "fallback_allowed": False,
        "reference": "accepted_interndata_point_video_material",
    }


def test_surface_mesh_updates_all_topology_normals_and_extent_atomically():
    replay = _module()
    from pxr import UsdGeom

    stage = _stage_with_legacy_liquid()
    vertices1, faces1, normals1 = _tetra(scale=0.01)
    vertices2, faces2, normals2 = _tetra(scale=0.02, offset=(0.1, 0.2, 0.3))

    first = replay.update_surface_mesh(stage, vertices1, faces1, normals1)
    second = replay.update_surface_mesh(stage, vertices2, faces2, normals2)

    mesh = UsdGeom.Mesh(stage.GetPrimAtPath("/World/InternDataSurfaceReplay"))
    assert first["vertex_count"] == second["vertex_count"] == 4
    assert np.allclose(np.asarray(mesh.GetPointsAttr().Get()), vertices2)
    assert list(mesh.GetFaceVertexCountsAttr().Get()) == [3, 3, 3, 3]
    assert list(mesh.GetFaceVertexIndicesAttr().Get()) == faces2.reshape(-1).tolist()
    assert np.allclose(np.asarray(mesh.GetNormalsAttr().Get()), normals2)
    assert mesh.GetNormalsInterpolation() == UsdGeom.Tokens.vertex
    assert mesh.GetSubdivisionSchemeAttr().Get() == UsdGeom.Tokens.none
    extent = np.asarray(mesh.GetExtentAttr().Get(), dtype=np.float64)
    assert extent[0].tolist() == pytest.approx(vertices2.min(axis=0).tolist())
    assert extent[1].tolist() == pytest.approx(vertices2.max(axis=0).tolist())
    assert second["world_space_vertices"] is True
    assert second["identity_transform"] is True


def test_visual_authority_hides_every_old_path_and_disables_isosurface():
    replay = _module()
    from pxr import UsdGeom

    stage = _stage_with_legacy_liquid()
    vertices, faces, normals = _tetra(scale=0.01)
    replay.update_surface_mesh(stage, vertices, faces, normals)

    authority = replay.configure_surface_visual_authority(stage)

    for path in replay.build_replay_contract()["legacy_liquid_paths"]:
        assert (
            UsdGeom.Imageable(stage.GetPrimAtPath(path)).GetVisibilityAttr().Get()
            == UsdGeom.Tokens.invisible
        )
    generated = stage.GetPrimAtPath(
        "/World/InternDataParityFluid/ParticleSystem/GeneratedIsosurface"
    )
    assert UsdGeom.Imageable(generated).GetVisibilityAttr().Get() == UsdGeom.Tokens.invisible
    system = stage.GetPrimAtPath("/World/InternDataParityFluid/ParticleSystem")
    assert system.GetAttribute("physxParticleIsosurface:isosurfaceEnabled").Get() is False
    surface = stage.GetPrimAtPath("/World/InternDataSurfaceReplay")
    assert UsdGeom.Imageable(surface).GetVisibilityAttr().Get() == UsdGeom.Tokens.inherited
    assert authority["sole_visible_liquid_representation"] is True
    assert authority["visible_liquid_paths"] == ["/World/InternDataSurfaceReplay"]


def test_surface_material_is_authored_and_read_back_exactly():
    replay = _module()
    from pxr import UsdShade

    stage = _stage_with_legacy_liquid()
    vertices, faces, normals = _tetra(scale=0.01)
    replay.update_surface_mesh(stage, vertices, faces, normals)

    authored = replay.author_surface_material(stage)

    shader = UsdShade.Shader(
        stage.GetPrimAtPath(
            "/World/Looks/InternDataDerivedSurfaceWater/PreviewSurface"
        )
    )
    assert shader.GetIdAttr().Get() == "UsdPreviewSurface"
    assert shader.GetInput("diffuseColor").Get() == pytest.approx((0.46, 0.82, 0.96))
    assert shader.GetInput("roughness").Get() == pytest.approx(0.06)
    assert shader.GetInput("opacity").Get() == pytest.approx(0.06)
    assert shader.GetInput("ior").Get() == pytest.approx(1.333)
    binding = UsdShade.MaterialBindingAPI(
        stage.GetPrimAtPath("/World/InternDataSurfaceReplay")
    ).GetDirectBinding()
    assert str(binding.GetMaterialPath()) == authored["material_path"]
    assert authored["readback_matches_contract"] is True
    assert authored["fallback_used"] is False


def test_closeup_camera_contract_moves_to_receiver_safe_azimuth():
    replay = _module()

    contract = replay.build_closeup_camera_contract()

    assert contract == {
        "path": "/World/InternDataParityCloseupCamera",
        "eye": pytest.approx([0.1645, -0.6469, 1.0200]),
        "target": pytest.approx([0.2785233518810611, -0.22147663301350906, 0.8899941121566101]),
        "up": [0.0, 0.0, 1.0],
        "focal_length": pytest.approx(22.0),
        "horizontal_aperture": pytest.approx(24.0),
        "vertical_aperture": pytest.approx(16.0),
        "critical_rim_projection_margin_px": pytest.approx(31.7),
        "reference": "target_local_azimuth_minus_150_degrees",
    }


def test_closeup_camera_contract_is_authored_exactly():
    replay = _module()
    from pxr import Gf, UsdGeom

    stage = _stage_with_legacy_liquid()
    contract = replay.build_closeup_camera_contract()

    authored = replay.configure_presentation_closeup_camera(stage)

    camera = UsdGeom.Camera(
        stage.GetPrimAtPath("/World/InternDataParityCloseupCamera")
    )
    expected = Gf.Matrix4d(1).SetLookAt(
        Gf.Vec3d(*contract["eye"]),
        Gf.Vec3d(*contract["target"]),
        Gf.Vec3d(*contract["up"]),
    ).GetInverse()
    actual = UsdGeom.Xformable(camera.GetPrim()).GetLocalTransformation()
    assert actual == expected
    assert camera.GetFocalLengthAttr().Get() == pytest.approx(22.0)
    assert authored["readback_matches_contract"] is True


def test_render_settings_contract_matches_accepted_lighting_and_water_capture():
    replay = _module()

    contract = replay.build_render_settings_contract()

    assert contract == {
        "renderer": "RayTracedLighting",
        "width": 960,
        "height": 540,
        "warmup_rt_subframes": 8,
        "capture_rt_subframes": 8,
        "settings": {
            "/rtx/ambientOcclusion/enabled": False,
            "/rtx/shadows/enabled": True,
            "/rtx/shadows/sampleCount": 4,
            "/rtx/translucency/maxRefractionBounces": 12,
        },
        "lighting": {
            "distant_intensity": pytest.approx(950.0),
            "distant_rotation_xyz": [55.0, 0.0, 35.0],
            "dome_intensity": pytest.approx(400.0),
        },
    }


def test_source_parent_matrix_is_applied_without_transforming_surface():
    replay = _module()
    from pxr import Gf, UsdGeom

    stage = _stage_with_legacy_liquid()
    vertices, faces, normals = _tetra(scale=0.01)
    replay.update_surface_mesh(stage, vertices, faces, normals)
    matrix = [
        [0.0, 1.0, 0.0, 0.0],
        [-1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.2, -0.3, 0.8, 1.0],
    ]

    applied = replay.apply_source_parent_matrix(stage, matrix)

    source_matrix = UsdGeom.Xformable(
        stage.GetPrimAtPath("/World/beaker2")
    ).GetLocalTransformation()
    surface_matrix = UsdGeom.Xformable(
        stage.GetPrimAtPath("/World/InternDataSurfaceReplay")
    ).GetLocalTransformation()
    assert source_matrix == Gf.Matrix4d(*matrix)
    assert surface_matrix == Gf.Matrix4d(1.0)
    assert applied["max_abs_error"] <= 1e-12


def test_capture_mapping_requires_exact_unique_70_frames_and_excludes_warmup():
    replay = _module()
    mappings = [
        {
            "frame_index": index,
            "step_index": step,
            "cache_geometry_sha256": f"{index:064x}",
            "context_path": f"frames/context/frame_{index:04d}.png",
            "closeup_path": f"frames/closeup/frame_{index:04d}.png",
        }
        for index, step in enumerate(range(0, 691, 10))
    ]

    summary = replay.validate_capture_mapping(mappings)

    assert summary["valid"] is True
    assert summary["frame_count"] == 70
    assert summary["selected_steps"] == list(range(0, 691, 10))
    duplicate = [*mappings]
    duplicate[-1] = {**duplicate[-1], "context_path": duplicate[0]["context_path"]}
    with pytest.raises(ValueError, match="capture_paths_not_unique"):
        replay.validate_capture_mapping(duplicate)


def test_ffmpeg_command_is_h264_yuv420p_and_uses_15_fps(tmp_path):
    replay = _module()

    command = replay.build_ffmpeg_command(
        frame_pattern=tmp_path / "frame_%04d.png",
        output_path=tmp_path / "video.mp4",
        fps=15,
    )

    assert command[0] == "ffmpeg"
    assert ["-c:v", "libx264"] == command[command.index("-c:v") : command.index("-c:v") + 2]
    assert ["-pix_fmt", "yuv420p"] == command[
        command.index("-pix_fmt") : command.index("-pix_fmt") + 2
    ]
    assert ["-framerate", "15"] == command[
        command.index("-framerate") : command.index("-framerate") + 2
    ]


def test_cli_defaults_point_to_pinned_scene_and_external_cache():
    replay = _module()

    args = replay.build_arg_parser().parse_args([])

    assert Path(args.usd).name == "authored_scene.usda"
    assert Path(args.cache_dir).name == "mesh_cache"
    assert args.width == 960
    assert args.height == 540
    assert args.video_fps == 15
    assert args.headless is True
    assert args.overwrite is False
