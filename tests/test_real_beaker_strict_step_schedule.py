from __future__ import annotations

import pytest
from pxr import Sdf, Usd, UsdGeom

from tools.labutopia_fluid import (
    run_colleague_native_usd_completed_pbd_step_video as runner,
)


class _FakePhysxSimulation:
    def __init__(self, *, attach_success: bool = True) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.attach_success = attach_success
        self.attached_stage = 0

    def attach_stage(self, stage_id: int) -> bool:
        self.calls.append(("attach_stage", stage_id))
        if self.attach_success:
            self.attached_stage = stage_id
        return self.attach_success

    def get_attached_stage(self) -> int:
        return self.attached_stage

    def simulate(self, dt: float, current_time: float) -> None:
        self.calls.append(("simulate", dt, current_time))

    def fetch_results(self) -> None:
        self.calls.append(("fetch_results",))

    def detach_stage(self) -> None:
        self.calls.append(("detach_stage",))
        self.attached_stage = 0


class _FakeTimeline:
    def __init__(self, playing: bool) -> None:
        self.playing = playing
        self.stop_count = 0

    def is_playing(self) -> bool:
        return self.playing

    def stop(self) -> None:
        self.playing = False
        self.stop_count += 1


class _FakeApp:
    def __init__(self) -> None:
        self.update_count = 0

    def update(self) -> None:
        self.update_count += 1


class _FakeSettings:
    def __init__(self, playing: bool = True) -> None:
        self.values = {"/app/player/playSimulations": playing}
        self.history: list[tuple[str, bool]] = []

    def get(self, key: str):
        return self.values.get(key)

    def set_bool(self, key: str, value: bool) -> None:
        self.values[key] = value
        self.history.append((key, value))


def test_strict_stepper_executes_exact_substeps_and_monotonic_simulation_time():
    interface = _FakePhysxSimulation()
    stepper = runner.StrictPhysicsStepper.attach(
        interface=interface,
        logical_dt=1.0 / 60.0,
        integration_dt=1.0 / 600.0,
        substeps_per_logical_step=10,
        stage_id=1234,
    )

    for _ in range(3):
        stepper.step()
    stepper.detach()

    expected_calls = [("attach_stage", 1234)]
    for integration_step in range(30):
        expected_calls.extend(
            [
                (
                    "simulate",
                    1.0 / 600.0,
                    integration_step * (1.0 / 600.0),
                ),
                ("fetch_results",),
            ]
        )
    expected_calls.append(("detach_stage",))
    assert interface.calls == expected_calls
    summary = stepper.summary(requested_steps=3)
    lifecycle_sha256 = summary.pop("lifecycle_event_sha256")
    assert len(lifecycle_sha256) == 64
    assert summary == {
        "requested_logical_steps": 3,
        "executed_logical_steps": 3,
        "requested_integration_steps": 30,
        "executed_integration_steps": 30,
        "logical_dt": 1.0 / 60.0,
        "integration_dt": 1.0 / 600.0,
        "substeps_per_logical_step": 10,
        "logical_steps_per_second": 60,
        "integration_steps_per_second": 600,
        "simulated_seconds": 3.0 / 60.0,
        "exact_logical_step_count_verified": True,
        "exact_integration_step_count_verified": True,
        "exact_step_count_verified": True,
        "simulate_fetch_pair_count": 30,
        "ordered_lifecycle_verified": True,
        "lifecycle_event_count": 65,
        "stage_id": 1234,
        "attach_verified": True,
        "detach_verified": True,
        "render_updates_advance_physics": False,
        "render_invariance_checks": 0,
    }


def test_strict_stepper_fails_closed_when_stage_attach_fails():
    interface = _FakePhysxSimulation(attach_success=False)

    with pytest.raises(RuntimeError, match="strict_physx_stage_attach_failed"):
        runner.StrictPhysicsStepper.attach(
            interface=interface,
            logical_dt=1.0 / 60.0,
            integration_dt=1.0 / 600.0,
            substeps_per_logical_step=10,
            stage_id=1234,
        )


def test_paused_render_update_rejects_timeline_that_is_still_playing():
    app = _FakeApp()
    settings = _FakeSettings()

    with pytest.raises(RuntimeError, match="strict_render_update_while_timeline_playing"):
        runner.paused_render_update(app, _FakeTimeline(playing=True), settings=settings)

    runner.paused_render_update(app, _FakeTimeline(playing=False), settings=settings)
    assert app.update_count == 1
    assert settings.history == [
        ("/app/player/playSimulations", False),
        ("/app/player/playSimulations", True),
    ]


def test_physics_scene_timestep_requires_an_exact_reciprocal_integer():
    assert runner.physics_steps_per_second(1.0 / 60.0) == 60
    with pytest.raises(ValueError, match="physics_dt_must_have_integer_frequency"):
        runner.physics_steps_per_second(0.017)


def test_strict_stepper_rejects_schedule_that_does_not_cover_one_logical_step():
    with pytest.raises(ValueError, match="strict_physx_step_schedule_mismatch"):
        runner.StrictPhysicsStepper.attach(
            interface=_FakePhysxSimulation(),
            logical_dt=1.0 / 60.0,
            integration_dt=1.0 / 600.0,
            substeps_per_logical_step=9,
            stage_id=1234,
        )


def test_strict_stepper_reports_each_completed_integration_substep():
    observed = []
    stepper = runner.StrictPhysicsStepper.attach(
        interface=_FakePhysxSimulation(),
        logical_dt=1.0 / 60.0,
        integration_dt=1.0 / 600.0,
        substeps_per_logical_step=10,
        stage_id=1234,
    )

    stepper.step(
        after_integration_step=lambda index, seconds: observed.append(
            (index, seconds)
        )
    )

    assert observed == [
        (index, index * (1.0 / 600.0)) for index in range(1, 11)
    ]


def test_strict_particle_offsets_respect_physx_fluid_hierarchy():
    offsets = runner.normalize_strict_particle_offsets(
        {
            "particle_width": 0.0006,
            "particle_contact_offset": 0.00054,
            "particle_system_contact_offset": 0.00081,
            "solid_rest_offset": 0.000594,
            "fluid_rest_offset": 0.000352836,
        }
    )

    assert offsets["particle_contact_offset"] == pytest.approx(2.0 * 0.000352836)
    assert offsets["particle_contact_offset"] >= offsets["solid_rest_offset"]
    assert offsets["particle_system_contact_offset"] == pytest.approx(
        1.5 * offsets["particle_contact_offset"]
    )
    assert offsets["physx_offset_hierarchy_verified"] is True


def test_legacy_particle_graph_isolated_before_strict_physx_attach():
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Xform.Define(stage, "/World/fluid")
    sampler = UsdGeom.Mesh.Define(stage, "/World/fluid/Cylinder").GetPrim()
    sampler.CreateRelationship("physxParticleSampling:particles").SetTargets(
        [Sdf.Path("/World/ParticleSet")]
    )
    sampler.CreateAttribute(
        "physxParticleSampling:volume", Sdf.ValueTypeNames.Bool
    ).Set(True)
    particle_set = UsdGeom.Points.Define(stage, "/World/ParticleSet").GetPrim()
    particle_set.CreateRelationship("physxParticle:particleSystem").SetTargets(
        [Sdf.Path("/World/ParticleSystem")]
    )
    particle_system = UsdGeom.Xform.Define(stage, "/World/ParticleSystem").GetPrim()
    particle_system.CreateAttribute(
        "particleSystemEnabled", Sdf.ValueTypeNames.Bool
    ).Set(True)

    first = runner._deactivate_original_fluid_prims(stage)
    second = runner._deactivate_original_fluid_prims(stage)

    assert sampler.IsActive() is True
    assert particle_set.IsActive() is True
    assert particle_system.IsActive() is True
    assert sampler.GetRelationship(
        "physxParticleSampling:particles"
    ).GetTargets() == []
    assert sampler.GetAttribute("physxParticleSampling:volume").Get() is False
    assert particle_set.GetRelationship("physxParticle:particleSystem").GetTargets() == []
    assert particle_set.GetAttribute("physxParticle:fluid").Get() is False
    assert particle_set.GetAttribute("physxParticle:selfCollision").Get() is False
    assert particle_system.GetAttribute("particleSystemEnabled").Get() is False
    assert first["ownership_isolation"]["verified"] is True
    assert first["ownership_isolation"]["synchronization_required"] is True
    assert second["ownership_isolation"]["verified"] is True
    assert second["ownership_isolation"]["synchronization_required"] is False


def test_strict_legacy_graph_sync_stops_timeline_and_runs_update_barrier():
    app = _FakeApp()
    timeline = _FakeTimeline(playing=True)
    settings = _FakeSettings()
    isolation = {
        "ownership_isolation": {
            "verified": True,
            "synchronization_required": True,
        }
    }

    result = runner.synchronize_legacy_particle_graph(
        app=app,
        timeline=timeline,
        settings=settings,
        isolation_summary=isolation,
        warmup_updates=1,
        strict_mode=True,
    )

    assert timeline.stop_count == 1
    assert app.update_count == 1
    assert result["ownership_isolation"]["synchronization_updates"] == 1
    assert result["ownership_isolation"]["synchronization_verified"] is True


def test_strict_legacy_graph_sync_rejects_missing_update_barrier():
    with pytest.raises(RuntimeError, match="legacy_particle_graph_sync_missing"):
        runner.synchronize_legacy_particle_graph(
            app=_FakeApp(),
            timeline=_FakeTimeline(playing=False),
            settings=_FakeSettings(),
            isolation_summary={
                "ownership_isolation": {
                    "verified": True,
                    "synchronization_required": True,
                }
            },
            warmup_updates=0,
            strict_mode=True,
        )


def test_strict_runtime_removes_legacy_sampling_api_with_official_command():
    class FakePrim:
        def __init__(self):
            self.schemas = ["PhysxParticleSamplingAPI"]

        def __bool__(self):
            return True

        def GetAppliedSchemas(self):
            return list(self.schemas)

        def GetPath(self):
            return Sdf.Path("/World/fluid/Cylinder")

        def IsActive(self):
            return True

    sampler_prim = FakePrim()

    class FakeStage:
        def GetPrimAtPath(self, path):
            assert path == "/World/fluid/Cylinder"
            return sampler_prim

    stage = FakeStage()
    calls = []

    def execute(command, **kwargs):
        calls.append((command, kwargs))
        assert command == "RemoveParticleSamplingCommand"
        sampler_prim.schemas.remove("PhysxParticleSamplingAPI")

    summary = runner.remove_legacy_particle_sampling_api(
        stage,
        execute_command=execute,
    )

    assert calls == [
        (
            "RemoveParticleSamplingCommand",
            {"stage": stage, "prim": sampler_prim},
        ),
    ]
    assert summary["api_present_before"] is True
    assert summary["api_present_after"] is False
    assert summary["verified"] is True
