#!/usr/bin/env python3
"""Replay one accepted real-beaker trace as five render-only OmniGlass candidates."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import ctypes
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import fcntl
import gzip
import hashlib
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path
import shutil
import secrets
import stat
import struct
import subprocess
import sys
import tempfile
import traceback
from typing import TYPE_CHECKING, Any, Mapping, Sequence
import zipfile


_SEALED_RUNTIME = os.environ.get("LABUTOPIA_SEALED_RUNTIME") == "1"
if _SEALED_RUNTIME:
    _sealed_repo_root = os.environ.get("LABUTOPIA_REPO_ROOT")
    if not _sealed_repo_root or not Path(_sealed_repo_root).is_absolute():
        raise RuntimeError("sealed_runtime_repo_root_missing")
    REPO_ROOT = Path(_sealed_repo_root).resolve()
else:
    REPO_ROOT = Path(__file__).resolve().parents[2]
    _configured_repo_root = os.environ.get("LABUTOPIA_REPO_ROOT")
    if (
        _configured_repo_root is not None
        and Path(_configured_repo_root).resolve() != REPO_ROOT
    ):
        raise RuntimeError("live_repo_root_environment_override")
if _SEALED_RUNTIME and any(
    path == str(REPO_ROOT) or path.startswith(str(REPO_ROOT) + os.sep)
    for path in sys.path
):
    raise RuntimeError("sealed_runtime_live_repo_on_sys_path")
if not _SEALED_RUNTIME and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if TYPE_CHECKING:
    from tools.labutopia_fluid.real_beaker import CupInteriorFrame


PRESENTATION_POINTS_PATH = "/World/CompletedPBD/PresentationParticleSet"
PRESENTATION_SURFACE_PATH = "/World/CompletedPBD/PresentationSurface"
HIDDEN_PHYSICAL_INITIAL_STATE_PATH = "/World/CompletedPBD/AcceptedPhysicalInitialState"
SOURCE_SAMPLER_PATH = "/World/fluid/Cylinder"
SOURCE_PARTICLE_SET_PATH = "/World/ParticleSet"
SOURCE_PARTICLE_SYSTEM_PATH = "/World/ParticleSystem"
BEAKER_NORMAL_REMEDIATION_ID = "beaker_normals_block_v1"
BEAKER_NORMAL_RENDERER_SCOPE = "isaacsim41_rtx"
BEAKER_NORMAL_MATRIX_PROJECTION_ID = (
    "beaker_normal_remediation_matrix_equivalence_v1"
)
BEAKER_NORMAL_MESH_PATHS = (
    "/World/beaker1/mesh",
    "/World/beaker2/mesh",
)
AUTHORITY_BUNDLE_BASENAME = "accepted_authority_bundle.json"
RUNTIME_EVIDENCE_SNAPSHOT_DIR = "runtime_evidence_snapshot"
AUTHORITY_LOG_SEGMENT_BASENAME = "run_scoped_kit_log_segment.log"
ALLOWED_KIT_RUNTIME_SESSION_ROOT_PATHS = (
    "/OmniverseKit_Persp",
    "/OmniverseKit_Front",
    "/OmniverseKit_Top",
    "/OmniverseKit_Right",
    "/Render",
)
ALLOWED_REPLICATOR_RUNTIME_SESSION_ROOT_PATHS = (
    "/Orchestrator",
)
PHYSX_RUNTIME_ISOSURFACE_PATH = "/World/ParticleSystem/Isosurface"
PHYSX_RUNTIME_ISOSURFACE_SPEC_PATHS = (
    "/World",
    "/World/ParticleSystem",
    PHYSX_RUNTIME_ISOSURFACE_PATH,
    f"{PHYSX_RUNTIME_ISOSURFACE_PATH}.faceVertexCounts",
    f"{PHYSX_RUNTIME_ISOSURFACE_PATH}.faceVertexIndices",
    f"{PHYSX_RUNTIME_ISOSURFACE_PATH}.normals",
    f"{PHYSX_RUNTIME_ISOSURFACE_PATH}.points",
)
REFERENCE_CANDIDATE_IDS = (
    "OMNI_REF_FINE",
    "OMNI_REF_RATIO_15",
    "OMNI_REF_RATIO_12",
    "OMNI_REF_SURFACE",
    "OMNI_REF_DISPLAY_FILL",
)
DISPLAY_FILL_VISUAL_PROTOTYPE_CANDIDATE_IDS = ("OMNI_REF_DISPLAY_FILL",)
DEFAULT_CANDIDATES = ",".join(REFERENCE_CANDIDATE_IDS)
DEFAULT_OUT_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_omniglass_reference_20260711_001"
)
VERSION_MATCHED_MDL_CLOSURE_DIRNAME = "material_closure_isaacsim41_conda_core"
REPLAY_PRESENTATION_LOOK_ID = "weekly_omniglass_C"
LIGHTING_VARIANT_C_CONTROL = "C_CONTROL"
LIGHTING_VARIANT_B = "B_LIGHTING"
ALLOWED_LIGHTING_VARIANTS = (
    LIGHTING_VARIANT_C_CONTROL,
    LIGHTING_VARIANT_B,
)
REPLAY_RT_SUBFRAMES = 4
REPLAY_MAX_REFRACTION_BOUNCES = 12
REPLAY_REFRACTION_SETTING_PATH = "/rtx/translucency/maxRefractionBounces"
REPLAY_AMBIENT_OCCLUSION_SETTING_PATH = "/rtx/ambientOcclusion/enabled"
REPLAY_AMBIENT_OCCLUSION_RAY_LENGTH_SETTING_PATH = (
    "/rtx/ambientOcclusion/rayLength"
)
REPLAY_AMBIENT_OCCLUSION_MIN_SAMPLES_SETTING_PATH = (
    "/rtx/ambientOcclusion/minSamples"
)
REPLAY_AMBIENT_OCCLUSION_MAX_SAMPLES_SETTING_PATH = (
    "/rtx/ambientOcclusion/maxSamples"
)
REPLAY_AMBIENT_OCCLUSION_DENOISER_MODE_SETTING_PATH = (
    "/rtx/ambientOcclusion/denoiserMode"
)
REPLAY_SHADOWS_SETTING_PATH = "/rtx/shadows/enabled"
REPLAY_SHADOW_SAMPLE_COUNT_SETTING_PATH = "/rtx/shadows/sampleCount"
REPLAY_RENDERER_CONSUMPTION_VERIFICATION = "NOT_AVAILABLE_ISAACSIM41"
RENDER_DIAGNOSTIC_EXPERIMENT_ID = "real_beaker_ao_rt_matrix_v3_20260712_008"
RENDER_DIAGNOSTIC_AGGREGATE_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / RENDER_DIAGNOSTIC_EXPERIMENT_ID
)
RENDER_DIAGNOSTIC_PRE_FREEZE_PATH = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_008_protected_tree_freeze_pre.json"
)
RENDER_DIAGNOSTIC_POST_FREEZE_PATH = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_008_protected_tree_freeze_post.json"
)
RENDER_DIAGNOSTIC_IMPLEMENTATION_FREEZE_PATH = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_008_implementation_identity.json"
)
RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH = (
    RENDER_DIAGNOSTIC_AGGREGATE_ROOT.parent
    / f".{RENDER_DIAGNOSTIC_EXPERIMENT_ID}.aggregate.lock"
)
HISTORICAL_003_EXPERIMENT_ID = "real_beaker_ao_rt_matrix_v3_20260712_003"
HISTORICAL_003_AGGREGATE_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / HISTORICAL_003_EXPERIMENT_ID
)
HISTORICAL_003_TERMINAL_ATTESTATION_PATH = (
    HISTORICAL_003_AGGREGATE_ROOT.parent
    / f"{HISTORICAL_003_EXPERIMENT_ID}_terminal_validation.json"
)
HISTORICAL_003_TERMINAL_ATTESTATION_FILE_SHA256 = (
    "ac99aa8d494dcab04fe401da4c025e840ba7bb81996438ddc012d4e0ed46ec71"
)
HISTORICAL_003_TERMINAL_ATTESTATION_LOGICAL_SHA256 = (
    "2a3d413edb376a21ad8e46e916492afc690d49223e4b6f4b6845065418c7fb0b"
)
HISTORICAL_004_EXPERIMENT_ID = "real_beaker_ao_rt_matrix_v3_20260712_004"
HISTORICAL_004_AGGREGATE_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / HISTORICAL_004_EXPERIMENT_ID
)
HISTORICAL_004_IMPLEMENTATION_IDENTITY_SHA256 = (
    "c309525589be9fee5aeb95293e06dd9defbf3def510b63aedfa3611232666a3d"
)
HISTORICAL_004_PRE_FREEZE_SHA256 = (
    "d5939d4267241f7a7f93ae84675d6f7acde5350119c59e80d1c3d4687f67bba9"
)
HISTORICAL_004_POST_FREEZE_SHA256 = (
    "1512cdc413f4b3eb3b7dd5583fba0b94bce7ade066e7c36aa6e1608c1a887dfa"
)
HISTORICAL_004_MATRIX_DECISION_SHA256 = (
    "53b5bb7fd01b58ba60a1cc06060602ea331b6a709ae7f4d14e18c1e425422b4e"
)
HISTORICAL_004_DECISION_FILE_SHA256 = (
    "79ebffbe432f229ed7c19288af82d3f0cc32779823fb952506294c5a6fe5cc44"
)
HISTORICAL_004_CELL_STATUS_FILE_SHA256 = (
    "1dfa4cb8b284c6c69e74e1a153bdc8062ae887200fcb6061bd45ad009b487271"
)
HISTORICAL_004_EXTERNAL_FILE_SHA256 = {
    "aggregate_lock": (
        "59a69a413554621148a3cafae1ab4aa9461fc28894c2029412a62dc238d58935"
    ),
    "implementation_identity": (
        "88155f9da05530b2870bb30896ff5f6d0ae49cf5dbc51123568988f89fdcbf1c"
    ),
    "pre_freeze": (
        "6dc3a9553a97d0db97324142d11104e154a9eaf4044b46e0a8627ca01b8e8803"
    ),
    "post_freeze": (
        "d382d7f65e5a95e5d3533dff2016c9718bdafa834b7ba058f83935ff258e21de"
    ),
}
HISTORICAL_005_EXPERIMENT_ID = "real_beaker_ao_rt_matrix_v3_20260712_005"
HISTORICAL_005_AGGREGATE_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / HISTORICAL_005_EXPERIMENT_ID
)
HISTORICAL_005_IMPLEMENTATION_IDENTITY_SHA256 = (
    "68675a401bd28feadb0e7c93e2a6479343210cf2585d9bd2a9aafcc709b49420"
)
HISTORICAL_005_PRE_FREEZE_SHA256 = (
    "310faf31d5c91db2ffcf33a7a507d071f68a02d476dd3f27e03d03b443d07f50"
)
HISTORICAL_005_POST_FREEZE_SHA256 = (
    "5c11902b429600de09ae76859d4914aa735874cc4ffedf0c14eebfcac43b4665"
)
HISTORICAL_005_MATRIX_DECISION_SHA256 = (
    "c51096a38145a09cd0d5c17cfbbb89b6f7ff27bd6e343cae9f2ca3f050b42d4e"
)
HISTORICAL_005_DECISION_FILE_SHA256 = (
    "d7eaf0b41b10747899ebf98a41f9de85bcf475502e0c811318adc828353a79b8"
)
HISTORICAL_005_CELL_STATUS_FILE_SHA256 = (
    "81f9bd1a4b79a37e3c6bc585958df94f4ad2e7e6a208abb226223ed2f6a816f5"
)
HISTORICAL_005_FAILURE_FILE_SHA256 = (
    "ce68dc20bd470f5fec7deb63aad4d69ce7ebf0a77303414f8d62e2c03227f564"
)
HISTORICAL_005_EXTERNAL_FILE_SHA256 = {
    "aggregate_lock": (
        "66ead25f7eab24fe76277f7c1f171c94fb7b1bc2f12bee100f158350b98529c7"
    ),
    "implementation_identity": (
        "7a08e8b04c38e978774339f2527a06037e608f4bb5c48bb0f7bb6cd6d8e4f6c6"
    ),
    "pre_freeze": (
        "2a45befcd0be7d51341d33ea1b67bc8a8ea31935adc233eb723141ac30873bba"
    ),
    "post_freeze": (
        "554b3b9b4fa2b786b8749d076b0f66026ab25bb655f54009e5b015becf310d6b"
    ),
}
HISTORICAL_006_EXPERIMENT_ID = "real_beaker_ao_rt_matrix_v3_20260712_006"
HISTORICAL_006_AGGREGATE_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / HISTORICAL_006_EXPERIMENT_ID
)
HISTORICAL_006_IMPLEMENTATION_IDENTITY_SHA256 = (
    "e8aacf651ce2251677e6f4ff326d343415c8710d1d4a451a2dd4414659bba096"
)
HISTORICAL_006_PRE_FREEZE_SHA256 = (
    "b49784284c0fcb8c7b1d9ef2b08dd3329681cfc1963322202e944f728198f929"
)
HISTORICAL_006_POST_FREEZE_SHA256 = (
    "a36c0eeec17bcfabde6df78304a63574e6d2eb668214193657f4959ec7db0513"
)
HISTORICAL_006_MATRIX_DECISION_SHA256 = (
    "816df6f52ec01642098542ef22fed8132f8a65389351cd96c2c3603074cd30aa"
)
HISTORICAL_006_DECISION_FILE_SHA256 = (
    "e57ae4e0a78285f3022ec4a5e2f9b2b8878aa389c78565a1a568326c1841afff"
)
HISTORICAL_006_CELL_STATUS_FILE_SHA256 = (
    "0a98b98e853b0e2e0a50c85e5c125d3879dcfbe6ac5d512c18e9de3760d79b29"
)
HISTORICAL_006_FAILURE_FILE_SHA256 = (
    "a3a1d14c2ae7be35a0942f6aaab8e9f6c7effec766070fd3b95c0cef24f74ad2"
)
HISTORICAL_006_EXTERNAL_FILE_SHA256 = {
    "aggregate_lock": (
        "79c6c83854211b256ecaa6e7e91338736433515066d22ce8ddda848b27e4da02"
    ),
    "implementation_identity": (
        "f6ada89343c4348bc86a17235a158d209dcb7eeb49176cb9c2845d922e71c550"
    ),
    "pre_freeze": (
        "78fd5f0af4b3cfc336b7389c00837e9e271b8982a0f5f0642b03e9ccee665d4b"
    ),
    "post_freeze": (
        "fb7c26e6630966fd6381a3aa2f9a299b8f8d0ca2c11ac9f607508d99db68146a"
    ),
}
HISTORICAL_007_EXPERIMENT_ID = "real_beaker_ao_rt_matrix_v3_20260712_007"
HISTORICAL_007_AGGREGATE_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / HISTORICAL_007_EXPERIMENT_ID
)
HISTORICAL_007_IMPLEMENTATION_IDENTITY_SHA256 = (
    "476af5e56c2e90ca9dcdd2d377582e906ea0fddb94dbd806b255acad424d4928"
)
HISTORICAL_007_PRE_FREEZE_SHA256 = (
    "03412d96394389a9020f644c561acd17f7caa2e33d4c0410a3c65ad0281264c2"
)
HISTORICAL_007_POST_FREEZE_SHA256 = (
    "e0b8d390181e7e516c47c455b1bf787d3c72bc1052ca6fe2a5302f5a32404d3a"
)
HISTORICAL_007_MATRIX_DECISION_SHA256 = (
    "6c568e104b33ba2f4deaa01dfc9baf7fe5a03dd371a8d7225e91ce93d0e001cc"
)
HISTORICAL_007_DECISION_FILE_SHA256 = (
    "205f0bfae48926371efe29174b32000f7455a327e9365a7b10202b4d63363182"
)
HISTORICAL_007_CELL_STATUS_FILE_SHA256 = (
    "6d9c52272034a33fd19737e3763432f490695153149fa8dbf05401214bba06cf"
)
HISTORICAL_007_EXTERNAL_FILE_SHA256 = {
    "aggregate_lock": (
        "60df1de69e4eb0eb021c91f4d9d53028ea61799c227bcc2a90f1be6b0f60f29b"
    ),
    "implementation_identity": (
        "a7835862a0b898c851fbdc65b8f99527502dc258bcdfe3a5f71d8fc4cfe763e0"
    ),
    "pre_freeze": (
        "8a2269d3777401bf66a0343fd577a43e0615d3587eb288c63cf49de5e07330f3"
    ),
    "post_freeze": (
        "94ad20eee552f210b5f05e4ceee46b373bafc39e9c1c16f056260a5fd982c123"
    ),
}
RENDER_DIAGNOSTIC_ANCHOR_BASENAME = "experiment_anchor.json"
RENDER_DIAGNOSTIC_POST_SEAL_BASENAME = "successful_post_seal.json"
RENDER_DIAGNOSTIC_FINAL_CLOSURE_DIRNAME = "final_closure"
RENDER_DIAGNOSTIC_CLOSURE_MANIFEST_BASENAME = "closure_manifest.json"
RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME = "matrix_decision_authority"
RENDER_DIAGNOSTIC_AUTHORITY_JOURNAL_BASENAME = (
    "authority_publication_intent.json"
)
_RENDER_DIAGNOSTIC_CANONICAL_AGGREGATE_ROOT = RENDER_DIAGNOSTIC_AGGREGATE_ROOT
_RENDER_DIAGNOSTIC_CANONICAL_LOCK_PATH = RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH
RENDER_DIAGNOSTIC_ACCEPTED_AUTHORITY_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "fluid_spike_real_beaker_static_hold_support_aligned_v1_20260712"
    / "accepted_authority_P4096_S2"
)
RENDER_DIAGNOSTIC_SOURCE_PACKAGE_ROOT = (
    REPO_ROOT
    / "outputs/usd_asset_packages"
    / "lab_001_level1_pour_support_aligned_v1_20260712"
)
RENDER_DIAGNOSTIC_LOCALIZED_DEPENDENCY_ROOT = (
    REPO_ROOT
    / "outputs/usd_asset_packages"
    / "lab_001_localized_20260707"
)
RENDER_DIAGNOSTIC_VERSION_MATCHED_MDL_SOURCE_ROOT = (
    REPO_ROOT.parent
    / "conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310"
    / "lib/python3.10/site-packages/omni/mdl/core"
)
RENDER_DIAGNOSTIC_SOURCE_ENTRY_PATH = (
    RENDER_DIAGNOSTIC_SOURCE_PACKAGE_ROOT
    / "lab_001_level1_pour_support_aligned_v1.usda"
)
RENDER_DIAGNOSTIC_EXPECTED_AUTHORITY_SHA256 = (
    "edfbc37b108a5972d9ef6bbf3a306b4eea1ab71e872c9c58df8d51dfeda51605"
)
RENDER_DIAGNOSTIC_EXPECTED_SOURCE_SHA256 = (
    "3cd4f73913a600f2ac19c490080ac17ffcd395072a1e54101960803e8fa9939b"
)
RENDER_DIAGNOSTIC_EXPECTED_TRACE_SHA256 = (
    "124492bbffa9cbc4134ba1ee3558f0e52eee9ea502797ed0fb8b32dd2ebda5fd"
)
RENDER_DIAGNOSTIC_EXPECTED_NORMAL_MATRIX_PROJECTION_SHA256 = (
    "7ac77839b4b9124fa07db5633998cf7512789f1fa7c79fbe81cd53ae98b33160"
)
RENDER_DIAGNOSTIC_PROTECTED_REGISTRY_ID = (
    "real_beaker_ao_rt_matrix_v3_protected_registry_v6"
)
RENDER_DIAGNOSTIC_PROTECTED_ROOTS = (
    HISTORICAL_007_AGGREGATE_ROOT,
    HISTORICAL_006_AGGREGATE_ROOT,
    HISTORICAL_005_AGGREGATE_ROOT,
    HISTORICAL_004_AGGREGATE_ROOT,
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_003",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_002",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "fluid_spike_real_beaker_static_hold_support_aligned_v1_20260712"
    / "accepted_authority_P4096_S2",
    REPO_ROOT
    / "outputs/usd_asset_packages"
    / "lab_001_level1_pour_support_aligned_v1_20260712",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_omniglass_support_aligned_normals_v1_20260712_001",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_display_fill_normal_block_support_aligned_20260712_002",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_omniglass_reference_si600_restoffset_20260712_024_smoke",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_display_fill_ao_visual_prototype_20260712_026",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_display_fill_normal_block_lighting_C_control_20260712_001",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_display_fill_normal_block_lighting_B_treatment_20260712_001",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_normal_block_lighting_ab_blind_review_20260712",
    RENDER_DIAGNOSTIC_LOCALIZED_DEPENDENCY_ROOT,
    RENDER_DIAGNOSTIC_VERSION_MATCHED_MDL_SOURCE_ROOT,
)
RENDER_DIAGNOSTIC_PROTECTED_FILES = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_007_implementation_identity.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_007_protected_tree_freeze_pre.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_007_protected_tree_freeze_post.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / ".real_beaker_ao_rt_matrix_v3_20260712_007.aggregate.lock",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_006_implementation_identity.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_006_protected_tree_freeze_pre.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_006_protected_tree_freeze_post.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / ".real_beaker_ao_rt_matrix_v3_20260712_006.aggregate.lock",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_005_implementation_identity.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_005_protected_tree_freeze_pre.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_005_protected_tree_freeze_post.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / ".real_beaker_ao_rt_matrix_v3_20260712_005.aggregate.lock",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_004_implementation_identity.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_004_protected_tree_freeze_pre.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_004_protected_tree_freeze_post.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / ".real_beaker_ao_rt_matrix_v3_20260712_004.aggregate.lock",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_003_implementation_identity.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_003_protected_tree_freeze_pre.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_003_protected_tree_freeze_post.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / ".real_beaker_ao_rt_matrix_v3_20260712_003.aggregate.lock",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_003_terminal_validation.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_002_implementation_identity.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_002_protected_tree_freeze_pre.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / ".real_beaker_ao_rt_matrix_v3_20260712_002.aggregate.lock",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_implementation_identity_20260712.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_protected_tree_freeze_pre_20260712.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / ".real_beaker_ao_rt_matrix_v3_20260712_001.aggregate.lock",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_001_first_root_publication_failure.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_002_cpfs_rename_probe.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_normal_block_lighting_ab_machine_verification_20260712.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_normal_block_look_recovery_v2_protected_tree_freeze_pre_20260712.json",
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_normal_block_look_recovery_v2_protected_tree_freeze_post_20260712.json",
    REPO_ROOT / "tools/labutopia_fluid/run_real_beaker_omniglass_replay.py",
    REPO_ROOT / "tests/test_real_beaker_runtime_contract.py",
    REPO_ROOT / "tests/test_omniglass_reference.py",
    REPO_ROOT / "tests/test_real_beaker.py",
    REPO_ROOT / "tests/test_real_beaker_matrix_isaac_runtime.py",
    REPO_ROOT / "tests/test_real_beaker_strict_step_schedule.py",
    REPO_ROOT
    / "tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py",
    REPO_ROOT / "tests/test_level1_pour_support_aligned_scene.py",
    REPO_ROOT / "tests/test_support_aligned_authority_bundle.py",
    REPO_ROOT
    / "docs/runs/2026-07-12-real-beaker-black-liquid-causal-matrix-plan-v3.md",
    REPO_ROOT
    / "docs/runs/2026-07-12-real-beaker-black-liquid-causal-matrix-hardening-plan.md",
    REPO_ROOT
    / "docs/runs/2026-07-13-real-beaker-presentation-layer-save-recovery-plan.md",
    REPO_ROOT
    / "docs/runs/2026-07-13-real-beaker-presentation-layer-file-mode-plan.md",
    REPO_ROOT
    / "docs/runs/2026-07-13-real-beaker-normal-equivalence-projection-plan.md",
    REPO_ROOT
    / "docs/runs/2026-07-13-real-beaker-material-id-hash-plan.md",
    REPO_ROOT
    / "docs/runs/2026-07-13-real-beaker-parent-pxr-closure-plan.md",
    REPO_ROOT
    / "outputs/usd_asset_packages"
    / "lab_001_level1_pour_support_aligned_v1_20260712"
    / "lab_001_level1_pour_support_aligned_v1.usda",
    REPO_ROOT
    / "tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py",
    RENDER_DIAGNOSTIC_IMPLEMENTATION_FREEZE_PATH,
)
RENDER_DIAGNOSTIC_VARIANTS = (
    "AO0_RT4_CONTROL",
    "AO0_RT12",
    "AO1_RT4",
    "AO1_RT12",
)
RENDER_DIAGNOSTIC_VARIANT_SETTINGS = {
    "AO0_RT4_CONTROL": (False, 4),
    "AO0_RT12": (False, 12),
    "AO1_RT4": (True, 4),
    "AO1_RT12": (True, 12),
}
RENDER_DIAGNOSTIC_BALANCED_ORDER = {
    "A": (
        "AO0_RT4_CONTROL",
        "AO0_RT12",
        "AO1_RT4",
        "AO1_RT12",
    ),
    "B": (
        "AO1_RT12",
        "AO1_RT4",
        "AO0_RT12",
        "AO0_RT4_CONTROL",
    ),
    "C": (
        "AO0_RT12",
        "AO1_RT12",
        "AO0_RT4_CONTROL",
        "AO1_RT4",
    ),
    "D": (
        "AO1_RT4",
        "AO0_RT4_CONTROL",
        "AO1_RT12",
        "AO0_RT12",
    ),
}
RENDER_DIAGNOSTIC_REPLICATES = ("A", "B", "C", "D")
RENDER_DIAGNOSTIC_REVIEW_VIEWS = ("source_beaker_closeup", "context")
RENDER_DIAGNOSTIC_REVIEW_FRAMES = (0, 300, 600)
RENDER_DIAGNOSTIC_REVIEW_FRAME_LABELS = ("0000", "0300", "0600")
RENDER_DIAGNOSTIC_REPLICATE_PAIRS = (
    ("A", "B"),
    ("A", "C"),
    ("A", "D"),
    ("B", "C"),
    ("B", "D"),
    ("C", "D"),
)
EFFECTIVE_REPLAY_LOOK_MATRIX_PROJECTION_ID = (
    "effective_replay_look_matrix_projection_v1"
)
CANDIDATE_DIAGNOSTIC_ARTIFACT_ROLES = (
    "kit_log_segment",
    "capture_frame_bindings_json",
    "frozen_composed_world_fingerprint_json",
    "capture_composed_world_fingerprint_json",
    "reopened_composed_world_fingerprint_json",
    "capture_session_baseline_usda",
    "capture_session_baseline_json",
    "capture_session_post_cleanup_usda",
    "capture_session_post_cleanup_json",
    "capture_root_baseline_usda",
    "capture_root_baseline_json",
    "capture_root_post_cleanup_usda",
    "capture_root_post_cleanup_json",
    "capture_frame_final_usda",
    "capture_frame_final_json",
)
CAPTURE_CAMERA_ROLES = (
    "context",
    "source_beaker_closeup",
    "native_table_context",
)
COMPOSED_WORLD_FINGERPRINT_ALGORITHM = (
    "labutopia_composed_world_default_time_property_snapshot_v2_"
    "excluding_known_physx_runtime"
)
KNOWN_MDL_COMPATIBILITY_WARNING_TOKENS = (
    "Parameter 'specular_transmission_weight'",
    "not available in the MDL representation",
)
PHYSICAL_TRACE_IDENTITY_FIELDS = (
    "source_usd_sha256",
    "particle_count",
    "seed",
    "steps",
    "trace_interval",
    "frame_indices",
    "frame_particle_counts",
    "frame_count",
    "positions_sha256",
    "physical_trace_sha256",
)
_HEX_DIGITS = frozenset("0123456789abcdef")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    return _hash_regular_file_pinned(path, label="sha256_file")["sha256"]


def canonical_json_sha256_v1(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_sha256(value: Any) -> str:
    return canonical_json_sha256_v1(value)


def _json_native_copy(value: Any) -> Any:
    """Return a detached JSON-native value so persisted contracts round-trip."""
    return json.loads(json.dumps(value, allow_nan=False))


def _absolute_path_without_symlink_resolution(
    value: str | os.PathLike[str],
) -> Path:
    return Path(os.path.abspath(os.path.expanduser(os.fspath(value))))


def _reject_symlink_path_components(
    value: str | os.PathLike[str],
    *,
    label: str,
) -> Path:
    path = _absolute_path_without_symlink_resolution(value)
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label}_symlink:{current}")
    return path


def _verify_pinned_path_components(
    identities: Sequence[tuple[Path, int, int, int]],
    *,
    label: str,
) -> None:
    for path, device, inode, file_type in identities:
        try:
            current = os.lstat(path)
        except OSError as exc:
            raise ValueError(
                f"{label}_component_unreadable:{path}:{type(exc).__name__}:{exc}"
            ) from exc
        if (
            current.st_dev,
            current.st_ino,
            stat.S_IFMT(current.st_mode),
        ) != (device, inode, file_type):
            raise ValueError(f"{label}_component_changed:{path}")


@contextmanager
def _open_pinned_path(
    value: str | os.PathLike[str],
    *,
    leaf_directory: bool,
    label: str,
):
    path = _reject_symlink_path_components(value, label=label)
    flags_base = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags_base |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags_base |= os.O_NOFOLLOW
    descriptor = os.open(path.anchor, flags_base | os.O_DIRECTORY)
    identities: list[tuple[Path, int, int, int]] = []
    current_path = Path(path.anchor)
    root_stat = os.fstat(descriptor)
    identities.append(
        (
            current_path,
            root_stat.st_dev,
            root_stat.st_ino,
            stat.S_IFMT(root_stat.st_mode),
        )
    )
    try:
        components = path.parts[1:]
        for index, component in enumerate(components):
            is_leaf = index == len(components) - 1
            wants_directory = not is_leaf or leaf_directory
            flags = flags_base | (os.O_DIRECTORY if wants_directory else 0)
            next_descriptor = os.open(
                component,
                flags,
                dir_fd=descriptor,
            )
            try:
                opened = os.fstat(next_descriptor)
                named = os.stat(
                    component,
                    dir_fd=descriptor,
                    follow_symlinks=False,
                )
                if (
                    opened.st_dev,
                    opened.st_ino,
                    stat.S_IFMT(opened.st_mode),
                ) != (
                    named.st_dev,
                    named.st_ino,
                    stat.S_IFMT(named.st_mode),
                ):
                    raise ValueError(f"{label}_component_changed:{current_path / component}")
            except BaseException:
                os.close(next_descriptor)
                raise
            os.close(descriptor)
            descriptor = next_descriptor
            current_path = current_path / component
            identities.append(
                (
                    current_path,
                    opened.st_dev,
                    opened.st_ino,
                    stat.S_IFMT(opened.st_mode),
                )
            )
        if not components and not leaf_directory:
            raise ValueError(f"{label}_root_cannot_be_regular_file")
        yield path, descriptor, tuple(identities)
    finally:
        os.close(descriptor)


def _hash_open_regular_file(
    descriptor: int,
    *,
    label: str,
) -> dict[str, Any]:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"{label}_must_be_regular_file")
    digest = hashlib.sha256()
    byte_count = 0
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
        byte_count += len(chunk)
    after = os.fstat(descriptor)
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if before_identity != after_identity or byte_count != after.st_size:
        raise ValueError(f"{label}_changed_while_reading")
    return {
        "byte_count": byte_count,
        "sha256": digest.hexdigest(),
        "device": after.st_dev,
        "inode": after.st_ino,
        "file_type": stat.S_IFMT(after.st_mode),
    }


def _hash_regular_file_pinned(
    path: str | os.PathLike[str],
    *,
    label: str,
) -> dict[str, Any]:
    try:
        with _open_pinned_path(
            path,
            leaf_directory=False,
            label=label,
        ) as (checked_path, descriptor, identities):
            evidence = _hash_open_regular_file(descriptor, label=label)
            _verify_pinned_path_components(identities, label=label)
            return {"path": str(checked_path), **evidence}
    except OSError as exc:
        raise ValueError(
            f"{label}_unreadable:{type(exc).__name__}:{exc}"
        ) from exc


def _read_pinned_regular_file_evidence(
    path: str | os.PathLike[str],
    *,
    label: str,
    expected_bytes: bytes | None = None,
) -> dict[str, Any]:
    checked_path = _reject_symlink_path_components(path, label=label)
    components = checked_path.parts[1:]
    if not components:
        raise ValueError(f"{label}_root_cannot_be_regular_file")
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    nofollow = os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0
    directory_descriptors: list[int] = []
    leaf_descriptor: int | None = None
    try:
        current_descriptor = os.open(
            checked_path.anchor,
            flags | nofollow | os.O_DIRECTORY,
        )
        directory_descriptors.append(current_descriptor)
        root_stat = os.fstat(current_descriptor)
        component_identities = [
            (
                Path(checked_path.anchor),
                root_stat.st_dev,
                root_stat.st_ino,
                stat.S_IFMT(root_stat.st_mode),
            )
        ]
        current_path = Path(checked_path.anchor)
        for component in components[:-1]:
            named = os.stat(
                component,
                dir_fd=current_descriptor,
                follow_symlinks=False,
            )
            child_descriptor = os.open(
                component,
                flags | nofollow | os.O_DIRECTORY,
                dir_fd=current_descriptor,
            )
            opened = os.fstat(child_descriptor)
            if (
                opened.st_dev,
                opened.st_ino,
                stat.S_IFMT(opened.st_mode),
            ) != (
                named.st_dev,
                named.st_ino,
                stat.S_IFMT(named.st_mode),
            ):
                os.close(child_descriptor)
                raise ValueError(f"{label}_component_changed:{current_path / component}")
            directory_descriptors.append(child_descriptor)
            current_descriptor = child_descriptor
            current_path = current_path / component
            component_identities.append(
                (
                    current_path,
                    opened.st_dev,
                    opened.st_ino,
                    stat.S_IFMT(opened.st_mode),
                )
            )
        leaf_name = components[-1]
        leaf_descriptor = os.open(
            leaf_name,
            flags | nofollow,
            dir_fd=current_descriptor,
        )
        before = os.fstat(leaf_descriptor)
        named_before = os.stat(
            leaf_name,
            dir_fd=current_descriptor,
            follow_symlinks=False,
        )
        before_tuple = (
            before.st_dev,
            before.st_ino,
            stat.S_IFMT(before.st_mode),
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        named_before_tuple = (
            named_before.st_dev,
            named_before.st_ino,
            stat.S_IFMT(named_before.st_mode),
            named_before.st_nlink,
            named_before.st_size,
            named_before.st_mtime_ns,
            named_before.st_ctime_ns,
        )
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before_tuple != named_before_tuple
        ):
            raise ValueError(f"{label}_identity_invalid")
        chunks = []
        digest = hashlib.sha256()
        byte_count = 0
        while True:
            chunk = os.read(leaf_descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            digest.update(chunk)
            byte_count += len(chunk)
        after = os.fstat(leaf_descriptor)
        after_tuple = (
            after.st_dev,
            after.st_ino,
            stat.S_IFMT(after.st_mode),
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        named_after = os.stat(
            leaf_name,
            dir_fd=current_descriptor,
            follow_symlinks=False,
        )
        named_after_tuple = (
            named_after.st_dev,
            named_after.st_ino,
            stat.S_IFMT(named_after.st_mode),
            named_after.st_nlink,
            named_after.st_size,
            named_after.st_mtime_ns,
            named_after.st_ctime_ns,
        )
        if (
            before_tuple != after_tuple
            or after_tuple != named_after_tuple
            or byte_count != after.st_size
        ):
            raise ValueError(f"{label}_identity_changed")
        _verify_pinned_path_components(component_identities, label=label)
        payload = b"".join(chunks)
        if expected_bytes is not None and payload != expected_bytes:
            raise ValueError(f"{label}_bytes_mismatch")
        return {
            "path": str(checked_path),
            "byte_count": byte_count,
            "sha256": digest.hexdigest(),
            "device": after.st_dev,
            "inode": after.st_ino,
            "file_type": "regular_non_symlink",
            "link_count": after.st_nlink,
        }
    except OSError as exc:
        raise ValueError(
            f"{label}_unreadable:{type(exc).__name__}:{exc}"
        ) from exc
    finally:
        if leaf_descriptor is not None:
            os.close(leaf_descriptor)
        for descriptor in reversed(directory_descriptors):
            os.close(descriptor)


def _path_identity_from_file_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "real_path": str(evidence["path"]),
        "file_type": str(evidence["file_type"]),
        "device": int(evidence["device"]),
        "inode": int(evidence["inode"]),
        "link_count": int(evidence["link_count"]),
    }


def _capture_baseline_record(
    role: str,
    path: str | os.PathLike[str],
) -> dict[str, Any]:
    evidence = _read_pinned_regular_file_evidence(
        path,
        label=f"capture_baseline_{role}",
    )
    return {
        "role": role,
        "path": evidence["path"],
        "sha256": evidence["sha256"],
        "device": evidence["device"],
        "inode": evidence["inode"],
        "file_type": evidence["file_type"],
        "link_count": evidence["link_count"],
    }


def build_capture_persistent_layer_baseline(
    *,
    source_path: str | os.PathLike[str],
    presentation_path: str | os.PathLike[str],
    static_entry_path: str | os.PathLike[str],
    expected_source: Mapping[str, Any] | None = None,
    expected_presentation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    files = sorted(
        (
            _capture_baseline_record("source", source_path),
            _capture_baseline_record("presentation", presentation_path),
            _capture_baseline_record("static_entry", static_entry_path),
        ),
        key=lambda record: record["path"],
    )
    by_role = {record["role"]: record for record in files}
    for role, expected in (
        ("source", expected_source),
        ("presentation", expected_presentation),
    ):
        if expected is None:
            continue
        record = by_role[role]
        expected_path = expected.get("path", expected.get("real_path"))
        expected_fields = set(expected)
        if (
            expected_fields
            not in (
                {"path", "sha256", "device", "inode", "file_type", "link_count"},
                {
                    "real_path",
                    "sha256",
                    "device",
                    "inode",
                    "file_type",
                    "link_count",
                },
            )
            or any(
                record[field] != expected[field]
                for field in ("sha256", "device", "inode", "file_type", "link_count")
            )
            or record["path"] != expected_path
        ):
            raise ValueError(
                f"capture_persistent_layer_baseline_handoff_mismatch:{role}"
            )
    payload = {
        "schema_version": 1,
        "contract_id": "capture_persistent_layer_baseline_v1",
        "files": files,
    }
    return {**payload, "baseline_sha256": canonical_json_sha256_v1(payload)}


def validate_capture_persistent_layer_baseline(
    baseline: Mapping[str, Any],
) -> dict[str, Any]:
    fields = {"schema_version", "contract_id", "files", "baseline_sha256"}
    record_fields = {
        "role",
        "path",
        "sha256",
        "device",
        "inode",
        "file_type",
        "link_count",
    }
    if not isinstance(baseline, Mapping) or set(baseline) != fields:
        raise ValueError("capture_persistent_layer_baseline_schema_invalid")
    actual = _json_native_copy(dict(baseline))
    files = actual.get("files")
    payload = {key: actual[key] for key in ("schema_version", "contract_id", "files")}
    if (
        actual.get("schema_version") != 1
        or actual.get("contract_id") != "capture_persistent_layer_baseline_v1"
        or not isinstance(files, list)
        or len(files) != 3
        or files != sorted(files, key=lambda record: record.get("path", ""))
        or {record.get("role") for record in files if isinstance(record, Mapping)}
        != {"source", "presentation", "static_entry"}
        or any(
            not isinstance(record, Mapping)
            or set(record) != record_fields
            or not isinstance(record.get("path"), str)
            or not Path(record["path"]).is_absolute()
            or not _is_sha256_text(record.get("sha256"))
            or type(record.get("device")) is not int
            or type(record.get("inode")) is not int
            or record.get("file_type") != "regular_non_symlink"
            or record.get("link_count") != 1
            for record in files
        )
        or actual.get("baseline_sha256") != canonical_json_sha256_v1(payload)
    ):
        raise ValueError("capture_persistent_layer_baseline_invalid")
    return actual


def _snapshot_pinned_regular_tree(
    root: str | os.PathLike[str],
    *,
    label: str,
) -> tuple[Path, list[dict[str, Any]]]:
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    def walk(
        directory_descriptor: int,
        relative_parent: Path,
        absolute_parent: Path,
    ) -> list[dict[str, Any]]:
        names_before = sorted(os.listdir(directory_descriptor))
        records = []
        for name in names_before:
            named = os.stat(
                name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            relative = relative_parent / name
            absolute = absolute_parent / name
            if stat.S_ISLNK(named.st_mode):
                raise ValueError(f"{label}_symlink_rejected:{absolute}")
            if stat.S_ISDIR(named.st_mode):
                child_descriptor = os.open(
                    name,
                    flags,
                    dir_fd=directory_descriptor,
                )
                try:
                    opened = os.fstat(child_descriptor)
                    if (opened.st_dev, opened.st_ino) != (
                        named.st_dev,
                        named.st_ino,
                    ):
                        raise ValueError(f"{label}_changed:{absolute}")
                    records.extend(
                        walk(child_descriptor, relative, absolute)
                    )
                    named_after = os.stat(
                        name,
                        dir_fd=directory_descriptor,
                        follow_symlinks=False,
                    )
                    if (named_after.st_dev, named_after.st_ino) != (
                        opened.st_dev,
                        opened.st_ino,
                    ):
                        raise ValueError(f"{label}_changed:{absolute}")
                finally:
                    os.close(child_descriptor)
                continue
            if not stat.S_ISREG(named.st_mode):
                raise ValueError(f"{label}_nonregular_rejected:{absolute}")
            file_flags = os.O_RDONLY
            if hasattr(os, "O_CLOEXEC"):
                file_flags |= os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                file_flags |= os.O_NOFOLLOW
            file_descriptor = os.open(
                name,
                file_flags,
                dir_fd=directory_descriptor,
            )
            try:
                opened = os.fstat(file_descriptor)
                if (opened.st_dev, opened.st_ino) != (
                    named.st_dev,
                    named.st_ino,
                ):
                    raise ValueError(f"{label}_changed:{absolute}")
                evidence = _hash_open_regular_file(
                    file_descriptor,
                    label=label,
                )
                named_after = os.stat(
                    name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
                if (named_after.st_dev, named_after.st_ino) != (
                    evidence["device"],
                    evidence["inode"],
                ):
                    raise ValueError(f"{label}_changed:{absolute}")
            finally:
                os.close(file_descriptor)
            records.append(
                {
                    "path": relative.as_posix(),
                    "byte_count": evidence["byte_count"],
                    "sha256": evidence["sha256"],
                }
            )
        if sorted(os.listdir(directory_descriptor)) != names_before:
            raise ValueError(f"{label}_membership_changed:{absolute_parent}")
        return records

    with _open_pinned_path(
        root,
        leaf_directory=True,
        label=label,
    ) as (checked_root, descriptor, identities):
        records = walk(descriptor, Path(), checked_root)
        _verify_pinned_path_components(identities, label=label)
    return checked_root, sorted(records, key=lambda record: record["path"])


def _snapshot_pinned_direct_files(
    root: str | os.PathLike[str],
    *,
    suffix: str,
    label: str,
) -> tuple[Path, list[dict[str, str]]]:
    file_flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        file_flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        file_flags |= os.O_NOFOLLOW
    with _open_pinned_path(
        root,
        leaf_directory=True,
        label=label,
    ) as (checked_root, descriptor, identities):
        names_before = sorted(os.listdir(descriptor))
        records = []
        for name in names_before:
            if not name.endswith(suffix):
                continue
            named = os.stat(
                name,
                dir_fd=descriptor,
                follow_symlinks=False,
            )
            if stat.S_ISLNK(named.st_mode) or not stat.S_ISREG(named.st_mode):
                raise ValueError(f"{label}_member_invalid:{checked_root / name}")
            file_descriptor = os.open(name, file_flags, dir_fd=descriptor)
            try:
                opened = os.fstat(file_descriptor)
                if (opened.st_dev, opened.st_ino) != (
                    named.st_dev,
                    named.st_ino,
                ):
                    raise ValueError(
                        f"{label}_member_changed:{checked_root / name}"
                    )
                evidence = _hash_open_regular_file(
                    file_descriptor,
                    label=label,
                )
                named_after = os.stat(
                    name,
                    dir_fd=descriptor,
                    follow_symlinks=False,
                )
                if (named_after.st_dev, named_after.st_ino) != (
                    evidence["device"],
                    evidence["inode"],
                ):
                    raise ValueError(
                        f"{label}_member_changed:{checked_root / name}"
                    )
            finally:
                os.close(file_descriptor)
            records.append({"name": name, "sha256": evidence["sha256"]})
        if sorted(os.listdir(descriptor)) != names_before:
            raise ValueError(f"{label}_membership_changed:{checked_root}")
        _verify_pinned_path_components(identities, label=label)
    return checked_root, records


def _pinned_directory_entries(
    root: str | os.PathLike[str],
    *,
    label: str,
) -> tuple[dict[str, str], ...]:
    with _open_pinned_path(
        root,
        leaf_directory=True,
        label=label,
    ) as (_root, descriptor, identities):
        names_before = sorted(os.listdir(descriptor))
        entries = []
        for name in names_before:
            metadata = os.stat(
                name,
                dir_fd=descriptor,
                follow_symlinks=False,
            )
            file_type = stat.S_IFMT(metadata.st_mode)
            kind = (
                "file"
                if file_type == stat.S_IFREG
                else "directory"
                if file_type == stat.S_IFDIR
                else "symlink"
                if file_type == stat.S_IFLNK
                else "other"
            )
            entries.append({"name": name, "kind": kind})
        if sorted(os.listdir(descriptor)) != names_before:
            raise ValueError(f"{label}_membership_changed")
        _verify_pinned_path_components(identities, label=label)
    return tuple(entries)


def _validate_pinned_readonly_tree_modes(
    root: str | os.PathLike[str],
    *,
    label: str,
) -> None:
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    def walk(descriptor: int, display_path: Path) -> None:
        directory_stat = os.fstat(descriptor)
        if (directory_stat.st_mode & 0o222) != 0:
            raise ValueError(f"{label}_directory_mode_invalid:{display_path}")
        names_before = sorted(os.listdir(descriptor))
        for name in names_before:
            named = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            child_path = display_path / name
            if stat.S_ISLNK(named.st_mode):
                raise ValueError(f"{label}_symlink:{child_path}")
            if stat.S_ISDIR(named.st_mode):
                child = os.open(name, flags, dir_fd=descriptor)
                try:
                    opened = os.fstat(child)
                    if (opened.st_dev, opened.st_ino) != (
                        named.st_dev,
                        named.st_ino,
                    ):
                        raise ValueError(f"{label}_changed:{child_path}")
                    walk(child, child_path)
                finally:
                    os.close(child)
                continue
            if not stat.S_ISREG(named.st_mode):
                raise ValueError(f"{label}_nonregular:{child_path}")
            if (named.st_mode & 0o222) != 0:
                raise ValueError(f"{label}_member_mode_invalid:{child_path}")
        if sorted(os.listdir(descriptor)) != names_before:
            raise ValueError(f"{label}_membership_changed:{display_path}")

    with _open_pinned_path(
        root,
        leaf_directory=True,
        label=label,
    ) as (checked_root, descriptor, identities):
        walk(descriptor, checked_root)
        _verify_pinned_path_components(identities, label=label)


def _atomic_rename_noreplace(
    source: str | os.PathLike[str],
    target: str | os.PathLike[str],
) -> None:
    source_path = _reject_symlink_path_components(
        source,
        label="atomic_rename_source",
    )
    target_path = _reject_symlink_path_components(
        target,
        label="atomic_rename_target",
    )
    with _open_pinned_path(
        source_path.parent,
        leaf_directory=True,
        label="atomic_rename_source_parent",
    ) as (_source_parent, source_descriptor, source_identities):
        with _open_pinned_path(
            target_path.parent,
            leaf_directory=True,
            label="atomic_rename_target_parent",
        ) as (_target_parent, target_descriptor, target_identities):
            source_stat = os.stat(
                source_path.name,
                dir_fd=source_descriptor,
                follow_symlinks=False,
            )
            libc = ctypes.CDLL(None, use_errno=True)
            renameat2 = getattr(libc, "renameat2", None)
            if renameat2 is None:
                result = -1
                error = errno.ENOSYS
            else:
                renameat2.argtypes = (
                    ctypes.c_int,
                    ctypes.c_char_p,
                    ctypes.c_int,
                    ctypes.c_char_p,
                    ctypes.c_uint,
                )
                renameat2.restype = ctypes.c_int
                result = renameat2(
                    source_descriptor,
                    os.fsencode(source_path.name),
                    target_descriptor,
                    os.fsencode(target_path.name),
                    1,
                )
                error = ctypes.get_errno() if result != 0 else 0
            if result != 0:
                if error in {errno.EEXIST, errno.ENOTEMPTY}:
                    raise FileExistsError(
                        error,
                        os.strerror(error),
                        str(target_path),
                    )
                compatibility_errors = {
                    errno.EINVAL,
                    errno.ENOSYS,
                    getattr(errno, "EOPNOTSUPP", errno.ENOTSUP),
                }
                if error not in compatibility_errors:
                    raise OSError(
                        error,
                        os.strerror(error),
                        str(target_path),
                    )
                if not stat.S_ISDIR(source_stat.st_mode):
                    raise OSError(
                        errno.EOPNOTSUPP,
                        "atomic rename compatibility requires a directory",
                        str(source_path),
                    )
                try:
                    os.mkdir(
                        target_path.name,
                        mode=0o700,
                        dir_fd=target_descriptor,
                    )
                except FileExistsError:
                    raise FileExistsError(
                        errno.EEXIST,
                        os.strerror(errno.EEXIST),
                        str(target_path),
                    )
                reservation_stat = os.stat(
                    target_path.name,
                    dir_fd=target_descriptor,
                    follow_symlinks=False,
                )
                os.fsync(target_descriptor)
                _verify_pinned_path_components(
                    source_identities,
                    label="atomic_rename_source_parent",
                )
                _verify_pinned_path_components(
                    target_identities,
                    label="atomic_rename_target_parent",
                )
                try:
                    reservation_flags = os.O_RDONLY | os.O_DIRECTORY
                    if hasattr(os, "O_NOFOLLOW"):
                        reservation_flags |= os.O_NOFOLLOW
                    reservation_descriptor = os.open(
                        target_path.name,
                        reservation_flags,
                        dir_fd=target_descriptor,
                    )
                    try:
                        pinned_reservation = os.fstat(reservation_descriptor)
                        if (
                            not stat.S_ISDIR(pinned_reservation.st_mode)
                            or (
                                pinned_reservation.st_dev,
                                pinned_reservation.st_ino,
                            )
                            != (
                                reservation_stat.st_dev,
                                reservation_stat.st_ino,
                            )
                            or os.listdir(reservation_descriptor)
                        ):
                            raise OSError(
                                errno.ENOTEMPTY,
                                "atomic rename reservation changed or nonempty",
                                str(target_path),
                            )
                    finally:
                        os.close(reservation_descriptor)
                    os.rename(
                        source_path.name,
                        target_path.name,
                        src_dir_fd=source_descriptor,
                        dst_dir_fd=target_descriptor,
                    )
                except BaseException:
                    try:
                        current_reservation = os.stat(
                            target_path.name,
                            dir_fd=target_descriptor,
                            follow_symlinks=False,
                        )
                        if (
                            stat.S_ISDIR(current_reservation.st_mode)
                            and (
                                current_reservation.st_dev,
                                current_reservation.st_ino,
                            )
                            == (
                                reservation_stat.st_dev,
                                reservation_stat.st_ino,
                            )
                        ):
                            cleanup_flags = os.O_RDONLY | os.O_DIRECTORY
                            if hasattr(os, "O_NOFOLLOW"):
                                cleanup_flags |= os.O_NOFOLLOW
                            cleanup_descriptor = os.open(
                                target_path.name,
                                cleanup_flags,
                                dir_fd=target_descriptor,
                            )
                            try:
                                cleanup_stat = os.fstat(cleanup_descriptor)
                                cleanup_allowed = (
                                    (
                                        cleanup_stat.st_dev,
                                        cleanup_stat.st_ino,
                                    )
                                    == (
                                        reservation_stat.st_dev,
                                        reservation_stat.st_ino,
                                    )
                                    and not os.listdir(cleanup_descriptor)
                                )
                            finally:
                                os.close(cleanup_descriptor)
                            if cleanup_allowed:
                                os.rmdir(
                                    target_path.name,
                                    dir_fd=target_descriptor,
                                )
                                os.fsync(target_descriptor)
                    except (FileNotFoundError, OSError):
                        pass
                    raise
            target_stat = os.stat(
                target_path.name,
                dir_fd=target_descriptor,
                follow_symlinks=False,
            )
            if (target_stat.st_dev, target_stat.st_ino) != (
                source_stat.st_dev,
                source_stat.st_ino,
            ):
                raise RuntimeError("atomic_rename_published_identity_mismatch")
            os.fsync(source_descriptor)
            if (source_descriptor != target_descriptor):
                os.fsync(target_descriptor)
            _verify_pinned_path_components(
                source_identities,
                label="atomic_rename_source_parent",
            )
            _verify_pinned_path_components(
                target_identities,
                label="atomic_rename_target_parent",
            )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _render_diagnostic_lock_path() -> Path:
    configured = _absolute_path_without_symlink_resolution(
        RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH
    )
    root = _absolute_path_without_symlink_resolution(
        RENDER_DIAGNOSTIC_AGGREGATE_ROOT
    )
    if (
        configured
        == _absolute_path_without_symlink_resolution(
            _RENDER_DIAGNOSTIC_CANONICAL_LOCK_PATH
        )
        and root
        != _absolute_path_without_symlink_resolution(
            _RENDER_DIAGNOSTIC_CANONICAL_AGGREGATE_ROOT
        )
    ):
        return root.parent / f".{root.name}.aggregate.lock"
    return configured


def _render_diagnostic_anchor_slots() -> list[dict[str, Any]]:
    return [
        {
            "sequence_index": sequence_index,
            "variant": slot["variant"],
            "replicate": slot["replicate"],
            "execution_order_index": slot["execution_order_index"],
            "cell_name": slot["cell_name"],
        }
        for sequence_index, slot in enumerate(render_diagnostic_slots())
    ]


_RENDER_DIAGNOSTIC_ANCHOR_FIELDS = frozenset(
    {
        "schema_version",
        "experiment_id",
        "aggregate_root",
        "aggregate_root_device",
        "aggregate_root_inode",
        "lock_path",
        "lock_device",
        "lock_inode",
        "implementation_identity_sha256",
        "implementation_identity_path",
        "pre_freeze_path",
        "post_freeze_path",
        "pre_freeze_sha256",
        "canonical_slots",
        "experiment_binding_sha256",
        "anchor_sha256",
    }
)


def build_render_diagnostic_experiment_anchor(
    *,
    aggregate_root: Path,
    lock_descriptor: int,
    implementation_identity_sha256: str,
    pre_freeze_sha256: str,
) -> dict[str, Any]:
    root = _reject_symlink_path_components(
        aggregate_root,
        label="render_diagnostic_anchor_root",
    )
    root_stat = os.stat(root, follow_symlinks=False)
    lock_stat = os.fstat(lock_descriptor)
    if (
        not stat.S_ISDIR(root_stat.st_mode)
        or not stat.S_ISREG(lock_stat.st_mode)
        or not _is_sha256_text(implementation_identity_sha256)
        or not _is_sha256_text(pre_freeze_sha256)
    ):
        raise ValueError("render_diagnostic_anchor_input_invalid")
    anchor_projection = {
        "schema_version": 1,
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "aggregate_root": str(
            _absolute_path_without_symlink_resolution(
                RENDER_DIAGNOSTIC_AGGREGATE_ROOT
            )
        ),
        "aggregate_root_device": root_stat.st_dev,
        "aggregate_root_inode": root_stat.st_ino,
        "lock_path": str(
            _render_diagnostic_lock_path()
        ),
        "lock_device": lock_stat.st_dev,
        "lock_inode": lock_stat.st_ino,
        "implementation_identity_sha256": implementation_identity_sha256,
        "implementation_identity_path": str(
            _absolute_path_without_symlink_resolution(
                RENDER_DIAGNOSTIC_IMPLEMENTATION_FREEZE_PATH
            )
        ),
        "pre_freeze_path": str(
            _absolute_path_without_symlink_resolution(
                RENDER_DIAGNOSTIC_PRE_FREEZE_PATH
            )
        ),
        "post_freeze_path": str(
            _absolute_path_without_symlink_resolution(
                RENDER_DIAGNOSTIC_POST_FREEZE_PATH
            )
        ),
        "pre_freeze_sha256": pre_freeze_sha256,
        "canonical_slots": _render_diagnostic_anchor_slots(),
    }
    binding_payload = {
        "schema_version": 1,
        "record_type": "EXPERIMENT_BINDING",
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "aggregate_root": anchor_projection["aggregate_root"],
        "aggregate_root_device": root_stat.st_dev,
        "aggregate_root_inode": root_stat.st_ino,
        "lock_device": lock_stat.st_dev,
        "lock_inode": lock_stat.st_ino,
        "anchor_projection_sha256": canonical_json_sha256_v1(
            anchor_projection
        ),
    }
    payload = {
        **anchor_projection,
        "experiment_binding_sha256": canonical_json_sha256_v1(
            binding_payload
        ),
    }
    return {
        **payload,
        "anchor_sha256": canonical_json_sha256_v1(payload),
    }


def validate_render_diagnostic_experiment_anchor(
    anchor: Mapping[str, Any],
    *,
    expected_root: str | os.PathLike[str] | None = None,
    expected_lock_path: str | os.PathLike[str] | None = None,
    verify_live_identity: bool = True,
) -> dict[str, Any]:
    if not isinstance(anchor, Mapping) or set(anchor) != set(
        _RENDER_DIAGNOSTIC_ANCHOR_FIELDS
    ):
        raise ValueError("render_diagnostic_anchor_schema_invalid")
    actual = _json_native_copy(dict(anchor))
    root = _absolute_path_without_symlink_resolution(
        expected_root or RENDER_DIAGNOSTIC_AGGREGATE_ROOT
    )
    lock_path = _absolute_path_without_symlink_resolution(
        expected_lock_path or _render_diagnostic_lock_path()
    )
    hash_payload = {
        key: value for key, value in actual.items() if key != "anchor_sha256"
    }
    projection_payload = {
        key: value
        for key, value in actual.items()
        if key not in {"anchor_sha256", "experiment_binding_sha256"}
    }
    binding_hash_payload = {
        "schema_version": 1,
        "record_type": "EXPERIMENT_BINDING",
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "aggregate_root": str(root),
        "aggregate_root_device": actual.get("aggregate_root_device"),
        "aggregate_root_inode": actual.get("aggregate_root_inode"),
        "lock_device": actual.get("lock_device"),
        "lock_inode": actual.get("lock_inode"),
        "anchor_projection_sha256": canonical_json_sha256_v1(
            projection_payload
        ),
    }
    int_fields = (
        "aggregate_root_device",
        "aggregate_root_inode",
        "lock_device",
        "lock_inode",
    )
    if (
        actual.get("schema_version") != 1
        or actual.get("experiment_id") != RENDER_DIAGNOSTIC_EXPERIMENT_ID
        or actual.get("aggregate_root") != str(root)
        or actual.get("lock_path") != str(lock_path)
        or any(type(actual.get(field)) is not int for field in int_fields)
        or any(actual[field] < 0 for field in int_fields)
        or not _is_sha256_text(
            actual.get("implementation_identity_sha256")
        )
        or not _is_sha256_text(actual.get("pre_freeze_sha256"))
        or actual.get("experiment_binding_sha256")
        != canonical_json_sha256_v1(binding_hash_payload)
        or actual.get("implementation_identity_path")
        != str(
            _absolute_path_without_symlink_resolution(
                RENDER_DIAGNOSTIC_IMPLEMENTATION_FREEZE_PATH
            )
        )
        or actual.get("pre_freeze_path")
        != str(
            _absolute_path_without_symlink_resolution(
                RENDER_DIAGNOSTIC_PRE_FREEZE_PATH
            )
        )
        or actual.get("post_freeze_path")
        != str(
            _absolute_path_without_symlink_resolution(
                RENDER_DIAGNOSTIC_POST_FREEZE_PATH
            )
        )
        or actual.get("canonical_slots") != _render_diagnostic_anchor_slots()
        or actual.get("anchor_sha256")
        != canonical_json_sha256_v1(hash_payload)
    ):
        raise ValueError("render_diagnostic_anchor_contract_invalid")
    if verify_live_identity:
        checked_root = _reject_symlink_path_components(
            root,
            label="render_diagnostic_anchor_live_root",
        )
        checked_lock = _reject_symlink_path_components(
            lock_path,
            label="render_diagnostic_anchor_live_lock",
        )
        root_stat = os.stat(checked_root, follow_symlinks=False)
        lock_stat = os.stat(checked_lock, follow_symlinks=False)
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or not stat.S_ISREG(lock_stat.st_mode)
            or (root_stat.st_dev, root_stat.st_ino)
            != (
                actual["aggregate_root_device"],
                actual["aggregate_root_inode"],
            )
            or (lock_stat.st_dev, lock_stat.st_ino)
            != (actual["lock_device"], actual["lock_inode"])
        ):
            raise ValueError("render_diagnostic_anchor_live_identity_invalid")
    return actual


_RENDER_DIAGNOSTIC_EXPERIMENT_BINDING_FIELDS = frozenset(
    {
        "schema_version",
        "record_type",
        "experiment_id",
        "aggregate_root",
        "aggregate_root_device",
        "aggregate_root_inode",
        "lock_device",
        "lock_inode",
        "anchor_projection_sha256",
        "generated_at_utc",
        "experiment_binding_sha256",
    }
)
_RENDER_DIAGNOSTIC_AUTHORITY_WITNESS_FIELDS = frozenset(
    {
        "schema_version",
        "record_type",
        "experiment_id",
        "experiment_binding_sha256",
        "authority_path",
        "authority_device",
        "authority_inode",
        "lock_device",
        "lock_inode",
        "publication_intent_sha256",
        "decision_sha256",
        "decision_commit_sha256",
        "closure_snapshot_sha256",
        "publication_nonce",
        "generated_at_utc",
        "authority_witness_sha256",
    }
)


def build_render_diagnostic_experiment_binding(
    anchor: Mapping[str, Any],
    *,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    validated = validate_render_diagnostic_experiment_anchor(
        anchor,
        expected_root=anchor.get("aggregate_root"),
        expected_lock_path=anchor.get("lock_path"),
        verify_live_identity=False,
    )
    projection = {
        key: value
        for key, value in validated.items()
        if key not in {"anchor_sha256", "experiment_binding_sha256"}
    }
    payload = {
        "schema_version": 1,
        "record_type": "EXPERIMENT_BINDING",
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "aggregate_root": validated["aggregate_root"],
        "aggregate_root_device": validated["aggregate_root_device"],
        "aggregate_root_inode": validated["aggregate_root_inode"],
        "lock_device": validated["lock_device"],
        "lock_inode": validated["lock_inode"],
        "anchor_projection_sha256": canonical_json_sha256_v1(projection),
        "generated_at_utc": generated_at_utc or _utc_now(),
    }
    hash_payload = {
        key: value for key, value in payload.items() if key != "generated_at_utc"
    }
    binding = {
        **payload,
        "experiment_binding_sha256": canonical_json_sha256_v1(hash_payload),
    }
    if binding["experiment_binding_sha256"] != validated[
        "experiment_binding_sha256"
    ]:
        raise ValueError("experiment_binding_anchor_mismatch")
    return binding


def _compact_json_line(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def validate_render_diagnostic_lock_journal(
    lock: int | str | os.PathLike[str],
    *,
    anchor: Mapping[str, Any],
    authority_required: bool,
) -> dict[str, Any]:
    if type(authority_required) is not bool:
        raise ValueError("lock_journal_authority_required_invalid")
    validated_anchor = validate_render_diagnostic_experiment_anchor(
        anchor,
        expected_root=anchor.get("aggregate_root"),
        expected_lock_path=anchor.get("lock_path"),
        verify_live_identity=False,
    )
    close_descriptor = False
    if type(lock) is int:
        descriptor = lock
    else:
        path = _reject_symlink_path_components(lock, label="lock_journal")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        close_descriptor = True
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or (metadata.st_dev, metadata.st_ino)
            != (validated_anchor["lock_device"], validated_anchor["lock_inode"])
        ):
            raise ValueError("lock_journal_identity_invalid")
        payload = os.pread(descriptor, metadata.st_size, 0)
    finally:
        if close_descriptor:
            os.close(descriptor)
    try:
        raw_lines = payload.splitlines(keepends=True)
        if b"".join(raw_lines) != payload or any(
            not line.endswith(b"\n") for line in raw_lines
        ):
            raise ValueError("lock_journal_line_encoding_invalid")
        records = [json.loads(line) for line in raw_lines]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("lock_journal_json_invalid") from exc
    expected_count = 2 if authority_required else 1
    if len(records) != expected_count:
        raise ValueError("lock_journal_record_count_invalid")
    binding = records[0]
    if (
        not isinstance(binding, Mapping)
        or set(binding) != set(_RENDER_DIAGNOSTIC_EXPERIMENT_BINDING_FIELDS)
    ):
        raise ValueError("experiment_binding_schema_invalid")
    expected_binding = build_render_diagnostic_experiment_binding(
        validated_anchor,
        generated_at_utc=binding.get("generated_at_utc"),
    )
    if binding != expected_binding or _compact_json_line(binding) != raw_lines[0]:
        raise ValueError("experiment_binding_invalid")
    witness = None
    if authority_required:
        witness = records[1]
        if (
            not isinstance(witness, Mapping)
            or set(witness) != set(_RENDER_DIAGNOSTIC_AUTHORITY_WITNESS_FIELDS)
        ):
            raise ValueError("authority_witness_schema_invalid")
        witness_hash_payload = {
            key: value
            for key, value in witness.items()
            if key not in {"generated_at_utc", "authority_witness_sha256"}
        }
        if (
            witness.get("schema_version") != 1
            or witness.get("record_type") != "AUTHORITY_WITNESS"
            or witness.get("experiment_id") != RENDER_DIAGNOSTIC_EXPERIMENT_ID
            or witness.get("experiment_binding_sha256")
            != binding["experiment_binding_sha256"]
            or witness.get("lock_device") != validated_anchor["lock_device"]
            or witness.get("lock_inode") != validated_anchor["lock_inode"]
            or any(
                type(witness.get(field)) is not int or witness[field] < 0
                for field in ("authority_device", "authority_inode")
            )
            or any(
                not _is_sha256_text(witness.get(field))
                for field in (
                    "publication_intent_sha256",
                    "decision_sha256",
                    "decision_commit_sha256",
                )
            )
            or (
                witness.get("closure_snapshot_sha256") is not None
                and not _is_sha256_text(
                    witness.get("closure_snapshot_sha256")
                )
            )
            or not isinstance(witness.get("publication_nonce"), str)
            or len(witness["publication_nonce"]) != 64
            or any(
                character not in "0123456789abcdef"
                for character in witness["publication_nonce"]
            )
            or not isinstance(witness.get("generated_at_utc"), str)
            or not witness["generated_at_utc"]
            or witness.get("authority_witness_sha256")
            != canonical_json_sha256_v1(witness_hash_payload)
            or _compact_json_line(witness) != raw_lines[1]
        ):
            raise ValueError("authority_witness_invalid")
    return {
        "experiment_binding": _json_native_copy(binding),
        "authority_witness": (
            _json_native_copy(witness) if authority_required else None
        ),
        "byte_count": len(payload),
    }


def write_render_diagnostic_experiment_binding(
    lock_descriptor: int,
    *,
    anchor: Mapping[str, Any],
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    metadata = os.fstat(lock_descriptor)
    if metadata.st_size != 0:
        raise ValueError("experiment_binding_lock_not_empty")
    binding = build_render_diagnostic_experiment_binding(
        anchor,
        generated_at_utc=generated_at_utc,
    )
    encoded = _compact_json_line(binding)
    written = os.pwrite(lock_descriptor, encoded, 0)
    if written != len(encoded):
        raise OSError("experiment_binding_short_write")
    os.fsync(lock_descriptor)
    validate_render_diagnostic_lock_journal(
        lock_descriptor,
        anchor=anchor,
        authority_required=False,
    )
    return binding


@contextmanager
def acquire_render_diagnostic_experiment_lock():
    lock_path = _reject_symlink_path_components(
        _render_diagnostic_lock_path(),
        label="render_diagnostic_aggregate_lock",
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    with _open_pinned_path(
        lock_path.parent,
        leaf_directory=True,
        label="render_diagnostic_aggregate_lock_parent",
    ) as (_parent, parent_descriptor, identities):
        try:
            descriptor = os.open(
                lock_path.name,
                flags | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=parent_descriptor,
            )
        except FileExistsError:
            descriptor = os.open(
                lock_path.name,
                flags,
                dir_fd=parent_descriptor,
            )
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("render_diagnostic_aggregate_lock_not_regular")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError(
                    "render_diagnostic_aggregate_already_running"
                ) from exc
            path_metadata = os.stat(
                lock_path.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (path_metadata.st_dev, path_metadata.st_ino) != (
                metadata.st_dev,
                metadata.st_ino,
            ):
                raise ValueError("render_diagnostic_aggregate_lock_replaced")
            aggregate_root = _absolute_path_without_symlink_resolution(
                RENDER_DIAGNOSTIC_AGGREGATE_ROOT
            )
            if metadata.st_size == 0:
                if aggregate_root.exists() or aggregate_root.is_symlink():
                    raise ValueError("render_diagnostic_empty_lock_with_root")
            else:
                if not aggregate_root.is_dir() or aggregate_root.is_symlink():
                    raise ValueError("render_diagnostic_bound_lock_without_root")
                bound_anchor = _load_json_object(
                    aggregate_root / RENDER_DIAGNOSTIC_ANCHOR_BASENAME,
                    label="render_diagnostic_bound_lock_anchor",
                )
                lock_payload = os.pread(descriptor, metadata.st_size, 0)
                authority_required = lock_payload.count(b"\n") == 2
                validate_render_diagnostic_lock_journal(
                    descriptor,
                    anchor=bound_anchor,
                    authority_required=authority_required,
                )
            _verify_pinned_path_components(
                identities,
                label="render_diagnostic_aggregate_lock_parent",
            )
            yield descriptor
            path_metadata = os.stat(
                lock_path.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (path_metadata.st_dev, path_metadata.st_ino) != (
                metadata.st_dev,
                metadata.st_ino,
            ):
                raise ValueError("render_diagnostic_aggregate_lock_replaced")
            _verify_pinned_path_components(
                identities,
                label="render_diagnostic_aggregate_lock_parent",
            )
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


def render_diagnostic_runtime_child_subprocess_kwargs(
    *,
    lock_descriptor: int,
    archive_descriptor: int,
) -> dict[str, Any]:
    if (
        type(lock_descriptor) is not int
        or lock_descriptor < 0
        or type(archive_descriptor) is not int
        or archive_descriptor < 0
        or archive_descriptor == lock_descriptor
    ):
        raise ValueError("render_diagnostic_inherited_descriptor_invalid")
    return {
        "pass_fds": (lock_descriptor, archive_descriptor),
        "close_fds": True,
    }


def verify_render_diagnostic_inherited_lock_held(
    *,
    lock_descriptor: int,
    lock_path: str | os.PathLike[str],
) -> dict[str, int]:
    inherited = os.fstat(lock_descriptor)
    checked_path = _reject_symlink_path_components(
        lock_path,
        label="runtime_child_inherited_lock",
    )
    with _open_pinned_path(
        checked_path.parent,
        leaf_directory=True,
        label="runtime_child_lock_parent",
    ) as (_parent, parent_descriptor, identities):
        flags = os.O_RDWR
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        probe = os.open(
            checked_path.name,
            flags,
            dir_fd=parent_descriptor,
        )
        try:
            named = os.fstat(probe)
            if (named.st_dev, named.st_ino) != (
                inherited.st_dev,
                inherited.st_ino,
            ):
                raise ValueError("runtime_child_inherited_lock_inode_mismatch")
            try:
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                pass
            else:
                fcntl.flock(probe, fcntl.LOCK_UN)
                raise ValueError("runtime_child_inherited_lock_not_held")
            try:
                fcntl.flock(
                    lock_descriptor,
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
            except BlockingIOError as exc:
                raise ValueError(
                    "runtime_child_inherited_lock_not_held_by_descriptor"
                ) from exc
            _verify_pinned_path_components(
                identities,
                label="runtime_child_lock_parent",
            )
        finally:
            os.close(probe)
    return {"device": inherited.st_dev, "inode": inherited.st_ino}


def validate_runtime_child_invocation(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    runtime_child = bool(getattr(args, "runtime_child", False))
    parent_pid = getattr(args, "runtime_parent_pid", None)
    lock_descriptor = getattr(args, "runtime_parent_lock_fd", None)
    archive_descriptor = getattr(args, "runtime_parent_archive_fd", None)
    archive_sha256 = getattr(args, "runtime_parent_archive_sha256", None)
    bootstrap_sha256 = getattr(args, "runtime_bootstrap_sha256", None)
    if not runtime_child:
        if any(
            value is not None
            for value in (
                parent_pid,
                lock_descriptor,
                archive_descriptor,
                archive_sha256,
                bootstrap_sha256,
            )
        ):
            raise ValueError("runtime_child_parent_contract_without_child")
        return None
    if type(parent_pid) is not int or parent_pid <= 0 or parent_pid != os.getppid():
        raise ValueError("runtime_child_parent_contract_invalid")
    identity = validate_render_diagnostic_cell_scope(args)
    if identity is None:
        if any(
            value is not None
            for value in (
                lock_descriptor,
                archive_descriptor,
                archive_sha256,
                bootstrap_sha256,
            )
        ):
            raise ValueError("runtime_child_parent_contract_unexpected_lock")
        return {"parent_pid": parent_pid, "diagnostic": False}
    if (
        type(lock_descriptor) is not int
        or lock_descriptor < 0
        or type(archive_descriptor) is not int
        or archive_descriptor < 0
        or archive_descriptor == lock_descriptor
        or not _is_sha256_text(archive_sha256)
        or bootstrap_sha256 != RENDER_DIAGNOSTIC_RUNTIME_BOOTSTRAP_SHA256
    ):
        raise ValueError("runtime_child_parent_contract_lock_missing")
    try:
        descriptor_stat = os.fstat(lock_descriptor)
    except OSError as exc:
        raise ValueError("runtime_child_parent_contract_lock_invalid") from exc
    aggregate_root = _reject_symlink_path_components(
        RENDER_DIAGNOSTIC_AGGREGATE_ROOT,
        label="runtime_child_aggregate_root",
    )
    anchor = validate_render_diagnostic_experiment_anchor(
        _load_json_object(
            aggregate_root / RENDER_DIAGNOSTIC_ANCHOR_BASENAME,
            label="runtime_child_anchor",
        ),
        expected_root=aggregate_root,
        expected_lock_path=_render_diagnostic_lock_path(),
    )
    held_lock = verify_render_diagnostic_inherited_lock_held(
        lock_descriptor=lock_descriptor,
        lock_path=_render_diagnostic_lock_path(),
    )
    if (descriptor_stat.st_dev, descriptor_stat.st_ino) != (
        anchor["lock_device"],
        anchor["lock_inode"],
    ) or (held_lock["device"], held_lock["inode"]) != (
        anchor["lock_device"],
        anchor["lock_inode"],
    ):
        raise ValueError("runtime_child_parent_contract_lock_mismatch")
    slot = next(
        record
        for record in render_diagnostic_slots()
        if record["cell_name"] == Path(identity["cell_root"]).name
    )
    intent = _load_launch_intent(
        aggregate_root / "launch_intents" / f"{slot['cell_name']}.json",
        slot,
    )
    pre = verify_render_diagnostic_pre_freeze_unchanged()
    implementation = load_and_verify_frozen_matrix_implementation_identity()
    archive_contract = validate_render_diagnostic_sealed_archive_fd(
        archive_descriptor,
        expected_archive_sha256=archive_sha256,
    )
    archive_bytes = b"".join(
        os.pread(
            archive_descriptor,
            min(1024 * 1024, archive_contract["byte_count"] - offset),
            offset,
        )
        for offset in range(0, archive_contract["byte_count"], 1024 * 1024)
    )
    archive_evidence = {
        "schema_version": 1,
        "archive_id": "matrix_runtime_implementation_archive_v1",
        "source_files": _runtime_archive_source_records(implementation),
        "synthetic_files": [
            {"path": path, "sha256": hashlib.sha256(payload).hexdigest()}
            for path, payload in sorted(
                _RUNTIME_ARCHIVE_SYNTHETIC_ENTRIES.items()
            )
        ],
        "archive_sha256": archive_sha256,
    }
    archive_evidence = (
        validate_render_diagnostic_runtime_implementation_archive(
            archive_evidence,
            archive_bytes=archive_bytes,
            implementation_identity=implementation,
        )
    )
    if (
        intent["launcher_pid"] != parent_pid
        or intent["anchor_sha256"] != anchor["anchor_sha256"]
        or intent["pre_freeze_sha256"] != pre["sha256"]
        or intent["implementation_identity_sha256"]
        != implementation["implementation_identity_sha256"]
    ):
        raise ValueError("runtime_child_parent_contract_binding_invalid")
    inherited_fd_contract = {
        "schema_version": 1,
        "standard_fds": [0, 1, 2],
        "lock_fd": lock_descriptor,
        "archive_fd": archive_descriptor,
        "lock_access_mode": "READ_WRITE",
        "archive_access_mode": "READ_ONLY",
        "archive_seals": archive_contract["seals"],
    }
    args._runtime_implementation_archive = archive_evidence
    args._runtime_implementation_archive_bytes = archive_bytes
    args._inherited_fd_contract = inherited_fd_contract
    args._matrix_implementation_identity = deepcopy(implementation)
    return {
        "parent_pid": parent_pid,
        "diagnostic": True,
        "lock_descriptor": lock_descriptor,
        "archive_descriptor": archive_descriptor,
        "runtime_implementation_archive_sha256": canonical_json_sha256_v1(
            archive_evidence
        ),
        "inherited_fd_contract_sha256": canonical_json_sha256_v1(
            inherited_fd_contract
        ),
        "anchor_sha256": anchor["anchor_sha256"],
        "launch_intent_sha256": intent["launch_intent_sha256"],
    }


def build_effective_replay_look_contract(
    lighting_variant_id: str = LIGHTING_VARIANT_C_CONTROL,
    *,
    render_diagnostic_variant_id: str | None = None,
) -> dict[str, Any]:
    """Resolve one canonical replay look, including optional render diagnostics."""
    from tools.labutopia_fluid.presentation_look_profiles import (
        PRESENTATION_LOOK_WEEKLY_B,
        PRESENTATION_LOOK_WEEKLY_C,
        resolve_presentation_look_profile,
    )

    if lighting_variant_id not in ALLOWED_LIGHTING_VARIANTS:
        raise ValueError(
            f"effective_replay_lighting_variant_invalid:{lighting_variant_id!r}"
        )
    if (
        render_diagnostic_variant_id is not None
        and render_diagnostic_variant_id not in RENDER_DIAGNOSTIC_VARIANTS
    ):
        raise ValueError(
            "effective_replay_render_diagnostic_variant_invalid:"
            f"{render_diagnostic_variant_id!r}"
        )
    if (
        render_diagnostic_variant_id is not None
        and lighting_variant_id != LIGHTING_VARIANT_C_CONTROL
    ):
        raise ValueError("effective_replay_render_diagnostic_requires_c_lighting")
    ambient_occlusion_enabled, rt_subframes = (
        RENDER_DIAGNOSTIC_VARIANT_SETTINGS[render_diagnostic_variant_id]
        if render_diagnostic_variant_id is not None
        else (False, REPLAY_RT_SUBFRAMES)
    )
    base_profile = _json_native_copy(
        resolve_presentation_look_profile(PRESENTATION_LOOK_WEEKLY_C)
    )
    lighting_source_profile_id = (
        PRESENTATION_LOOK_WEEKLY_C
        if lighting_variant_id == LIGHTING_VARIANT_C_CONTROL
        else PRESENTATION_LOOK_WEEKLY_B
    )
    lighting_source_profile = _json_native_copy(
        resolve_presentation_look_profile(lighting_source_profile_id)
    )
    non_lighting = {
        "base_profile_id": PRESENTATION_LOOK_WEEKLY_C,
        "base_source_profile_sha256": _json_sha256(base_profile),
        "liquid_material": {
            "backend": base_profile["water_backend"],
            "mdl": base_profile["water_mdl"],
            "sub_identifier": base_profile["water_sub_identifier"],
            "material_hash": base_profile["material_hash"],
            "glass_color": base_profile["glass_color"],
            "reflection_color": base_profile["reflection_color"],
        },
        "native_beaker_material_retained": True,
        "profile_beaker_override_applied": False,
        "measured_replay_cameras_retained": True,
        "profile_camera_applied": False,
        "profile_postprocess_applied": False,
        "normal_remediation_id": BEAKER_NORMAL_REMEDIATION_ID,
        "normal_remediation_required": True,
        "normal_remediation_applied": True,
        "presentation_candidate_id": "OMNI_REF_DISPLAY_FILL",
        "render_settings": {
            "rt_subframes": rt_subframes,
            "max_refraction_bounces": REPLAY_MAX_REFRACTION_BOUNCES,
            "max_refraction_bounces_setting_path": (
                REPLAY_REFRACTION_SETTING_PATH
            ),
            "ambient_occlusion_enabled": ambient_occlusion_enabled,
            "ambient_occlusion_setting_path": (
                REPLAY_AMBIENT_OCCLUSION_SETTING_PATH
            ),
            "ambient_occlusion_ray_length": 5.0,
            "ambient_occlusion_ray_length_setting_path": (
                REPLAY_AMBIENT_OCCLUSION_RAY_LENGTH_SETTING_PATH
            ),
            "ambient_occlusion_min_samples": 8,
            "ambient_occlusion_min_samples_setting_path": (
                REPLAY_AMBIENT_OCCLUSION_MIN_SAMPLES_SETTING_PATH
            ),
            "ambient_occlusion_max_samples": 16,
            "ambient_occlusion_max_samples_setting_path": (
                REPLAY_AMBIENT_OCCLUSION_MAX_SAMPLES_SETTING_PATH
            ),
            "ambient_occlusion_denoiser_mode": 2,
            "ambient_occlusion_denoiser_mode_setting_path": (
                REPLAY_AMBIENT_OCCLUSION_DENOISER_MODE_SETTING_PATH
            ),
            "shadows_enabled": True,
            "shadows_setting_path": REPLAY_SHADOWS_SETTING_PATH,
            "shadow_sample_count": 4,
            "shadow_sample_count_setting_path": (
                REPLAY_SHADOW_SAMPLE_COUNT_SETTING_PATH
            ),
            "renderer_consumption_verification": (
                REPLAY_RENDERER_CONSUMPTION_VERIFICATION
            ),
        },
    }
    payload = {
        "schema_version": 2,
        "contract_type": "effective_real_beaker_replay_look",
        **non_lighting,
        "render_diagnostic_variant_id": render_diagnostic_variant_id,
        "lighting_variant_id": lighting_variant_id,
        "lighting_source_profile_id": lighting_source_profile_id,
        "lighting_source_profile_sha256": _json_sha256(
            lighting_source_profile
        ),
        "effective_lighting": lighting_source_profile["lighting"],
        "effective_replay_non_lighting_contract_sha256": _json_sha256(
            non_lighting
        ),
    }
    return {
        **payload,
        "effective_replay_look_contract_sha256": _json_sha256(payload),
    }


def validate_effective_replay_look_contract(
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Reject any contract not equal to a fresh canonical resolution."""
    if not isinstance(contract, Mapping):
        raise ValueError("effective_replay_look_contract_mismatch:not_object")
    variant = contract.get("lighting_variant_id")
    render_diagnostic_variant = contract.get("render_diagnostic_variant_id")
    if render_diagnostic_variant is not None and not isinstance(
        render_diagnostic_variant, str
    ):
        raise ValueError(
            "effective_replay_look_contract_mismatch:invalid_render_diagnostic_variant"
        )
    try:
        expected = build_effective_replay_look_contract(
            str(variant),
            render_diagnostic_variant_id=render_diagnostic_variant,
        )
    except ValueError as exc:
        raise ValueError(
            "effective_replay_look_contract_mismatch:invalid_variant"
        ) from exc
    actual = _json_native_copy(dict(contract))
    if actual != expected:
        raise ValueError("effective_replay_look_contract_mismatch")
    return expected


def build_effective_replay_look_matrix_projection(
    contract: Mapping[str, Any],
    *,
    validate_full_contract: bool = True,
) -> dict[str, Any]:
    """Remove only the five predeclared matrix-variable JSON pointers."""
    if not isinstance(contract, Mapping):
        raise ValueError("matrix_projection_contract_not_object")
    pointers = (
        ("/render_diagnostic_variant_id", ("render_diagnostic_variant_id",)),
        (
            "/render_settings/ambient_occlusion_enabled",
            ("render_settings", "ambient_occlusion_enabled"),
        ),
        (
            "/render_settings/rt_subframes",
            ("render_settings", "rt_subframes"),
        ),
        (
            "/effective_replay_non_lighting_contract_sha256",
            ("effective_replay_non_lighting_contract_sha256",),
        ),
        (
            "/effective_replay_look_contract_sha256",
            ("effective_replay_look_contract_sha256",),
        ),
    )
    raw = _json_native_copy(dict(contract))
    for pointer, path_parts in pointers:
        parent: Any = raw
        for path_part in path_parts[:-1]:
            if not isinstance(parent, dict) or path_part not in parent:
                raise ValueError(f"matrix_projection_pointer_missing:{pointer}")
            parent = parent[path_part]
        if not isinstance(parent, dict) or path_parts[-1] not in parent:
            raise ValueError(f"matrix_projection_pointer_missing:{pointer}")
    source = (
        validate_effective_replay_look_contract(contract)
        if validate_full_contract
        else raw
    )
    projected = _json_native_copy(source)
    for pointer, path_parts in pointers:
        parent: Any = projected
        for path_part in path_parts[:-1]:
            if not isinstance(parent, dict) or path_part not in parent:
                raise ValueError(f"matrix_projection_pointer_missing:{pointer}")
            parent = parent[path_part]
        leaf = path_parts[-1]
        if not isinstance(parent, dict) or leaf not in parent:
            raise ValueError(f"matrix_projection_pointer_missing:{pointer}")
        del parent[leaf]
    encoded = json.dumps(
        projected,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        "schema_version": 1,
        "projection_id": EFFECTIVE_REPLAY_LOOK_MATRIX_PROJECTION_ID,
        "removed_json_pointers": [pointer for pointer, _parts in pointers],
        "projected_contract": projected,
        "canonical_json_utf8_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def validate_render_diagnostic_cell_scope(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    """Fail closed on mixed or non-canonical diagnostic cell identity."""
    variant = getattr(args, "visual_prototype_render_diagnostic_variant", None)
    experiment_id = getattr(args, "render_diagnostic_experiment_id", None)
    replicate = getattr(args, "render_diagnostic_replicate", None)
    order_index = getattr(args, "render_diagnostic_order_index", None)
    identity_values = (variant, experiment_id, replicate, order_index)
    if all(value is None for value in identity_values):
        return None
    if any(value is None for value in identity_values):
        raise ValueError("render_diagnostic_identity_incomplete")
    if variant not in RENDER_DIAGNOSTIC_VARIANTS:
        raise ValueError("render_diagnostic_identity_variant_invalid")
    if experiment_id != RENDER_DIAGNOSTIC_EXPERIMENT_ID:
        raise ValueError("render_diagnostic_identity_experiment_invalid")
    if replicate not in RENDER_DIAGNOSTIC_BALANCED_ORDER:
        raise ValueError("render_diagnostic_identity_replicate_invalid")
    if type(order_index) is not int or order_index not in range(4):
        raise ValueError("render_diagnostic_order_invalid")
    expected_variant = RENDER_DIAGNOSTIC_BALANCED_ORDER[replicate][order_index]
    if variant != expected_variant:
        raise ValueError("render_diagnostic_order_variant_mismatch")
    if (
        not bool(getattr(args, "visual_prototype_display_fill_only", False))
        or str(getattr(args, "candidates", "")) != "OMNI_REF_DISPLAY_FILL"
        or getattr(args, "visual_prototype_lighting_variant", None)
        != LIGHTING_VARIANT_C_CONTROL
    ):
        raise ValueError("render_diagnostic_scope_requires_c_display_fill_prototype")
    if (
        bool(getattr(args, "headless", False)) is not True
        or int(getattr(args, "width", 0)) != 960
        or int(getattr(args, "height", 0)) != 540
        or float(getattr(args, "video_fps", 0.0)) != 15.0
        or int(getattr(args, "warmup_updates", 0)) != 8
        or int(getattr(args, "camera_warmup_updates", 0)) != 8
    ):
        raise ValueError("render_diagnostic_scope_runtime_parameters_mismatch")
    aggregate_root = _reject_symlink_path_components(
        RENDER_DIAGNOSTIC_AGGREGATE_ROOT,
        label="render_diagnostic_aggregate_root",
    )
    if aggregate_root.exists() and not aggregate_root.is_dir():
        raise ValueError("render_diagnostic_aggregate_root_invalid")
    authority_arg = getattr(args, "accepted_authority_bundle", None)
    if authority_arg is None:
        raise ValueError("render_diagnostic_authority_path_missing")
    authority_path = _reject_symlink_path_components(
        str(authority_arg),
        label="render_diagnostic_authority_path",
    )
    expected_authority_root = _reject_symlink_path_components(
        RENDER_DIAGNOSTIC_ACCEPTED_AUTHORITY_ROOT,
        label="render_diagnostic_authority_root",
    )
    if authority_path not in {
        expected_authority_root,
        expected_authority_root / AUTHORITY_BUNDLE_BASENAME,
    }:
        raise ValueError("render_diagnostic_authority_path_mismatch")
    expected_root = (
        aggregate_root
        / "cells"
        / f"{replicate}_{order_index}_{variant}"
    )
    actual_root = _absolute_path_without_symlink_resolution(
        str(getattr(args, "out_root", ""))
    )
    if actual_root != expected_root:
        raise ValueError(
            f"render_diagnostic_cell_root_mismatch:{actual_root}!={expected_root}"
        )
    if getattr(args, "manifest", None) is not None:
        raise ValueError("render_diagnostic_scope_custom_manifest_forbidden")
    return {
        "experiment_id": experiment_id,
        "render_diagnostic_variant_id": variant,
        "replicate": replicate,
        "execution_order_index": order_index,
        "cell_root": str(expected_root),
    }


def render_diagnostic_slots() -> list[dict[str, Any]]:
    return [
        {
            "variant": variant,
            "replicate": replicate,
            "execution_order_index": order_index,
            "cell_name": f"{replicate}_{order_index}_{variant}",
        }
        for replicate in RENDER_DIAGNOSTIC_REPLICATES
        for order_index, variant in enumerate(
            RENDER_DIAGNOSTIC_BALANCED_ORDER[replicate]
        )
    ]


def build_matrix_implementation_identity_v1() -> dict[str, Any]:
    fixed_paths = (
        REPO_ROOT / "tests/test_real_beaker_runtime_contract.py",
        REPO_ROOT / "tests/test_omniglass_reference.py",
        REPO_ROOT / "tests/test_real_beaker.py",
        REPO_ROOT / "tests/test_real_beaker_matrix_isaac_runtime.py",
        REPO_ROOT / "tests/test_real_beaker_strict_step_schedule.py",
        REPO_ROOT
        / "tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py",
        REPO_ROOT / "tests/test_level1_pour_support_aligned_scene.py",
        REPO_ROOT / "tests/test_support_aligned_authority_bundle.py",
        REPO_ROOT
        / "docs/runs/2026-07-12-real-beaker-black-liquid-causal-matrix-plan-v3.md",
        REPO_ROOT
        / "docs/runs/2026-07-12-real-beaker-black-liquid-causal-matrix-hardening-plan.md",
        REPO_ROOT
        / "docs/runs/2026-07-13-real-beaker-presentation-layer-save-recovery-plan.md",
        REPO_ROOT
        / "docs/runs/2026-07-13-real-beaker-presentation-layer-file-mode-plan.md",
        REPO_ROOT
        / "docs/runs/2026-07-13-real-beaker-normal-equivalence-projection-plan.md",
        REPO_ROOT
        / "docs/runs/2026-07-13-real-beaker-material-id-hash-plan.md",
        REPO_ROOT
        / "docs/runs/2026-07-13-real-beaker-parent-pxr-closure-plan.md",
        REPO_ROOT
        / "tools/labutopia_fluid/run_sealed_child_with_pipe_log.sh",
        REPO_ROOT
        / "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_003.sh",
        REPO_ROOT
        / "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_004.sh",
        REPO_ROOT
        / "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_005.sh",
        REPO_ROOT
        / "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_006.sh",
        REPO_ROOT
        / "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_007.sh",
        REPO_ROOT
        / "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_008.sh",
    )
    tool_dir = REPO_ROOT / "tools/labutopia_fluid"
    checked_tool_dir, tool_records = _snapshot_pinned_direct_files(
        tool_dir,
        suffix=".py",
        label="matrix_implementation_tool_dir",
    )
    records = [
        {
            "path": str(
                (checked_tool_dir / record["name"]).relative_to(REPO_ROOT)
            ),
            "sha256": record["sha256"],
        }
        for record in tool_records
    ]
    for raw_path in fixed_paths:
        path = _reject_symlink_path_components(
            raw_path,
            label="matrix_implementation_member",
        )
        try:
            relative = path.relative_to(REPO_ROOT)
        except ValueError as exc:
            raise RuntimeError(
                f"matrix_implementation_member_outside_repo:{path}"
            ) from exc
        evidence = _hash_regular_file_pinned(
            path,
            label="matrix_implementation_member",
        )
        records.append({"path": str(relative), "sha256": evidence["sha256"]})
    records.sort(key=lambda record: record["path"])
    payload = {
        "schema_version": 1,
        "identity_id": "matrix_implementation_identity_v1",
        "files": records,
    }
    return {
        **payload,
        "implementation_identity_sha256": canonical_json_sha256_v1(payload),
    }


def verify_matrix_implementation_identity_unchanged(
    expected_identity: Mapping[str, Any],
) -> dict[str, Any]:
    actual = build_matrix_implementation_identity_v1()
    expected = _json_native_copy(dict(expected_identity))
    if actual != expected:
        raise RuntimeError(
            "matrix_implementation_identity_changed:"
            f"actual={actual['implementation_identity_sha256']}:"
            f"expected={expected.get('implementation_identity_sha256')}"
        )
    return {
        "verified": True,
        "implementation_identity_sha256": actual[
            "implementation_identity_sha256"
        ],
        "file_count": len(actual["files"]),
    }


def validate_matrix_implementation_identity_v1(
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(identity, Mapping) or set(identity) != {
        "schema_version",
        "identity_id",
        "files",
        "implementation_identity_sha256",
    }:
        raise ValueError("matrix_implementation_identity_schema_invalid")
    actual = _json_native_copy(dict(identity))
    files = actual.get("files")
    if (
        actual.get("schema_version") != 1
        or actual.get("identity_id") != "matrix_implementation_identity_v1"
        or not isinstance(files, list)
        or not files
        or any(
            not isinstance(record, Mapping)
            or set(record) != {"path", "sha256"}
            or not isinstance(record.get("path"), str)
            or not record["path"]
            or Path(record["path"]).is_absolute()
            or ".." in Path(record["path"]).parts
            or not _is_sha256_text(record.get("sha256"))
            for record in files
        )
        or files != sorted(files, key=lambda record: record["path"])
        or len({record["path"] for record in files}) != len(files)
    ):
        raise ValueError("matrix_implementation_identity_schema_invalid")
    payload = {
        "schema_version": 1,
        "identity_id": "matrix_implementation_identity_v1",
        "files": files,
    }
    if actual.get("implementation_identity_sha256") != (
        canonical_json_sha256_v1(payload)
    ):
        raise ValueError("matrix_implementation_identity_hash_invalid")
    return actual


def write_frozen_matrix_implementation_identity() -> dict[str, Any]:
    aggregate_root = _reject_symlink_path_components(
        RENDER_DIAGNOSTIC_AGGREGATE_ROOT,
        label="matrix_implementation_aggregate_root",
    )
    if aggregate_root.exists() or aggregate_root.is_symlink():
        raise ValueError("matrix_implementation_freeze_requires_absent_aggregate")
    identity = validate_matrix_implementation_identity_v1(
        build_matrix_implementation_identity_v1()
    )
    _write_json_create_exclusive(
        RENDER_DIAGNOSTIC_IMPLEMENTATION_FREEZE_PATH,
        identity,
    )
    return identity


def load_and_verify_frozen_matrix_implementation_identity() -> dict[str, Any]:
    path = _reject_symlink_path_components(
        RENDER_DIAGNOSTIC_IMPLEMENTATION_FREEZE_PATH,
        label="matrix_implementation_identity_freeze",
    )
    frozen = validate_matrix_implementation_identity_v1(
        _load_json_object(path, label="matrix_implementation_identity_freeze")
    )
    verify_matrix_implementation_identity_unchanged(frozen)
    return frozen


_RUNTIME_ARCHIVE_SYNTHETIC_ENTRIES = {
    "tools/__init__.py": b"",
    "tools/labutopia_fluid/__init__.py": b"",
}
_RUNTIME_ARCHIVE_EXPECTED_NAMES = tuple(
    sorted(
        [
            *_RUNTIME_ARCHIVE_SYNTHETIC_ENTRIES,
            *(
                f"tools/labutopia_fluid/{path.name}"
                for path in (
                    REPO_ROOT / "tools/labutopia_fluid"
                ).glob("*.py")
            ),
        ]
    )
)
_LINUX_F_ADD_SEALS = getattr(fcntl, "F_ADD_SEALS", 1033)
_LINUX_F_GET_SEALS = getattr(fcntl, "F_GET_SEALS", 1034)
_LINUX_F_SEAL_SEAL = getattr(fcntl, "F_SEAL_SEAL", 0x0001)
_LINUX_F_SEAL_SHRINK = getattr(fcntl, "F_SEAL_SHRINK", 0x0002)
_LINUX_F_SEAL_GROW = getattr(fcntl, "F_SEAL_GROW", 0x0004)
_LINUX_F_SEAL_WRITE = getattr(fcntl, "F_SEAL_WRITE", 0x0008)
_RUNTIME_ARCHIVE_SEAL_MASK = (
    _LINUX_F_SEAL_SEAL
    | _LINUX_F_SEAL_SHRINK
    | _LINUX_F_SEAL_GROW
    | _LINUX_F_SEAL_WRITE
)
RENDER_DIAGNOSTIC_RUNTIME_BOOTSTRAP_SOURCE = r'''import fcntl
import hashlib
import os
import stat
import sys
import sysconfig
import zipfile


EXPECTED_ARCHIVE_NAMES = __RUNTIME_ARCHIVE_EXPECTED_NAMES__

if (
    sys.flags.isolated != 1
    or sys.flags.no_site != 1
    or sys.flags.ignore_environment != 1
    or sys.flags.no_user_site != 1
):
    raise SystemExit("runtime_bootstrap_interpreter_flags_invalid")


def _value(name):
    values = sys.argv[1:]
    if values.count(name) != 1:
        raise SystemExit("runtime_bootstrap_option_invalid:" + name)
    index = values.index(name)
    if index + 1 >= len(values):
        raise SystemExit("runtime_bootstrap_option_missing:" + name)
    return values[index + 1]


parts = open("/proc/self/cmdline", "rb").read().split(b"\0")
try:
    source_bytes = parts[parts.index(b"-c") + 1]
except (ValueError, IndexError):
    raise SystemExit("runtime_bootstrap_cmdline_invalid")
bootstrap_sha256 = _value("--runtime-bootstrap-sha256")
if hashlib.sha256(source_bytes).hexdigest() != bootstrap_sha256:
    raise SystemExit("runtime_bootstrap_hash_invalid")

archive_fd = int(_value("--runtime-parent-archive-fd"))
lock_fd = int(_value("--runtime-parent-lock-fd"))
if archive_fd == lock_fd or min(archive_fd, lock_fd) < 0:
    raise SystemExit("runtime_bootstrap_descriptor_invalid")
allowed_fds = {0, 1, 2, archive_fd, lock_fd}
for raw in os.listdir("/proc/self/fd"):
    descriptor = int(raw)
    if descriptor in allowed_fds:
        continue
    try:
        os.fstat(descriptor)
    except OSError:
        continue
    raise SystemExit("runtime_bootstrap_unexpected_fd:" + raw)
for descriptor in (0, 1, 2):
    mode = os.fstat(descriptor).st_mode
    if not (stat.S_ISCHR(mode) or stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode)):
        raise SystemExit("runtime_bootstrap_standard_fd_invalid")
archive_stat = os.fstat(archive_fd)
lock_stat = os.fstat(lock_fd)
if not stat.S_ISREG(archive_stat.st_mode) or not stat.S_ISREG(lock_stat.st_mode):
    raise SystemExit("runtime_bootstrap_inherited_fd_type_invalid")
if (fcntl.fcntl(lock_fd, fcntl.F_GETFL) & os.O_ACCMODE) != os.O_RDWR:
    raise SystemExit("runtime_bootstrap_lock_not_readwrite")
if (fcntl.fcntl(archive_fd, fcntl.F_GETFL) & os.O_ACCMODE) != os.O_RDONLY:
    raise SystemExit("runtime_bootstrap_archive_not_readonly")
if fcntl.fcntl(archive_fd, 1034) != 15:
    raise SystemExit("runtime_bootstrap_archive_unsealed")
expected_archive_sha256 = _value("--runtime-parent-archive-sha256")
digest = hashlib.sha256()
offset = 0
while offset < archive_stat.st_size:
    chunk = os.pread(archive_fd, min(1048576, archive_stat.st_size - offset), offset)
    if not chunk:
        raise SystemExit("runtime_bootstrap_archive_short_read")
    digest.update(chunk)
    offset += len(chunk)
if digest.hexdigest() != expected_archive_sha256:
    raise SystemExit("runtime_bootstrap_archive_hash_invalid")

archive_path = "/proc/self/fd/" + str(archive_fd)
try:
    with zipfile.ZipFile(archive_path, mode="r") as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if (
            names != list(EXPECTED_ARCHIVE_NAMES)
            or len(set(names)) != len(names)
            or any(
                info.is_dir()
                or info.compress_type != zipfile.ZIP_STORED
                or info.date_time != (1980, 1, 1, 0, 0, 0)
                for info in infos
            )
        ):
            raise SystemExit("runtime_bootstrap_archive_membership_invalid")
        for info in infos:
            payload = archive.read(info.filename)
            if info.filename in {
                "tools/__init__.py",
                "tools/labutopia_fluid/__init__.py",
            } and payload != b"":
                raise SystemExit("runtime_bootstrap_archive_synthetic_invalid")
except (OSError, RuntimeError, zipfile.BadZipFile):
    raise SystemExit("runtime_bootstrap_archive_invalid")

meta_names = [getattr(finder, "__name__", None) for finder in sys.meta_path]
hook_names = [getattr(hook, "__qualname__", None) for hook in sys.path_hooks]
if meta_names != ["BuiltinImporter", "FrozenImporter", "PathFinder"]:
    raise SystemExit("runtime_bootstrap_meta_path_invalid")
if hook_names != ["zipimporter", "FileFinder.path_hook.<locals>.path_hook_for_FileFinder"]:
    raise SystemExit("runtime_bootstrap_path_hooks_invalid")
if any(
    name == "tools"
    or name.startswith("tools.")
    or name in {"site", "sitecustomize", "usercustomize"}
    for name in sys.modules
):
    raise SystemExit("runtime_bootstrap_preloaded_module_invalid")

repo_root = os.environ.get("LABUTOPIA_REPO_ROOT")
if not repo_root or not os.path.isabs(repo_root):
    raise SystemExit("runtime_bootstrap_repo_root_invalid")
if any(path == repo_root or path.startswith(repo_root + os.sep) for path in sys.path):
    raise SystemExit("runtime_bootstrap_live_repo_on_sys_path")
purelib = sysconfig.get_paths().get("purelib")
if not purelib or not os.path.isabs(purelib) or purelib.startswith(repo_root + os.sep):
    raise SystemExit("runtime_bootstrap_purelib_invalid")
sys.path.insert(0, archive_path)
sys.path.append(purelib)
module = __import__(
    "tools.labutopia_fluid.run_real_beaker_omniglass_replay",
    fromlist=["main"],
)
if (
    type(getattr(module, "__loader__", None)).__name__ != "zipimporter"
    or not str(getattr(module, "__file__", "")).startswith(
        archive_path + "/tools/labutopia_fluid/"
    )
):
    raise SystemExit("runtime_bootstrap_main_module_loader_invalid")
sys.argv = [
    os.path.join(repo_root, "tools/labutopia_fluid/run_real_beaker_omniglass_replay.py"),
    *sys.argv[1:],
]
raise SystemExit(module.main())
'''.replace(
    "__RUNTIME_ARCHIVE_EXPECTED_NAMES__",
    repr(_RUNTIME_ARCHIVE_EXPECTED_NAMES),
)
RENDER_DIAGNOSTIC_RUNTIME_BOOTSTRAP_SHA256 = hashlib.sha256(
    RENDER_DIAGNOSTIC_RUNTIME_BOOTSTRAP_SOURCE.encode("utf-8")
).hexdigest()


def _runtime_archive_source_records(
    implementation_identity: Mapping[str, Any],
) -> list[dict[str, str]]:
    validated = validate_matrix_implementation_identity_v1(
        implementation_identity
    )
    records = [
        _json_native_copy(record)
        for record in validated["files"]
        if Path(record["path"]).parent == Path("tools/labutopia_fluid")
        and Path(record["path"]).suffix == ".py"
    ]
    if not records or records != sorted(records, key=lambda item: item["path"]):
        raise ValueError("runtime_implementation_archive_source_set_invalid")
    return records


def build_render_diagnostic_runtime_implementation_archive(
    implementation_identity: Mapping[str, Any],
) -> tuple[dict[str, Any], bytes]:
    source_records = _runtime_archive_source_records(implementation_identity)
    payloads: dict[str, bytes] = {}
    for record in source_records:
        path = REPO_ROOT / record["path"]
        payload = _read_regular_file_snapshot(
            path,
            label="runtime_implementation_archive_source",
        )
        if hashlib.sha256(payload).hexdigest() != record["sha256"]:
            raise ValueError("runtime_implementation_archive_source_hash_mismatch")
        payloads[record["path"]] = payload
    payloads.update(_RUNTIME_ARCHIVE_SYNTHETIC_ENTRIES)
    synthetic_records = [
        {"path": path, "sha256": hashlib.sha256(payload).hexdigest()}
        for path, payload in sorted(_RUNTIME_ARCHIVE_SYNTHETIC_ENTRIES.items())
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer,
        mode="w",
        compression=zipfile.ZIP_STORED,
        allowZip64=True,
        strict_timestamps=True,
    ) as archive:
        for path in sorted(payloads):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o444) << 16
            archive.writestr(info, payloads[path])
    archive_bytes = buffer.getvalue()
    evidence = {
        "schema_version": 1,
        "archive_id": "matrix_runtime_implementation_archive_v1",
        "source_files": source_records,
        "synthetic_files": synthetic_records,
        "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
    }
    return (
        validate_render_diagnostic_runtime_implementation_archive(
            evidence,
            archive_bytes=archive_bytes,
            implementation_identity=implementation_identity,
        ),
        archive_bytes,
    )


def validate_render_diagnostic_runtime_implementation_archive(
    evidence: Mapping[str, Any],
    *,
    archive_bytes: bytes,
    implementation_identity: Mapping[str, Any],
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "archive_id",
        "source_files",
        "synthetic_files",
        "archive_sha256",
    }
    if (
        not isinstance(evidence, Mapping)
        or set(evidence) != fields
        or not isinstance(archive_bytes, bytes)
    ):
        raise ValueError("runtime_implementation_archive_schema_invalid")
    actual = _json_native_copy(dict(evidence))
    expected_sources = _runtime_archive_source_records(implementation_identity)
    expected_synthetic = [
        {"path": path, "sha256": hashlib.sha256(payload).hexdigest()}
        for path, payload in sorted(_RUNTIME_ARCHIVE_SYNTHETIC_ENTRIES.items())
    ]
    if (
        actual.get("schema_version") != 1
        or actual.get("archive_id")
        != "matrix_runtime_implementation_archive_v1"
        or actual.get("source_files") != expected_sources
        or actual.get("synthetic_files") != expected_synthetic
        or actual.get("archive_sha256")
        != hashlib.sha256(archive_bytes).hexdigest()
    ):
        raise ValueError("runtime_implementation_archive_invalid")
    expected_records = [*expected_sources, *expected_synthetic]
    expected_names = [record["path"] for record in expected_records]
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), mode="r") as archive:
            infos = archive.infolist()
            if (
                [info.filename for info in infos] != sorted(expected_names)
                or len({info.filename for info in infos}) != len(infos)
                or any(
                    info.is_dir()
                    or info.compress_type != zipfile.ZIP_STORED
                    or info.date_time != (1980, 1, 1, 0, 0, 0)
                    for info in infos
                )
            ):
                raise ValueError("runtime_implementation_archive_membership_invalid")
            record_by_path = {
                record["path"]: record for record in expected_records
            }
            for info in infos:
                payload = archive.read(info.filename)
                if hashlib.sha256(payload).hexdigest() != record_by_path[
                    info.filename
                ]["sha256"]:
                    raise ValueError(
                        "runtime_implementation_archive_member_hash_invalid"
                    )
    except (KeyError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise ValueError("runtime_implementation_archive_invalid") from exc
    return actual


def _linux_memfd_create(name: bytes, flags: int) -> int:
    creator = getattr(os, "memfd_create", None)
    if callable(creator):
        return int(creator(name.decode("ascii"), flags))
    libc = ctypes.CDLL(None, use_errno=True)
    function = getattr(libc, "memfd_create", None)
    if function is None:
        raise OSError(errno.ENOSYS, "memfd_create_unavailable")
    function.argtypes = (ctypes.c_char_p, ctypes.c_uint)
    function.restype = ctypes.c_int
    descriptor = int(function(name, flags))
    if descriptor < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return descriptor


def validate_render_diagnostic_sealed_archive_fd(
    descriptor: int,
    *,
    expected_archive_sha256: str,
) -> dict[str, Any]:
    if type(descriptor) is not int or descriptor < 0:
        raise ValueError("runtime_archive_descriptor_invalid")
    try:
        metadata = os.fstat(descriptor)
        access_mode = fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE
        seals = fcntl.fcntl(descriptor, _LINUX_F_GET_SEALS)
    except OSError as exc:
        raise ValueError("runtime_archive_descriptor_invalid") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or access_mode != os.O_RDONLY
        or seals != _RUNTIME_ARCHIVE_SEAL_MASK
        or not _is_sha256_text(expected_archive_sha256)
    ):
        raise ValueError("runtime_archive_descriptor_contract_invalid")
    digest = hashlib.sha256()
    offset = 0
    while offset < metadata.st_size:
        chunk = os.pread(descriptor, min(1024 * 1024, metadata.st_size - offset), offset)
        if not chunk:
            raise ValueError("runtime_archive_descriptor_short_read")
        digest.update(chunk)
        offset += len(chunk)
    after = os.fstat(descriptor)
    if (
        (after.st_dev, after.st_ino, after.st_size)
        != (metadata.st_dev, metadata.st_ino, metadata.st_size)
        or digest.hexdigest() != expected_archive_sha256
    ):
        raise ValueError("runtime_archive_descriptor_hash_invalid")
    return {
        "schema_version": 1,
        "access_mode": "READ_ONLY",
        "seals": sorted(
            [
                "F_SEAL_SEAL",
                "F_SEAL_SHRINK",
                "F_SEAL_GROW",
                "F_SEAL_WRITE",
            ]
        ),
        "archive_sha256": expected_archive_sha256,
        "byte_count": metadata.st_size,
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
    }


def create_render_diagnostic_sealed_archive_fd(archive_bytes: bytes) -> int:
    if not isinstance(archive_bytes, bytes) or not archive_bytes:
        raise ValueError("runtime_archive_bytes_invalid")
    writable = _linux_memfd_create(
        b"labutopia-render-diagnostic-runtime",
        0x0001 | 0x0002,
    )
    readonly: int | None = None
    try:
        view = memoryview(archive_bytes)
        while view:
            written = os.write(writable, view)
            if written <= 0:
                raise OSError("runtime_archive_short_write")
            view = view[written:]
        os.fsync(writable)
        fcntl.fcntl(writable, _LINUX_F_ADD_SEALS, _RUNTIME_ARCHIVE_SEAL_MASK)
        readonly_flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            readonly_flags |= os.O_CLOEXEC
        readonly = os.open(f"/proc/self/fd/{writable}", readonly_flags)
    finally:
        os.close(writable)
    if readonly is None:
        raise RuntimeError("runtime_archive_readonly_reopen_failed")
    try:
        validate_render_diagnostic_sealed_archive_fd(
            readonly,
            expected_archive_sha256=hashlib.sha256(archive_bytes).hexdigest(),
        )
    except BaseException:
        os.close(readonly)
        raise
    return readonly


def validate_render_diagnostic_inherited_fd_contract(
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "standard_fds",
        "lock_fd",
        "archive_fd",
        "lock_access_mode",
        "archive_access_mode",
        "archive_seals",
    }
    if not isinstance(contract, Mapping) or set(contract) != fields:
        raise ValueError("inherited_fd_contract_schema_invalid")
    actual = _json_native_copy(dict(contract))
    if (
        actual.get("schema_version") != 1
        or actual.get("standard_fds") != [0, 1, 2]
        or type(actual.get("lock_fd")) is not int
        or type(actual.get("archive_fd")) is not int
        or actual["lock_fd"] < 0
        or actual["archive_fd"] < 0
        or actual["lock_fd"] == actual["archive_fd"]
        or actual.get("lock_access_mode") != "READ_WRITE"
        or actual.get("archive_access_mode") != "READ_ONLY"
        or actual.get("archive_seals")
        != sorted(
            [
                "F_SEAL_SEAL",
                "F_SEAL_SHRINK",
                "F_SEAL_GROW",
                "F_SEAL_WRITE",
            ]
        )
    ):
        raise ValueError("inherited_fd_contract_invalid")
    return actual


def attach_render_diagnostic_runtime_evidence(
    result: Mapping[str, Any],
    *,
    args: argparse.Namespace,
    cell_root: str | os.PathLike[str],
    implementation_identity: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        raise ValueError("render_diagnostic_runtime_result_invalid")
    cell = _reject_symlink_path_components(
        cell_root,
        label="render_diagnostic_runtime_evidence_cell",
    )
    archive_path = _reject_symlink_path_components(
        cell / "runtime_implementation_archive.zip",
        label="runtime_implementation_archive_artifact",
    )
    bootstrap_path = _reject_symlink_path_components(
        cell / "runtime_bootstrap.py",
        label="runtime_bootstrap_artifact",
    )
    archive_bytes = _read_regular_file_snapshot(
        archive_path,
        label="runtime_implementation_archive_artifact",
    )
    try:
        archive_evidence = (
            validate_render_diagnostic_runtime_implementation_archive(
                getattr(args, "_runtime_implementation_archive", None),
                archive_bytes=archive_bytes,
                implementation_identity=implementation_identity,
            )
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"runtime_implementation_archive_artifact_invalid:{exc}"
        ) from exc
    if hashlib.sha256(archive_bytes).hexdigest() != archive_evidence[
        "archive_sha256"
    ]:
        raise ValueError("runtime_implementation_archive_artifact_hash_invalid")
    bootstrap_bytes = _read_regular_file_snapshot(
        bootstrap_path,
        label="runtime_bootstrap_artifact",
    )
    bootstrap_sha256 = hashlib.sha256(bootstrap_bytes).hexdigest()
    if (
        bootstrap_bytes
        != RENDER_DIAGNOSTIC_RUNTIME_BOOTSTRAP_SOURCE.encode("utf-8")
        or bootstrap_sha256 != RENDER_DIAGNOSTIC_RUNTIME_BOOTSTRAP_SHA256
    ):
        raise ValueError("runtime_bootstrap_artifact_invalid")
    material_closure = getattr(args, "_preboot_material_closure", None)
    if not isinstance(material_closure, Mapping):
        raise ValueError("runtime_material_closure_missing")
    material_closure_root = _absolute_path_without_symlink_resolution(
        str(material_closure.get("closure_root", ""))
    )
    source_closure = validate_render_diagnostic_source_dependency_snapshot(
        cell,
        getattr(args, "_source_dependency_closure", None),
        additional_allowed_dependency_roots=(material_closure_root,),
    )
    runtime_dependency_resolution = (
        build_render_diagnostic_runtime_dependency_resolution(
            cell,
            source_closure,
            additional_allowed_dependency_roots=(material_closure_root,),
        )
    )
    if runtime_dependency_resolution != getattr(
        args, "_runtime_dependency_resolution", None
    ):
        raise ValueError("runtime_dependency_resolution_changed")
    inherited_fd_contract = validate_render_diagnostic_inherited_fd_contract(
        getattr(args, "_inherited_fd_contract", None)
    )
    attached = _json_native_copy(dict(result))
    attached.update(
        {
            "runtime_implementation_archive": archive_evidence,
            "runtime_implementation_archive_artifact": {
                "path": str(archive_path),
                "sha256": archive_evidence["archive_sha256"],
            },
            "runtime_bootstrap_artifact": {
                "path": str(bootstrap_path),
                "sha256": bootstrap_sha256,
            },
            "runtime_bootstrap_sha256": bootstrap_sha256,
            "inherited_fd_contract": inherited_fd_contract,
            "source_dependency_closure": source_closure,
            "runtime_dependency_resolution": runtime_dependency_resolution,
        }
    )
    runtime_contract = attached.setdefault("runtime_contract", {})
    if not isinstance(runtime_contract, dict):
        raise ValueError("render_diagnostic_runtime_contract_invalid")
    runtime_contract.update(
        {
            "usd_dependency_closure_bytes_verified": True,
            "usd_dependency_resolution_status": "PASS",
            "renderer_dependency_consumption_verification": (
                REPLAY_RENDERER_CONSUMPTION_VERIFICATION
            ),
        }
    )
    return attached


def validate_render_diagnostic_runtime_manifest_evidence(
    final_manifest: Mapping[str, Any],
    *,
    cell_root: str | os.PathLike[str],
    implementation_identity: Mapping[str, Any],
    authoritative_path_resolver: Any | None = None,
) -> dict[str, Any]:
    if not isinstance(final_manifest, Mapping):
        raise ValueError("runtime_manifest_evidence_invalid")
    cell = _reject_symlink_path_components(
        cell_root,
        label="runtime_manifest_evidence_cell",
    )

    def authority(path: Path) -> Path:
        return _reject_symlink_path_components(
            authoritative_path_resolver(path)
            if authoritative_path_resolver is not None
            else path,
            label="runtime_manifest_evidence_artifact",
        )

    archive_artifact = final_manifest.get(
        "runtime_implementation_archive_artifact"
    )
    bootstrap_artifact = final_manifest.get("runtime_bootstrap_artifact")
    if (
        not isinstance(archive_artifact, Mapping)
        or set(archive_artifact) != {"path", "sha256"}
        or not isinstance(bootstrap_artifact, Mapping)
        or set(bootstrap_artifact) != {"path", "sha256"}
    ):
        raise ValueError("runtime_manifest_artifact_schema_invalid")
    archive_path = _absolute_path_without_symlink_resolution(
        str(archive_artifact.get("path", ""))
    )
    bootstrap_path = _absolute_path_without_symlink_resolution(
        str(bootstrap_artifact.get("path", ""))
    )
    if (
        archive_path != cell / "runtime_implementation_archive.zip"
        or bootstrap_path != cell / "runtime_bootstrap.py"
    ):
        raise ValueError("runtime_manifest_artifact_path_invalid")
    archive_bytes = _read_regular_file_snapshot(
        authority(archive_path),
        label="runtime_manifest_archive",
    )
    archive_evidence = (
        validate_render_diagnostic_runtime_implementation_archive(
            final_manifest.get("runtime_implementation_archive"),
            archive_bytes=archive_bytes,
            implementation_identity=implementation_identity,
        )
    )
    bootstrap_bytes = _read_regular_file_snapshot(
        authority(bootstrap_path),
        label="runtime_manifest_bootstrap",
    )
    bootstrap_sha256 = hashlib.sha256(bootstrap_bytes).hexdigest()
    if (
        archive_artifact.get("sha256") != archive_evidence["archive_sha256"]
        or bootstrap_bytes
        != RENDER_DIAGNOSTIC_RUNTIME_BOOTSTRAP_SOURCE.encode("utf-8")
        or bootstrap_artifact.get("sha256") != bootstrap_sha256
        or final_manifest.get("runtime_bootstrap_sha256") != bootstrap_sha256
        or bootstrap_sha256 != RENDER_DIAGNOSTIC_RUNTIME_BOOTSTRAP_SHA256
    ):
        raise ValueError("runtime_manifest_artifact_hash_invalid")
    candidates = final_manifest.get("candidate_manifests")
    if not isinstance(candidates, Mapping) or set(candidates) != {
        "OMNI_REF_DISPLAY_FILL"
    }:
        raise ValueError("runtime_manifest_candidate_set_invalid")
    candidate = candidates["OMNI_REF_DISPLAY_FILL"]
    material_closure = (
        candidate.get("material_closure")
        if isinstance(candidate, Mapping)
        else None
    )
    if not isinstance(material_closure, Mapping):
        raise ValueError("runtime_manifest_material_closure_invalid")
    logical_material_root = _absolute_path_without_symlink_resolution(
        str(material_closure.get("closure_root", ""))
    )
    source_closure = validate_render_diagnostic_source_dependency_snapshot(
        authority(cell),
        final_manifest.get("source_dependency_closure"),
        verify_usd_dependencies=False,
    )
    runtime_dependency_resolution = (
        validate_render_diagnostic_runtime_dependency_resolution(
            final_manifest.get("runtime_dependency_resolution"),
            cell_root=cell,
            material_closure_root=logical_material_root,
        )
    )
    if candidate.get("runtime_dependency_resolution") != (
        runtime_dependency_resolution
    ):
        raise ValueError("runtime_manifest_dependency_resolution_mismatch")
    source_sidecar = _load_json_object(
        authority(cell / RENDER_DIAGNOSTIC_SOURCE_CLOSURE_BASENAME),
        label="runtime_manifest_source_dependency_closure",
    )
    if source_sidecar != source_closure:
        raise ValueError("runtime_manifest_source_closure_sidecar_mismatch")
    inherited_fd_contract = validate_render_diagnostic_inherited_fd_contract(
        final_manifest.get("inherited_fd_contract")
    )
    return {
        "runtime_implementation_archive": archive_evidence,
        "runtime_implementation_archive_sha256": canonical_json_sha256_v1(
            archive_evidence
        ),
        "runtime_bootstrap_sha256": bootstrap_sha256,
        "source_dependency_closure": source_closure,
        "source_dependency_closure_sha256": source_closure[
            "source_dependency_closure_sha256"
        ],
        "runtime_dependency_resolution": runtime_dependency_resolution,
        "inherited_fd_contract": inherited_fd_contract,
        "inherited_fd_contract_sha256": canonical_json_sha256_v1(
            inherited_fd_contract
        ),
    }


def build_render_diagnostic_device_identity() -> dict[str, Any]:
    output = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=uuid,name,driver_version",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        stderr=subprocess.STDOUT,
    )
    rows = [row.strip() for row in output.splitlines() if row.strip()]
    if not rows:
        raise RuntimeError("render_diagnostic_gpu_identity_missing")
    parts = [part.strip() for part in rows[0].split(",", 2)]
    if len(parts) != 3 or any(not part for part in parts):
        raise RuntimeError("render_diagnostic_gpu_identity_invalid")
    payload = {
        "schema_version": 1,
        "gpu_uuid": parts[0],
        "gpu_name": parts[1],
        "driver_version": parts[2],
    }
    return {
        **payload,
        "device_identity_sha256": canonical_json_sha256_v1(payload),
    }


_MATRIX_CELL_EVIDENCE_FIELDS = frozenset(
    {
        "schema_version",
        "manifest_type",
        "experiment_id",
        "variant",
        "replicate",
        "execution_order_index",
        "classification",
        "child_exit_code",
        "cell_root",
        "implementation_identity_sha256",
        "source_usd_sha256",
        "authority_bundle_sha256",
        "physical_trace_sha256",
        "normal_remediation_matrix_projection_sha256",
        "liquid_material_sha256",
        "display_fill_geometry_sha256",
        "camera_contract_sha256",
        "effective_replay_look_contract_sha256",
        "effective_replay_look_matrix_projection_sha256",
        "render_settings_sha256",
        "mdl_closure_sha256",
        "runtime_identity_sha256",
        "device_identity_sha256",
        "process_identity_sha256",
        "runtime_implementation_archive_sha256",
        "runtime_bootstrap_sha256",
        "source_dependency_closure_sha256",
        "artifact_inventory_sha256",
        "frame_bindings_sha256",
        "media_index_sha256",
        "stopped_timeline",
        "replicator_delta_time",
        "default_time_points_unchanged",
        "standalone_final_evidence_authority",
        "exporter_admitted",
        "visual_selection_eligible",
        "formal_scope",
        "delivery_ready",
        "matrix_cell_evidence_sha256",
    }
)
_MATRIX_CELL_HASH_FIELDS = tuple(
    sorted(
        field
        for field in _MATRIX_CELL_EVIDENCE_FIELDS
        if field.endswith("_sha256")
        and field != "matrix_cell_evidence_sha256"
    )
)


def _is_sha256_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX_DIGITS for character in value)
    )


def validate_render_diagnostic_matrix_cell_evidence(
    evidence: Mapping[str, Any],
    *,
    expected_cell_root: str | os.PathLike[str] | None = None,
    expected_slot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(evidence, Mapping) or set(evidence) != set(
        _MATRIX_CELL_EVIDENCE_FIELDS
    ):
        raise ValueError("matrix_cell_evidence_mismatch:field_set")
    actual = _json_native_copy(dict(evidence))
    variant = actual.get("variant")
    replicate = actual.get("replicate")
    order_index = actual.get("execution_order_index")
    if (
        actual.get("schema_version") != 1
        or actual.get("manifest_type")
        != "real_beaker_render_diagnostic_matrix_cell"
        or actual.get("experiment_id") != RENDER_DIAGNOSTIC_EXPERIMENT_ID
        or variant not in RENDER_DIAGNOSTIC_VARIANTS
        or replicate not in RENDER_DIAGNOSTIC_REPLICATES
        or type(order_index) is not int
        or order_index not in range(4)
        or RENDER_DIAGNOSTIC_BALANCED_ORDER[replicate][order_index] != variant
        or actual.get("classification")
        != "DIAGNOSTIC_RENDER_COMPLETE_PENDING_VISUAL_REVIEW"
        or actual.get("child_exit_code") != 0
    ):
        raise ValueError("matrix_cell_evidence_mismatch:identity")
    root = actual.get("cell_root")
    if not isinstance(root, str) or not root or not Path(root).is_absolute():
        raise ValueError("matrix_cell_evidence_mismatch:cell_root")
    if expected_cell_root is not None and (
        _absolute_path_without_symlink_resolution(root)
        != _absolute_path_without_symlink_resolution(expected_cell_root)
    ):
        raise ValueError("matrix_cell_evidence_mismatch:canonical_cell_root")
    if expected_slot is not None and (
        actual.get("variant") != expected_slot.get("variant")
        or actual.get("replicate") != expected_slot.get("replicate")
        or actual.get("execution_order_index")
        != expected_slot.get("execution_order_index")
    ):
        raise ValueError("matrix_cell_evidence_mismatch:canonical_slot")
    if any(not _is_sha256_text(actual.get(field)) for field in _MATRIX_CELL_HASH_FIELDS):
        raise ValueError("matrix_cell_evidence_mismatch:hash")
    if (
        actual.get("authority_bundle_sha256")
        != RENDER_DIAGNOSTIC_EXPECTED_AUTHORITY_SHA256
        or actual.get("source_usd_sha256")
        != RENDER_DIAGNOSTIC_EXPECTED_SOURCE_SHA256
        or actual.get("physical_trace_sha256")
        != RENDER_DIAGNOSTIC_EXPECTED_TRACE_SHA256
        or actual.get("normal_remediation_matrix_projection_sha256")
        != RENDER_DIAGNOSTIC_EXPECTED_NORMAL_MATRIX_PROJECTION_SHA256
    ):
        raise ValueError("matrix_cell_evidence_mismatch:established_inputs")
    if (
        actual.get("stopped_timeline") is not True
        or actual.get("default_time_points_unchanged") is not True
        or type(actual.get("replicator_delta_time")) not in (int, float)
        or type(actual.get("replicator_delta_time")) is bool
        or not math.isfinite(float(actual["replicator_delta_time"]))
        or float(actual["replicator_delta_time"]) != 0.0
        or any(
            actual.get(field) is not False
            for field in (
                "standalone_final_evidence_authority",
                "exporter_admitted",
                "visual_selection_eligible",
                "formal_scope",
                "delivery_ready",
            )
        )
    ):
        raise ValueError("matrix_cell_evidence_mismatch:lifecycle")
    payload = {
        key: value
        for key, value in actual.items()
        if key != "matrix_cell_evidence_sha256"
    }
    if actual.get("matrix_cell_evidence_sha256") != canonical_json_sha256_v1(
        payload
    ):
        raise ValueError("matrix_cell_evidence_mismatch:self_hash")
    return actual


def validate_render_diagnostic_matrix_closure(
    cell_evidence: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    validated = [
        validate_render_diagnostic_matrix_cell_evidence(item)
        for item in cell_evidence
    ]
    actual_keys = [
        (
            item["variant"],
            item["replicate"],
            item["execution_order_index"],
        )
        for item in validated
    ]
    expected_keys = {
        (slot["variant"], slot["replicate"], slot["execution_order_index"])
        for slot in render_diagnostic_slots()
    }
    exact_slot_closure = (
        len(actual_keys) == 16
        and len(set(actual_keys)) == 16
        and set(actual_keys) == expected_keys
    )
    equality_fields = {
        "implementation_identity": "implementation_identity_sha256",
        "source_usd": "source_usd_sha256",
        "authority_bundle": "authority_bundle_sha256",
        "physical_trace": "physical_trace_sha256",
        "normal_remediation_matrix_projection": (
            "normal_remediation_matrix_projection_sha256"
        ),
        "liquid_material": "liquid_material_sha256",
        "display_fill_geometry": "display_fill_geometry_sha256",
        "camera_contract": "camera_contract_sha256",
        "mdl_closure": "mdl_closure_sha256",
        "runtime_identity": "runtime_identity_sha256",
        "device_identity": "device_identity_sha256",
        "runtime_implementation_archive": (
            "runtime_implementation_archive_sha256"
        ),
        "runtime_bootstrap": "runtime_bootstrap_sha256",
        "source_dependency_closure": "source_dependency_closure_sha256",
    }
    equality_checks = []
    for name, field in sorted(equality_fields.items()):
        values = {item[field] for item in validated}
        sorted_values = sorted(values)
        equality_checks.append(
            {
                "name": name,
                "status": "PASS" if len(values) == 1 and values else "FAIL",
                "reference_sha256": (
                    sorted_values[0]
                    if sorted_values
                    else canonical_json_sha256_v1([])
                ),
            }
        )
    projection_values = {
        item["effective_replay_look_matrix_projection_sha256"]
        for item in validated
    }
    projection_byte_equality = len(projection_values) == 1 and bool(
        projection_values
    )
    all_cells_successful = len(validated) == len(cell_evidence)
    passed = (
        exact_slot_closure
        and all_cells_successful
        and projection_byte_equality
        and all(item["status"] == "PASS" for item in equality_checks)
    )
    payload = {
        "schema_version": 1,
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "status": "PASS" if passed else "FAIL",
        "exact_slot_closure": exact_slot_closure,
        "all_cells_successful": all_cells_successful,
        "unexpected_paths": [],
        "equality_checks": equality_checks,
        "projection_byte_equality": projection_byte_equality,
        "projection_sha256": (
            next(iter(projection_values))
            if projection_byte_equality
            else None
        ),
    }
    return {
        **payload,
        "matrix_validation_evidence_sha256": canonical_json_sha256_v1(payload),
    }


_RENDER_DIAGNOSTIC_LAUNCH_INTENT_FIELDS = frozenset(
    {
        "schema_version",
        "experiment_id",
        "variant",
        "replicate",
        "execution_order_index",
        "cell_root",
        "launcher_pid",
        "generated_at_utc",
        "sequence_index",
        "anchor_sha256",
        "predecessor_launch_intent_sha256",
        "predecessor_cell_evidence_sha256",
        "implementation_identity_sha256",
        "pre_freeze_sha256",
        "launch_intent_sha256",
    }
)


def _validate_launch_intent_object(
    intent: Mapping[str, Any],
    *,
    slot: Mapping[str, Any],
    intent_path: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(intent, Mapping) or set(intent) != set(
        _RENDER_DIAGNOSTIC_LAUNCH_INTENT_FIELDS
    ):
        raise ValueError("render_diagnostic_launch_intent_invalid:field_set")
    actual = _json_native_copy(dict(intent))
    expected_cell_root = _absolute_path_without_symlink_resolution(
        RENDER_DIAGNOSTIC_AGGREGATE_ROOT
        / "cells"
        / str(slot["cell_name"])
    )
    if intent_path is not None:
        expected_intent_path = _absolute_path_without_symlink_resolution(
            RENDER_DIAGNOSTIC_AGGREGATE_ROOT
            / "launch_intents"
            / f"{slot['cell_name']}.json"
        )
        if (
            _absolute_path_without_symlink_resolution(intent_path)
            != expected_intent_path
        ):
            raise ValueError(
                "render_diagnostic_launch_intent_invalid:canonical_path"
            )
    hash_payload = {
        key: value
        for key, value in actual.items()
        if key not in {"generated_at_utc", "launch_intent_sha256"}
    }
    slots = render_diagnostic_slots()
    expected_sequence_index = next(
        (
            index
            for index, candidate in enumerate(slots)
            if candidate["cell_name"] == slot["cell_name"]
        ),
        None,
    )
    predecessor_launch = actual.get("predecessor_launch_intent_sha256")
    predecessor_cell = actual.get("predecessor_cell_evidence_sha256")
    if (
        actual.get("schema_version") != 1
        or actual.get("experiment_id") != RENDER_DIAGNOSTIC_EXPERIMENT_ID
        or actual.get("variant") != slot["variant"]
        or actual.get("replicate") != slot["replicate"]
        or actual.get("execution_order_index")
        != slot["execution_order_index"]
        or type(actual.get("execution_order_index")) is not int
        or not isinstance(actual.get("cell_root"), str)
        or not actual["cell_root"]
        or not Path(actual["cell_root"]).is_absolute()
        or _absolute_path_without_symlink_resolution(actual["cell_root"])
        != expected_cell_root
        or type(actual.get("launcher_pid")) is not int
        or actual["launcher_pid"] <= 0
        or not isinstance(actual.get("generated_at_utc"), str)
        or not actual["generated_at_utc"]
        or actual.get("sequence_index") != expected_sequence_index
        or type(actual.get("sequence_index")) is not int
        or not _is_sha256_text(actual.get("anchor_sha256"))
        or (
            expected_sequence_index == 0
            and (predecessor_launch is not None or predecessor_cell is not None)
        )
        or (
            expected_sequence_index != 0
            and (
                not _is_sha256_text(predecessor_launch)
                or not _is_sha256_text(predecessor_cell)
            )
        )
        or not _is_sha256_text(
            actual.get("implementation_identity_sha256")
        )
        or not _is_sha256_text(actual.get("pre_freeze_sha256"))
        or actual.get("launch_intent_sha256")
        != canonical_json_sha256_v1(hash_payload)
    ):
        raise ValueError("render_diagnostic_launch_intent_invalid:content")
    return actual


def _load_launch_intent(path: Path, slot: Mapping[str, Any]) -> dict[str, Any]:
    intent = _load_json_object(path, label="render_diagnostic_launch_intent")
    return _validate_launch_intent_object(
        intent,
        slot=slot,
        intent_path=path,
    )


def validate_render_diagnostic_launch_chain(
    *,
    aggregate_root: str | os.PathLike[str],
    anchor_sha256: str,
    expected_implementation_identity_sha256: str,
    expected_pre_freeze_sha256: str,
    cell_status_index: Mapping[str, Any],
    require_artifact_closure: bool,
    expected_implementation_identity: Mapping[str, Any] | None = None,
    authoritative_path_resolver: Any | None = None,
) -> dict[str, Any]:
    root = _absolute_path_without_symlink_resolution(aggregate_root)
    status = validate_render_diagnostic_cell_status_index(cell_status_index)
    if (
        not _is_sha256_text(anchor_sha256)
        or not _is_sha256_text(expected_implementation_identity_sha256)
        or not _is_sha256_text(expected_pre_freeze_sha256)
        or (
            require_artifact_closure
            and (
                not isinstance(expected_implementation_identity, Mapping)
                or expected_implementation_identity.get(
                    "implementation_identity_sha256"
                )
                != expected_implementation_identity_sha256
            )
        )
    ):
        raise ValueError("render_diagnostic_launch_chain_input_invalid")

    def authoritative_path(path: Path) -> Path:
        return (
            _absolute_path_without_symlink_resolution(
                authoritative_path_resolver(path)
            )
            if authoritative_path_resolver is not None
            else _reject_symlink_path_components(
                path,
                label="render_diagnostic_launch_chain_path",
            )
        )

    predecessor_launch = None
    predecessor_cell = None
    sequence_open = True
    validated_records = []
    successful_cell_evidence = []
    artifact_closures = []
    for slot, record in zip(render_diagnostic_slots(), status["cells"]):
        state = record["status"]
        launched = state in {
            "SUCCESS",
            "FAILED",
            "LAUNCHED_EVIDENCE_MISSING",
        }
        if not launched:
            sequence_open = False
            continue
        if not sequence_open:
            raise ValueError("render_diagnostic_launch_chain_launch_after_gap")
        intent_path = root / "launch_intents" / f"{slot['cell_name']}.json"
        if (
            _absolute_path_without_symlink_resolution(
                record["launch_intent_path"]
            )
            != intent_path
        ):
            raise ValueError("render_diagnostic_launch_chain_intent_path")
        intent = _validate_launch_intent_object(
            _load_json_object(
                authoritative_path(intent_path),
                label="render_diagnostic_launch_chain_intent",
            ),
            slot=slot,
            intent_path=intent_path,
        )
        if (
            intent["launch_intent_sha256"]
            != record["launch_intent_sha256"]
            or intent["anchor_sha256"] != anchor_sha256
            or intent["implementation_identity_sha256"]
            != expected_implementation_identity_sha256
            or intent["pre_freeze_sha256"] != expected_pre_freeze_sha256
            or intent["predecessor_launch_intent_sha256"]
            != predecessor_launch
            or intent["predecessor_cell_evidence_sha256"]
            != predecessor_cell
        ):
            raise ValueError("render_diagnostic_launch_chain_predecessor_invalid")
        artifact = None
        if state == "SUCCESS":
            cell_root = root / "cells" / str(slot["cell_name"])
            evidence_path = cell_root / "matrix_cell_evidence.json"
            if (
                _absolute_path_without_symlink_resolution(
                    record["cell_evidence_path"]
                )
                != evidence_path
            ):
                raise ValueError("render_diagnostic_launch_chain_evidence_path")
            artifact = validate_render_diagnostic_matrix_cell_evidence(
                _load_json_object(
                    authoritative_path(evidence_path),
                    label="render_diagnostic_launch_chain_cell_evidence",
                ),
                expected_cell_root=cell_root,
                expected_slot=slot,
            )
            if (
                artifact["matrix_cell_evidence_sha256"]
                != record["cell_evidence_sha256"]
            ):
                raise ValueError("render_diagnostic_launch_chain_evidence_hash")
            if require_artifact_closure:
                closure = validate_render_diagnostic_cell_artifact_closure(
                    cell_root=cell_root,
                    expected_slot=slot,
                    expected_implementation_identity=(
                        expected_implementation_identity
                    ),
                    expected_launch_intent=intent,
                    authoritative_path_resolver=authoritative_path_resolver,
                )
                if closure["cell_evidence"] != artifact:
                    raise ValueError(
                        "render_diagnostic_launch_chain_artifact_mismatch"
                    )
                artifact_closures.append(closure)
            successful_cell_evidence.append(artifact)
            predecessor_launch = intent["launch_intent_sha256"]
            predecessor_cell = artifact["matrix_cell_evidence_sha256"]
        elif state == "FAILED":
            cell_root = root / "cells" / str(slot["cell_name"])
            evidence_path = cell_root / "matrix_cell_failure_evidence.json"
            if (
                _absolute_path_without_symlink_resolution(
                    record["cell_evidence_path"]
                )
                != evidence_path
            ):
                raise ValueError("render_diagnostic_launch_chain_failure_path")
            failure = validate_render_diagnostic_cell_failure_evidence(
                _load_json_object(
                    authoritative_path(evidence_path),
                    label="render_diagnostic_launch_chain_failure_evidence",
                ),
                expected_cell_root=cell_root,
                expected_slot=slot,
                expected_launch_intent=intent,
                expected_implementation_identity={
                    "implementation_identity_sha256": (
                        expected_implementation_identity_sha256
                    )
                },
            )
            if (
                failure["matrix_cell_failure_evidence_sha256"]
                != record["cell_evidence_sha256"]
                or failure["classification"] != record["classification"]
                or failure["child_exit_code"] != record["child_exit_code"]
            ):
                raise ValueError("render_diagnostic_launch_chain_failure_hash")
            sequence_open = False
        else:
            sequence_open = False
        validated_records.append(
            {
                "sequence_index": intent["sequence_index"],
                "status": state,
                "launch_intent_sha256": intent["launch_intent_sha256"],
                "cell_artifact_sha256": record["cell_evidence_sha256"],
            }
        )
    return {
        "schema_version": 1,
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "validated_records": validated_records,
        "successful_cell_evidence": successful_cell_evidence,
        "artifact_closures": artifact_closures,
        "completed_successful_sequence_length": sum(
            record["status"] == "SUCCESS" for record in validated_records
        ),
        "last_launch_intent_sha256": (
            validated_records[-1]["launch_intent_sha256"]
            if validated_records
            else None
        ),
        "last_cell_artifact_sha256": (
            validated_records[-1]["cell_artifact_sha256"]
            if validated_records
            else None
        ),
    }


def _best_effort_regular_file_sha256(path: Path) -> str | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return _sha256_file(path)
    except (OSError, ValueError):
        return None


def _artifact_fingerprint_sha256(path: Path) -> str:
    regular_hash = _best_effort_regular_file_sha256(path)
    if regular_hash is not None:
        return regular_hash
    try:
        metadata = os.lstat(path)
        payload = {
            "path": str(path),
            "mode": metadata.st_mode,
            "size": metadata.st_size,
            "symlink_target": os.readlink(path) if path.is_symlink() else None,
        }
    except OSError as exc:
        payload = {
            "path": str(path),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    return canonical_json_sha256_v1(payload)


def build_render_diagnostic_cell_status_index(
    aggregate_root: str | os.PathLike[str],
    *,
    expected_implementation_identity: Mapping[str, Any] | None = None,
    expected_pre_freeze_sha256: str | None = None,
) -> dict[str, Any]:
    root = _reject_symlink_path_components(
        aggregate_root,
        label="render_diagnostic_status_root",
    )
    cells = []
    for slot in render_diagnostic_slots():
        cell_root = root / "cells" / slot["cell_name"]
        intent_path = root / "launch_intents" / f"{slot['cell_name']}.json"
        success_path = cell_root / "matrix_cell_evidence.json"
        failure_path = cell_root / "matrix_cell_failure_evidence.json"
        record = {
            "variant": slot["variant"],
            "replicate": slot["replicate"],
            "execution_order_index": slot["execution_order_index"],
            "launch_intent_path": None,
            "launch_intent_sha256": None,
            "cell_root": str(cell_root),
            "cell_evidence_path": None,
            "cell_evidence_sha256": None,
            "classification": None,
            "child_exit_code": None,
            "status": "NOT_LAUNCHED",
        }
        intent_present = intent_path.exists() or intent_path.is_symlink()
        if not intent_present:
            if cell_root.exists() or cell_root.is_symlink():
                record["status"] = "MIXED_UNREGISTERED_CELL_ROOT"
            cells.append(record)
            continue
        record["launch_intent_path"] = str(intent_path)
        try:
            intent = _load_launch_intent(intent_path, slot)
            if (
                expected_pre_freeze_sha256 is not None
                and intent["pre_freeze_sha256"]
                != expected_pre_freeze_sha256
            ):
                raise ValueError("render_diagnostic_launch_pre_freeze_mismatch")
        except (OSError, TypeError, ValueError):
            record["launch_intent_sha256"] = _artifact_fingerprint_sha256(
                intent_path
            )
            record["status"] = "LAUNCHED_EVIDENCE_MISSING"
            cells.append(record)
            continue
        record["launch_intent_sha256"] = intent["launch_intent_sha256"]
        success_present = success_path.exists() or success_path.is_symlink()
        failure_present = failure_path.exists() or failure_path.is_symlink()
        if success_present and not failure_present:
            try:
                evidence = validate_render_diagnostic_matrix_cell_evidence(
                    _load_json_object(
                        success_path,
                        label="matrix_cell_evidence",
                    ),
                    expected_cell_root=cell_root,
                    expected_slot=slot,
                )
                implementation = _load_json_object(
                    cell_root / "matrix_implementation_identity.json",
                    label="matrix_implementation_identity",
                )
                closure = validate_render_diagnostic_cell_artifact_closure(
                    cell_root=cell_root,
                    expected_slot=slot,
                    expected_implementation_identity=(
                        expected_implementation_identity or implementation
                    ),
                    expected_launch_intent=intent,
                )
                evidence = closure["cell_evidence"]
            except (OSError, ValueError):
                record["status"] = "LAUNCHED_EVIDENCE_MISSING"
            else:
                record.update(
                    {
                        "cell_evidence_path": str(success_path),
                        "cell_evidence_sha256": evidence[
                            "matrix_cell_evidence_sha256"
                        ],
                        "classification": evidence["classification"],
                        "child_exit_code": evidence["child_exit_code"],
                        "status": "SUCCESS",
                    }
                )
        elif failure_present and not success_present:
            try:
                failure = validate_render_diagnostic_cell_failure_evidence(
                    _load_json_object(
                        failure_path,
                        label="matrix_cell_failure_evidence",
                    ),
                    expected_cell_root=cell_root,
                    expected_slot=slot,
                    expected_launch_intent=intent,
                    expected_implementation_identity={
                        "implementation_identity_sha256": intent[
                            "implementation_identity_sha256"
                        ]
                    },
                )
            except (OSError, TypeError, ValueError):
                record["status"] = "LAUNCHED_EVIDENCE_MISSING"
            else:
                record.update(
                    {
                        "cell_evidence_path": str(failure_path),
                        "cell_evidence_sha256": failure[
                            "matrix_cell_failure_evidence_sha256"
                        ],
                        "classification": failure["classification"],
                        "child_exit_code": failure["child_exit_code"],
                        "status": "FAILED",
                    }
                )
        else:
            record["status"] = "LAUNCHED_EVIDENCE_MISSING"
        cells.append(record)
    index = {
        "schema_version": 1,
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "cells": cells,
    }
    return validate_render_diagnostic_cell_status_index(index)


def validate_render_diagnostic_cell_status_index(
    index: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(index, Mapping) or set(index) != {
        "schema_version",
        "experiment_id",
        "cells",
    }:
        raise ValueError("render_diagnostic_cell_status_index_schema_invalid")
    actual = _json_native_copy(dict(index))
    cells = actual.get("cells")
    slots = render_diagnostic_slots()
    fields = {
        "variant",
        "replicate",
        "execution_order_index",
        "launch_intent_path",
        "launch_intent_sha256",
        "cell_root",
        "cell_evidence_path",
        "cell_evidence_sha256",
        "classification",
        "child_exit_code",
        "status",
    }
    if (
        actual.get("schema_version") != 1
        or actual.get("experiment_id") != RENDER_DIAGNOSTIC_EXPERIMENT_ID
        or not isinstance(cells, list)
        or len(cells) != len(slots)
    ):
        raise ValueError("render_diagnostic_cell_status_index_schema_invalid")
    for record, slot in zip(cells, slots):
        if not isinstance(record, Mapping) or set(record) != fields:
            raise ValueError("render_diagnostic_cell_status_record_invalid")
        root = (
            _absolute_path_without_symlink_resolution(
                RENDER_DIAGNOSTIC_AGGREGATE_ROOT
            )
            / "cells"
            / slot["cell_name"]
        )
        status = record.get("status")
        if (
            record.get("variant") != slot["variant"]
            or record.get("replicate") != slot["replicate"]
            or record.get("execution_order_index")
            != slot["execution_order_index"]
            or record.get("cell_root") != str(root)
            or status
            not in {
                "NOT_LAUNCHED",
                "MIXED_UNREGISTERED_CELL_ROOT",
                "LAUNCHED_EVIDENCE_MISSING",
                "FAILED",
                "SUCCESS",
            }
        ):
            raise ValueError("render_diagnostic_cell_status_record_invalid")
        intent_fields_valid = (
            isinstance(record.get("launch_intent_path"), str)
            and bool(record["launch_intent_path"])
            and _is_sha256_text(record.get("launch_intent_sha256"))
        )
        evidence_fields_null = all(
            record.get(field) is None
            for field in (
                "cell_evidence_path",
                "cell_evidence_sha256",
                "classification",
                "child_exit_code",
            )
        )
        if status in {"NOT_LAUNCHED", "MIXED_UNREGISTERED_CELL_ROOT"}:
            if (
                record.get("launch_intent_path") is not None
                or record.get("launch_intent_sha256") is not None
                or not evidence_fields_null
            ):
                raise ValueError("render_diagnostic_cell_status_record_invalid")
        elif status == "LAUNCHED_EVIDENCE_MISSING":
            if not intent_fields_valid or not evidence_fields_null:
                raise ValueError("render_diagnostic_cell_status_record_invalid")
        elif status == "FAILED":
            if (
                not intent_fields_valid
                or not isinstance(record.get("cell_evidence_path"), str)
                or not _is_sha256_text(record.get("cell_evidence_sha256"))
                or not isinstance(record.get("classification"), str)
                or not record["classification"]
                or record["classification"]
                == "DIAGNOSTIC_RENDER_COMPLETE_PENDING_VISUAL_REVIEW"
                or (
                    record.get("child_exit_code") is not None
                    and type(record["child_exit_code"]) is not int
                )
            ):
                raise ValueError("render_diagnostic_cell_status_record_invalid")
        elif status == "SUCCESS" and (
            not intent_fields_valid
            or not isinstance(record.get("cell_evidence_path"), str)
            or not _is_sha256_text(record.get("cell_evidence_sha256"))
            or record.get("classification")
            != "DIAGNOSTIC_RENDER_COMPLETE_PENDING_VISUAL_REVIEW"
            or record.get("child_exit_code") != 0
        ):
            raise ValueError("render_diagnostic_cell_status_record_invalid")
    return actual


def snapshot_render_diagnostic_protected_registry(
    *,
    protected_roots: Sequence[str | os.PathLike[str]],
    protected_files: Sequence[str | os.PathLike[str]],
    registry_id: str,
) -> dict[str, Any]:
    if not isinstance(registry_id, str) or not registry_id:
        raise ValueError("protected_registry_id_invalid")

    def capture() -> dict[str, Any]:
        root_records = []
        for raw_root in protected_roots:
            root, records = _snapshot_pinned_regular_tree(
                raw_root,
                label="protected_registry",
            )
            root_records.append({"root_path": str(root), "files": records})
        file_records = []
        for raw_path in protected_files:
            evidence = _hash_regular_file_pinned(
                raw_path,
                label="protected_registry_file",
            )
            file_records.append(
                {
                    "path": evidence["path"],
                    "byte_count": evidence["byte_count"],
                    "sha256": evidence["sha256"],
                }
            )
        return {
            "schema_version": 1,
            "registry_id": registry_id,
            "protected_roots": root_records,
            "protected_files": file_records,
        }

    first = capture()
    second = capture()
    if first != second:
        raise ValueError("protected_registry_changed_during_snapshot")
    return first


def snapshot_default_render_diagnostic_protected_registry() -> dict[str, Any]:
    return snapshot_render_diagnostic_protected_registry(
        protected_roots=RENDER_DIAGNOSTIC_PROTECTED_ROOTS,
        protected_files=RENDER_DIAGNOSTIC_PROTECTED_FILES,
        registry_id=RENDER_DIAGNOSTIC_PROTECTED_REGISTRY_ID,
    )


def _validate_render_diagnostic_protected_snapshot_structure(
    snapshot: Mapping[str, Any],
    *,
    protected_roots: Sequence[str | os.PathLike[str]] | None = None,
    protected_files: Sequence[str | os.PathLike[str]] | None = None,
    registry_id: str | None = None,
) -> tuple[dict[str, Any], tuple[Any, ...], tuple[Any, ...], str]:
    expected_roots = tuple(
        RENDER_DIAGNOSTIC_PROTECTED_ROOTS
        if protected_roots is None
        else protected_roots
    )
    expected_files = tuple(
        RENDER_DIAGNOSTIC_PROTECTED_FILES
        if protected_files is None
        else protected_files
    )
    expected_registry_id = (
        RENDER_DIAGNOSTIC_PROTECTED_REGISTRY_ID
        if registry_id is None
        else registry_id
    )
    if (
        not isinstance(snapshot, Mapping)
        or set(snapshot)
        != {"schema_version", "registry_id", "protected_roots", "protected_files"}
        or snapshot.get("schema_version") != 1
        or not isinstance(snapshot.get("registry_id"), str)
        or not isinstance(snapshot.get("protected_roots"), list)
        or not isinstance(snapshot.get("protected_files"), list)
    ):
        raise ValueError("protected_registry_snapshot_schema_invalid")
    expected_root_paths = [
        str(
            _reject_symlink_path_components(
                path,
                label="protected_registry_expected_root",
            )
        )
        for path in expected_roots
    ]
    expected_file_paths = [
        str(
            _reject_symlink_path_components(
                path,
                label="protected_registry_expected_file",
            )
        )
        for path in expected_files
    ]
    roots = snapshot["protected_roots"]
    files = snapshot["protected_files"]
    if (
        snapshot.get("registry_id") != expected_registry_id
        or len(roots) != len(expected_root_paths)
        or len(files) != len(expected_file_paths)
        or any(
            not isinstance(record, Mapping)
            or set(record) != {"root_path", "files"}
            or record.get("root_path") != expected_path
            or not isinstance(record.get("files"), list)
            for record, expected_path in zip(roots, expected_root_paths)
        )
        or any(
            not isinstance(record, Mapping)
            or set(record) != {"path", "byte_count", "sha256"}
            or record.get("path") != expected_path
            for record, expected_path in zip(files, expected_file_paths)
        )
        or any(
            not isinstance(item, Mapping)
            or set(item) != {"path", "byte_count", "sha256"}
            or not isinstance(item.get("path"), str)
            or not item["path"]
            or Path(item["path"]).is_absolute()
            or ".." in Path(item["path"]).parts
            or type(item.get("byte_count")) is not int
            or item["byte_count"] < 0
            or not _is_sha256_text(item.get("sha256"))
            for root_record in roots
            for item in root_record["files"]
        )
        or any(
            type(record.get("byte_count")) is not int
            or record["byte_count"] < 0
            or not _is_sha256_text(record.get("sha256"))
            for record in files
        )
        or any(
            root_record["files"]
            != sorted(root_record["files"], key=lambda item: item["path"])
            or len({item["path"] for item in root_record["files"]})
            != len(root_record["files"])
            for root_record in roots
        )
    ):
        raise ValueError("protected_registry_snapshot_schema_invalid")
    return (
        _json_native_copy(dict(snapshot)),
        expected_roots,
        expected_files,
        expected_registry_id,
    )


def validate_render_diagnostic_protected_snapshot(
    snapshot: Mapping[str, Any],
    *,
    protected_roots: Sequence[str | os.PathLike[str]] | None = None,
    protected_files: Sequence[str | os.PathLike[str]] | None = None,
    registry_id: str | None = None,
) -> dict[str, Any]:
    actual, expected_roots, expected_files, expected_registry_id = (
        _validate_render_diagnostic_protected_snapshot_structure(
            snapshot,
            protected_roots=protected_roots,
            protected_files=protected_files,
            registry_id=registry_id,
        )
    )
    expected = snapshot_render_diagnostic_protected_registry(
        protected_roots=expected_roots,
        protected_files=expected_files,
        registry_id=expected_registry_id,
    )
    if actual != expected:
        raise ValueError("protected_registry_snapshot_content_mismatch")
    return actual


def write_default_render_diagnostic_protected_snapshot(
    path: str | os.PathLike[str],
) -> dict[str, Any]:
    snapshot = snapshot_default_render_diagnostic_protected_registry()
    _write_json_create_exclusive(
        _absolute_path_without_symlink_resolution(path),
        snapshot,
    )
    return snapshot


def validate_historical_003_terminal_attestation() -> dict[str, Any]:
    evidence = _hash_regular_file_pinned(
        HISTORICAL_003_TERMINAL_ATTESTATION_PATH,
        label="historical_003_terminal_attestation",
    )
    if evidence["sha256"] != HISTORICAL_003_TERMINAL_ATTESTATION_FILE_SHA256:
        raise ValueError("historical_003_terminal_attestation_file_hash_mismatch")
    actual = _load_json_object(
        HISTORICAL_003_TERMINAL_ATTESTATION_PATH,
        label="historical_003_terminal_attestation",
    )
    fields = {
        "schema_version",
        "attestation_id",
        "experiment_id",
        "aggregate_root",
        "aggregate_tree_files",
        "aggregate_tree_sha256",
        "external_files",
        "anchor_sha256",
        "decision_sha256",
        "decision_commit_sha256",
        "publication_intent_sha256",
        "authority_witness_sha256",
        "terminal_state",
        "cell_status_index",
        "cell_status_index_sha256",
        "validated_launch_chain",
        "validated_launch_chain_sha256",
        "semantic_validation_passed",
        "authority_validation_passed",
        "terminal_validation_sha256",
    }
    payload = {
        key: value
        for key, value in actual.items()
        if key != "terminal_validation_sha256"
    }
    if (
        set(actual) != fields
        or actual.get("schema_version") != 1
        or actual.get("experiment_id") != HISTORICAL_003_EXPERIMENT_ID
        or actual.get("aggregate_root") != str(HISTORICAL_003_AGGREGATE_ROOT)
        or actual.get("semantic_validation_passed") is not True
        or actual.get("authority_validation_passed") is not True
        or actual.get("aggregate_tree_sha256")
        != canonical_json_sha256_v1(actual.get("aggregate_tree_files"))
        or actual.get("cell_status_index_sha256")
        != canonical_json_sha256_v1(actual.get("cell_status_index"))
        or actual.get("validated_launch_chain_sha256")
        != canonical_json_sha256_v1(actual.get("validated_launch_chain"))
        or actual.get("terminal_validation_sha256")
        != HISTORICAL_003_TERMINAL_ATTESTATION_LOGICAL_SHA256
        or canonical_json_sha256_v1(payload)
        != HISTORICAL_003_TERMINAL_ATTESTATION_LOGICAL_SHA256
    ):
        raise ValueError("historical_003_terminal_attestation_invalid")
    external = actual.get("external_files")
    if not isinstance(external, Mapping) or set(external) != {
        "aggregate_lock",
        "implementation_identity",
        "post_freeze",
        "pre_freeze",
    }:
        raise ValueError("historical_003_terminal_attestation_external_invalid")
    external_fields = {
        "path",
        "byte_count",
        "sha256",
        "device",
        "inode",
        "file_type",
    }
    for record in external.values():
        if not isinstance(record, Mapping) or set(record) != external_fields:
            raise ValueError("historical_003_terminal_attestation_external_invalid")
        observed = _hash_regular_file_pinned(
            record["path"],
            label="historical_003_terminal_external",
        )
        if any(observed[field] != record[field] for field in external_fields):
            raise ValueError("historical_003_terminal_attestation_external_changed")
    checked_root, tree = _snapshot_pinned_regular_tree(
        HISTORICAL_003_AGGREGATE_ROOT,
        label="historical_003_terminal_tree",
    )
    statuses = [
        record.get("status")
        for record in (actual.get("cell_status_index") or {}).get("cells", [])
        if isinstance(record, Mapping)
    ]
    if (
        checked_root != HISTORICAL_003_AGGREGATE_ROOT
        or tree != actual.get("aggregate_tree_files")
        or len(tree) != 349
        or (actual.get("terminal_state") or {}).get("code")
        != "STOP_CELL_RUNTIME_OR_ARTIFACT_FAILURE"
        or len(statuses) != 16
        or statuses.count("FAILED") != 1
        or statuses.count("NOT_LAUNCHED") != 15
    ):
        raise ValueError("historical_003_terminal_attestation_semantics_invalid")
    return _json_native_copy(actual)


def validate_historical_004_terminal_state() -> dict[str, Any]:
    decision_path = (
        HISTORICAL_004_AGGREGATE_ROOT
        / RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME
        / "matrix_decision.json"
    )
    status_path = HISTORICAL_004_AGGREGATE_ROOT / "evidence/cell_status_index.json"
    decision = _load_json_object(
        decision_path,
        label="historical_004_matrix_decision",
    )
    status_index = _load_json_object(
        status_path,
        label="historical_004_cell_status_index",
    )
    cells = status_index.get("cells")
    statuses = [
        record.get("status")
        for record in cells or []
        if isinstance(record, Mapping)
    ]
    failed = [
        record
        for record in cells or []
        if isinstance(record, Mapping) and record.get("status") == "FAILED"
    ]
    decision_payload = {
        key: value
        for key, value in decision.items()
        if key not in {"generated_at_utc", "matrix_decision_sha256"}
    }
    external_paths = {
        "aggregate_lock": HISTORICAL_004_AGGREGATE_ROOT.parent
        / f".{HISTORICAL_004_EXPERIMENT_ID}.aggregate.lock",
        "implementation_identity": HISTORICAL_004_AGGREGATE_ROOT.parent
        / f"{HISTORICAL_004_EXPERIMENT_ID}_implementation_identity.json",
        "pre_freeze": HISTORICAL_004_AGGREGATE_ROOT.parent
        / f"{HISTORICAL_004_EXPERIMENT_ID}_protected_tree_freeze_pre.json",
        "post_freeze": HISTORICAL_004_AGGREGATE_ROOT.parent
        / f"{HISTORICAL_004_EXPERIMENT_ID}_protected_tree_freeze_post.json",
    }
    decision_file_sha256 = _sha256_file(decision_path)
    status_file_sha256 = _sha256_file(status_path)
    external_file_sha256 = {
        role: _sha256_file(path) for role, path in external_paths.items()
    }
    if (
        decision.get("schema_version") != 1
        or decision.get("experiment_id") != HISTORICAL_004_EXPERIMENT_ID
        or decision.get("implementation_identity_sha256")
        != HISTORICAL_004_IMPLEMENTATION_IDENTITY_SHA256
        or decision.get("pre_freeze_sha256")
        != HISTORICAL_004_PRE_FREEZE_SHA256
        or decision.get("post_freeze_sha256")
        != HISTORICAL_004_POST_FREEZE_SHA256
        or decision.get("matrix_decision_sha256")
        != HISTORICAL_004_MATRIX_DECISION_SHA256
        or decision.get("matrix_decision_sha256")
        != canonical_json_sha256_v1(decision_payload)
        or decision_file_sha256 != HISTORICAL_004_DECISION_FILE_SHA256
        or status_file_sha256 != HISTORICAL_004_CELL_STATUS_FILE_SHA256
        or external_file_sha256 != HISTORICAL_004_EXTERNAL_FILE_SHA256
        or (decision.get("terminal_state") or {}).get("code")
        != "STOP_CELL_RUNTIME_OR_ARTIFACT_FAILURE"
        or status_index.get("schema_version") != 1
        or status_index.get("experiment_id") != HISTORICAL_004_EXPERIMENT_ID
        or decision.get("cell_status_index") != status_index
        or not isinstance(cells, list)
        or len(cells) != 16
        or statuses.count("FAILED") != 1
        or statuses.count("NOT_LAUNCHED") != 15
        or len(failed) != 1
        or failed[0].get("classification") != "STOP_RUNTIME_ERROR"
        or failed[0].get("variant") != "AO0_RT4_CONTROL"
        or failed[0].get("replicate") != "A"
        or failed[0].get("execution_order_index") != 0
    ):
        raise ValueError("historical_004_terminal_state_invalid")
    payload = {
        "schema_version": 1,
        "experiment_id": HISTORICAL_004_EXPERIMENT_ID,
        "terminal_state": _json_native_copy(decision["terminal_state"]),
        "cell_status_index": _json_native_copy(status_index),
        "decision_file_sha256": decision_file_sha256,
        "cell_status_file_sha256": status_file_sha256,
        "external_file_sha256": external_file_sha256,
    }
    return {
        **payload,
        "terminal_validation_sha256": canonical_json_sha256_v1(payload),
    }


def validate_historical_005_terminal_state() -> dict[str, Any]:
    decision_path = (
        HISTORICAL_005_AGGREGATE_ROOT
        / RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME
        / "matrix_decision.json"
    )
    status_path = HISTORICAL_005_AGGREGATE_ROOT / "evidence/cell_status_index.json"
    failure_path = (
        HISTORICAL_005_AGGREGATE_ROOT
        / "cells/A_0_AO0_RT4_CONTROL/matrix_cell_failure_evidence.json"
    )
    decision = _load_json_object(
        decision_path,
        label="historical_005_matrix_decision",
    )
    status_index = _load_json_object(
        status_path,
        label="historical_005_cell_status_index",
    )
    failure = _load_json_object(
        failure_path,
        label="historical_005_failure_evidence",
    )
    cells = status_index.get("cells")
    statuses = [
        record.get("status")
        for record in cells or []
        if isinstance(record, Mapping)
    ]
    failed = [
        record
        for record in cells or []
        if isinstance(record, Mapping) and record.get("status") == "FAILED"
    ]
    decision_payload = {
        key: value
        for key, value in decision.items()
        if key not in {"generated_at_utc", "matrix_decision_sha256"}
    }
    failure_payload = {
        key: value
        for key, value in failure.items()
        if key not in {"generated_at_utc", "matrix_cell_failure_evidence_sha256"}
    }
    external_paths = {
        "aggregate_lock": HISTORICAL_005_AGGREGATE_ROOT.parent
        / f".{HISTORICAL_005_EXPERIMENT_ID}.aggregate.lock",
        "implementation_identity": HISTORICAL_005_AGGREGATE_ROOT.parent
        / f"{HISTORICAL_005_EXPERIMENT_ID}_implementation_identity.json",
        "pre_freeze": HISTORICAL_005_AGGREGATE_ROOT.parent
        / f"{HISTORICAL_005_EXPERIMENT_ID}_protected_tree_freeze_pre.json",
        "post_freeze": HISTORICAL_005_AGGREGATE_ROOT.parent
        / f"{HISTORICAL_005_EXPERIMENT_ID}_protected_tree_freeze_post.json",
    }
    decision_file_sha256 = _sha256_file(decision_path)
    status_file_sha256 = _sha256_file(status_path)
    failure_file_sha256 = _sha256_file(failure_path)
    external_file_sha256 = {
        role: _sha256_file(path) for role, path in external_paths.items()
    }
    if (
        decision.get("schema_version") != 1
        or decision.get("experiment_id") != HISTORICAL_005_EXPERIMENT_ID
        or decision.get("implementation_identity_sha256")
        != HISTORICAL_005_IMPLEMENTATION_IDENTITY_SHA256
        or decision.get("pre_freeze_sha256")
        != HISTORICAL_005_PRE_FREEZE_SHA256
        or decision.get("post_freeze_sha256")
        != HISTORICAL_005_POST_FREEZE_SHA256
        or decision.get("matrix_decision_sha256")
        != HISTORICAL_005_MATRIX_DECISION_SHA256
        or decision.get("matrix_decision_sha256")
        != canonical_json_sha256_v1(decision_payload)
        or decision_file_sha256 != HISTORICAL_005_DECISION_FILE_SHA256
        or status_file_sha256 != HISTORICAL_005_CELL_STATUS_FILE_SHA256
        or failure_file_sha256 != HISTORICAL_005_FAILURE_FILE_SHA256
        or external_file_sha256 != HISTORICAL_005_EXTERNAL_FILE_SHA256
        or (decision.get("terminal_state") or {}).get("code")
        != "STOP_CELL_RUNTIME_OR_ARTIFACT_FAILURE"
        or status_index.get("schema_version") != 1
        or status_index.get("experiment_id") != HISTORICAL_005_EXPERIMENT_ID
        or decision.get("cell_status_index") != status_index
        or not isinstance(cells, list)
        or len(cells) != 16
        or statuses.count("FAILED") != 1
        or statuses.count("NOT_LAUNCHED") != 15
        or len(failed) != 1
        or failed[0].get("classification") != "STOP_RUNTIME_ERROR"
        or failed[0].get("variant") != "AO0_RT4_CONTROL"
        or failed[0].get("replicate") != "A"
        or failed[0].get("execution_order_index") != 0
        or failed[0].get("child_exit_code") != 0
        or failed[0].get("cell_evidence_path") != str(failure_path)
        or failed[0].get("cell_evidence_sha256")
        != failure.get("matrix_cell_failure_evidence_sha256")
        or failure.get("matrix_cell_failure_evidence_sha256")
        != canonical_json_sha256_v1(failure_payload)
        or failure.get("experiment_id") != HISTORICAL_005_EXPERIMENT_ID
        or failure.get("failure_stage")
        != "parent_launcher_sidecar_finalization"
        or failure.get("classification") != "STOP_RUNTIME_ERROR"
        or failure.get("child_exit_code") != 0
        or failure.get("error_type") != "ValueError"
        or failure.get("error_message")
        != "matrix_sidecar_established_input_mismatch"
    ):
        raise ValueError("historical_005_terminal_state_invalid")
    payload = {
        "schema_version": 1,
        "experiment_id": HISTORICAL_005_EXPERIMENT_ID,
        "terminal_state": _json_native_copy(decision["terminal_state"]),
        "cell_status_index": _json_native_copy(status_index),
        "failed_cell_evidence": _json_native_copy(failure),
        "decision_file_sha256": decision_file_sha256,
        "cell_status_file_sha256": status_file_sha256,
        "failure_file_sha256": failure_file_sha256,
        "external_file_sha256": external_file_sha256,
    }
    return {
        **payload,
        "terminal_validation_sha256": canonical_json_sha256_v1(payload),
    }


def validate_historical_006_terminal_state() -> dict[str, Any]:
    decision_path = (
        HISTORICAL_006_AGGREGATE_ROOT
        / RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME
        / "matrix_decision.json"
    )
    status_path = HISTORICAL_006_AGGREGATE_ROOT / "evidence/cell_status_index.json"
    failure_path = (
        HISTORICAL_006_AGGREGATE_ROOT
        / "cells/A_0_AO0_RT4_CONTROL/matrix_cell_failure_evidence.json"
    )
    decision = _load_json_object(
        decision_path,
        label="historical_006_matrix_decision",
    )
    status_index = _load_json_object(
        status_path,
        label="historical_006_cell_status_index",
    )
    failure = _load_json_object(
        failure_path,
        label="historical_006_failure_evidence",
    )
    cells = status_index.get("cells")
    statuses = [
        record.get("status")
        for record in cells or []
        if isinstance(record, Mapping)
    ]
    failed = [
        record
        for record in cells or []
        if isinstance(record, Mapping) and record.get("status") == "FAILED"
    ]
    decision_payload = {
        key: value
        for key, value in decision.items()
        if key not in {"generated_at_utc", "matrix_decision_sha256"}
    }
    failure_payload = {
        key: value
        for key, value in failure.items()
        if key not in {"generated_at_utc", "matrix_cell_failure_evidence_sha256"}
    }
    external_paths = {
        "aggregate_lock": HISTORICAL_006_AGGREGATE_ROOT.parent
        / f".{HISTORICAL_006_EXPERIMENT_ID}.aggregate.lock",
        "implementation_identity": HISTORICAL_006_AGGREGATE_ROOT.parent
        / f"{HISTORICAL_006_EXPERIMENT_ID}_implementation_identity.json",
        "pre_freeze": HISTORICAL_006_AGGREGATE_ROOT.parent
        / f"{HISTORICAL_006_EXPERIMENT_ID}_protected_tree_freeze_pre.json",
        "post_freeze": HISTORICAL_006_AGGREGATE_ROOT.parent
        / f"{HISTORICAL_006_EXPERIMENT_ID}_protected_tree_freeze_post.json",
    }
    decision_file_sha256 = _sha256_file(decision_path)
    status_file_sha256 = _sha256_file(status_path)
    failure_file_sha256 = _sha256_file(failure_path)
    external_file_sha256 = {
        role: _sha256_file(path) for role, path in external_paths.items()
    }
    if (
        decision.get("schema_version") != 1
        or decision.get("experiment_id") != HISTORICAL_006_EXPERIMENT_ID
        or decision.get("implementation_identity_sha256")
        != HISTORICAL_006_IMPLEMENTATION_IDENTITY_SHA256
        or decision.get("pre_freeze_sha256")
        != HISTORICAL_006_PRE_FREEZE_SHA256
        or decision.get("post_freeze_sha256")
        != HISTORICAL_006_POST_FREEZE_SHA256
        or decision.get("matrix_decision_sha256")
        != HISTORICAL_006_MATRIX_DECISION_SHA256
        or decision.get("matrix_decision_sha256")
        != canonical_json_sha256_v1(decision_payload)
        or decision_file_sha256 != HISTORICAL_006_DECISION_FILE_SHA256
        or status_file_sha256 != HISTORICAL_006_CELL_STATUS_FILE_SHA256
        or failure_file_sha256 != HISTORICAL_006_FAILURE_FILE_SHA256
        or external_file_sha256 != HISTORICAL_006_EXTERNAL_FILE_SHA256
        or (decision.get("terminal_state") or {}).get("code")
        != "STOP_CELL_RUNTIME_OR_ARTIFACT_FAILURE"
        or status_index.get("schema_version") != 1
        or status_index.get("experiment_id") != HISTORICAL_006_EXPERIMENT_ID
        or decision.get("cell_status_index") != status_index
        or not isinstance(cells, list)
        or len(cells) != 16
        or statuses.count("FAILED") != 1
        or statuses.count("NOT_LAUNCHED") != 15
        or len(failed) != 1
        or failed[0].get("classification") != "STOP_RUNTIME_ERROR"
        or failed[0].get("variant") != "AO0_RT4_CONTROL"
        or failed[0].get("replicate") != "A"
        or failed[0].get("execution_order_index") != 0
        or failed[0].get("child_exit_code") != 0
        or failed[0].get("cell_evidence_path") != str(failure_path)
        or failed[0].get("cell_evidence_sha256")
        != failure.get("matrix_cell_failure_evidence_sha256")
        or failure.get("matrix_cell_failure_evidence_sha256")
        != canonical_json_sha256_v1(failure_payload)
        or failure.get("experiment_id") != HISTORICAL_006_EXPERIMENT_ID
        or failure.get("failure_stage")
        != "parent_launcher_sidecar_finalization"
        or failure.get("classification") != "STOP_RUNTIME_ERROR"
        or failure.get("child_exit_code") != 0
        or failure.get("error_type") != "ValueError"
        or failure.get("error_message") != "matrix_cell_evidence_mismatch:hash"
    ):
        raise ValueError("historical_006_terminal_state_invalid")
    payload = {
        "schema_version": 1,
        "experiment_id": HISTORICAL_006_EXPERIMENT_ID,
        "terminal_state": _json_native_copy(decision["terminal_state"]),
        "cell_status_index": _json_native_copy(status_index),
        "failed_cell_evidence": _json_native_copy(failure),
        "decision_file_sha256": decision_file_sha256,
        "cell_status_file_sha256": status_file_sha256,
        "failure_file_sha256": failure_file_sha256,
        "external_file_sha256": external_file_sha256,
    }
    return {
        **payload,
        "terminal_validation_sha256": canonical_json_sha256_v1(payload),
    }


def validate_historical_007_terminal_state() -> dict[str, Any]:
    decision_path = (
        HISTORICAL_007_AGGREGATE_ROOT
        / RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME
        / "matrix_decision.json"
    )
    status_path = HISTORICAL_007_AGGREGATE_ROOT / "evidence/cell_status_index.json"
    decision = _load_json_object(
        decision_path,
        label="historical_007_matrix_decision",
    )
    status_index = _load_json_object(
        status_path,
        label="historical_007_cell_status_index",
    )
    cells = status_index.get("cells")
    statuses = [
        record.get("status")
        for record in cells or []
        if isinstance(record, Mapping)
    ]
    successful = [
        record
        for record in cells or []
        if isinstance(record, Mapping) and record.get("status") == "SUCCESS"
    ]
    decision_payload = {
        key: value
        for key, value in decision.items()
        if key not in {"generated_at_utc", "matrix_decision_sha256"}
    }
    external_paths = {
        "aggregate_lock": HISTORICAL_007_AGGREGATE_ROOT.parent
        / f".{HISTORICAL_007_EXPERIMENT_ID}.aggregate.lock",
        "implementation_identity": HISTORICAL_007_AGGREGATE_ROOT.parent
        / f"{HISTORICAL_007_EXPERIMENT_ID}_implementation_identity.json",
        "pre_freeze": HISTORICAL_007_AGGREGATE_ROOT.parent
        / f"{HISTORICAL_007_EXPERIMENT_ID}_protected_tree_freeze_pre.json",
        "post_freeze": HISTORICAL_007_AGGREGATE_ROOT.parent
        / f"{HISTORICAL_007_EXPERIMENT_ID}_protected_tree_freeze_post.json",
    }
    decision_file_sha256 = _sha256_file(decision_path)
    status_file_sha256 = _sha256_file(status_path)
    external_file_sha256 = {
        role: _sha256_file(path) for role, path in external_paths.items()
    }
    expected_success_root = (
        HISTORICAL_007_AGGREGATE_ROOT / "cells/A_0_AO0_RT4_CONTROL"
    )
    expected_success_evidence = expected_success_root / "matrix_cell_evidence.json"
    if (
        decision.get("schema_version") != 1
        or decision.get("experiment_id") != HISTORICAL_007_EXPERIMENT_ID
        or decision.get("implementation_identity_sha256")
        != HISTORICAL_007_IMPLEMENTATION_IDENTITY_SHA256
        or decision.get("pre_freeze_sha256")
        != HISTORICAL_007_PRE_FREEZE_SHA256
        or decision.get("post_freeze_sha256")
        != HISTORICAL_007_POST_FREEZE_SHA256
        or decision.get("matrix_decision_sha256")
        != HISTORICAL_007_MATRIX_DECISION_SHA256
        or decision.get("matrix_decision_sha256")
        != canonical_json_sha256_v1(decision_payload)
        or decision_file_sha256 != HISTORICAL_007_DECISION_FILE_SHA256
        or status_file_sha256 != HISTORICAL_007_CELL_STATUS_FILE_SHA256
        or external_file_sha256 != HISTORICAL_007_EXTERNAL_FILE_SHA256
        or (decision.get("terminal_state") or {}).get("code")
        != "INDETERMINATE_MATRIX_INCOMPLETE_OR_MIXED"
        or (decision.get("matrix_validation") or {}).get("status") != "FAIL"
        or (decision.get("repeat_stability") or {}).get("status")
        != "NOT_REACHED"
        or status_index.get("schema_version") != 1
        or status_index.get("experiment_id") != HISTORICAL_007_EXPERIMENT_ID
        or decision.get("cell_status_index") != status_index
        or not isinstance(cells, list)
        or len(cells) != 16
        or statuses.count("SUCCESS") != 1
        or statuses.count("NOT_LAUNCHED") != 15
        or len(successful) != 1
        or successful[0].get("classification")
        != "DIAGNOSTIC_RENDER_COMPLETE_PENDING_VISUAL_REVIEW"
        or successful[0].get("variant") != "AO0_RT4_CONTROL"
        or successful[0].get("replicate") != "A"
        or successful[0].get("execution_order_index") != 0
        or successful[0].get("child_exit_code") != 0
        or successful[0].get("cell_root") != str(expected_success_root)
        or successful[0].get("cell_evidence_path")
        != str(expected_success_evidence)
        or not _is_sha256_text(successful[0].get("cell_evidence_sha256"))
    ):
        raise ValueError("historical_007_terminal_state_invalid")
    payload = {
        "schema_version": 1,
        "experiment_id": HISTORICAL_007_EXPERIMENT_ID,
        "terminal_state": _json_native_copy(decision["terminal_state"]),
        "cell_status_index": _json_native_copy(status_index),
        "decision_file_sha256": decision_file_sha256,
        "cell_status_file_sha256": status_file_sha256,
        "external_file_sha256": external_file_sha256,
    }
    return {
        **payload,
        "terminal_validation_sha256": canonical_json_sha256_v1(payload),
    }


def validate_render_diagnostic_source_dependency_discovery(
    discovery: Mapping[str, Any],
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "discovery_id",
        "entry_source_usd_path",
        "allowed_roots",
        "layers",
        "assets",
        "unresolved",
        "status",
        "dependency_discovery_sha256",
    }
    if not isinstance(discovery, Mapping) or set(discovery) != fields:
        raise ValueError("source_dependency_discovery_schema_invalid")
    actual = _json_native_copy(dict(discovery))
    expected_roots = [
        str(_absolute_path_without_symlink_resolution(path))
        for path in (
            RENDER_DIAGNOSTIC_SOURCE_PACKAGE_ROOT,
            RENDER_DIAGNOSTIC_LOCALIZED_DEPENDENCY_ROOT,
        )
    ]
    payload = {
        key: value
        for key, value in actual.items()
        if key != "dependency_discovery_sha256"
    }
    path_lists = (actual.get("layers"), actual.get("assets"))
    if (
        actual.get("schema_version") != 1
        or actual.get("discovery_id")
        != "support_aligned_source_dependency_discovery_v1"
        or actual.get("entry_source_usd_path")
        != str(_absolute_path_without_symlink_resolution(
            RENDER_DIAGNOSTIC_SOURCE_ENTRY_PATH
        ))
        or actual.get("allowed_roots") != expected_roots
        or actual.get("unresolved") != []
        or actual.get("status") != "PASS"
        or actual.get("dependency_discovery_sha256")
        != canonical_json_sha256_v1(payload)
        or any(
            not isinstance(values, list)
            or values != sorted(set(values))
            or any(
                not isinstance(value, str) or not Path(value).is_absolute()
                for value in values
            )
            for values in path_lists
        )
    ):
        raise ValueError("source_dependency_discovery_invalid")
    roots = tuple(Path(path) for path in expected_roots)
    for value in [*actual["layers"], *actual["assets"]]:
        path = _absolute_path_without_symlink_resolution(value)
        if not any(path == root or root in path.parents for root in roots):
            raise ValueError(
                f"source_dependency_discovery_outside_allowed_roots:{path}"
            )
        checked = _reject_symlink_path_components(
            path,
            label="source_dependency_discovery_member",
        )
        if not checked.is_file() or checked.is_symlink():
            raise ValueError(
                f"source_dependency_discovery_member_invalid:{checked}"
            )
    return actual


def build_render_diagnostic_source_dependency_discovery() -> dict[str, Any]:
    from pxr import UsdUtils

    entry = _reject_symlink_path_components(
        RENDER_DIAGNOSTIC_SOURCE_ENTRY_PATH,
        label="source_dependency_discovery_entry",
    )
    if not entry.is_file() or entry.is_symlink():
        raise ValueError("source_dependency_discovery_entry_invalid")
    layers, assets, unresolved = UsdUtils.ComputeAllDependencies(str(entry))

    def normalized_path(value: str | os.PathLike[str]) -> str:
        raw = Path(os.fspath(value))
        if not raw.is_absolute():
            raw = entry.parent / raw
        return str(_absolute_path_without_symlink_resolution(raw))

    layer_paths = []
    for layer in layers:
        raw_path = str(getattr(layer, "realPath", "") or layer.identifier)
        layer_paths.append(normalized_path(raw_path))
    asset_paths = [normalized_path(str(asset)) for asset in assets]
    payload = {
        "schema_version": 1,
        "discovery_id": "support_aligned_source_dependency_discovery_v1",
        "entry_source_usd_path": str(
            _absolute_path_without_symlink_resolution(entry)
        ),
        "allowed_roots": [
            str(_absolute_path_without_symlink_resolution(path))
            for path in (
                RENDER_DIAGNOSTIC_SOURCE_PACKAGE_ROOT,
                RENDER_DIAGNOSTIC_LOCALIZED_DEPENDENCY_ROOT,
            )
        ],
        "layers": sorted(set(layer_paths)),
        "assets": sorted(set(asset_paths)),
        "unresolved": sorted(set(str(value) for value in unresolved)),
        "status": "PASS" if not unresolved else "FAIL",
    }
    return validate_render_diagnostic_source_dependency_discovery(
        {
            **payload,
            "dependency_discovery_sha256": canonical_json_sha256_v1(payload),
        }
    )


RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_DIRNAME = "source_dependency_snapshot"
RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_INTENT_BASENAME = (
    "source_dependency_snapshot_intent.json"
)
RENDER_DIAGNOSTIC_SOURCE_CLOSURE_BASENAME = (
    "matrix_source_dependency_closure.json"
)
RENDER_DIAGNOSTIC_ARTIFACT_INVENTORY_BASENAME = (
    "matrix_cell_artifact_inventory.json"
)
_RENDER_DIAGNOSTIC_SUCCESS_SIDECAR_BASENAMES = frozenset(
    {
        "matrix_frame_bindings.json",
        "matrix_media_index.json",
        "matrix_cell_evidence.json",
        "matrix_implementation_identity.json",
        "runtime_identity.json",
        "device_identity.json",
        "process_identity.json",
        "matrix_mdl_closure.json",
        RENDER_DIAGNOSTIC_SOURCE_CLOSURE_BASENAME,
        RENDER_DIAGNOSTIC_ARTIFACT_INVENTORY_BASENAME,
    }
)
_RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_ROOTS = (
    (
        "lab_001_level1_pour_support_aligned_v1_20260712",
        lambda: RENDER_DIAGNOSTIC_SOURCE_PACKAGE_ROOT,
    ),
    (
        "lab_001_localized_20260707",
        lambda: RENDER_DIAGNOSTIC_LOCALIZED_DEPENDENCY_ROOT,
    ),
)
_RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_ENTRY = (
    "lab_001_level1_pour_support_aligned_v1_20260712/"
    "lab_001_level1_pour_support_aligned_v1.usda"
)


def compute_usd_dependency_paths(
    entry_path: str | os.PathLike[str],
) -> tuple[list[Path], list[Path], list[str]]:
    from pxr import UsdUtils

    entry = _reject_symlink_path_components(
        entry_path,
        label="source_dependency_entry",
    )
    layers, assets, unresolved = UsdUtils.ComputeAllDependencies(str(entry))

    def absolute(value: Any) -> Path:
        raw = str(getattr(value, "realPath", "") or getattr(value, "identifier", "") or value)
        path = Path(raw)
        if not path.is_absolute():
            path = entry.parent / path
        return _absolute_path_without_symlink_resolution(path)

    return (
        sorted(set(absolute(layer) for layer in layers), key=str),
        sorted(set(absolute(asset) for asset in assets), key=str),
        sorted(set(str(value) for value in unresolved)),
    )


def _protected_source_root_records(
    protected_snapshot: Mapping[str, Any],
) -> list[tuple[Path, str, list[dict[str, Any]]]]:
    roots = protected_snapshot.get("protected_roots")
    if not isinstance(roots, list):
        raise ValueError("source_dependency_protected_snapshot_invalid")
    by_path = {
        record.get("root_path"): record
        for record in roots
        if isinstance(record, Mapping)
    }
    result = []
    for snapshot_subdirectory, root_getter in (
        _RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_ROOTS
    ):
        source_root = _absolute_path_without_symlink_resolution(root_getter())
        record = by_path.get(str(source_root))
        if (
            not isinstance(record, Mapping)
            or set(record) != {"root_path", "files"}
            or not isinstance(record.get("files"), list)
        ):
            raise ValueError("source_dependency_protected_root_missing")
        files = _json_native_copy(record["files"])
        if (
            files != sorted(files, key=lambda item: item.get("path", ""))
            or any(
                not isinstance(item, Mapping)
                or set(item) != {"path", "byte_count", "sha256"}
                or not isinstance(item.get("path"), str)
                or Path(item["path"]).is_absolute()
                or ".." in Path(item["path"]).parts
                or type(item.get("byte_count")) is not int
                or item["byte_count"] < 0
                or not _is_sha256_text(item.get("sha256"))
                for item in files
            )
        ):
            raise ValueError("source_dependency_protected_files_invalid")
        result.append((source_root, snapshot_subdirectory, files))
    return result


def build_render_diagnostic_source_dependency_closure(
    protected_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    root_records = _protected_source_root_records(protected_snapshot)
    source_roots = [
        {
            "source_root": str(source_root),
            "snapshot_subdirectory": snapshot_subdirectory,
        }
        for source_root, snapshot_subdirectory, _files in root_records
    ]
    files = sorted(
        [
            {
                "path": f"{snapshot_subdirectory}/{record['path']}",
                "byte_count": record["byte_count"],
                "sha256": record["sha256"],
            }
            for _source_root, snapshot_subdirectory, records in root_records
            for record in records
        ],
        key=lambda item: item["path"],
    )
    payload = {
        "schema_version": 1,
        "closure_id": "support_aligned_source_dependency_closure_v1",
        "source_roots": source_roots,
        "entry_source_usd_path": str(
            _absolute_path_without_symlink_resolution(
                RENDER_DIAGNOSTIC_SOURCE_ENTRY_PATH
            )
        ),
        "snapshot_entry_source_usd_path": (
            _RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_ENTRY
        ),
        "files": files,
    }
    return {
        **payload,
        "source_dependency_closure_sha256": canonical_json_sha256_v1(payload),
    }


def _validate_render_diagnostic_source_dependency_closure_schema(
    closure: Mapping[str, Any],
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "closure_id",
        "source_roots",
        "entry_source_usd_path",
        "snapshot_entry_source_usd_path",
        "files",
        "source_dependency_closure_sha256",
    }
    if not isinstance(closure, Mapping) or set(closure) != fields:
        raise ValueError("source_dependency_closure_schema_invalid")
    actual = _json_native_copy(dict(closure))
    payload = {
        key: value
        for key, value in actual.items()
        if key != "source_dependency_closure_sha256"
    }
    expected_roots = [
        {
            "source_root": str(
                _absolute_path_without_symlink_resolution(root_getter())
            ),
            "snapshot_subdirectory": snapshot_subdirectory,
        }
        for snapshot_subdirectory, root_getter in (
            _RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_ROOTS
        )
    ]
    files = actual.get("files")
    allowed_prefixes = {
        item["snapshot_subdirectory"] for item in expected_roots
    }
    if (
        actual.get("schema_version") != 1
        or actual.get("closure_id")
        != "support_aligned_source_dependency_closure_v1"
        or actual.get("source_roots") != expected_roots
        or actual.get("entry_source_usd_path")
        != str(_absolute_path_without_symlink_resolution(
            RENDER_DIAGNOSTIC_SOURCE_ENTRY_PATH
        ))
        or actual.get("snapshot_entry_source_usd_path")
        != _RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_ENTRY
        or not isinstance(files, list)
        or files != sorted(files, key=lambda item: item.get("path", ""))
        or len({item.get("path") for item in files if isinstance(item, Mapping)})
        != len(files)
        or any(
            not isinstance(item, Mapping)
            or set(item) != {"path", "byte_count", "sha256"}
            or not isinstance(item.get("path"), str)
            or Path(item["path"]).is_absolute()
            or len(Path(item["path"]).parts) < 2
            or Path(item["path"]).parts[0] not in allowed_prefixes
            or any(part in {"", ".", ".."} for part in Path(item["path"]).parts)
            or type(item.get("byte_count")) is not int
            or item["byte_count"] < 0
            or not _is_sha256_text(item.get("sha256"))
            for item in files
        )
        or actual.get("source_dependency_closure_sha256")
        != canonical_json_sha256_v1(payload)
    ):
        raise ValueError("source_dependency_closure_invalid")
    return actual


def _copy_regular_file_create_exclusive(
    source_path: Path,
    target_path: Path,
    *,
    expected_byte_count: int,
    expected_sha256: str,
    label: str,
) -> None:
    payload = _read_regular_file_snapshot(source_path, label=label)
    if (
        len(payload) != expected_byte_count
        or hashlib.sha256(payload).hexdigest() != expected_sha256
    ):
        raise ValueError(f"{label}_source_changed")
    target = _reject_symlink_path_components(target_path, label=f"{label}_target")
    target.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    with _open_pinned_path(
        target.parent,
        leaf_directory=True,
        label=f"{label}_destination_parent",
    ) as (_parent, parent_descriptor, identities):
        descriptor = os.open(
            target.name,
            flags,
            0o600,
            dir_fd=parent_descriptor,
        )
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                raise ValueError(f"{label}_destination_link_invalid")
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError(f"{label}_short_write")
                view = view[written:]
            os.fsync(descriptor)
            after = os.fstat(descriptor)
            named = os.stat(
                target.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                (after.st_dev, after.st_ino) != (named.st_dev, named.st_ino)
                or after.st_nlink != 1
                or named.st_nlink != 1
                or after.st_size != expected_byte_count
                or hashlib.sha256(
                    os.pread(descriptor, after.st_size, 0)
                ).hexdigest()
                != expected_sha256
            ):
                raise ValueError(f"{label}_destination_verification_failed")
            _verify_pinned_path_components(
                identities,
                label=f"{label}_destination_parent",
            )
        finally:
            os.close(descriptor)
        os.fsync(parent_descriptor)


def _write_source_snapshot_intent(
    cell_root: Path,
    intent: Mapping[str, Any],
    *,
    nonce: str,
) -> Path:
    fixed = cell_root / RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_INTENT_BASENAME
    temporary = cell_root / f".source_dependency_snapshot_intent.{nonce}.tmp"
    _write_json_create_exclusive(temporary, intent)
    _fsync_directory(cell_root)
    try:
        os.link(temporary, fixed, follow_symlinks=False)
        _fsync_directory(cell_root)
    except BaseException:
        if temporary.exists():
            temporary.unlink()
            _fsync_directory(cell_root)
        raise
    temporary.unlink()
    _fsync_directory(cell_root)
    return fixed


def _validate_source_snapshot_intent(
    intent: Mapping[str, Any],
    *,
    cell: Path,
    closure: Mapping[str, Any],
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "experiment_id",
        "cell_root",
        "target_path",
        "staging_path",
        "publication_nonce",
        "expected_source_dependency_closure_sha256",
        "generated_at_utc",
        "source_snapshot_intent_sha256",
    }
    if not isinstance(intent, Mapping) or set(intent) != fields:
        raise ValueError("source_dependency_snapshot_intent_schema_invalid")
    actual = _json_native_copy(dict(intent))
    nonce = actual.get("publication_nonce")
    payload = {
        key: value
        for key, value in actual.items()
        if key not in {"generated_at_utc", "source_snapshot_intent_sha256"}
    }
    if (
        actual.get("schema_version") != 1
        or actual.get("experiment_id") != RENDER_DIAGNOSTIC_EXPERIMENT_ID
        or actual.get("cell_root") != str(cell)
        or actual.get("target_path")
        != str(cell / RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_DIRNAME)
        or not isinstance(nonce, str)
        or len(nonce) != 64
        or any(character not in "0123456789abcdef" for character in nonce)
        or actual.get("staging_path")
        != str(cell / f".source_dependency_snapshot.{nonce}.staging")
        or actual.get("expected_source_dependency_closure_sha256")
        != closure["source_dependency_closure_sha256"]
        or not isinstance(actual.get("generated_at_utc"), str)
        or not actual["generated_at_utc"]
        or actual.get("source_snapshot_intent_sha256")
        != canonical_json_sha256_v1(payload)
    ):
        raise ValueError("source_dependency_snapshot_intent_invalid")
    return actual


def _cleanup_authenticated_source_snapshot_staging(
    staging: Path,
    *,
    closure: Mapping[str, Any],
) -> None:
    if not staging.exists():
        return
    if staging.is_symlink() or not staging.is_dir():
        raise ValueError("source_dependency_snapshot_staging_invalid")
    _root, records = _snapshot_pinned_regular_tree(
        staging,
        label="source_dependency_snapshot_recovery",
    )
    allowed = {record["path"] for record in closure["files"]}
    if any(record["path"] not in allowed for record in records):
        raise ValueError("source_dependency_snapshot_recovery_membership_invalid")
    for directory in sorted(
        [staging, *[path for path in staging.rglob("*") if path.is_dir()]],
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        directory.chmod(0o700)
    shutil.rmtree(staging)
    _fsync_directory(staging.parent)


def validate_render_diagnostic_source_dependency_snapshot(
    cell_root: str | os.PathLike[str],
    closure: Mapping[str, Any],
    *,
    verify_usd_dependencies: bool = True,
    additional_allowed_dependency_roots: Sequence[
        str | os.PathLike[str]
    ] = (),
) -> dict[str, Any]:
    actual = _validate_render_diagnostic_source_dependency_closure_schema(closure)
    cell = _reject_symlink_path_components(
        cell_root,
        label="source_dependency_cell",
    )
    snapshot_root = _reject_symlink_path_components(
        cell / RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_DIRNAME,
        label="source_dependency_snapshot_target",
    )
    if not snapshot_root.is_dir():
        raise ValueError("source_dependency_snapshot_target_missing")
    _root, records = _snapshot_pinned_regular_tree(
        snapshot_root,
        label="source_dependency_snapshot",
    )
    if records != actual["files"]:
        raise ValueError("source_dependency_snapshot_membership_mismatch")
    _validate_pinned_readonly_tree_modes(
        snapshot_root,
        label="source_dependency_snapshot",
    )
    if type(verify_usd_dependencies) is not bool:
        raise ValueError("source_dependency_snapshot_verify_usd_invalid")
    if verify_usd_dependencies:
        resolution = build_render_diagnostic_runtime_dependency_resolution(
            cell,
            actual,
            additional_allowed_dependency_roots=(
                additional_allowed_dependency_roots
            ),
        )
        if resolution["status"] != "PASS":
            raise ValueError("source_dependency_snapshot_usd_closure_invalid")
    return actual


def build_render_diagnostic_runtime_dependency_resolution(
    cell_root: str | os.PathLike[str],
    closure: Mapping[str, Any],
    *,
    additional_allowed_dependency_roots: Sequence[
        str | os.PathLike[str]
    ],
) -> dict[str, Any]:
    actual = _validate_render_diagnostic_source_dependency_closure_schema(
        closure
    )
    cell = _reject_symlink_path_components(
        cell_root,
        label="runtime_dependency_resolution_cell",
    )
    snapshot_root = cell / RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_DIRNAME
    allowed_roots = [
        snapshot_root,
        *[
            _reject_symlink_path_components(
                root,
                label="runtime_dependency_resolution_allowed_root",
            )
            for root in additional_allowed_dependency_roots
        ],
    ]
    entry = snapshot_root / actual["snapshot_entry_source_usd_path"]
    layers, assets, unresolved = compute_usd_dependency_paths(entry)
    outside = [
        str(path)
        for path in [*layers, *assets]
        if not any(path == root or root in path.parents for root in allowed_roots)
    ]
    payload = {
        "schema_version": 1,
        "resolver_runtime": "isaacsim41_post_simulation_app_boot",
        "entry_path": str(entry),
        "allowed_roots": [str(root) for root in allowed_roots],
        "layers": [str(path) for path in layers],
        "assets": [str(path) for path in assets],
        "unresolved": list(unresolved),
        "outside_allowed_roots": outside,
        "status": (
            "PASS" if not unresolved and not outside else "FAIL"
        ),
    }
    return {
        **payload,
        "runtime_dependency_resolution_sha256": canonical_json_sha256_v1(
            payload
        ),
    }


def build_render_diagnostic_exported_static_dependency_resolution(
    entry_path: str | os.PathLike[str],
    *,
    cell_root: str | os.PathLike[str],
    candidate_root: str | os.PathLike[str],
    material_closure_root: str | os.PathLike[str],
) -> dict[str, Any]:
    cell = _reject_symlink_path_components(
        cell_root,
        label="exported_static_dependency_cell",
    )
    candidate = _reject_symlink_path_components(
        candidate_root,
        label="exported_static_dependency_candidate",
    )
    snapshot = _reject_symlink_path_components(
        cell / RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_DIRNAME,
        label="exported_static_dependency_source_snapshot",
    )
    material = _reject_symlink_path_components(
        material_closure_root,
        label="exported_static_dependency_material_closure",
    )
    entry = _reject_symlink_path_components(
        entry_path,
        label="exported_static_dependency_entry",
    )
    if (
        candidate.parent != cell
        or entry != candidate / entry.name
        or not entry.is_file()
        or not snapshot.is_dir()
        or not material.is_dir()
    ):
        raise ValueError("exported_static_dependency_scope_invalid")
    allowed_roots = [candidate, snapshot, material]
    layers, assets, unresolved = compute_usd_dependency_paths(entry)
    outside = [
        str(path)
        for path in [*layers, *assets]
        if not any(path == root or root in path.parents for root in allowed_roots)
    ]
    payload = {
        "schema_version": 1,
        "resolver_runtime": (
            "isaacsim41_post_simulation_app_boot_exported_static_usd"
        ),
        "entry_path": str(entry),
        "allowed_roots": [str(root) for root in allowed_roots],
        "layers": [str(path) for path in layers],
        "assets": [str(path) for path in assets],
        "unresolved": list(unresolved),
        "outside_allowed_roots": outside,
        "status": "PASS" if not unresolved and not outside else "FAIL",
    }
    return {
        **payload,
        "runtime_dependency_resolution_sha256": canonical_json_sha256_v1(
            payload
        ),
    }


def validate_render_diagnostic_runtime_dependency_resolution(
    contract: Mapping[str, Any],
    *,
    cell_root: str | os.PathLike[str],
    material_closure_root: str | os.PathLike[str],
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "resolver_runtime",
        "entry_path",
        "allowed_roots",
        "layers",
        "assets",
        "unresolved",
        "outside_allowed_roots",
        "status",
        "runtime_dependency_resolution_sha256",
    }
    if not isinstance(contract, Mapping) or set(contract) != fields:
        raise ValueError("runtime_dependency_resolution_schema_invalid")
    actual = _json_native_copy(dict(contract))
    payload = {
        key: value
        for key, value in actual.items()
        if key != "runtime_dependency_resolution_sha256"
    }
    cell = _absolute_path_without_symlink_resolution(cell_root)
    snapshot_root = cell / RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_DIRNAME
    material_root = _absolute_path_without_symlink_resolution(
        material_closure_root
    )
    allowed = [snapshot_root, material_root]
    entry = snapshot_root / (
        "lab_001_level1_pour_support_aligned_v1_20260712/"
        "lab_001_level1_pour_support_aligned_v1.usda"
    )
    if (
        actual.get("schema_version") != 1
        or actual.get("resolver_runtime")
        != "isaacsim41_post_simulation_app_boot"
        or actual.get("entry_path") != str(entry)
        or actual.get("allowed_roots") != [str(root) for root in allowed]
        or not isinstance(actual.get("layers"), list)
        or not isinstance(actual.get("assets"), list)
        or actual.get("unresolved") != []
        or actual.get("outside_allowed_roots") != []
        or actual.get("status") != "PASS"
        or any(
            not isinstance(raw, str)
            or not Path(raw).is_absolute()
            or not any(
                _absolute_path_without_symlink_resolution(raw) == root
                or root in _absolute_path_without_symlink_resolution(raw).parents
                for root in allowed
            )
            for raw in [*actual["layers"], *actual["assets"]]
        )
        or actual.get("runtime_dependency_resolution_sha256")
        != canonical_json_sha256_v1(payload)
    ):
        raise ValueError("runtime_dependency_resolution_invalid")
    return actual


def publish_render_diagnostic_source_dependency_snapshot(
    cell_root: str | os.PathLike[str],
    *,
    protected_snapshot: Mapping[str, Any],
    publication_nonce: str | None = None,
    verify_usd_dependencies: bool = True,
) -> dict[str, Any]:
    nonce = publication_nonce or secrets.token_hex(32)
    if (
        not isinstance(nonce, str)
        or len(nonce) != 64
        or any(character not in "0123456789abcdef" for character in nonce)
    ):
        raise ValueError("source_dependency_snapshot_nonce_invalid")
    closure = build_render_diagnostic_source_dependency_closure(
        protected_snapshot
    )
    root_records = _protected_source_root_records(protected_snapshot)
    for source_root, _subdirectory, expected_records in root_records:
        _checked, current_records = _snapshot_pinned_regular_tree(
            source_root,
            label="source_dependency_snapshot_source",
        )
        if current_records != expected_records:
            raise ValueError("source_dependency_snapshot_source_changed")
    cell = _reject_symlink_path_components(
        cell_root,
        label="source_dependency_cell",
    )
    cell.mkdir(parents=True, exist_ok=True)
    if not cell.is_dir() or cell.is_symlink():
        raise ValueError("source_dependency_cell_invalid")
    target = cell / RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_DIRNAME
    journal = cell / RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_INTENT_BASENAME
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_dir():
            raise ValueError("source_dependency_snapshot_target_exists")
        validated = validate_render_diagnostic_source_dependency_snapshot(
            cell,
            closure,
            verify_usd_dependencies=verify_usd_dependencies,
        )
        sidecar = cell / RENDER_DIAGNOSTIC_SOURCE_CLOSURE_BASENAME
        if sidecar.exists() or sidecar.is_symlink():
            if (
                sidecar.is_symlink()
                or _load_json_object(
                    sidecar,
                    label="source_dependency_snapshot_closure",
                )
                != validated
            ):
                raise ValueError("source_dependency_snapshot_closure_changed")
        else:
            _write_json_create_exclusive(sidecar, validated)
        if journal.exists() or journal.is_symlink():
            if journal.is_symlink():
                raise ValueError("source_dependency_snapshot_intent_symlink")
            recovered_intent = _validate_source_snapshot_intent(
                _load_json_object(
                    journal,
                    label="source_dependency_snapshot_intent",
                ),
                cell=cell,
                closure=closure,
            )
            recovered_staging = Path(recovered_intent["staging_path"])
            if recovered_staging.exists() or recovered_staging.is_symlink():
                raise ValueError("source_dependency_snapshot_target_and_staging")
            journal.unlink()
        _fsync_directory(cell)
        return validated
    if journal.exists() or journal.is_symlink():
        if journal.is_symlink():
            raise ValueError("source_dependency_snapshot_intent_symlink")
        recovered_intent = _validate_source_snapshot_intent(
            _load_json_object(
                journal,
                label="source_dependency_snapshot_intent",
            ),
            cell=cell,
            closure=closure,
        )
        recovered_staging = Path(recovered_intent["staging_path"])
        _cleanup_authenticated_source_snapshot_staging(
            recovered_staging,
            closure=closure,
        )
        journal.unlink()
        _fsync_directory(cell)
        return publish_render_diagnostic_source_dependency_snapshot(
            cell,
            protected_snapshot=protected_snapshot,
            publication_nonce=publication_nonce,
            verify_usd_dependencies=verify_usd_dependencies,
        )
    staging = cell / f".source_dependency_snapshot.{nonce}.staging"
    if staging.exists() or staging.is_symlink():
        raise ValueError("source_dependency_snapshot_staging_exists")
    intent_payload = {
        "schema_version": 1,
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "cell_root": str(cell),
        "target_path": str(target),
        "staging_path": str(staging),
        "publication_nonce": nonce,
        "expected_source_dependency_closure_sha256": closure[
            "source_dependency_closure_sha256"
        ],
        "generated_at_utc": _utc_now(),
    }
    intent_hash_payload = {
        key: value
        for key, value in intent_payload.items()
        if key != "generated_at_utc"
    }
    intent = {
        **intent_payload,
        "source_snapshot_intent_sha256": canonical_json_sha256_v1(
            intent_hash_payload
        ),
    }
    journal = _write_source_snapshot_intent(cell, intent, nonce=nonce)
    staging.mkdir(mode=0o700)
    _fsync_directory(cell)
    try:
        for source_root, snapshot_subdirectory, records in root_records:
            for record in records:
                destination = staging / snapshot_subdirectory / record["path"]
                _copy_regular_file_create_exclusive(
                    source_root / record["path"],
                    destination,
                    expected_byte_count=record["byte_count"],
                    expected_sha256=record["sha256"],
                    label="source_dependency_snapshot",
                )
        for source_root, _subdirectory, expected_records in root_records:
            _checked, current_records = _snapshot_pinned_regular_tree(
                source_root,
                label="source_dependency_snapshot_source",
            )
            if current_records != expected_records:
                raise ValueError("source_dependency_snapshot_source_changed")
        directories = sorted(
            [path for path in staging.rglob("*") if path.is_dir()],
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for path in staging.rglob("*"):
            if path.is_file():
                path.chmod(0o444)
        for directory in directories:
            _fsync_directory(directory)
            directory.chmod(0o555)
        _fsync_directory(staging)
        staging.chmod(0o555)
        _atomic_rename_noreplace(staging, target)
        _fsync_directory(cell)
        validated = validate_render_diagnostic_source_dependency_snapshot(
            cell,
            closure,
            verify_usd_dependencies=verify_usd_dependencies,
        )
        _write_json_create_exclusive(
            cell / RENDER_DIAGNOSTIC_SOURCE_CLOSURE_BASENAME,
            validated,
        )
        _fsync_directory(cell)
        journal.unlink()
        _fsync_directory(cell)
        return validated
    except BaseException:
        raise


def build_render_diagnostic_cell_artifact_inventory(
    cell_root: str | os.PathLike[str],
    *,
    expected_relative_paths: set[str] | None = None,
) -> dict[str, Any]:
    root = _reject_symlink_path_components(
        cell_root,
        label="artifact_inventory_root",
    )
    if not root.is_dir() or root.is_symlink():
        raise ValueError("artifact_inventory_root_invalid")
    _checked, records = _snapshot_pinned_regular_tree(
        root,
        label="artifact_inventory",
    )
    inode_paths: dict[tuple[int, int], str] = {}
    for record in records:
        path = root / record["path"]
        metadata = os.lstat(path)
        identity = (metadata.st_dev, metadata.st_ino)
        if identity in inode_paths:
            raise ValueError(
                "artifact_inventory_duplicate_inode:"
                f"{inode_paths[identity]}:{record['path']}"
            )
        inode_paths[identity] = record["path"]
    expected_directories = {
        parent.as_posix()
        for record in records
        for parent in list(Path(record["path"]).parents)[:-1]
    }
    actual_directories = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_dir() and not path.is_symlink()
    }
    if actual_directories != expected_directories:
        raise ValueError(
            "artifact_inventory_directory_membership_invalid:"
            f"actual={sorted(actual_directories)}:"
            f"expected={sorted(expected_directories)}"
        )
    excluded = {
        "replay_manifest.json",
        *_RENDER_DIAGNOSTIC_SUCCESS_SIDECAR_BASENAMES,
    }
    files = [record for record in records if record["path"] not in excluded]
    if expected_relative_paths is not None:
        expected = {
            _normalized_render_diagnostic_snapshot_path(path)
            for path in expected_relative_paths
        }
        actual = {record["path"] for record in files}
        if actual != expected:
            raise ValueError(
                "artifact_inventory_unreferenced_or_missing:"
                f"actual={sorted(actual)}:expected={sorted(expected)}"
            )
    payload = {
        "schema_version": 1,
        "inventory_id": "matrix_cell_runtime_artifact_inventory_v1",
        "files": files,
    }
    return {
        **payload,
        "artifact_inventory_sha256": canonical_json_sha256_v1(payload),
    }


def build_render_diagnostic_expected_artifact_paths(
    final_manifest: Mapping[str, Any],
    *,
    cell_root: str | os.PathLike[str],
    authoritative_path_resolver: Any | None = None,
) -> set[str]:
    cell = _absolute_path_without_symlink_resolution(cell_root)
    excluded = {
        "replay_manifest.json",
        *_RENDER_DIAGNOSTIC_SUCCESS_SIDECAR_BASENAMES,
    }
    expected: set[str] = set()

    def authority(path: Path) -> Path:
        return _absolute_path_without_symlink_resolution(
            authoritative_path_resolver(path)
            if authoritative_path_resolver is not None
            else path
        )

    def add_if_file(raw_path: Any, *, required: bool = False) -> None:
        if not isinstance(raw_path, (str, os.PathLike)):
            if required:
                raise ValueError("artifact_inventory_expected_path_invalid")
            return
        logical = _absolute_path_without_symlink_resolution(raw_path)
        if logical == cell or cell not in logical.parents:
            if required:
                raise ValueError("artifact_inventory_expected_path_outside_cell")
            return
        checked = authority(logical)
        if not checked.is_file() or checked.is_symlink():
            if required:
                raise ValueError(
                    f"artifact_inventory_expected_file_missing:{logical}"
                )
            return
        relative = logical.relative_to(cell).as_posix()
        if relative not in excluded:
            expected.add(relative)

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for child in value.values():
                walk(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                walk(child)
        elif isinstance(value, str) and Path(value).is_absolute():
            add_if_file(value)

    walk(final_manifest)
    candidates = final_manifest.get("candidate_manifests")
    if not isinstance(candidates, Mapping):
        raise ValueError("artifact_inventory_candidate_set_invalid")
    for candidate in candidates.values():
        if not isinstance(candidate, Mapping):
            raise ValueError("artifact_inventory_candidate_invalid")
        closure = candidate.get("material_closure")
        if not isinstance(closure, Mapping):
            raise ValueError("artifact_inventory_mdl_closure_invalid")
        closure_root = _absolute_path_without_symlink_resolution(
            str(closure.get("closure_root", ""))
        )
        copied = closure.get("copied_file_sha256")
        if not isinstance(copied, Mapping) or not copied:
            raise ValueError("artifact_inventory_mdl_files_invalid")
        for relative in copied:
            normalized = _normalized_render_diagnostic_snapshot_path(
                str(relative)
            )
            add_if_file(closure_root / normalized, required=True)
    source_closure = final_manifest.get("source_dependency_closure")
    if not isinstance(source_closure, Mapping):
        raise ValueError("artifact_inventory_source_closure_invalid")
    source_files = source_closure.get("files")
    if not isinstance(source_files, list) or not source_files:
        raise ValueError("artifact_inventory_source_files_invalid")
    source_root = cell / RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_DIRNAME
    for record in source_files:
        if not isinstance(record, Mapping):
            raise ValueError("artifact_inventory_source_file_invalid")
        relative = _normalized_render_diagnostic_snapshot_path(
            str(record.get("path", ""))
        )
        add_if_file(source_root / relative, required=True)
    return expected


def validate_render_diagnostic_cell_artifact_inventory(
    inventory: Mapping[str, Any],
    *,
    cell_root: str | os.PathLike[str],
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "inventory_id",
        "files",
        "artifact_inventory_sha256",
    }
    if not isinstance(inventory, Mapping) or set(inventory) != fields:
        raise ValueError("artifact_inventory_schema_invalid")
    actual = _json_native_copy(dict(inventory))
    payload = {
        key: value
        for key, value in actual.items()
        if key != "artifact_inventory_sha256"
    }
    if (
        actual.get("schema_version") != 1
        or actual.get("inventory_id")
        != "matrix_cell_runtime_artifact_inventory_v1"
        or not isinstance(actual.get("files"), list)
        or actual["files"] != sorted(
            actual["files"], key=lambda item: item.get("path", "")
        )
        or len(
            {
                item.get("path")
                for item in actual["files"]
                if isinstance(item, Mapping)
            }
        )
        != len(actual["files"])
        or any(
            not isinstance(item, Mapping)
            or set(item) != {"path", "byte_count", "sha256"}
            or not isinstance(item.get("path"), str)
            or Path(item["path"]).is_absolute()
            or any(part in {"", ".", ".."} for part in Path(item["path"]).parts)
            or type(item.get("byte_count")) is not int
            or item["byte_count"] < 0
            or not _is_sha256_text(item.get("sha256"))
            for item in actual["files"]
        )
        or actual.get("artifact_inventory_sha256")
        != canonical_json_sha256_v1(payload)
    ):
        raise ValueError("artifact_inventory_invalid")
    rebuilt = build_render_diagnostic_cell_artifact_inventory(cell_root)
    if actual != rebuilt:
        raise ValueError("artifact_inventory_membership_mismatch")
    return actual


def write_render_diagnostic_pre_freeze() -> dict[str, Any]:
    aggregate_root = _reject_symlink_path_components(
        RENDER_DIAGNOSTIC_AGGREGATE_ROOT,
        label="render_diagnostic_pre_freeze_aggregate_root",
    )
    if aggregate_root.exists() or aggregate_root.is_symlink():
        raise ValueError("render_diagnostic_pre_freeze_requires_absent_aggregate")
    validate_historical_003_terminal_attestation()
    validate_historical_004_terminal_state()
    validate_historical_005_terminal_state()
    validate_historical_006_terminal_state()
    validate_historical_007_terminal_state()
    build_render_diagnostic_source_dependency_discovery()
    load_and_verify_frozen_matrix_implementation_identity()
    return write_default_render_diagnostic_protected_snapshot(
        RENDER_DIAGNOSTIC_PRE_FREEZE_PATH
    )


def verify_render_diagnostic_pre_freeze_unchanged() -> dict[str, Any]:
    snapshot = load_and_verify_render_diagnostic_pre_freeze_snapshot()
    path = _reject_symlink_path_components(
        RENDER_DIAGNOSTIC_PRE_FREEZE_PATH,
        label="render_diagnostic_pre_freeze",
    )
    return {
        "verified": True,
        "path": str(path),
        "sha256": canonical_json_sha256_v1(snapshot),
        "registry_id": snapshot["registry_id"],
    }


def run_render_diagnostic_launch_preflight() -> dict[str, Any]:
    historical_003 = validate_historical_003_terminal_attestation()
    historical_004 = validate_historical_004_terminal_state()
    historical_005 = validate_historical_005_terminal_state()
    historical_006 = validate_historical_006_terminal_state()
    historical_007 = validate_historical_007_terminal_state()
    implementation = load_and_verify_frozen_matrix_implementation_identity()
    protected = verify_render_diagnostic_pre_freeze_unchanged()
    return {
        "status": "PASS",
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "implementation_identity_sha256": implementation[
            "implementation_identity_sha256"
        ],
        "pre_freeze_sha256": protected["sha256"],
        "historical_terminal_validation_sha256": historical_003[
            "terminal_validation_sha256"
        ],
        "historical_004_terminal_validation_sha256": historical_004[
            "terminal_validation_sha256"
        ],
        "historical_005_terminal_validation_sha256": historical_005[
            "terminal_validation_sha256"
        ],
        "historical_006_terminal_validation_sha256": historical_006[
            "terminal_validation_sha256"
        ],
        "historical_007_terminal_validation_sha256": historical_007[
            "terminal_validation_sha256"
        ],
    }


def load_and_verify_render_diagnostic_pre_freeze_snapshot() -> dict[str, Any]:
    path = _reject_symlink_path_components(
        RENDER_DIAGNOSTIC_PRE_FREEZE_PATH,
        label="render_diagnostic_pre_freeze",
    )
    if path.is_symlink():
        raise ValueError("render_diagnostic_pre_freeze_symlink")
    snapshot = validate_render_diagnostic_protected_snapshot(
        _load_json_object(path, label="render_diagnostic_pre_freeze")
    )
    return snapshot


_RENDER_DIAGNOSTIC_POST_FREEZE_FIELDS = frozenset(
    {
        "schema_version",
        "experiment_id",
        "anchor_sha256",
        "completed_successful_sequence_length",
        "last_launch_intent_sha256",
        "last_cell_artifact_sha256",
        "registry_snapshot",
        "generated_at_utc",
        "post_freeze_sha256",
    }
)


def _render_diagnostic_post_chain_projection(
    cell_status_index: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(cell_status_index, Mapping) or not isinstance(
        cell_status_index.get("cells"), list
    ):
        raise ValueError("post_freeze_envelope_status_index_invalid")
    completed = 0
    sequence_open = True
    last_launch = None
    last_artifact = None
    for record in cell_status_index["cells"]:
        if not isinstance(record, Mapping):
            raise ValueError("post_freeze_envelope_status_record_invalid")
        status_value = record.get("status")
        launch_hash = record.get("launch_intent_sha256")
        artifact_hash = record.get("cell_evidence_sha256")
        if status_value == "SUCCESS" and sequence_open:
            if not _is_sha256_text(launch_hash) or not _is_sha256_text(
                artifact_hash
            ):
                raise ValueError("post_freeze_envelope_success_hash_invalid")
            completed += 1
        elif status_value == "SUCCESS":
            raise ValueError("post_freeze_envelope_success_after_gap")
        else:
            sequence_open = False
        if launch_hash is not None:
            if not _is_sha256_text(launch_hash):
                raise ValueError("post_freeze_envelope_launch_hash_invalid")
            last_launch = launch_hash
            if artifact_hash is not None and not _is_sha256_text(artifact_hash):
                raise ValueError("post_freeze_envelope_artifact_hash_invalid")
            last_artifact = artifact_hash
    return {
        "completed_successful_sequence_length": completed,
        "last_launch_intent_sha256": last_launch,
        "last_cell_artifact_sha256": last_artifact,
    }


def build_render_diagnostic_post_freeze_envelope(
    *,
    registry_snapshot: Mapping[str, Any],
    anchor: Mapping[str, Any],
    cell_status_index: Mapping[str, Any],
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    snapshot = _json_native_copy(dict(registry_snapshot))
    if (
        set(snapshot)
        != {"schema_version", "registry_id", "protected_roots", "protected_files"}
        or snapshot.get("schema_version") != 1
        or not isinstance(snapshot.get("registry_id"), str)
        or not snapshot["registry_id"]
        or not isinstance(snapshot.get("protected_roots"), list)
        or not isinstance(snapshot.get("protected_files"), list)
    ):
        raise ValueError("post_freeze_envelope_registry_invalid")
    anchor_hash = anchor.get("anchor_sha256") if isinstance(anchor, Mapping) else None
    if not _is_sha256_text(anchor_hash):
        raise ValueError("post_freeze_envelope_anchor_invalid")
    generated = generated_at_utc or _utc_now()
    if not isinstance(generated, str) or not generated:
        raise ValueError("post_freeze_envelope_generated_at_invalid")
    projection = _render_diagnostic_post_chain_projection(cell_status_index)
    payload = {
        "schema_version": 1,
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "anchor_sha256": anchor_hash,
        **projection,
        "registry_snapshot": snapshot,
        "generated_at_utc": generated,
    }
    hash_payload = {
        key: value for key, value in payload.items() if key != "generated_at_utc"
    }
    return {
        **payload,
        "post_freeze_sha256": canonical_json_sha256_v1(hash_payload),
    }


def validate_render_diagnostic_post_freeze_envelope(
    envelope: Mapping[str, Any],
    *,
    expected_registry_snapshot: Mapping[str, Any],
    expected_anchor_sha256: str,
    expected_cell_status_index: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(envelope, Mapping) or set(envelope) != set(
        _RENDER_DIAGNOSTIC_POST_FREEZE_FIELDS
    ):
        raise ValueError("post_freeze_envelope_schema_invalid")
    actual = _json_native_copy(dict(envelope))
    rebuilt = build_render_diagnostic_post_freeze_envelope(
        registry_snapshot=expected_registry_snapshot,
        anchor={"anchor_sha256": expected_anchor_sha256},
        cell_status_index=expected_cell_status_index,
        generated_at_utc=actual.get("generated_at_utc"),
    )
    if actual != rebuilt:
        raise ValueError("post_freeze_envelope_binding_invalid")
    return actual


_RENDER_DIAGNOSTIC_POST_SEAL_FIELDS = frozenset(
    {
        "schema_version",
        "experiment_id",
        "anchor_sha256",
        "completed_sequence_length",
        "final_launch_intent_sha256",
        "final_cell_evidence_sha256",
        "pre_freeze_sha256",
        "post_freeze_sha256",
        "implementation_identity_sha256",
        "generated_at_utc",
        "post_seal_sha256",
    }
)


def build_render_diagnostic_successful_post_seal(
    *,
    anchor: Mapping[str, Any],
    post_freeze_envelope: Mapping[str, Any],
    cell_status_index: Mapping[str, Any],
    validated_launch_chain: Mapping[str, Any],
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    projection = _render_diagnostic_post_chain_projection(cell_status_index)
    cells = cell_status_index.get("cells") if isinstance(
        cell_status_index, Mapping
    ) else None
    if (
        not isinstance(cells, list)
        or len(cells) != 16
        or projection["completed_successful_sequence_length"] != 16
        or any(record.get("status") != "SUCCESS" for record in cells)
        or not isinstance(validated_launch_chain, Mapping)
        or validated_launch_chain.get(
            "completed_successful_sequence_length"
        )
        != 16
        or validated_launch_chain.get("last_launch_intent_sha256")
        != projection["last_launch_intent_sha256"]
        or validated_launch_chain.get("last_cell_artifact_sha256")
        != projection["last_cell_artifact_sha256"]
    ):
        raise ValueError("post_seal_complete_chain_required")
    anchor_hash = anchor.get("anchor_sha256") if isinstance(anchor, Mapping) else None
    pre_hash = anchor.get("pre_freeze_sha256") if isinstance(anchor, Mapping) else None
    implementation_hash = (
        anchor.get("implementation_identity_sha256")
        if isinstance(anchor, Mapping)
        else None
    )
    post_hash = (
        post_freeze_envelope.get("post_freeze_sha256")
        if isinstance(post_freeze_envelope, Mapping)
        else None
    )
    if (
        not _is_sha256_text(anchor_hash)
        or not _is_sha256_text(pre_hash)
        or not _is_sha256_text(implementation_hash)
        or not _is_sha256_text(post_hash)
        or post_freeze_envelope.get("anchor_sha256") != anchor_hash
        or post_freeze_envelope.get("completed_successful_sequence_length")
        != 16
        or post_freeze_envelope.get("last_launch_intent_sha256")
        != projection["last_launch_intent_sha256"]
        or post_freeze_envelope.get("last_cell_artifact_sha256")
        != projection["last_cell_artifact_sha256"]
    ):
        raise ValueError("post_seal_binding_invalid")
    generated = generated_at_utc or _utc_now()
    payload = {
        "schema_version": 1,
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "anchor_sha256": anchor_hash,
        "completed_sequence_length": 16,
        "final_launch_intent_sha256": projection[
            "last_launch_intent_sha256"
        ],
        "final_cell_evidence_sha256": projection[
            "last_cell_artifact_sha256"
        ],
        "pre_freeze_sha256": pre_hash,
        "post_freeze_sha256": post_hash,
        "implementation_identity_sha256": implementation_hash,
        "generated_at_utc": generated,
    }
    hash_payload = {
        key: value for key, value in payload.items() if key != "generated_at_utc"
    }
    return {
        **payload,
        "post_seal_sha256": canonical_json_sha256_v1(hash_payload),
    }


def validate_render_diagnostic_successful_post_seal(
    seal: Mapping[str, Any],
    *,
    anchor: Mapping[str, Any],
    post_freeze_envelope: Mapping[str, Any],
    cell_status_index: Mapping[str, Any],
    validated_launch_chain: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(seal, Mapping) or set(seal) != set(
        _RENDER_DIAGNOSTIC_POST_SEAL_FIELDS
    ):
        raise ValueError("post_seal_schema_invalid")
    actual = _json_native_copy(dict(seal))
    expected = build_render_diagnostic_successful_post_seal(
        anchor=anchor,
        post_freeze_envelope=post_freeze_envelope,
        cell_status_index=cell_status_index,
        validated_launch_chain=validated_launch_chain,
        generated_at_utc=actual.get("generated_at_utc"),
    )
    if actual != expected:
        raise ValueError("post_seal_contract_invalid")
    return actual


def _write_regular_bytes_create_exclusive(path: Path, payload: bytes) -> None:
    path = _reject_symlink_path_components(
        path,
        label="render_diagnostic_closure_destination",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("render_diagnostic_closure_short_write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _normalized_render_diagnostic_snapshot_path(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("render_diagnostic_closure_path_invalid")
    path = Path(value)
    if (
        path.is_absolute()
        or value != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("render_diagnostic_closure_path_invalid")
    return value


def create_render_diagnostic_final_closure_snapshot(
    *,
    aggregate_root: str | os.PathLike[str],
    external_files: Mapping[str, str | os.PathLike[str]],
    closure_root_override: str | os.PathLike[str] | None = None,
    excluded_aggregate_prefixes: Sequence[str] = (),
) -> dict[str, Any]:
    root = _reject_symlink_path_components(
        aggregate_root,
        label="render_diagnostic_closure_aggregate_root",
    )
    if not root.is_dir() or root.is_symlink():
        raise ValueError("render_diagnostic_closure_aggregate_root_invalid")
    target = _reject_symlink_path_components(
        closure_root_override
        if closure_root_override is not None
        else root / RENDER_DIAGNOSTIC_FINAL_CLOSURE_DIRNAME,
        label="render_diagnostic_closure_target",
    )
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"render_diagnostic_closure_exists:{target}")
    if not isinstance(external_files, Mapping):
        raise ValueError("render_diagnostic_closure_external_files_invalid")
    normalized_exclusions = tuple(
        _normalized_render_diagnostic_snapshot_path(value)
        for value in excluded_aggregate_prefixes
    )
    aggregate_parent = target.parent
    aggregate_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{root.name}.final_closure.",
            dir=aggregate_parent,
        )
    )
    active_exclusions = (
        *normalized_exclusions,
        *(
            (staging.name,)
            if staging.parent == root
            else ()
        ),
    )
    records: list[dict[str, Any]] = []
    try:
        _, aggregate_snapshot_before_full = _snapshot_pinned_regular_tree(
            root,
            label="render_diagnostic_closure_aggregate_source",
        )
        aggregate_snapshot_before = [
            record
            for record in aggregate_snapshot_before_full
            if not any(
                record["path"] == prefix
                or record["path"].startswith(prefix + "/")
                for prefix in active_exclusions
            )
        ]
        source_records: list[tuple[str, Path, int, str]] = []
        for source_record in aggregate_snapshot_before:
            relative = source_record["path"]
            if relative == "matrix_decision.json":
                continue
            source_records.append(
                (
                    f"aggregate/{relative}",
                    root / relative,
                    source_record["byte_count"],
                    source_record["sha256"],
                )
            )
        external_evidence: dict[str, dict[str, Any]] = {}
        for logical_path, raw_source in external_files.items():
            normalized = _normalized_render_diagnostic_snapshot_path(
                str(logical_path)
            )
            if not normalized.startswith("external/"):
                raise ValueError(
                    "render_diagnostic_closure_external_logical_path_invalid"
                )
            evidence = _hash_regular_file_pinned(
                raw_source,
                label="render_diagnostic_closure_external_source",
            )
            external_evidence[normalized] = evidence
            source_records.append(
                (
                    normalized,
                    Path(evidence["path"]),
                    evidence["byte_count"],
                    evidence["sha256"],
                )
            )
        logical_paths = [record[0] for record in source_records]
        if len(set(logical_paths)) != len(logical_paths):
            raise ValueError("render_diagnostic_closure_path_duplicate")
        for logical_path, source, expected_size, expected_hash in sorted(
            source_records
        ):
            normalized = _normalized_render_diagnostic_snapshot_path(
                logical_path
            )
            payload = _read_regular_file_snapshot(
                source,
                label="render_diagnostic_closure_source",
            )
            if (
                len(payload) != expected_size
                or hashlib.sha256(payload).hexdigest() != expected_hash
            ):
                raise ValueError(
                    "render_diagnostic_closure_source_changed_before_copy"
                )
            destination = staging / normalized
            _write_regular_bytes_create_exclusive(destination, payload)
            records.append(
                {
                    "logical_path": normalized,
                    "snapshot_path": normalized,
                    "byte_count": len(payload),
                    "sha256": expected_hash,
                }
            )
        _, aggregate_snapshot_after_full = _snapshot_pinned_regular_tree(
            root,
            label="render_diagnostic_closure_aggregate_source",
        )
        aggregate_snapshot_after = [
            record
            for record in aggregate_snapshot_after_full
            if not any(
                record["path"] == prefix
                or record["path"].startswith(prefix + "/")
                for prefix in active_exclusions
            )
        ]
        if aggregate_snapshot_after != aggregate_snapshot_before:
            raise ValueError(
                "render_diagnostic_closure_aggregate_changed_during_copy"
            )
        for logical_path, evidence in external_evidence.items():
            current = _hash_regular_file_pinned(
                evidence["path"],
                label="render_diagnostic_closure_external_source",
            )
            if (
                current["byte_count"] != evidence["byte_count"]
                or current["sha256"] != evidence["sha256"]
            ):
                raise ValueError(
                    f"render_diagnostic_closure_external_changed:{logical_path}"
                )
        snapshot_stat = os.stat(staging, follow_symlinks=False)
        payload = {
            "schema_version": 1,
            "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
            "snapshot_device": snapshot_stat.st_dev,
            "snapshot_inode": snapshot_stat.st_ino,
            "files": records,
        }
        manifest = {
            **payload,
            "closure_snapshot_sha256": canonical_json_sha256_v1(payload),
        }
        _write_json_create_exclusive(
            staging / RENDER_DIAGNOSTIC_CLOSURE_MANIFEST_BASENAME,
            manifest,
        )
        for file_path in sorted(staging.rglob("*")):
            if file_path.is_file():
                file_path.chmod(0o444)
        directories = [
            path for path in staging.rglob("*") if path.is_dir()
        ]
        for directory in sorted(
            directories,
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            directory.chmod(0o555)
        staging.chmod(0o555)
        _atomic_rename_noreplace(staging, target)
        _fsync_directory(target.parent)
        return validate_render_diagnostic_final_closure_snapshot(target)
    finally:
        if staging.exists():
            for directory in [staging, *staging.rglob("*")]:
                if directory.is_dir():
                    try:
                        directory.chmod(0o755)
                    except OSError:
                        pass
            shutil.rmtree(staging)


def validate_render_diagnostic_final_closure_snapshot(
    closure_root: str | os.PathLike[str],
) -> dict[str, Any]:
    root = _reject_symlink_path_components(
        closure_root,
        label="render_diagnostic_final_closure_root",
    )
    _, tree_snapshot_before = _snapshot_pinned_regular_tree(
        root,
        label="render_diagnostic_final_closure",
    )
    manifest_path = root / RENDER_DIAGNOSTIC_CLOSURE_MANIFEST_BASENAME
    manifest = _load_json_object(
        manifest_path,
        label="render_diagnostic_closure_manifest",
    )
    if not isinstance(manifest, Mapping) or set(manifest) != {
        "schema_version",
        "experiment_id",
        "snapshot_device",
        "snapshot_inode",
        "files",
        "closure_snapshot_sha256",
    }:
        raise ValueError("render_diagnostic_closure_manifest_schema_invalid")
    actual = _json_native_copy(dict(manifest))
    records = actual.get("files")
    with _open_pinned_path(
        root,
        leaf_directory=True,
        label="render_diagnostic_closure_identity",
    ) as (_root, root_descriptor, identities):
        root_stat = os.fstat(root_descriptor)
        _verify_pinned_path_components(
            identities,
            label="render_diagnostic_closure_identity",
        )
    hash_payload = {
        key: value
        for key, value in actual.items()
        if key != "closure_snapshot_sha256"
    }
    if (
        actual.get("schema_version") != 1
        or actual.get("experiment_id") != RENDER_DIAGNOSTIC_EXPERIMENT_ID
        or type(actual.get("snapshot_device")) is not int
        or type(actual.get("snapshot_inode")) is not int
        or (root_stat.st_dev, root_stat.st_ino)
        != (actual["snapshot_device"], actual["snapshot_inode"])
        or not isinstance(records, list)
        or actual.get("closure_snapshot_sha256")
        != canonical_json_sha256_v1(hash_payload)
    ):
        raise ValueError("render_diagnostic_closure_manifest_invalid")
    if (root_stat.st_mode & 0o222) != 0:
        raise ValueError("render_diagnostic_closure_directory_mode_invalid")
    expected_paths: set[str] = set()
    for record in records:
        if (
            not isinstance(record, Mapping)
            or set(record)
            != {"logical_path", "snapshot_path", "byte_count", "sha256"}
            or record.get("logical_path") != record.get("snapshot_path")
            or type(record.get("byte_count")) is not int
            or record["byte_count"] < 0
            or not _is_sha256_text(record.get("sha256"))
        ):
            raise ValueError("render_diagnostic_closure_record_invalid")
        relative = _normalized_render_diagnostic_snapshot_path(
            record["snapshot_path"]
        )
        if relative in expected_paths:
            raise ValueError("render_diagnostic_closure_path_duplicate")
        expected_paths.add(relative)
        path = root / relative
        payload = _read_regular_file_snapshot(
            path,
            label="render_diagnostic_closure_member",
        )
        if (
            len(payload) != record["byte_count"]
            or hashlib.sha256(payload).hexdigest() != record["sha256"]
        ):
            raise ValueError("render_diagnostic_closure_member_mismatch")
    _validate_pinned_readonly_tree_modes(
        root,
        label="render_diagnostic_closure",
    )
    actual_paths = {
        record["path"]
        for record in tree_snapshot_before
        if record["path"] != RENDER_DIAGNOSTIC_CLOSURE_MANIFEST_BASENAME
    }
    if actual_paths != expected_paths:
        raise ValueError("render_diagnostic_closure_membership_mismatch")
    _, tree_snapshot_after = _snapshot_pinned_regular_tree(
        root,
        label="render_diagnostic_final_closure",
    )
    if tree_snapshot_after != tree_snapshot_before:
        raise ValueError("render_diagnostic_closure_changed_during_validation")
    return actual


def resolve_render_diagnostic_closure_authoritative_path(
    original_path: str | os.PathLike[str],
    *,
    aggregate_root: str | os.PathLike[str],
    closure_root: str | os.PathLike[str],
) -> Path:
    original = _absolute_path_without_symlink_resolution(original_path)
    aggregate = _absolute_path_without_symlink_resolution(aggregate_root)
    closure = _reject_symlink_path_components(
        closure_root,
        label="render_diagnostic_closure_resolver_root",
    )
    try:
        relative = original.relative_to(aggregate)
    except ValueError:
        external_mapping = {
            _absolute_path_without_symlink_resolution(
                RENDER_DIAGNOSTIC_IMPLEMENTATION_FREEZE_PATH
            ): "external/implementation_identity.json",
            _absolute_path_without_symlink_resolution(
                RENDER_DIAGNOSTIC_PRE_FREEZE_PATH
            ): "external/pre_freeze.json",
            _absolute_path_without_symlink_resolution(
                RENDER_DIAGNOSTIC_POST_FREEZE_PATH
            ): "external/post_freeze.json",
        }
        mapped_relative = external_mapping.get(original)
        if mapped_relative is None:
            raise ValueError(
                f"render_diagnostic_closure_path_outside_authority:{original}"
            )
        mapped = closure / mapped_relative
    else:
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("render_diagnostic_closure_relative_path_invalid")
        mapped = closure / "aggregate" / relative
    return _reject_symlink_path_components(
        mapped,
        label="render_diagnostic_closure_resolved_member",
    )


_RENDER_DIAGNOSTIC_PROTECTED_FAILURE_FIELDS = frozenset(
    {
        "schema_version",
        "registry_id",
        "failed_path",
        "failure_kind",
        "expected_sha256",
        "observed_sha256",
        "generated_at_utc",
        "protected_input_failure_evidence_sha256",
    }
)
_RENDER_DIAGNOSTIC_PROTECTED_FAILURE_KINDS = frozenset(
    {
        "MISSING",
        "UNREADABLE",
        "SYMLINK",
        "ADDED",
        "REMOVED",
        "SIZE_CHANGED",
        "CONTENT_CHANGED",
        "REGISTRY_CHANGED",
        "IMPLEMENTATION_CHANGED",
    }
)


def _render_diagnostic_absent_path_sha256(path: str | os.PathLike[str]) -> str:
    return canonical_json_sha256_v1(
        {
            "path": str(_absolute_path_without_symlink_resolution(path)),
            "state": "ABSENT",
        }
    )


def _render_diagnostic_complete_failure_hashes(
    *,
    failed_path: str | os.PathLike[str],
    failure_kind: str,
    expected_sha256: str | None,
    observed_sha256: str | None,
) -> tuple[str | None, str | None]:
    if failure_kind in {"MISSING", "UNREADABLE", "SYMLINK"}:
        return expected_sha256, observed_sha256
    absent = _render_diagnostic_absent_path_sha256(failed_path)
    return expected_sha256 or absent, observed_sha256 or absent


def build_render_diagnostic_protected_input_failure(
    *,
    failed_path: str | os.PathLike[str],
    failure_kind: str,
    expected_sha256: str | None,
    observed_sha256: str | None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    if (
        failure_kind not in _RENDER_DIAGNOSTIC_PROTECTED_FAILURE_KINDS
        or (
            expected_sha256 is not None
            and not _is_sha256_text(expected_sha256)
        )
        or (
            observed_sha256 is not None
            and not _is_sha256_text(observed_sha256)
        )
        or (
            failure_kind not in {"MISSING", "UNREADABLE", "SYMLINK"}
            and (
                not _is_sha256_text(expected_sha256)
                or not _is_sha256_text(observed_sha256)
            )
        )
    ):
        raise ValueError("protected_input_failure_contract_invalid")
    payload = {
        "schema_version": 1,
        "registry_id": RENDER_DIAGNOSTIC_PROTECTED_REGISTRY_ID,
        "failed_path": str(
            _absolute_path_without_symlink_resolution(failed_path)
        ),
        "failure_kind": failure_kind,
        "expected_sha256": expected_sha256,
        "observed_sha256": observed_sha256,
        "generated_at_utc": generated_at_utc or _utc_now(),
    }
    hash_payload = {
        key: value for key, value in payload.items() if key != "generated_at_utc"
    }
    return {
        **payload,
        "protected_input_failure_evidence_sha256": (
            canonical_json_sha256_v1(hash_payload)
        ),
    }


def validate_render_diagnostic_protected_input_failure(
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(evidence, Mapping) or set(evidence) != set(
        _RENDER_DIAGNOSTIC_PROTECTED_FAILURE_FIELDS
    ):
        raise ValueError("protected_input_failure_schema_invalid")
    actual = _json_native_copy(dict(evidence))
    if (
        actual.get("schema_version") != 1
        or actual.get("registry_id")
        != RENDER_DIAGNOSTIC_PROTECTED_REGISTRY_ID
        or not isinstance(actual.get("failed_path"), str)
        or not actual["failed_path"]
        or actual.get("failure_kind")
        not in _RENDER_DIAGNOSTIC_PROTECTED_FAILURE_KINDS
        or (
            actual.get("expected_sha256") is not None
            and not _is_sha256_text(actual.get("expected_sha256"))
        )
        or (
            actual.get("observed_sha256") is not None
            and not _is_sha256_text(actual.get("observed_sha256"))
        )
        or (
            actual.get("failure_kind")
            not in {"MISSING", "UNREADABLE", "SYMLINK"}
            and (
                not _is_sha256_text(actual.get("expected_sha256"))
                or not _is_sha256_text(actual.get("observed_sha256"))
            )
        )
        or not isinstance(actual.get("generated_at_utc"), str)
        or not actual["generated_at_utc"]
    ):
        raise ValueError("protected_input_failure_contract_invalid")
    hash_payload = {
        key: value
        for key, value in actual.items()
        if key
        not in {
            "generated_at_utc",
            "protected_input_failure_evidence_sha256",
        }
    }
    if actual.get("protected_input_failure_evidence_sha256") != (
        canonical_json_sha256_v1(hash_payload)
    ):
        raise ValueError("protected_input_failure_hash_invalid")
    return actual


def _protected_freeze_failure_kind(path: Path, exc: BaseException) -> str:
    if path.is_symlink():
        return "SYMLINK"
    if not path.exists():
        return "MISSING"
    if "unreadable" in str(exc).lower():
        return "UNREADABLE"
    return "REGISTRY_CHANGED"


def _first_render_diagnostic_protected_snapshot_difference(
    expected: Mapping[str, Any],
    observed: Mapping[str, Any],
) -> tuple[str, str, str | None, str | None] | None:
    expected_records: list[tuple[str, Mapping[str, Any]]] = []
    observed_records: list[tuple[str, Mapping[str, Any]]] = []
    for snapshot, target in (
        (expected, expected_records),
        (observed, observed_records),
    ):
        for root_record in snapshot["protected_roots"]:
            root_path = Path(root_record["root_path"])
            for record in root_record["files"]:
                target.append((str(root_path / record["path"]), record))
        for record in snapshot["protected_files"]:
            target.append((record["path"], record))
    expected_by_path = dict(expected_records)
    observed_by_path = dict(observed_records)
    for path in sorted(set(expected_by_path) | set(observed_by_path)):
        expected_record = expected_by_path.get(path)
        observed_record = observed_by_path.get(path)
        if expected_record is None:
            return (
                "ADDED",
                path,
                _render_diagnostic_absent_path_sha256(path),
                observed_record["sha256"],
            )
        if observed_record is None:
            return (
                "REMOVED",
                path,
                expected_record["sha256"],
                _render_diagnostic_absent_path_sha256(path),
            )
        if expected_record["byte_count"] != observed_record["byte_count"]:
            return (
                "SIZE_CHANGED",
                path,
                expected_record["sha256"],
                observed_record["sha256"],
            )
        if expected_record["sha256"] != observed_record["sha256"]:
            return (
                "CONTENT_CHANGED",
                path,
                expected_record["sha256"],
                observed_record["sha256"],
            )
    return None


def inspect_render_diagnostic_protected_freezes(
    *,
    pre_path: str | os.PathLike[str],
    post_path: str | os.PathLike[str],
    anchor: Mapping[str, Any],
    cell_status_index: Mapping[str, Any],
) -> dict[str, Any]:
    pre = _absolute_path_without_symlink_resolution(pre_path)
    post = _absolute_path_without_symlink_resolution(post_path)
    accepted_pre_hash = anchor.get("pre_freeze_sha256")
    if not _is_sha256_text(accepted_pre_hash):
        raise ValueError("render_diagnostic_freeze_anchor_pre_hash_invalid")
    observed_pre_hash = _best_effort_regular_file_sha256(pre)
    post_hash = _best_effort_regular_file_sha256(post)
    try:
        pre_snapshot = _load_json_object(pre, label="matrix_pre_freeze")
        pre_snapshot, _roots, _files, _registry = (
            _validate_render_diagnostic_protected_snapshot_structure(
                pre_snapshot
            )
        )
        observed_pre_hash = canonical_json_sha256_v1(pre_snapshot)
    except (OSError, TypeError, ValueError) as exc:
        failure_kind = _protected_freeze_failure_kind(pre, exc)
        expected_hash, observed_hash = _render_diagnostic_complete_failure_hashes(
            failed_path=pre,
            failure_kind=failure_kind,
            expected_sha256=accepted_pre_hash,
            observed_sha256=observed_pre_hash,
        )
        failure = build_render_diagnostic_protected_input_failure(
            failed_path=pre,
            failure_kind=failure_kind,
            expected_sha256=expected_hash,
            observed_sha256=observed_hash,
        )
        return {
            "protected_inputs_match": False,
            "pre_freeze_sha256": accepted_pre_hash,
            "post_freeze_sha256": post_hash,
            "failure": failure,
        }
    try:
        post_envelope = _load_json_object(post, label="matrix_post_freeze")
        post_snapshot = post_envelope.get("registry_snapshot")
        post_envelope = validate_render_diagnostic_post_freeze_envelope(
            post_envelope,
            expected_registry_snapshot=post_snapshot,
            expected_anchor_sha256=anchor["anchor_sha256"],
            expected_cell_status_index=cell_status_index,
        )
        post_hash = post_envelope["post_freeze_sha256"]
    except (OSError, TypeError, ValueError) as exc:
        failure_kind = _protected_freeze_failure_kind(post, exc)
        expected_hash, observed_hash = _render_diagnostic_complete_failure_hashes(
            failed_path=post,
            failure_kind=failure_kind,
            expected_sha256=accepted_pre_hash,
            observed_sha256=post_hash,
        )
        failure = build_render_diagnostic_protected_input_failure(
            failed_path=post,
            failure_kind=failure_kind,
            expected_sha256=expected_hash,
            observed_sha256=observed_hash,
        )
        return {
            "protected_inputs_match": False,
            "pre_freeze_sha256": accepted_pre_hash,
            "post_freeze_sha256": post_hash,
            "failure": failure,
        }
    if observed_pre_hash != accepted_pre_hash or pre_snapshot != post_snapshot:
        difference = _first_render_diagnostic_protected_snapshot_difference(
            pre_snapshot,
            post_snapshot,
        )
        kind, failed_path, expected_hash, observed_hash = difference or (
            "REGISTRY_CHANGED",
            str(post),
            accepted_pre_hash,
            post_hash,
        )
        expected_hash, observed_hash = _render_diagnostic_complete_failure_hashes(
            failed_path=failed_path,
            failure_kind=kind,
            expected_sha256=expected_hash,
            observed_sha256=observed_hash,
        )
        failure = build_render_diagnostic_protected_input_failure(
            failed_path=failed_path,
            failure_kind=kind,
            expected_sha256=expected_hash,
            observed_sha256=observed_hash,
        )
        return {
            "protected_inputs_match": False,
            "pre_freeze_sha256": accepted_pre_hash,
            "post_freeze_sha256": post_hash,
            "failure": failure,
        }
    try:
        current_snapshot = snapshot_default_render_diagnostic_protected_registry()
    except (OSError, TypeError, ValueError) as exc:
        failure_kind = _protected_freeze_failure_kind(post, exc)
        expected_hash, observed_hash = _render_diagnostic_complete_failure_hashes(
            failed_path=post,
            failure_kind=failure_kind,
            expected_sha256=accepted_pre_hash,
            observed_sha256=post_hash,
        )
        failure = build_render_diagnostic_protected_input_failure(
            failed_path=post,
            failure_kind=failure_kind,
            expected_sha256=expected_hash,
            observed_sha256=observed_hash,
        )
        return {
            "protected_inputs_match": False,
            "pre_freeze_sha256": accepted_pre_hash,
            "post_freeze_sha256": post_hash,
            "failure": failure,
        }
    if current_snapshot != pre_snapshot:
        difference = _first_render_diagnostic_protected_snapshot_difference(
            pre_snapshot,
            current_snapshot,
        )
        kind, failed_path, expected_hash, observed_hash = difference or (
            "REGISTRY_CHANGED",
            str(post),
            accepted_pre_hash,
            post_hash,
        )
        expected_hash, observed_hash = _render_diagnostic_complete_failure_hashes(
            failed_path=failed_path,
            failure_kind=kind,
            expected_sha256=expected_hash,
            observed_sha256=observed_hash,
        )
        failure = build_render_diagnostic_protected_input_failure(
            failed_path=failed_path,
            failure_kind=kind,
            expected_sha256=expected_hash,
            observed_sha256=observed_hash,
        )
        return {
            "protected_inputs_match": False,
            "pre_freeze_sha256": accepted_pre_hash,
            "post_freeze_sha256": post_hash,
            "failure": failure,
        }
    return {
        "protected_inputs_match": True,
        "pre_freeze_sha256": accepted_pre_hash,
        "post_freeze_sha256": post_hash,
        "failure": None,
        "post_freeze_envelope": post_envelope,
    }


def _prepare_render_diagnostic_launch_sequence(
    *,
    slot: Mapping[str, Any],
    pre_freeze_sha256: str,
    implementation_identity_sha256: str,
    expected_implementation_identity: Mapping[str, Any] | None,
    lock_descriptor: int,
) -> dict[str, Any]:
    slots = render_diagnostic_slots()
    slot_keys = [record["cell_name"] for record in slots]
    cell_name = str(slot["cell_name"])
    try:
        sequence_index = slot_keys.index(cell_name)
    except ValueError as exc:
        raise ValueError("render_diagnostic_launch_sequence_slot_invalid") from exc
    root = _reject_symlink_path_components(
        RENDER_DIAGNOSTIC_AGGREGATE_ROOT,
        label="render_diagnostic_aggregate_root",
    )
    if root.is_symlink():
        raise ValueError("render_diagnostic_aggregate_root_symlink")
    intent_path = root / "launch_intents" / f"{cell_name}.json"
    if not root.exists():
        if sequence_index != 0:
            raise ValueError("render_diagnostic_launch_sequence_out_of_order")
        root.parent.mkdir(parents=True, exist_ok=True)
        return {
            "root_created": True,
            "sequence_index": sequence_index,
            "anchor": None,
            "predecessor_launch_intent_sha256": None,
            "predecessor_cell_evidence_sha256": None,
        }
    elif not root.is_dir():
        raise ValueError("render_diagnostic_aggregate_root_invalid")
    elif sequence_index == 0 and not intent_path.exists():
        raise ValueError("render_diagnostic_launch_sequence_root_preexisting")
    anchor = validate_render_diagnostic_experiment_anchor(
        _load_json_object(
            root / RENDER_DIAGNOSTIC_ANCHOR_BASENAME,
            label="render_diagnostic_experiment_anchor",
        ),
        expected_root=root,
        expected_lock_path=_render_diagnostic_lock_path(),
    )
    lock_stat = os.fstat(lock_descriptor)
    if (
        (lock_stat.st_dev, lock_stat.st_ino)
        != (anchor["lock_device"], anchor["lock_inode"])
        or anchor["pre_freeze_sha256"] != pre_freeze_sha256
        or anchor["implementation_identity_sha256"]
        != implementation_identity_sha256
    ):
        raise ValueError("render_diagnostic_launch_sequence_anchor_mismatch")
    intents_root = root / "launch_intents"
    if intents_root.is_symlink() or (
        intents_root.exists() and not intents_root.is_dir()
    ):
        raise ValueError("render_diagnostic_launch_sequence_intents_invalid")
    intents_root.mkdir(exist_ok=True)
    existing_intents = {
        path.name for path in intents_root.iterdir() if path.name.endswith(".json")
    }
    expected_prior = {
        f"{name}.json" for name in slot_keys[:sequence_index]
    }
    allowed = set(expected_prior)
    if intent_path.exists() and not intent_path.is_symlink():
        allowed.add(intent_path.name)
    if existing_intents != allowed or any(
        path.is_symlink() or not path.is_file()
        for path in intents_root.iterdir()
    ):
        raise ValueError("render_diagnostic_launch_sequence_intent_set_invalid")
    predecessor_launch_hash = None
    predecessor_cell_hash = None
    for prior_index, prior in enumerate(slots[:sequence_index]):
        prior_root = root / "cells" / str(prior["cell_name"])
        try:
            prior_intent = _load_launch_intent(
                intents_root / f"{prior['cell_name']}.json",
                prior,
            )
            if (
                prior_intent["pre_freeze_sha256"] != pre_freeze_sha256
                or prior_intent["implementation_identity_sha256"]
                != implementation_identity_sha256
                or prior_intent["anchor_sha256"]
                != anchor["anchor_sha256"]
                or prior_intent["sequence_index"] != prior_index
                or prior_intent["predecessor_launch_intent_sha256"]
                != predecessor_launch_hash
                or prior_intent["predecessor_cell_evidence_sha256"]
                != predecessor_cell_hash
            ):
                raise ValueError("prior_pre_freeze_mismatch")
            prior_evidence = validate_render_diagnostic_matrix_cell_evidence(
                _load_json_object(
                    prior_root / "matrix_cell_evidence.json",
                    label="prior_matrix_cell_evidence",
                ),
                expected_cell_root=prior_root,
                expected_slot=prior,
            )
            if (prior_root / "matrix_cell_failure_evidence.json").exists():
                raise ValueError("prior_failure_evidence_present")
            if expected_implementation_identity is not None:
                closure = validate_render_diagnostic_cell_artifact_closure(
                    cell_root=prior_root,
                    expected_slot=prior,
                    expected_implementation_identity=(
                        expected_implementation_identity
                    ),
                    expected_launch_intent=prior_intent,
                )
                if closure["cell_evidence"] != prior_evidence:
                    raise ValueError("prior_cell_evidence_closure_mismatch")
            predecessor_launch_hash = prior_intent["launch_intent_sha256"]
            predecessor_cell_hash = prior_evidence[
                "matrix_cell_evidence_sha256"
            ]
        except (OSError, TypeError, ValueError):
            raise ValueError("render_diagnostic_launch_sequence_prior_not_successful")
    return {
        "root_created": False,
        "sequence_index": sequence_index,
        "anchor": anchor,
        "predecessor_launch_intent_sha256": predecessor_launch_hash,
        "predecessor_cell_evidence_sha256": predecessor_cell_hash,
    }


def write_render_diagnostic_launch_intent(
    identity: Mapping[str, Any],
    *,
    implementation_identity_sha256: str,
    expected_implementation_identity: Mapping[str, Any] | None = None,
    pre_freeze_sha256: str,
    launcher_pid: int | None = None,
    generated_at_utc: str | None = None,
    lock_descriptor: int | None = None,
) -> dict[str, Any]:
    required = {
        "experiment_id",
        "render_diagnostic_variant_id",
        "replicate",
        "execution_order_index",
        "cell_root",
    }
    if not isinstance(identity, Mapping) or set(identity) != required:
        raise ValueError("render_diagnostic_launch_identity_invalid")
    variant = identity["render_diagnostic_variant_id"]
    replicate = identity["replicate"]
    order_index = identity["execution_order_index"]
    expected_name = f"{replicate}_{order_index}_{variant}"
    if (
        identity["experiment_id"] != RENDER_DIAGNOSTIC_EXPERIMENT_ID
        or replicate not in RENDER_DIAGNOSTIC_REPLICATES
        or type(order_index) is not int
        or order_index not in range(4)
        or RENDER_DIAGNOSTIC_BALANCED_ORDER[replicate][order_index] != variant
        or _absolute_path_without_symlink_resolution(identity["cell_root"])
        != _absolute_path_without_symlink_resolution(
            RENDER_DIAGNOSTIC_AGGREGATE_ROOT / "cells" / expected_name
        )
        or not _is_sha256_text(implementation_identity_sha256)
        or not _is_sha256_text(pre_freeze_sha256)
        or (
            expected_implementation_identity is not None
            and (
                not isinstance(expected_implementation_identity, Mapping)
                or expected_implementation_identity.get(
                    "implementation_identity_sha256"
                )
                != implementation_identity_sha256
            )
        )
    ):
        raise ValueError("render_diagnostic_launch_identity_invalid")
    pid = os.getpid() if launcher_pid is None else launcher_pid
    if type(pid) is not int or pid <= 0:
        raise ValueError("render_diagnostic_launcher_pid_invalid")
    slot = {
        "variant": variant,
        "replicate": replicate,
        "execution_order_index": order_index,
        "cell_name": expected_name,
    }

    def write_with_lock(descriptor: int) -> dict[str, Any]:
        sequence = _prepare_render_diagnostic_launch_sequence(
            slot=slot,
            pre_freeze_sha256=pre_freeze_sha256,
            implementation_identity_sha256=implementation_identity_sha256,
            expected_implementation_identity=expected_implementation_identity,
            lock_descriptor=descriptor,
        )
        intent_path = (
            RENDER_DIAGNOSTIC_AGGREGATE_ROOT
            / "launch_intents"
            / f"{expected_name}.json"
        )
        anchor = sequence["anchor"]
        staging_root = None
        if sequence["root_created"]:
            aggregate_root = _absolute_path_without_symlink_resolution(
                RENDER_DIAGNOSTIC_AGGREGATE_ROOT
            )
            staging_root = Path(
                tempfile.mkdtemp(
                    prefix=f".{aggregate_root.name}.launching.",
                    dir=aggregate_root.parent,
                )
            )
            anchor = build_render_diagnostic_experiment_anchor(
                aggregate_root=staging_root,
                lock_descriptor=descriptor,
                implementation_identity_sha256=(
                    implementation_identity_sha256
                ),
                pre_freeze_sha256=pre_freeze_sha256,
            )
        if anchor is None:
            raise AssertionError("render_diagnostic_anchor_missing")
        payload = {
            "schema_version": 1,
            "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
            "variant": variant,
            "replicate": replicate,
            "execution_order_index": order_index,
            "cell_root": str(
                _absolute_path_without_symlink_resolution(
                    identity["cell_root"]
                )
            ),
            "launcher_pid": pid,
            "generated_at_utc": generated_at_utc or _utc_now(),
            "sequence_index": sequence["sequence_index"],
            "anchor_sha256": anchor["anchor_sha256"],
            "predecessor_launch_intent_sha256": sequence[
                "predecessor_launch_intent_sha256"
            ],
            "predecessor_cell_evidence_sha256": sequence[
                "predecessor_cell_evidence_sha256"
            ],
            "implementation_identity_sha256": (
                implementation_identity_sha256
            ),
            "pre_freeze_sha256": pre_freeze_sha256,
        }
        hash_payload = {
            key: value
            for key, value in payload.items()
            if key != "generated_at_utc"
        }
        intent = {
            **payload,
            "launch_intent_sha256": canonical_json_sha256_v1(hash_payload),
        }
        if staging_root is None:
            _write_json_create_exclusive(intent_path, intent)
            return intent
        aggregate_root = _absolute_path_without_symlink_resolution(
            RENDER_DIAGNOSTIC_AGGREGATE_ROOT
        )
        try:
            _write_json_create_exclusive(
                staging_root / RENDER_DIAGNOSTIC_ANCHOR_BASENAME,
                anchor,
            )
            _write_json_create_exclusive(
                staging_root / "launch_intents" / intent_path.name,
                intent,
            )
            _fsync_directory(staging_root / "launch_intents")
            _fsync_directory(staging_root)
            write_render_diagnostic_experiment_binding(
                descriptor,
                anchor=anchor,
            )
            _atomic_rename_noreplace(staging_root, aggregate_root)
            validate_render_diagnostic_experiment_anchor(
                anchor,
                expected_root=aggregate_root,
                expected_lock_path=_render_diagnostic_lock_path(),
            )
        finally:
            if staging_root.exists():
                shutil.rmtree(staging_root)
        return intent

    if lock_descriptor is not None:
        return write_with_lock(lock_descriptor)
    with acquire_render_diagnostic_experiment_lock() as descriptor:
        return write_with_lock(descriptor)


def build_render_diagnostic_cell_sidecar_payloads(
    *,
    final_manifest: Mapping[str, Any],
    identity: Mapping[str, Any],
    implementation_identity: Mapping[str, Any],
    launch_intent: Mapping[str, Any],
    launcher_pid: int,
    child_pid: int,
    device_identity: Mapping[str, Any],
    authoritative_path_resolver: Any | None = None,
) -> dict[str, dict[str, Any]]:
    from PIL import Image

    if not isinstance(final_manifest, Mapping):
        raise ValueError("matrix_sidecar_final_manifest_invalid")
    if final_manifest.get("classification") != (
        "DIAGNOSTIC_RENDER_COMPLETE_PENDING_VISUAL_REVIEW"
    ):
        raise ValueError("matrix_sidecar_final_classification_invalid")
    required_identity = {
        "experiment_id",
        "render_diagnostic_variant_id",
        "replicate",
        "execution_order_index",
        "cell_root",
    }
    if not isinstance(identity, Mapping) or set(identity) != required_identity:
        raise ValueError("matrix_sidecar_identity_invalid")
    variant = identity["render_diagnostic_variant_id"]
    replicate = identity["replicate"]
    order_index = identity["execution_order_index"]
    if (
        identity["experiment_id"] != RENDER_DIAGNOSTIC_EXPERIMENT_ID
        or replicate not in RENDER_DIAGNOSTIC_REPLICATES
        or type(order_index) is not int
        or order_index not in range(4)
        or RENDER_DIAGNOSTIC_BALANCED_ORDER[replicate][order_index] != variant
    ):
        raise ValueError("matrix_sidecar_identity_invalid")
    cell_root = _absolute_path_without_symlink_resolution(identity["cell_root"])

    def authoritative_path(path: Path) -> Path:
        return _reject_symlink_path_components(
            authoritative_path_resolver(path)
            if authoritative_path_resolver is not None
            else path,
            label="matrix_sidecar_authoritative_path",
        )
    implementation_hash = implementation_identity.get(
        "implementation_identity_sha256"
    )
    if (
        not _is_sha256_text(implementation_hash)
        or launch_intent.get("implementation_identity_sha256")
        != implementation_hash
        or not _is_sha256_text(launch_intent.get("launch_intent_sha256"))
        or launch_intent.get("variant") != variant
        or launch_intent.get("replicate") != replicate
        or launch_intent.get("execution_order_index") != order_index
        or _absolute_path_without_symlink_resolution(
            str(launch_intent.get("cell_root", ""))
        )
        != cell_root
    ):
        raise ValueError("matrix_sidecar_launch_binding_invalid")
    runtime_evidence = validate_render_diagnostic_runtime_manifest_evidence(
        final_manifest,
        cell_root=cell_root,
        implementation_identity=implementation_identity,
        authoritative_path_resolver=authoritative_path_resolver,
    )
    expected_artifact_paths = build_render_diagnostic_expected_artifact_paths(
        final_manifest,
        cell_root=cell_root,
        authoritative_path_resolver=authoritative_path_resolver,
    )
    artifact_inventory = build_render_diagnostic_cell_artifact_inventory(
        authoritative_path(cell_root),
        expected_relative_paths=expected_artifact_paths,
    )
    candidates = final_manifest.get("candidate_manifests")
    if not isinstance(candidates, Mapping) or set(candidates) != {
        "OMNI_REF_DISPLAY_FILL"
    }:
        raise ValueError("matrix_sidecar_candidate_set_invalid")
    candidate = candidates["OMNI_REF_DISPLAY_FILL"]
    if not isinstance(candidate, Mapping):
        raise ValueError("matrix_sidecar_candidate_invalid")
    look = validate_effective_replay_look_contract(
        final_manifest.get("effective_replay_look_contract")  # type: ignore[arg-type]
    )
    projection = build_effective_replay_look_matrix_projection(look)
    if (
        look["render_diagnostic_variant_id"] != variant
        or final_manifest.get("render_diagnostic_variant_id") != variant
        or final_manifest.get("effective_replay_look_contract_sha256")
        != look["effective_replay_look_contract_sha256"]
        or final_manifest.get("effective_replay_look_matrix_projection_sha256")
        != projection["canonical_json_utf8_sha256"]
        or candidate.get("effective_replay_look_contract") != look
    ):
        raise ValueError("matrix_sidecar_effective_look_invalid")
    capture_bindings = candidate.get("capture_frame_bindings")
    if not isinstance(capture_bindings, Mapping):
        raise ValueError("matrix_sidecar_frame_bindings_missing")
    bindings = capture_bindings.get("bindings")
    if (
        not isinstance(bindings, list)
        or len(bindings) != 21
        or capture_bindings.get("bindings_sha256")
        != canonical_json_sha256_v1(bindings)
    ):
        raise ValueError("matrix_sidecar_frame_bindings_invalid")
    expected_frames = list(range(0, 601, 30))
    matrix_frames = []
    for expected_frame, binding in zip(expected_frames, bindings):
        if (
            not isinstance(binding, Mapping)
            or binding.get("physical_trace_frame_index") != expected_frame
            or not _is_sha256_text(binding.get("source_positions_sha256"))
            or not _is_sha256_text(binding.get("proxy_geometry_sha256"))
            or not isinstance(binding.get("image_paths"), Mapping)
            or not isinstance(binding.get("image_sha256"), Mapping)
            or set(binding["image_paths"]) != set(CAPTURE_CAMERA_ROLES)
            or set(binding["image_sha256"]) != set(CAPTURE_CAMERA_ROLES)
        ):
            raise ValueError("matrix_sidecar_frame_binding_invalid")
        camera_hashes = {}
        for role in CAPTURE_CAMERA_ROLES:
            image_path = _absolute_path_without_symlink_resolution(
                binding["image_paths"][role]
            )
            authoritative_image = authoritative_path(image_path)
            if (
                not authoritative_image.is_file()
                or authoritative_image.is_symlink()
                or cell_root not in image_path.parents
            ):
                raise ValueError("matrix_sidecar_image_path_invalid")
            actual_hash = _sha256_file(authoritative_image)
            if actual_hash != binding["image_sha256"][role]:
                raise ValueError("matrix_sidecar_image_hash_invalid")
            camera_hashes[role] = actual_hash
        matrix_frames.append(
            {
                "frame": expected_frame,
                "accepted_points_sha256": binding["source_positions_sha256"],
                "display_fill_geometry_sha256": binding[
                    "proxy_geometry_sha256"
                ],
                "camera_image_sha256s": camera_hashes,
            }
        )
    frame_payload = {"schema_version": 1, "frames": matrix_frames}
    frame_sidecar = {
        **frame_payload,
        "frame_bindings_sha256": canonical_json_sha256_v1(frame_payload),
    }

    path_lists = {
        "context": candidate.get("context_image_paths"),
        "source_beaker_closeup": candidate.get("closeup_image_paths"),
        "native_table_context": candidate.get("native_context_image_paths"),
    }
    images = []
    for role in CAPTURE_CAMERA_ROLES:
        paths = path_lists[role]
        if not isinstance(paths, list) or len(paths) != 21:
            raise ValueError("matrix_sidecar_image_list_invalid")
        for frame, raw_path, binding in zip(expected_frames, paths, bindings):
            path = _absolute_path_without_symlink_resolution(raw_path)
            if path != _absolute_path_without_symlink_resolution(
                binding["image_paths"][role]
            ):
                raise ValueError("matrix_sidecar_image_binding_path_mismatch")
            authoritative_image = authoritative_path(path)
            with _open_image_file_snapshot(
                authoritative_image,
                label="matrix_sidecar_image",
            ) as image:
                width, height = image.size
                image.verify()
            if (width, height) != (960, 540):
                raise ValueError("matrix_sidecar_image_dimensions_invalid")
            images.append(
                {
                    "camera": role,
                    "frame": frame,
                    "path": str(path),
                    "sha256": _sha256_file(authoritative_image),
                    "width": width,
                    "height": height,
                }
            )
    video_paths = candidate.get("video_paths")
    video_validation = candidate.get("video_validation")
    if (
        not isinstance(video_paths, Mapping)
        or not isinstance(video_validation, Mapping)
        or set(video_paths) != set(CAPTURE_CAMERA_ROLES)
        or set(video_validation) != set(CAPTURE_CAMERA_ROLES)
    ):
        raise ValueError("matrix_sidecar_video_set_invalid")
    videos = []
    for role in CAPTURE_CAMERA_ROLES:
        path = _absolute_path_without_symlink_resolution(video_paths[role])
        authoritative_video = authoritative_path(path)
        validation = video_validation[role]
        if (
            not authoritative_video.is_file()
            or authoritative_video.is_symlink()
            or cell_root not in path.parents
            or not isinstance(validation, Mapping)
            or validation.get("decodable") is not True
            or validation.get("frame_count") != 21
            or validation.get("width") != 960
            or validation.get("height") != 540
            or float(validation.get("fps", -1.0)) != 15.0
        ):
            raise ValueError("matrix_sidecar_video_invalid")
        videos.append(
            {
                "camera": role,
                "path": str(path),
                "sha256": _sha256_file(authoritative_video),
                "frame_count": 21,
                "width": 960,
                "height": 540,
                "fps": 15.0,
            }
        )
    media_payload = {
        "schema_version": 1,
        "images": images,
        "videos": videos,
    }
    media_sidecar = {
        **media_payload,
        "media_index_sha256": canonical_json_sha256_v1(media_payload),
    }

    provenance = final_manifest.get("execution_provenance")
    runtime_contract = final_manifest.get("runtime_contract")
    if not isinstance(provenance, Mapping) or not isinstance(
        runtime_contract, Mapping
    ):
        raise ValueError("matrix_sidecar_runtime_provenance_invalid")
    python_info = provenance.get("python")
    runtime_info = provenance.get("runtime")
    render_parameters = provenance.get("render_parameters")
    if not all(
        isinstance(value, Mapping)
        for value in (python_info, runtime_info, render_parameters)
    ):
        raise ValueError("matrix_sidecar_runtime_provenance_invalid")
    runtime_payload = {
        "schema_version": 1,
        "isaac_version": str(runtime_info.get("isaacsim_version")),
        "kit_version": str(runtime_contract.get("kit_version")),
        "python_executable": str(python_info.get("executable")),
        "render_delegate": str(runtime_contract.get("render_delegate")),
        "headless": bool(render_parameters.get("headless")),
    }
    if any(
        not isinstance(runtime_payload[field], str) or not runtime_payload[field]
        for field in (
            "isaac_version",
            "kit_version",
            "python_executable",
            "render_delegate",
        )
    ):
        raise ValueError("matrix_sidecar_runtime_identity_invalid")
    runtime_identity = {
        **runtime_payload,
        "runtime_identity_sha256": canonical_json_sha256_v1(runtime_payload),
    }
    device = _json_native_copy(dict(device_identity))
    device_payload = {
        key: value for key, value in device.items() if key != "device_identity_sha256"
    }
    if (
        set(device_payload)
        != {"schema_version", "gpu_uuid", "gpu_name", "driver_version"}
        or device.get("device_identity_sha256")
        != canonical_json_sha256_v1(device_payload)
        or any(
            not isinstance(device_payload[field], str) or not device_payload[field]
            for field in ("gpu_uuid", "gpu_name", "driver_version")
        )
    ):
        raise ValueError("matrix_sidecar_device_identity_invalid")
    if type(launcher_pid) is not int or launcher_pid <= 0 or type(child_pid) is not int or child_pid <= 0:
        raise ValueError("matrix_sidecar_process_pid_invalid")
    process_payload = {
        "schema_version": 1,
        "launcher_pid": launcher_pid,
        "child_pid": child_pid,
        "parent_child_fresh_process": True,
        "cold_start": True,
        "launch_intent_sha256": launch_intent["launch_intent_sha256"],
        "runtime_implementation_archive_sha256": runtime_evidence[
            "runtime_implementation_archive_sha256"
        ],
        "inherited_fd_contract_sha256": runtime_evidence[
            "inherited_fd_contract_sha256"
        ],
    }
    process_identity = {
        **process_payload,
        "process_identity_sha256": canonical_json_sha256_v1(process_payload),
    }
    static_capture = candidate.get("static_replicator_capture")
    if not isinstance(static_capture, Mapping):
        raise ValueError("matrix_sidecar_static_capture_invalid")
    authority = final_manifest.get("accepted_authority_input")
    physical_trace = final_manifest.get("physical_trace_identity")
    material = candidate.get("material")
    material_closure = candidate.get("material_closure")
    mdl_search_path_contract = candidate.get("mdl_search_path_contract")
    render_settings = candidate.get("render_settings")
    if not all(
        isinstance(value, Mapping)
        for value in (
            authority,
            physical_trace,
            material,
            material_closure,
            mdl_search_path_contract,
            render_settings,
        )
    ):
        raise ValueError("matrix_sidecar_candidate_contract_invalid")
    material_id = material.get("material_hash")
    if not isinstance(material_id, str) or not material_id:
        raise ValueError("matrix_sidecar_material_id_invalid")
    if material_id != look["liquid_material"]["material_hash"]:
        raise ValueError("matrix_sidecar_material_id_mismatch")
    material_id_sha256 = canonical_json_sha256_v1(material_id)
    normal_contract = candidate.get("beaker_normal_remediation_contract")
    if not isinstance(normal_contract, Mapping):
        raise ValueError("matrix_sidecar_normal_contract_invalid")
    normal_projection = build_beaker_normal_matrix_equivalence_projection(
        normal_contract
    )
    if candidate.get("beaker_normal_remediation_contract_sha256") != (
        normal_contract.get("beaker_normal_remediation_contract_sha256")
    ):
        raise ValueError("matrix_sidecar_normal_contract_hash_mismatch")
    if (
        final_manifest.get("source_usd_sha256")
        != RENDER_DIAGNOSTIC_EXPECTED_SOURCE_SHA256
        or authority.get("accepted_authority_bundle_sha256")
        != RENDER_DIAGNOSTIC_EXPECTED_AUTHORITY_SHA256
        or physical_trace.get("physical_trace_sha256")
        != RENDER_DIAGNOSTIC_EXPECTED_TRACE_SHA256
        or normal_projection["canonical_json_utf8_sha256"]
        != RENDER_DIAGNOSTIC_EXPECTED_NORMAL_MATRIX_PROJECTION_SHA256
    ):
        raise ValueError("matrix_sidecar_established_input_mismatch")
    render_settings_evidence = (
        build_render_diagnostic_render_settings_evidence(
            render_settings=render_settings,
            effective_look_contract=look,
            static_capture=static_capture,
        )
    )
    mdl_closure_root = _absolute_path_without_symlink_resolution(
        str(material_closure.get("closure_root", ""))
    )
    if mdl_closure_root != cell_root / VERSION_MATCHED_MDL_CLOSURE_DIRNAME:
        raise ValueError("matrix_sidecar_mdl_closure_root_mismatch")
    mdl_closure_evidence = build_render_diagnostic_mdl_closure_evidence(
        authoritative_path(mdl_closure_root)
    )
    closure_hash_map = {
        record["path"]: record["sha256"]
        for record in mdl_closure_evidence["files"]
    }
    if (
        material_closure.get("copied_file_sha256") != closure_hash_map
        or material_closure.get("copied_tree_sha256")
        != canonical_json_sha256_v1(closure_hash_map)
    ):
        raise ValueError("matrix_sidecar_mdl_closure_declared_mismatch")

    class _RecordedMdlSettings:
        def get(self, path: str) -> Any:
            return {
                "/app/mdl/additionalUserPaths": mdl_search_path_contract.get(
                    "additional_user_paths_readback"
                ),
                "/materialConfig/searchPaths/custom": (
                    mdl_search_path_contract.get(
                        "material_custom_paths_readback"
                    )
                ),
                "/renderer/mdl/searchPaths/custom": ";".join(
                    mdl_search_path_contract.get(
                        "renderer_custom_paths_readback"
                    )
                    or []
                ),
            }.get(path)

    expected_mdl_startup = build_render_diagnostic_mdl_startup_arguments(
        material_closure,
        authoritative_path_resolver=authoritative_path_resolver,
    )
    canonical_mdl_search = validate_render_diagnostic_mdl_search_path_readback(
        _RecordedMdlSettings(),
        expected_mdl_startup,
    )
    if (
        _json_native_copy(dict(mdl_search_path_contract))
        != canonical_mdl_search
        or final_manifest.get("mdl_search_path_contract")
        != mdl_search_path_contract
    ):
        raise ValueError("matrix_sidecar_mdl_search_path_contract_mismatch")
    mdl_matrix_projection = {
        "schema_version": 1,
        "closure_id": mdl_closure_evidence["closure_id"],
        "files": deepcopy(mdl_closure_evidence["files"]),
        "search_path_roles": ["mdl_module_root", "base_material_root"],
        "startup_setting_paths": [
            argument.split("=", 1)[0]
            for argument in canonical_mdl_search["startup_arguments"]
        ],
        "closure_paths_precede_default_paths": True,
        "readback_verified": True,
    }
    mdl_matrix_projection_sha256 = canonical_json_sha256_v1(
        mdl_matrix_projection
    )
    mdl_closure_evidence = {
        **mdl_closure_evidence,
        "mdl_search_path_contract": canonical_mdl_search,
        "matrix_equivalence_projection": mdl_matrix_projection,
        "matrix_equivalence_projection_sha256": (
            mdl_matrix_projection_sha256
        ),
    }
    cell_payload = {
        "schema_version": 1,
        "manifest_type": "real_beaker_render_diagnostic_matrix_cell",
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "variant": variant,
        "replicate": replicate,
        "execution_order_index": order_index,
        "classification": final_manifest["classification"],
        "child_exit_code": final_manifest.get("child_process_contract", {}).get(
            "exit_code"
        ),
        "cell_root": str(cell_root),
        "implementation_identity_sha256": implementation_hash,
        "source_usd_sha256": final_manifest.get("source_usd_sha256"),
        "authority_bundle_sha256": authority.get(
            "accepted_authority_bundle_sha256"
        ),
        "physical_trace_sha256": physical_trace.get("physical_trace_sha256"),
        "normal_remediation_matrix_projection_sha256": normal_projection[
            "canonical_json_utf8_sha256"
        ],
        "liquid_material_sha256": material_id_sha256,
        "display_fill_geometry_sha256": canonical_json_sha256_v1(
            [record["display_fill_geometry_sha256"] for record in matrix_frames]
        ),
        "camera_contract_sha256": canonical_json_sha256_v1(
            final_manifest.get("camera_contracts_preflight")
        ),
        "effective_replay_look_contract_sha256": look[
            "effective_replay_look_contract_sha256"
        ],
        "effective_replay_look_matrix_projection_sha256": projection[
            "canonical_json_utf8_sha256"
        ],
        "render_settings_sha256": canonical_json_sha256_v1(
            render_settings_evidence
        ),
        "mdl_closure_sha256": mdl_matrix_projection_sha256,
        "runtime_identity_sha256": runtime_identity["runtime_identity_sha256"],
        "device_identity_sha256": device["device_identity_sha256"],
        "process_identity_sha256": process_identity["process_identity_sha256"],
        "runtime_implementation_archive_sha256": runtime_evidence[
            "runtime_implementation_archive_sha256"
        ],
        "runtime_bootstrap_sha256": runtime_evidence[
            "runtime_bootstrap_sha256"
        ],
        "source_dependency_closure_sha256": runtime_evidence[
            "source_dependency_closure_sha256"
        ],
        "artifact_inventory_sha256": artifact_inventory[
            "artifact_inventory_sha256"
        ],
        "frame_bindings_sha256": frame_sidecar["frame_bindings_sha256"],
        "media_index_sha256": media_sidecar["media_index_sha256"],
        "stopped_timeline": runtime_contract.get(
            "timeline_observed_stopped_at_all_checkpoints"
        ),
        "replicator_delta_time": static_capture.get("replicator_delta_time"),
        "default_time_points_unchanged": not bool(
            runtime_contract.get(
                "observed_default_time_usd_point_attributes_changed"
            )
        ),
        "standalone_final_evidence_authority": final_manifest.get(
            "standalone_final_evidence_authority"
        ),
        "exporter_admitted": final_manifest.get("exporter_admitted"),
        "visual_selection_eligible": final_manifest.get(
            "visual_selection_eligible"
        ),
        "formal_scope": final_manifest.get("formal_scope"),
        "delivery_ready": final_manifest.get("delivery_ready"),
    }
    cell_evidence = {
        **cell_payload,
        "matrix_cell_evidence_sha256": canonical_json_sha256_v1(cell_payload),
    }
    validate_render_diagnostic_matrix_cell_evidence(cell_evidence)
    return {
        "frame_bindings": frame_sidecar,
        "media_index": media_sidecar,
        "cell_evidence": cell_evidence,
        "implementation_identity": _json_native_copy(dict(implementation_identity)),
        "runtime_identity": runtime_identity,
        "device_identity": device,
        "process_identity": process_identity,
        "mdl_closure": mdl_closure_evidence,
        "source_dependency_closure": runtime_evidence[
            "source_dependency_closure"
        ],
        "artifact_inventory": artifact_inventory,
    }


_RENDER_DIAGNOSTIC_CELL_FAILURE_FIELDS = frozenset(
    {
        "schema_version",
        "manifest_type",
        "experiment_id",
        "variant",
        "replicate",
        "execution_order_index",
        "classification",
        "child_exit_code",
        "cell_root",
        "launch_intent_sha256",
        "implementation_identity_sha256",
        "failure_stage",
        "error_type",
        "error_message",
        "partial_manifest_path",
        "partial_manifest_sha256",
        "generated_at_utc",
        "matrix_cell_failure_evidence_sha256",
    }
)


def validate_render_diagnostic_cell_failure_evidence(
    evidence: Mapping[str, Any],
    *,
    expected_cell_root: str | os.PathLike[str] | None = None,
    expected_slot: Mapping[str, Any] | None = None,
    expected_launch_intent: Mapping[str, Any] | None = None,
    expected_implementation_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(evidence, Mapping) or set(evidence) != set(
        _RENDER_DIAGNOSTIC_CELL_FAILURE_FIELDS
    ):
        raise ValueError("matrix_cell_failure_schema_invalid")
    actual = _json_native_copy(dict(evidence))
    variant = actual.get("variant")
    replicate = actual.get("replicate")
    order_index = actual.get("execution_order_index")
    child_exit_code = actual.get("child_exit_code")
    root_value = actual.get("cell_root")
    if (
        actual.get("schema_version") != 1
        or actual.get("manifest_type")
        != "real_beaker_render_diagnostic_matrix_cell_failure"
        or actual.get("experiment_id") != RENDER_DIAGNOSTIC_EXPERIMENT_ID
        or variant not in RENDER_DIAGNOSTIC_VARIANTS
        or replicate not in RENDER_DIAGNOSTIC_REPLICATES
        or type(order_index) is not int
        or order_index not in range(4)
        or RENDER_DIAGNOSTIC_BALANCED_ORDER[replicate][order_index] != variant
        or not isinstance(actual.get("classification"), str)
        or not actual["classification"]
        or actual["classification"]
        == "DIAGNOSTIC_RENDER_COMPLETE_PENDING_VISUAL_REVIEW"
        or (
            child_exit_code is not None
            and type(child_exit_code) is not int
        )
            or (
                child_exit_code is None
                and actual.get("failure_stage")
                not in {
                    "parent_launcher_pre_spawn_setup",
                    "parent_launcher_child_start",
                }
            )
        or not isinstance(root_value, str)
        or not root_value
        or not Path(root_value).is_absolute()
        or not _is_sha256_text(actual.get("launch_intent_sha256"))
        or not _is_sha256_text(
            actual.get("implementation_identity_sha256")
        )
        or any(
            not isinstance(actual.get(field), str) or not actual[field]
            for field in (
                "failure_stage",
                "error_type",
                "error_message",
                "generated_at_utc",
            )
        )
    ):
        raise ValueError("matrix_cell_failure_contract_invalid")
    cell_root = _absolute_path_without_symlink_resolution(root_value)
    canonical_root = _absolute_path_without_symlink_resolution(
        RENDER_DIAGNOSTIC_AGGREGATE_ROOT
        / "cells"
        / f"{replicate}_{order_index}_{variant}"
    )
    if cell_root != canonical_root:
        raise ValueError("matrix_cell_failure_root_invalid")
    if expected_cell_root is not None and cell_root != (
        _absolute_path_without_symlink_resolution(expected_cell_root)
    ):
        raise ValueError("matrix_cell_failure_root_invalid")
    if expected_slot is not None and (
        variant != expected_slot.get("variant")
        or replicate != expected_slot.get("replicate")
        or order_index != expected_slot.get("execution_order_index")
        or f"{replicate}_{order_index}_{variant}"
        != expected_slot.get("cell_name")
    ):
        raise ValueError("matrix_cell_failure_slot_invalid")
    if expected_launch_intent is not None and (
        actual["launch_intent_sha256"]
        != expected_launch_intent.get("launch_intent_sha256")
        or actual["implementation_identity_sha256"]
        != expected_launch_intent.get("implementation_identity_sha256")
    ):
        raise ValueError("matrix_cell_failure_launch_binding_invalid")
    if expected_implementation_identity is not None and (
        actual["implementation_identity_sha256"]
        != expected_implementation_identity.get(
            "implementation_identity_sha256"
        )
    ):
        raise ValueError("matrix_cell_failure_implementation_binding_invalid")
    partial_path_value = actual.get("partial_manifest_path")
    partial_hash = actual.get("partial_manifest_sha256")
    if (partial_path_value is None) != (partial_hash is None):
        raise ValueError("matrix_cell_failure_partial_binding_invalid")
    if partial_path_value is not None:
        if (
            not isinstance(partial_path_value, str)
            or not partial_path_value
            or not _is_sha256_text(partial_hash)
        ):
            raise ValueError("matrix_cell_failure_partial_binding_invalid")
        partial_path = _absolute_path_without_symlink_resolution(
            partial_path_value
        )
        if (
            partial_path.parent != cell_root
            or partial_path.is_symlink()
            or not partial_path.is_file()
            or _sha256_file(partial_path) != partial_hash
        ):
            raise ValueError("matrix_cell_failure_partial_binding_invalid")
    hash_payload = {
        key: value
        for key, value in actual.items()
        if key
        not in {
            "generated_at_utc",
            "matrix_cell_failure_evidence_sha256",
        }
    }
    if actual.get("matrix_cell_failure_evidence_sha256") != (
        canonical_json_sha256_v1(hash_payload)
    ):
        raise ValueError("matrix_cell_failure_hash_invalid")
    return actual


def build_render_diagnostic_cell_failure_evidence(
    *,
    identity: Mapping[str, Any],
    implementation_identity: Mapping[str, Any],
    launch_intent: Mapping[str, Any],
    classification: str,
    child_exit_code: int | None,
    failure_stage: str,
    error_type: str,
    error_message: str,
    partial_manifest_path: str | os.PathLike[str] | None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    required_identity = {
        "experiment_id",
        "render_diagnostic_variant_id",
        "replicate",
        "execution_order_index",
        "cell_root",
    }
    if not isinstance(identity, Mapping) or set(identity) != required_identity:
        raise ValueError("matrix_cell_failure_identity_invalid")
    variant = identity["render_diagnostic_variant_id"]
    replicate = identity["replicate"]
    order_index = identity["execution_order_index"]
    implementation_hash = implementation_identity.get(
        "implementation_identity_sha256"
    )
    if (
        identity["experiment_id"] != RENDER_DIAGNOSTIC_EXPERIMENT_ID
        or replicate not in RENDER_DIAGNOSTIC_REPLICATES
        or type(order_index) is not int
        or order_index not in range(4)
        or RENDER_DIAGNOSTIC_BALANCED_ORDER[replicate][order_index] != variant
        or not _is_sha256_text(implementation_hash)
        or launch_intent.get("implementation_identity_sha256")
        != implementation_hash
        or not _is_sha256_text(launch_intent.get("launch_intent_sha256"))
    ):
        raise ValueError("matrix_cell_failure_identity_invalid")
    if (
        not isinstance(classification, str)
        or not classification
        or classification
        == "DIAGNOSTIC_RENDER_COMPLETE_PENDING_VISUAL_REVIEW"
        or (child_exit_code is not None and type(child_exit_code) is not int)
        or any(
            not isinstance(value, str) or not value
            for value in (failure_stage, error_type, error_message)
        )
    ):
        raise ValueError("matrix_cell_failure_contract_invalid")
    partial_path_value = None
    partial_hash = None
    if partial_manifest_path is not None:
        partial_path = _absolute_path_without_symlink_resolution(
            partial_manifest_path
        )
        if not partial_path.is_file() or partial_path.is_symlink():
            raise ValueError("matrix_cell_failure_partial_manifest_invalid")
        partial_path_value = str(partial_path)
        partial_hash = _sha256_file(partial_path)
    payload = {
        "schema_version": 1,
        "manifest_type": "real_beaker_render_diagnostic_matrix_cell_failure",
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "variant": variant,
        "replicate": replicate,
        "execution_order_index": order_index,
        "classification": classification,
        "child_exit_code": child_exit_code,
        "cell_root": str(
            _absolute_path_without_symlink_resolution(identity["cell_root"])
        ),
        "launch_intent_sha256": launch_intent["launch_intent_sha256"],
        "implementation_identity_sha256": implementation_hash,
        "failure_stage": failure_stage,
        "error_type": error_type,
        "error_message": error_message,
        "partial_manifest_path": partial_path_value,
        "partial_manifest_sha256": partial_hash,
        "generated_at_utc": generated_at_utc or _utc_now(),
    }
    hash_payload = {
        key: value for key, value in payload.items() if key != "generated_at_utc"
    }
    evidence = {
        **payload,
        "matrix_cell_failure_evidence_sha256": canonical_json_sha256_v1(
            hash_payload
        ),
    }
    return validate_render_diagnostic_cell_failure_evidence(
        evidence,
        expected_cell_root=identity["cell_root"],
        expected_slot={
            "variant": variant,
            "replicate": replicate,
            "execution_order_index": order_index,
            "cell_name": f"{replicate}_{order_index}_{variant}",
        },
        expected_launch_intent=launch_intent,
        expected_implementation_identity=implementation_identity,
    )


def write_render_diagnostic_cell_failure_evidence(
    *,
    cell_root: str | os.PathLike[str],
    evidence: Mapping[str, Any],
) -> dict[str, str]:
    root = _reject_symlink_path_components(
        cell_root,
        label="render_diagnostic_failure_evidence_root",
    )
    validated = validate_render_diagnostic_cell_failure_evidence(
        evidence,
        expected_cell_root=root,
    )
    path = root / "matrix_cell_failure_evidence.json"
    _write_json_create_exclusive(path, validated)
    return {"path": str(path), "sha256": _sha256_file(path)}


def _write_json_create_exclusive(
    path: Path,
    value: Mapping[str, Any],
    *,
    pre_publish_validator: Any | None = None,
    post_publish_validator: Any | None = None,
) -> None:
    path = _reject_symlink_path_components(
        path,
        label="json_create_exclusive_path",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        value,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    temporary_name = f".{path.name}.{secrets.token_hex(16)}.tmp"
    with _open_pinned_path(
        path.parent,
        leaf_directory=True,
        label="json_create_exclusive_parent",
    ) as (_parent, directory_descriptor, identities):
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if pre_publish_validator is not None:
            pre_publish_validator()
        descriptor = os.open(
            temporary_name,
            flags,
            0o600,
            dir_fd=directory_descriptor,
        )
        try:
            payload = encoded.encode("utf-8")
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("json_create_exclusive_short_write")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        published_created = False
        try:
            _verify_pinned_path_components(
                identities,
                label="json_create_exclusive_parent",
            )
            os.link(
                temporary_name,
                path.name,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            published_created = True
            published_stat = os.stat(
                path.name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            temporary = os.stat(
                temporary_name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            if (published_stat.st_dev, published_stat.st_ino) != (
                temporary.st_dev,
                temporary.st_ino,
            ):
                raise RuntimeError("json_create_exclusive_publish_mismatch")
            os.unlink(temporary_name, dir_fd=directory_descriptor)
            os.fsync(directory_descriptor)
            _verify_pinned_path_components(
                identities,
                label="json_create_exclusive_parent",
            )
            if post_publish_validator is not None:
                post_publish_validator()
        except BaseException:
            if published_created:
                try:
                    os.unlink(path.name, dir_fd=directory_descriptor)
                    os.fsync(directory_descriptor)
                except OSError:
                    pass
            raise
        finally:
            try:
                os.unlink(temporary_name, dir_fd=directory_descriptor)
            except FileNotFoundError:
                pass


def write_render_diagnostic_cell_sidecars(
    *,
    cell_root: str | os.PathLike[str],
    sidecars: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    root = _reject_symlink_path_components(
        cell_root,
        label="render_diagnostic_sidecar_root",
    )
    expected = {
        "frame_bindings": "matrix_frame_bindings.json",
        "media_index": "matrix_media_index.json",
        "implementation_identity": "matrix_implementation_identity.json",
        "runtime_identity": "runtime_identity.json",
        "device_identity": "device_identity.json",
        "process_identity": "process_identity.json",
        "mdl_closure": "matrix_mdl_closure.json",
        "source_dependency_closure": (
            RENDER_DIAGNOSTIC_SOURCE_CLOSURE_BASENAME
        ),
        "artifact_inventory": RENDER_DIAGNOSTIC_ARTIFACT_INVENTORY_BASENAME,
        "cell_evidence": "matrix_cell_evidence.json",
    }
    if not isinstance(sidecars, Mapping) or set(sidecars) != set(expected):
        raise ValueError("matrix_sidecar_set_invalid")
    written = {}
    for key, filename in expected.items():
        path = root / filename
        if key == "source_dependency_closure" and path.is_file():
            if _load_json_object(
                path,
                label="matrix_source_dependency_closure",
            ) != _json_native_copy(dict(sidecars[key])):
                raise ValueError("matrix_source_dependency_closure_changed")
        else:
            _write_json_create_exclusive(path, sidecars[key])
        written_key = {
            "frame_bindings": "matrix_frame_bindings",
            "media_index": "matrix_media_index",
            "cell_evidence": "matrix_cell_evidence",
            "implementation_identity": "matrix_implementation_identity",
            "runtime_identity": "runtime_identity",
            "device_identity": "device_identity",
            "process_identity": "process_identity",
            "mdl_closure": "matrix_mdl_closure",
            "source_dependency_closure": (
                "matrix_source_dependency_closure"
            ),
            "artifact_inventory": "matrix_cell_artifact_inventory",
        }[key]
        written[written_key] = {
            "path": str(path),
            "sha256": _sha256_file(path),
        }
    return written


def validate_render_diagnostic_cell_artifact_closure(
    *,
    cell_root: str | os.PathLike[str],
    expected_slot: Mapping[str, Any],
    expected_implementation_identity: Mapping[str, Any],
    expected_launch_intent: Mapping[str, Any],
    authoritative_path_resolver: Any | None = None,
) -> dict[str, Any]:
    root = _reject_symlink_path_components(
        cell_root,
        label="render_diagnostic_cell_artifact_root",
    )
    try:
        expected_name = expected_slot["cell_name"]
        if root.name != expected_name:
            raise ValueError("canonical_root_name_mismatch")
        identity = {
            "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
            "render_diagnostic_variant_id": expected_slot["variant"],
            "replicate": expected_slot["replicate"],
            "execution_order_index": expected_slot["execution_order_index"],
            "cell_root": str(root),
        }
        paths = {
            "frame_bindings": root / "matrix_frame_bindings.json",
            "media_index": root / "matrix_media_index.json",
            "cell_evidence": root / "matrix_cell_evidence.json",
            "implementation_identity": root / "matrix_implementation_identity.json",
            "runtime_identity": root / "runtime_identity.json",
            "device_identity": root / "device_identity.json",
            "process_identity": root / "process_identity.json",
            "mdl_closure": root / "matrix_mdl_closure.json",
            "source_dependency_closure": (
                root / RENDER_DIAGNOSTIC_SOURCE_CLOSURE_BASENAME
            ),
            "artifact_inventory": (
                root / RENDER_DIAGNOSTIC_ARTIFACT_INVENTORY_BASENAME
            ),
        }

        def authority(path: Path) -> Path:
            return _reject_symlink_path_components(
                authoritative_path_resolver(path)
                if authoritative_path_resolver is not None
                else path,
                label="matrix_artifact_authoritative_path",
            )

        loaded = {
            key: _load_json_object(
                authority(path),
                label=f"matrix_artifact:{key}",
            )
            for key, path in paths.items()
        }
        if loaded["implementation_identity"] != _json_native_copy(
            dict(expected_implementation_identity)
        ):
            raise ValueError("implementation_identity_mismatch")
        if authoritative_path_resolver is None:
            verify_matrix_implementation_identity_unchanged(
                expected_implementation_identity
            )
        cell_evidence = validate_render_diagnostic_matrix_cell_evidence(
            loaded["cell_evidence"],
            expected_cell_root=root,
            expected_slot=expected_slot,
        )
        process = loaded["process_identity"]
        process_fields = {
            "schema_version",
            "launcher_pid",
            "child_pid",
            "parent_child_fresh_process",
            "cold_start",
            "launch_intent_sha256",
            "runtime_implementation_archive_sha256",
            "inherited_fd_contract_sha256",
            "process_identity_sha256",
        }
        if (
            set(process) != process_fields
            or process.get("schema_version") != 1
            or type(process.get("launcher_pid")) is not int
            or type(process.get("child_pid")) is not int
            or process.get("launcher_pid", 0) <= 0
            or process.get("child_pid", 0) <= 0
            or process.get("parent_child_fresh_process") is not True
            or process.get("cold_start") is not True
            or process.get("process_identity_sha256")
            != canonical_json_sha256_v1(
                {
                    key: value
                    for key, value in process.items()
                    if key != "process_identity_sha256"
                }
            )
            or process.get("launch_intent_sha256")
            != expected_launch_intent.get("launch_intent_sha256")
        ):
            raise ValueError("process_identity_mismatch")
        final_manifest_path = root / "replay_manifest.json"
        final_manifest = _load_json_object(
            authority(final_manifest_path),
            label="matrix_replay_manifest",
        )
        sidecar_bindings = final_manifest.get("matrix_sidecars")
        if not isinstance(sidecar_bindings, Mapping):
            raise ValueError("manifest_sidecar_bindings_missing")
        binding_names = {
            "frame_bindings": "matrix_frame_bindings",
            "media_index": "matrix_media_index",
            "cell_evidence": "matrix_cell_evidence",
            "implementation_identity": "matrix_implementation_identity",
            "runtime_identity": "runtime_identity",
            "device_identity": "device_identity",
            "process_identity": "process_identity",
            "mdl_closure": "matrix_mdl_closure",
            "source_dependency_closure": (
                "matrix_source_dependency_closure"
            ),
            "artifact_inventory": "matrix_cell_artifact_inventory",
        }
        if set(sidecar_bindings) != set(binding_names.values()):
            raise ValueError("manifest_sidecar_binding_set_invalid")
        for key, binding_name in binding_names.items():
            binding = sidecar_bindings[binding_name]
            if (
                not isinstance(binding, Mapping)
                or _absolute_path_without_symlink_resolution(
                    binding.get("path", "")
                )
                != paths[key]
                or binding.get("sha256")
                != _sha256_file(authority(paths[key]))
            ):
                raise ValueError(f"manifest_sidecar_binding_invalid:{key}")
        if final_manifest.get("matrix_cell_evidence_sha256") != cell_evidence[
            "matrix_cell_evidence_sha256"
        ]:
            raise ValueError("manifest_cell_evidence_hash_mismatch")
        runtime_evidence = validate_render_diagnostic_runtime_manifest_evidence(
            final_manifest,
            cell_root=root,
            implementation_identity=expected_implementation_identity,
            authoritative_path_resolver=authoritative_path_resolver,
        )
        source_closure = validate_render_diagnostic_source_dependency_snapshot(
            authority(root),
            loaded["source_dependency_closure"],
            verify_usd_dependencies=False,
        )
        artifact_inventory = (
            validate_render_diagnostic_cell_artifact_inventory(
                loaded["artifact_inventory"],
                cell_root=authority(root),
            )
        )
        if (
            process.get("runtime_implementation_archive_sha256")
            != runtime_evidence["runtime_implementation_archive_sha256"]
            or process.get("inherited_fd_contract_sha256")
            != runtime_evidence["inherited_fd_contract_sha256"]
            or cell_evidence.get("runtime_implementation_archive_sha256")
            != runtime_evidence["runtime_implementation_archive_sha256"]
            or cell_evidence.get("runtime_bootstrap_sha256")
            != runtime_evidence["runtime_bootstrap_sha256"]
            or cell_evidence.get("source_dependency_closure_sha256")
            != source_closure["source_dependency_closure_sha256"]
            or cell_evidence.get("artifact_inventory_sha256")
            != artifact_inventory["artifact_inventory_sha256"]
        ):
            raise ValueError("runtime_evidence_binding_mismatch")
        rebuilt = build_render_diagnostic_cell_sidecar_payloads(
            final_manifest=final_manifest,
            identity=identity,
            implementation_identity=expected_implementation_identity,
            launch_intent=expected_launch_intent,
            launcher_pid=process["launcher_pid"],
            child_pid=process["child_pid"],
            device_identity=loaded["device_identity"],
            authoritative_path_resolver=authoritative_path_resolver,
        )
        for key, expected_value in rebuilt.items():
            if loaded.get(key) != expected_value:
                raise ValueError(f"rebuilt_sidecar_mismatch:{key}")
        return {
            "validated": True,
            "cell_root": str(root),
            "replay_manifest_sha256": _sha256_file(
                authority(final_manifest_path)
            ),
            "cell_evidence": cell_evidence,
            "sidecars": loaded,
            "replay_manifest": final_manifest,
            "sidecar_file_sha256": {
                key: _sha256_file(authority(path))
                for key, path in paths.items()
            },
        }
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError(f"matrix_artifact_closure:{exc}") from exc


def compute_render_diagnostic_repeat_stability(
    image_paths: Mapping[tuple[str, str, str, int], str | os.PathLike[str]],
) -> dict[str, Any]:
    import numpy as np
    from PIL import Image

    expected_keys = {
        (variant, replicate, view, frame)
        for variant in RENDER_DIAGNOSTIC_VARIANTS
        for replicate in RENDER_DIAGNOSTIC_REPLICATES
        for view in RENDER_DIAGNOSTIC_REVIEW_VIEWS
        for frame in RENDER_DIAGNOSTIC_REVIEW_FRAMES
    }
    if not isinstance(image_paths, Mapping) or set(image_paths) != expected_keys:
        raise ValueError("repeat_stability_image_key_set_invalid")
    array_cache: dict[Path, Any] = {}
    hash_cache: dict[Path, str] = {}

    def load(path_value: str | os.PathLike[str]) -> tuple[Any, str]:
        path = _reject_symlink_path_components(
            path_value,
            label="render_diagnostic_repeat_image",
        )
        if path not in array_cache:
            if not path.is_file() or path.is_symlink():
                raise ValueError(f"repeat_stability_image_invalid:{path}")
            with _open_image_file_snapshot(
                path,
                label="render_diagnostic_repeat_image",
            ) as image:
                array = np.asarray(image.convert("RGB"), dtype=np.float64)
            if array.ndim != 3 or array.shape[2] != 3:
                raise ValueError(f"repeat_stability_image_rgb_invalid:{path}")
            array_cache[path] = array
            hash_cache[path] = _sha256_file(path)
        return array_cache[path], hash_cache[path]

    comparisons: list[dict[str, Any]] = []
    for variant in RENDER_DIAGNOSTIC_VARIANTS:
        for view in RENDER_DIAGNOSTIC_REVIEW_VIEWS:
            for frame in RENDER_DIAGNOSTIC_REVIEW_FRAMES:
                for left_replicate, right_replicate in (
                    RENDER_DIAGNOSTIC_REPLICATE_PAIRS
                ):
                    left, left_hash = load(
                        image_paths[(variant, left_replicate, view, frame)]
                    )
                    right, right_hash = load(
                        image_paths[(variant, right_replicate, view, frame)]
                    )
                    if left.shape != right.shape:
                        raise ValueError("repeat_stability_image_shape_mismatch")
                    difference = left - right
                    mae = float(np.mean(np.abs(difference)))
                    mse = float(np.mean(np.square(difference)))
                    psnr: float | str = (
                        "INF"
                        if mse == 0.0
                        else float(10.0 * math.log10((255.0**2) / mse))
                    )
                    passed = mae <= 5.0 and (
                        psnr == "INF" or float(psnr) >= 30.0
                    )
                    comparisons.append(
                        {
                            "variant": variant,
                            "view": view,
                            "frame": frame,
                            "left_replicate": left_replicate,
                            "right_replicate": right_replicate,
                            "left_png_sha256": left_hash,
                            "right_png_sha256": right_hash,
                            "rgb_mae": mae,
                            "psnr_db": psnr,
                            "status": "PASS" if passed else "FAIL",
                        }
                    )
    payload = {
        "schema_version": 1,
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "status": (
            "PASS"
            if all(record["status"] == "PASS" for record in comparisons)
            else "FAIL"
        ),
        "thresholds": {"rgb_mae_max": 5.0, "psnr_db_min": 30.0},
        "comparisons": comparisons,
    }
    return {
        **payload,
        "repeat_stability_evidence_sha256": canonical_json_sha256_v1(payload),
    }


def validate_render_diagnostic_matrix_validation_evidence(
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "experiment_id",
        "status",
        "exact_slot_closure",
        "all_cells_successful",
        "unexpected_paths",
        "equality_checks",
        "projection_byte_equality",
        "projection_sha256",
        "matrix_validation_evidence_sha256",
    }
    if not isinstance(evidence, Mapping) or set(evidence) != fields:
        raise ValueError("matrix_validation_evidence_schema_invalid")
    actual = _json_native_copy(dict(evidence))
    payload = {
        key: value
        for key, value in actual.items()
        if key != "matrix_validation_evidence_sha256"
    }
    status_value = actual.get("status")
    if (
        actual.get("schema_version") != 1
        or actual.get("experiment_id") != RENDER_DIAGNOSTIC_EXPERIMENT_ID
        or status_value not in {"PASS", "FAIL", "NOT_REACHED"}
        or actual.get("matrix_validation_evidence_sha256")
        != canonical_json_sha256_v1(payload)
    ):
        raise ValueError("matrix_validation_evidence_invalid")
    if status_value == "NOT_REACHED":
        if (
            actual["exact_slot_closure"] is not None
            or actual["all_cells_successful"] is not None
            or actual["projection_byte_equality"] is not None
            or actual["projection_sha256"] is not None
            or actual["unexpected_paths"] != []
            or actual["equality_checks"] != []
        ):
            raise ValueError("matrix_validation_evidence_not_reached_invalid")
        return actual
    equality_names = {
        "implementation_identity",
        "source_usd",
        "authority_bundle",
        "physical_trace",
            "normal_remediation_matrix_projection",
        "liquid_material",
        "display_fill_geometry",
        "camera_contract",
        "mdl_closure",
        "runtime_identity",
        "device_identity",
        "runtime_implementation_archive",
        "runtime_bootstrap",
        "source_dependency_closure",
    }
    checks = actual["equality_checks"]
    unexpected = actual["unexpected_paths"]
    if (
        any(
            type(actual[field]) is not bool
            for field in (
                "exact_slot_closure",
                "all_cells_successful",
                "projection_byte_equality",
            )
        )
        or not isinstance(unexpected, list)
        or unexpected != sorted(set(unexpected))
        or any(
            not isinstance(path, str) or not Path(path).is_absolute()
            for path in unexpected
        )
        or not isinstance(checks, list)
        or any(not isinstance(record, Mapping) for record in checks)
        or [record.get("name") for record in checks]
        != sorted(equality_names)
        or any(
            set(record) != {"name", "status", "reference_sha256"}
            or record.get("status") not in {"PASS", "FAIL"}
            or not _is_sha256_text(record.get("reference_sha256"))
            for record in checks
        )
        or (
            actual["projection_sha256"] is not None
            and not _is_sha256_text(actual["projection_sha256"])
        )
        or (
            actual["projection_byte_equality"]
            and not _is_sha256_text(actual["projection_sha256"])
        )
    ):
        raise ValueError("matrix_validation_evidence_reached_invalid")
    return actual


def validate_render_diagnostic_repeat_stability_evidence(
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "experiment_id",
        "status",
        "thresholds",
        "comparisons",
        "repeat_stability_evidence_sha256",
    }
    if not isinstance(evidence, Mapping) or set(evidence) != fields:
        raise ValueError("repeat_stability_evidence_schema_invalid")
    actual = _json_native_copy(dict(evidence))
    payload = {
        key: value
        for key, value in actual.items()
        if key != "repeat_stability_evidence_sha256"
    }
    status_value = actual.get("status")
    if (
        actual.get("schema_version") != 1
        or actual.get("experiment_id") != RENDER_DIAGNOSTIC_EXPERIMENT_ID
        or status_value not in {"PASS", "FAIL", "NOT_REACHED"}
        or actual.get("thresholds")
        != {"rgb_mae_max": 5.0, "psnr_db_min": 30.0}
        or actual.get("repeat_stability_evidence_sha256")
        != canonical_json_sha256_v1(payload)
        or not isinstance(actual.get("comparisons"), list)
    ):
        raise ValueError("repeat_stability_evidence_invalid")
    comparisons = actual["comparisons"]
    if status_value == "NOT_REACHED":
        if comparisons:
            raise ValueError("repeat_stability_not_reached_invalid")
        return actual
    expected_order = [
        (variant, view, frame, left, right)
        for variant in RENDER_DIAGNOSTIC_VARIANTS
        for view in RENDER_DIAGNOSTIC_REVIEW_VIEWS
        for frame in RENDER_DIAGNOSTIC_REVIEW_FRAMES
        for left, right in RENDER_DIAGNOSTIC_REPLICATE_PAIRS
    ]
    actual_order = []
    record_fields = {
        "variant",
        "view",
        "frame",
        "left_replicate",
        "right_replicate",
        "left_png_sha256",
        "right_png_sha256",
        "rgb_mae",
        "psnr_db",
        "status",
    }
    for record in comparisons:
        if not isinstance(record, Mapping) or set(record) != record_fields:
            raise ValueError("repeat_stability_comparison_schema_invalid")
        actual_order.append(
            (
                record["variant"],
                record["view"],
                record["frame"],
                record["left_replicate"],
                record["right_replicate"],
            )
        )
        psnr = record["psnr_db"]
        if (
            not _is_sha256_text(record["left_png_sha256"])
            or not _is_sha256_text(record["right_png_sha256"])
            or type(record["rgb_mae"]) not in {int, float}
            or type(record["rgb_mae"]) is bool
            or not math.isfinite(float(record["rgb_mae"]))
            or not (
                psnr == "INF"
                or (
                    type(psnr) in {int, float}
                    and type(psnr) is not bool
                    and math.isfinite(float(psnr))
                )
            )
            or record["status"] not in {"PASS", "FAIL"}
        ):
            raise ValueError("repeat_stability_comparison_invalid")
    if actual_order != expected_order:
        raise ValueError("repeat_stability_comparison_order_invalid")
    return actual


def capture_and_discard_render_diagnostic_warmup(
    *,
    capture_function: Any,
    output_root: str | os.PathLike[str],
    frame_index: int,
    orchestrator: Any,
    timeline: Any,
    annotators: Mapping[str, Any],
    width: int,
    height: int,
    rt_subframes: int,
    observed_default_time_usd_point_attributes_hash: Any,
) -> dict[str, Any]:
    from PIL import Image

    if not callable(capture_function):
        raise TypeError("render_diagnostic_warmup_capture_not_callable")
    if set(annotators) != set(CAPTURE_CAMERA_ROLES):
        raise ValueError("render_diagnostic_warmup_camera_roles_invalid")
    index = _require_plain_int("render_diagnostic_warmup_frame", frame_index, minimum=0)
    root = _reject_symlink_path_components(
        output_root,
        label="render_diagnostic_warmup_root",
    )
    if root.exists():
        raise FileExistsError(f"render_diagnostic_warmup_root_exists:{root}")
    paths = {
        role: root / role / f"frame_{index:04d}.png"
        for role in CAPTURE_CAMERA_ROLES
    }
    capture_contract: dict[str, Any] | None = None
    hashes: dict[str, str] = {}
    try:
        capture_contract = capture_function(
            orchestrator=orchestrator,
            timeline=timeline,
            annotators=dict(annotators),
            output_paths=paths,
            width=width,
            height=height,
            rt_subframes=rt_subframes,
            observed_default_time_usd_point_attributes_hash=(
                observed_default_time_usd_point_attributes_hash
            ),
        )
        if not isinstance(capture_contract, Mapping):
            raise RuntimeError("render_diagnostic_warmup_capture_contract_invalid")
        for role, path in paths.items():
            if not path.is_file() or path.is_symlink():
                raise RuntimeError(
                    f"render_diagnostic_warmup_image_missing:{role}:{path}"
                )
            with _open_image_file_snapshot(
                path,
                label="render_diagnostic_warmup_image",
            ) as image:
                actual_size = image.size
                image.convert("RGB").load()
            if actual_size != (width, height):
                raise RuntimeError(
                    "render_diagnostic_warmup_image_dimensions_invalid:"
                    f"{role}:{actual_size}!={(width, height)}"
                )
            hashes[role] = _sha256_file(path)
    finally:
        if root.exists():
            shutil.rmtree(root)
    if capture_contract is None:
        raise AssertionError("render_diagnostic_warmup_capture_missing")
    return {
        "schema_version": 1,
        "discarded": True,
        "frame_index": index,
        "discarded_image_sha256": hashes,
        "capture_contract": _json_native_copy(dict(capture_contract)),
        "output_root_removed": not root.exists(),
    }


def create_render_diagnostic_blind_review_assets(
    *,
    image_paths: Mapping[tuple[str, str, str, int], str | os.PathLike[str]],
    output_root: str | os.PathLike[str],
    label_variant_order: Sequence[str] | None = None,
    column_label_orders: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    from PIL import Image, ImageDraw, ImageFont

    expected_keys = {
        (variant, replicate, view, frame)
        for variant in RENDER_DIAGNOSTIC_VARIANTS
        for replicate in RENDER_DIAGNOSTIC_REPLICATES
        for view in RENDER_DIAGNOSTIC_REVIEW_VIEWS
        for frame in RENDER_DIAGNOSTIC_REVIEW_FRAMES
    }
    if not isinstance(image_paths, Mapping) or set(image_paths) != expected_keys:
        raise ValueError("blind_review_image_key_set_invalid")
    root = _reject_symlink_path_components(
        output_root,
        label="blind_review_output_root",
    )
    if root.exists():
        raise FileExistsError(f"blind_review_output_root_exists:{root}")
    root.mkdir(parents=True)
    sheets_root = root / "sheets"
    sheets_root.mkdir()
    labels = [f"L{index}" for index in range(4)]
    if label_variant_order is None:
        variants = list(RENDER_DIAGNOSTIC_VARIANTS)
        secrets.SystemRandom().shuffle(variants)
    else:
        variants = list(label_variant_order)
    if len(variants) != 4 or set(variants) != set(RENDER_DIAGNOSTIC_VARIANTS):
        raise ValueError("blind_review_label_variant_order_invalid")
    variant_by_label = dict(zip(labels, variants))
    if column_label_orders is None:
        resolved_column_orders = {}
        random_source = secrets.SystemRandom()
        for replicate in RENDER_DIAGNOSTIC_REPLICATES:
            order = list(labels)
            random_source.shuffle(order)
            resolved_column_orders[replicate] = tuple(order)
    else:
        if set(column_label_orders) != set(RENDER_DIAGNOSTIC_REPLICATES):
            raise ValueError("blind_review_column_orders_invalid")
        resolved_column_orders = {
            replicate: tuple(column_label_orders[replicate])
            for replicate in RENDER_DIAGNOSTIC_REPLICATES
        }
    if any(
        len(order) != 4 or set(order) != set(labels)
        for order in resolved_column_orders.values()
    ):
        raise ValueError("blind_review_column_orders_invalid")
    panel_width = 640
    panel_height = 360
    header_height = 40
    font = ImageFont.load_default()
    sheet_records = []
    panel_records = []
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    try:
        for replicate in RENDER_DIAGNOSTIC_REPLICATES:
            column_labels = resolved_column_orders[replicate]
            for view in RENDER_DIAGNOSTIC_REVIEW_VIEWS:
                sheet = Image.new(
                    "RGB",
                    (panel_width * 4, header_height + panel_height * 3),
                    (20, 20, 20),
                )
                draw = ImageDraw.Draw(sheet)
                sheet_panels = []
                for column, label in enumerate(column_labels):
                    draw.text(
                        (column * panel_width + 12, 12),
                        label,
                        fill=(255, 255, 255),
                        font=font,
                    )
                for row, (frame, frame_label) in enumerate(
                    zip(
                        RENDER_DIAGNOSTIC_REVIEW_FRAMES,
                        RENDER_DIAGNOSTIC_REVIEW_FRAME_LABELS,
                    )
                ):
                    for column, label in enumerate(column_labels):
                        variant = variant_by_label[label]
                        source_path = _reject_symlink_path_components(
                            image_paths[(variant, replicate, view, frame)],
                            label="blind_review_source_image",
                        )
                        if not source_path.is_file() or source_path.is_symlink():
                            raise ValueError(
                                f"blind_review_source_image_invalid:{source_path}"
                            )
                        with _open_image_file_snapshot(
                            source_path,
                            label="blind_review_source_image",
                        ) as source:
                            rgb = source.convert("RGB")
                            resized = rgb.resize(
                                (panel_width, panel_height),
                                resampling,
                            )
                        sheet.paste(
                            resized,
                            (
                                column * panel_width,
                                header_height + row * panel_height,
                            ),
                        )
                        panel_id = (
                            f"{replicate}/{view}/{frame_label}/"
                            f"column_{column}/{label}"
                        )
                        sheet_panels.append(
                            {
                                "panel_id": panel_id,
                                "replicate": replicate,
                                "view": view,
                                "frame": frame_label,
                                "blinded_column": column,
                                "sheet_sha256": None,
                                "blinded_label": label,
                                "source_png_path": str(source_path),
                                "source_png_sha256": _sha256_file(source_path),
                            }
                        )
                sheet_path = sheets_root / f"{replicate}_{view}.png"
                sheet.save(sheet_path)
                sheet_hash = _sha256_file(sheet_path)
                for panel in sheet_panels:
                    panel["sheet_sha256"] = sheet_hash
                panel_records.extend(sheet_panels)
                sheet_records.append(
                    {
                        "path": str(sheet_path),
                        "sha256": sheet_hash,
                        "width": sheet.width,
                        "height": sheet.height,
                    }
                )
    except BaseException:
        if root.exists():
            shutil.rmtree(root)
        raise
    panel_map = {"schema_version": 1, "panels": panel_records}
    blinded_label_map = {
        "schema_version": 1,
        "labels": [
            {"blinded_label": label, "variant": variant_by_label[label]}
            for label in labels
        ],
    }
    _write_json_create_exclusive(root / "panel_map.json", panel_map)
    _write_json_create_exclusive(
        root / "blinded_label_map.json",
        blinded_label_map,
    )
    return {
        "sheets": sorted(sheet_records, key=lambda record: record["path"]),
        "panel_map": panel_map,
        "panel_map_sha256": canonical_json_sha256_v1(panel_map),
        "blinded_label_map": blinded_label_map,
        "blinded_label_map_sha256": canonical_json_sha256_v1(
            blinded_label_map
        ),
        "column_label_orders": {
            replicate: list(resolved_column_orders[replicate])
            for replicate in RENDER_DIAGNOSTIC_REPLICATES
        },
    }


def derive_render_diagnostic_visual_gates(
    *,
    panel_map: Mapping[str, Any],
    blinded_label_map: Mapping[str, Any],
    raw_blinded_verdicts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    panel_fields = {
        "panel_id",
        "replicate",
        "view",
        "frame",
        "blinded_column",
        "sheet_sha256",
        "blinded_label",
        "source_png_path",
        "source_png_sha256",
    }
    verdict_fields = {
        "panel_id",
        "source_png_sha256",
        "material_verdict",
        "hard_flags",
        "containment_and_grounding",
        "external_liquid_visible",
        "penetration_visible",
        "starburst_visible",
        "broken_normal_visible",
        "framing_blocker_visible",
        "visible_evidence",
    }
    hard_flag_fields = {
        "top_is_nearly_black",
        "body_is_ink_like",
        "cyan_top_not_readable",
    }
    if (
        not isinstance(panel_map, Mapping)
        or set(panel_map) != {"schema_version", "panels"}
        or panel_map.get("schema_version") != 1
        or not isinstance(panel_map.get("panels"), list)
    ):
        raise ValueError("render_diagnostic_panel_map_invalid")
    if (
        not isinstance(blinded_label_map, Mapping)
        or set(blinded_label_map) != {"schema_version", "labels"}
        or blinded_label_map.get("schema_version") != 1
        or not isinstance(blinded_label_map.get("labels"), list)
    ):
        raise ValueError("render_diagnostic_label_map_invalid")
    labels = blinded_label_map["labels"]
    expected_labels = [f"L{index}" for index in range(4)]
    if (
        len(labels) != 4
        or any(
            not isinstance(record, Mapping)
            or
            set(record) != {"blinded_label", "variant"}
            for record in labels
        )
        or [record.get("blinded_label") for record in labels] != expected_labels
        or {record.get("variant") for record in labels}
        != set(RENDER_DIAGNOSTIC_VARIANTS)
    ):
        raise ValueError("render_diagnostic_label_map_invalid")
    variant_by_label = {
        record["blinded_label"]: record["variant"] for record in labels
    }
    panels = panel_map["panels"]
    if len(panels) != 96:
        raise ValueError("render_diagnostic_panel_count_invalid")
    panel_by_id: dict[str, Mapping[str, Any]] = {}
    panel_order_keys = []
    group_labels: dict[tuple[str, str, str], set[str]] = {}
    group_columns: dict[tuple[str, str, str], set[int]] = {}
    for panel in panels:
        if not isinstance(panel, Mapping) or set(panel) != panel_fields:
            raise ValueError("render_diagnostic_panel_record_invalid")
        panel_id = panel["panel_id"]
        expected_id = (
            f"{panel['replicate']}/{panel['view']}/{panel['frame']}/"
            f"column_{panel['blinded_column']}/{panel['blinded_label']}"
        )
        if (
            panel_id != expected_id
            or panel["replicate"] not in RENDER_DIAGNOSTIC_REPLICATES
            or panel["view"] not in RENDER_DIAGNOSTIC_REVIEW_VIEWS
            or panel["frame"] not in RENDER_DIAGNOSTIC_REVIEW_FRAME_LABELS
            or type(panel["blinded_column"]) is not int
            or panel["blinded_column"] not in range(4)
            or panel["blinded_label"] not in variant_by_label
            or not _is_sha256_text(panel["sheet_sha256"])
            or not _is_sha256_text(panel["source_png_sha256"])
            or not isinstance(panel["source_png_path"], str)
            or not panel["source_png_path"]
            or panel_id in panel_by_id
        ):
            raise ValueError("render_diagnostic_panel_record_invalid")
        panel_by_id[panel_id] = panel
        group = (panel["replicate"], panel["view"], panel["frame"])
        group_labels.setdefault(group, set()).add(panel["blinded_label"])
        group_columns.setdefault(group, set()).add(panel["blinded_column"])
        panel_order_keys.append(
            (
                RENDER_DIAGNOSTIC_REPLICATES.index(panel["replicate"]),
                RENDER_DIAGNOSTIC_REVIEW_VIEWS.index(panel["view"]),
                RENDER_DIAGNOSTIC_REVIEW_FRAME_LABELS.index(panel["frame"]),
                panel["blinded_column"],
            )
        )
    expected_groups = {
        (replicate, view, frame)
        for replicate in RENDER_DIAGNOSTIC_REPLICATES
        for view in RENDER_DIAGNOSTIC_REVIEW_VIEWS
        for frame in RENDER_DIAGNOSTIC_REVIEW_FRAME_LABELS
    }
    if (
        panel_order_keys != sorted(panel_order_keys)
        or set(group_labels) != expected_groups
        or any(labels != set(expected_labels) for labels in group_labels.values())
        or any(columns != set(range(4)) for columns in group_columns.values())
    ):
        raise ValueError("render_diagnostic_panel_order_invalid")
    if (
        not isinstance(raw_blinded_verdicts, Sequence)
        or isinstance(raw_blinded_verdicts, (str, bytes))
        or len(raw_blinded_verdicts) != 96
    ):
        raise ValueError("render_diagnostic_raw_verdict_count_invalid")
    verdict_by_id: dict[str, dict[str, Any]] = {}
    for verdict in raw_blinded_verdicts:
        if not isinstance(verdict, Mapping) or set(verdict) != verdict_fields:
            raise ValueError("render_diagnostic_raw_verdict_invalid")
        native = _json_native_copy(dict(verdict))
        panel_id = native["panel_id"]
        flags = native["hard_flags"]
        visibility_fields = (
            "external_liquid_visible",
            "penetration_visible",
            "starburst_visible",
            "broken_normal_visible",
            "framing_blocker_visible",
        )
        if (
            panel_id not in panel_by_id
            or panel_id in verdict_by_id
            or native["source_png_sha256"]
            != panel_by_id[panel_id]["source_png_sha256"]
            or native["material_verdict"] not in {"PASS", "WARN", "FAIL"}
            or native["containment_and_grounding"]
            not in {"PASS", "WARN", "FAIL"}
            or not isinstance(flags, dict)
            or set(flags) != hard_flag_fields
            or any(type(value) is not bool for value in flags.values())
            or any(type(native[field]) is not bool for field in visibility_fields)
            or not isinstance(native["visible_evidence"], list)
            or not native["visible_evidence"]
            or any(
                not isinstance(value, str) or not value
                for value in native["visible_evidence"]
            )
        ):
            raise ValueError("render_diagnostic_raw_verdict_invalid")
        verdict_by_id[panel_id] = native
    if [record["panel_id"] for record in raw_blinded_verdicts] != sorted(
        verdict_by_id
    ):
        raise ValueError("render_diagnostic_raw_verdict_order_invalid")

    verdicts = {
        variant: {
            replicate: {
                view: {frame: None for frame in RENDER_DIAGNOSTIC_REVIEW_FRAME_LABELS}
                for view in RENDER_DIAGNOSTIC_REVIEW_VIEWS
            }
            for replicate in RENDER_DIAGNOSTIC_REPLICATES
        }
        for variant in RENDER_DIAGNOSTIC_VARIANTS
    }
    for panel_id, panel in panel_by_id.items():
        variant = variant_by_label[panel["blinded_label"]]
        verdicts[variant][panel["replicate"]][panel["view"]][panel["frame"]] = (
            verdict_by_id[panel_id]
        )

    panel_gates: dict[str, Any] = {}
    replicate_gates: dict[str, Any] = {}
    configuration_gates: dict[str, str] = {}
    visibility_fields = (
        "external_liquid_visible",
        "penetration_visible",
        "starburst_visible",
        "broken_normal_visible",
        "framing_blocker_visible",
    )
    for variant in RENDER_DIAGNOSTIC_VARIANTS:
        panel_gates[variant] = {}
        replicate_gates[variant] = {}
        for replicate in RENDER_DIAGNOSTIC_REPLICATES:
            panel_gates[variant][replicate] = {}
            replicate_leaf_gates = []
            for view in RENDER_DIAGNOSTIC_REVIEW_VIEWS:
                panel_gates[variant][replicate][view] = {}
                for frame in RENDER_DIAGNOSTIC_REVIEW_FRAME_LABELS:
                    leaf = verdicts[variant][replicate][view][frame]
                    if leaf is None:
                        gate = "INDETERMINATE"
                    elif (
                        leaf["material_verdict"] == "WARN"
                        or leaf["containment_and_grounding"] == "WARN"
                    ):
                        gate = "INDETERMINATE"
                    elif (
                        leaf["material_verdict"] == "FAIL"
                        or leaf["containment_and_grounding"] == "FAIL"
                        or any(leaf["hard_flags"].values())
                        or any(leaf[field] for field in visibility_fields)
                    ):
                        gate = "FAIL"
                    else:
                        gate = "PASS"
                    panel_gates[variant][replicate][view][frame] = gate
                    replicate_leaf_gates.append(gate)
            if all(gate == "PASS" for gate in replicate_leaf_gates):
                replicate_gate = "PASS"
            elif "INDETERMINATE" not in replicate_leaf_gates and any(
                gate == "FAIL" for gate in replicate_leaf_gates
            ):
                replicate_gate = "FAIL"
            else:
                replicate_gate = "INDETERMINATE"
            replicate_gates[variant][replicate] = replicate_gate
        replicate_values = list(replicate_gates[variant].values())
        configuration_gates[variant] = (
            replicate_values[0]
            if len(set(replicate_values)) == 1
            and replicate_values[0] in {"PASS", "FAIL"}
            else "INDETERMINATE"
        )
    gates = {
        "panel_gates": panel_gates,
        "replicate_gates": replicate_gates,
        "configuration_gates": configuration_gates,
    }
    return {
        "raw_blinded_verdicts": _json_native_copy(list(raw_blinded_verdicts)),
        "raw_blinded_verdicts_sha256": canonical_json_sha256_v1(
            list(raw_blinded_verdicts)
        ),
        "verdicts": verdicts,
        "verdicts_sha256": canonical_json_sha256_v1(verdicts),
        **gates,
        "derived_gate_sha256": canonical_json_sha256_v1(gates),
    }


_RENDER_DIAGNOSTIC_REVIEW_FIELDS = frozenset(
    {
        "schema_version",
        "review_id",
        "sheets",
        "panel_map_path",
        "panel_map_sha256",
        "blinded_label_map_path",
        "blinded_label_map_sha256",
        "reviewer",
        "raw_blinded_verdicts",
        "raw_blinded_verdicts_sha256",
        "verdicts",
        "verdicts_sha256",
        "panel_gates",
        "replicate_gates",
        "configuration_gates",
        "derived_gate_sha256",
        "review_record_sha256",
    }
)
_RENDER_DIAGNOSTIC_REVIEWER_FIELDS = frozenset(
    {
        "mechanism",
        "session_id",
        "forked_implementation_context",
        "repository_context_supplied",
        "condition_mapping_supplied_before_verdict",
    }
)


def build_render_diagnostic_review_record(
    *,
    review_root: str | os.PathLike[str],
    review_id: str,
    reviewer: Mapping[str, Any],
    raw_blinded_verdicts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    from PIL import Image

    root = _reject_symlink_path_components(
        review_root,
        label="render_diagnostic_review_root",
    )
    panel_map_path = root / "panel_map.json"
    label_map_path = root / "blinded_label_map.json"
    panel_map = _load_json_object(panel_map_path, label="review_panel_map")
    label_map = _load_json_object(label_map_path, label="review_label_map")
    sheet_records = []
    for replicate in RENDER_DIAGNOSTIC_REPLICATES:
        for view in RENDER_DIAGNOSTIC_REVIEW_VIEWS:
            path = root / "sheets" / f"{replicate}_{view}.png"
            if not path.is_file() or path.is_symlink():
                raise ValueError(f"review_sheet_invalid:{path}")
            with _open_image_file_snapshot(
                path,
                label="review_sheet",
            ) as image:
                width, height = image.size
                image.verify()
            sheet_records.append(
                {
                    "path": str(path),
                    "sha256": _sha256_file(path),
                    "width": width,
                    "height": height,
                }
            )
    sheet_records.sort(key=lambda record: record["path"])
    derived = derive_render_diagnostic_visual_gates(
        panel_map=panel_map,
        blinded_label_map=label_map,
        raw_blinded_verdicts=raw_blinded_verdicts,
    )
    payload = {
        "schema_version": 1,
        "review_id": review_id,
        "sheets": sheet_records,
        "panel_map_path": str(panel_map_path),
        "panel_map_sha256": canonical_json_sha256_v1(panel_map),
        "blinded_label_map_path": str(label_map_path),
        "blinded_label_map_sha256": canonical_json_sha256_v1(label_map),
        "reviewer": _json_native_copy(dict(reviewer)),
        "raw_blinded_verdicts": derived["raw_blinded_verdicts"],
        "raw_blinded_verdicts_sha256": derived[
            "raw_blinded_verdicts_sha256"
        ],
        "verdicts": derived["verdicts"],
        "verdicts_sha256": derived["verdicts_sha256"],
        "panel_gates": derived["panel_gates"],
        "replicate_gates": derived["replicate_gates"],
        "configuration_gates": derived["configuration_gates"],
        "derived_gate_sha256": derived["derived_gate_sha256"],
    }
    record = {
        **payload,
        "review_record_sha256": canonical_json_sha256_v1(payload),
    }
    return validate_render_diagnostic_review_record(record)


def validate_render_diagnostic_review_record(
    review_record: Mapping[str, Any],
    *,
    expected_image_lookup: Mapping[
        tuple[str, str, str, int], str | os.PathLike[str]
    ]
    | None = None,
    expected_review_root: str | os.PathLike[str] | None = None,
    authoritative_path_resolver: Any | None = None,
) -> dict[str, Any]:
    from PIL import Image

    if not isinstance(review_record, Mapping) or set(review_record) != set(
        _RENDER_DIAGNOSTIC_REVIEW_FIELDS
    ):
        raise ValueError("render_diagnostic_review_record_schema_invalid")
    actual = _json_native_copy(dict(review_record))
    reviewer = actual.get("reviewer")
    if (
        not isinstance(reviewer, Mapping)
        or set(reviewer) != set(_RENDER_DIAGNOSTIC_REVIEWER_FIELDS)
        or not isinstance(reviewer.get("mechanism"), str)
        or not reviewer.get("mechanism")
        or not isinstance(reviewer.get("session_id"), str)
        or not reviewer.get("session_id")
        or any(
            type(reviewer.get(field)) is not bool
            for field in (
                "forked_implementation_context",
                "repository_context_supplied",
                "condition_mapping_supplied_before_verdict",
            )
        )
        or any(
            reviewer.get(field) is not False
            for field in (
                "forked_implementation_context",
                "repository_context_supplied",
                "condition_mapping_supplied_before_verdict",
            )
        )
    ):
        raise ValueError("reviewer_independence_invalid")
    if actual.get("schema_version") != 1 or not isinstance(
        actual.get("review_id"), str
    ) or not actual.get("review_id"):
        raise ValueError("render_diagnostic_review_record_schema_invalid")

    def read_path(path: Path) -> Path:
        if authoritative_path_resolver is None:
            return path
        resolved = authoritative_path_resolver(path)
        return _reject_symlink_path_components(
            resolved,
            label="render_diagnostic_review_authoritative_path",
        )

    panel_map_path = _reject_symlink_path_components(
        actual["panel_map_path"],
        label="render_diagnostic_review_panel_map",
    )
    label_map_path = _reject_symlink_path_components(
        actual["blinded_label_map_path"],
        label="render_diagnostic_review_label_map",
    )
    review_root = panel_map_path.parent
    if (
        panel_map_path != review_root / "panel_map.json"
        or label_map_path != review_root / "blinded_label_map.json"
        or (
            expected_review_root is not None
            and review_root
            != _reject_symlink_path_components(
                expected_review_root,
                label="render_diagnostic_review_root",
            )
        )
    ):
        raise ValueError("render_diagnostic_review_root_binding_invalid")
    panel_map = _load_json_object(
        read_path(panel_map_path), label="review_panel_map"
    )
    label_map = _load_json_object(
        read_path(label_map_path), label="review_label_map"
    )
    if (
        actual["panel_map_sha256"] != canonical_json_sha256_v1(panel_map)
        or actual["blinded_label_map_sha256"]
        != canonical_json_sha256_v1(label_map)
    ):
        raise ValueError("render_diagnostic_review_mapping_hash_invalid")
    sheets = actual.get("sheets")
    if not isinstance(sheets, list) or len(sheets) != 8:
        raise ValueError("render_diagnostic_review_sheet_set_invalid")
    if any(
        not isinstance(sheet, Mapping)
        or set(sheet) != {"path", "sha256", "width", "height"}
        or not isinstance(sheet.get("path"), str)
        for sheet in sheets
    ):
        raise ValueError("render_diagnostic_review_sheet_invalid")
    if sheets != sorted(sheets, key=lambda record: record["path"]):
        raise ValueError("render_diagnostic_review_sheet_order_invalid")
    expected_sheet_paths = {
        (replicate, view): (
            review_root / "sheets" / f"{replicate}_{view}.png"
        ).resolve()
        for replicate in RENDER_DIAGNOSTIC_REPLICATES
        for view in RENDER_DIAGNOSTIC_REVIEW_VIEWS
    }
    sheet_by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
    for sheet in sheets:
        path = _reject_symlink_path_components(
            sheet["path"],
            label="render_diagnostic_review_sheet",
        )
        authoritative_sheet = read_path(path)
        matching_keys = [
            key for key, expected_path in expected_sheet_paths.items()
            if path == expected_path
        ]
        if (
            len(matching_keys) != 1
            or matching_keys[0] in sheet_by_key
            or authoritative_sheet.is_symlink()
            or not authoritative_sheet.is_file()
            or not _is_sha256_text(sheet.get("sha256"))
            or type(sheet.get("width")) is not int
            or type(sheet.get("height")) is not int
            or sheet["width"] <= 0
            or sheet["height"] <= 0
            or _sha256_file(authoritative_sheet) != sheet["sha256"]
        ):
            raise ValueError("render_diagnostic_review_sheet_invalid")
        with _open_image_file_snapshot(
            authoritative_sheet,
            label="render_diagnostic_review_sheet",
        ) as image:
            dimensions = image.size
            image.verify()
        if (
            dimensions != (sheet["width"], sheet["height"])
            or dimensions != (2560, 1120)
        ):
            raise ValueError("render_diagnostic_review_sheet_invalid")
        sheet_by_key[matching_keys[0]] = sheet
    if set(sheet_by_key) != set(expected_sheet_paths):
        raise ValueError("render_diagnostic_review_sheet_set_invalid")
    labels = label_map.get("labels")
    if not isinstance(labels, list):
        raise ValueError("render_diagnostic_label_map_invalid")
    variant_by_label = {
        record.get("blinded_label"): record.get("variant")
        for record in labels
        if isinstance(record, Mapping)
    }
    required_image_keys = {
        (variant, replicate, view, frame)
        for variant in RENDER_DIAGNOSTIC_VARIANTS
        for replicate in RENDER_DIAGNOSTIC_REPLICATES
        for view in RENDER_DIAGNOSTIC_REVIEW_VIEWS
        for frame in RENDER_DIAGNOSTIC_REVIEW_FRAMES
    }
    if expected_image_lookup is not None and set(expected_image_lookup) != (
        required_image_keys
    ):
        raise ValueError("render_diagnostic_review_image_lookup_invalid")
    frame_by_label = dict(
        zip(
            RENDER_DIAGNOSTIC_REVIEW_FRAME_LABELS,
            RENDER_DIAGNOSTIC_REVIEW_FRAMES,
        )
    )
    panels = panel_map.get("panels")
    if not isinstance(panels, list):
        raise ValueError("render_diagnostic_panel_map_invalid")
    for panel in panels:
        if not isinstance(panel, Mapping):
            raise ValueError("render_diagnostic_panel_record_invalid")
        sheet_key = (panel.get("replicate"), panel.get("view"))
        if (
            sheet_key not in sheet_by_key
            or panel.get("sheet_sha256")
            != sheet_by_key[sheet_key]["sha256"]
        ):
            raise ValueError("render_diagnostic_review_panel_sheet_binding_invalid")
        source_value = panel.get("source_png_path")
        source_hash = panel.get("source_png_sha256")
        if not isinstance(source_value, str) or not source_value:
            raise ValueError("render_diagnostic_review_source_image_binding_invalid")
        source_path = _reject_symlink_path_components(
            source_value,
            label="render_diagnostic_review_source",
        )
        authoritative_source = read_path(source_path)
        if (
            authoritative_source.is_symlink()
            or not authoritative_source.is_file()
            or not _is_sha256_text(source_hash)
            or _sha256_file(authoritative_source) != source_hash
        ):
            raise ValueError("render_diagnostic_review_source_image_binding_invalid")
        if expected_image_lookup is not None:
            image_key = (
                variant_by_label.get(panel.get("blinded_label")),
                panel.get("replicate"),
                panel.get("view"),
                frame_by_label.get(panel.get("frame")),
            )
            expected_source = expected_image_lookup.get(image_key)
            if expected_source is None:
                raise ValueError(
                    "render_diagnostic_review_source_image_binding_invalid"
                )
            expected_path = _reject_symlink_path_components(
                expected_source,
                label="render_diagnostic_review_expected_source",
            )
            authoritative_expected = read_path(expected_path)
            if (
                source_path != expected_path
                or authoritative_expected.is_symlink()
                or not authoritative_expected.is_file()
                or _sha256_file(authoritative_expected) != source_hash
            ):
                raise ValueError(
                    "render_diagnostic_review_source_image_binding_invalid"
                )
    from PIL import ImageDraw, ImageFont

    panel_width = 640
    panel_height = 360
    header_height = 40
    font = ImageFont.load_default()
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    for sheet_key, sheet in sheet_by_key.items():
        replicate, view = sheet_key
        bound_panels = [
            panel
            for panel in panels
            if panel.get("replicate") == replicate
            and panel.get("view") == view
        ]
        if len(bound_panels) != 12:
            raise ValueError("render_diagnostic_review_sheet_pixel_binding_invalid")
        label_by_column: dict[int, str] = {}
        for panel in bound_panels:
            column = panel.get("blinded_column")
            label = panel.get("blinded_label")
            if type(column) is not int or not isinstance(label, str):
                raise ValueError(
                    "render_diagnostic_review_sheet_pixel_binding_invalid"
                )
            existing = label_by_column.setdefault(column, label)
            if existing != label:
                raise ValueError(
                    "render_diagnostic_review_sheet_pixel_binding_invalid"
                )
        if set(label_by_column) != set(range(4)):
            raise ValueError("render_diagnostic_review_sheet_pixel_binding_invalid")
        expected_sheet = Image.new(
            "RGB",
            (panel_width * 4, header_height + panel_height * 3),
            (20, 20, 20),
        )
        draw = ImageDraw.Draw(expected_sheet)
        for column in range(4):
            draw.text(
                (column * panel_width + 12, 12),
                label_by_column[column],
                fill=(255, 255, 255),
                font=font,
            )
        panel_by_position = {
            (panel.get("frame"), panel.get("blinded_column")): panel
            for panel in bound_panels
        }
        for row, frame_label in enumerate(
            RENDER_DIAGNOSTIC_REVIEW_FRAME_LABELS
        ):
            for column in range(4):
                panel = panel_by_position.get((frame_label, column))
                if panel is None:
                    raise ValueError(
                        "render_diagnostic_review_sheet_pixel_binding_invalid"
                    )
                panel_source_path = _reject_symlink_path_components(
                    panel["source_png_path"],
                    label="render_diagnostic_review_panel_pixel_source",
                )
                with _open_image_file_snapshot(
                    read_path(panel_source_path),
                    label="render_diagnostic_review_panel_pixel_source",
                ) as source:
                    resized = source.convert("RGB").resize(
                        (panel_width, panel_height),
                        resampling,
                    )
                expected_sheet.paste(
                    resized,
                    (
                        column * panel_width,
                        header_height + row * panel_height,
                    ),
                )
        observed_sheet_path = _reject_symlink_path_components(
            sheet["path"],
            label="render_diagnostic_review_observed_sheet",
        )
        with _open_image_file_snapshot(
            read_path(observed_sheet_path),
            label="render_diagnostic_review_observed_sheet",
        ) as observed:
            observed_rgb = observed.convert("RGB")
            observed_rgb.load()
        if observed_rgb.tobytes() != expected_sheet.tobytes():
            raise ValueError(
                "render_diagnostic_review_sheet_pixel_binding_invalid"
            )
    derived = derive_render_diagnostic_visual_gates(
        panel_map=panel_map,
        blinded_label_map=label_map,
        raw_blinded_verdicts=actual["raw_blinded_verdicts"],
    )
    for field in (
        "raw_blinded_verdicts_sha256",
        "verdicts",
        "verdicts_sha256",
        "panel_gates",
        "replicate_gates",
        "configuration_gates",
        "derived_gate_sha256",
    ):
        if actual.get(field) != derived[field]:
            raise ValueError(
                f"render_diagnostic_review_derived_mismatch:{field}"
            )
    payload = {
        key: value for key, value in actual.items() if key != "review_record_sha256"
    }
    if actual["review_record_sha256"] != canonical_json_sha256_v1(payload):
        raise ValueError("render_diagnostic_review_record_hash_invalid")
    return actual


def resolve_render_diagnostic_terminal_state(
    *,
    protected_inputs_match: bool,
    all_launched_cells_successful: bool,
    matrix_status: str,
    repeat_status: str,
    configuration_gates: Mapping[str, str] | None,
    pre_freeze_sha256: str | None = None,
    post_freeze_sha256: str | None = None,
    implementation_identity_sha256: str | None = None,
    protected_input_failure_evidence_sha256: str | None = None,
    cell_status_index_sha256: str | None = None,
    matrix_validation_evidence_sha256: str | None = None,
    repeat_stability_evidence_sha256: str | None = None,
    review_record_sha256: str | None = None,
    visual_gates: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if type(protected_inputs_match) is not bool or type(
        all_launched_cells_successful
    ) is not bool:
        raise ValueError("render_diagnostic_terminal_boolean_invalid")
    if matrix_status not in {"PASS", "FAIL", "NOT_REACHED"} or repeat_status not in {
        "PASS",
        "FAIL",
        "NOT_REACHED",
    }:
        raise ValueError("render_diagnostic_terminal_status_invalid")
    gates_determinate = (
        isinstance(configuration_gates, Mapping)
        and set(configuration_gates) == set(RENDER_DIAGNOSTIC_VARIANTS)
        and all(
            value in {"PASS", "FAIL"}
            for value in configuration_gates.values()
        )
    )
    all_fail = gates_determinate and all(
        configuration_gates[variant] == "FAIL"  # type: ignore[index]
        for variant in RENDER_DIAGNOSTIC_VARIANTS
    )
    any_pass = gates_determinate and any(
        configuration_gates[variant] == "PASS"  # type: ignore[index]
        for variant in RENDER_DIAGNOSTIC_VARIANTS
    )
    configuration_gates_sha256 = (
        canonical_json_sha256_v1(dict(configuration_gates))
        if isinstance(configuration_gates, Mapping)
        else None
    )
    visual_gates_sha256 = (
        canonical_json_sha256_v1(dict(visual_gates))
        if isinstance(visual_gates, Mapping)
        else None
    )
    predicate_names = (
        "protected_input_mutation",
        "cell_runtime_or_artifact_failure",
        "matrix_incomplete_or_mixed",
        "repeat_instability",
        "visual_review_indeterminate",
        "all_configurations_reproducibly_fail",
        "at_least_one_configuration_reproducibly_passes",
    )
    predicate_values = (
        not protected_inputs_match,
        not all_launched_cells_successful,
        matrix_status != "PASS",
        repeat_status != "PASS",
        not gates_determinate,
        all_fail,
        any_pass,
    )
    try:
        winner = predicate_values.index(True)
    except ValueError as exc:
        raise ValueError("render_diagnostic_terminal_no_winning_predicate") from exc
    codes = (
        "STOP_PROTECTED_INPUT_MUTATION",
        "STOP_CELL_RUNTIME_OR_ARTIFACT_FAILURE",
        "INDETERMINATE_MATRIX_INCOMPLETE_OR_MIXED",
        "INDETERMINATE_REPEAT",
        "INDETERMINATE_VISUAL_REVIEW",
        "FAIL_NO_RENDER_SETTING_RECOVERY",
        "PASS_VISUALLY_PASSED_RENDER_DIAGNOSTIC",
    )
    base_inputs = (
        {
            "pre_freeze_sha256": pre_freeze_sha256,
            "post_freeze_sha256": post_freeze_sha256,
            "implementation_identity_sha256": (
                implementation_identity_sha256
            ),
            "protected_input_failure_evidence_sha256": (
                protected_input_failure_evidence_sha256
            ),
            "protected_inputs_match": protected_inputs_match,
        },
        {
            "cell_status_index_sha256": cell_status_index_sha256,
            "every_launched_cell_successful": all_launched_cells_successful,
        },
        {
            "matrix_validation_status": matrix_status,
            "matrix_validation_evidence_sha256": (
                matrix_validation_evidence_sha256
            ),
        },
        {
            "repeat_stability_status": repeat_status,
            "repeat_stability_evidence_sha256": (
                repeat_stability_evidence_sha256
            ),
        },
        {
            "review_record_sha256": review_record_sha256,
            "visual_gates_sha256": visual_gates_sha256,
            "visual_review_determinate": gates_determinate,
        },
        {
            "configuration_gates_sha256": configuration_gates_sha256,
            "all_configurations_fail": all_fail,
        },
        {
            "configuration_gates_sha256": configuration_gates_sha256,
            "at_least_one_configuration_passes": any_pass,
        },
    )
    evaluated_predicates = []
    for index, (name, value, inputs) in enumerate(
        zip(predicate_names, predicate_values, base_inputs)
    ):
        result = (
            "NOT_REACHED"
            if index > winner
            else ("TRUE" if value else "FALSE")
        )
        evidence_payload = {
            "schema_version": 1,
            "name": name,
            "result": result,
            "inputs": inputs if result != "NOT_REACHED" else {},
        }
        evaluated_predicates.append(
            {
                "name": name,
                "result": result,
                "evidence_sha256": canonical_json_sha256_v1(evidence_payload),
            }
        )
    return {
        "code": codes[winner],
        "precedence_index": winner + 2,
        "evaluated_predicates": evaluated_predicates,
        "evidence_sha256": canonical_json_sha256_v1(evaluated_predicates),
    }


_RENDER_DIAGNOSTIC_MATRIX_DECISION_FIELDS = frozenset(
    {
        "schema_version",
        "manifest_type",
        "experiment_id",
        "generated_at_utc",
        "terminal_state",
        "cell_status_index",
        "aggregate_cell_index",
        "anchor_sha256",
        "post_seal_sha256",
        "closure_snapshot_sha256",
        "pre_freeze_sha256",
        "post_freeze_sha256",
        "implementation_identity_sha256",
        "matrix_validation",
        "repeat_stability",
        "review_record_sha256",
        "visual_gates",
        "descriptive_contrasts",
        "operational_preference",
        "visually_passed_configuration",
        "claim_boundary",
        "matrix_decision_sha256",
    }
)


def validate_render_diagnostic_matrix_decision(
    decision: Mapping[str, Any],
    *,
    closure_root_override: str | os.PathLike[str] | None = None,
    require_live_experiment_identity: bool | None = None,
    authority_publication_staging_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(decision, Mapping) or set(decision) != set(
        _RENDER_DIAGNOSTIC_MATRIX_DECISION_FIELDS
    ):
        raise ValueError("render_diagnostic_matrix_decision_schema_invalid")
    actual = _json_native_copy(dict(decision))
    terminal = actual.get("terminal_state")
    terminal_codes = (
        "STOP_PROTECTED_INPUT_MUTATION",
        "STOP_CELL_RUNTIME_OR_ARTIFACT_FAILURE",
        "INDETERMINATE_MATRIX_INCOMPLETE_OR_MIXED",
        "INDETERMINATE_REPEAT",
        "INDETERMINATE_VISUAL_REVIEW",
        "FAIL_NO_RENDER_SETTING_RECOVERY",
        "PASS_VISUALLY_PASSED_RENDER_DIAGNOSTIC",
    )
    predicate_names = (
        "protected_input_mutation",
        "cell_runtime_or_artifact_failure",
        "matrix_incomplete_or_mixed",
        "repeat_instability",
        "visual_review_indeterminate",
        "all_configurations_reproducibly_fail",
        "at_least_one_configuration_reproducibly_passes",
    )
    if (
        actual.get("schema_version") != 1
        or actual.get("manifest_type")
        != "real_beaker_render_diagnostic_matrix_decision"
        or actual.get("experiment_id") != RENDER_DIAGNOSTIC_EXPERIMENT_ID
        or not isinstance(actual.get("generated_at_utc"), str)
        or not actual["generated_at_utc"]
        or not isinstance(terminal, Mapping)
        or set(terminal)
        != {"code", "precedence_index", "evaluated_predicates", "evidence_sha256"}
        or terminal.get("code") not in terminal_codes
        or terminal.get("precedence_index")
        != terminal_codes.index(terminal["code"]) + 2
        or not isinstance(terminal.get("evaluated_predicates"), list)
        or len(terminal["evaluated_predicates"]) != 7
        or [
            record.get("name")
            for record in terminal["evaluated_predicates"]
            if isinstance(record, Mapping)
        ]
        != list(predicate_names)
        or any(
            not isinstance(record, Mapping)
            or set(record) != {"name", "result", "evidence_sha256"}
            or record.get("result") not in {"TRUE", "FALSE", "NOT_REACHED"}
            or not _is_sha256_text(record.get("evidence_sha256"))
            for record in terminal["evaluated_predicates"]
        )
        or terminal.get("evidence_sha256")
        != canonical_json_sha256_v1(terminal["evaluated_predicates"])
        or not _is_sha256_text(actual.get("pre_freeze_sha256"))
        or not _is_sha256_text(actual.get("anchor_sha256"))
        or not _is_sha256_text(actual.get("implementation_identity_sha256"))
        or (
            actual.get("post_freeze_sha256") is not None
            and not _is_sha256_text(actual.get("post_freeze_sha256"))
        )
        or (
            actual.get("post_freeze_sha256") is None
            and terminal["code"] != "STOP_PROTECTED_INPUT_MUTATION"
        )
    ):
        raise ValueError("render_diagnostic_matrix_decision_contract_invalid")
    early_without_seal = terminal["code"] in {
        "STOP_PROTECTED_INPUT_MUTATION",
        "STOP_CELL_RUNTIME_OR_ARTIFACT_FAILURE",
    }
    closure_required = terminal["code"] in {
        "FAIL_NO_RENDER_SETTING_RECOVERY",
        "PASS_VISUALLY_PASSED_RENDER_DIAGNOSTIC",
    }
    if (
        closure_root_override is not None and not closure_required
    ) or (
        require_live_experiment_identity is not None
        and type(require_live_experiment_identity) is not bool
    ):
        raise ValueError("render_diagnostic_matrix_decision_validation_scope_invalid")
    post_seal = actual.get("post_seal_sha256")
    closure_snapshot = actual.get("closure_snapshot_sha256")
    if (
        (post_seal is not None and not _is_sha256_text(post_seal))
        or (
            closure_snapshot is not None
            and not _is_sha256_text(closure_snapshot)
        )
        or
        (early_without_seal and post_seal is not None)
        or (
            terminal["code"]
            in {
                "INDETERMINATE_REPEAT",
                "INDETERMINATE_VISUAL_REVIEW",
                "FAIL_NO_RENDER_SETTING_RECOVERY",
                "PASS_VISUALLY_PASSED_RENDER_DIAGNOSTIC",
            }
            and not _is_sha256_text(post_seal)
        )
        or (closure_required and not _is_sha256_text(closure_snapshot))
        or (not closure_required and closure_snapshot is not None)
    ):
        raise ValueError("render_diagnostic_matrix_decision_closure_invalid")
    aggregate_root = _absolute_path_without_symlink_resolution(
        RENDER_DIAGNOSTIC_AGGREGATE_ROOT
    )
    authoritative_path = lambda path: _absolute_path_without_symlink_resolution(
        path
    )
    if closure_required:
        closure_root = _reject_symlink_path_components(
            closure_root_override
            if closure_root_override is not None
            else aggregate_root / RENDER_DIAGNOSTIC_FINAL_CLOSURE_DIRNAME,
            label="render_diagnostic_decision_closure_root",
        )
        closure_manifest = validate_render_diagnostic_final_closure_snapshot(
            closure_root
        )
        if (
            closure_manifest["closure_snapshot_sha256"]
            != closure_snapshot
        ):
            raise ValueError(
                "render_diagnostic_matrix_decision_closure_hash_invalid"
            )

        def authoritative_path(path: str | os.PathLike[str]) -> Path:
            return resolve_render_diagnostic_closure_authoritative_path(
                path,
                aggregate_root=aggregate_root,
                closure_root=closure_root,
            )
    winner = terminal["precedence_index"] - 2
    expected_results = [
        "FALSE" if index < winner else ("TRUE" if index == winner else "NOT_REACHED")
        for index in range(7)
    ]
    if [
        record["result"] for record in terminal["evaluated_predicates"]
    ] != expected_results:
        raise ValueError("render_diagnostic_matrix_decision_predicate_order_invalid")
    validate_render_diagnostic_cell_status_index(actual["cell_status_index"])
    aggregate_index = actual.get("aggregate_cell_index")
    if (
        not isinstance(aggregate_index, Mapping)
        or set(aggregate_index) != {"schema_version", "experiment_id", "cells"}
        or aggregate_index.get("schema_version") != 1
        or aggregate_index.get("experiment_id")
        != RENDER_DIAGNOSTIC_EXPERIMENT_ID
        or not isinstance(aggregate_index.get("cells"), list)
        or any(
            not isinstance(record, Mapping)
            or set(record)
            != {
                "variant",
                "replicate",
                "execution_order_index",
                "manifest_path",
                "manifest_sha256",
                "implementation_identity_sha256",
                "effective_replay_look_contract_sha256",
            }
            or not _is_sha256_text(record.get("manifest_sha256"))
            or not _is_sha256_text(
                record.get("implementation_identity_sha256")
            )
            or not _is_sha256_text(
                record.get("effective_replay_look_contract_sha256")
            )
            for record in aggregate_index["cells"]
        )
    ):
        raise ValueError("render_diagnostic_matrix_decision_cell_index_invalid")
    successful_status_slots = {
        (record["variant"], record["replicate"]): record
        for record in actual["cell_status_index"]["cells"]
        if record["status"] == "SUCCESS"
    }
    expected_index_order = sorted(
        successful_status_slots,
        key=lambda key: (
            RENDER_DIAGNOSTIC_VARIANTS.index(key[0]),
            RENDER_DIAGNOSTIC_REPLICATES.index(key[1]),
        ),
    )
    actual_index_order = [
        (record["variant"], record["replicate"])
        for record in aggregate_index["cells"]
    ]
    if actual_index_order != expected_index_order:
        raise ValueError("render_diagnostic_matrix_decision_cell_index_order_invalid")
    for record in aggregate_index["cells"]:
        slot_status = successful_status_slots[
            (record["variant"], record["replicate"])
        ]
        expected_manifest = (
            aggregate_root
            / "cells"
            / f"{record['replicate']}_{record['execution_order_index']}_{record['variant']}"
            / "replay_manifest.json"
        )
        manifest_path = _absolute_path_without_symlink_resolution(
            record["manifest_path"]
        )
        authoritative_manifest = authoritative_path(manifest_path)
        if (
            record["execution_order_index"]
            != slot_status["execution_order_index"]
            or manifest_path != expected_manifest
            or not authoritative_manifest.is_file()
            or authoritative_manifest.is_symlink()
            or _sha256_file(authoritative_manifest)
            != record["manifest_sha256"]
            or record["implementation_identity_sha256"]
            != actual["implementation_identity_sha256"]
        ):
            raise ValueError(
                "render_diagnostic_matrix_decision_cell_index_binding_invalid"
            )
    matrix = actual.get("matrix_validation")
    repeat = actual.get("repeat_stability")
    if (
        not isinstance(matrix, Mapping)
        or set(matrix) != {"status", "evidence_sha256"}
        or matrix.get("status") not in {"PASS", "FAIL", "NOT_REACHED"}
        or not _is_sha256_text(matrix.get("evidence_sha256"))
        or not isinstance(repeat, Mapping)
        or set(repeat) != {"status", "evidence_sha256"}
        or repeat.get("status") not in {"PASS", "FAIL", "NOT_REACHED"}
        or not _is_sha256_text(repeat.get("evidence_sha256"))
    ):
        raise ValueError("render_diagnostic_matrix_decision_evidence_invalid")
    expected_statuses = {
        "STOP_PROTECTED_INPUT_MUTATION": ("NOT_REACHED", "NOT_REACHED"),
        "STOP_CELL_RUNTIME_OR_ARTIFACT_FAILURE": (
            "NOT_REACHED",
            "NOT_REACHED",
        ),
        "INDETERMINATE_MATRIX_INCOMPLETE_OR_MIXED": ("FAIL", "NOT_REACHED"),
        "INDETERMINATE_REPEAT": ("PASS", "FAIL"),
        "INDETERMINATE_VISUAL_REVIEW": ("PASS", "PASS"),
        "FAIL_NO_RENDER_SETTING_RECOVERY": ("PASS", "PASS"),
        "PASS_VISUALLY_PASSED_RENDER_DIAGNOSTIC": ("PASS", "PASS"),
    }
    if (matrix["status"], repeat["status"]) != expected_statuses[
        terminal["code"]
    ]:
        raise ValueError("render_diagnostic_matrix_decision_status_invalid")
    evidence_root = aggregate_root / "evidence"
    bound_anchor = validate_render_diagnostic_experiment_anchor(
        _load_json_object(
            authoritative_path(
                evidence_root.parent / RENDER_DIAGNOSTIC_ANCHOR_BASENAME
            ),
            label="decision_experiment_anchor",
        ),
        expected_root=evidence_root.parent,
        expected_lock_path=_render_diagnostic_lock_path(),
        verify_live_identity=(
            bool(require_live_experiment_identity)
            if require_live_experiment_identity is not None
            else not closure_required
        ),
    )
    if bound_anchor["anchor_sha256"] != actual["anchor_sha256"]:
        raise ValueError("render_diagnostic_matrix_decision_anchor_invalid")
    bound_implementation = None
    try:
        if closure_required:
            bound_implementation = validate_matrix_implementation_identity_v1(
                _load_json_object(
                    authoritative_path(
                        RENDER_DIAGNOSTIC_IMPLEMENTATION_FREEZE_PATH
                    ),
                    label="decision_implementation_identity",
                )
            )
        else:
            bound_implementation = (
                load_and_verify_frozen_matrix_implementation_identity()
            )
        if (
            bound_implementation["implementation_identity_sha256"]
            != actual["implementation_identity_sha256"]
        ):
            raise ValueError("decision_implementation_identity_mismatch")
    except (OSError, TypeError, ValueError):
        if terminal["code"] != "STOP_PROTECTED_INPUT_MUTATION":
            raise
        bound_implementation = None
    launch_chain = validate_render_diagnostic_launch_chain(
        aggregate_root=aggregate_root,
        anchor_sha256=bound_anchor["anchor_sha256"],
        expected_implementation_identity_sha256=actual[
            "implementation_identity_sha256"
        ],
        expected_pre_freeze_sha256=actual["pre_freeze_sha256"],
        cell_status_index=actual["cell_status_index"],
        require_artifact_closure=bound_implementation is not None,
        expected_implementation_identity=bound_implementation,
        authoritative_path_resolver=(
            authoritative_path if closure_required else None
        ),
    )
    closures_by_root = {
        closure["cell_root"]: closure
        for closure in launch_chain["artifact_closures"]
    }
    if bound_implementation is not None:
        for record in aggregate_index["cells"]:
            closure = closures_by_root.get(
                str(Path(record["manifest_path"]).parent)
            )
            if (
                closure is None
                or closure["replay_manifest_sha256"]
                != record["manifest_sha256"]
            ):
                raise ValueError(
                    "render_diagnostic_matrix_decision_cell_closure_binding_invalid"
                )
    if post_seal is not None:
        bound_pre_snapshot = _load_json_object(
            authoritative_path(RENDER_DIAGNOSTIC_PRE_FREEZE_PATH),
            label="decision_pre_freeze",
        )
        bound_post_envelope = (
            validate_render_diagnostic_post_freeze_envelope(
                _load_json_object(
                    authoritative_path(RENDER_DIAGNOSTIC_POST_FREEZE_PATH),
                    label="decision_post_freeze",
                ),
                expected_registry_snapshot=bound_pre_snapshot,
                expected_anchor_sha256=bound_anchor["anchor_sha256"],
                expected_cell_status_index=actual["cell_status_index"],
            )
        )
        bound_seal = validate_render_diagnostic_successful_post_seal(
            _load_json_object(
                authoritative_path(
                    aggregate_root / RENDER_DIAGNOSTIC_POST_SEAL_BASENAME
                ),
                label="decision_post_seal",
            ),
            anchor=bound_anchor,
            post_freeze_envelope=bound_post_envelope,
            cell_status_index=actual["cell_status_index"],
            validated_launch_chain=launch_chain,
        )
        if (
            bound_post_envelope["post_freeze_sha256"]
            != actual["post_freeze_sha256"]
            or bound_seal["post_seal_sha256"] != post_seal
        ):
            raise ValueError(
                "render_diagnostic_matrix_decision_post_seal_invalid"
            )
    status_evidence = _load_json_object(
        authoritative_path(evidence_root / "cell_status_index.json"),
        label="decision_cell_status_index",
    )
    matrix_evidence = validate_render_diagnostic_matrix_validation_evidence(
        _load_json_object(
            authoritative_path(evidence_root / "matrix_validation.json"),
            label="decision_matrix_validation",
        )
    )
    repeat_evidence = validate_render_diagnostic_repeat_stability_evidence(
        _load_json_object(
            authoritative_path(evidence_root / "repeat_stability.json"),
            label="decision_repeat_stability",
        )
    )
    matrix_hash_payload = {
        key: value
        for key, value in matrix_evidence.items()
        if key != "matrix_validation_evidence_sha256"
    }
    repeat_hash_payload = {
        key: value
        for key, value in repeat_evidence.items()
        if key != "repeat_stability_evidence_sha256"
    }
    if (
        status_evidence != actual["cell_status_index"]
        or canonical_json_sha256_v1(status_evidence)
        != canonical_json_sha256_v1(actual["cell_status_index"])
        or matrix_evidence.get("status") != matrix["status"]
        or matrix_evidence.get("matrix_validation_evidence_sha256")
        != matrix["evidence_sha256"]
        or matrix["evidence_sha256"]
        != canonical_json_sha256_v1(matrix_hash_payload)
        or repeat_evidence.get("status") != repeat["status"]
        or repeat_evidence.get("repeat_stability_evidence_sha256")
        != repeat["evidence_sha256"]
        or repeat["evidence_sha256"]
        != canonical_json_sha256_v1(repeat_hash_payload)
    ):
        raise ValueError("render_diagnostic_matrix_decision_evidence_binding_invalid")
    if (
        not closure_required
        and terminal["code"]
        in {
            "INDETERMINATE_MATRIX_INCOMPLETE_OR_MIXED",
            "INDETERMINATE_REPEAT",
            "INDETERMINATE_VISUAL_REVIEW",
        }
    ):
        rebuilt_machine = build_render_diagnostic_machine_verification(
            aggregate_root,
            expected_implementation_identity=bound_implementation,
            expected_pre_freeze_sha256=actual["pre_freeze_sha256"],
            authority_publication_staging_root=(
                authority_publication_staging_root
            ),
        )
        if (
            rebuilt_machine["cell_status_index"] != status_evidence
            or rebuilt_machine["matrix_validation"] != matrix_evidence
            or rebuilt_machine["repeat_stability"] != repeat_evidence
        ):
            raise ValueError(
                "render_diagnostic_matrix_decision_machine_rebuild_invalid"
            )
    if closure_required:
        rebuilt_matrix = validate_render_diagnostic_matrix_closure(
            launch_chain["successful_cell_evidence"]
        )
        if rebuilt_matrix != matrix_evidence:
            raise ValueError(
                "render_diagnostic_matrix_decision_snapshot_matrix_rebuild_invalid"
            )
        rebuilt_image_lookup: dict[tuple[str, str, str, int], Path] = {}
        for closure in launch_chain["artifact_closures"]:
            cell = closure["cell_evidence"]
            for image_record in closure["sidecars"]["media_index"]["images"]:
                key = (
                    cell["variant"],
                    cell["replicate"],
                    image_record["camera"],
                    image_record["frame"],
                )
                if (
                    key[2] in RENDER_DIAGNOSTIC_REVIEW_VIEWS
                    and key[3] in RENDER_DIAGNOSTIC_REVIEW_FRAMES
                ):
                    resolved = authoritative_path(image_record["path"])
                    if key in rebuilt_image_lookup:
                        raise ValueError(
                            "render_diagnostic_matrix_decision_snapshot_image_duplicate"
                        )
                    rebuilt_image_lookup[key] = resolved
        expected_image_keys = {
            (variant, replicate, view, frame)
            for variant in RENDER_DIAGNOSTIC_VARIANTS
            for replicate in RENDER_DIAGNOSTIC_REPLICATES
            for view in RENDER_DIAGNOSTIC_REVIEW_VIEWS
            for frame in RENDER_DIAGNOSTIC_REVIEW_FRAMES
        }
        if set(rebuilt_image_lookup) != expected_image_keys:
            raise ValueError(
                "render_diagnostic_matrix_decision_snapshot_image_set_invalid"
            )
        rebuilt_repeat = compute_render_diagnostic_repeat_stability(
            rebuilt_image_lookup
        )
        if rebuilt_repeat != repeat_evidence:
            raise ValueError(
                "render_diagnostic_matrix_decision_snapshot_repeat_rebuild_invalid"
            )
    expected_preference = [
        {
            "variant": variant,
            "score": [
                int(RENDER_DIAGNOSTIC_VARIANT_SETTINGS[variant][0]),
                RENDER_DIAGNOSTIC_VARIANT_SETTINGS[variant][1],
            ],
        }
        for variant in RENDER_DIAGNOSTIC_VARIANTS
    ]
    expected_blocked = sorted(
        [
            "causal_renderer_consumption_claim",
            "colleague_delivery",
            "exporter_admission",
            "formal_look_selection",
            "package_localization",
        ]
    )
    claim = actual.get("claim_boundary")
    interpretation_allowed = terminal["code"] in {
        "FAIL_NO_RENDER_SETTING_RECOVERY",
        "PASS_VISUALLY_PASSED_RENDER_DIAGNOSTIC",
    }
    if not interpretation_allowed and (
        actual.get("descriptive_contrasts") is not None
        or actual.get("visually_passed_configuration") is not None
    ):
        raise ValueError(
            "render_diagnostic_matrix_decision_noninterpretive_fields_invalid"
        )
    if (actual.get("review_record_sha256") is None) != (
        actual.get("visual_gates") is None
    ):
        raise ValueError(
            "render_diagnostic_matrix_decision_review_nullability_invalid"
        )
    expected_allowed = (
        sorted(
            [
                "observed_pixel_association_under_tested_isaacsim41_configuration",
                "next_reviewed_planning_action",
            ]
        )
        if interpretation_allowed
        else []
    )
    if (
        actual.get("operational_preference") != expected_preference
        or not isinstance(claim, Mapping)
        or set(claim) != {"allowed", "blocked"}
        or claim.get("allowed") != expected_allowed
        or claim.get("blocked") != expected_blocked
        or (
            actual.get("review_record_sha256") is not None
            and not _is_sha256_text(actual.get("review_record_sha256"))
        )
        or (
            interpretation_allowed
            and (
                actual.get("review_record_sha256") is None
                or not isinstance(actual.get("visual_gates"), Mapping)
                or not isinstance(actual.get("descriptive_contrasts"), list)
            )
        )
    ):
        raise ValueError("render_diagnostic_matrix_decision_claim_invalid")
    visual_gates = actual.get("visual_gates")
    configuration_gates = None
    if visual_gates is not None:
        if not isinstance(visual_gates, Mapping) or set(visual_gates) != {
            "panel_gates",
            "replicate_gates",
            "configuration_gates",
        }:
            raise ValueError("render_diagnostic_matrix_decision_visual_gates_invalid")
        configuration_gates = visual_gates["configuration_gates"]
        replicate_gates = visual_gates["replicate_gates"]
        panel_gates = visual_gates["panel_gates"]
        if (
            not isinstance(configuration_gates, Mapping)
            or set(configuration_gates) != set(RENDER_DIAGNOSTIC_VARIANTS)
            or any(
                value not in {"PASS", "FAIL", "INDETERMINATE"}
                for value in configuration_gates.values()
            )
            or not isinstance(replicate_gates, Mapping)
            or set(replicate_gates) != set(RENDER_DIAGNOSTIC_VARIANTS)
            or any(
                not isinstance(replicate_gates[variant], Mapping)
                or set(replicate_gates[variant])
                != set(RENDER_DIAGNOSTIC_REPLICATES)
                or any(
                    value not in {"PASS", "FAIL", "INDETERMINATE"}
                    for value in replicate_gates[variant].values()
                )
                for variant in RENDER_DIAGNOSTIC_VARIANTS
            )
            or not isinstance(panel_gates, Mapping)
            or set(panel_gates) != set(RENDER_DIAGNOSTIC_VARIANTS)
            or any(
                not isinstance(panel_gates[variant], Mapping)
                or set(panel_gates[variant])
                != set(RENDER_DIAGNOSTIC_REPLICATES)
                for variant in RENDER_DIAGNOSTIC_VARIANTS
            )
        ):
            raise ValueError("render_diagnostic_matrix_decision_visual_gates_invalid")
        for variant in RENDER_DIAGNOSTIC_VARIANTS:
            for replicate in RENDER_DIAGNOSTIC_REPLICATES:
                views = panel_gates[variant][replicate]
                if (
                    not isinstance(views, Mapping)
                    or set(views) != set(RENDER_DIAGNOSTIC_REVIEW_VIEWS)
                    or any(
                        not isinstance(views[view], Mapping)
                        or set(views[view])
                        != set(RENDER_DIAGNOSTIC_REVIEW_FRAME_LABELS)
                        or any(
                            gate not in {"PASS", "FAIL", "INDETERMINATE"}
                            for gate in views[view].values()
                        )
                        for view in RENDER_DIAGNOSTIC_REVIEW_VIEWS
                    )
                ):
                    raise ValueError(
                        "render_diagnostic_matrix_decision_visual_gates_invalid"
                    )
    rebuilt_contrasts = None
    bound_review = None
    if actual.get("review_record_sha256") is not None:
        review_path = aggregate_root / "review" / "review_record.json"
        bound_review = validate_render_diagnostic_review_record(
            _load_json_object(
                authoritative_path(review_path),
                label="decision_review_record",
            ),
            expected_review_root=aggregate_root / "review",
            authoritative_path_resolver=(
                authoritative_path if closure_required else None
            ),
        )
        if (
            bound_review["review_record_sha256"]
            != actual["review_record_sha256"]
            or bound_review["panel_gates"] != visual_gates["panel_gates"]
            or bound_review["replicate_gates"]
            != visual_gates["replicate_gates"]
            or bound_review["configuration_gates"]
            != visual_gates["configuration_gates"]
        ):
            raise ValueError(
                "render_diagnostic_matrix_decision_review_binding_invalid"
            )
    if interpretation_allowed:
        if bound_review is None:
            raise ValueError(
                "render_diagnostic_matrix_decision_review_binding_invalid"
            )
        panel_map = _load_json_object(
            authoritative_path(bound_review["panel_map_path"]),
            label="decision_review_panel_map",
        )
        label_map = _load_json_object(
            authoritative_path(bound_review["blinded_label_map_path"]),
            label="decision_review_label_map",
        )
        variant_by_label = {
            record["blinded_label"]: record["variant"]
            for record in label_map["labels"]
        }
        frame_by_label = dict(
            zip(
                RENDER_DIAGNOSTIC_REVIEW_FRAME_LABELS,
                RENDER_DIAGNOSTIC_REVIEW_FRAMES,
            )
        )
        contrast_lookup = {}
        for panel in panel_map["panels"]:
            key = (
                variant_by_label[panel["blinded_label"]],
                panel["replicate"],
                panel["view"],
                frame_by_label[panel["frame"]],
            )
            source_path = authoritative_path(panel["source_png_path"])
            existing = contrast_lookup.setdefault(key, source_path)
            if existing != source_path:
                raise ValueError(
                    "render_diagnostic_matrix_decision_review_source_duplicate"
                )
        rebuilt_contrasts = _render_diagnostic_descriptive_contrasts(
            contrast_lookup,
            configuration_gates,
        )

    contrasts = actual.get("descriptive_contrasts")
    if interpretation_allowed:
        expected_contrast_names = {
            f"{metric}__{contrast}"
            for metric in (
                "visual_pass_indicator",
                "full_rgb_mean_u8",
                "cyan_channel_excess_u8",
                "rec709_luminance_u8",
            )
            for contrast in (
                "AO_ASSOCIATION",
                "RT_ASSOCIATION",
                "AO_RT_INTERACTION",
            )
        }
        if (
            not isinstance(contrasts, list)
            or len(contrasts) != 12
            or {record.get("name") for record in contrasts} != expected_contrast_names
            or any(
                not isinstance(record, Mapping)
                or set(record) != {"name", "metric", "cell_values", "estimate"}
                or not isinstance(record.get("cell_values"), Mapping)
                or set(record["cell_values"]) != set(RENDER_DIAGNOSTIC_VARIANTS)
                or type(record.get("estimate")) not in (int, float)
                or type(record.get("estimate")) is bool
                or not math.isfinite(float(record["estimate"]))
                for record in contrasts
            )
        ):
            raise ValueError("render_diagnostic_matrix_decision_contrasts_invalid")
        if contrasts != rebuilt_contrasts:
            raise ValueError(
                "render_diagnostic_matrix_decision_contrasts_mismatch"
            )
    selected = actual.get("visually_passed_configuration")
    if terminal["code"] == "PASS_VISUALLY_PASSED_RENDER_DIAGNOSTIC":
        expected_selected = next(
            variant
            for variant in RENDER_DIAGNOSTIC_VARIANTS
            if configuration_gates[variant] == "PASS"
        )
        if (
            selected != expected_selected
            or configuration_gates is None
            or configuration_gates[selected] != "PASS"
        ):
            raise ValueError("render_diagnostic_matrix_decision_selection_invalid")
    elif selected is not None:
        raise ValueError("render_diagnostic_matrix_decision_selection_invalid")
    protected_failure_hash = None
    protected_failure_path = evidence_root / "protected_input_failure.json"
    if terminal["code"] == "STOP_PROTECTED_INPUT_MUTATION":
        protected_failure = validate_render_diagnostic_protected_input_failure(
            _load_json_object(
                protected_failure_path,
                label="decision_protected_input_failure",
            )
        )
        protected_failure_hash = protected_failure[
            "protected_input_failure_evidence_sha256"
        ]
    rebuilt_terminal = resolve_render_diagnostic_terminal_state(
        protected_inputs_match=(
            terminal["code"] != "STOP_PROTECTED_INPUT_MUTATION"
        ),
        all_launched_cells_successful=(
            terminal["code"]
            != "STOP_CELL_RUNTIME_OR_ARTIFACT_FAILURE"
        ),
        matrix_status=matrix["status"],
        repeat_status=repeat["status"],
        configuration_gates=configuration_gates,
        pre_freeze_sha256=actual["pre_freeze_sha256"],
        post_freeze_sha256=actual["post_freeze_sha256"],
        implementation_identity_sha256=actual[
            "implementation_identity_sha256"
        ],
        protected_input_failure_evidence_sha256=protected_failure_hash,
        cell_status_index_sha256=canonical_json_sha256_v1(
            actual["cell_status_index"]
        ),
        matrix_validation_evidence_sha256=matrix["evidence_sha256"],
        repeat_stability_evidence_sha256=repeat["evidence_sha256"],
        review_record_sha256=actual["review_record_sha256"],
        visual_gates=visual_gates,
    )
    if terminal != rebuilt_terminal:
        raise ValueError("render_diagnostic_matrix_decision_terminal_mismatch")
    hash_payload = {
        key: value
        for key, value in actual.items()
        if key not in {"generated_at_utc", "matrix_decision_sha256"}
    }
    if actual.get("matrix_decision_sha256") != canonical_json_sha256_v1(
        hash_payload
    ):
        raise ValueError("render_diagnostic_matrix_decision_hash_invalid")
    return actual


def _effective_look_contract_from_args(args: argparse.Namespace) -> dict[str, Any]:
    render_diagnostic_identity = validate_render_diagnostic_cell_scope(args)
    variant = str(
        getattr(
            args,
            "visual_prototype_lighting_variant",
            LIGHTING_VARIANT_C_CONTROL,
        )
    )
    if variant == LIGHTING_VARIANT_B:
        if not bool(
            getattr(args, "visual_prototype_display_fill_only", False)
        ):
            raise ValueError("b_lighting_requires_visual_prototype")
        if _candidate_ids_from_args(args) != (
            DISPLAY_FILL_VISUAL_PROTOTYPE_CANDIDATE_IDS
        ):
            raise ValueError("b_lighting_requires_visual_prototype")
    return build_effective_replay_look_contract(
        variant,
        render_diagnostic_variant_id=(
            render_diagnostic_identity["render_diagnostic_variant_id"]
            if render_diagnostic_identity is not None
            else None
        ),
    )


def _validated_effective_look_contract_for_args(
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Use a frozen preflight contract when present and reject CLI drift."""
    resolved = _effective_look_contract_from_args(args)
    frozen = getattr(args, "_effective_replay_look_contract", None)
    if frozen is None:
        return resolved
    validated = validate_effective_replay_look_contract(frozen)
    if validated != resolved:
        raise ValueError("effective_replay_look_contract_cli_drift")
    return validated


def validate_replay_effective_look_consistency(
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Require the top-level and every candidate to bind one exact look."""
    if not isinstance(manifest, Mapping):
        raise ValueError("replay_effective_look_manifest_missing")
    top_look = validate_effective_replay_look_contract(
        manifest.get("effective_replay_look_contract")  # type: ignore[arg-type]
    )
    top_hash = top_look["effective_replay_look_contract_sha256"]
    render_diagnostic_variant = top_look["render_diagnostic_variant_id"]
    projection_hash = (
        build_effective_replay_look_matrix_projection(top_look)[
            "canonical_json_utf8_sha256"
        ]
        if render_diagnostic_variant is not None
        else None
    )
    if (
        manifest.get("lighting_variant_id") != top_look["lighting_variant_id"]
        or manifest.get("render_diagnostic_variant_id")
        != render_diagnostic_variant
        or manifest.get("effective_replay_look_matrix_projection_sha256")
        != projection_hash
        or manifest.get("effective_replay_look_contract_sha256") != top_hash
    ):
        raise ValueError("replay_effective_look_top_mismatch")
    candidates = manifest.get("candidate_manifests")
    if not isinstance(candidates, Mapping) or not candidates:
        raise ValueError("replay_effective_look_candidates_missing")
    for candidate_id, candidate in candidates.items():
        if not isinstance(candidate, Mapping):
            raise ValueError(
                f"replay_effective_look_candidate_mismatch:{candidate_id}"
            )
        if (
            candidate.get("lighting_variant_id")
            != top_look["lighting_variant_id"]
            or candidate.get("render_diagnostic_variant_id")
            != render_diagnostic_variant
            or candidate.get("effective_replay_look_matrix_projection_sha256")
            != projection_hash
            or candidate.get("effective_replay_look_contract") != top_look
            or candidate.get("effective_replay_look_contract_sha256") != top_hash
        ):
            raise ValueError(
                f"replay_effective_look_candidate_mismatch:{candidate_id}"
            )
    return {
        "validated": True,
        "lighting_variant_id": top_look["lighting_variant_id"],
        "render_diagnostic_variant_id": render_diagnostic_variant,
        "effective_replay_look_matrix_projection_sha256": projection_hash,
        "effective_replay_look_contract_sha256": top_hash,
        "candidate_count": len(candidates),
    }


def _expected_authored_effective_lighting(
    effective_look_contract: Mapping[str, Any],
) -> dict[str, Any]:
    look = validate_effective_replay_look_contract(effective_look_contract)
    lighting = look["effective_lighting"]
    expected = {
        "mode": str(lighting["mode"]),
        "key_intensity": float(lighting["key_intensity"]),
        "dome_intensity": float(lighting["dome_intensity"]),
        "rotate_xyz": [float(value) for value in lighting["key_rotate_xyz"]],
        "lighting_contract_hash": str(lighting["lighting_contract_hash"]),
    }
    for key in (
        "key_exposure",
        "dome_exposure",
        "key_color_temperature",
        "dome_color_temperature",
    ):
        if key in lighting:
            expected[key] = float(lighting[key])
    return expected


def validate_authored_effective_replay_lighting(
    authored_lighting: Mapping[str, Any],
    effective_look_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify the runtime authoring result against the frozen lighting block."""
    if not isinstance(authored_lighting, Mapping):
        raise ValueError("authored_effective_lighting_mismatch:not_object")
    look = validate_effective_replay_look_contract(effective_look_contract)
    expected = _expected_authored_effective_lighting(look)
    actual = {key: _json_native_copy(authored_lighting.get(key)) for key in expected}
    if actual != expected:
        raise ValueError(
            "authored_effective_lighting_mismatch:"
            f"actual={json.dumps(actual, sort_keys=True)}:"
            f"expected={json.dumps(expected, sort_keys=True)}"
        )
    return {
        "validated": True,
        "lighting_variant_id": look["lighting_variant_id"],
        "expected_authored_lighting": expected,
        "authored_lighting_sha256": _json_sha256(actual),
    }


def validate_authored_effective_replay_material(
    authored_material: Mapping[str, Any],
    effective_look_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify that the runtime material retained the frozen A18 values."""
    if not isinstance(authored_material, Mapping):
        raise ValueError("authored_effective_material_mismatch:not_object")
    look = validate_effective_replay_look_contract(effective_look_contract)
    material = look["liquid_material"]
    expected = {
        "preferred_backend": material["backend"],
        "sub_identifier": material["sub_identifier"],
        "material_hash": material["material_hash"],
        "glass_color": material["glass_color"],
        "reflection_color": material["reflection_color"],
    }
    actual = {
        key: _json_native_copy(authored_material.get(key)) for key in expected
    }
    if actual != expected:
        raise ValueError(
            "authored_effective_material_mismatch:"
            f"actual={json.dumps(actual, sort_keys=True)}:"
            f"expected={json.dumps(expected, sort_keys=True)}"
        )
    return {
        "validated": True,
        "material_hash": material["material_hash"],
        "authored_material_sha256": _json_sha256(actual),
    }


def _effective_replay_registry_records(
    effective_look_contract: Mapping[str, Any],
) -> list[dict[str, Any]]:
    look = validate_effective_replay_look_contract(effective_look_contract)
    render = look["render_settings"]
    values = (
        (
            REPLAY_AMBIENT_OCCLUSION_SETTING_PATH,
            "bool",
            render["ambient_occlusion_enabled"],
        ),
        (
            REPLAY_AMBIENT_OCCLUSION_RAY_LENGTH_SETTING_PATH,
            "float",
            render["ambient_occlusion_ray_length"],
        ),
        (
            REPLAY_AMBIENT_OCCLUSION_MIN_SAMPLES_SETTING_PATH,
            "int",
            render["ambient_occlusion_min_samples"],
        ),
        (
            REPLAY_AMBIENT_OCCLUSION_MAX_SAMPLES_SETTING_PATH,
            "int",
            render["ambient_occlusion_max_samples"],
        ),
        (
            REPLAY_AMBIENT_OCCLUSION_DENOISER_MODE_SETTING_PATH,
            "int",
            render["ambient_occlusion_denoiser_mode"],
        ),
        (
            REPLAY_SHADOWS_SETTING_PATH,
            "bool",
            render["shadows_enabled"],
        ),
        (
            REPLAY_SHADOW_SAMPLE_COUNT_SETTING_PATH,
            "int",
            render["shadow_sample_count"],
        ),
        (
            REPLAY_REFRACTION_SETTING_PATH,
            "int",
            render["max_refraction_bounces"],
        ),
    )
    return [
        {"path": path, "value_type": value_type, "value": value}
        for path, value_type, value in sorted(values, key=lambda item: item[0])
    ]


def build_effective_replay_kit_startup_arguments(
    effective_look_contract: Mapping[str, Any],
) -> list[str]:
    """Build the exact Kit launch-order registry arguments for one look."""
    look = validate_effective_replay_look_contract(effective_look_contract)
    render = look["render_settings"]
    ordered = (
        (
            REPLAY_AMBIENT_OCCLUSION_SETTING_PATH,
            render["ambient_occlusion_enabled"],
        ),
        (
            REPLAY_AMBIENT_OCCLUSION_RAY_LENGTH_SETTING_PATH,
            render["ambient_occlusion_ray_length"],
        ),
        (
            REPLAY_AMBIENT_OCCLUSION_MIN_SAMPLES_SETTING_PATH,
            render["ambient_occlusion_min_samples"],
        ),
        (
            REPLAY_AMBIENT_OCCLUSION_MAX_SAMPLES_SETTING_PATH,
            render["ambient_occlusion_max_samples"],
        ),
        (
            REPLAY_AMBIENT_OCCLUSION_DENOISER_MODE_SETTING_PATH,
            render["ambient_occlusion_denoiser_mode"],
        ),
        (REPLAY_SHADOWS_SETTING_PATH, render["shadows_enabled"]),
        (
            REPLAY_SHADOW_SAMPLE_COUNT_SETTING_PATH,
            render["shadow_sample_count"],
        ),
        (REPLAY_REFRACTION_SETTING_PATH, render["max_refraction_bounces"]),
    )

    def format_value(value: Any) -> str:
        if type(value) is bool:
            return "true" if value else "false"
        if type(value) is float:
            if not math.isfinite(value):
                raise ValueError("render_settings_startup_value_nonfinite")
            return str(value)
        if type(value) is int:
            return str(value)
        raise ValueError("render_settings_startup_value_type_invalid")

    return [f"--{path}={format_value(value)}" for path, value in ordered]


def install_effective_replay_kit_startup_arguments(
    argv: list[str],
    effective_look_contract: Mapping[str, Any],
) -> list[str]:
    """Install canonical Kit arguments once before SimulationApp construction."""
    startup_arguments = build_effective_replay_kit_startup_arguments(
        effective_look_contract
    )
    duplicates = [argument for argument in startup_arguments if argument in argv]
    if duplicates:
        raise ValueError(
            "kit_startup_argument_already_present:" + ",".join(duplicates)
        )
    argv.extend(startup_arguments)
    return startup_arguments


def build_render_diagnostic_mdl_startup_arguments(
    closure: Mapping[str, Any],
    *,
    authoritative_path_resolver: Any | None = None,
) -> dict[str, Any]:
    root = _absolute_path_without_symlink_resolution(
        str(closure.get("closure_root", ""))
    )
    base = _absolute_path_without_symlink_resolution(
        str(closure.get("closure_base_dir", ""))
    )
    module_parent = _absolute_path_without_symlink_resolution(
        str(closure.get("closure_omnisurface_module_dir", ""))
    ).parent
    checked_base = (
        _absolute_path_without_symlink_resolution(
            authoritative_path_resolver(base)
        )
        if authoritative_path_resolver is not None
        else base
    )
    checked_module_parent = (
        _absolute_path_without_symlink_resolution(
            authoritative_path_resolver(module_parent)
        )
        if authoritative_path_resolver is not None
        else module_parent
    )
    if (
        base != root / "Base"
        or module_parent != root / "mdl"
        or not checked_base.is_dir()
        or not checked_module_parent.is_dir()
    ):
        raise ValueError("render_diagnostic_mdl_closure_paths_invalid")
    paths = [str(module_parent), str(base)]
    encoded_paths = json.dumps(paths, separators=(",", ":"))
    arguments = [
        f"--/app/mdl/additionalUserPaths={encoded_paths}",
        f"--/materialConfig/searchPaths/custom={encoded_paths}",
        f"--/renderer/mdl/searchPaths/custom={';'.join(paths)}",
    ]
    return {
        "schema_version": 1,
        "search_paths": paths,
        "startup_arguments": arguments,
        "closure_paths_precede_default_paths": True,
    }


def install_render_diagnostic_mdl_startup_arguments(
    argv: list[str],
    closure: Mapping[str, Any],
) -> dict[str, Any]:
    contract = build_render_diagnostic_mdl_startup_arguments(closure)
    setting_prefixes = [argument.split("=", 1)[0] + "=" for argument in contract["startup_arguments"]]
    if any(
        any(existing.startswith(prefix) for prefix in setting_prefixes)
        for existing in argv
    ):
        raise ValueError("mdl_startup_argument_already_present")
    argv.extend(contract["startup_arguments"])
    return contract


def validate_render_diagnostic_mdl_search_path_readback(
    settings: Any,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    expected = list(contract.get("search_paths") or [])
    additional = list(settings.get("/app/mdl/additionalUserPaths") or [])
    material_custom = list(
        settings.get("/materialConfig/searchPaths/custom") or []
    )
    renderer_custom = settings.get("/renderer/mdl/searchPaths/custom")
    renderer_paths = (
        renderer_custom.split(";")
        if isinstance(renderer_custom, str)
        else list(renderer_custom or [])
    )
    if (
        not expected
        or additional[: len(expected)] != expected
        or material_custom[: len(expected)] != expected
        or renderer_paths[: len(expected)] != expected
    ):
        raise RuntimeError("render_diagnostic_mdl_search_path_readback_mismatch")
    return {
        **_json_native_copy(dict(contract)),
        "additional_user_paths_readback": additional,
        "material_custom_paths_readback": material_custom,
        "renderer_custom_paths_readback": renderer_paths,
        "readback_verified": True,
    }


def render_diagnostic_lifecycle_contract() -> dict[str, bool]:
    return {
        "standalone_final_evidence_authority": False,
        "exporter_admitted": False,
        "visual_selection_eligible": False,
        "formal_scope": False,
        "delivery_ready": False,
    }


def replay_success_classification(
    effective_look_contract: Mapping[str, Any],
) -> str:
    look = validate_effective_replay_look_contract(effective_look_contract)
    if look["render_diagnostic_variant_id"] is not None:
        return "DIAGNOSTIC_RENDER_COMPLETE_PENDING_VISUAL_REVIEW"
    return "RENDER_COMPLETE_PENDING_VISUAL_REVIEW"


def _set_render_registry_value(
    settings: Any,
    *,
    path: str,
    value_type: str,
    value: Any,
) -> None:
    setter = getattr(settings, f"set_{value_type}", None)
    if callable(setter):
        setter(path, value)
        return
    generic = getattr(settings, "set", None)
    if not callable(generic):
        raise RuntimeError(f"render_settings_setter_missing:{path}:{value_type}")
    generic(path, value)


def _validate_render_registry_readback(
    *,
    record: Mapping[str, Any],
    actual: Any,
) -> dict[str, Any]:
    path = str(record["path"])
    value_type = str(record["value_type"])
    expected = record["value"]
    if actual is None:
        raise RuntimeError(f"render_settings_readback_missing:{path}")
    type_valid = (
        (value_type == "bool" and type(actual) is bool)
        or (value_type == "int" and type(actual) is int)
        or (value_type == "float" and type(actual) is float)
    )
    if not type_valid:
        raise RuntimeError(
            f"render_settings_readback_type_mismatch:{path}:"
            f"actual={type(actual).__name__}:expected={value_type}"
        )
    if value_type == "float":
        value_valid = math.isfinite(actual) and math.isclose(
            actual, expected, rel_tol=0.0, abs_tol=1e-6
        )
    else:
        value_valid = actual == expected
    if not value_valid:
        raise RuntimeError(
            f"render_settings_readback_value_mismatch:{path}:"
            f"actual={actual!r}:expected={expected!r}"
        )
    return dict(record)


def apply_and_validate_effective_replay_render_settings(
    settings: Any,
    *,
    native: Any,
    effective_look_contract: Mapping[str, Any],
    update_barrier: Any | None = None,
) -> dict[str, Any]:
    """Apply and strictly read back every frozen render registry setting."""
    look = validate_effective_replay_look_contract(effective_look_contract)
    expected = look["render_settings"]
    native_refraction = native.apply_presentation_render_settings(settings)
    if (
        native_refraction.get("setting_path") != REPLAY_REFRACTION_SETTING_PATH
        or type(native_refraction.get("max_refraction_bounces")) is not int
        or native_refraction.get("max_refraction_bounces")
        != expected["max_refraction_bounces"]
    ):
        raise RuntimeError("native_refraction_render_settings_mismatch")
    requested_registry = _effective_replay_registry_records(look)
    for record in requested_registry:
        _set_render_registry_value(
            settings,
            path=record["path"],
            value_type=record["value_type"],
            value=record["value"],
        )
    update_barrier_executed = False
    if update_barrier is not None:
        if not callable(update_barrier):
            raise TypeError("render_settings_update_barrier_not_callable")
        update_barrier()
        update_barrier_executed = True
    registry_readback = [
        _validate_render_registry_readback(
            record=record,
            actual=settings.get(record["path"]),
        )
        for record in requested_registry
    ]
    readback_by_path = {
        record["path"]: record["value"] for record in registry_readback
    }
    actual = {
        "rt_subframes": expected["rt_subframes"],
        "max_refraction_bounces": readback_by_path[
            REPLAY_REFRACTION_SETTING_PATH
        ],
        "max_refraction_bounces_setting_path": native_refraction[
            "setting_path"
        ],
        "ambient_occlusion_enabled": readback_by_path[
            REPLAY_AMBIENT_OCCLUSION_SETTING_PATH
        ],
        "ambient_occlusion_setting_path": (
            REPLAY_AMBIENT_OCCLUSION_SETTING_PATH
        ),
        "ambient_occlusion_ray_length": readback_by_path[
            REPLAY_AMBIENT_OCCLUSION_RAY_LENGTH_SETTING_PATH
        ],
        "ambient_occlusion_ray_length_setting_path": (
            REPLAY_AMBIENT_OCCLUSION_RAY_LENGTH_SETTING_PATH
        ),
        "ambient_occlusion_min_samples": readback_by_path[
            REPLAY_AMBIENT_OCCLUSION_MIN_SAMPLES_SETTING_PATH
        ],
        "ambient_occlusion_min_samples_setting_path": (
            REPLAY_AMBIENT_OCCLUSION_MIN_SAMPLES_SETTING_PATH
        ),
        "ambient_occlusion_max_samples": readback_by_path[
            REPLAY_AMBIENT_OCCLUSION_MAX_SAMPLES_SETTING_PATH
        ],
        "ambient_occlusion_max_samples_setting_path": (
            REPLAY_AMBIENT_OCCLUSION_MAX_SAMPLES_SETTING_PATH
        ),
        "ambient_occlusion_denoiser_mode": readback_by_path[
            REPLAY_AMBIENT_OCCLUSION_DENOISER_MODE_SETTING_PATH
        ],
        "ambient_occlusion_denoiser_mode_setting_path": (
            REPLAY_AMBIENT_OCCLUSION_DENOISER_MODE_SETTING_PATH
        ),
        "shadows_enabled": readback_by_path[REPLAY_SHADOWS_SETTING_PATH],
        "shadows_setting_path": REPLAY_SHADOWS_SETTING_PATH,
        "shadow_sample_count": readback_by_path[
            REPLAY_SHADOW_SAMPLE_COUNT_SETTING_PATH
        ],
        "shadow_sample_count_setting_path": REPLAY_SHADOW_SAMPLE_COUNT_SETTING_PATH,
        "renderer_consumption_verification": (
            REPLAY_RENDERER_CONSUMPTION_VERIFICATION
        ),
    }
    if actual != expected:
        raise RuntimeError(
            "effective_replay_render_settings_mismatch:"
            f"actual={json.dumps(actual, sort_keys=True)}:"
            f"expected={json.dumps(expected, sort_keys=True)}"
        )
    return {
        **actual,
        "validated": True,
        "postboot_update_barrier_executed": update_barrier_executed,
        "requested_registry": requested_registry,
        "registry_readback": registry_readback,
        "startup_arguments": build_effective_replay_kit_startup_arguments(look),
        "renderer_consumption_verification": (
            REPLAY_RENDERER_CONSUMPTION_VERIFICATION
        ),
        "native_refraction_contract": _json_native_copy(native_refraction),
        "effective_replay_look_contract_sha256": look[
            "effective_replay_look_contract_sha256"
        ],
    }


def build_render_diagnostic_render_settings_evidence(
    *,
    render_settings: Mapping[str, Any],
    effective_look_contract: Mapping[str, Any],
    static_capture: Mapping[str, Any],
) -> dict[str, Any]:
    look = validate_effective_replay_look_contract(effective_look_contract)
    variant = look["render_diagnostic_variant_id"]
    if variant not in RENDER_DIAGNOSTIC_VARIANTS:
        raise ValueError("render_diagnostic_render_settings_variant_invalid")
    if not isinstance(render_settings, Mapping) or not isinstance(
        static_capture, Mapping
    ):
        raise ValueError("render_diagnostic_render_settings_contract_invalid")
    expected_registry = _effective_replay_registry_records(look)
    expected_startup = build_effective_replay_kit_startup_arguments(look)
    expected_rt = RENDER_DIAGNOSTIC_VARIANT_SETTINGS[variant][1]
    if (
        render_settings.get("validated") is not True
        or render_settings.get("postboot_update_barrier_executed") is not True
        or render_settings.get("requested_registry") != expected_registry
        or render_settings.get("registry_readback") != expected_registry
        or render_settings.get("startup_arguments") != expected_startup
        or render_settings.get("renderer_consumption_verification")
        != REPLAY_RENDERER_CONSUMPTION_VERIFICATION
        or render_settings.get("rt_subframes") != expected_rt
        or static_capture.get("rt_subframes") != expected_rt
        or type(static_capture.get("rt_subframes")) is not int
        or type(static_capture.get("replicator_delta_time")) not in (int, float)
        or type(static_capture.get("replicator_delta_time")) is bool
        or not math.isfinite(float(static_capture["replicator_delta_time"]))
        or float(static_capture["replicator_delta_time"]) != 0.0
        or static_capture.get("timeline_advanced") is not False
        or static_capture.get(
            "observed_default_time_usd_point_attributes_changed"
        )
        is not False
    ):
        raise ValueError("render_diagnostic_render_settings_contract_invalid")
    return {
        "schema_version": 1,
        "render_diagnostic_variant_id": variant,
        "requested_registry": _json_native_copy(expected_registry),
        "startup_arguments": list(expected_startup),
        "registry_readback": _json_native_copy(expected_registry),
        "renderer_consumption_verification": (
            REPLAY_RENDERER_CONSUMPTION_VERIFICATION
        ),
        "rt_subframes": expected_rt,
    }


def build_execution_provenance(args: argparse.Namespace) -> dict[str, Any]:
    """Bind the replay code, command line, runtime, and starting git state."""
    effective_look = _validated_effective_look_contract_for_args(args)
    render_diagnostic_identity = validate_render_diagnostic_cell_scope(args)
    source_paths = sorted(
        path.resolve()
        for path in (REPO_ROOT / "tools/labutopia_fluid").glob("*.py")
        if path.is_file() and not path.is_symlink()
    )
    missing = [str(path) for path in source_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("execution_provenance_source_missing:" + ",".join(missing))
    argv = list(getattr(args, "_execution_argv", []))
    if not argv:
        argv = [str(Path(__file__).resolve()), "<direct_python_call_no_cli_argv>"]
    git_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        stderr=subprocess.DEVNULL,
        text=True,
    ).strip()
    status_payload = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=REPO_ROOT,
        stderr=subprocess.DEVNULL,
    )
    status_tokens = [token for token in status_payload.split(b"\0") if token]
    status_record_count = sum(
        len(token) >= 3 and token[2:3] == b" " for token in status_tokens
    )
    try:
        isaacsim_version = importlib.metadata.version("isaacsim")
    except importlib.metadata.PackageNotFoundError:
        isaacsim_version = "NOT_INSTALLED_IN_CURRENT_INTERPRETER"
    payload = {
        "schema_version": 1,
        "argv": [str(value) for value in argv],
        "source_file_sha256": {
            str(path): _sha256_file(path) for path in source_paths
        },
        "source_file_set_policy": (
            "all_non_symlink_python_files_in_tools/labutopia_fluid_at_start"
        ),
        "source_directory": str(
            (REPO_ROOT / "tools/labutopia_fluid").resolve()
        ),
        "python": {
            "executable": str(Path(sys.executable).resolve()),
            "version": sys.version,
            "version_info": list(sys.version_info[:5]),
        },
        "runtime": {
            "isaacsim_version": isaacsim_version,
        },
        "git": {
            "repository_root": str(REPO_ROOT),
            "head_commit": git_head,
            "porcelain_v1_z_sha256": hashlib.sha256(status_payload).hexdigest(),
            "porcelain_v1_z_byte_count": len(status_payload),
            "status_record_count": status_record_count,
            "dirty": bool(status_payload),
        },
        "render_parameters": {
            "width": int(args.width),
            "height": int(args.height),
            "video_fps": float(args.video_fps),
            "warmup_updates": int(args.warmup_updates),
            "camera_warmup_updates": int(args.camera_warmup_updates),
            "headless": bool(args.headless),
            "candidates": list(_candidate_ids_from_args(args)),
            "visual_prototype_display_fill_only": bool(
                getattr(args, "visual_prototype_display_fill_only", False)
            ),
            "lighting_variant_id": effective_look["lighting_variant_id"],
            "effective_replay_look_contract_sha256": effective_look[
                "effective_replay_look_contract_sha256"
            ],
        },
    }
    if render_diagnostic_identity is not None:
        payload["render_parameters"].update(
            {
                "render_diagnostic_variant_id": effective_look[
                    "render_diagnostic_variant_id"
                ],
                "render_diagnostic_identity": deepcopy(
                    render_diagnostic_identity
                ),
                "kit_startup_arguments": (
                    build_effective_replay_kit_startup_arguments(effective_look)
                ),
            }
        )
    return {**payload, "provenance_sha256": _json_sha256(payload)}


def verify_execution_provenance_sources_unchanged(
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Re-hash the complete recorded local execution source set."""
    expected = provenance.get("source_file_sha256")
    if not isinstance(expected, Mapping) or not expected:
        raise ValueError("execution_source_provenance_missing")
    source_file_set_unchanged: bool | None = None
    if provenance.get("source_file_set_policy") == (
        "all_non_symlink_python_files_in_tools/labutopia_fluid_at_start"
    ):
        source_directory = Path(
            str(provenance.get("source_directory", ""))
        ).expanduser().resolve()
        current_paths = {
            str(path.resolve())
            for path in source_directory.glob("*.py")
            if path.is_file() and not path.is_symlink()
        }
        expected_paths = {str(Path(str(path)).expanduser().resolve()) for path in expected}
        if current_paths != expected_paths:
            raise RuntimeError(
                "execution_source_file_set_changed:"
                f"added={sorted(current_paths - expected_paths)}:"
                f"removed={sorted(expected_paths - current_paths)}"
            )
        source_file_set_unchanged = True
    verified: dict[str, str] = {}
    for raw_path, raw_digest in sorted(expected.items()):
        path = Path(str(raw_path)).expanduser().resolve()
        expected_digest = _require_sha256(
            f"execution_source_sha256:{path}", raw_digest
        )
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"execution_source_file_missing:{path}")
        actual_digest = _sha256_file(path)
        if actual_digest != expected_digest:
            raise RuntimeError(
                f"execution_source_file_changed:{path}:"
                f"{actual_digest}!={expected_digest}"
            )
        verified[str(path)] = actual_digest
    result = {
        "verified": True,
        "verified_file_count": len(verified),
        "verified_source_file_sha256": verified,
        "verified_source_tree_sha256": _json_sha256(verified),
        "source_file_set_unchanged": source_file_set_unchanged,
    }
    return result


def build_version_matched_mdl_source_contract(
    native: Any,
    *,
    runtime_prefix: str | os.PathLike[str] | None = None,
    runtime_version: str | None = None,
) -> dict[str, Any]:
    """Resolve and hash the active Isaac 4.1 conda MDL source tree."""
    prefix = Path(runtime_prefix or sys.prefix).resolve()
    version = runtime_version or importlib.metadata.version("isaacsim")
    if not str(version).startswith("4.1"):
        raise ValueError(f"target_isaacsim41_runtime_required:{version}")
    raw_source_root = Path(native.PRESENTATION_WATER_MDL_ROOT).expanduser()
    if raw_source_root.is_symlink():
        raise ValueError("version_matched_mdl_source_symlink_rejected")
    source_root = raw_source_root.resolve()
    try:
        relative_root = source_root.relative_to(prefix)
    except ValueError as exc:
        raise ValueError(
            f"version_matched_conda_mdl_root_required:{source_root}:runtime_prefix={prefix}"
        ) from exc
    if "site-packages" not in relative_root.parts or source_root.parts[-3:] != (
        "omni",
        "mdl",
        "core",
    ):
        raise ValueError(f"version_matched_conda_mdl_root_required:{source_root}")

    required_relative = {
        *(f"Base/{name}" for name in native.CORE_MDL_DIRECT_ASSETS),
        *(f"Base/{name}" for name in native.CORE_MDL_TRANSITIVE_DEPENDENCIES),
        "mdl/OmniSurface/OmniSurfaceBase.mdl",
        "mdl/nvidia/core_definitions.mdl",
        "mdl/nvidia/support_definitions.mdl",
    }
    missing = sorted(
        relative
        for relative in required_relative
        if not (source_root / relative).is_file()
    )
    if missing:
        raise FileNotFoundError(
            "version_matched_omniglass_mdl_files_missing:" + ",".join(missing)
        )
    source_files = sorted(
        [
            *source_root.glob("Base/*.mdl"),
            *(
                path
                for path in (source_root / "mdl").rglob("*")
                if path.is_file()
            ),
        ]
    )
    if not source_files or any(
        path.is_symlink() or not path.is_file() for path in source_files
    ):
        raise FileNotFoundError("version_matched_omniglass_mdl_tree_empty")
    source_hashes = {
        str(path.relative_to(source_root)): _sha256_file(path) for path in source_files
    }
    required_hashes = {
        relative: source_hashes[relative] for relative in sorted(required_relative)
    }
    return {
        "source_root": str(source_root),
        "runtime_prefix": str(prefix),
        "runtime_version": str(version),
        "source_root_under_runtime_prefix": True,
        "required_file_sha256": required_hashes,
        "source_file_sha256": source_hashes,
        "source_tree_sha256": _json_sha256(source_hashes),
        "host_isaac_sim_root_allowed": False,
    }


def build_render_diagnostic_mdl_closure_evidence(
    closure_root: str | os.PathLike[str],
) -> dict[str, Any]:
    _raw_root, records = _snapshot_pinned_regular_tree(
        closure_root,
        label="render_diagnostic_mdl_closure",
    )
    if not records:
        raise ValueError("render_diagnostic_mdl_closure_empty")
    return {
        "schema_version": 1,
        "closure_id": "isaacsim41_conda_version_matched_core",
        "files": records,
    }


def validate_version_matched_mdl_source_against_protected_snapshot(
    source: Mapping[str, Any],
    protected_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    source_root = _absolute_path_without_symlink_resolution(
        str(source.get("source_root", ""))
    )
    if source_root != _absolute_path_without_symlink_resolution(
        RENDER_DIAGNOSTIC_VERSION_MATCHED_MDL_SOURCE_ROOT
    ):
        raise ValueError("version_matched_mdl_protected_root_mismatch")
    protected_roots = protected_snapshot.get("protected_roots")
    if not isinstance(protected_roots, list):
        raise ValueError("version_matched_mdl_protected_snapshot_invalid")
    matching = [
        record
        for record in protected_roots
        if isinstance(record, Mapping)
        and _absolute_path_without_symlink_resolution(
            str(record.get("root_path", ""))
        )
        == source_root
    ]
    if len(matching) != 1 or not isinstance(matching[0].get("files"), list):
        raise ValueError("version_matched_mdl_protected_root_missing")
    protected_files = {
        record.get("path"): record
        for record in matching[0]["files"]
        if isinstance(record, Mapping)
    }
    source_files = source.get("source_file_sha256")
    if not isinstance(source_files, Mapping) or not source_files:
        raise ValueError("version_matched_mdl_source_contract_invalid")
    for relative, sha256 in source_files.items():
        record = protected_files.get(relative)
        source_path = source_root / str(relative)
        if (
            not isinstance(record, Mapping)
            or record.get("sha256") != sha256
            or record.get("byte_count") != source_path.stat().st_size
        ):
            raise ValueError(
                f"version_matched_mdl_protected_file_mismatch:{relative}"
            )
    return {
        "protected_source_root": str(source_root),
        "protected_source_tree_verified": True,
        "protected_source_file_count": len(source_files),
    }


def _mirror_version_matched_mdl_closure(
    native: Any,
    *,
    artifact_dir: Path,
    protected_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source = build_version_matched_mdl_source_contract(native)
    protected_source = (
        validate_version_matched_mdl_source_against_protected_snapshot(
            source,
            protected_snapshot,
        )
        if protected_snapshot is not None
        else None
    )
    source_root = Path(source["source_root"])
    closure_root = artifact_dir / VERSION_MATCHED_MDL_CLOSURE_DIRNAME
    for relative, expected_sha256 in source["source_file_sha256"].items():
        source_path = source_root / relative
        target_path = closure_root / relative
        source_payload = _read_regular_file_snapshot(
            source_path,
            label="version_matched_mdl_source",
        )
        _copy_regular_file_create_exclusive(
            source_path,
            target_path,
            expected_byte_count=len(source_payload),
            expected_sha256=expected_sha256,
            label="version_matched_mdl_copy",
        )
    copied_hashes = {
        relative: _sha256_file(closure_root / relative)
        for relative in source["source_file_sha256"]
    }
    if copied_hashes != source["source_file_sha256"]:
        raise RuntimeError("version_matched_mdl_closure_hash_mismatch")
    matrix_closure = build_render_diagnostic_mdl_closure_evidence(closure_root)
    return {
        **source,
        "material_closure_mode": "isaacsim41_conda_version_matched_core",
        "protected_source_verification": protected_source,
        "closure_root": str(closure_root),
        "closure_base_dir": str(closure_root / "Base"),
        "closure_omnisurface_module_dir": str(closure_root / "mdl/OmniSurface"),
        "copied_file_sha256": copied_hashes,
        "copied_tree_sha256": _json_sha256(copied_hashes),
        "matrix_mdl_closure": matrix_closure,
        "matrix_mdl_closure_sha256": canonical_json_sha256_v1(
            matrix_closure
        ),
    }


def verify_material_closure_snapshot_unchanged(
    closure: Mapping[str, Any],
) -> dict[str, Any]:
    root = _reject_symlink_path_components(
        str(closure.get("closure_root", "")),
        label="material_closure_snapshot_root",
    )
    expected_raw = closure.get("copied_file_sha256")
    if not root.is_dir() or not isinstance(expected_raw, Mapping) or not expected_raw:
        raise RuntimeError("material_closure_snapshot_contract_invalid")
    expected = {str(path): str(value) for path, value in expected_raw.items()}
    actual_paths = {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    if actual_paths != set(expected):
        raise RuntimeError(
            "material_closure_file_set_changed:"
            f"actual={sorted(actual_paths)}:expected={sorted(expected)}"
        )
    actual: dict[str, str] = {}
    for relative, expected_sha256 in sorted(expected.items()):
        path = root / relative
        actual_sha256 = _sha256_file(path)
        if actual_sha256 != expected_sha256:
            raise RuntimeError(
                "material_closure_file_changed:"
                f"{relative}:{actual_sha256}!={expected_sha256}"
            )
        actual[relative] = actual_sha256
    return {
        "material_closure_bytes_unchanged": True,
        "closure_root": str(root),
        "verified_file_count": len(actual),
        "verified_file_sha256": actual,
        "verified_tree_sha256": _json_sha256(actual),
    }


def _require_plain_int(name: str, value: Any, *, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise ValueError(f"{name}_must_be_non_bool_int")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name}_must_be_at_least_{minimum}")
    return value


def _require_sha256(name: str, value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX_DIGITS for character in value.lower())
    ):
        raise ValueError(f"{name}_must_be_sha256")
    return value.lower()


def _reject_nonfinite_json(token: str) -> Any:
    raise ValueError(f"nonfinite_json_token:{token}")


def _strict_json_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def _strict_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"nonfinite_json_number:{value}")
    return parsed


def _read_regular_file_snapshot(path: Path, *, label: str) -> bytes:
    try:
        with _open_pinned_path(
            path,
            leaf_directory=False,
            label=label,
        ) as (checked_path, descriptor, identities):
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError(
                    f"{label}_must_be_regular_file:{checked_path}"
                )
            chunks = []
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            payload = b"".join(chunks)
            after = os.fstat(descriptor)
            _verify_pinned_path_components(identities, label=label)
    except OSError as exc:
        raise ValueError(f"{label}_unreadable:{type(exc).__name__}:{exc}") from exc
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if before_identity != after_identity or len(payload) != after.st_size:
        raise ValueError(f"{label}_changed_while_reading:{checked_path}")
    return payload


def _open_image_file_snapshot(path: Path, *, label: str):
    from PIL import Image

    payload = _read_regular_file_snapshot(path, label=label)
    return Image.open(io.BytesIO(payload))


def _load_json_object_bytes(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        text = payload.decode("utf-8")
        if text.startswith("\ufeff"):
            raise ValueError("json_bom_not_allowed")
        value = json.loads(
            text,
            object_pairs_hook=_strict_json_object,
            parse_float=_strict_json_float,
            parse_constant=_reject_nonfinite_json,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label}_unreadable:{type(exc).__name__}:{exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label}_must_be_json_object")
    return value


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    payload = _read_regular_file_snapshot(path, label=label)
    if path.name.endswith(".gz"):
        try:
            payload = gzip.decompress(payload)
        except (OSError, EOFError) as exc:
            raise ValueError(
                f"{label}_gzip_unreadable:{type(exc).__name__}:{exc}"
            ) from exc
    return _load_json_object_bytes(payload, label=label)


def _load_trace_bytes(payload: bytes) -> tuple[dict[str, Any], ...]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"accepted_trace_unreadable:{type(exc).__name__}:{exc}"
        ) from exc
    if not text or not text.endswith("\n"):
        raise ValueError("accepted_trace_must_be_nonempty_newline_delimited_json")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise ValueError(f"accepted_trace_blank_line:{line_number}")
        try:
            record = json.loads(
                line,
                object_pairs_hook=_strict_json_object,
                parse_float=_strict_json_float,
                parse_constant=_reject_nonfinite_json,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(
                f"accepted_trace_json_invalid:{line_number}:{exc}"
            ) from exc
        if not isinstance(record, dict):
            raise ValueError(f"accepted_trace_record_not_object:{line_number}")
        records.append(record)
    return tuple(records)


def _load_trace_once(path: Path) -> tuple[dict[str, Any], ...]:
    return _load_trace_bytes(
        _read_regular_file_snapshot(path, label="accepted_trace")
    )


def _resolve_input_path(summary_path: Path, value: Any, *, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}_missing")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = summary_path.parent / path
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{label}_missing:{resolved}")
    return resolved


def _classification_name(value: Any) -> str | None:
    if isinstance(value, Mapping):
        name = value.get("classification")
        return str(name) if name is not None else None
    return str(value) if value is not None else None


def camera_capture_failure_message(
    *,
    candidate_id: str,
    role: str,
    frame_index: int,
    diagnostics: Mapping[str, Any],
) -> str:
    diagnostic_json = json.dumps(
        dict(diagnostics),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return (
        "omniglass_replay_image_capture_failed:"
        f"{candidate_id}:{role}:{frame_index}:{diagnostic_json}"
    )


def _validate_run_scoped_diagnostics(
    summary: Mapping[str, Any],
    *,
    summary_path: Path,
    diagnostic_segment_archive: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    segment = summary.get("strict_kit_log_segment")
    isaac_summary = summary.get("isaac_log_summary")
    if not isinstance(segment, Mapping) or not isinstance(isaac_summary, Mapping):
        raise ValueError("run_scoped_diagnostics_incomplete:missing_contract")
    try:
        if not isinstance(segment.get("log_path"), str) or not segment["log_path"]:
            raise ValueError("missing_log_path")
        byte_offset = _require_plain_int(
            "diagnostic_byte_offset", segment.get("byte_offset"), minimum=0
        )
        byte_count = _require_plain_int(
            "diagnostic_segment_byte_count",
            segment.get("segment_byte_count"),
            minimum=0,
        )
        segment_hash = _require_sha256(
            "diagnostic_segment_sha256", segment.get("segment_sha256")
        )
        if segment.get("cursor_captured") is not True:
            raise ValueError("cursor_not_captured")
        if segment.get("diagnostic_scan_complete") is not True:
            raise ValueError("scan_not_complete")
        if isaac_summary.get("run_segment_only") is not True:
            raise ValueError("diagnostics_not_run_segment_only")
        if isaac_summary.get("isaac_log_available") is not True:
            raise ValueError("isaac_log_unavailable")
        if isaac_summary.get("diagnostic_scan_complete") is not True:
            raise ValueError("isaac_scan_not_complete")
        equality_fields = {
            "log_path": segment["log_path"],
            "byte_offset": byte_offset,
            "segment_byte_count": byte_count,
            "segment_sha256": segment_hash,
            "cursor_captured": True,
        }
        for field, expected in equality_fields.items():
            if isaac_summary.get(field) != expected:
                raise ValueError(f"diagnostic_provenance_mismatch:{field}")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"run_scoped_diagnostics_incomplete:{exc}") from exc

    if diagnostic_segment_archive is not None:
        archive_path = Path(diagnostic_segment_archive).expanduser().resolve()
        payload = _read_regular_file_snapshot(
            archive_path,
            label="accepted_diagnostic_segment_archive",
        )
        source_mode = "explicit_archive_override"
        source_path = archive_path
        source_byte_offset = 0
    else:
        source_path = _resolve_input_path(
            summary_path, segment["log_path"], label="declared_kit_log"
        )
        source_mode = "declared_kit_log"
        source_byte_offset = byte_offset
        try:
            with source_path.open("rb") as stream:
                stream.seek(byte_offset)
                payload = stream.read(byte_count)
        except OSError as exc:
            raise ValueError(
                f"diagnostic_segment_unreadable:{type(exc).__name__}:{exc}"
            ) from exc
    actual_hash = hashlib.sha256(payload).hexdigest()
    if actual_hash != segment_hash:
        raise ValueError(
            f"diagnostic_segment_sha256_mismatch:{actual_hash}!={segment_hash}"
        )
    if len(payload) != byte_count:
        raise ValueError(
            f"diagnostic_segment_length_mismatch:{len(payload)}!={byte_count}"
        )
    return {
        "source_mode": source_mode,
        "archive_path": (
            str(source_path) if source_mode == "explicit_archive_override" else None
        ),
        "declared_log_path": str(segment["log_path"]),
        "source_path": str(source_path),
        "source_byte_offset": source_byte_offset,
        "segment_byte_count": byte_count,
        "segment_sha256": segment_hash,
        "diagnostic_scan_complete": True,
    }


def _vector3(name: str, value: Any) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"accepted_cup_frame_invalid:{name}")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"accepted_cup_frame_invalid:{name}")
    return result


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(float(left[index]) * float(right[index]) for index in range(3))


def _frame_from_summary(value: Any) -> CupInteriorFrame:
    from tools.labutopia_fluid.real_beaker import CupInteriorFrame

    if not isinstance(value, Mapping):
        raise ValueError("accepted_cup_frame_missing")
    core_fields = {
        "origin_world",
        "x_axis_world",
        "y_axis_world",
        "z_axis_world",
        "parent_local_axis",
        "outer_radius",
        "interior_radius",
        "outer_floor",
        "interior_floor",
        "rim_height",
        "calibration_source",
        "axis_alignment_dot",
    }
    try:
        origin = _vector3("origin_world", value["origin_world"])
        axes = tuple(
            _vector3(name, value[name])
            for name in ("x_axis_world", "y_axis_world", "z_axis_world")
        )
        scalars = {
            name: float(value[name])
            for name in (
                "outer_radius",
                "interior_radius",
                "outer_floor",
                "interior_floor",
                "rim_height",
                "axis_alignment_dot",
            )
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"accepted_cup_frame_invalid:{exc}") from exc
    if not all(math.isfinite(item) for item in scalars.values()):
        raise ValueError("accepted_cup_frame_invalid:nonfinite_scalar")
    if scalars["interior_radius"] <= 0.0 or scalars["outer_radius"] <= 0.0:
        raise ValueError("accepted_cup_frame_invalid:radius")
    if scalars["rim_height"] <= scalars["interior_floor"]:
        raise ValueError("accepted_cup_frame_invalid:height")
    if scalars["axis_alignment_dot"] < 0.999:
        raise ValueError("accepted_cup_frame_invalid:axis_alignment")
    for index, axis in enumerate(axes):
        if not math.isclose(_dot(axis, axis), 1.0, abs_tol=1e-6):
            raise ValueError(f"accepted_cup_frame_invalid:axis_norm:{index}")
    if any(
        not math.isclose(_dot(axes[left], axes[right]), 0.0, abs_tol=1e-6)
        for left, right in ((0, 1), (0, 2), (1, 2))
    ):
        raise ValueError("accepted_cup_frame_invalid:axis_orthogonality")
    measurements = {
        key: deepcopy(item) for key, item in value.items() if key not in core_fields
    }
    return CupInteriorFrame(
        origin_world=origin,
        x_axis_world=axes[0],
        y_axis_world=axes[1],
        z_axis_world=axes[2],
        parent_local_axis=str(value["parent_local_axis"]),
        outer_radius=scalars["outer_radius"],
        interior_radius=scalars["interior_radius"],
        outer_floor=scalars["outer_floor"],
        interior_floor=scalars["interior_floor"],
        rim_height=scalars["rim_height"],
        calibration_source=str(value["calibration_source"]),
        axis_alignment_dot=scalars["axis_alignment_dot"],
        _measurements=measurements,
    )


@dataclass(frozen=True)
class AcceptedReplayInput:
    summary_path: Path
    source_usd_path: Path
    trace_path: Path
    summary_sha256: str
    source_usd_sha256: str
    trace_sha256: str
    summary: dict[str, Any]
    records: tuple[dict[str, Any], ...]
    physical_trace_identity: dict[str, Any]
    diagnostic_segment_provenance: dict[str, Any]
    frame: CupInteriorFrame
    candidates: dict[str, dict[str, Any]]
    accepted_authority_bundle_path: Path | None = None
    accepted_authority_bundle_sha256: str | None = None
    accepted_authority: dict[str, Any] | None = None

    def proxy_frame(self, candidate_id: str, *, frame_offset: int) -> dict[str, Any]:
        from tools.labutopia_fluid.omniglass_reference import (
            build_presentation_proxy_frame,
        )

        if candidate_id not in self.candidates:
            raise ValueError(f"unknown_reference_candidate:{candidate_id}")
        try:
            record = self.records[frame_offset]
        except IndexError as exc:
            raise ValueError(f"trace_frame_offset_out_of_range:{frame_offset}") from exc
        return build_presentation_proxy_frame(
            record["positions"],
            frame=self.frame,
            candidate=self.candidates[candidate_id],
            nominal_physical_particle_width=float(
                self.summary["physics_particle_offsets"]["particle_width"]
            ),
        )


def load_and_validate_accepted_replay(
    accepted_summary: str | os.PathLike[str],
    *,
    diagnostic_segment_archive: str | os.PathLike[str] | None = None,
    trace_path_override: str | os.PathLike[str] | None = None,
    source_usd_path_override: str | os.PathLike[str] | None = None,
    accepted_authority_bundle_path: str | os.PathLike[str] | None = None,
    accepted_authority_bundle_sha256: str | None = None,
    accepted_authority: Mapping[str, Any] | None = None,
) -> AcceptedReplayInput:
    """Load all accepted evidence once and fail closed before Isaac is imported."""
    from tools.labutopia_fluid.omniglass_reference import (
        REFERENCE_CANDIDATE_IDS as HELPER_CANDIDATE_IDS,
        build_reference_candidates,
    )
    from tools.labutopia_fluid.real_beaker import validate_strict_trace_schema

    if HELPER_CANDIDATE_IDS != REFERENCE_CANDIDATE_IDS:
        raise RuntimeError("reference_candidate_ids_diverged")
    summary_path = Path(accepted_summary).expanduser().resolve()
    if not summary_path.is_file():
        raise FileNotFoundError(f"accepted_summary_missing:{summary_path}")
    summary_payload = _read_regular_file_snapshot(
        summary_path,
        label="accepted_summary",
    )
    summary_sha256 = hashlib.sha256(summary_payload).hexdigest()
    summary = _load_json_object_bytes(summary_payload, label="accepted_summary")
    strict = summary.get("strict_visible_classification")
    if not isinstance(strict, Mapping):
        raise ValueError("accepted_static_hold_required:strict_classification_missing")
    if (
        _classification_name(strict) != "PASS_VISIBLE_BEAKER_STATIC_HOLD"
        or _classification_name(summary.get("classification"))
        != "PASS_VISIBLE_BEAKER_STATIC_HOLD"
        or strict.get("trace_schema_valid") is not True
        or strict.get("diagnostic_scan_complete") is not True
        or summary.get("visible_beaker_containment_verified") is not True
    ):
        raise ValueError("accepted_static_hold_required")
    diagnostic_segment_provenance = _validate_run_scoped_diagnostics(
        summary,
        summary_path=summary_path,
        diagnostic_segment_archive=diagnostic_segment_archive,
    )

    identity_value = summary.get("physical_trace_identity")
    strict_identity = strict.get("physical_trace_identity")
    if not isinstance(identity_value, Mapping) or not isinstance(
        strict_identity, Mapping
    ):
        raise ValueError("physical_trace_identity_missing")
    identity = deepcopy(dict(identity_value))
    if dict(strict_identity) != identity:
        raise ValueError("physical_trace_identity_inconsistent_in_summary")
    try:
        requested_count = _require_plain_int(
            "identity_particle_count", identity["particle_count"], minimum=1
        )
        seed = _require_plain_int("identity_seed", identity["seed"], minimum=0)
        steps = _require_plain_int("identity_steps", identity["steps"], minimum=0)
        cadence = _require_plain_int(
            "identity_trace_interval", identity["trace_interval"], minimum=1
        )
        expected_source_hash = _require_sha256(
            "identity_source_usd_sha256", identity["source_usd_sha256"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"physical_trace_identity_incomplete:{exc}") from exc

    source_path = (
        Path(source_usd_path_override).expanduser().resolve(strict=True)
        if source_usd_path_override is not None
        else _resolve_input_path(
            summary_path, summary.get("source_usd_path"), label="accepted_source_usd"
        )
    )
    trace_path = (
        Path(trace_path_override).expanduser().resolve(strict=True)
        if trace_path_override is not None
        else _resolve_input_path(
            summary_path, summary.get("trace_path"), label="accepted_trace"
        )
    )
    source_payload = _read_regular_file_snapshot(
        source_path,
        label="accepted_source_usd",
    )
    actual_source_hash = hashlib.sha256(source_payload).hexdigest()
    if actual_source_hash != expected_source_hash:
        raise ValueError(
            f"accepted_source_usd_sha256_mismatch:{actual_source_hash}!={expected_source_hash}"
        )
    if summary.get("source_usd_sha256") not in (None, expected_source_hash):
        raise ValueError("accepted_summary_source_usd_sha256_mismatch")

    try:
        if (
            _require_plain_int(
                "selected_particle_count", summary["selected_particle_count"], minimum=1
            )
            != requested_count
        ):
            raise ValueError("selected_particle_count_mismatch")
        if _require_plain_int("summary_steps", summary["steps"], minimum=0) != steps:
            raise ValueError("summary_steps_mismatch")
        plan = summary["controlled_spawn_plan"]
        region = summary["region_config"]
        if not isinstance(plan, Mapping) or not isinstance(region, Mapping):
            raise ValueError("summary_trace_configuration_missing")
        if _require_plain_int("summary_seed", plan["particle_seed"], minimum=0) != seed:
            raise ValueError("summary_seed_mismatch")
        if (
            _require_plain_int(
                "summary_trace_interval", region["trace_interval"], minimum=1
            )
            != cadence
        ):
            raise ValueError("summary_trace_interval_mismatch")
        _vector3("region_source_center", region["source_center"])
        _vector3("region_target_center", region["target_center"])
        for radius_key in ("source_radius", "target_radius"):
            radius = float(region[radius_key])
            if not math.isfinite(radius) or radius <= 0.0:
                raise ValueError(f"region_{radius_key}_must_be_positive_finite")
        table_z = float(region["table_z"])
        if not math.isfinite(table_z):
            raise ValueError("region_table_z_must_be_finite")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"accepted_summary_trace_contract_invalid:{exc}") from exc

    try:
        trace_payload = _read_regular_file_snapshot(
            trace_path,
            label="accepted_trace",
        )
        trace_sha256 = hashlib.sha256(trace_payload).hexdigest()
        records = _load_trace_bytes(trace_payload)
        recomputed = validate_strict_trace_schema(
            records,
            requested_count=requested_count,
            steps=steps,
            cadence=cadence,
            source_usd_sha256=actual_source_hash,
            particle_seed=seed,
        )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"strict_trace_schema_invalid:{exc}") from exc
    if recomputed != identity:
        raise ValueError(
            "physical_trace_identity_mismatch:accepted_summary_does_not_exactly_equal_recomputed_trace"
        )
    if set(recomputed) != set(PHYSICAL_TRACE_IDENTITY_FIELDS):
        raise ValueError("physical_trace_identity_field_set_invalid")

    frame = _frame_from_summary(summary.get("cup_interior_frame"))
    candidates = build_reference_candidates(frame.interior_radius * 2.0)
    return AcceptedReplayInput(
        summary_path=summary_path,
        source_usd_path=source_path,
        trace_path=trace_path,
        summary_sha256=summary_sha256,
        source_usd_sha256=actual_source_hash,
        trace_sha256=trace_sha256,
        summary=summary,
        records=records,
        physical_trace_identity=recomputed,
        diagnostic_segment_provenance=diagnostic_segment_provenance,
        frame=frame,
        candidates=candidates,
        accepted_authority_bundle_path=(
            Path(accepted_authority_bundle_path).expanduser().resolve(strict=True)
            if accepted_authority_bundle_path is not None
            else None
        ),
        accepted_authority_bundle_sha256=accepted_authority_bundle_sha256,
        accepted_authority=(
            deepcopy(dict(accepted_authority))
            if accepted_authority is not None
            else None
        ),
    )


def load_and_validate_support_aligned_authority_bundle(
    path: str | os.PathLike[str],
    *,
    source_usd_path_override: str | os.PathLike[str] | None = None,
) -> tuple[AcceptedReplayInput, dict[str, Any]]:
    from tools.labutopia_fluid import (
        run_build_support_aligned_authority_bundle as authority,
    )

    requested = Path(path).expanduser().resolve(strict=True)
    if requested.is_dir():
        root = requested
        bundle_path = root / AUTHORITY_BUNDLE_BASENAME
    else:
        bundle_path = requested
        root = bundle_path.parent
    if bundle_path.name != AUTHORITY_BUNDLE_BASENAME:
        raise ValueError("support_aligned_authority_bundle_filename_invalid")
    bundle = authority._validate_final_bundle(root)
    logical_hash = _require_sha256(
        "accepted_authority_bundle_sha256",
        bundle.get("accepted_authority_bundle_sha256"),
    )
    if (
        bundle.get("accepted") is not True
        or bundle.get("manifest_type")
        != "support_aligned_p4096_s2_accepted_authority"
        or bundle.get("layout_semantics")
        != "config_range_midpoint_support_aligned"
        or bundle.get("exact_expert_episode_layout") is not False
        or bundle.get("physics_authority_particle_count") != 4096
        or bundle.get("physics_authority_seed") != 2
        or bundle.get("physics_authority_steps") != 600
        or (bundle.get("runtime_preflight") or {}).get(
            "unique_runtime_particle_authority"
        )
        is not True
    ):
        raise ValueError("support_aligned_authority_contract_invalid")
    snapshot_root = root / RUNTIME_EVIDENCE_SNAPSHOT_DIR
    summary_path = snapshot_root / "runtime_smoke_summary.json"
    trace_path = snapshot_root / "particle_readback_trace.jsonl"
    diagnostic_path = root / AUTHORITY_LOG_SEGMENT_BASENAME
    input_hashes = bundle.get("input_hashes")
    if not isinstance(input_hashes, Mapping):
        raise ValueError("support_aligned_authority_input_hashes_missing")
    if (
        _sha256_file(summary_path) != input_hashes.get("runtime_summary_sha256")
        or _sha256_file(trace_path)
        != input_hashes.get("particle_trace_file_sha256")
        or _sha256_file(diagnostic_path)
        != (bundle.get("kit_log_provenance") or {}).get("segment_sha256")
    ):
        raise ValueError("support_aligned_authority_snapshot_hash_mismatch")
    accepted = load_and_validate_accepted_replay(
        summary_path,
        diagnostic_segment_archive=diagnostic_path,
        trace_path_override=trace_path,
        source_usd_path_override=source_usd_path_override,
        accepted_authority_bundle_path=bundle_path,
        accepted_authority_bundle_sha256=logical_hash,
        accepted_authority=bundle,
    )
    if (
        accepted.summary_sha256 != input_hashes.get("runtime_summary_sha256")
        or accepted.trace_sha256 != input_hashes.get("particle_trace_file_sha256")
        or accepted.source_usd_sha256
        != input_hashes.get("support_entry_root_usd_sha256")
    ):
        raise ValueError("support_aligned_authority_replay_identity_mismatch")
    bundle_trace_identity = dict(bundle.get("trace_identity") or {})
    bundle_trace_identity.pop("strict_trace_schema_version", None)
    bundle_trace_identity.pop("strict_trace_schema_sha256", None)
    if bundle_trace_identity != accepted.physical_trace_identity:
        raise ValueError("support_aligned_authority_trace_identity_mismatch")
    contract = {
        "authority_kind": "support_aligned_p4096_s2_accepted_authority",
        "authority_bundle_path": str(bundle_path),
        "authority_bundle_file_sha256": _sha256_file(bundle_path),
        "accepted_authority_bundle_sha256": logical_hash,
        "layout_semantics": bundle["layout_semantics"],
        "exact_expert_episode_layout": False,
        "selected_cell_id": "P4096_S2",
        "selected_particle_count": 4096,
        "selected_seed": 2,
        "accepted_summary_sha256": accepted.summary_sha256,
        "accepted_trace_sha256": accepted.trace_sha256,
        "accepted_source_usd_sha256": accepted.source_usd_sha256,
        "physical_trace_identity": deepcopy(accepted.physical_trace_identity),
        "unique_runtime_particle_authority": True,
        "localized_source_usd_sha256": input_hashes[
            "localized_source_usd_sha256"
        ],
        "support_overlay_usd_sha256": input_hashes[
            "support_overlay_usd_sha256"
        ],
        "support_entry_root_usd_sha256": input_hashes[
            "support_entry_root_usd_sha256"
        ],
        "runtime_evidence_snapshot_tree_sha256": bundle[
            "runtime_evidence_snapshot_tree_sha256"
        ],
        # Compatibility aliases for the existing immutable-input verifier.
        "matrix_manifest_path": str(bundle_path),
        "matrix_manifest_sha256": _sha256_file(bundle_path),
        "matrix_run_identity_sha256": logical_hash,
    }
    return accepted, contract


def _declared_absolute_path(value: Any, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label}_missing")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{label}_must_be_absolute:{value}")
    return path.resolve()


def validate_authoritative_matrix_replay_input(
    accepted_matrix_manifest: str | os.PathLike[str],
    *,
    accepted: AcceptedReplayInput,
    recompute_closure: bool = True,
) -> dict[str, Any]:
    """Recompute matrix closure and bind replay to one accepted 4096 cell."""
    from tools.labutopia_fluid import run_real_beaker_static_hold_matrix as matrix

    matrix_path = Path(accepted_matrix_manifest).expanduser().resolve()
    if not matrix_path.is_file():
        raise FileNotFoundError(
            f"accepted_matrix_manifest_missing:{matrix_path}"
        )
    matrix_payload = _read_regular_file_snapshot(
        matrix_path,
        label="accepted_matrix_manifest",
    )
    matrix_manifest = _load_json_object_bytes(
        matrix_payload,
        label="accepted_matrix_manifest",
    )
    if (
        matrix_manifest.get("schema_version") != 1
        or matrix_manifest.get("manifest_type")
        != "fluid_spike_real_beaker_static_hold_matrix"
    ):
        raise ValueError("accepted_matrix_manifest_schema_invalid")
    cells = matrix_manifest.get("cells")
    if not isinstance(cells, list) or any(
        not isinstance(cell, Mapping) for cell in cells
    ):
        raise ValueError("accepted_matrix_cells_invalid")
    if matrix_manifest.get("real_beaker_static_hold_closed") is not True:
        raise ValueError("accepted_matrix_declared_closure_required")
    if recompute_closure and not matrix.real_beaker_static_hold_closed(cells):
        raise ValueError("accepted_matrix_closure_recomputation_failed")

    matrix_payload_after = _read_regular_file_snapshot(
        matrix_path,
        label="accepted_matrix_manifest",
    )
    if matrix_payload_after != matrix_payload:
        raise ValueError("accepted_matrix_manifest_changed_during_validation")

    matching_cells = []
    for cell in cells:
        try:
            summary_path = _declared_absolute_path(
                cell.get("summary_path"),
                label="matrix_cell_summary_path",
            )
        except ValueError:
            continue
        if summary_path == accepted.summary_path.resolve():
            matching_cells.append(cell)
    if len(matching_cells) != 1:
        raise ValueError(
            "accepted_summary_not_unique_matrix_member:"
            f"matches={len(matching_cells)}"
        )
    selected = matching_cells[0]
    if (
        type(selected.get("particle_count")) is not int
        or selected.get("particle_count") != 4096
        or accepted.physical_trace_identity.get("particle_count") != 4096
    ):
        raise ValueError("accepted_4096_matrix_member_required")
    if (
        type(selected.get("seed")) is not int
        or selected.get("seed") != accepted.physical_trace_identity.get("seed")
    ):
        raise ValueError("accepted_matrix_seed_mismatch")
    selected_trace_path = _declared_absolute_path(
        selected.get("trace_path"),
        label="matrix_cell_trace_path",
    )
    if selected_trace_path != accepted.trace_path.resolve():
        raise ValueError("accepted_matrix_trace_path_mismatch")
    if selected.get("physical_trace_identity") != accepted.physical_trace_identity:
        raise ValueError("accepted_matrix_physical_trace_identity_mismatch")
    if (
        selected.get("returncode") != 0
        or selected.get("classification")
        != "PASS_VISIBLE_BEAKER_STATIC_HOLD"
        or selected.get("visible_beaker_containment_verified") is not True
    ):
        raise ValueError("accepted_matrix_selected_cell_not_authoritative_pass")

    run_identity = matrix_manifest.get("run_identity")
    physical_authoring = selected.get("physical_authoring_identity")
    if not isinstance(run_identity, Mapping) or not isinstance(
        physical_authoring, Mapping
    ):
        raise ValueError("accepted_matrix_run_identity_missing")
    matrix_source_path = _declared_absolute_path(
        run_identity.get("source_usd_path"),
        label="matrix_source_usd_path",
    )
    source_hash = accepted.source_usd_sha256
    if (
        matrix_source_path != accepted.source_usd_path.resolve()
        or run_identity.get("source_usd_sha256") != source_hash
        or physical_authoring.get("source_usd_sha256") != source_hash
    ):
        raise ValueError("accepted_matrix_source_identity_mismatch")
    runner_hash = run_identity.get("child_script_sha256")
    if (
        not isinstance(runner_hash, str)
        or len(runner_hash) != 64
        or physical_authoring.get("runner_script_sha256") != runner_hash
    ):
        raise ValueError("accepted_matrix_runner_identity_mismatch")

    return {
        "matrix_manifest_path": str(matrix_path),
        "matrix_manifest_sha256": hashlib.sha256(matrix_payload).hexdigest(),
        "matrix_closure_declared": True,
        "matrix_closure_recomputed": bool(recompute_closure),
        "selected_cell_id": selected.get("cell_id"),
        "selected_particle_count": selected["particle_count"],
        "selected_seed": selected["seed"],
        "selected_summary_path": str(accepted.summary_path),
        "selected_trace_path": str(accepted.trace_path),
        "accepted_summary_sha256": accepted.summary_sha256,
        "accepted_trace_sha256": accepted.trace_sha256,
        "accepted_source_usd_sha256": source_hash,
        "physical_trace_identity": deepcopy(accepted.physical_trace_identity),
        "matrix_run_identity_sha256": _json_sha256(dict(run_identity)),
    }


def load_replay_inputs_from_args(
    args: argparse.Namespace,
    *,
    recompute_closure: bool,
) -> tuple[AcceptedReplayInput, dict[str, Any]]:
    authority_value = getattr(args, "accepted_authority_bundle", None)
    summary_value = getattr(args, "accepted_summary", None)
    matrix_value = getattr(args, "accepted_matrix_manifest", None)
    diagnostic_value = getattr(args, "accepted_diagnostic_segment_archive", None)
    if authority_value:
        if summary_value or matrix_value or diagnostic_value:
            raise ValueError("replay_authority_mode_ambiguous")
        source_override = getattr(
            args,
            "_runtime_source_snapshot_entry",
            None,
        )
        return load_and_validate_support_aligned_authority_bundle(
            authority_value,
            source_usd_path_override=(
                Path(source_override) if source_override is not None else None
            ),
        )
    if not summary_value or not matrix_value:
        raise ValueError("replay_authority_input_missing")
    accepted = load_and_validate_accepted_replay(
        summary_value,
        diagnostic_segment_archive=diagnostic_value,
    )
    matrix_authority = validate_authoritative_matrix_replay_input(
        matrix_value,
        accepted=accepted,
        recompute_closure=recompute_closure,
    )
    matrix_authority["authority_kind"] = "legacy_closed_matrix_baseline"
    return accepted, matrix_authority


def verify_replay_input_snapshots_unchanged(
    accepted: AcceptedReplayInput,
    matrix_authority: Mapping[str, Any],
) -> dict[str, Any]:
    expected = {
        "accepted_summary": (accepted.summary_path, accepted.summary_sha256),
        "accepted_trace": (accepted.trace_path, accepted.trace_sha256),
        "accepted_source_usd": (
            accepted.source_usd_path,
            accepted.source_usd_sha256,
        ),
        "accepted_matrix_manifest": (
            Path(str(matrix_authority["matrix_manifest_path"])),
            str(matrix_authority["matrix_manifest_sha256"]),
        ),
    }
    diagnostic_provenance = accepted.diagnostic_segment_provenance
    if diagnostic_provenance.get("source_mode") == "explicit_archive_override":
        expected["accepted_diagnostic_segment_archive"] = (
            Path(str(diagnostic_provenance["archive_path"])),
            str(diagnostic_provenance["segment_sha256"]),
        )
    actual: dict[str, str] = {}
    for label, (path, expected_sha256) in expected.items():
        payload = _read_regular_file_snapshot(Path(path), label=label)
        actual_sha256 = hashlib.sha256(payload).hexdigest()
        if actual_sha256 != expected_sha256:
            raise RuntimeError(
                f"replay_input_changed:{label}:"
                f"{actual_sha256}!={expected_sha256}"
            )
        actual[label] = actual_sha256
    return {
        "authoritative_root_input_byte_hashes_unchanged": True,
        "verified_root_input_labels": sorted(actual),
        "usd_dependency_closure_bytes_verified": False,
        "claim_scope": (
            "summary_trace_source_root_layer_and_matrix_manifest_only"
        ),
        "verified_sha256": actual,
    }


def _parse_candidate_ids(
    value: str | Sequence[str],
    *,
    visual_prototype_only: bool = False,
) -> tuple[str, ...]:
    if isinstance(value, str):
        candidate_ids = tuple(item.strip() for item in value.split(",") if item.strip())
    else:
        candidate_ids = tuple(str(item).strip() for item in value)
    if visual_prototype_only:
        if candidate_ids != DISPLAY_FILL_VISUAL_PROTOTYPE_CANDIDATE_IDS:
            raise ValueError(
                "visual_prototype_requires_exact_display_fill_candidate:"
                + ",".join(DISPLAY_FILL_VISUAL_PROTOTYPE_CANDIDATE_IDS)
            )
        return candidate_ids
    if candidate_ids != REFERENCE_CANDIDATE_IDS:
        raise ValueError(
            "replay_requires_all_five_candidates_in_canonical_order:"
            + ",".join(REFERENCE_CANDIDATE_IDS)
        )
    return candidate_ids


def _candidate_ids_from_args(args: argparse.Namespace) -> tuple[str, ...]:
    return _parse_candidate_ids(
        args.candidates,
        visual_prototype_only=bool(
            getattr(args, "visual_prototype_display_fill_only", False)
        ),
    )


def build_replay_scope_contract(
    candidate_ids: Sequence[str],
    *,
    visual_prototype_only: bool,
) -> dict[str, Any]:
    parsed = _parse_candidate_ids(
        candidate_ids,
        visual_prototype_only=visual_prototype_only,
    )
    if visual_prototype_only:
        return {
            "run_scope": "display_fill_normal_block_visual_prototype",
            "visual_prototype_only": True,
            "formal_five_candidate_set_complete": False,
            "formal_five_candidate_replay_complete": False,
            "candidate_ids": list(parsed),
            "colleague_delivery_ready": False,
        }
    return {
        "run_scope": "formal_five_candidate_reference_replay",
        "visual_prototype_only": False,
        "formal_five_candidate_set_complete": True,
        "formal_five_candidate_replay_complete": False,
        "candidate_ids": list(parsed),
        "colleague_delivery_ready": False,
    }


def build_candidate_replay_contracts(
    accepted: AcceptedReplayInput,
    candidate_ids: Sequence[str] = REFERENCE_CANDIDATE_IDS,
    *,
    visual_prototype_only: bool = False,
    effective_look_contract: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    candidate_ids = _parse_candidate_ids(
        candidate_ids,
        visual_prototype_only=visual_prototype_only,
    )
    run_scope = build_replay_scope_contract(
        candidate_ids,
        visual_prototype_only=visual_prototype_only,
    )
    effective_look = validate_effective_replay_look_contract(
        effective_look_contract
        if effective_look_contract is not None
        else build_effective_replay_look_contract()
    )
    render_diagnostic_projection = (
        build_effective_replay_look_matrix_projection(effective_look)
        if effective_look["render_diagnostic_variant_id"] is not None
        else None
    )
    if (
        effective_look["lighting_variant_id"] == LIGHTING_VARIANT_B
        and not visual_prototype_only
    ):
        raise ValueError("b_lighting_requires_visual_prototype")
    identity = accepted.physical_trace_identity
    manifests: dict[str, dict[str, Any]] = {}
    for candidate_id in candidate_ids:
        candidate = accepted.candidates[candidate_id]
        frame_contracts = []
        for frame_offset, record in enumerate(accepted.records):
            proxy = accepted.proxy_frame(candidate_id, frame_offset=frame_offset)
            frame_contract = {
                "frame_offset": frame_offset,
                "frame_index": int(record["step_index"]),
                "trace_record_sha256": _json_sha256(record),
                "source_positions_sha256": _json_sha256(record["positions"]),
                "proxy_geometry_sha256": proxy_geometry_sha256(proxy),
                "presentation_kind": proxy["presentation_kind"],
                "source_physical_point_count": proxy["source_physical_point_count"],
                "proxy_count": proxy["proxy_count"],
                "display_width": proxy["display_width"],
                "voxel_size": proxy["voxel_size"],
                "width_to_interior_ratio": proxy["width_to_interior_ratio"],
                "presentation_only_volume_disclaimer": proxy[
                    "presentation_only_volume_disclaimer"
                ],
                "presentation_only_shape_disclaimer": proxy[
                    "presentation_only_shape_disclaimer"
                ],
                "physical_volume_parity_claim_allowed": proxy[
                    "physical_volume_parity_claim_allowed"
                ],
                "free_surface_shape_claim_allowed": proxy[
                    "free_surface_shape_claim_allowed"
                ],
                "fluid_dynamics_claim_allowed": proxy[
                    "fluid_dynamics_claim_allowed"
                ],
            }
            if proxy["presentation_kind"] == "surface_mesh":
                required_surface_fields = (
                    "canonical_mesh_sha256",
                    "surface_geometry_contract_sha256",
                    "surface_frame_sha256",
                    "source_unique_canonical_position_set_sha256",
                    "source_positions_hash_semantics",
                    "vertex_count",
                    "face_count",
                    "canonical_center",
                    "raw_canonical_bounds",
                    "topology",
                    "containment",
                    "point_aabb_volume_m3",
                    "nominal_disjoint_particle_volume_m3",
                    "display_to_nominal_particle_volume_ratio",
                )
                missing_surface_fields = [
                    key for key in required_surface_fields if key not in proxy
                ]
                if missing_surface_fields:
                    raise ValueError(
                        "candidate_surface_contract_fields_missing:"
                        + ",".join(missing_surface_fields)
                    )
                frame_contract.update(
                    {
                        key: deepcopy(proxy[key])
                        for key in required_surface_fields
                    }
                )
                optional_surface_fields = (
                    "canonical_semi_axes",
                    "display_padding_xy",
                    "display_padding_z",
                    "radial_scale",
                    "radial_correction_m",
                    "axial_correction_m",
                    "display_volume_m3",
                    "surface_model_version",
                    "surface_model_contract",
                    "surface_model_contract_sha256",
                    "source_count_authority",
                    "source_layout_affects_geometry",
                    "nominal_physical_particle_width_affects_geometry",
                    "canonical_bounding_half_extents",
                    "display_fill_radius_m",
                    "display_fill_cap_radius_m",
                    "display_fill_height_m",
                    "display_fill_low_z_m",
                    "display_fill_high_z_m",
                    "edge_rounding_m",
                    "radial_segments",
                    "regular_polygon_area_coefficient",
                    "analytic_normal_contract_verified",
                    "display_proxy_aggregate_sphere_volume_m3",
                    "mesh_enclosed_volume_m3",
                    "mesh_to_display_proxy_volume_relative_error",
                    "display_proxy_volume_disclaimer",
                )
                frame_contract.update(
                    {
                        key: deepcopy(proxy[key])
                        for key in optional_surface_fields
                        if key in proxy
                    }
                )
            frame_contracts.append(frame_contract)
        presentation_kind = str(candidate["presentation_kind"])
        presentation_path = (
            PRESENTATION_SURFACE_PATH
            if presentation_kind == "surface_mesh"
            else PRESENTATION_POINTS_PATH
        )
        manifest = {
            "schema_version": 1,
            "manifest_type": "real_beaker_omniglass_reference_candidate",
            "candidate_id": candidate_id,
            "source_usd_path": str(accepted.source_usd_path),
            "accepted_summary_path": str(accepted.summary_path),
            "accepted_trace_path": str(accepted.trace_path),
            "physical_trace_identity": deepcopy(identity),
            "input_identity": deepcopy(identity),
            "display_width": candidate["display_width"],
            "voxel_size": candidate["voxel_size"],
            "width_to_interior_ratio": candidate["width_to_interior_ratio"],
            "interior_diameter": candidate["interior_diameter"],
            "proxy_mode": candidate["proxy_mode"],
            "presentation_kind": presentation_kind,
            "presentation_only": True,
            "run_scope": run_scope["run_scope"],
            "visual_prototype_only": run_scope["visual_prototype_only"],
            "lighting_variant_id": effective_look["lighting_variant_id"],
            "render_diagnostic_variant_id": effective_look[
                "render_diagnostic_variant_id"
            ],
            "effective_replay_look_matrix_projection_sha256": (
                render_diagnostic_projection["canonical_json_utf8_sha256"]
                if render_diagnostic_projection is not None
                else None
            ),
            "effective_replay_look_contract": deepcopy(effective_look),
            "effective_replay_look_contract_sha256": effective_look[
                "effective_replay_look_contract_sha256"
            ],
            "formal_five_candidate_set_complete": run_scope[
                "formal_five_candidate_set_complete"
            ],
            "presentation_primitive_path": presentation_path,
            "presentation_points_path": (
                PRESENTATION_POINTS_PATH if presentation_kind == "points" else None
            ),
            "presentation_surface_path": (
                PRESENTATION_SURFACE_PATH
                if presentation_kind == "surface_mesh"
                else None
            ),
            "presentation_uses_physx_api": False,
            "frames": frame_contracts,
            "frame_indices": deepcopy(identity["frame_indices"]),
            "frame_particle_counts": deepcopy(identity["frame_particle_counts"]),
            "frame_count": identity["frame_count"],
            "per_frame_proxy_counts": [
                frame["proxy_count"] for frame in frame_contracts
            ],
            "static_presentation_frame_index": identity["frame_indices"][-1],
            "static_presentation_source_physical_point_count": identity[
                "frame_particle_counts"
            ][-1],
            "hidden_physical_initial_state_path": HIDDEN_PHYSICAL_INITIAL_STATE_PATH,
            "hidden_physical_initial_state_frame_index": identity["frame_indices"][0],
            "hidden_physical_initial_state_point_count": identity[
                "frame_particle_counts"
            ][0],
            "a18_material": deepcopy(candidate["a18_reference"]),
            "beaker_override_required": False,
            "native_beaker_material_retarget_required": True,
            "runtime_contract": {
                "source_usd_path": str(accepted.source_usd_path),
                "author_stage_opened_exact_accepted_source": True,
                "static_entry_frozen_before_replicator": True,
                "capture_stage_opens_frozen_static_entry": True,
                "capture_frame_updates_use_anonymous_overlay": True,
                "capture_stage_discarded_after_candidate": None,
                "physics_step_count_instrumented": False,
                "physics_steps_executed": None,
                "observed_default_time_usd_point_attributes_changed": None,
                "timeline_observed_stopped_at_all_checkpoints": None,
                "required_timeline_state_at_capture": "stopped",
                "cameras": [
                    "context",
                    "source_beaker_closeup",
                    "native_table_context",
                ],
            },
            "accepted_4096_trace_preferred": identity["particle_count"] == 4096,
            "accepted_1024_visual_debug_limitation": identity["particle_count"] == 1024,
            "visual_review_verdict": "PENDING_INDEPENDENT_REVIEW",
            "omniglass_reference_particle_look_selected": False,
            "accepted_particle_trace_surface_presentation_selected": False,
            "physical_volume_parity_claim_allowed": candidate[
                "physical_volume_parity_claim_allowed"
            ],
            "presentation_only_volume_disclaimer": candidate.get(
                "presentation_only_volume_disclaimer"
            ),
            "presentation_only_shape_disclaimer": candidate.get(
                "presentation_only_shape_disclaimer"
            ),
            "free_surface_shape_claim_allowed": candidate.get(
                "free_surface_shape_claim_allowed"
            ),
            "fluid_dynamics_claim_allowed": candidate.get(
                "fluid_dynamics_claim_allowed"
            ),
        }
        if accepted.accepted_authority_bundle_sha256 is not None:
            authority_contract = accepted.accepted_authority or {}
            manifest.update(
                {
                    "accepted_authority_bundle_path": str(
                        accepted.accepted_authority_bundle_path
                    ),
                    "accepted_authority_bundle_sha256": (
                        accepted.accepted_authority_bundle_sha256
                    ),
                    "layout_semantics": authority_contract.get(
                        "layout_semantics"
                    ),
                    "exact_expert_episode_layout": authority_contract.get(
                        "exact_expert_episode_layout"
                    ),
                    "old_physics_authority_applies_to_support_aligned_stage": False,
                }
            )
        for key in (
            "surface_model_version",
            "surface_model_contract",
            "surface_model_contract_sha256",
            "display_proxy_volume_disclaimer",
        ):
            if key in candidate:
                manifest[key] = deepcopy(candidate[key])
        manifests[candidate_id] = manifest
    if any(manifest["input_identity"] != identity for manifest in manifests.values()):
        raise AssertionError("candidate_input_identity_diverged")
    return manifests


def validate_candidate_frame_contracts_against_accepted(
    contract: Mapping[str, Any],
    accepted: AcceptedReplayInput,
) -> dict[str, Any]:
    """Recompute candidate frame contracts from the immutable accepted trace."""
    candidate_id = str(contract.get("candidate_id", ""))
    if candidate_id not in REFERENCE_CANDIDATE_IDS:
        raise ValueError(f"candidate_frame_contract_id_invalid:{candidate_id}")
    recomputed = build_candidate_replay_contracts(accepted)[candidate_id]
    if contract.get("physical_trace_identity") != accepted.physical_trace_identity:
        raise ValueError("candidate_frame_contract_physical_trace_identity_mismatch")
    descriptor_fields = (
        "candidate_id",
        "display_width",
        "voxel_size",
        "width_to_interior_ratio",
        "interior_diameter",
        "proxy_mode",
        "presentation_kind",
        "presentation_primitive_path",
        "surface_model_version",
        "surface_model_contract",
        "surface_model_contract_sha256",
        "display_proxy_volume_disclaimer",
        "physical_volume_parity_claim_allowed",
        "free_surface_shape_claim_allowed",
        "fluid_dynamics_claim_allowed",
    )
    if any(
        contract.get(field) != recomputed.get(field)
        for field in descriptor_fields
    ):
        raise ValueError(
            f"candidate_descriptor_contract_mismatch:{candidate_id}"
        )
    if contract.get("frames") != recomputed["frames"]:
        raise ValueError(f"candidate_frame_contract_mismatch:{candidate_id}")
    if contract.get("frame_indices") != recomputed["frame_indices"]:
        raise ValueError(f"candidate_frame_indices_mismatch:{candidate_id}")
    return {
        "validated": True,
        "candidate_id": candidate_id,
        "frame_count": len(recomputed["frames"]),
        "frame_contracts_sha256": _json_sha256(recomputed["frames"]),
        "physical_trace_sha256": accepted.physical_trace_identity[
            "physical_trace_sha256"
        ],
        "accepted_trace_sha256": accepted.trace_sha256,
    }


def _atomic_write_bytes_pinned(
    path: str | os.PathLike[str],
    payload: bytes,
) -> None:
    target = _reject_symlink_path_components(
        path,
        label="atomic_write_target",
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = f".{target.name}.{secrets.token_hex(16)}.tmp"
    with _open_pinned_path(
        target.parent,
        leaf_directory=True,
        label="atomic_write_parent",
    ) as (_parent, directory_descriptor, identities):
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(
            temporary_name,
            flags,
            0o600,
            dir_fd=directory_descriptor,
        )
        try:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("atomic_write_short_write")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            _verify_pinned_path_components(
                identities,
                label="atomic_write_parent",
            )
            os.replace(
                temporary_name,
                target.name,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
            )
            os.fsync(directory_descriptor)
            _verify_pinned_path_components(
                identities,
                label="atomic_write_parent",
            )
        finally:
            try:
                os.unlink(temporary_name, dir_fd=directory_descriptor)
            except FileNotFoundError:
                pass


def atomic_write_json(path: str | os.PathLike[str], payload: Mapping[str, Any]) -> None:
    encoded = (
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    _atomic_write_bytes_pinned(path, encoded)


def atomic_write_json_gzip(
    path: str | os.PathLike[str],
    payload: Mapping[str, Any],
) -> None:
    """Write deterministic level-1 gzip JSON through an atomic rename."""
    encoded = (
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    buffer = io.BytesIO()
    with gzip.GzipFile(
        filename="",
        mode="wb",
        compresslevel=1,
        fileobj=buffer,
        mtime=0,
    ) as compressed_stream:
        compressed_stream.write(encoded)
    _atomic_write_bytes_pinned(path, buffer.getvalue())


def _artifact_relative_path(candidate_dir: Path, path: Path) -> str:
    resolved_dir = candidate_dir.resolve()
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(resolved_dir))
    except ValueError as exc:
        raise ValueError(f"candidate_artifact_outside_run_scope:{resolved}") from exc


def _validate_nonempty_artifact(path: Path, *, label: str) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError(f"candidate_artifact_missing:{label}:{path}")


def _validate_png(path: Path, *, width: int, height: int) -> dict[str, Any]:
    from PIL import Image

    _validate_nonempty_artifact(path, label="image")
    try:
        with _open_image_file_snapshot(
            path,
            label="candidate_image",
        ) as image:
            image.load()
            image_format = str(image.format)
            image_mode = str(image.mode)
            image_size = tuple(int(value) for value in image.size)
    except Exception as exc:
        raise ValueError(
            f"candidate_image_not_decodable:{path}:{type(exc).__name__}:{exc}"
        ) from exc
    if image_format != "PNG":
        raise ValueError(f"candidate_image_not_png:{path}:{image_format}")
    if image_mode != "RGB":
        raise ValueError(f"candidate_image_not_rgb:{path}:{image_mode}")
    if image_size != (width, height):
        raise ValueError(
            f"candidate_image_size_mismatch:{path}:"
            f"actual={image_size}:expected={(width, height)}"
        )
    return {
        "path": str(path.resolve()),
        "decodable": True,
        "format": image_format,
        "mode": image_mode,
        "width": image_size[0],
        "height": image_size[1],
    }


def probe_mp4_frame_count(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Decode every MP4 frame instead of trusting container frame metadata."""
    import cv2

    target = Path(path)
    _validate_nonempty_artifact(target, label="video")
    capture = cv2.VideoCapture(str(target))
    try:
        if not capture.isOpened():
            raise ValueError(f"candidate_video_not_decodable:{target}")
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps <= 0.0:
            raise ValueError(f"candidate_video_fps_invalid:{target}:{fps}")
        frame_count = 0
        frame_shape: list[int] | None = None
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame is None or frame.ndim != 3 or frame.shape[2] < 3:
                raise ValueError(f"candidate_video_frame_invalid:{target}:{frame_count}")
            shape = [int(value) for value in frame.shape]
            if frame_shape is None:
                frame_shape = shape
            elif shape != frame_shape:
                raise ValueError(
                    f"candidate_video_frame_shape_changed:{target}:"
                    f"{frame_shape}!={shape}"
                )
            frame_count += 1
    finally:
        capture.release()
    if frame_count <= 0 or frame_shape is None:
        raise ValueError(f"candidate_video_has_no_decodable_frames:{target}")
    return {
        "path": str(target.resolve()),
        "decodable": True,
        "frame_count": frame_count,
        "frame_shape": frame_shape,
        "width": frame_shape[1],
        "height": frame_shape[0],
        "fps": fps,
    }


def probe_mp4_against_png_frames(
    path: str | os.PathLike[str],
    frame_paths: Sequence[str | os.PathLike[str]],
    *,
    maximum_mean_absolute_error: float = 8.0,
    minimum_psnr_db: float = 28.0,
) -> dict[str, Any]:
    """Decode an MP4 and compare every lossy frame with its ordered source PNG."""
    import cv2
    import numpy as np

    target = Path(path).expanduser().resolve()
    references = [Path(value).expanduser().resolve() for value in frame_paths]
    if not references:
        raise ValueError("candidate_video_reference_frames_empty")
    _validate_nonempty_artifact(target, label="video")
    for reference in references:
        _validate_nonempty_artifact(reference, label="video_reference_image")
    capture = cv2.VideoCapture(str(target))
    if not capture.isOpened():
        capture.release()
        raise ValueError(f"candidate_video_not_decodable:{target}")
    frame_count = 0
    frame_shape: list[int] | None = None
    frame_metrics: list[dict[str, Any]] = []
    comparison_shape_mismatch = False
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps <= 0.0:
            raise ValueError(f"candidate_video_fps_invalid:{target}:{fps}")
        while True:
            ok, decoded = capture.read()
            if not ok:
                break
            if decoded is None or decoded.ndim != 3 or decoded.shape[2] < 3:
                raise ValueError(
                    f"candidate_video_frame_invalid:{target}:{frame_count}"
                )
            shape = [int(value) for value in decoded.shape]
            if frame_shape is None:
                frame_shape = shape
            elif shape != frame_shape:
                raise ValueError(
                    f"candidate_video_frame_shape_changed:{target}:"
                    f"{frame_shape}!={shape}"
                )
            if frame_count < len(references):
                reference = cv2.imread(
                    str(references[frame_count]),
                    cv2.IMREAD_COLOR,
                )
                if reference is None or reference.shape != decoded.shape:
                    comparison_shape_mismatch = True
                else:
                    difference = reference.astype(np.float32) - decoded.astype(
                        np.float32
                    )
                    absolute_error = np.abs(difference)
                    mean_absolute_error = float(absolute_error.mean())
                    mean_squared_error = float((difference * difference).mean())
                    psnr_db = (
                        99.0
                        if mean_squared_error == 0.0
                        else 10.0
                        * math.log10((255.0 * 255.0) / mean_squared_error)
                    )
                    frame_metrics.append(
                        {
                            "frame_offset": frame_count,
                            "source_png_path": str(references[frame_count]),
                            "source_png_sha256": _sha256_file(
                                references[frame_count]
                            ),
                            "mean_absolute_error": mean_absolute_error,
                            "psnr_db": psnr_db,
                            "maximum_absolute_error": float(
                                absolute_error.max()
                            ),
                        }
                    )
            frame_count += 1
    finally:
        capture.release()
    if frame_count <= 0 or frame_shape is None:
        raise ValueError(f"candidate_video_has_no_decodable_frames:{target}")
    maximum_observed_mae = (
        max(item["mean_absolute_error"] for item in frame_metrics)
        if frame_metrics
        else float("inf")
    )
    minimum_observed_psnr = (
        min(item["psnr_db"] for item in frame_metrics)
        if frame_metrics
        else float("-inf")
    )
    sequence_bound = (
        frame_count == len(references)
        and len(frame_metrics) == len(references)
        and not comparison_shape_mismatch
        and maximum_observed_mae <= float(maximum_mean_absolute_error)
        and minimum_observed_psnr >= float(minimum_psnr_db)
    )
    source_sequence = [
        {"path": str(reference), "sha256": _sha256_file(reference)}
        for reference in references
    ]
    return {
        "path": str(target),
        "decodable": True,
        "frame_count": frame_count,
        "frame_shape": frame_shape,
        "width": frame_shape[1],
        "height": frame_shape[0],
        "fps": fps,
        "source_frame_count": len(references),
        "source_frame_sequence": source_sequence,
        "source_frame_sequence_sha256": _json_sha256(source_sequence),
        "frame_content_metrics": frame_metrics,
        "maximum_frame_mean_absolute_error": maximum_observed_mae,
        "minimum_frame_psnr_db": minimum_observed_psnr,
        "maximum_allowed_mean_absolute_error": float(
            maximum_mean_absolute_error
        ),
        "minimum_required_psnr_db": float(minimum_psnr_db),
        "comparison_shape_mismatch": comparison_shape_mismatch,
        "content_sequence_bound": sequence_bound,
    }


def _normalize_new_usd_layer_private_writable(
    layer: Any,
    path: str | os.PathLike[str],
    *,
    label: str,
) -> None:
    target = Path(path).expanduser().resolve()
    target.chmod(0o600)
    if stat.S_IMODE(target.stat().st_mode) != 0o600:
        raise RuntimeError(f"{label}_private_mode_failed:{target}")
    if not layer.permissionToEdit or not layer.permissionToSave:
        raise RuntimeError(f"{label}_writable_readback_failed:{target}")


def begin_candidate_presentation_layer(
    stage: Any,
    path: str | os.PathLike[str],
) -> Any:
    """Add a file-backed presentation layer below the stage session layer."""
    from pxr import Sdf, Usd

    session_layer = stage.GetSessionLayer()
    if session_layer is None:
        raise RuntimeError("stage_session_layer_missing")
    session_root_paths = {str(prim.path) for prim in session_layer.rootPrims}
    unexpected_session_roots = session_root_paths - set(
        ALLOWED_KIT_RUNTIME_SESSION_ROOT_PATHS
    )
    if unexpected_session_roots or session_layer.subLayerPaths:
        raise RuntimeError(
            "session_layer_scene_opinions_present:"
            f"unexpected_roots={sorted(unexpected_session_roots)}:"
            f"sublayers={len(session_layer.subLayerPaths)}"
        )
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError(f"presentation_layer_already_exists:{target}")
    layer = Sdf.Layer.CreateNew(str(target))
    if layer is None:
        raise RuntimeError(f"presentation_layer_create_failed:{target}")
    _normalize_new_usd_layer_private_writable(
        layer,
        target,
        label="presentation_layer",
    )
    session_layer.subLayerPaths.insert(0, layer.identifier)
    stage.SetEditTarget(Usd.EditTarget(layer))
    if stage.GetEditTarget().GetLayer().identifier != layer.identifier:
        raise RuntimeError(f"presentation_layer_edit_target_failed:{target}")
    return layer


def _beaker_source_layer_stack(stage: Any) -> list[dict[str, Any]]:
    layers = stage.GetLayerStack(False)
    result = []
    for layer in layers:
        content = layer.ExportToString().encode("utf-8")
        real_path = str(layer.realPath or "")
        entry = {
            "identifier": str(layer.identifier),
            "real_path": real_path or None,
            "dirty": bool(layer.dirty),
            "content_sha256": hashlib.sha256(content).hexdigest(),
            "file_sha256": None,
        }
        if real_path:
            file_path = Path(real_path).resolve(strict=True)
            entry["file_sha256"] = _sha256_file(file_path)
        result.append(entry)
    return result


def _normal_value_block_layers(attribute: Any) -> list[str]:
    from pxr import Sdf, Usd

    layers = []
    for spec in attribute.GetPropertyStack(Usd.TimeCode.Default()):
        if isinstance(spec, Sdf.AttributeSpec) and isinstance(
            spec.default, Sdf.ValueBlock
        ):
            layers.append(str(spec.layer.identifier))
    return layers


def _beaker_mesh_signature(stage: Any, path: str) -> dict[str, Any]:
    from pxr import UsdGeom, UsdShade

    prim = stage.GetPrimAtPath(path)
    if not prim.IsValid() or not prim.IsA(UsdGeom.Mesh):
        raise ValueError(f"beaker_normal_mesh_missing:{path}")
    mesh = UsdGeom.Mesh(prim)
    points = _canonical_usd_value(mesh.GetPointsAttr().Get())
    counts = _canonical_usd_value(mesh.GetFaceVertexCountsAttr().Get())
    indices = _canonical_usd_value(mesh.GetFaceVertexIndicesAttr().Get())
    normals_attr = mesh.GetNormalsAttr()
    block_layers = _normal_value_block_layers(normals_attr)
    normals = _canonical_usd_value(normals_attr.Get())
    parent = prim.GetParent()
    xform_ops = []
    for op in UsdGeom.Xformable(parent).GetOrderedXformOps():
        xform_ops.append(
            {
                "name": op.GetOpName(),
                "type": str(op.GetOpType()),
                "precision": str(op.GetPrecision()),
                "value": _canonical_usd_value(op.Get()),
            }
        )
    material, _relationship = UsdShade.MaterialBindingAPI(
        prim
    ).ComputeBoundMaterial()
    physics_attributes = {}
    for attribute in prim.GetAttributes():
        name = attribute.GetName()
        if name.lower().startswith(("physics:", "physx")):
            physics_attributes[name] = _canonical_usd_value(attribute.Get())
    physics_relationships = {}
    for relationship in prim.GetRelationships():
        name = relationship.GetName()
        if name.lower().startswith(("physics:", "physx")):
            physics_relationships[name] = [
                str(target) for target in relationship.GetTargets()
            ]
    topology = {"face_vertex_counts": counts, "face_vertex_indices": indices}
    immutable = {
        "prim_path": path,
        "points_sha256": _json_sha256(points),
        "topology_sha256": _json_sha256(topology),
        "subdivision_scheme": str(mesh.GetSubdivisionSchemeAttr().Get()),
        "double_sided": bool(mesh.GetDoubleSidedAttr().Get()),
        "parent_xform_ops": xform_ops,
        "material_binding": str(material.GetPath()) if material else None,
        "applied_schemas": sorted(str(value) for value in prim.GetAppliedSchemas()),
        "physics_attributes": physics_attributes,
        "physics_relationships": physics_relationships,
    }
    immutable["physics_sha256"] = _json_sha256(
        {
            "applied_schemas": immutable["applied_schemas"],
            "attributes": physics_attributes,
            "relationships": physics_relationships,
        }
    )
    immutable["immutable_mesh_sha256"] = _json_sha256(immutable)
    signature = {
        **immutable,
        "normals_sha256": _json_sha256(normals) if normals is not None else None,
        "normals_count": len(normals) if isinstance(normals, list) else None,
        "normals_interpolation": str(mesh.GetNormalsInterpolation()),
        "normal_value_block_layers": block_layers,
        "composed_normals_present": normals is not None,
    }
    signature["source_mesh_signature_sha256"] = _json_sha256(signature)
    return signature


def _validate_beaker_normal_contract_hash(contract: Mapping[str, Any]) -> None:
    payload = deepcopy(dict(contract))
    expected = payload.pop("beaker_normal_remediation_contract_sha256", None)
    if not isinstance(expected, str) or expected != _json_sha256(payload):
        raise ValueError("beaker_normal_remediation_contract_sha256_mismatch")


def build_beaker_normal_matrix_equivalence_projection(
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(contract, Mapping):
        raise ValueError("beaker_normal_matrix_projection_contract_not_object")
    _validate_beaker_normal_contract_hash(contract)
    projected = _json_native_copy(dict(contract))
    removed_json_pointers = [
        "/beaker_normal_remediation_contract_sha256",
        "/source_usd_path",
        "/source_layer_stack/*/identifier",
        "/source_layer_stack/*/real_path",
    ]
    for field in (
        "beaker_normal_remediation_contract_sha256",
        "source_usd_path",
    ):
        if field not in projected:
            raise ValueError(f"beaker_normal_matrix_projection_field_missing:{field}")
        del projected[field]
    source_layers = projected.get("source_layer_stack")
    if not isinstance(source_layers, list):
        raise ValueError("beaker_normal_matrix_projection_source_layer_stack_invalid")
    for index, layer in enumerate(source_layers):
        if not isinstance(layer, dict):
            raise ValueError(
                f"beaker_normal_matrix_projection_source_layer_invalid:{index}"
            )
        for field in ("identifier", "real_path"):
            if field not in layer:
                raise ValueError(
                    "beaker_normal_matrix_projection_layer_field_missing:"
                    f"{index}:{field}"
                )
            del layer[field]
    return {
        "schema_version": 1,
        "projection_id": BEAKER_NORMAL_MATRIX_PROJECTION_ID,
        "removed_json_pointers": removed_json_pointers,
        "projected_contract": projected,
        "canonical_json_utf8_sha256": canonical_json_sha256_v1(projected),
    }


def build_beaker_normals_block_contract(
    stage: Any,
    *,
    source_usd_path: str | os.PathLike[str],
    source_usd_sha256: str,
) -> dict[str, Any]:
    source_path = Path(source_usd_path).expanduser().resolve(strict=True)
    expected_source_hash = _require_sha256(
        "beaker_normal_source_usd_sha256", source_usd_sha256
    )
    if _sha256_file(source_path) != expected_source_hash:
        raise ValueError("beaker_normal_source_usd_sha256_mismatch")
    root_real_path = Path(stage.GetRootLayer().realPath).resolve(strict=True)
    if root_real_path != source_path:
        raise ValueError("beaker_normal_source_root_path_mismatch")
    source_layers = _beaker_source_layer_stack(stage)
    dirty_layers = [item["identifier"] for item in source_layers if item["dirty"]]
    if dirty_layers:
        raise RuntimeError(
            "beaker_normal_source_layer_dirty:" + ",".join(dirty_layers)
        )
    signatures = {}
    for path in BEAKER_NORMAL_MESH_PATHS:
        signature = _beaker_mesh_signature(stage, path)
        if signature["normal_value_block_layers"]:
            raise ValueError(f"beaker_source_normals_preblocked:{path}")
        if not signature["composed_normals_present"]:
            raise ValueError(f"beaker_source_normals_missing:{path}")
        if signature["normals_interpolation"] != "faceVarying":
            raise ValueError(f"beaker_source_normals_interpolation_invalid:{path}")
        signatures[path] = signature
    contract: dict[str, Any] = {
        "schema_version": 1,
        "normal_remediation_id": BEAKER_NORMAL_REMEDIATION_ID,
        "renderer_acceptance_scope": BEAKER_NORMAL_RENDERER_SCOPE,
        "mesh_paths": list(BEAKER_NORMAL_MESH_PATHS),
        "source_usd_path": str(source_path),
        "source_usd_sha256": expected_source_hash,
        "source_layer_stack": source_layers,
        "source_mesh_signatures": signatures,
        "authoring_mode": "presentation_layer_normals_value_block_only",
        "normal_recomputation_performed": False,
        "rtx_generated_normals_readback_claimed": False,
        "rtx_generated_normals_hashed": False,
        "native_normal_fidelity": False,
        "source_geometry_mutation_allowed": False,
        "source_physics_mutation_allowed": False,
    }
    contract["beaker_normal_remediation_contract_sha256"] = _json_sha256(contract)
    return contract


def _assert_beaker_source_unchanged(
    stage: Any, contract: Mapping[str, Any], *, require_normals: bool
) -> None:
    from pxr import Usd

    source_path = Path(str(contract["source_usd_path"]))
    if _sha256_file(source_path) != contract["source_usd_sha256"]:
        raise RuntimeError("beaker_normal_source_file_changed")
    current_root_real_path = str(stage.GetRootLayer().realPath or "")
    if current_root_real_path and Path(current_root_real_path).resolve() == source_path:
        source_layers = _beaker_source_layer_stack(stage)
    else:
        source_stage = Usd.Stage.Open(str(source_path), Usd.Stage.LoadAll)
        if source_stage is None:
            raise RuntimeError("beaker_normal_source_reopen_failed")
        source_layers = _beaker_source_layer_stack(source_stage)
    if source_layers != contract["source_layer_stack"]:
        raise RuntimeError("beaker_normal_source_layers_changed")
    for path in contract["mesh_paths"]:
        current = _beaker_mesh_signature(stage, path)
        expected = contract["source_mesh_signatures"][path]
        if current["immutable_mesh_sha256"] != expected["immutable_mesh_sha256"]:
            raise RuntimeError(f"beaker_normal_source_signature_changed:{path}")
        if require_normals and current != expected:
            raise RuntimeError(f"beaker_normal_source_signature_changed:{path}")


def verify_beaker_normals_block(
    stage: Any, *, contract: Mapping[str, Any]
) -> dict[str, Any]:
    from pxr import UsdGeom

    _validate_beaker_normal_contract_hash(contract)
    if (
        contract.get("normal_remediation_id") != BEAKER_NORMAL_REMEDIATION_ID
        or contract.get("renderer_acceptance_scope")
        != BEAKER_NORMAL_RENDERER_SCOPE
    ):
        raise RuntimeError("beaker_normals_block_contract_identity_invalid")
    _assert_beaker_source_unchanged(stage, contract, require_normals=False)
    block_layers = {}
    for path in contract["mesh_paths"]:
        mesh = UsdGeom.Mesh(stage.GetPrimAtPath(path))
        attribute = mesh.GetNormalsAttr()
        layers = _normal_value_block_layers(attribute)
        if attribute.Get() is not None or len(layers) != 1:
            raise RuntimeError(f"beaker_normals_block_incomplete:{path}")
        block_layers[path] = layers[0]
    if len(set(block_layers.values())) != 1:
        raise RuntimeError("beaker_normals_block_layer_diverged")
    return {
        "verified": True,
        "normal_remediation_id": BEAKER_NORMAL_REMEDIATION_ID,
        "renderer_acceptance_scope": BEAKER_NORMAL_RENDERER_SCOPE,
        "blocked_mesh_paths": list(contract["mesh_paths"]),
        "normal_block_layer_identifier": next(iter(block_layers.values())),
        "source_layer_stack": deepcopy(contract["source_layer_stack"]),
        "beaker_normal_remediation_contract_sha256": contract[
            "beaker_normal_remediation_contract_sha256"
        ],
        "rtx_generated_normals_readback_claimed": False,
        "rtx_generated_normals_hashed": False,
    }


def author_beaker_normals_block(
    stage: Any,
    *,
    contract: Mapping[str, Any],
    presentation_layer: Any,
) -> dict[str, Any]:
    from pxr import Sdf, UsdGeom

    _validate_beaker_normal_contract_hash(contract)
    if stage.GetEditTarget().GetLayer().identifier != presentation_layer.identifier:
        raise RuntimeError("beaker_normals_block_edit_target_mismatch")
    _assert_beaker_source_unchanged(stage, contract, require_normals=True)
    source_root_snapshot = stage.GetRootLayer().ExportToString()
    for path in contract["mesh_paths"]:
        mesh = UsdGeom.Mesh(stage.GetPrimAtPath(path))
        mesh.GetNormalsAttr().Block()
        spec = presentation_layer.GetAttributeAtPath(Sdf.Path(f"{path}.normals"))
        if spec is None or not isinstance(spec.default, Sdf.ValueBlock):
            raise RuntimeError(f"beaker_normals_value_block_not_authored:{path}")
    if stage.GetRootLayer().ExportToString() != source_root_snapshot:
        raise RuntimeError("beaker_normals_block_mutated_source_root")
    verified = verify_beaker_normals_block(stage, contract=contract)
    if verified["normal_block_layer_identifier"] != presentation_layer.identifier:
        raise RuntimeError("beaker_normals_block_wrong_layer")
    return verified


class SessionLayerValidationError(RuntimeError):
    """Carry an auditable session-layer contract with a strict export failure."""

    def __init__(self, message: str, contract: Mapping[str, Any]):
        self.session_layer_contract = deepcopy(dict(contract))
        super().__init__(message)


class PresentationLayerPermissionRecoveryError(RuntimeError):
    """Carry the exact partial presentation-save recovery evidence."""

    def __init__(self, message: str, contract: Mapping[str, Any]):
        self.presentation_layer_export_permission_recovery = deepcopy(dict(contract))
        super().__init__(message)


_PERMISSION_RECOVERY_PHASES = (
    "before_recovery",
    "after_recovery",
    "after_save",
    "after_relock",
)


def _empty_permission_recovery_phase_map() -> dict[str, Any]:
    return {phase: None for phase in _PERMISSION_RECOVERY_PHASES}


def _empty_layer_identity() -> dict[str, Any]:
    return {
        "identifier": None,
        "real_path": None,
        "device": None,
        "inode": None,
        "link_count": None,
    }


def _permission_pair(layer: Any) -> dict[str, bool]:
    return {
        "permission_to_edit": bool(layer.permissionToEdit),
        "permission_to_save": bool(layer.permissionToSave),
    }


def _verified_file_backed_layer_identity(
    layer: Any,
    *,
    expected_path: str | os.PathLike[str],
    label: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    identifier = getattr(layer, "identifier", None)
    real_path = getattr(layer, "realPath", None)
    if (
        not isinstance(identifier, str)
        or not identifier
        or not isinstance(real_path, str)
        or not real_path
        or "://" in real_path
        or not Path(real_path).is_absolute()
    ):
        raise ValueError(f"{label}_not_local_file_backed")
    expected = _reject_symlink_path_components(expected_path, label=label)
    if _absolute_path_without_symlink_resolution(real_path) != expected:
        raise ValueError(f"{label}_unexpected_real_path:{real_path}!={expected}")
    evidence = _read_pinned_regular_file_evidence(expected, label=label)
    identity = {
        "identifier": identifier,
        "real_path": evidence["path"],
        "device": evidence["device"],
        "inode": evidence["inode"],
        "link_count": evidence["link_count"],
    }
    return identity, evidence


def _new_presentation_permission_recovery_contract() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract_id": "presentation_layer_export_permission_recovery_v1",
        "status": "FAIL",
        "failure_stage": None,
        "secondary_failure_stage": None,
        "presentation_layer": _empty_layer_identity(),
        "source_root_layer": _empty_layer_identity(),
        "presentation_permissions": _empty_permission_recovery_phase_map(),
        "source_permissions": _empty_permission_recovery_phase_map(),
        "recovery_attempted": False,
        "set_edit_attempted": False,
        "set_save_attempted": False,
        "set_edit_readback": None,
        "set_save_readback": None,
        "save_attempted": False,
        "save_succeeded": False,
        "relock_attempted": False,
        "relock_succeeded": False,
        "source_file_sha256": _empty_permission_recovery_phase_map(),
        "source_layer_snapshot_sha256": _empty_permission_recovery_phase_map(),
        "presentation_file_sha256": _empty_permission_recovery_phase_map(),
        "presentation_layer_snapshot_sha256": (
            _empty_permission_recovery_phase_map()
        ),
        "presentation_path_identity": _empty_permission_recovery_phase_map(),
        "source_path_identity": _empty_permission_recovery_phase_map(),
    }


def validate_presentation_layer_export_permission_recovery_contract(
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    expected_fields = set(_new_presentation_permission_recovery_contract())
    if not isinstance(contract, Mapping) or set(contract) != expected_fields:
        raise ValueError("permission_recovery_contract_schema_invalid")
    actual = _json_native_copy(dict(contract))
    if (
        actual.get("schema_version") != 1
        or actual.get("contract_id")
        != "presentation_layer_export_permission_recovery_v1"
        or actual.get("status") not in {"PASS", "FAIL"}
        or actual.get("failure_stage")
        not in {
            None,
            "IDENTITY_PREFLIGHT",
            "SET_EDIT",
            "SET_SAVE",
            "RECOVERY_READBACK",
            "SAVE",
            "POST_SAVE_EVIDENCE",
            "POST_SAVE_SOURCE_GUARD",
            "RELOCK",
        }
        or actual.get("secondary_failure_stage") not in {None, "RELOCK"}
    ):
        raise ValueError("permission_recovery_contract_invalid")
    identity_fields = {"identifier", "real_path", "device", "inode", "link_count"}
    layer_identity_full = {}
    for key in ("presentation_layer", "source_root_layer"):
        identity = actual.get(key)
        if not isinstance(identity, Mapping) or set(identity) != identity_fields:
            raise ValueError("permission_recovery_contract_schema_invalid")
        values = list(identity.values())
        if not (all(value is None for value in values) or all(value is not None for value in values)):
            raise ValueError("permission_recovery_contract_invalid")
        full = all(value is not None for value in values)
        layer_identity_full[key] = full
        if full and (
            not isinstance(identity["identifier"], str)
            or not isinstance(identity["real_path"], str)
            or not Path(identity["real_path"]).is_absolute()
            or type(identity["device"]) is not int
            or type(identity["inode"]) is not int
            or identity["link_count"] != 1
        ):
            raise ValueError("permission_recovery_contract_invalid")
    phase_map_keys = (
        "presentation_permissions",
        "source_permissions",
        "source_file_sha256",
        "source_layer_snapshot_sha256",
        "presentation_file_sha256",
        "presentation_layer_snapshot_sha256",
        "presentation_path_identity",
        "source_path_identity",
    )
    for key in phase_map_keys:
        phases = actual.get(key)
        if not isinstance(phases, Mapping) or set(phases) != set(_PERMISSION_RECOVERY_PHASES):
            raise ValueError("permission_recovery_contract_schema_invalid")
    permission_keys = ("presentation_permissions", "source_permissions")
    sha_keys = (
        "source_file_sha256",
        "source_layer_snapshot_sha256",
        "presentation_file_sha256",
        "presentation_layer_snapshot_sha256",
    )
    path_identity_keys = ("presentation_path_identity", "source_path_identity")
    path_identity_fields = {
        "real_path",
        "file_type",
        "device",
        "inode",
        "link_count",
    }
    reached = {}
    for phase in _PERMISSION_RECOVERY_PHASES:
        phase_values = [actual[key][phase] for key in phase_map_keys]
        if not (
            all(value is None for value in phase_values)
            or all(value is not None for value in phase_values)
        ):
            raise ValueError("permission_recovery_contract_phase_partial")
        reached[phase] = all(value is not None for value in phase_values)
        if not reached[phase]:
            continue
        for key in permission_keys:
            value = actual[key][phase]
            if (
                not isinstance(value, Mapping)
                or set(value) != {"permission_to_edit", "permission_to_save"}
                or type(value["permission_to_edit"]) is not bool
                or type(value["permission_to_save"]) is not bool
            ):
                raise ValueError("permission_recovery_contract_invalid")
        if any(not _is_sha256_text(actual[key][phase]) for key in sha_keys):
            raise ValueError("permission_recovery_contract_invalid")
        for key in path_identity_keys:
            value = actual[key][phase]
            if (
                not isinstance(value, Mapping)
                or set(value) != path_identity_fields
                or not isinstance(value["real_path"], str)
                or not Path(value["real_path"]).is_absolute()
                or value["file_type"] != "regular_non_symlink"
                or type(value["device"]) is not int
                or type(value["inode"]) is not int
                or value["link_count"] != 1
            ):
                raise ValueError("permission_recovery_contract_invalid")
    boolean_fields = (
        "recovery_attempted",
        "set_edit_attempted",
        "set_save_attempted",
        "save_attempted",
        "save_succeeded",
        "relock_attempted",
        "relock_succeeded",
    )
    if any(type(actual.get(key)) is not bool for key in boolean_fields):
        raise ValueError("permission_recovery_contract_invalid")
    if any(actual.get(key) not in {None, True, False} for key in ("set_edit_readback", "set_save_readback")):
        raise ValueError("permission_recovery_contract_invalid")
    if (
        actual["recovery_attempted"]
        != (actual["set_edit_attempted"] or actual["set_save_attempted"])
        or (not actual["set_edit_attempted"] and actual["set_edit_readback"] is not None)
        or (not actual["set_save_attempted"] and actual["set_save_readback"] is not None)
        or (actual["save_succeeded"] and not actual["save_attempted"])
        or (actual["relock_succeeded"] and not actual["relock_attempted"])
        or reached["after_recovery"] and not reached["before_recovery"]
        or reached["after_save"] and not reached["after_recovery"]
        or actual["save_attempted"] and not reached["after_recovery"]
        or (reached["after_relock"] and not actual["relock_attempted"])
    ):
        raise ValueError("permission_recovery_contract_invalid")
    if actual["failure_stage"] != "IDENTITY_PREFLIGHT" and not all(
        layer_identity_full.values()
    ):
        raise ValueError("permission_recovery_contract_invalid")
    if actual["secondary_failure_stage"] == "RELOCK" and (
        actual["failure_stage"] in {None, "RELOCK"}
        or actual["relock_succeeded"]
    ):
        raise ValueError("permission_recovery_contract_invalid")
    if actual["failure_stage"] == "RELOCK" and actual["secondary_failure_stage"] is not None:
        raise ValueError("permission_recovery_contract_invalid")
    if actual["status"] == "PASS":
        final_permissions = actual["presentation_permissions"]["after_relock"]
        source_final = actual["source_permissions"]["after_relock"]
        if (
            actual["failure_stage"] is not None
            or actual["secondary_failure_stage"] is not None
            or not actual["save_succeeded"]
            or not actual["save_attempted"]
            or not actual["relock_succeeded"]
            or not all(layer_identity_full.values())
            or not all(reached.values())
            or actual["set_edit_attempted"]
            != (
                not actual["presentation_permissions"]["before_recovery"][
                    "permission_to_edit"
                ]
            )
            or actual["set_save_attempted"]
            != (
                not actual["presentation_permissions"]["before_recovery"][
                    "permission_to_save"
                ]
            )
            or (
                actual["set_edit_attempted"]
                and actual["set_edit_readback"] is not True
            )
            or (
                actual["set_save_attempted"]
                and actual["set_save_readback"] is not True
            )
            or actual["presentation_permissions"]["after_recovery"]
            != {"permission_to_edit": True, "permission_to_save": True}
            or actual["presentation_permissions"]["after_save"]
            != {"permission_to_edit": True, "permission_to_save": True}
            or final_permissions
            != {"permission_to_edit": False, "permission_to_save": False}
            or source_final
            != {"permission_to_edit": False, "permission_to_save": False}
            or actual["source_file_sha256"]["before_recovery"]
            != actual["source_file_sha256"]["after_relock"]
            or actual["source_path_identity"]["before_recovery"]
            != actual["source_path_identity"]["after_relock"]
            or len(
                {
                    actual["source_file_sha256"][phase]
                    for phase in _PERMISSION_RECOVERY_PHASES
                }
            )
            != 1
            or len(
                {
                    actual["source_layer_snapshot_sha256"][phase]
                    for phase in _PERMISSION_RECOVERY_PHASES
                }
            )
            != 1
            or any(
                actual["source_path_identity"][phase]
                != actual["source_path_identity"]["before_recovery"]
                for phase in _PERMISSION_RECOVERY_PHASES
            )
            or actual["presentation_path_identity"]["after_recovery"]
            != actual["presentation_path_identity"]["before_recovery"]
            or actual["presentation_path_identity"]["after_relock"]
            != actual["presentation_path_identity"]["after_save"]
            or actual["presentation_file_sha256"]["after_recovery"]
            != actual["presentation_file_sha256"]["before_recovery"]
            or actual["presentation_file_sha256"]["after_relock"]
            != actual["presentation_file_sha256"]["after_save"]
        ):
            raise ValueError("permission_recovery_contract_invalid")
    else:
        stage = actual["failure_stage"]
        invalid_failure_state = (
            stage is None
            or (stage != "IDENTITY_PREFLIGHT" and not actual["relock_attempted"])
            or (stage == "RELOCK" and actual["relock_succeeded"])
            or (
                stage == "SET_EDIT"
                and (
                    not reached["before_recovery"]
                    or not actual["set_edit_attempted"]
                    or reached["after_recovery"]
                    or actual["save_attempted"]
                )
            )
            or (
                stage == "SET_SAVE"
                and (
                    not reached["before_recovery"]
                    or not actual["set_save_attempted"]
                    or reached["after_recovery"]
                    or actual["save_attempted"]
                )
            )
            or (
                stage == "RECOVERY_READBACK"
                and (
                    not reached["before_recovery"]
                    or reached["after_recovery"]
                    or actual["save_attempted"]
                )
            )
            or (
                stage == "SAVE"
                and (
                    not reached["after_recovery"]
                    or not actual["save_attempted"]
                    or reached["after_save"]
                )
            )
            or (
                stage == "POST_SAVE_EVIDENCE"
                and (
                    not actual["save_succeeded"]
                    or reached["after_save"]
                )
            )
            or (
                stage == "POST_SAVE_SOURCE_GUARD"
                and (
                    not actual["save_succeeded"]
                    or not reached["after_save"]
                )
            )
            or (
                stage == "RELOCK"
                and (
                    not actual["save_succeeded"]
                    or not reached["after_save"]
                    or not actual["relock_attempted"]
                )
            )
        )
        if invalid_failure_state:
            raise ValueError("permission_recovery_contract_invalid")
    return actual


def _save_presentation_layer_with_permission_recovery(
    stage: Any,
    *,
    presentation_layer: Any,
    expected_presentation_path: str | os.PathLike[str],
    source_path: str | os.PathLike[str],
    expected_source_sha256: str,
) -> dict[str, Any]:
    contract = _new_presentation_permission_recovery_contract()
    root_layer = stage.GetRootLayer()
    primary_error: BaseException | None = None
    current_stage = "IDENTITY_PREFLIGHT"
    lifecycle_started = False
    presentation_preflight_identity: dict[str, Any] | None = None

    def observe_phase(phase: str, *, expected_presentation_bytes: bytes | None = None) -> None:
        source_evidence = _read_pinned_regular_file_evidence(
            source_path,
            label=f"permission_recovery_source_{phase}",
        )
        presentation_evidence = _read_pinned_regular_file_evidence(
            expected_presentation_path,
            label=f"permission_recovery_presentation_{phase}",
            expected_bytes=expected_presentation_bytes,
        )
        source_permissions = _permission_pair(root_layer)
        presentation_permissions = _permission_pair(presentation_layer)
        source_snapshot = snapshot_sdf_layer(root_layer)["snapshot_sha256"]
        presentation_snapshot = snapshot_sdf_layer(presentation_layer)[
            "snapshot_sha256"
        ]
        source_identity = _path_identity_from_file_evidence(source_evidence)
        presentation_identity = _path_identity_from_file_evidence(
            presentation_evidence
        )
        contract["source_permissions"][phase] = source_permissions
        contract["presentation_permissions"][phase] = presentation_permissions
        contract["source_file_sha256"][phase] = source_evidence["sha256"]
        contract["presentation_file_sha256"][phase] = presentation_evidence[
            "sha256"
        ]
        contract["source_layer_snapshot_sha256"][phase] = source_snapshot
        contract["presentation_layer_snapshot_sha256"][phase] = (
            presentation_snapshot
        )
        contract["source_path_identity"][phase] = source_identity
        contract["presentation_path_identity"][phase] = presentation_identity

    try:
        source_identity, source_evidence = _verified_file_backed_layer_identity(
            root_layer,
            expected_path=source_path,
            label="permission_recovery_source_root",
        )
        contract["source_root_layer"] = source_identity
        presentation_identity, presentation_evidence = (
            _verified_file_backed_layer_identity(
                presentation_layer,
                expected_path=expected_presentation_path,
                label="permission_recovery_presentation",
            )
        )
        contract["presentation_layer"] = presentation_identity
        presentation_preflight_identity = _path_identity_from_file_evidence(
            presentation_evidence
        )
        if (
            root_layer is presentation_layer
            or source_identity["identifier"] == presentation_identity["identifier"]
            or source_identity["real_path"] == presentation_identity["real_path"]
            or (source_identity["device"], source_identity["inode"])
            == (presentation_identity["device"], presentation_identity["inode"])
        ):
            raise ValueError("permission_recovery_layer_alias")
        edit_target_layer = stage.GetEditTarget().GetLayer()
        if edit_target_layer is not presentation_layer and (
            edit_target_layer.identifier != presentation_layer.identifier
        ):
            raise ValueError("permission_recovery_wrong_edit_target")
        source_permissions = _permission_pair(root_layer)
        presentation_permissions = _permission_pair(presentation_layer)
        if source_permissions != {
            "permission_to_edit": False,
            "permission_to_save": False,
        }:
            raise ValueError("permission_recovery_source_root_not_locked")
        lifecycle_started = True
        observe_phase("before_recovery")
        if source_evidence["sha256"] != expected_source_sha256:
            raise ValueError("permission_recovery_source_hash_mismatch")

        contract["recovery_attempted"] = not all(
            presentation_permissions.values()
        )
        if not presentation_permissions["permission_to_edit"]:
            current_stage = "SET_EDIT"
            contract["set_edit_attempted"] = True
            presentation_layer.SetPermissionToEdit(True)
            contract["set_edit_readback"] = bool(presentation_layer.permissionToEdit)
            if contract["set_edit_readback"] is not True:
                raise RuntimeError("permission_recovery_set_edit_readback_false")
        if not presentation_permissions["permission_to_save"]:
            current_stage = "SET_SAVE"
            contract["set_save_attempted"] = True
            presentation_layer.SetPermissionToSave(True)
            contract["set_save_readback"] = bool(presentation_layer.permissionToSave)
            if contract["set_save_readback"] is not True:
                raise RuntimeError("permission_recovery_set_save_readback_false")

        current_stage = "RECOVERY_READBACK"
        if _permission_pair(presentation_layer) != {
            "permission_to_edit": True,
            "permission_to_save": True,
        }:
            raise RuntimeError("permission_recovery_final_readback_false")
        observe_phase("after_recovery")
        if (
            contract["source_path_identity"]["after_recovery"]
            != contract["source_path_identity"]["before_recovery"]
            or contract["presentation_path_identity"]["after_recovery"]
            != presentation_preflight_identity
            or contract["source_file_sha256"]["after_recovery"]
            != expected_source_sha256
        ):
            raise RuntimeError("permission_recovery_pre_save_guard_failed")

        current_stage = "SAVE"
        contract["save_attempted"] = True
        if not presentation_layer.Save():
            raise RuntimeError("presentation_layer_save_failed")
        contract["save_succeeded"] = True

        current_stage = "POST_SAVE_EVIDENCE"
        observe_phase(
            "after_save",
            expected_presentation_bytes=presentation_layer.ExportToString().encode(
                "utf-8"
            ),
        )
        current_stage = "POST_SAVE_SOURCE_GUARD"
        if (
            contract["source_file_sha256"]["after_save"] != expected_source_sha256
            or contract["source_path_identity"]["after_save"]
            != contract["source_path_identity"]["before_recovery"]
            or contract["source_layer_snapshot_sha256"]["after_save"]
            != contract["source_layer_snapshot_sha256"]["before_recovery"]
            or contract["source_permissions"]["after_save"]
            != {"permission_to_edit": False, "permission_to_save": False}
        ):
            raise RuntimeError("permission_recovery_post_save_source_guard_failed")
    except BaseException as exc:
        primary_error = exc
        contract["failure_stage"] = current_stage
    finally:
        if lifecycle_started:
            contract["relock_attempted"] = True
            relock_errors = []
            try:
                presentation_layer.SetPermissionToEdit(False)
            except BaseException as exc:
                relock_errors.append(exc)
            try:
                presentation_layer.SetPermissionToSave(False)
            except BaseException as exc:
                relock_errors.append(exc)
            try:
                observe_phase("after_relock")
            except BaseException as exc:
                relock_errors.append(exc)
            expected_identity = next(
                (
                    contract["presentation_path_identity"][phase]
                    for phase in ("after_save", "after_recovery", "before_recovery")
                    if contract["presentation_path_identity"][phase] is not None
                ),
                presentation_preflight_identity,
            )
            if (
                relock_errors
                or contract["presentation_permissions"]["after_relock"]
                != {"permission_to_edit": False, "permission_to_save": False}
                or contract["source_permissions"]["after_relock"]
                != {"permission_to_edit": False, "permission_to_save": False}
                or contract["presentation_path_identity"]["after_relock"]
                != expected_identity
                or contract["source_path_identity"]["after_relock"]
                != contract["source_path_identity"]["before_recovery"]
                or contract["source_file_sha256"]["after_relock"]
                != contract["source_file_sha256"]["before_recovery"]
                or contract["source_layer_snapshot_sha256"]["after_relock"]
                != contract["source_layer_snapshot_sha256"]["before_recovery"]
            ):
                if contract["failure_stage"] is None:
                    contract["failure_stage"] = "RELOCK"
                else:
                    contract["secondary_failure_stage"] = "RELOCK"
            else:
                contract["relock_succeeded"] = True

    if contract["failure_stage"] is None:
        contract["status"] = "PASS"
        return validate_presentation_layer_export_permission_recovery_contract(
            contract
        )
    contract["status"] = "FAIL"
    validated = validate_presentation_layer_export_permission_recovery_contract(
        contract
    )
    message = (
        f"presentation_layer_permission_recovery_failed:{contract['failure_stage']}:"
        f"{type(primary_error).__name__ if primary_error is not None else 'RelockError'}:"
        f"{primary_error if primary_error is not None else 'relock_failed'}"
    )
    raise PresentationLayerPermissionRecoveryError(message, validated) from primary_error


def snapshot_sdf_layer(layer: Any) -> dict[str, Any]:
    """Return raw and canonical evidence for every authored layer spec."""
    from pxr import Sdf

    if layer is None:
        raise ValueError("sdf_layer_missing")
    specs: dict[str, dict[str, Any]] = {}

    def visit(path: Any) -> None:
        spec = layer.GetObjectAtPath(path)
        if spec is None:
            return
        info: dict[str, Any] = {}
        for key in sorted(spec.ListInfoKeys(), key=str):
            key_name = str(key)
            if str(path) == "/" and key_name in {"subLayers", "subLayerOffsets"}:
                continue
            try:
                info[key_name] = _canonical_usd_value(spec.GetInfo(key))
            except TypeError:
                info[key_name] = {
                    "python_binding_value_unavailable": True,
                }
        specs[str(path)] = {
            "spec_type": type(spec).__name__,
            "info": info,
        }

    layer.Traverse(Sdf.Path.absoluteRootPath, visit)
    raw_text = layer.ExportToString()
    payload = {
        "sub_layer_paths": list(layer.subLayerPaths),
        "sub_layer_offsets": [
            {
                "offset": float(offset.offset),
                "scale": float(offset.scale),
            }
            for offset in layer.subLayerOffsets
        ],
        "specs": {path: specs[path] for path in sorted(specs)},
    }
    return {
        **payload,
        "snapshot_sha256": _json_sha256(payload),
        "raw_usda_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        "raw_usda_byte_count": len(raw_text.encode("utf-8")),
        "identifier": str(layer.identifier),
        "real_path": str(layer.realPath) if layer.realPath else None,
        "permission_to_edit": bool(layer.permissionToEdit),
        "permission_to_save": bool(layer.permissionToSave),
    }


def snapshot_session_layer(stage: Any) -> dict[str, Any]:
    """Return a deterministic snapshot of every authored session-layer spec."""
    layer = stage.GetSessionLayer()
    if layer is None:
        raise RuntimeError("stage_session_layer_missing")
    return {
        **snapshot_sdf_layer(layer),
        "root_prim_paths": sorted(str(prim.path) for prim in layer.rootPrims),
    }


def diff_layer_snapshots(
    baseline: Mapping[str, Any],
    current: Mapping[str, Any],
) -> dict[str, Any]:
    """Report spec-, field-, and sublayer-level changes between two snapshots."""
    baseline_specs = dict(baseline.get("specs") or {})
    current_specs = dict(current.get("specs") or {})
    baseline_paths = set(baseline_specs)
    current_paths = set(current_specs)
    added = sorted(current_paths - baseline_paths)
    removed = sorted(baseline_paths - current_paths)
    modified = sorted(
        path
        for path in baseline_paths & current_paths
        if baseline_specs[path] != current_specs[path]
    )
    sublayers_changed = (
        baseline.get("sub_layer_paths") != current.get("sub_layer_paths")
        or baseline.get("sub_layer_offsets") != current.get("sub_layer_offsets")
    )
    changed = bool(added or removed or modified or sublayers_changed)
    return {
        "changed": changed,
        "added_spec_paths": added,
        "removed_spec_paths": removed,
        "modified_spec_paths": modified,
        "sublayers_changed": sublayers_changed,
        "baseline_snapshot_sha256": baseline.get("snapshot_sha256"),
        "current_snapshot_sha256": current.get("snapshot_sha256"),
    }


def begin_disposable_capture_frame_layer(
    stage: Any,
    *,
    candidate_id: str,
) -> Any:
    """Add one anonymous frame overlay to a disposable capture stage."""
    from pxr import Sdf, Usd

    if candidate_id not in REFERENCE_CANDIDATE_IDS:
        raise ValueError(f"unknown_reference_candidate:{candidate_id}")
    session_layer = stage.GetSessionLayer()
    if session_layer is None:
        raise RuntimeError("stage_session_layer_missing")
    if session_layer.subLayerPaths:
        raise RuntimeError("capture_session_sublayers_must_start_empty")
    frame_layer = Sdf.Layer.CreateAnonymous(
        f"LabUtopiaCaptureFrame_{candidate_id}"
    )
    if frame_layer is None:
        raise RuntimeError("capture_frame_layer_create_failed")
    session_layer.subLayerPaths.insert(0, frame_layer.identifier)
    stage.SetEditTarget(Usd.EditTarget(frame_layer))
    if stage.GetEditTarget().GetLayer().identifier != frame_layer.identifier:
        raise RuntimeError("capture_frame_layer_edit_target_failed")
    return frame_layer


def lock_capture_persistent_layers(
    stage: Any,
    *,
    frame_layer: Any,
    expected_file_sha256: Mapping[str, str] | None = None,
    expected_baseline: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Make every file-backed capture dependency immutable in memory and on disk."""
    session_layer = stage.GetSessionLayer()
    if session_layer is None:
        raise RuntimeError("stage_session_layer_missing")
    used_layers = list(stage.GetUsedLayers())
    persistent_layers = sorted(
        (
            layer
            for layer in used_layers
            if layer.identifier not in {
                session_layer.identifier,
                frame_layer.identifier,
            }
            and layer.realPath
        ),
        key=lambda layer: str(_absolute_path_without_symlink_resolution(layer.realPath)),
    )
    unexpected_anonymous = sorted(
        layer.identifier
        for layer in used_layers
        if layer.identifier not in {
            session_layer.identifier,
            frame_layer.identifier,
        }
        and not layer.realPath
    )
    if unexpected_anonymous:
        raise RuntimeError(
            "capture_stage_has_unexpected_anonymous_dependency:"
            + ",".join(unexpected_anonymous)
        )
    records = []
    for layer in persistent_layers:
        if layer.dirty:
            raise RuntimeError(
                f"capture_persistent_layer_dirty_before_lock:{layer.identifier}"
            )
        path = _absolute_path_without_symlink_resolution(layer.realPath)
        evidence = _read_pinned_regular_file_evidence(
            path,
            label="capture_persistent_layer_lock",
        )
        record = {
            "identifier": str(layer.identifier),
            "path": evidence["path"],
            "sha256": evidence["sha256"],
            "device": evidence["device"],
            "inode": evidence["inode"],
            "file_type": evidence["file_type"],
            "link_count": evidence["link_count"],
        }
        records.append(record)
    validated_baseline = (
        validate_capture_persistent_layer_baseline(expected_baseline)
        if expected_baseline is not None
        else None
    )
    records_by_path = {record["path"]: record for record in records}
    if validated_baseline is not None:
        for expected in validated_baseline["files"]:
            actual = records_by_path.get(expected["path"])
            if actual is None or any(
                actual.get(field) != expected[field]
                for field in (
                    "sha256",
                    "device",
                    "inode",
                    "file_type",
                    "link_count",
                )
            ):
                raise RuntimeError(
                    "capture_persistent_layer_baseline_identity_mismatch:"
                    f"{expected['role']}:{expected['path']}"
                )
    layers_by_path = {
        str(_absolute_path_without_symlink_resolution(layer.realPath)): layer
        for layer in persistent_layers
    }
    for record in records:
        layer = layers_by_path[record["path"]]
        layer.SetPermissionToEdit(False)
        layer.SetPermissionToSave(False)
        record["permission_to_edit"] = bool(layer.permissionToEdit)
        record["permission_to_save"] = bool(layer.permissionToSave)
    all_locked = all(
        record["permission_to_edit"] is False
        and record["permission_to_save"] is False
        for record in records
    )
    if not all_locked:
        raise RuntimeError("capture_persistent_layer_lock_failed")
    expected_hashes = {
        str(Path(path).expanduser().resolve()): _require_sha256(
            f"capture_expected_file_sha256:{path}", digest
        )
        for path, digest in (expected_file_sha256 or {}).items()
    }
    actual_hashes = {record["path"]: record["sha256"] for record in records}
    missing_expected_paths = sorted(set(expected_hashes) - set(actual_hashes))
    mismatched_expected_paths = sorted(
        path
        for path, digest in expected_hashes.items()
        if actual_hashes.get(path) != digest
    )
    if missing_expected_paths or mismatched_expected_paths:
        raise RuntimeError(
            "capture_persistent_layer_expected_hash_mismatch:"
            f"missing={missing_expected_paths}:mismatched={mismatched_expected_paths}"
        )
    return {
        "persistent_layer_count": len(records),
        "persistent_layers": records,
        "all_persistent_layers_locked": True,
        "capture_frame_layer_identifier": frame_layer.identifier,
        "capture_frame_layer_anonymous": not bool(frame_layer.realPath),
        "expected_file_sha256": expected_hashes,
        "expected_file_sha256_verified": True,
        "expected_baseline": validated_baseline,
        "expected_baseline_verified": validated_baseline is not None,
        "expected_used_layer_identifiers": sorted(
            layer.identifier for layer in used_layers
        ),
    }


def verify_capture_persistent_layers_unchanged(
    stage: Any,
    lock_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Re-hash every locked file-backed layer after Replicator cleanup."""
    current_used_layers = list(stage.GetUsedLayers())
    layers_by_identifier = {
        layer.identifier: layer for layer in current_used_layers
    }
    expected_identifiers = set(
        lock_contract.get("expected_used_layer_identifiers") or []
    )
    current_identifiers = set(layers_by_identifier)
    if current_identifiers != expected_identifiers:
        raise RuntimeError(
            "capture_used_layer_set_changed:"
            f"added={sorted(current_identifiers - expected_identifiers)}:"
            f"removed={sorted(expected_identifiers - current_identifiers)}"
        )
    verified = []
    for expected in lock_contract.get("persistent_layers") or []:
        identifier = str(expected["identifier"])
        layer = layers_by_identifier.get(identifier)
        if layer is None:
            raise RuntimeError(
                f"capture_persistent_layer_missing_after_capture:{identifier}"
            )
        path = _absolute_path_without_symlink_resolution(expected["path"])
        try:
            actual_evidence = _read_pinned_regular_file_evidence(
                path,
                label="capture_persistent_layer_verify",
            )
        except ValueError as exc:
            raise RuntimeError(
                f"capture_persistent_layer_identity_changed:{path}:{exc}"
            ) from exc
        actual_sha256 = actual_evidence["sha256"]
        identity_changed = any(
            actual_evidence.get(field) != expected.get(field)
            for field in ("device", "inode", "file_type", "link_count")
        )
        if identity_changed:
            raise RuntimeError(
                "capture_persistent_layer_identity_changed:"
                f"{path}"
            )
        if actual_sha256 != expected["sha256"]:
            raise RuntimeError(
                "capture_persistent_layer_file_changed:"
                f"{path}:{actual_sha256}!={expected['sha256']}"
            )
        if layer.dirty:
            raise RuntimeError(
                f"capture_persistent_layer_dirty_after_capture:{identifier}"
            )
        if layer.permissionToEdit or layer.permissionToSave:
            raise RuntimeError(
                f"capture_persistent_layer_lock_lost:{identifier}"
            )
        verified.append(
            {
                **dict(expected),
                "actual_sha256": actual_sha256,
                "dirty": False,
                "lock_preserved": True,
            }
        )
    return {
        "verified": True,
        "persistent_layer_count": len(verified),
        "persistent_layers": verified,
        "used_layer_set_unchanged": True,
        "used_layer_identifiers": sorted(current_identifiers),
    }


def write_layer_audit_artifacts(
    layer: Any,
    *,
    usda_path: str | os.PathLike[str],
    json_path: str | os.PathLike[str],
) -> dict[str, Any]:
    """Persist raw USDA plus canonical JSON without overwriting prior evidence."""
    usda_target = Path(usda_path).resolve()
    json_target = Path(json_path).resolve()
    for target in (usda_target, json_target):
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise ValueError(f"layer_audit_artifact_already_exists:{target}")
    raw_text = layer.ExportToString()
    usda_target.write_text(raw_text, encoding="utf-8")
    snapshot = snapshot_sdf_layer(layer)
    atomic_write_json(json_target, snapshot)
    return {
        "raw_usda_path": str(usda_target),
        "raw_usda_sha256": _sha256_file(usda_target),
        "raw_usda_byte_count": usda_target.stat().st_size,
        "canonical_json_path": str(json_target),
        "canonical_json_sha256": _sha256_file(json_target),
        "snapshot_sha256": snapshot["snapshot_sha256"],
    }


def composed_world_fingerprint_payload(stage: Any) -> dict[str, Any]:
    """Build the canonical, independently hashable scoped /World payload."""
    from pxr import Usd

    excluded_roots = (PHYSX_RUNTIME_ISOSURFACE_PATH,)
    prim_payloads = []
    for prim in Usd.PrimRange.Stage(stage, Usd.PrimAllPrimsPredicate):
        path = str(prim.GetPath())
        if path != "/World" and not path.startswith("/World/"):
            continue
        if any(path == root or path.startswith(f"{root}/") for root in excluded_roots):
            continue
        attributes = []
        for attribute in sorted(prim.GetAttributes(), key=lambda item: item.GetName()):
            attributes.append(
                {
                    "name": attribute.GetName(),
                    "type": str(attribute.GetTypeName()),
                    "value": _canonical_usd_value(attribute.Get()),
                    "connections": sorted(
                        str(connection) for connection in attribute.GetConnections()
                    ),
                    "metadata": _canonical_usd_value(
                        attribute.GetAllMetadata()
                    ),
                }
            )
        relationships = []
        for relationship in sorted(
            prim.GetRelationships(), key=lambda item: item.GetName()
        ):
            relationships.append(
                {
                    "name": relationship.GetName(),
                    "targets": sorted(str(target) for target in relationship.GetTargets()),
                    "metadata": _canonical_usd_value(
                        relationship.GetAllMetadata()
                    ),
                }
            )
        prim_payloads.append(
            {
                "path": path,
                "type_name": prim.GetTypeName(),
                "active": prim.IsActive(),
                "applied_schemas": sorted(prim.GetAppliedSchemas()),
                "metadata": _canonical_usd_value(prim.GetAllMetadata()),
                "attributes": attributes,
                "relationships": relationships,
            }
        )
    return {
        "schema_version": 1,
        "algorithm": COMPOSED_WORLD_FINGERPRINT_ALGORITHM,
        "scope": {
            "root_prim_path": "/World",
            "time_code": "default",
            "excluded_runtime_roots": list(excluded_roots),
            "prim_predicate": "Usd.PrimAllPrimsPredicate",
            "includes_inactive_prims": True,
            "property_coverage": (
                "prim metadata/applied schemas plus attribute default values, "
                "attribute metadata/connections, and relationship metadata/targets"
            ),
            "full_stage_equivalence_claimed": False,
            "session_layer_equivalence_claimed": False,
            "pixel_equivalence_claimed": False,
        },
        "prims": prim_payloads,
    }


def composed_world_fingerprint_from_payload(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Summarize one already captured payload without traversing the stage again."""
    if payload.get("algorithm") != COMPOSED_WORLD_FINGERPRINT_ALGORITHM:
        raise ValueError("composed_world_fingerprint_algorithm_mismatch")
    prims = payload["prims"]
    return {
        "sha256": _json_sha256(payload),
        "algorithm": COMPOSED_WORLD_FINGERPRINT_ALGORITHM,
        "prim_count": len(prims),
        "attribute_count": sum(len(prim["attributes"]) for prim in prims),
        "relationship_count": sum(len(prim["relationships"]) for prim in prims),
        "scope": deepcopy(payload["scope"]),
        "full_render_entry_equivalence_status": "NOT_CLAIMED",
    }


def composed_world_fingerprint(stage: Any) -> dict[str, Any]:
    """Summarize the scoped composed /World payload without hiding its limits."""
    return composed_world_fingerprint_from_payload(
        composed_world_fingerprint_payload(stage)
    )


def write_composed_world_fingerprint_artifact(
    stage: Any,
    path: str | os.PathLike[str],
) -> dict[str, Any]:
    """Persist the canonical payload and its recomputable digest."""
    target = Path(path).expanduser().resolve()
    if target.exists():
        raise ValueError(f"world_fingerprint_artifact_already_exists:{target}")
    payload = composed_world_fingerprint_payload(stage)
    fingerprint = composed_world_fingerprint_from_payload(payload)
    artifact_payload = {
        "schema_version": 1,
        "artifact_type": "scoped_composed_world_fingerprint",
        "payload": payload,
        "payload_sha256": _json_sha256(payload),
        "fingerprint": fingerprint,
    }
    if target.name.endswith(".gz"):
        atomic_write_json_gzip(target, artifact_payload)
    else:
        atomic_write_json(target, artifact_payload)
    return {
        "artifact_path": str(target),
        "artifact_sha256": _sha256_file(target),
        "payload_sha256": artifact_payload["payload_sha256"],
        "fingerprint": fingerprint,
    }


def validate_composed_world_fingerprint_artifact(
    path: str | os.PathLike[str],
    *,
    expected_fingerprint: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute a persisted scoped fingerprint payload and compare its summary."""
    target = Path(path).expanduser().resolve()
    artifact = _load_json_object(target, label="composed_world_fingerprint")
    payload = artifact.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("composed_world_fingerprint_payload_missing")
    recomputed_sha256 = _json_sha256(payload)
    if artifact.get("payload_sha256") != recomputed_sha256:
        raise ValueError("composed_world_fingerprint_payload_sha256_mismatch")
    recomputed_fingerprint = composed_world_fingerprint_from_payload(payload)
    if artifact.get("fingerprint") != recomputed_fingerprint:
        raise ValueError("composed_world_fingerprint_summary_mismatch")
    if recomputed_fingerprint != dict(expected_fingerprint):
        raise ValueError("composed_world_fingerprint_expected_summary_mismatch")
    return {
        "validated": True,
        "artifact_path": str(target),
        "artifact_sha256": _sha256_file(target),
        "payload_sha256": recomputed_sha256,
        "fingerprint": recomputed_fingerprint,
    }


def build_capture_session_residue_contract(
    stage: Any,
    *,
    baseline_snapshot: Mapping[str, Any],
    frame_layer: Any,
) -> dict[str, Any]:
    """Classify disposable capture residue without claiming native cleanup."""
    current = snapshot_session_layer(stage)
    baseline = deepcopy(dict(baseline_snapshot))
    diff = diff_layer_snapshots(baseline, current)
    baseline_paths = set((baseline.get("specs") or {}).keys())
    current_paths = set((current.get("specs") or {}).keys())
    new_paths = current_paths - baseline_paths
    runtime_roots = (
        *ALLOWED_KIT_RUNTIME_SESSION_ROOT_PATHS,
        *ALLOWED_REPLICATOR_RUNTIME_SESSION_ROOT_PATHS,
    )
    physx_isosurface = _physx_runtime_isosurface_contract(current["specs"])
    unexpected = sorted(
        path
        for path in new_paths
        if path != "/"
        and not _session_path_in_runtime_namespace(path, runtime_roots)
        and path not in PHYSX_RUNTIME_ISOSURFACE_SPEC_PATHS
    )
    sublayer_exact = current["sub_layer_paths"] == [frame_layer.identifier]
    failures = []
    if unexpected:
        failures.append("unclassified_session_specs")
    if diff["removed_spec_paths"]:
        failures.append("baseline_session_specs_removed")
    if physx_isosurface["present"] and not physx_isosurface[
        "exact_known_structure"
    ]:
        failures.append("physx_runtime_isosurface_structure_changed")
    if not sublayer_exact:
        failures.append("capture_frame_sublayer_changed")
    residue = bool(
        diff["added_spec_paths"]
        or diff["removed_spec_paths"]
        or diff["modified_spec_paths"]
    )
    return {
        "classification_gate_status": "PASS" if not failures else "FAIL",
        "classification_failures": failures,
        "native_cleanup_status": "RESIDUAL" if residue else "CLEAN",
        "session_delta_status": "RESIDUAL" if residue else "CLEAN",
        "manual_restore_status": "NOT_RUN_DISPOSABLE_STAGE",
        "capture_stage_disposition": "PENDING_DISCARD",
        "entry_isolation_status": "PASS_STATIC_ENTRY_PREEXISTED_CAPTURE",
        "runtime_session_specs_exported": False,
        "composed_world_default_time_property_snapshot_equivalence_"
        "excluding_known_physx_runtime_status": "PENDING",
        "full_render_entry_equivalence_status": "NOT_CLAIMED",
        "capture_frame_sublayer_exact": sublayer_exact,
        "unclassified_scene_opinion_count": len(unexpected),
        "unclassified_spec_paths": unexpected,
        "physx_runtime_isosurface": physx_isosurface,
        "layer_diff": diff,
        "baseline_snapshot_sha256": baseline.get("snapshot_sha256"),
        "post_cleanup_snapshot_sha256": current.get("snapshot_sha256"),
        "allowed_claims": [
            "capture_stage_is_disposable=true",
            "persistent_entry_preexisted_replicator=true",
            "runtime_session_specs_exported=false",
        ],
        "blocked_claims": [
            "native_replicator_cleanup_removed_all_session_opinions=true",
            "session_was_never_modified=true",
            "full_render_entry_equivalence_verified=true",
            "session_layer_equivalence_verified=true",
            "pixel_equivalence_verified=true",
        ],
    }


def discard_capture_stage(
    *,
    context: Any,
    app: Any,
    timeline: Any,
    expected_root_path: str | os.PathLike[str],
    flush_updates: int = 2,
) -> dict[str, Any]:
    """Close the candidate stage and flush delayed Kit cleanup before reuse."""
    require_stopped_timeline(timeline)
    stage = context.get_stage()
    if stage is None:
        raise RuntimeError("capture_stage_missing_before_discard")
    actual_root = Path(stage.GetRootLayer().realPath).resolve()
    expected_root = Path(expected_root_path).resolve()
    if actual_root != expected_root:
        raise RuntimeError(
            f"capture_stage_discard_root_mismatch:{actual_root}!={expected_root}"
        )
    context.close_stage()
    for _ in range(max(1, int(flush_updates))):
        require_stopped_timeline(timeline)
        app.update()
    if context.get_stage() is not None:
        raise RuntimeError("capture_stage_still_open_after_discard")
    return {
        "discarded": True,
        "root_path": str(expected_root),
        "flush_updates": max(1, int(flush_updates)),
        "context_stage_is_none": True,
    }


def emergency_discard_active_capture_stage(
    args: argparse.Namespace,
    *,
    context: Any,
    app: Any,
    timeline: Any,
    flush_updates: int = 2,
) -> dict[str, Any]:
    """Best-effort failure-path discard that never masks the primary error."""
    active_root = getattr(args, "_active_capture_stage_root", None)
    if not active_root:
        return {
            "emergency_discard_status": "NOT_APPLICABLE",
            "discarded": False,
            "root_path": None,
            "error": None,
        }
    try:
        if context.get_stage() is None:
            contract = {
                "discarded": True,
                "root_path": str(Path(active_root).resolve()),
                "flush_updates": 0,
                "context_stage_is_none": True,
                "already_closed": True,
            }
        else:
            contract = discard_capture_stage(
                context=context,
                app=app,
                timeline=timeline,
                expected_root_path=active_root,
                flush_updates=flush_updates,
            )
        args._active_capture_stage_root = None
        return {
            **contract,
            "emergency_discard_status": "PASS",
            "error": None,
        }
    except BaseException as exc:
        return {
            "emergency_discard_status": "FAIL",
            "discarded": False,
            "root_path": str(Path(active_root).resolve()),
            "error": f"{type(exc).__name__}:{exc}",
        }


def quiesce_capture_session(
    stage: Any,
    *,
    app: Any,
    timeline: Any,
    minimum_updates: int = 2,
    maximum_updates: int = 8,
) -> dict[str, Any]:
    """Wait for two identical consecutive post-cleanup session snapshots."""
    minimum = _require_plain_int(
        "capture_quiescence_minimum_updates", minimum_updates, minimum=2
    )
    maximum = _require_plain_int(
        "capture_quiescence_maximum_updates", maximum_updates, minimum=minimum
    )
    snapshot_hashes = [snapshot_session_layer(stage)["snapshot_sha256"]]
    stable_count = 1
    updates = 0
    for _ in range(maximum):
        require_stopped_timeline(timeline)
        app.update()
        updates += 1
        current_hash = snapshot_session_layer(stage)["snapshot_sha256"]
        stable_count = (
            stable_count + 1 if current_hash == snapshot_hashes[-1] else 1
        )
        snapshot_hashes.append(current_hash)
        if updates >= minimum and stable_count >= 2:
            break
    stable = updates >= minimum and stable_count >= 2
    return {
        "quiescence_status": (
            "PASS_STABLE_CONSECUTIVE_SNAPSHOTS"
            if stable
            else "FAIL_SESSION_SNAPSHOTS_DID_NOT_STABILIZE"
        ),
        "updates_executed": updates,
        "minimum_updates": minimum,
        "maximum_updates": maximum,
        "stable_consecutive_snapshot_count": stable_count,
        "snapshot_sha256_sequence": snapshot_hashes,
        "final_two_snapshot_sha256": snapshot_hashes[-2:],
    }


def clone_session_layer(stage: Any) -> Any:
    """Clone the exact session content for candidate-level restoration."""
    from pxr import Sdf

    session_layer = stage.GetSessionLayer()
    if session_layer is None:
        raise RuntimeError("stage_session_layer_missing")
    clone = Sdf.Layer.CreateAnonymous("labutopia_candidate_session_baseline")
    if clone is None:
        raise RuntimeError("candidate_session_baseline_clone_create_failed")
    clone.TransferContent(session_layer)
    return clone


def restore_candidate_session_layer(
    stage: Any,
    *,
    baseline_layer: Any,
    baseline_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Restore the pre-candidate session exactly and detach presentation state."""
    session_layer = stage.GetSessionLayer()
    if session_layer is None:
        raise RuntimeError("stage_session_layer_missing")
    session_layer.TransferContent(baseline_layer)
    stage.SetEditTarget(stage.GetRootLayer())
    restored = snapshot_session_layer(stage)
    expected = deepcopy(dict(baseline_snapshot))
    if restored != expected:
        raise RuntimeError(
            "candidate_session_restore_mismatch:"
            f"actual={restored.get('snapshot_sha256')}:"
            f"expected={expected.get('snapshot_sha256')}"
        )
    return {
        "restored": True,
        "restored_snapshot_sha256": restored["snapshot_sha256"],
        "baseline_snapshot_sha256": expected["snapshot_sha256"],
        "presentation_sublayer_detached": True,
        "edit_target_restored_to_source_root": True,
    }


def _session_path_in_runtime_namespace(path: str, roots: Sequence[str]) -> bool:
    return any(
        path == root
        or path.startswith(f"{root}/")
        or path.startswith(f"{root}.")
        for root in roots
    )


def _physx_runtime_isosurface_contract(
    specs: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    world_paths = sorted(
        path
        for path in specs
        if path == "/World"
        or path.startswith("/World/")
        or path.startswith("/World.")
    )
    if not world_paths:
        return {
            "present": False,
            "actual_spec_paths": [],
            "expected_spec_paths": list(PHYSX_RUNTIME_ISOSURFACE_SPEC_PATHS),
            "exact_known_structure": True,
        }

    expected_paths = set(PHYSX_RUNTIME_ISOSURFACE_SPEC_PATHS)
    actual_paths = set(world_paths)
    expected_attr_contracts = {
        f"{PHYSX_RUNTIME_ISOSURFACE_PATH}.faceVertexCounts": {
            "typeName": "int[]",
            "default": [3],
        },
        f"{PHYSX_RUNTIME_ISOSURFACE_PATH}.faceVertexIndices": {
            "typeName": "int[]",
            "default": [0, 0, 0],
        },
        f"{PHYSX_RUNTIME_ISOSURFACE_PATH}.normals": {
            "typeName": "normal3f[]",
            "default": [[0.0, 0.0, 0.0]],
        },
        f"{PHYSX_RUNTIME_ISOSURFACE_PATH}.points": {
            "typeName": "point3f[]",
            "default": [[0.0, 0.0, 0.0]],
        },
    }
    field_checks = {
        "/World": specs.get("/World", {}).get("info", {}).get("specifier")
        == "Sdf.SpecifierOver",
        "/World/ParticleSystem": specs.get("/World/ParticleSystem", {})
        .get("info", {})
        .get("specifier")
        == "Sdf.SpecifierOver",
        PHYSX_RUNTIME_ISOSURFACE_PATH: (
            specs.get(PHYSX_RUNTIME_ISOSURFACE_PATH, {})
            .get("info", {})
            .get("specifier")
            == "Sdf.SpecifierDef"
            and specs.get(PHYSX_RUNTIME_ISOSURFACE_PATH, {})
            .get("info", {})
            .get("typeName")
            == "Mesh"
        ),
    }
    for path, expected in expected_attr_contracts.items():
        info = specs.get(path, {}).get("info", {})
        field_checks[path] = all(info.get(key) == value for key, value in expected.items())
    return {
        "present": True,
        "actual_spec_paths": world_paths,
        "expected_spec_paths": list(PHYSX_RUNTIME_ISOSURFACE_SPEC_PATHS),
        "field_checks": field_checks,
        "exact_known_structure": actual_paths == expected_paths
        and all(field_checks.values()),
    }


def build_export_session_layer_contract(
    stage: Any,
    *,
    presentation_layer: Any,
    baseline_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate exact runtime-only session opinions before static composition."""
    current = snapshot_session_layer(stage)
    baseline = deepcopy(dict(baseline_snapshot))
    baseline_payload = {
        "sub_layer_paths": baseline.get("sub_layer_paths"),
        "sub_layer_offsets": baseline.get("sub_layer_offsets"),
        "specs": baseline.get("specs"),
    }
    baseline_hash_valid = baseline.get("snapshot_sha256") == _json_sha256(
        baseline_payload
    )
    baseline_specs = baseline.get("specs")
    if not isinstance(baseline_specs, Mapping):
        baseline_specs = {}
    current_specs = current["specs"]
    baseline_runtime_roots = tuple(ALLOWED_KIT_RUNTIME_SESSION_ROOT_PATHS)
    export_runtime_roots = (
        *ALLOWED_KIT_RUNTIME_SESSION_ROOT_PATHS,
        *ALLOWED_REPLICATOR_RUNTIME_SESSION_ROOT_PATHS,
    )
    baseline_unexpected = sorted(
        path
        for path in baseline_specs
        if path != "/"
        and not _session_path_in_runtime_namespace(path, baseline_runtime_roots)
    )
    physx_isosurface = _physx_runtime_isosurface_contract(current_specs)
    unexpected_paths = sorted(
        path
        for path in current_specs
        if path != "/"
        and not _session_path_in_runtime_namespace(path, export_runtime_roots)
        and path not in PHYSX_RUNTIME_ISOSURFACE_SPEC_PATHS
    )
    baseline_paths = set(baseline_specs)
    current_paths = set(current_specs)
    added_paths = sorted(current_paths - baseline_paths)
    removed_paths = sorted(baseline_paths - current_paths)
    modified_paths = sorted(
        path
        for path in baseline_paths & current_paths
        if baseline_specs[path] != current_specs[path]
    )
    presentation_sublayer_exact = current["sub_layer_paths"] == [
        presentation_layer.identifier
    ]
    failures = []
    if not baseline_hash_valid:
        failures.append("baseline_snapshot_hash_mismatch")
    if baseline.get("sub_layer_paths") != []:
        failures.append("baseline_sublayers_not_empty")
    if baseline_unexpected:
        failures.append("baseline_unexpected_scene_specs")
    if removed_paths:
        failures.append("baseline_specs_removed")
    if unexpected_paths:
        failures.append("unexpected_scene_specs")
    if physx_isosurface["present"] and not physx_isosurface[
        "exact_known_structure"
    ]:
        failures.append("physx_runtime_isosurface_structure_changed")
    if not presentation_sublayer_exact:
        failures.append("presentation_sublayer_mismatch")
    runtime_spec_residue = bool(added_paths or removed_paths or modified_paths)
    author_session_delta_status = (
        "RESIDUAL" if runtime_spec_residue else "CLEAN"
    )
    return {
        "phase": "AUTHOR_FREEZE_BEFORE_REPLICATOR",
        "classification_gate_status": "PASS" if not failures else "FAIL",
        "validation_failures": failures,
        "native_cleanup_status": "NOT_APPLICABLE_AUTHOR_STAGE",
        "session_delta_status": author_session_delta_status,
        "manual_restore_status": "NOT_APPLICABLE_AUTHOR_STAGE",
        "entry_isolation_status": "PENDING",
        "composed_world_default_time_property_snapshot_equivalence_"
        "excluding_known_physx_runtime_status": "NOT_VERIFIED",
        "full_render_entry_equivalence_status": "NOT_CLAIMED",
        "baseline_snapshot_sha256": baseline.get("snapshot_sha256"),
        "at_export_snapshot_sha256": current["snapshot_sha256"],
        "baseline_root_prim_paths": baseline.get("root_prim_paths"),
        "at_export_root_prim_paths": current["root_prim_paths"],
        "baseline_sublayer_paths": baseline.get("sub_layer_paths"),
        "at_export_sublayer_paths": current["sub_layer_paths"],
        "presentation_sublayer_exact": presentation_sublayer_exact,
        "added_spec_paths": added_paths,
        "removed_spec_paths": removed_paths,
        "modified_spec_paths": modified_paths,
        "baseline_unexpected_spec_paths": baseline_unexpected,
        "unexpected_spec_paths": unexpected_paths,
        "allowed_runtime_namespace_roots": list(export_runtime_roots),
        "physx_runtime_isosurface": physx_isosurface,
        "unclassified_scene_opinion_count": len(unexpected_paths),
        "runtime_session_specs_observed": runtime_spec_residue,
        "runtime_session_specs_exported": False,
        "allowed_claims": [
            "author_session_delta_classified=true",
            "static_entry_excludes_author_session_layer=true",
        ],
        "blocked_claims": [
            "composed_world_default_time_property_snapshot_equivalence_"
            "excluding_known_physx_runtime_verified=true",
            "full_render_entry_equivalence_verified=true",
            "session_layer_equivalence_verified=true",
            "pixel_equivalence_verified=true",
        ],
    }


class _PresentationLayerStageProxy:
    """Delegate Stage APIs while redirecting legacy root edit-target requests."""

    def __init__(self, stage: Any, presentation_layer: Any):
        self.wrapped_stage = stage
        self._presentation_layer = presentation_layer

    def __getattr__(self, name: str) -> Any:
        return getattr(self.wrapped_stage, name)

    def SetEditTarget(self, edit_target: Any) -> None:
        layer = (
            edit_target.GetLayer()
            if hasattr(edit_target, "GetLayer")
            else edit_target
        )
        root_identifier = self.wrapped_stage.GetRootLayer().identifier
        if getattr(layer, "identifier", None) == root_identifier:
            layer = self._presentation_layer
        self.wrapped_stage.SetEditTarget(layer)


def presentation_layer_stage_proxy(stage: Any, presentation_layer: Any) -> Any:
    if stage.GetEditTarget().GetLayer().identifier != presentation_layer.identifier:
        raise RuntimeError("presentation_layer_proxy_requires_active_edit_target")
    return _PresentationLayerStageProxy(stage, presentation_layer)


def export_static_candidate_entry(
    stage: Any,
    *,
    presentation_layer: Any,
    session_layer_baseline: Mapping[str, Any],
    source_usd_path: str | os.PathLike[str],
    expected_source_sha256: str,
    static_usd_path: str | os.PathLike[str],
    required_presentation_prim_path: str,
    required_source_prim_path: str,
    expected_presentation_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Save presentation opinions and compose them over an unchanged source USD."""
    from pxr import Sdf, Usd

    source_path = Path(source_usd_path).expanduser().resolve()
    static_path = Path(static_usd_path).expanduser().resolve()
    presentation_path = _absolute_path_without_symlink_resolution(
        presentation_layer.realPath
    )
    expected_presentation = (
        presentation_path
        if expected_presentation_path is None
        else _absolute_path_without_symlink_resolution(expected_presentation_path)
    )
    root_layer = stage.GetRootLayer()
    if (
        not isinstance(expected_source_sha256, str)
        or len(expected_source_sha256) != 64
        or any(character not in _HEX_DIGITS for character in expected_source_sha256)
    ):
        raise ValueError("expected_source_sha256_must_be_lowercase_hex")
    source_sha256_before = _sha256_file(source_path)
    if source_sha256_before != expected_source_sha256:
        raise RuntimeError(
            "source_file_sha256_changed_before_static_export:"
            f"actual={source_sha256_before}:expected={expected_source_sha256}"
        )
    session_contract = build_export_session_layer_contract(
        stage,
        presentation_layer=presentation_layer,
        baseline_snapshot=session_layer_baseline,
    )
    if session_contract["classification_gate_status"] != "PASS":
        raise SessionLayerValidationError(
            "session_layer_scene_opinions_present_at_export:"
            f"failures={session_contract['validation_failures']}:"
            f"unexpected_specs={session_contract['unexpected_spec_paths']}:"
            f"sublayers={session_contract['at_export_sublayer_paths']}",
            session_contract,
        )
    if not root_layer.realPath:
        raise RuntimeError("source_root_layer_has_no_real_path")
    if Path(root_layer.realPath).resolve() != source_path:
        raise RuntimeError(
            f"source_root_layer_mismatch:{root_layer.realPath}!={source_path}"
        )
    if root_layer.dirty:
        raise RuntimeError("source_root_layer_dirty_before_static_export")
    if stage.GetEditTarget().GetLayer().identifier != presentation_layer.identifier:
        raise RuntimeError("presentation_layer_is_not_current_edit_target")
    if not stage.GetPrimAtPath(required_presentation_prim_path).IsValid():
        raise RuntimeError(
            "required_presentation_prim_missing_before_export:"
            f"{required_presentation_prim_path}"
        )
    if not stage.GetPrimAtPath(required_source_prim_path).IsValid():
        raise RuntimeError(
            f"required_source_prim_missing_before_export:{required_source_prim_path}"
        )
    permission_recovery = _save_presentation_layer_with_permission_recovery(
        stage,
        presentation_layer=presentation_layer,
        expected_presentation_path=expected_presentation,
        source_path=source_path,
        expected_source_sha256=expected_source_sha256,
    )
    if root_layer.dirty:
        raise RuntimeError("source_root_layer_dirty_after_presentation_save")
    if static_path.exists():
        raise ValueError(f"static_candidate_entry_already_exists:{static_path}")
    static_path.parent.mkdir(parents=True, exist_ok=True)
    entry_layer = Sdf.Layer.CreateNew(str(static_path))
    if entry_layer is None:
        raise RuntimeError(f"static_candidate_entry_create_failed:{static_path}")
    _normalize_new_usd_layer_private_writable(
        entry_layer,
        static_path,
        label="static_candidate_entry",
    )
    skipped_metadata_keys = {"subLayers", "subLayerOffsets"}
    copied_metadata_keys: list[str] = []
    for key in root_layer.pseudoRoot.ListInfoKeys():
        if key in skipped_metadata_keys:
            continue
        entry_layer.pseudoRoot.SetInfo(key, root_layer.pseudoRoot.GetInfo(key))
        copied_metadata_keys.append(str(key))
    presentation_sublayer = os.path.relpath(presentation_path, static_path.parent)
    source_sublayer = os.path.relpath(source_path, static_path.parent)
    if Path(source_sublayer).is_absolute():
        raise RuntimeError("static_candidate_source_sublayer_not_relative")
    entry_layer.subLayerPaths = [presentation_sublayer, source_sublayer]
    if not entry_layer.Save():
        raise RuntimeError(f"static_candidate_entry_save_failed:{static_path}")
    reopened = Usd.Stage.Open(str(static_path))
    if reopened is None:
        raise RuntimeError(f"static_candidate_entry_reopen_failed:{static_path}")
    if not reopened.GetPrimAtPath(required_presentation_prim_path).IsValid():
        raise RuntimeError(
            "static_candidate_entry_missing_presentation_prim:"
            f"{required_presentation_prim_path}"
        )
    if not reopened.GetPrimAtPath(required_source_prim_path).IsValid():
        raise RuntimeError(
            f"static_candidate_entry_missing_source_prim:{required_source_prim_path}"
        )
    used_layer_identifiers = {
        Path(layer.realPath).resolve()
        for layer in reopened.GetUsedLayers()
        if layer.realPath
    }
    if source_path not in used_layer_identifiers:
        raise RuntimeError(
            f"static_candidate_entry_source_root_unresolved:{source_path}"
        )
    source_without_session = Usd.Stage.Open(str(source_path))
    if source_without_session is None:
        raise RuntimeError(f"source_stage_plain_reopen_failed:{source_path}")
    session_only_prim_paths = sorted(
        path
        for path, payload in snapshot_session_layer(stage)["specs"].items()
        if path != "/"
        and payload.get("spec_type") == "PrimSpec"
        and not source_without_session.GetPrimAtPath(path).IsValid()
    )
    leaked_session_prim_paths = [
        path
        for path in session_only_prim_paths
        if reopened.GetPrimAtPath(path).IsValid()
    ]
    if leaked_session_prim_paths:
        raise RuntimeError(
            "static_candidate_entry_contains_session_only_runtime_prims:"
            + ",".join(leaked_session_prim_paths)
        )
    source_sha256_after = _sha256_file(source_path)
    if source_sha256_after != expected_source_sha256:
        raise RuntimeError(
            "source_file_sha256_changed_during_static_export:"
            f"actual={source_sha256_after}:expected={expected_source_sha256}"
        )
    session_contract["entry_isolation_status"] = "PASS"
    source_default_prim = stage.GetDefaultPrim()
    reopened_default_prim = reopened.GetDefaultPrim()
    if bool(source_default_prim) != bool(reopened_default_prim) or (
        source_default_prim
        and reopened_default_prim
        and source_default_prim.GetPath() != reopened_default_prim.GetPath()
    ):
        raise RuntimeError("static_candidate_entry_default_prim_mismatch")
    from pxr import UsdGeom

    source_stage_metadata = {
        "up_axis": str(UsdGeom.GetStageUpAxis(stage)),
        "meters_per_unit": float(UsdGeom.GetStageMetersPerUnit(stage)),
        "start_time_code": float(stage.GetStartTimeCode()),
        "end_time_code": float(stage.GetEndTimeCode()),
        "time_codes_per_second": float(stage.GetTimeCodesPerSecond()),
        "frames_per_second": float(stage.GetFramesPerSecond()),
    }
    reopened_stage_metadata = {
        "up_axis": str(UsdGeom.GetStageUpAxis(reopened)),
        "meters_per_unit": float(UsdGeom.GetStageMetersPerUnit(reopened)),
        "start_time_code": float(reopened.GetStartTimeCode()),
        "end_time_code": float(reopened.GetEndTimeCode()),
        "time_codes_per_second": float(reopened.GetTimeCodesPerSecond()),
        "frames_per_second": float(reopened.GetFramesPerSecond()),
    }
    if source_stage_metadata != reopened_stage_metadata:
        raise RuntimeError(
            "static_candidate_entry_stage_metadata_mismatch:"
            f"source={source_stage_metadata}:reopened={reopened_stage_metadata}"
        )
    capture_baseline = validate_capture_persistent_layer_baseline(
        build_capture_persistent_layer_baseline(
            source_path=source_path,
            presentation_path=presentation_path,
            static_entry_path=static_path,
            expected_source={
                **permission_recovery["source_path_identity"]["after_relock"],
                "sha256": permission_recovery["source_file_sha256"][
                    "after_relock"
                ],
            },
            expected_presentation={
                **permission_recovery["presentation_path_identity"][
                    "after_relock"
                ],
                "sha256": permission_recovery["presentation_file_sha256"][
                    "after_relock"
                ],
            },
        )
    )
    return {
        "source_root_path": str(source_path),
        "source_root_sha256": source_sha256_after,
        "source_file_sha256_before": source_sha256_before,
        "source_file_sha256_after": source_sha256_after,
        "source_root_unchanged": not root_layer.dirty
        and source_sha256_before == source_sha256_after == expected_source_sha256,
        "presentation_layer_path": str(presentation_path),
        "presentation_layer_sha256": _sha256_file(presentation_path),
        "presentation_layer_export_permission_recovery": permission_recovery,
        "presentation_sublayer_path": presentation_sublayer,
        "static_entry_path": str(static_path),
        "static_entry_sha256": _sha256_file(static_path),
        "capture_persistent_layer_baseline": capture_baseline,
        "static_entry_source_sublayer_path": source_sublayer,
        "source_sublayer_path_mode": "relative_cell_source_snapshot",
        "source_sublayer_portable": True,
        "requires_localization_before_colleague_delivery": False,
        "static_entry_reopened": True,
        "copied_root_metadata_keys": sorted(copied_metadata_keys),
        "source_stage_metadata": source_stage_metadata,
        "reopened_stage_metadata": reopened_stage_metadata,
        "stage_metadata_preserved": True,
        "required_presentation_prim_path": required_presentation_prim_path,
        "required_presentation_prim_resolved": True,
        "required_source_prim_path": required_source_prim_path,
        "required_source_prim_resolved": True,
        "source_root_layer_resolved": True,
        "session_layer_runtime_opinions": {
            **session_contract,
            "session_only_prim_paths": session_only_prim_paths,
            "session_only_prim_paths_absent_from_static_entry": True,
        },
        "excluded_kit_runtime_session_root_paths": sorted(
            set(session_contract["at_export_root_prim_paths"])
            & set(ALLOWED_KIT_RUNTIME_SESSION_ROOT_PATHS)
        ),
        "excluded_session_runtime_root_paths": session_contract[
            "at_export_root_prim_paths"
        ],
        "session_world_opinions_present": session_contract[
            "physx_runtime_isosurface"
        ]["present"],
        "session_world_opinions_exact_known_physx_runtime_isosurface": (
            session_contract["physx_runtime_isosurface"]["present"]
            and session_contract["physx_runtime_isosurface"][
                "exact_known_structure"
            ]
        ),
        "kit_runtime_session_roots_exported": False,
    }


def validate_candidate_runtime_evidence_gate(
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Require every lifecycle state before emitting positive render claims."""
    lifecycle = contract.get("capture_stage_lifecycle")
    cleanup = contract.get("replicator_resource_cleanup")
    runtime = contract.get("runtime_contract")
    failures: list[str] = []
    if not isinstance(cleanup, Mapping) or cleanup.get("cleanup_complete") is not True:
        failures.append("replicator_cleanup_incomplete")
    if not isinstance(cleanup, Mapping) or cleanup.get("cleanup_failures"):
        failures.append("replicator_cleanup_failures_present")
    if not isinstance(lifecycle, Mapping):
        failures.append("capture_stage_lifecycle_missing")
        lifecycle = {}
    persistent = lifecycle.get("persistent_layers_after_capture") or {}
    if persistent.get("verified") is not True:
        failures.append("persistent_layer_verification_missing")
    if persistent.get("used_layer_set_unchanged") is not True:
        failures.append("persistent_layer_set_changed")
    residue = lifecycle.get("session_residue") or {}
    scoped_status_field = (
        "composed_world_default_time_property_snapshot_equivalence_"
        "excluding_known_physx_runtime_status"
    )
    if residue.get("classification_gate_status") != "PASS":
        failures.append("capture_session_residue_unclassified")
    if residue.get(scoped_status_field) != "PASS":
        failures.append("scoped_composed_snapshot_equivalence_not_pass")
    if residue.get("full_render_entry_equivalence_status") != "NOT_CLAIMED":
        failures.append("full_render_entry_equivalence_boundary_missing")
    discard = lifecycle.get("capture_stage_discard") or {}
    if discard.get("discarded") is not True:
        failures.append("capture_stage_not_discarded")
    quiescence = lifecycle.get("capture_session_quiescence") or {}
    if not str(quiescence.get("quiescence_status", "")).startswith("PASS_"):
        failures.append("capture_session_not_quiescent")
    final_binding = lifecycle.get(
        "final_presentation_binding_after_quiescence"
    ) or {}
    if final_binding.get("verified") is not True:
        failures.append("final_presentation_binding_not_verified")
    fingerprints = [
        lifecycle.get("frozen_world_fingerprint"),
        lifecycle.get("capture_world_fingerprint"),
        lifecycle.get("reopened_world_fingerprint"),
    ]
    if any(not isinstance(value, Mapping) for value in fingerprints):
        failures.append("composed_snapshot_fingerprint_missing")
    elif not (fingerprints[0] == fingerprints[1] == fingerprints[2]):
        failures.append("composed_snapshot_fingerprints_diverged")
    elif fingerprints[0].get("algorithm") != COMPOSED_WORLD_FINGERPRINT_ALGORITHM:
        failures.append("composed_snapshot_fingerprint_algorithm_mismatch")
    if not isinstance(runtime, Mapping):
        failures.append("runtime_contract_missing")
        runtime = {}
    for field, expected in (
        ("capture_stage_discarded_after_candidate", True),
        ("observed_default_time_usd_point_attributes_changed", False),
        ("timeline_observed_stopped_at_all_checkpoints", True),
    ):
        if runtime.get(field) is not expected:
            failures.append(f"runtime_contract_{field}_mismatch")
    gate = {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "positive_claims_conditioned_on_gate": True,
        "scoped_fingerprint_status_field": scoped_status_field,
    }
    if failures:
        raise ValueError(
            "candidate_runtime_evidence_gate_failed:"
            + json.dumps(gate, sort_keys=True)
        )
    return gate


def finalize_candidate_manifest(
    contract: Mapping[str, Any],
    *,
    accepted_replay: AcceptedReplayInput,
    candidate_dir: str | os.PathLike[str],
    static_usd_path: str | os.PathLike[str],
    presentation_layer_path: str | os.PathLike[str],
    closeup_image_paths: Sequence[str | os.PathLike[str]],
    context_image_paths: Sequence[str | os.PathLike[str]],
    native_context_image_paths: Sequence[str | os.PathLike[str]],
    video_paths: Mapping[str, str | os.PathLike[str]],
    diagnostic_artifact_paths: Mapping[str, str | os.PathLike[str]],
) -> dict[str, Any]:
    """Hash complete artifacts and leave visual acceptance to independent review."""
    candidate_root = Path(candidate_dir).resolve()
    authoritative_frame_contract_validation = (
        validate_candidate_frame_contracts_against_accepted(
            contract,
            accepted_replay,
        )
    )
    runtime_evidence_gate = validate_candidate_runtime_evidence_gate(contract)
    static_path = Path(static_usd_path)
    presentation_path = Path(presentation_layer_path)
    closeups = [Path(path) for path in closeup_image_paths]
    contexts = [Path(path) for path in context_image_paths]
    native_contexts = [Path(path) for path in native_context_image_paths]
    expected_video_roles = {
        "context",
        "source_beaker_closeup",
        "native_table_context",
    }
    if set(video_paths) != expected_video_roles:
        raise ValueError(
            "candidate_video_roles_invalid:"
            f"actual={sorted(video_paths)}:expected={sorted(expected_video_roles)}"
        )
    if set(diagnostic_artifact_paths) != set(
        CANDIDATE_DIAGNOSTIC_ARTIFACT_ROLES
    ):
        raise ValueError(
            "candidate_diagnostic_artifact_roles_invalid:"
            f"actual={sorted(diagnostic_artifact_paths)}:"
            f"expected={sorted(CANDIDATE_DIAGNOSTIC_ARTIFACT_ROLES)}"
        )
    videos = {role: Path(path) for role, path in video_paths.items()}
    diagnostics = {
        role: Path(path) for role, path in diagnostic_artifact_paths.items()
    }
    render_output_contract = contract.get("render_output_contract")
    if not isinstance(render_output_contract, Mapping):
        raise ValueError("candidate_render_output_contract_missing")
    output_width = _require_plain_int(
        "candidate_render_width", render_output_contract.get("width"), minimum=1
    )
    output_height = _require_plain_int(
        "candidate_render_height", render_output_contract.get("height"), minimum=1
    )
    raw_fps = render_output_contract.get("fps")
    if isinstance(raw_fps, bool):
        raise ValueError("candidate_render_fps_must_be_positive_and_finite")
    try:
        output_fps = float(raw_fps)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "candidate_render_fps_must_be_positive_and_finite"
        ) from exc
    if not math.isfinite(output_fps) or output_fps <= 0.0:
        raise ValueError("candidate_render_fps_must_be_positive_and_finite")
    expected_frames = _require_plain_int(
        "candidate_frame_count", contract.get("frame_count"), minimum=1
    )
    raw_frame_indices = render_output_contract.get("expected_frame_indices")
    if not isinstance(raw_frame_indices, list):
        raise ValueError("candidate_expected_frame_indices_must_be_list")
    expected_frame_indices = [
        _require_plain_int(
            f"candidate_expected_frame_index_{offset}", value, minimum=0
        )
        for offset, value in enumerate(raw_frame_indices)
    ]
    if expected_frame_indices != list(contract.get("frame_indices") or []):
        raise ValueError("candidate_expected_frame_indices_diverged_from_trace")
    if len(expected_frame_indices) != expected_frames:
        raise ValueError("candidate_expected_frame_indices_count_mismatch")
    if (
        len(closeups) != expected_frames
        or len(contexts) != expected_frames
        or len(native_contexts) != expected_frames
    ):
        raise ValueError(
            "candidate_images_incomplete:"
            f"closeup={len(closeups)},context={len(contexts)},"
            f"native_context={len(native_contexts)},expected={expected_frames}"
        )
    missing_images = [
        path
        for path in [*closeups, *contexts, *native_contexts]
        if not path.is_file()
    ]
    if missing_images:
        raise ValueError(
            "candidate_images_incomplete:missing="
            + ",".join(str(path) for path in missing_images)
        )
    _validate_nonempty_artifact(static_path, label="static_usd")
    _validate_nonempty_artifact(presentation_path, label="presentation_layer")
    image_sets = {
        "source_beaker_closeup": closeups,
        "context": contexts,
        "native_table_context": native_contexts,
    }
    image_validation: dict[str, list[dict[str, Any]]] = {}
    for role, paths in image_sets.items():
        expected_names = [
            f"frame_{frame_index:04d}.png"
            for frame_index in expected_frame_indices
        ]
        actual_names = [path.name for path in paths]
        if actual_names != expected_names:
            raise ValueError(
                "candidate_image_frame_mapping_mismatch:"
                f"role={role}:actual={actual_names}:expected={expected_names}"
            )
        image_validation[role] = [
            _validate_png(path, width=output_width, height=output_height)
            for path in paths
        ]
    video_validation: dict[str, Any] = {}
    for role, path in videos.items():
        _validate_nonempty_artifact(path, label="video")
        probe = probe_mp4_against_png_frames(path, image_sets[role])
        if (
            probe.get("decodable") is not True
            or probe.get("frame_count") != expected_frames
        ):
            raise ValueError(
                "candidate_video_frame_count_mismatch:"
                f"role={role}:actual={probe.get('frame_count')}:"
                f"expected={expected_frames}"
            )
        if (
            probe.get("width") != output_width
            or probe.get("height") != output_height
        ):
            raise ValueError(
                "candidate_video_size_mismatch:"
                f"role={role}:actual={(probe.get('width'), probe.get('height'))}:"
                f"expected={(output_width, output_height)}"
            )
        try:
            video_fps = float(probe.get("fps"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"candidate_video_fps_invalid:role={role}") from exc
        if not math.isclose(video_fps, output_fps, rel_tol=0.0, abs_tol=1e-3):
            raise ValueError(
                "candidate_video_fps_mismatch:"
                f"role={role}:actual={video_fps}:expected={output_fps}"
            )
        if probe.get("content_sequence_bound") is not True:
            raise ValueError(
                "candidate_video_content_sequence_mismatch:"
                f"role={role}:max_mae={probe.get('maximum_frame_mean_absolute_error')}:"
                f"min_psnr={probe.get('minimum_frame_psnr_db')}"
            )
        video_validation[role] = probe
    for path in diagnostics.values():
        _validate_nonempty_artifact(path, label="diagnostic_artifact")
    lifecycle = contract["capture_stage_lifecycle"]
    fingerprint_artifact_validation = {
        role: validate_composed_world_fingerprint_artifact(
            diagnostics[role],
            expected_fingerprint=lifecycle[lifecycle_key],
        )
        for role, lifecycle_key in (
            (
                "frozen_composed_world_fingerprint_json",
                "frozen_world_fingerprint",
            ),
            (
                "capture_composed_world_fingerprint_json",
                "capture_world_fingerprint",
            ),
            (
                "reopened_composed_world_fingerprint_json",
                "reopened_world_fingerprint",
            ),
        )
    }
    physical_trace_identity = contract.get("physical_trace_identity")
    if not isinstance(physical_trace_identity, Mapping):
        raise ValueError("candidate_physical_trace_identity_missing")
    frame_binding_validation = validate_capture_frame_bindings_artifact(
        diagnostics["capture_frame_bindings_json"],
        candidate_id=str(contract.get("candidate_id", "")),
        physical_trace_sha256=str(
            physical_trace_identity.get("physical_trace_sha256", "")
        ),
        frame_indices=expected_frame_indices,
        image_paths_by_role={
            "context": contexts,
            "source_beaker_closeup": closeups,
            "native_table_context": native_contexts,
        },
        expected_frame_contracts=contract["frames"],
        expected_effective_look_contract=contract.get(
            "effective_replay_look_contract"
        ),
    )
    artifacts = [
        static_path,
        presentation_path,
        *closeups,
        *contexts,
        *native_contexts,
        *videos.values(),
        *diagnostics.values(),
    ]
    resolved_artifacts = [path.resolve() for path in artifacts]
    if len(set(resolved_artifacts)) != len(resolved_artifacts):
        raise ValueError("candidate_artifact_paths_must_be_unique")
    hashes = {
        _artifact_relative_path(candidate_root, path): _sha256_file(path)
        for path in artifacts
    }
    finalized = deepcopy(dict(contract))
    finalized.update(
        {
            "static_candidate_usd_path": str(static_path.resolve()),
            "presentation_layer_path": str(presentation_path.resolve()),
            "closeup_image_paths": [str(path.resolve()) for path in closeups],
            "context_image_paths": [str(path.resolve()) for path in contexts],
            "native_context_image_paths": [
                str(path.resolve()) for path in native_contexts
            ],
            "video_paths": {
                role: str(path.resolve()) for role, path in videos.items()
            },
            "video_validation": video_validation,
            "render_output_validation": {
                "width": output_width,
                "height": output_height,
                "fps": output_fps,
                "frame_indices": expected_frame_indices,
                "image_validation": image_validation,
                "video_validation": video_validation,
                "all_images_decoded": True,
                "all_videos_decoded": True,
                "all_video_content_sequences_bound": True,
                "filename_trace_mapping_verified": True,
                "capture_frame_binding_validation": frame_binding_validation,
                "authoritative_frame_contract_validation": (
                    authoritative_frame_contract_validation
                ),
            },
            "diagnostic_artifact_paths": {
                role: str(path.resolve()) for role, path in diagnostics.items()
            },
            "artifact_sha256": hashes,
            "render_artifact_set_complete": True,
            "standalone_final_evidence_authority": False,
            "top_level_post_application_close_manifest_required": True,
            "execution_source_end_verification_status": (
                "PENDING_TOP_LEVEL_POST_APPLICATION_CLOSE"
            ),
            "runtime_evidence_gate": runtime_evidence_gate,
            "fingerprint_artifact_validation": (
                fingerprint_artifact_validation
            ),
            "portable_dependency_closure_complete": False,
            "colleague_delivery_ready": False,
            "visual_review_verdict": "PENDING_INDEPENDENT_REVIEW",
            "omniglass_reference_particle_look_selected": False,
            "claim_boundary": {
                "allowed": [
                    "deterministic_presentation_proxy_derived_from_accepted_trace_rendered=true",
                    "timeline_observed_stopped_at_all_capture_checkpoints=true",
                    "observed_default_time_usd_point_attributes_unchanged_at_capture_checkpoints=true",
                    "render_only_omniglass_proxy_authored=true",
                    "candidate_images_recorded=true",
                    "static_entry_frozen_before_replicator=true",
                    "capture_updates_isolated_in_anonymous_layer=true",
                    "capture_persistent_layers_byte_unchanged=true",
                    "capture_and_static_entry_default_time_property_snapshot_"
                    "fingerprints_equal_excluding_known_physx_runtime=true",
                    "capture_stage_discarded=true",
                    "replicator_native_cleanup_residue_recorded=true",
                ],
                "blocked": [
                    "visual_review_passed=true",
                    "omniglass_reference_particle_look_selected=true",
                    "presentation_points_are_physical_particles=true",
                    "gpu_or_fabric_physics_state_proven_unchanged=true",
                    "physical_trace_directly_rendered=true",
                    "portable_dependency_closure_complete=true",
                    "free_surface_shape_physically_valid=true",
                    "fluid_dynamics_validated_by_presentation_surface=true",
                    "physical_volume_parity_validated_by_presentation_proxy=true",
                    "full_render_entry_equivalence_verified=true",
                    "session_layer_equivalence_verified=true",
                    "pixel_equivalence_verified=true",
                ],
            },
        }
    )
    return finalized


def hide_physical_and_debug_points(stage: Any) -> dict[str, Any]:
    from pxr import UsdGeom

    hidden: list[str] = []
    physical_roots = {
        "/World/fluid",
        "/World/ParticleSet",
        "/World/ParticleSystem",
        "/World/CompletedPBD/ParticleSet",
        "/World/CompletedPBD/ParticleSystem",
    }
    for prim in list(stage.Traverse()):
        path = str(prim.GetPath())
        lower_path = path.lower()
        is_debug = any(
            token in lower_path for token in ("debug", "reviewmarker", "visualizer")
        )
        is_physical_root = path in physical_roots
        if path != PRESENTATION_POINTS_PATH and (is_debug or is_physical_root):
            imageable = UsdGeom.Imageable(prim)
            if imageable:
                imageable.MakeInvisible()
                hidden.append(path)
    return {
        "hidden_paths": sorted(hidden),
        "disabled_particle_system_paths": [],
        "physics_attributes_authored": False,
        "physical_and_debug_points_hidden": True,
    }


def require_stopped_timeline(timeline: Any) -> None:
    if bool(timeline.is_playing()):
        raise RuntimeError("timeline_must_remain_stopped_for_static_trace_replay")


def _normalized_vector(name: str, value: Sequence[float]) -> tuple[float, float, float]:
    vector = _vector3(name, value)
    length = math.sqrt(math.fsum(component * component for component in vector))
    if not math.isfinite(length) or length <= 0.0:
        raise ValueError(f"{name}_must_have_positive_length")
    return tuple(component / length for component in vector)


def _cross_vector(
    left: Sequence[float], right: Sequence[float]
) -> tuple[float, float, float]:
    return (
        float(left[1]) * float(right[2])
        - float(left[2]) * float(right[1]),
        float(left[2]) * float(right[0])
        - float(left[0]) * float(right[2]),
        float(left[0]) * float(right[1])
        - float(left[1]) * float(right[0]),
    )


def _dot_vector(left: Sequence[float], right: Sequence[float]) -> float:
    return math.fsum(float(left[index]) * float(right[index]) for index in range(3))


def _camera_projection_contract(
    *,
    eye: Sequence[float],
    target: Sequence[float],
    up: Sequence[float],
    focal_length: float,
    horizontal_aperture: float,
    vertical_aperture: float,
    required_points: Sequence[Sequence[float]],
    width: int,
    height: int,
) -> dict[str, Any]:
    resolution_width = _require_plain_int("camera_width", width, minimum=1)
    resolution_height = _require_plain_int("camera_height", height, minimum=1)
    eye_value = _vector3("camera_eye", eye)
    target_value = _vector3("camera_target", target)
    up_value = _normalized_vector("camera_up", up)
    forward = _normalized_vector(
        "camera_forward",
        tuple(target_value[index] - eye_value[index] for index in range(3)),
    )
    right = _normalized_vector(
        "camera_right", _cross_vector(forward, up_value)
    )
    true_up = _normalized_vector(
        "camera_true_up", _cross_vector(right, forward)
    )
    focal = _positive_finite_runtime("camera_focal_length", focal_length)
    horizontal = _positive_finite_runtime(
        "camera_horizontal_aperture", horizontal_aperture
    )
    vertical = _positive_finite_runtime(
        "camera_vertical_aperture", vertical_aperture
    )
    if not required_points:
        raise ValueError("camera_required_points_missing")
    ndc_points = []
    minimum_depth = math.inf
    for index, raw_point in enumerate(required_points):
        point = _vector3(f"camera_required_point_{index}", raw_point)
        relative = tuple(point[axis] - eye_value[axis] for axis in range(3))
        depth = _dot_vector(relative, forward)
        if not math.isfinite(depth) or depth <= 0.01:
            raise ValueError(f"camera_required_point_behind_near_plane:{index}")
        minimum_depth = min(minimum_depth, depth)
        ndc_points.append(
            (
                2.0 * focal * _dot_vector(relative, right) / (horizontal * depth),
                2.0 * focal * _dot_vector(relative, true_up) / (vertical * depth),
            )
        )
    minimum_x = min(point[0] for point in ndc_points)
    maximum_x = max(point[0] for point in ndc_points)
    minimum_y = min(point[1] for point in ndc_points)
    maximum_y = max(point[1] for point in ndc_points)
    minimum_margin = min(
        1.0 + minimum_x,
        1.0 - maximum_x,
        1.0 + minimum_y,
        1.0 - maximum_y,
    )
    required_margin = 0.05
    all_in_frame = minimum_margin >= required_margin
    return {
        "resolution": [resolution_width, resolution_height],
        "required_point_count": len(required_points),
        "ndc_bounds": {
            "minimum": [minimum_x, minimum_y],
            "maximum": [maximum_x, maximum_y],
        },
        "minimum_depth": minimum_depth,
        "minimum_ndc_margin": minimum_margin,
        "required_minimum_ndc_margin": required_margin,
        "all_required_points_in_frame": all_in_frame,
        "projection_formula": (
            "ndc=2*focal*camera_axis_coordinate/(aperture*forward_depth)"
        ),
    }


def build_measured_beaker_closeup_camera_contract(
    *,
    frame: CupInteriorFrame,
    width: int = 960,
    height: int = 540,
) -> dict[str, Any]:
    measured_height = float(frame.rim_height - frame.outer_floor)
    cup_target_height = frame.interior_floor + min(
        0.045,
        0.5 * float(frame.rim_height - frame.interior_floor),
    )
    target = tuple(
        float(frame.origin_world[index])
        + float(frame.z_axis_world[index]) * cup_target_height
        for index in range(3)
    )
    view_elevation_degrees = 25.0
    azimuth_degrees = -50.0
    horizontal_distance = 0.30
    azimuth = math.radians(azimuth_degrees)
    radial_direction = tuple(
        math.cos(azimuth) * float(frame.x_axis_world[index])
        + math.sin(azimuth) * float(frame.y_axis_world[index])
        for index in range(3)
    )
    axial_distance = horizontal_distance * math.tan(
        math.radians(view_elevation_degrees)
    )
    eye = tuple(
        target[index]
        + radial_direction[index] * horizontal_distance
        + float(frame.z_axis_world[index]) * axial_distance
        for index in range(3)
    )
    up = tuple(float(value) for value in frame.z_axis_world)
    focal_length = 32.0
    horizontal_aperture = 22.0
    vertical_aperture = 16.0
    distance = math.dist(eye, target)
    measured_outer_diameter = 2.0 * float(frame.outer_radius)
    required_points = []
    sample_count = 24
    for canonical_z, radius in (
        (float(frame.outer_floor), float(frame.outer_radius)),
        (float(frame.rim_height), float(frame.outer_radius)),
        (float(frame.outer_floor), 1.35 * float(frame.outer_radius)),
    ):
        for sample in range(sample_count):
            angle = 2.0 * math.pi * sample / sample_count
            required_points.append(
                frame.canonical_to_world(
                    (
                        radius * math.cos(angle),
                        radius * math.sin(angle),
                        canonical_z,
                    )
                )
            )
    projection = _camera_projection_contract(
        eye=eye,
        target=target,
        up=up,
        focal_length=focal_length,
        horizontal_aperture=horizontal_aperture,
        vertical_aperture=vertical_aperture,
        required_points=required_points,
        width=width,
        height=height,
    )
    projection.update(
        {
            "complete_beaker_bounds_projected": True,
            "table_surround_projected": True,
        }
    )
    if projection["all_required_points_in_frame"] is not True:
        raise ValueError("closeup_camera_projection_margin_failed")
    contract = {
        "camera_path": "/World/Beaker2CloseupNativeMaterialCamera",
        "camera_source": "measured_source_beaker_closeup",
        "eye": list(eye),
        "target": list(target),
        "up": list(up),
        "focal_length": focal_length,
        "horizontal_aperture": horizontal_aperture,
        "vertical_aperture": vertical_aperture,
        "measured_outer_diameter": measured_outer_diameter,
        "measured_height": measured_height,
        "camera_distance": distance,
        "view_elevation_degrees": view_elevation_degrees,
        "degrees_off_cup_axis": 90.0 - view_elevation_degrees,
        "azimuth_degrees": azimuth_degrees,
        "horizontal_distance": horizontal_distance,
        "angle_convention": "degrees_above_cup_radial_plane",
        "projected_width_occupancy": (
            focal_length
            * measured_outer_diameter
            / (horizontal_aperture * distance)
        ),
        "projected_height_occupancy": (
            focal_length * measured_height / (vertical_aperture * distance)
        ),
        "base_table_contact_visible_intent": True,
        "liquid_depth_visible_intent": True,
        "review_viewpoint": "three_quarter_oblique_source_beaker",
        "projection_contract": projection,
    }
    contract["camera_contract_sha256"] = _json_sha256(contract)
    return contract


def build_measured_pair_context_camera_contract(
    *,
    region_config: Mapping[str, Any],
    width: int = 960,
    height: int = 540,
) -> dict[str, Any]:
    source = _vector3("pair_context_source_center", region_config.get("source_center"))
    target_cup = _vector3(
        "pair_context_target_center", region_config.get("target_center")
    )
    source_radius = _positive_finite_runtime(
        "pair_context_source_radius", region_config.get("source_radius")
    )
    target_radius = _positive_finite_runtime(
        "pair_context_target_radius", region_config.get("target_radius")
    )
    source_height = _positive_finite_runtime(
        "pair_context_source_height", region_config.get("source_height")
    )
    target_height = _positive_finite_runtime(
        "pair_context_target_height", region_config.get("target_height")
    )
    table_z = float(region_config.get("table_z"))
    if not math.isfinite(table_z):
        raise ValueError("pair_context_table_z_must_be_finite")
    pair_target = (
        (source[0] + target_cup[0]) / 2.0,
        (source[1] + target_cup[1]) / 2.0,
        table_z + 0.05,
    )
    eye = (
        pair_target[0] + 0.62,
        pair_target[1] - 0.12,
        pair_target[2] + 0.30,
    )
    up = (0.0, 0.0, 1.0)
    focal_length = 25.5
    horizontal_aperture = 22.0
    vertical_aperture = 16.0
    distance = math.dist(eye, pair_target)
    center_span = math.hypot(
        source[0] - target_cup[0], source[1] - target_cup[1]
    )
    pair_span = center_span + source_radius + target_radius
    required_points = []
    sample_count = 24
    for center, radius, cup_height in (
        (source, source_radius, source_height),
        (target_cup, target_radius, target_height),
    ):
        bottom = center[2] - cup_height / 2.0
        top = center[2] + cup_height / 2.0
        for z_value, sample_radius in (
            (bottom, radius),
            (top, radius),
            (bottom, 1.12 * radius),
        ):
            for sample in range(sample_count):
                angle = 2.0 * math.pi * sample / sample_count
                required_points.append(
                    (
                        center[0] + sample_radius * math.cos(angle),
                        center[1] + sample_radius * math.sin(angle),
                        z_value,
                    )
                )
    projection = _camera_projection_contract(
        eye=eye,
        target=pair_target,
        up=up,
        focal_length=focal_length,
        horizontal_aperture=horizontal_aperture,
        vertical_aperture=vertical_aperture,
        required_points=required_points,
        width=width,
        height=height,
    )
    projection.update(
        {
            "both_complete_cup_bounds_projected": True,
            "base_surround_points_projected": True,
        }
    )
    if projection["all_required_points_in_frame"] is not True:
        raise ValueError("pair_camera_projection_margin_failed")
    contract = {
        "camera_path": "/World/BeakerPairContextCamera",
        "role": "measured_beaker_pair_context",
        "camera_source": "measured_beaker_pair_context",
        "eye": list(eye),
        "target": list(pair_target),
        "up": list(up),
        "focal_length": focal_length,
        "horizontal_aperture": horizontal_aperture,
        "vertical_aperture": vertical_aperture,
        "camera_distance": distance,
        "source_center": list(source),
        "target_center": list(target_cup),
        "source_radius": source_radius,
        "target_radius": target_radius,
        "source_height": source_height,
        "target_height": target_height,
        "pair_span_with_radii": pair_span,
        "projected_pair_occupancy": (
            focal_length * pair_span / (horizontal_aperture * distance)
        ),
        "both_complete_cup_bounds_required": True,
        "base_table_contact_visible_intent": True,
        "review_viewpoint": "lower_three_quarter_two_beaker_context",
        "projection_contract": projection,
    }
    contract["camera_contract_sha256"] = _json_sha256(contract)
    return contract


def build_replay_camera_contracts(
    *,
    frame: CupInteriorFrame,
    region_config: Mapping[str, Any],
    width: int = 960,
    height: int = 540,
) -> dict[str, dict[str, Any]]:
    return {
        "source_beaker_closeup": build_measured_beaker_closeup_camera_contract(
            frame=frame,
            width=width,
            height=height,
        ),
        "context": build_measured_pair_context_camera_contract(
            region_config=region_config,
            width=width,
            height=height,
        ),
    }


def define_measured_beaker_closeup_camera(
    stage: Any,
    *,
    frame: CupInteriorFrame,
    width: int = 960,
    height: int = 540,
) -> dict[str, Any]:
    """Use an oblique close-up that shows liquid depth and table contact."""
    from pxr import Gf, UsdGeom

    contract = build_measured_beaker_closeup_camera_contract(
        frame=frame,
        width=width,
        height=height,
    )
    camera_path = contract["camera_path"]
    eye = contract["eye"]
    target = contract["target"]
    up = contract["up"]

    camera = UsdGeom.Camera.Define(stage, camera_path)
    transform = (
        Gf.Matrix4d(1)
        .SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(*up))
        .GetInverse()
    )
    camera.ClearXformOpOrder()
    camera.AddTransformOp().Set(transform)
    camera.CreateFocalLengthAttr(contract["focal_length"])
    camera.CreateHorizontalApertureAttr(contract["horizontal_aperture"])
    camera.CreateVerticalApertureAttr(contract["vertical_aperture"])
    camera.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))
    return contract


def define_measured_pair_context_camera(
    stage: Any,
    *,
    region_config: Mapping[str, Any],
    width: int = 960,
    height: int = 540,
) -> dict[str, Any]:
    """Frame both measured beakers at a useful medium-wide tabletop scale."""
    from pxr import Gf, UsdGeom

    contract = build_measured_pair_context_camera_contract(
        region_config=region_config,
        width=width,
        height=height,
    )
    camera_path = contract["camera_path"]
    pair_target = contract["target"]
    eye = contract["eye"]
    up = contract["up"]
    camera = UsdGeom.Camera.Define(stage, camera_path)
    camera.ClearXformOpOrder()
    camera.AddTransformOp().Set(
        Gf.Matrix4d(1)
        .SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*pair_target), Gf.Vec3d(*up))
        .GetInverse()
    )
    camera.CreateFocalLengthAttr(contract["focal_length"])
    camera.CreateHorizontalApertureAttr(contract["horizontal_aperture"])
    camera.CreateVerticalApertureAttr(contract["vertical_aperture"])
    camera.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))
    return contract


def _positive_finite_runtime(name: str, value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}_must_be_positive_and_finite") from exc
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name}_must_be_positive_and_finite")
    return result


def apply_replay_camera_policy(
    stage: Any,
    *,
    pair_context_info: Mapping[str, Any],
    closeup_info: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Use measured review cameras and retain the native table camera as provenance."""
    from pxr import UsdGeom

    context_path = "/World/Camera1"
    context_prim = stage.GetPrimAtPath(context_path)
    if not context_prim.IsValid() or not context_prim.IsA(UsdGeom.Camera):
        raise RuntimeError(f"native_tabletop_camera_missing:{context_path}")
    context_camera = UsdGeom.Camera(context_prim)
    context_focal_length = context_camera.GetFocalLengthAttr().Get()
    if context_focal_length is None or float(context_focal_length) <= 0.0:
        raise RuntimeError(f"native_tabletop_camera_invalid_focal_length:{context_path}")

    closeup_path = str(closeup_info.get("camera_path", ""))
    closeup_prim = stage.GetPrimAtPath(closeup_path)
    if not closeup_prim.IsValid() or not closeup_prim.IsA(UsdGeom.Camera):
        raise RuntimeError(f"source_beaker_closeup_camera_missing:{closeup_path}")
    closeup_camera = UsdGeom.Camera(closeup_prim)
    closeup_focal_length = float(closeup_info.get("focal_length", 0.0))
    if not math.isfinite(closeup_focal_length) or closeup_focal_length <= 0.0:
        raise RuntimeError("source_beaker_closeup_camera_invalid_focal_length")
    closeup_camera.GetFocalLengthAttr().Set(closeup_focal_length)

    native_context_info = {
        "camera_path": context_path,
        "camera_source": "native_tabletop_camera",
        "focal_length": float(context_focal_length),
    }
    pair_path = str(pair_context_info.get("camera_path", ""))
    pair_prim = stage.GetPrimAtPath(pair_path)
    if not pair_prim.IsValid() or not pair_prim.IsA(UsdGeom.Camera):
        raise RuntimeError(f"measured_pair_context_camera_missing:{pair_path}")
    pair_focal_length = float(pair_context_info.get("focal_length", 0.0))
    if not math.isfinite(pair_focal_length) or pair_focal_length <= 0.0:
        raise RuntimeError("measured_pair_context_camera_invalid_focal_length")
    resolved_context = dict(pair_context_info)
    resolved_context.update(
        {
            "role": "measured_beaker_pair_context",
            "camera_source": "measured_beaker_pair_context",
            "focal_length": pair_focal_length,
            "native_provenance_camera": native_context_info,
        }
    )
    resolved_closeup = dict(closeup_info)
    resolved_closeup.update(
        {
            "role": "source_beaker_closeup",
            "camera_source": "measured_source_beaker_closeup",
            "focal_length": closeup_focal_length,
        }
    )
    return resolved_context, resolved_closeup


def step_static_render_frame(
    *,
    orchestrator: Any,
    timeline: Any,
    rt_subframes: int,
) -> dict[str, Any]:
    if type(rt_subframes) is not int or rt_subframes <= 0:
        raise ValueError("static_render_rt_subframes_must_be_positive_int")
    require_stopped_timeline(timeline)
    time_before = float(timeline.get_current_time())
    orchestrator.step(
        rt_subframes=rt_subframes,
        pause_timeline=True,
        delta_time=0.0,
    )
    require_stopped_timeline(timeline)
    time_after = float(timeline.get_current_time())
    if not math.isclose(time_after, time_before, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError("static_render_advanced_timeline")
    return {
        "rt_subframes": rt_subframes,
        "timeline_time_before": time_before,
        "timeline_time_after": time_after,
        "timeline_advanced": False,
        "replicator_orchestrator_steps_executed": 1,
        "replicator_delta_time": 0.0,
        "physics_step_count_instrumented": False,
        "physics_steps_executed": None,
    }


def _canonical_usd_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return {"nonfinite_float": "nan"}
        if math.isinf(value):
            return {"nonfinite_float": "+inf" if value > 0.0 else "-inf"}
        return 0.0 if value == 0.0 else value
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_usd_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if hasattr(value, "pathString"):
        return str(value.pathString)
    if hasattr(value, "path") and isinstance(getattr(value, "path"), str):
        return str(value.path)
    try:
        return [_canonical_usd_value(item) for item in value]
    except TypeError:
        return str(value)


def usd_observed_default_time_point_attributes_sha256(stage: Any) -> str:
    """Hash composed default-time USD point/instancer attributes."""
    from pxr import UsdGeom

    excluded_roots = (PRESENTATION_POINTS_PATH, PRESENTATION_SURFACE_PATH)
    prim_payloads: list[dict[str, Any]] = []
    for prim in stage.Traverse():
        if not (
            prim.IsA(UsdGeom.Points)
            or prim.IsA(UsdGeom.PointInstancer)
        ):
            continue
        path = str(prim.GetPath())
        if any(path == root or path.startswith(f"{root}/") for root in excluded_roots):
            continue
        attributes = []
        for attribute in sorted(prim.GetAttributes(), key=lambda item: item.GetName()):
            attributes.append(
                {
                    "name": attribute.GetName(),
                    "type": str(attribute.GetTypeName()),
                    "value": _canonical_usd_value(attribute.Get()),
                }
            )
        relationships = []
        for relationship in sorted(
            prim.GetRelationships(), key=lambda item: item.GetName()
        ):
            relationships.append(
                {
                    "name": relationship.GetName(),
                    "targets": sorted(str(path) for path in relationship.GetTargets()),
                }
            )
        prim_payloads.append(
            {
                "path": path,
                "type": prim.GetTypeName(),
                "applied_schemas": sorted(prim.GetAppliedSchemas()),
                "attributes": attributes,
                "relationships": relationships,
            }
        )
    return _json_sha256(
        {
            "schema_version": 1,
            "physical_point_prim_count": len(prim_payloads),
            "physical_point_prims": sorted(
                prim_payloads,
                key=lambda item: item["path"],
            ),
        }
    )
def capture_static_replicator_rgbs(
    *,
    orchestrator: Any,
    timeline: Any,
    annotators: Mapping[str, Any],
    output_paths: Mapping[str, str | os.PathLike[str]],
    width: int,
    height: int,
    rt_subframes: int,
    observed_default_time_usd_point_attributes_hash: Callable[[], str],
) -> dict[str, Any]:
    from PIL import Image
    import numpy as np

    if set(annotators) != set(output_paths):
        raise ValueError("replicator_annotator_output_roles_mismatch")
    observed_before = str(observed_default_time_usd_point_attributes_hash())
    step_contract = step_static_render_frame(
        orchestrator=orchestrator,
        timeline=timeline,
        rt_subframes=rt_subframes,
    )
    orchestrator.wait_until_complete()
    require_stopped_timeline(timeline)
    timeline_time_after = float(timeline.get_current_time())
    if not math.isclose(
        timeline_time_after,
        float(step_contract["timeline_time_before"]),
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise RuntimeError("static_render_advanced_timeline")
    observed_after = str(observed_default_time_usd_point_attributes_hash())
    if observed_after != observed_before:
        raise RuntimeError(
            "static_render_changed_observed_default_time_usd_point_attributes"
        )

    frames: dict[str, dict[str, Any]] = {}
    for role, annotator in annotators.items():
        raw = np.asarray(annotator.get_data())
        if raw.ndim != 3 or raw.shape[:2] != (height, width) or raw.shape[2] < 3:
            raise RuntimeError(
                f"static_replicator_capture_shape_mismatch:{role}:{list(raw.shape)}"
            )
        if raw.dtype == np.uint8:
            converted = raw
        else:
            converted = np.nan_to_num(
                raw.astype(np.float32), nan=0.0, posinf=255.0, neginf=0.0
            )
            if converted.size and float(converted.max()) <= 1.0:
                converted *= 255.0
            converted = np.clip(converted, 0.0, 255.0).astype(np.uint8)
        rgb = converted[:, :, :3]
        mean = float(rgb.mean())
        std = float(rgb.std())
        if mean < 5.0 or std < 2.0:
            raise RuntimeError(
                f"static_replicator_capture_near_black_or_flat:{role}:"
                f"mean={mean}:std={std}"
            )
        path = Path(output_paths[role])
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(rgb, mode="RGB").save(path)
        frames[role] = {
            "status": "saved_static_replicator_rgb",
            "path": str(path),
            "shape": list(raw.shape),
            "dtype": str(raw.dtype),
            "mean": mean,
            "std": std,
            "sha256": _sha256_file(path),
        }
    return {
        "capture_backend": "replicator_render_products",
        "rt_subframes": rt_subframes,
        "timeline_time_before": step_contract["timeline_time_before"],
        "timeline_time_after": timeline_time_after,
        "timeline_advanced": False,
        "observed_default_time_usd_point_attributes_sha256_before": observed_before,
        "observed_default_time_usd_point_attributes_sha256_after": observed_after,
        "observed_default_time_usd_point_attributes_changed": False,
        "replicator_orchestrator_steps_executed": step_contract[
            "replicator_orchestrator_steps_executed"
        ],
        "replicator_delta_time": step_contract["replicator_delta_time"],
        "physics_step_count_instrumented": False,
        "physics_steps_executed": None,
        "frames": frames,
    }


def deactivate_source_fluid_prims_for_presentation(stage: Any) -> dict[str, Any]:
    """Block source fluid graph relationships in a stronger presentation layer."""
    from pxr import Sdf, UsdGeom

    root_layer = stage.GetRootLayer()
    edit_target_layer = stage.GetEditTarget().GetLayer()
    if edit_target_layer.identifier == root_layer.identifier:
        raise RuntimeError("presentation_fluid_deactivation_requires_overlay_layer")
    if root_layer.dirty:
        raise RuntimeError("source_root_dirty_before_presentation_fluid_deactivation")

    results: dict[str, Any] = {}
    graph_changed = False
    for path in (
        SOURCE_SAMPLER_PATH,
        "/World/fluid",
        SOURCE_PARTICLE_SET_PATH,
        SOURCE_PARTICLE_SYSTEM_PATH,
    ):
        prim = stage.GetPrimAtPath(path)
        entry: dict[str, Any] = {
            "existed": bool(prim),
            "visibility_authored_in_presentation_layer": False,
            "disabled_attrs": {},
            "blocked_relationships": {},
        }
        results[path] = entry
        if not prim:
            continue
        imageable = UsdGeom.Imageable(prim)
        if imageable:
            imageable.MakeInvisible()
            entry["visibility_authored_in_presentation_layer"] = True

        if path == SOURCE_SAMPLER_PATH:
            relation = prim.GetRelationship("physxParticleSampling:particles")
            targets_before = list(relation.GetTargets()) if relation else []
            if relation:
                relation.SetTargets([])
            targets_after = list(relation.GetTargets()) if relation else []
            graph_changed = graph_changed or bool(targets_before)
            entry["blocked_relationships"][
                "physxParticleSampling:particles"
            ] = {
                "targets_before": [str(target) for target in targets_before],
                "targets_after": [str(target) for target in targets_after],
                "explicit_empty_target_list_authored": True,
            }
            volume = prim.GetAttribute("physxParticleSampling:volume")
            if not volume:
                volume = prim.CreateAttribute(
                    "physxParticleSampling:volume", Sdf.ValueTypeNames.Bool
                )
            volume.Set(False)
            entry["disabled_attrs"]["physxParticleSampling:volume"] = False

        if path == SOURCE_PARTICLE_SET_PATH:
            relation = prim.GetRelationship("physxParticle:particleSystem")
            targets_before = list(relation.GetTargets()) if relation else []
            if relation:
                relation.SetTargets([])
            targets_after = list(relation.GetTargets()) if relation else []
            graph_changed = graph_changed or bool(targets_before)
            entry["blocked_relationships"]["physxParticle:particleSystem"] = {
                "targets_before": [str(target) for target in targets_before],
                "targets_after": [str(target) for target in targets_after],
                "explicit_empty_target_list_authored": True,
            }
            for name in ("physxParticle:selfCollision", "physxParticle:fluid"):
                attribute = prim.GetAttribute(name)
                if not attribute:
                    attribute = prim.CreateAttribute(name, Sdf.ValueTypeNames.Bool)
                attribute.Set(False)
                entry["disabled_attrs"][name] = False

        if path == SOURCE_PARTICLE_SYSTEM_PATH:
            enabled = prim.GetAttribute("particleSystemEnabled")
            if not enabled:
                enabled = prim.CreateAttribute(
                    "particleSystemEnabled", Sdf.ValueTypeNames.Bool
                )
            enabled.Set(False)
            entry["disabled_attrs"]["particleSystemEnabled"] = False

    sampler_prim = stage.GetPrimAtPath(SOURCE_SAMPLER_PATH)
    sampler_targets = (
        list(
            sampler_prim.GetRelationship(
                "physxParticleSampling:particles"
            ).GetTargets()
        )
        if sampler_prim
        and sampler_prim.GetRelationship("physxParticleSampling:particles")
        else []
    )
    particle_set_prim = stage.GetPrimAtPath(SOURCE_PARTICLE_SET_PATH)
    particle_set_targets = (
        list(
            particle_set_prim.GetRelationship(
                "physxParticle:particleSystem"
            ).GetTargets()
        )
        if particle_set_prim
        and particle_set_prim.GetRelationship("physxParticle:particleSystem")
        else []
    )
    if root_layer.dirty:
        raise RuntimeError("source_root_dirty_after_presentation_fluid_deactivation")
    results["ownership_isolation"] = {
        "sampler_targets_after": [str(target) for target in sampler_targets],
        "particle_set_targets_after": [
            str(target) for target in particle_set_targets
        ],
        "synchronization_required": graph_changed,
        "explicit_overlay_blocking_used": True,
        "verified": not sampler_targets and not particle_set_targets,
    }
    return results


def prepare_static_render_physics_graph(
    stage: Any,
    *,
    native: Any,
    execute_command: Callable[..., Any],
) -> dict[str, Any]:
    """Remove the source sampler graph from the render-only stage copy."""
    edit_target_layer = stage.GetEditTarget().GetLayer()
    sampler = native.remove_legacy_particle_sampling_api(
        stage,
        execute_command=execute_command,
    )
    if stage.GetEditTarget().GetLayer().identifier != edit_target_layer.identifier:
        raise RuntimeError("sampler_removal_changed_candidate_edit_target")
    if sampler.get("verified") is not True or sampler.get("api_present_after") is not False:
        raise RuntimeError("static_render_legacy_particle_sampler_removal_failed")
    deactivation = deactivate_source_fluid_prims_for_presentation(stage)
    if stage.GetEditTarget().GetLayer().identifier != edit_target_layer.identifier:
        raise RuntimeError("fluid_deactivation_changed_candidate_edit_target")
    if deactivation.get("ownership_isolation", {}).get("verified") is not True:
        raise RuntimeError("static_render_source_particle_graph_deactivation_failed")
    return {
        "legacy_particle_sampling_removed": True,
        "source_particle_graph_deactivated": True,
        "sampler_removal": sampler,
        "source_graph_deactivation": deactivation,
    }


class ReplicatorResourceCreationError(RuntimeError):
    def __init__(self, primary: BaseException, cleanup_contract: Mapping[str, Any]):
        self.primary = primary
        self.cleanup_contract = deepcopy(dict(cleanup_contract))
        super().__init__(
            "replicator_resource_creation_failed:"
            f"primary={type(primary).__name__}:{primary}:"
            "partial_cleanup="
            + json.dumps(self.cleanup_contract, sort_keys=True, default=str)
        )


def create_replicator_capture_resources(
    rep: Any,
    *,
    cameras: Mapping[str, Mapping[str, Any]],
    resolution: tuple[int, int],
) -> dict[str, dict[str, Any]]:
    """Create all camera resources and clean partial creation on any failure."""
    expected_roles = {
        "context",
        "source_beaker_closeup",
        "native_table_context",
    }
    if set(cameras) != expected_roles:
        raise ValueError(
            "replicator_camera_roles_invalid:"
            f"actual={sorted(cameras)}:expected={sorted(expected_roles)}"
        )
    width, height = resolution
    if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
        raise ValueError("replicator_resolution_must_be_positive_ints")
    resources: dict[str, dict[str, Any]] = {}
    try:
        for role, camera_info in cameras.items():
            render_product = rep.create.render_product(
                camera_info["camera_path"],
                (width, height),
            )
            resources[role] = {"render_product": render_product}
            annotator = rep.AnnotatorRegistry.get_annotator("rgb")
            resources[role]["annotator"] = annotator
            resources[role]["annotator_attached"] = False
            resources[role]["annotator_detach_required"] = True
            annotator.attach(render_product)
            resources[role]["annotator_attached"] = True
    except BaseException as exc:
        cleanup = destroy_replicator_capture_resources(resources)
        raise ReplicatorResourceCreationError(exc, cleanup) from exc
    return resources


def destroy_replicator_capture_resources(
    resources: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Detach annotators before destroying every render product."""
    detached: list[str] = []
    detach_not_applicable: list[str] = []
    destroyed: list[str] = []
    failures: dict[str, str] = {}
    annotator_groups: dict[int, dict[str, Any]] = {}
    for role, resource in resources.items():
        annotator = resource.get("annotator")
        annotator_detach_required = resource.get(
            "annotator_detach_required", annotator is not None
        )
        if annotator is None or annotator_detach_required is False:
            detach_not_applicable.append(role)
        else:
            group = annotator_groups.setdefault(
                id(annotator),
                {"annotator": annotator, "roles": []},
            )
            group["roles"].append(role)
    for group in annotator_groups.values():
        roles = list(group["roles"])
        try:
            group["annotator"].detach()
            detached.extend(roles)
        except Exception as exc:
            for role in roles:
                failures[f"{role}:detach"] = repr(exc)
    for role, resource in resources.items():
        render_product = resource.get("render_product")
        try:
            render_product.destroy()
            destroyed.append(role)
        except Exception as exc:
            failures[f"{role}:destroy"] = repr(exc)
    return {
        "detached_roles": sorted(detached),
        "detach_not_applicable_roles": sorted(detach_not_applicable),
        "destroyed_roles": sorted(destroyed),
        "cleanup_failures": failures,
        "cleanup_complete": not failures and len(destroyed) == len(resources),
        "detached_annotator_group_count": len(annotator_groups),
    }


def require_replicator_cleanup(contract: Mapping[str, Any]) -> None:
    if contract.get("cleanup_complete") is not True or contract.get(
        "cleanup_failures"
    ):
        raise RuntimeError(
            "replicator_resource_cleanup_failed:"
            + json.dumps(
                dict(contract),
                sort_keys=True,
                separators=(",", ":"),
            )
        )


def validate_replay_mdl_log_segment(
    native: Any,
    *,
    cursor: Mapping[str, Any],
    log_artifact_path: str | os.PathLike[str],
    mdl_source_sha256: Mapping[str, str],
) -> dict[str, Any]:
    """Persist and scan the exact run log without claiming positive compilation."""
    segment = native._read_kit_log_segment(dict(cursor))
    if (
        segment.get("cursor_captured") is not True
        or segment.get("diagnostic_scan_complete") is not True
        or not isinstance(segment.get("log_text"), str)
        or not isinstance(segment.get("log_path"), str)
        or type(segment.get("byte_offset")) is not int
        or type(segment.get("segment_byte_count")) is not int
        or not isinstance(segment.get("segment_sha256"), str)
    ):
        raise RuntimeError(
            "replay_mdl_log_scan_incomplete:"
            + json.dumps(
                {key: value for key, value in segment.items() if key != "log_text"},
                sort_keys=True,
                default=str,
            )
        )
    log_text = segment["log_text"]
    source_log_path = Path(segment["log_path"])
    try:
        with source_log_path.open("rb") as stream:
            stream.seek(segment["byte_offset"])
            raw_segment = stream.read(segment["segment_byte_count"])
    except OSError as exc:
        raise RuntimeError(
            f"replay_mdl_log_segment_unreadable:{type(exc).__name__}:{exc}"
        ) from exc
    if not raw_segment:
        raise RuntimeError("replay_mdl_log_segment_empty")
    raw_sha256 = hashlib.sha256(raw_segment).hexdigest()
    if (
        segment["segment_byte_count"] != len(raw_segment)
        or segment["segment_sha256"] != raw_sha256
        or raw_segment.decode("utf-8", errors="replace") != log_text
    ):
        raise RuntimeError(
            "replay_mdl_log_segment_identity_mismatch:"
            f"declared_count={segment.get('segment_byte_count')}:"
            f"actual_count={len(raw_segment)}:"
            f"declared_sha256={segment.get('segment_sha256')}:"
            f"actual_sha256={raw_sha256}"
        )
    scan = native.scan_mdl_compile_errors(log_text)
    scanner_status = scan.get("mdl_compile_status")
    if scanner_status != native.MDL_COMPILE_STATUS_PASS:
        raise RuntimeError(
            "replay_mdl_compile_failed:"
            + json.dumps(dict(scan), sort_keys=True, default=str)
        )
    mdl_error_scan = {
        key: deepcopy(value)
        for key, value in scan.items()
        if key != "mdl_compile_status"
    }
    mdl_error_scan["status"] = "NO_MATCHING_MDL_ERRORS_OBSERVED"
    mdl_error_scan["scanner_raw_status_interpretation"] = (
        "legacy_PASS_means_error_patterns_not_observed_not_compile_confirmation"
    )
    known_warning_lines = [
        {"line_number": line_number, "line_sha256": _json_sha256(line)}
        for line_number, line in enumerate(log_text.splitlines(), start=1)
        if all(token in line for token in KNOWN_MDL_COMPATIBILITY_WARNING_TOKENS)
    ]
    known_warning = {
        "tokens": list(KNOWN_MDL_COMPATIBILITY_WARNING_TOKENS),
        "count": len(known_warning_lines),
        "matches": known_warning_lines,
        "status": (
            "OBSERVED_NON_FATAL_COMPATIBILITY_WARNING"
            if known_warning_lines
            else "NOT_OBSERVED"
        ),
        "render_failure_inferred": False,
        "failure_policy": (
            "record_separately; do_not_fail_without_matching_compile_error_or_"
            "independent_visual_failure"
        ),
    }
    artifact_path = Path(log_artifact_path).expanduser().resolve()
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    if artifact_path.exists():
        raise ValueError(f"replay_mdl_log_artifact_already_exists:{artifact_path}")
    artifact_path.write_bytes(raw_segment)
    return {
        "run_segment_only": True,
        "diagnostic_scan_complete": True,
        "mdl_error_scan_status": "NO_MATCHING_MDL_ERRORS_OBSERVED",
        "mdl_compile_status": "NOT_POSITIVELY_CONFIRMED",
        "mdl_compile_success_claim_allowed": False,
        "mdl_source_sha256_context": dict(mdl_source_sha256),
        "strict_kit_log_segment": {
            key: value for key, value in segment.items() if key != "log_text"
        },
        "kit_log_segment_artifact": {
            "path": str(artifact_path),
            "byte_count": artifact_path.stat().st_size,
            "sha256": _sha256_file(artifact_path),
        },
        "mdl_error_scan": mdl_error_scan,
        "known_mdl_compatibility_warning": known_warning,
    }


def capture_static_viewport_png(
    *,
    viewport: Any,
    capture_interface: Any,
    capture_to_file: Callable[..., Any],
    app: Any,
    timeline: Any,
    camera_path: str,
    output_path: str | os.PathLike[str],
    width: int,
    height: int,
    settle_updates: int = 2,
    max_capture_updates: int = 120,
) -> dict[str, Any]:
    from PIL import Image
    import numpy as np

    if type(width) is not int or width <= 0 or type(height) is not int or height <= 0:
        raise ValueError("static_viewport_resolution_must_be_positive_ints")
    if type(settle_updates) is not int or settle_updates < 0:
        raise ValueError("static_viewport_settle_updates_must_be_nonnegative_int")
    if type(max_capture_updates) is not int or max_capture_updates <= 0:
        raise ValueError("static_viewport_max_capture_updates_must_be_positive_int")
    require_stopped_timeline(timeline)
    time_before = float(timeline.get_current_time())
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    viewport.camera_path = camera_path
    viewport.resolution = (width, height)
    viewport.resolution_scale = 1
    for _ in range(settle_updates):
        require_stopped_timeline(timeline)
        app.update()
    render_product_path = viewport.get_render_product_path()
    capture_to_file(
        viewport,
        file_path=str(path),
    )
    capture_updates = 0
    while capture_updates < max_capture_updates:
        require_stopped_timeline(timeline)
        app.update()
        capture_interface.wait_async_capture()
        capture_updates += 1
        if path.is_file():
            break
    if not path.is_file():
        raise RuntimeError(
            f"static_viewport_capture_timeout:{camera_path}:{max_capture_updates}"
        )
    app.update()
    require_stopped_timeline(timeline)
    time_after = float(timeline.get_current_time())
    if not math.isclose(time_after, time_before, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError("static_viewport_capture_advanced_timeline")
    if not path.is_file():
        raise RuntimeError(f"static_viewport_capture_missing_file:{path}")
    with _open_image_file_snapshot(
        path,
        label="static_viewport_capture",
    ) as image:
        rgb = np.asarray(image.convert("RGB"))
    if rgb.shape != (height, width, 3):
        raise RuntimeError(
            f"static_viewport_capture_shape_mismatch:{list(rgb.shape)}"
        )
    mean = float(rgb.mean())
    std = float(rgb.std())
    if mean < 5.0 or std < 2.0:
        raise RuntimeError(
            f"static_viewport_capture_near_black_or_flat:mean={mean}:std={std}"
        )
    return {
        "status": "saved_static_viewport_rgb",
        "camera_path": camera_path,
        "path": str(path),
        "shape": list(rgb.shape),
        "dtype": str(rgb.dtype),
        "mean": mean,
        "std": std,
        "sha256": _sha256_file(path),
        "settle_updates": settle_updates,
        "capture_updates": capture_updates,
        "render_product_path": str(render_product_path),
        "timeline_time_before": time_before,
        "timeline_time_after": time_after,
        "timeline_advanced": False,
        "physics_step_count_instrumented": False,
        "physics_steps_executed": None,
    }


def author_static_candidate_state(
    stage: Any,
    *,
    accepted: AcceptedReplayInput,
    candidate_contract: Mapping[str, Any],
    material_path: str | None,
) -> dict[str, Any]:
    """Author hidden initial physical evidence and the final presentation default."""
    from pxr import Sdf, UsdGeom

    from tools.labutopia_fluid.omniglass_reference import (
        author_presentation_points,
        author_presentation_surface,
    )

    candidate_id = str(candidate_contract["candidate_id"])
    visibility = hide_physical_and_debug_points(stage)
    physics_width = float(
        accepted.summary["physics_particle_offsets"]["particle_width"]
    )
    hidden_prim = author_presentation_points(
        stage,
        path=HIDDEN_PHYSICAL_INITIAL_STATE_PATH,
        positions=accepted.records[0]["positions"],
        display_width=physics_width,
        material_path=None,
    )
    UsdGeom.Imageable(hidden_prim).MakeInvisible()
    hidden_prim.CreateAttribute(
        "labutopia:physicalTraceFrameIndex", Sdf.ValueTypeNames.Int, custom=True
    ).Set(int(candidate_contract["hidden_physical_initial_state_frame_index"]))
    hidden_prim.CreateAttribute(
        "labutopia:traceRole", Sdf.ValueTypeNames.Token, custom=True
    ).Set("accepted_physical_initial_state")

    final_proxy = accepted.proxy_frame(candidate_id, frame_offset=-1)
    if final_proxy["presentation_kind"] == "surface_mesh":
        presentation_prim = author_presentation_surface(
            stage,
            path=PRESENTATION_SURFACE_PATH,
            surface_frame=final_proxy,
            material_path=material_path,
        )
    else:
        presentation_prim = author_presentation_points(
            stage,
            path=PRESENTATION_POINTS_PATH,
            positions=final_proxy["positions_world"],
            display_width=float(candidate_contract["display_width"]),
            material_path=material_path,
        )
    UsdGeom.Imageable(presentation_prim).MakeVisible()
    presentation_prim.CreateAttribute(
        "labutopia:physicalTraceFrameIndex", Sdf.ValueTypeNames.Int, custom=True
    ).Set(int(candidate_contract["static_presentation_frame_index"]))
    presentation_prim.CreateAttribute(
        "labutopia:proxyGeometrySha256", Sdf.ValueTypeNames.String, custom=True
    ).Set(proxy_geometry_sha256(final_proxy))
    presentation_prim.CreateAttribute(
        "labutopia:candidateId", Sdf.ValueTypeNames.Token, custom=True
    ).Set(candidate_id)
    presentation_has_physx = any(
        "physx" in token.lower() for token in presentation_prim.GetAppliedSchemas()
    ) or any(
        relationship.GetName().lower().startswith("physx")
        for relationship in presentation_prim.GetRelationships()
    )
    if presentation_has_physx:
        raise RuntimeError("presentation_points_unexpectedly_have_physx_api")
    result = {
        **visibility,
        "presentation_primitive_path": str(presentation_prim.GetPath()),
        "presentation_points_path": (
            PRESENTATION_POINTS_PATH
            if final_proxy["presentation_kind"] == "points"
            else None
        ),
        "presentation_surface_path": (
            PRESENTATION_SURFACE_PATH
            if final_proxy["presentation_kind"] == "surface_mesh"
            else None
        ),
        "presentation_kind": final_proxy["presentation_kind"],
        "hidden_physical_initial_state_path": HIDDEN_PHYSICAL_INITIAL_STATE_PATH,
        "static_presentation_frame_index": int(
            candidate_contract["static_presentation_frame_index"]
        ),
        "hidden_physical_initial_state_frame_index": int(
            candidate_contract["hidden_physical_initial_state_frame_index"]
        ),
        "static_proxy_count": final_proxy["proxy_count"],
        "hidden_physical_initial_state_point_count": len(
            accepted.records[0]["positions"]
        ),
        "physics_schema_applied_to_presentation": False,
        "physical_volume_parity_claim_allowed": final_proxy.get(
            "physical_volume_parity_claim_allowed"
        ),
        "static_proxy_geometry_sha256": proxy_geometry_sha256(final_proxy),
    }
    if final_proxy.get("surface_model_version") is not None:
        result.update(
            {
                "surface_model_version": final_proxy[
                    "surface_model_version"
                ],
                "surface_model_contract_sha256": final_proxy[
                    "surface_model_contract_sha256"
                ],
            }
        )
    return result


def proxy_geometry_sha256(proxy: Mapping[str, Any]) -> str:
    """Hash exactly the presentation geometry consumed by the USD authoring path."""
    presentation_kind = str(proxy.get("presentation_kind", ""))
    positions_world = [
        [
            struct.unpack("<f", struct.pack("<f", float(component)))[0]
            for component in point
        ]
        for point in proxy.get("positions_world") or []
    ]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "candidate_id": str(proxy.get("candidate_id", "")),
        "presentation_kind": presentation_kind,
        "positions_world": positions_world,
    }
    if presentation_kind == "surface_mesh":
        payload.update(
            {
                "normals_world": [
                    [
                        struct.unpack("<f", struct.pack("<f", float(component)))[
                            0
                        ]
                        for component in normal
                    ]
                    for normal in proxy.get("normals_world") or []
                ],
                "face_vertex_counts": deepcopy(proxy.get("face_vertex_counts")),
                "face_vertex_indices": deepcopy(proxy.get("face_vertex_indices")),
                "canonical_mesh_sha256": proxy.get("canonical_mesh_sha256"),
            }
        )
        if proxy.get("surface_model_version") is not None:
            payload.update(
                {
                    "surface_model_version": proxy.get(
                        "surface_model_version"
                    ),
                    "surface_model_contract_sha256": proxy.get(
                        "surface_model_contract_sha256"
                    ),
                }
            )
    elif presentation_kind == "points":
        payload["display_width"] = struct.unpack(
            "<f", struct.pack("<f", float(proxy.get("display_width")))
        )[0]
    else:
        raise ValueError(f"presentation_kind_invalid:{presentation_kind}")
    return _json_sha256(payload)


def verify_presentation_frame_binding(
    stage: Any,
    proxy: Mapping[str, Any],
    *,
    frame_index: int,
) -> dict[str, Any]:
    """Read authored USD geometry back and verify its trace/hash attributes."""
    from pxr import UsdGeom

    expected_frame_index = _require_plain_int(
        "physical_trace_frame_index", frame_index, minimum=0
    )
    presentation_kind = str(proxy.get("presentation_kind", ""))
    candidate_id = str(proxy.get("candidate_id", ""))
    if presentation_kind == "surface_mesh":
        schema = UsdGeom.Mesh(stage.GetPrimAtPath(PRESENTATION_SURFACE_PATH))
        if not schema:
            raise RuntimeError("presentation_surface_missing_during_verification")
        prim = schema.GetPrim()
        actual_proxy = {
            "candidate_id": candidate_id,
            "presentation_kind": presentation_kind,
            "positions_world": [tuple(value) for value in schema.GetPointsAttr().Get()],
            "normals_world": [tuple(value) for value in schema.GetNormalsAttr().Get()],
            "face_vertex_counts": list(schema.GetFaceVertexCountsAttr().Get()),
            "face_vertex_indices": list(schema.GetFaceVertexIndicesAttr().Get()),
            "canonical_mesh_sha256": prim.GetAttribute(
                "labutopia:canonicalMeshSha256"
            ).Get(),
        }
        if proxy.get("surface_model_version") is not None:
            actual_proxy.update(
                {
                    "surface_model_version": prim.GetAttribute(
                        "labutopia:surfaceModelVersion"
                    ).Get(),
                    "surface_model_contract_sha256": prim.GetAttribute(
                        "labutopia:surfaceModelContractSha256"
                    ).Get(),
                }
            )
    elif presentation_kind == "points":
        schema = UsdGeom.Points(stage.GetPrimAtPath(PRESENTATION_POINTS_PATH))
        if not schema:
            raise RuntimeError("presentation_points_missing_during_verification")
        prim = schema.GetPrim()
        widths = list(schema.GetWidthsAttr().Get() or [])
        if len(widths) != 1:
            raise RuntimeError("presentation_points_constant_width_missing")
        actual_proxy = {
            "candidate_id": candidate_id,
            "presentation_kind": presentation_kind,
            "positions_world": [tuple(value) for value in schema.GetPointsAttr().Get()],
            "display_width": float(widths[0]),
        }
    else:
        raise ValueError(f"presentation_kind_invalid:{presentation_kind}")
    expected_geometry_sha256 = proxy_geometry_sha256(proxy)
    actual_geometry_sha256 = proxy_geometry_sha256(actual_proxy)
    authored_geometry_sha256 = prim.GetAttribute(
        "labutopia:proxyGeometrySha256"
    ).Get()
    authored_frame_index = prim.GetAttribute(
        "labutopia:physicalTraceFrameIndex"
    ).Get()
    if actual_geometry_sha256 != expected_geometry_sha256:
        raise RuntimeError(
            "presentation_actual_usd_geometry_hash_mismatch:"
            f"{actual_geometry_sha256}!={expected_geometry_sha256}"
        )
    if authored_geometry_sha256 != expected_geometry_sha256:
        raise RuntimeError("presentation_authored_geometry_hash_mismatch")
    if authored_frame_index != expected_frame_index:
        raise RuntimeError("presentation_authored_trace_frame_index_mismatch")
    result = {
        "physical_trace_frame_index": expected_frame_index,
        "presentation_primitive_path": str(prim.GetPath()),
        "presentation_kind": presentation_kind,
        "candidate_id": candidate_id,
        "expected_proxy_geometry_sha256": expected_geometry_sha256,
        "actual_usd_geometry_sha256": actual_geometry_sha256,
        "authored_proxy_geometry_sha256": authored_geometry_sha256,
        "verified": True,
    }
    if proxy.get("surface_model_version") is not None:
        result.update(
            {
                "surface_model_version": proxy["surface_model_version"],
                "surface_model_contract_sha256": proxy[
                    "surface_model_contract_sha256"
                ],
            }
        )
    return result


def _set_presentation_frame(
    stage: Any,
    proxy: Mapping[str, Any],
    *,
    frame_index: int,
) -> dict[str, Any]:
    from pxr import Gf, Sdf, UsdGeom

    trace_frame_index = _require_plain_int(
        "physical_trace_frame_index", frame_index, minimum=0
    )
    geometry_sha256 = proxy_geometry_sha256(proxy)

    if proxy.get("presentation_kind") == "surface_mesh":
        mesh = UsdGeom.Mesh(stage.GetPrimAtPath(PRESENTATION_SURFACE_PATH))
        if not mesh:
            raise RuntimeError("presentation_surface_missing_during_replay")
        counts = list(mesh.GetFaceVertexCountsAttr().Get() or [])
        indices = list(mesh.GetFaceVertexIndicesAttr().Get() or [])
        if counts != list(proxy["face_vertex_counts"]) or indices != list(
            proxy["face_vertex_indices"]
        ):
            raise RuntimeError("presentation_surface_topology_changed_during_replay")
        mesh.GetPointsAttr().Set(
            [Gf.Vec3f(*point) for point in proxy["positions_world"]]
        )
        mesh.GetNormalsAttr().Set(
            [Gf.Vec3f(*normal) for normal in proxy["normals_world"]]
        )
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
        prim = mesh.GetPrim()
        prim.CreateAttribute(
            "labutopia:canonicalMeshSha256",
            Sdf.ValueTypeNames.String,
            custom=True,
        ).Set(str(proxy["canonical_mesh_sha256"]))
        if proxy.get("surface_model_version") is not None:
            prim.CreateAttribute(
                "labutopia:surfaceModelVersion",
                Sdf.ValueTypeNames.String,
                custom=True,
            ).Set(str(proxy["surface_model_version"]))
            prim.CreateAttribute(
                "labutopia:surfaceModelContractSha256",
                Sdf.ValueTypeNames.String,
                custom=True,
            ).Set(str(proxy["surface_model_contract_sha256"]))
    else:
        points = UsdGeom.Points(stage.GetPrimAtPath(PRESENTATION_POINTS_PATH))
        if not points:
            raise RuntimeError("presentation_points_missing_during_replay")
        points.GetPointsAttr().Set(
            [Gf.Vec3f(*point) for point in proxy["positions_world"]]
        )
        points.GetWidthsAttr().Set([float(proxy["display_width"])])
        points.SetWidthsInterpolation(UsdGeom.Tokens.constant)
        prim = points.GetPrim()
    prim.CreateAttribute(
        "labutopia:physicalTraceFrameIndex",
        Sdf.ValueTypeNames.Int,
        custom=True,
    ).Set(trace_frame_index)
    prim.CreateAttribute(
        "labutopia:proxyGeometrySha256",
        Sdf.ValueTypeNames.String,
        custom=True,
    ).Set(geometry_sha256)
    if prim.GetAttribute("labutopia:physicalTraceFrameIndex").Get() != trace_frame_index:
        raise RuntimeError("presentation_trace_frame_index_binding_failed")
    if prim.GetAttribute("labutopia:proxyGeometrySha256").Get() != geometry_sha256:
        raise RuntimeError("presentation_geometry_hash_binding_failed")
    usd_geometry_binding = verify_presentation_frame_binding(
        stage,
        proxy,
        frame_index=trace_frame_index,
    )
    result = {
        "physical_trace_frame_index": trace_frame_index,
        "proxy_geometry_sha256": geometry_sha256,
        "presentation_primitive_path": str(prim.GetPath()),
        "presentation_kind": str(proxy["presentation_kind"]),
        "canonical_mesh_sha256": proxy.get("canonical_mesh_sha256"),
        "usd_geometry_binding": usd_geometry_binding,
    }
    if proxy.get("surface_model_version") is not None:
        result.update(
            {
                "surface_model_version": proxy["surface_model_version"],
                "surface_model_contract_sha256": proxy[
                    "surface_model_contract_sha256"
                ],
            }
        )
    return result


def build_capture_frame_binding(
    *,
    candidate_id: str,
    frame_offset: int,
    record: Mapping[str, Any],
    physical_trace_sha256: str,
    proxy_update: Mapping[str, Any],
    image_paths: Mapping[str, str | os.PathLike[str]],
    effective_look_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind one accepted trace record to authored geometry and three RGB files."""
    effective_look = validate_effective_replay_look_contract(
        effective_look_contract
        if effective_look_contract is not None
        else build_effective_replay_look_contract()
    )
    render_diagnostic_projection = (
        build_effective_replay_look_matrix_projection(effective_look)
        if effective_look["render_diagnostic_variant_id"] is not None
        else None
    )
    offset = _require_plain_int("capture_frame_offset", frame_offset, minimum=0)
    frame_index = _require_plain_int(
        "capture_trace_frame_index", record.get("step_index"), minimum=0
    )
    particle_count = _require_plain_int(
        "capture_trace_particle_count", record.get("particle_count"), minimum=1
    )
    positions = record.get("positions")
    if not isinstance(positions, list) or len(positions) != particle_count:
        raise ValueError("capture_trace_particle_count_mismatch")
    if proxy_update.get("physical_trace_frame_index") != frame_index:
        raise ValueError(
            "proxy_trace_frame_index_mismatch:"
            f"{proxy_update.get('physical_trace_frame_index')}!={frame_index}"
        )
    geometry_sha256 = _require_sha256(
        "proxy_geometry_sha256", proxy_update.get("proxy_geometry_sha256")
    )
    usd_geometry_binding = proxy_update.get("usd_geometry_binding")
    if not isinstance(usd_geometry_binding, Mapping) or usd_geometry_binding.get(
        "verified"
    ) is not True:
        raise ValueError("proxy_usd_geometry_binding_missing")
    actual_usd_geometry_sha256 = _require_sha256(
        "actual_usd_geometry_sha256",
        usd_geometry_binding.get("actual_usd_geometry_sha256"),
    )
    if actual_usd_geometry_sha256 != geometry_sha256:
        raise ValueError("proxy_usd_geometry_sha256_mismatch")
    usd_geometry_binding_after_capture = proxy_update.get(
        "usd_geometry_binding_after_capture"
    )
    if not isinstance(
        usd_geometry_binding_after_capture, Mapping
    ) or usd_geometry_binding_after_capture.get("verified") is not True:
        raise ValueError("proxy_usd_geometry_binding_after_capture_missing")
    actual_usd_geometry_sha256_after_capture = _require_sha256(
        "actual_usd_geometry_sha256_after_capture",
        usd_geometry_binding_after_capture.get("actual_usd_geometry_sha256"),
    )
    if actual_usd_geometry_sha256_after_capture != geometry_sha256:
        raise ValueError("proxy_usd_geometry_sha256_after_capture_mismatch")
    surface_model_version = proxy_update.get("surface_model_version")
    surface_model_contract_sha256 = proxy_update.get(
        "surface_model_contract_sha256"
    )
    if surface_model_version is not None:
        if not isinstance(surface_model_version, str) or not surface_model_version:
            raise ValueError("capture_surface_model_version_invalid")
        surface_model_contract_sha256 = _require_sha256(
            "capture_surface_model_contract_sha256",
            surface_model_contract_sha256,
        )
        for label, binding in (
            ("before_capture", usd_geometry_binding),
            ("after_capture", usd_geometry_binding_after_capture),
        ):
            if (
                binding.get("surface_model_version") != surface_model_version
                or binding.get("surface_model_contract_sha256")
                != surface_model_contract_sha256
            ):
                raise ValueError(
                    f"capture_surface_model_binding_mismatch:{label}"
                )
    elif surface_model_contract_sha256 is not None:
        raise ValueError("capture_surface_model_hash_without_version")
    trace_sha256 = _require_sha256(
        "physical_trace_sha256", physical_trace_sha256
    )
    if set(image_paths) != set(CAPTURE_CAMERA_ROLES):
        raise ValueError(
            "capture_frame_image_roles_invalid:"
            f"actual={sorted(image_paths)}:expected={sorted(CAPTURE_CAMERA_ROLES)}"
        )
    resolved_images: dict[str, str] = {}
    image_sha256: dict[str, str] = {}
    expected_name = f"frame_{frame_index:04d}.png"
    for role in CAPTURE_CAMERA_ROLES:
        path = Path(image_paths[role]).expanduser().resolve()
        if path.name != expected_name:
            raise ValueError(
                f"capture_frame_image_name_mismatch:{role}:{path.name}!={expected_name}"
            )
        _validate_nonempty_artifact(path, label=f"capture_frame_image:{role}")
        resolved_images[role] = str(path)
        image_sha256[role] = _sha256_file(path)
    payload = {
        "schema_version": 1,
        "candidate_id": str(candidate_id),
        "frame_offset": offset,
        "physical_trace_frame_index": frame_index,
        "physical_trace_sha256": trace_sha256,
        "trace_record_sha256": _json_sha256(record),
        "source_positions_sha256": _json_sha256(positions),
        "source_physical_point_count": particle_count,
        "presentation_kind": str(proxy_update.get("presentation_kind", "")),
        "presentation_primitive_path": str(
            proxy_update.get("presentation_primitive_path", "")
        ),
        "proxy_geometry_sha256": geometry_sha256,
        "actual_usd_geometry_sha256": actual_usd_geometry_sha256,
        "usd_geometry_binding_verified": True,
        "actual_usd_geometry_sha256_after_capture": (
            actual_usd_geometry_sha256_after_capture
        ),
        "usd_geometry_binding_after_capture_verified": True,
        "canonical_mesh_sha256": proxy_update.get("canonical_mesh_sha256"),
        "lighting_variant_id": effective_look["lighting_variant_id"],
        "render_diagnostic_variant_id": effective_look[
            "render_diagnostic_variant_id"
        ],
        "effective_replay_look_matrix_projection_sha256": (
            render_diagnostic_projection["canonical_json_utf8_sha256"]
            if render_diagnostic_projection is not None
            else None
        ),
        "effective_replay_look_contract": deepcopy(effective_look),
        "effective_replay_look_contract_sha256": effective_look[
            "effective_replay_look_contract_sha256"
        ],
        "image_paths": resolved_images,
        "image_sha256": image_sha256,
    }
    if surface_model_version is not None:
        payload.update(
            {
                "surface_model_version": surface_model_version,
                "surface_model_contract_sha256": (
                    surface_model_contract_sha256
                ),
            }
        )
    return {**payload, "frame_binding_sha256": _json_sha256(payload)}


def validate_capture_frame_bindings_artifact(
    path: str | os.PathLike[str],
    *,
    candidate_id: str,
    physical_trace_sha256: str,
    frame_indices: Sequence[int],
    image_paths_by_role: Mapping[str, Sequence[str | os.PathLike[str]]],
    expected_frame_contracts: Sequence[Mapping[str, Any]],
    expected_effective_look_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Recompute every frame/image binding from the persisted evidence file."""
    target = Path(path).expanduser().resolve()
    artifact = _load_json_object(target, label="capture_frame_bindings")
    expected_look = validate_effective_replay_look_contract(
        expected_effective_look_contract
        if expected_effective_look_contract is not None
        else build_effective_replay_look_contract()
    )
    for field, expected_value in (
        ("lighting_variant_id", expected_look["lighting_variant_id"]),
        ("effective_replay_look_contract", expected_look),
        (
            "effective_replay_look_contract_sha256",
            expected_look["effective_replay_look_contract_sha256"],
        ),
    ):
        if artifact.get(field) != expected_value:
            raise ValueError(f"capture_binding_effective_look_mismatch:{field}")
    expected_trace_sha256 = _require_sha256(
        "capture_binding_physical_trace_sha256", physical_trace_sha256
    )
    expected_indices = [
        _require_plain_int(
            f"capture_binding_expected_frame_{offset}", value, minimum=0
        )
        for offset, value in enumerate(frame_indices)
    ]
    if artifact.get("candidate_id") != candidate_id:
        raise ValueError("capture_binding_candidate_id_mismatch")
    if artifact.get("physical_trace_sha256") != expected_trace_sha256:
        raise ValueError("capture_binding_physical_trace_sha256_mismatch")
    if artifact.get("frame_indices") != expected_indices:
        raise ValueError("capture_binding_frame_indices_mismatch")
    bindings = artifact.get("bindings")
    if not isinstance(bindings, list) or len(bindings) != len(expected_indices):
        raise ValueError("capture_binding_count_mismatch")
    if len(expected_frame_contracts) != len(expected_indices):
        raise ValueError("capture_binding_expected_frame_contract_count_mismatch")
    if artifact.get("bindings_sha256") != _json_sha256(bindings):
        raise ValueError("capture_bindings_sha256_mismatch")
    if set(image_paths_by_role) != set(CAPTURE_CAMERA_ROLES):
        raise ValueError("capture_binding_image_role_set_mismatch")
    expected_paths = {
        role: [Path(value).expanduser().resolve() for value in image_paths_by_role[role]]
        for role in CAPTURE_CAMERA_ROLES
    }
    if any(len(paths) != len(expected_indices) for paths in expected_paths.values()):
        raise ValueError("capture_binding_image_count_mismatch")

    for offset, (frame_index, binding) in enumerate(zip(expected_indices, bindings)):
        if not isinstance(binding, Mapping):
            raise ValueError(f"capture_binding_not_object:{offset}")
        binding_payload = {
            key: deepcopy(value)
            for key, value in binding.items()
            if key != "frame_binding_sha256"
        }
        if binding.get("frame_binding_sha256") != _json_sha256(binding_payload):
            raise ValueError(f"capture_frame_binding_sha256_mismatch:{offset}")
        if binding.get("candidate_id") != candidate_id:
            raise ValueError(f"capture_binding_candidate_id_mismatch:{offset}")
        if binding.get("frame_offset") != offset:
            raise ValueError(f"capture_binding_frame_offset_mismatch:{offset}")
        if binding.get("physical_trace_frame_index") != frame_index:
            raise ValueError(f"capture_binding_frame_index_mismatch:{offset}")
        if binding.get("physical_trace_sha256") != expected_trace_sha256:
            raise ValueError(f"capture_binding_trace_sha256_mismatch:{offset}")
        for field, expected_value in (
            ("lighting_variant_id", expected_look["lighting_variant_id"]),
            ("effective_replay_look_contract", expected_look),
            (
                "effective_replay_look_contract_sha256",
                expected_look["effective_replay_look_contract_sha256"],
            ),
        ):
            if binding.get(field) != expected_value:
                raise ValueError(
                    f"capture_binding_effective_look_mismatch:{offset}:{field}"
                )
        expected_frame = expected_frame_contracts[offset]
        expected_fields = {
            "physical_trace_frame_index": expected_frame.get("frame_index"),
            "trace_record_sha256": expected_frame.get("trace_record_sha256"),
            "source_positions_sha256": expected_frame.get(
                "source_positions_sha256"
            ),
            "source_physical_point_count": expected_frame.get(
                "source_physical_point_count"
            ),
            "presentation_kind": expected_frame.get("presentation_kind"),
            "proxy_geometry_sha256": expected_frame.get(
                "proxy_geometry_sha256"
            ),
            "actual_usd_geometry_sha256": expected_frame.get(
                "proxy_geometry_sha256"
            ),
            "usd_geometry_binding_verified": True,
            "actual_usd_geometry_sha256_after_capture": expected_frame.get(
                "proxy_geometry_sha256"
            ),
            "usd_geometry_binding_after_capture_verified": True,
            "canonical_mesh_sha256": expected_frame.get(
                "canonical_mesh_sha256"
            ),
        }
        if expected_frame.get("surface_model_version") is not None:
            expected_fields.update(
                {
                    "surface_model_version": expected_frame.get(
                        "surface_model_version"
                    ),
                    "surface_model_contract_sha256": expected_frame.get(
                        "surface_model_contract_sha256"
                    ),
                }
            )
        for field, expected_value in expected_fields.items():
            if binding.get(field) != expected_value:
                raise ValueError(
                    f"capture_binding_authoritative_frame_mismatch:{offset}:{field}"
                )
        for field in (
            "trace_record_sha256",
            "source_positions_sha256",
            "proxy_geometry_sha256",
        ):
            _require_sha256(f"capture_binding_{field}_{offset}", binding.get(field))
        canonical_mesh_sha256 = binding.get("canonical_mesh_sha256")
        if canonical_mesh_sha256 is not None:
            _require_sha256(
                f"capture_binding_canonical_mesh_sha256_{offset}",
                canonical_mesh_sha256,
            )
        surface_model_contract_sha256 = binding.get(
            "surface_model_contract_sha256"
        )
        if surface_model_contract_sha256 is not None:
            _require_sha256(
                f"capture_binding_surface_model_contract_sha256_{offset}",
                surface_model_contract_sha256,
            )
        binding_paths = binding.get("image_paths")
        binding_hashes = binding.get("image_sha256")
        if not isinstance(binding_paths, Mapping) or not isinstance(
            binding_hashes, Mapping
        ):
            raise ValueError(f"capture_binding_images_missing:{offset}")
        if set(binding_paths) != set(CAPTURE_CAMERA_ROLES) or set(
            binding_hashes
        ) != set(CAPTURE_CAMERA_ROLES):
            raise ValueError(f"capture_binding_image_roles_mismatch:{offset}")
        for role in CAPTURE_CAMERA_ROLES:
            expected_path = expected_paths[role][offset]
            bound_path = Path(str(binding_paths[role])).expanduser().resolve()
            if bound_path != expected_path:
                raise ValueError(
                    f"capture_binding_image_path_mismatch:{role}:{offset}"
                )
            actual_sha256 = _sha256_file(expected_path)
            if binding_hashes[role] != actual_sha256:
                raise ValueError(
                    f"capture_binding_image_sha256_mismatch:{role}:{offset}"
                )
    return {
        "validated": True,
        "artifact_path": str(target),
        "artifact_sha256": _sha256_file(target),
        "candidate_id": candidate_id,
        "physical_trace_sha256": expected_trace_sha256,
        "frame_indices": expected_indices,
        "binding_count": len(bindings),
        "bindings_sha256": artifact["bindings_sha256"],
        "lighting_variant_id": expected_look["lighting_variant_id"],
        "effective_replay_look_contract_sha256": expected_look[
            "effective_replay_look_contract_sha256"
        ],
    }


def _same_frame_core(left: CupInteriorFrame, right: CupInteriorFrame) -> bool:
    if left.parent_local_axis != right.parent_local_axis:
        return False
    for name in (
        "origin_world",
        "x_axis_world",
        "y_axis_world",
        "z_axis_world",
    ):
        if any(
            not math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1e-9)
            for a, b in zip(getattr(left, name), getattr(right, name))
        ):
            return False
    return all(
        math.isclose(
            float(getattr(left, name)),
            float(getattr(right, name)),
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        for name in (
            "outer_radius",
            "interior_radius",
            "outer_floor",
            "interior_floor",
            "rim_height",
            "axis_alignment_dot",
        )
    )


def _author_version_matched_beaker_override(
    stage: Any,
    *,
    profile: Mapping[str, Any],
    mdl_source_asset: Path,
) -> dict[str, Any]:
    from pxr import Gf, Sdf, UsdGeom, UsdShade

    override = dict(profile.get("beaker_override") or {})
    if override.get("enabled") is not True:
        raise ValueError("beaker_override_required_for_omniglass_replay")
    source_asset = mdl_source_asset.resolve()
    if not source_asset.is_file() or source_asset.name != "OmniGlass.mdl":
        raise FileNotFoundError(f"version_matched_omniglass_mdl_missing:{source_asset}")
    looks_path = Sdf.Path("/World/Looks")
    if not stage.GetPrimAtPath(looks_path):
        UsdGeom.Scope.Define(stage, looks_path)

    target_mesh = str(override.get("target_mesh") or "/World/beaker2/mesh")
    material_path = str(
        override.get("material_path") or "/World/Looks/LiquidPresentationBeakerGlass"
    )
    glass_color = override.get("glass_color") or (0.85, 0.92, 0.95)
    reflection_color = override.get("reflection_color") or (0.90, 0.95, 0.98)
    cutout_opacity = float(override.get("cutout_opacity", 0.72))
    enable_opacity = bool(override.get("enable_opacity", True))

    material_sdf_path = Sdf.Path(material_path)
    material = UsdShade.Material.Define(stage, material_sdf_path)
    shader_path = material_sdf_path.AppendChild("Shader")
    shader = UsdShade.Shader.Define(stage, shader_path)
    shader.GetImplementationSourceAttr().Set(UsdShade.Tokens.sourceAsset)
    shader.SetSourceAsset(Sdf.AssetPath(str(source_asset)), "mdl")
    shader.SetSourceAssetSubIdentifier("OmniGlass", "mdl")
    shader.CreateInput("glass_color", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*(float(value) for value in glass_color))
    )
    shader.CreateInput("reflection_color", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*(float(value) for value in reflection_color))
    )
    if enable_opacity:
        shader.CreateInput("enable_opacity", Sdf.ValueTypeNames.Bool).Set(True)
        shader.CreateInput("cutout_opacity", Sdf.ValueTypeNames.Float).Set(
            cutout_opacity
        )
    shader.CreateOutput("out", Sdf.ValueTypeNames.Token)
    material.CreateSurfaceOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")

    mesh_prim = stage.GetPrimAtPath(target_mesh)
    if not mesh_prim:
        raise RuntimeError(f"beaker_override_target_missing:{target_mesh}")
    UsdShade.MaterialBindingAPI.Apply(mesh_prim).Bind(material)
    return {
        "enabled": True,
        "beaker_override_used": True,
        "target_mesh": target_mesh,
        "material_path": material_path,
        "shader_path": str(shader_path),
        "mdl_source_asset": str(source_asset),
        "mdl_source_sha256": _sha256_file(source_asset),
        "glass_color": [float(value) for value in glass_color],
        "reflection_color": [float(value) for value in reflection_color],
        "cutout_opacity": cutout_opacity,
        "enable_opacity": enable_opacity,
        "official_visual_a_compatible": False,
    }


def verify_version_matched_native_beaker_material(
    stage: Any,
    *,
    material_retarget: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep the authored cup binding and verify its Isaac 4.1 MDL retarget."""
    from pxr import UsdShade

    target_mesh = "/World/beaker2/mesh"
    mesh_prim = stage.GetPrimAtPath(target_mesh)
    if not mesh_prim.IsValid():
        raise RuntimeError(f"native_beaker_mesh_missing:{target_mesh}")
    material, _relationship = UsdShade.MaterialBindingAPI(
        mesh_prim
    ).ComputeBoundMaterial()
    if not material or str(material.GetPath()) != "/World/Looks/OmniSurface_Glass":
        raise RuntimeError("native_beaker_material_binding_not_preserved")
    shader_path = "/World/Looks/OmniSurface_Glass/Shader"
    shader_prim = stage.GetPrimAtPath(shader_path)
    if not shader_prim.IsValid():
        raise RuntimeError(f"native_beaker_shader_missing:{shader_path}")
    source_asset_attr = shader_prim.GetAttribute("info:mdl:sourceAsset")
    source_asset = source_asset_attr.Get() if source_asset_attr else None
    source_asset_path = getattr(source_asset, "path", str(source_asset or ""))
    sub_identifier_attr = shader_prim.GetAttribute(
        "info:mdl:sourceAsset:subIdentifier"
    )
    sub_identifier = sub_identifier_attr.Get() if sub_identifier_attr else None
    matching_records = [
        record
        for record in material_retarget.get("retargeted_shaders", [])
        if record.get("shader_path") == shader_path
        and record.get("retargeted_source_asset_basename") == "OmniGlass.mdl"
        and record.get("retargeted_sub_identifier") == "OmniGlass"
    ]
    if (
        not source_asset_path.endswith("/OmniGlass.mdl")
        or sub_identifier != "OmniGlass"
        or len(matching_records) != 1
    ):
        raise RuntimeError("native_beaker_version_matched_mdl_retarget_not_verified")
    return {
        "enabled": True,
        "target_mesh": target_mesh,
        "material_path": str(material.GetPath()),
        "shader_path": shader_path,
        "mdl_source_asset": source_asset_path,
        "mdl_source_asset_basename": "OmniGlass.mdl",
        "mdl_sub_identifier": "OmniGlass",
        "compatibility_fallback": matching_records[0].get(
            "compatibility_fallback"
        ),
        "native_material_binding_preserved": True,
        "version_matched_mdl_retarget_verified": True,
        "beaker_override_used": False,
    }


def _validate_output_scope(args: argparse.Namespace) -> tuple[Path, Path]:
    render_diagnostic_identity = validate_render_diagnostic_cell_scope(args)
    out_root = (
        _reject_symlink_path_components(
            args.out_root,
            label="render_diagnostic_output",
        )
        if render_diagnostic_identity is not None
        else Path(args.out_root).expanduser().resolve()
    )
    manifest_path = (
        (
            _reject_symlink_path_components(
                args.manifest,
                label="render_diagnostic_manifest",
            )
            if render_diagnostic_identity is not None
            else Path(args.manifest).expanduser().resolve()
        )
        if args.manifest
        else out_root / "replay_manifest.json"
    )
    if out_root == Path(out_root.anchor) or out_root == Path.cwd().resolve():
        raise ValueError(f"out_root_not_run_scoped:{out_root}")
    protected = {
        Path(raw_path).expanduser().resolve()
        for raw_path in (
            getattr(args, "accepted_summary", None),
            getattr(args, "accepted_matrix_manifest", None),
            getattr(args, "accepted_diagnostic_segment_archive", None),
        )
        if raw_path
    }
    if out_root in protected or manifest_path in protected:
        raise ValueError("output_path_overlaps_accepted_input")
    authority_arg = getattr(args, "accepted_authority_bundle", None)
    if authority_arg:
        authority_input = Path(authority_arg).expanduser().resolve()
        authority_root = (
            authority_input.parent
            if authority_input.name == AUTHORITY_BUNDLE_BASENAME
            else authority_input
        )
        if (
            out_root == authority_root
            or authority_root in out_root.parents
            or manifest_path == authority_root
            or authority_root in manifest_path.parents
        ):
            raise ValueError("output_path_overlaps_accepted_authority")
    if render_diagnostic_identity is not None and out_root.exists():
        if not bool(getattr(args, "runtime_child", False)):
            raise ValueError(f"diagnostic_out_root_must_be_absent:{out_root}")
        allowed_runtime_child_members = {
            "runtime_implementation_archive.zip",
            "runtime_bootstrap.py",
            RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_DIRNAME,
            RENDER_DIAGNOSTIC_SOURCE_CLOSURE_BASENAME,
        }
        actual_runtime_child_members = {path.name for path in out_root.iterdir()}
        if actual_runtime_child_members != allowed_runtime_child_members:
            raise ValueError(
                "diagnostic_runtime_child_initial_membership_invalid:"
                f"{sorted(actual_runtime_child_members)}"
            )
    if out_root.exists() and any(out_root.iterdir()):
        if render_diagnostic_identity is None or not bool(
            getattr(args, "runtime_child", False)
        ):
            raise ValueError(f"out_root_must_be_empty_or_absent:{out_root}")
    if manifest_path.exists():
        raise ValueError(f"manifest_already_exists:{manifest_path}")
    return out_root, manifest_path


def build_dry_plan(args: argparse.Namespace) -> dict[str, Any]:
    candidate_ids = _candidate_ids_from_args(args)
    effective_look = _validated_effective_look_contract_for_args(args)
    render_diagnostic_identity = validate_render_diagnostic_cell_scope(args)
    render_diagnostic_projection = (
        build_effective_replay_look_matrix_projection(effective_look)
        if render_diagnostic_identity is not None
        else None
    )
    visual_prototype_only = bool(
        getattr(args, "visual_prototype_display_fill_only", False)
    )
    run_scope = build_replay_scope_contract(
        candidate_ids,
        visual_prototype_only=visual_prototype_only,
    )
    formulas = {
        "OMNI_REF_FINE": "clamp(interior_diameter/32,0.0015,0.0020)",
        "OMNI_REF_RATIO_15": "interior_diameter/15",
        "OMNI_REF_RATIO_12": "interior_diameter/12",
        "OMNI_REF_SURFACE": "clamp(interior_diameter/32,0.0015,0.0020)",
        "OMNI_REF_DISPLAY_FILL": "interior_diameter/15",
    }

    def candidate_contract(candidate_id: str) -> dict[str, Any]:
        look_binding = {
            "lighting_variant_id": effective_look["lighting_variant_id"],
            "effective_replay_look_contract_sha256": effective_look[
                "effective_replay_look_contract_sha256"
            ],
        }
        if render_diagnostic_projection is not None:
            look_binding.update(
                {
                    "render_diagnostic_variant_id": effective_look[
                        "render_diagnostic_variant_id"
                    ],
                    "effective_replay_look_matrix_projection_sha256": (
                        render_diagnostic_projection[
                            "canonical_json_utf8_sha256"
                        ]
                    ),
                }
            )
        if candidate_id == "OMNI_REF_DISPLAY_FILL":
            return {
                "candidate_id": candidate_id,
                **look_binding,
                "width_formula": formulas[candidate_id],
                "voxel_size_formula": None,
                "proxy_mode": (
                    "deterministic_a18_display_proxy_rounded_cylinder"
                ),
                "surface_model_version": (
                    "a18_display_proxy_rounded_cylinder_v1"
                ),
                "presentation_points_type": "UsdGeom.Mesh",
                "physx_api_applied": False,
                "cameras": [
                    "context",
                    "source_beaker_closeup",
                    "native_table_context",
                ],
            }
        if candidate_id == "OMNI_REF_SURFACE":
            return {
                "candidate_id": candidate_id,
                **look_binding,
                "width_formula": formulas[candidate_id],
                "voxel_size_formula": None,
                "proxy_mode": "deterministic_trace_bounds_uv_ellipsoid",
                "presentation_points_type": "UsdGeom.Mesh",
                "physx_api_applied": False,
                "cameras": [
                    "context",
                    "source_beaker_closeup",
                    "native_table_context",
                ],
            }
        return {
            "candidate_id": candidate_id,
            **look_binding,
            "width_formula": formulas[candidate_id],
            "voxel_size_formula": "display_width",
            "proxy_mode": "deterministic_canonical_voxel_centroid",
            "presentation_points_type": "UsdGeom.Points",
            "physx_api_applied": False,
            "cameras": [
                "context",
                "source_beaker_closeup",
                "native_table_context",
            ],
        }

    return {
        "mode": "real_beaker_omniglass_reference_dry_plan",
        **run_scope,
        "lighting_variant_id": effective_look["lighting_variant_id"],
        "render_diagnostic_variant_id": effective_look[
            "render_diagnostic_variant_id"
        ],
        "render_diagnostic_identity": deepcopy(render_diagnostic_identity),
        "effective_replay_look_matrix_projection": deepcopy(
            render_diagnostic_projection
        ),
        "kit_startup_arguments": (
            build_effective_replay_kit_startup_arguments(effective_look)
            if render_diagnostic_identity is not None
            else []
        ),
        "diagnostic_lifecycle": (
            render_diagnostic_lifecycle_contract()
            if render_diagnostic_identity is not None
            else None
        ),
        "effective_replay_look_contract": deepcopy(effective_look),
        "effective_replay_look_contract_sha256": effective_look[
            "effective_replay_look_contract_sha256"
        ],
        "accepted_summary": args.accepted_summary,
        "accepted_authority_bundle": args.accepted_authority_bundle,
        "accepted_matrix_manifest": args.accepted_matrix_manifest,
        "accepted_diagnostic_segment_archive": (
            args.accepted_diagnostic_segment_archive
        ),
        "accepted_summary_read": False,
        "accepted_matrix_manifest_read": False,
        "accepted_diagnostic_segment_archive_read": False,
        "trace_read": False,
        "isaac_runtime_imported": False,
        "simulation_app_started": False,
        "physics_step_count_instrumented": False,
        "physics_steps_planned": None,
        "replicator_render_steps_planned": "one_per_trace_frame_per_candidate",
        "timeline_play_planned": False,
        "candidate_contracts": {
            candidate_id: candidate_contract(candidate_id)
            for candidate_id in candidate_ids
        },
        "out_root": str(Path(args.out_root).expanduser().resolve()),
        "manifest": str(
            Path(args.manifest).expanduser().resolve()
            if args.manifest
            else Path(args.out_root).expanduser().resolve() / "replay_manifest.json"
        ),
    }


def _open_exact_stage(
    *,
    context: Any,
    app: Any,
    timeline: Any,
    source_path: Path,
    warmup_updates: int,
) -> Any:
    opened = bool(context.open_stage(str(source_path)))
    stage = context.get_stage()
    updates = 0
    while stage is None and updates < max(1, warmup_updates):
        require_stopped_timeline(timeline)
        app.update()
        updates += 1
        stage = context.get_stage()
    if not opened or stage is None:
        raise RuntimeError(f"open_exact_accepted_source_failed:{source_path}")
    root_real_path = Path(stage.GetRootLayer().realPath).resolve()
    if root_real_path != source_path.resolve():
        raise RuntimeError(
            f"opened_source_path_mismatch:{root_real_path}!={source_path}"
        )
    stage.Reload()
    reloaded_root_path = Path(stage.GetRootLayer().realPath).resolve()
    if reloaded_root_path != source_path.resolve():
        raise RuntimeError(
            f"reloaded_source_path_mismatch:{reloaded_root_path}!={source_path}"
        )
    return stage


def _render_validated_replay(
    args: argparse.Namespace,
    accepted: AcceptedReplayInput,
    contracts: Mapping[str, Mapping[str, Any]],
    *,
    app: Any,
    out_root: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    import carb
    import omni.kit.app
    import omni.kit.commands
    import omni.physx.bindings._physx as pb
    import omni.replicator.core as rep
    import omni.timeline
    import omni.usd
    from pxr import Usd

    from tools.labutopia_fluid import (
        run_colleague_native_usd_completed_pbd_step_video as native,
    )
    from tools.labutopia_fluid.presentation_look_profiles import (
        REF_OMNIGLASS_GLASS_COLOR,
        REF_OMNIGLASS_REFLECTION_COLOR,
        resolve_presentation_look_profile,
    )
    from tools.labutopia_fluid.real_beaker import derive_cup_interior_frame

    out_root.mkdir(parents=True, exist_ok=True)
    settings = carb.settings.get_settings()
    effective_look = _validated_effective_look_contract_for_args(args)
    render_diagnostic_identity = validate_render_diagnostic_cell_scope(args)
    render_settings = apply_and_validate_effective_replay_render_settings(
        settings,
        native=native,
        effective_look_contract=effective_look,
        update_barrier=app.update,
    )
    mdl_search_path_contract = getattr(
        args,
        "_render_diagnostic_mdl_search_path_contract",
        None,
    )
    if render_diagnostic_identity is not None:
        if not isinstance(mdl_search_path_contract, Mapping):
            raise RuntimeError("render_diagnostic_mdl_search_path_contract_missing")
        mdl_search_path_contract = (
            validate_render_diagnostic_mdl_search_path_readback(
                settings,
                mdl_search_path_contract,
            )
        )
        args._render_diagnostic_mdl_search_path_contract = deepcopy(
            mdl_search_path_contract
        )
    settings.set(pb.SETTING_DISPLAY_PARTICLES, native._physx_visualizer_mode_none(pb))
    settings.set_bool("/app/player/playSimulations", False)
    settings.set_bool("/omni/replicator/captureOnPlay", False)
    rep.orchestrator.set_capture_on_play(False)
    if render_diagnostic_identity is not None:
        preboot_closure = getattr(args, "_preboot_material_closure", None)
        if not isinstance(preboot_closure, Mapping):
            raise RuntimeError("render_diagnostic_preboot_mdl_closure_missing")
        closure = deepcopy(dict(preboot_closure))
        expected_closure_root = out_root / VERSION_MATCHED_MDL_CLOSURE_DIRNAME
        if _absolute_path_without_symlink_resolution(
            str(closure.get("closure_root", ""))
        ) != expected_closure_root:
            raise RuntimeError("render_diagnostic_preboot_mdl_closure_root_mismatch")
    else:
        closure = _mirror_version_matched_mdl_closure(
            native,
            artifact_dir=out_root,
        )
    material_closure_snapshot_before = verify_material_closure_snapshot_unchanged(
        closure
    )
    omniglass_source = Path(closure["closure_base_dir"]) / "OmniGlass.mdl"
    context = omni.usd.get_context()
    timeline = omni.timeline.get_timeline_interface()
    require_stopped_timeline(timeline)
    args._timeline_checkpoint_observed = True
    if effective_look["base_profile_id"] != REPLAY_PRESENTATION_LOOK_ID:
        raise RuntimeError("replay_presentation_look_constant_mismatch")
    profile = resolve_presentation_look_profile(
        effective_look["base_profile_id"]
    )
    profile["lighting"] = deepcopy(effective_look["effective_lighting"])
    runtime_camera_contracts = build_replay_camera_contracts(
        frame=accepted.frame,
        region_config=accepted.summary["region_config"],
        width=int(args.width),
        height=int(args.height),
    )
    if runtime_camera_contracts != getattr(
        args, "_camera_contracts_preflight", None
    ):
        raise RuntimeError("camera_contracts_changed_after_simulation_app_boot")
    completed: dict[str, dict[str, Any]] = {}
    matrix_authority = deepcopy(dict(args._matrix_authority))
    input_snapshot_verification_before = verify_replay_input_snapshots_unchanged(
        accepted,
        matrix_authority,
    )
    expected_candidate_ids = _candidate_ids_from_args(args)
    if tuple(contracts) != expected_candidate_ids:
        raise RuntimeError(
            "runtime_candidate_set_does_not_match_declared_scope:"
            + ",".join(contracts)
        )

    for candidate_id in contracts:
        args._active_candidate_id = candidate_id
        args._completed_candidate_ids = list(completed)
        args._last_replicator_cleanup = None
        args._last_session_restore = None
        contract = deepcopy(dict(contracts[candidate_id]))
        candidate_dir = out_root / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=False)
        stage = Usd.Stage.Open(str(accepted.source_usd_path), Usd.Stage.LoadAll)
        if stage is None:
            raise RuntimeError(
                f"candidate_author_stage_open_failed:{accepted.source_usd_path}"
            )
        author_root_layer = stage.GetRootLayer()
        if Path(author_root_layer.realPath).resolve() != accepted.source_usd_path:
            raise RuntimeError("candidate_author_stage_source_root_mismatch")
        if author_root_layer.dirty:
            raise RuntimeError("candidate_author_source_root_dirty_at_open")
        if _sha256_file(accepted.source_usd_path) != accepted.source_usd_sha256:
            raise RuntimeError("candidate_author_source_file_hash_changed_at_open")
        author_root_layer.SetPermissionToEdit(False)
        author_root_layer.SetPermissionToSave(False)
        author_root_snapshot = snapshot_sdf_layer(author_root_layer)
        normal_remediation_contract = build_beaker_normals_block_contract(
            stage,
            source_usd_path=accepted.source_usd_path,
            source_usd_sha256=accepted.source_usd_sha256,
        )
        if completed:
            previous_normal_hashes = {
                item["beaker_normal_remediation_contract_sha256"]
                for item in completed.values()
            }
            if previous_normal_hashes != {
                normal_remediation_contract[
                    "beaker_normal_remediation_contract_sha256"
                ]
            }:
                raise RuntimeError("candidate_normal_remediation_contract_diverged")
        contract["beaker_normal_remediation_contract"] = deepcopy(
            normal_remediation_contract
        )
        contract["beaker_normal_remediation_contract_sha256"] = (
            normal_remediation_contract[
                "beaker_normal_remediation_contract_sha256"
            ]
        )
        session_layer_baseline = snapshot_session_layer(stage)
        derived_frame = derive_cup_interior_frame(
            stage,
            parent_path="/World/beaker2",
            visual_mesh_path="/World/beaker2/mesh",
            calibration_points_path="/World/ParticleSet",
        )
        if not _same_frame_core(accepted.frame, derived_frame):
            raise RuntimeError("opened_source_cup_frame_mismatch")
        presentation_layer_path = (
            candidate_dir / f"{candidate_id}_presentation.usda"
        )
        presentation_layer = begin_candidate_presentation_layer(
            stage,
            presentation_layer_path,
        )
        normal_remediation = author_beaker_normals_block(
            stage,
            contract=normal_remediation_contract,
            presentation_layer=presentation_layer,
        )
        physics_graph_preparation = prepare_static_render_physics_graph(
            stage,
            native=native,
            execute_command=omni.kit.commands.execute,
        )
        guarded_stage = presentation_layer_stage_proxy(stage, presentation_layer)
        material_retarget = native._retarget_stage_mdl_source_assets(
            guarded_stage,
            closure,
        )
        if (
            stage.GetEditTarget().GetLayer().identifier
            != presentation_layer.identifier
        ):
            raise RuntimeError("mdl_retarget_changed_candidate_edit_target")
        material = native._author_omniglass_presentation_water_material(
            stage,
            glass_color=REF_OMNIGLASS_GLASS_COLOR,
            reflection_color=REF_OMNIGLASS_REFLECTION_COLOR,
            mdl_source_asset=omniglass_source,
            closure_base_dir=closure["closure_base_dir"],
        )
        material = dict(material)
        authored_material_validation = (
            validate_authored_effective_replay_material(
                material,
                effective_look,
            )
        )
        material["mdl_compile_status"] = "NOT_POSITIVELY_CONFIRMED"
        material["mdl_error_scan_status"] = "PENDING_RUNTIME_LOG_SCAN"
        material["mdl_compile_success_claim_allowed"] = False
        beaker_material = verify_version_matched_native_beaker_material(
            stage,
            material_retarget=material_retarget,
        )
        lighting = native._author_liquid_presentation_lighting(stage, profile)
        authored_lighting_validation = (
            validate_authored_effective_replay_lighting(
                lighting,
                effective_look,
            )
        )
        closeup_camera = define_measured_beaker_closeup_camera(
            stage,
            frame=derived_frame,
            width=int(args.width),
            height=int(args.height),
        )
        pair_context_camera = define_measured_pair_context_camera(
            stage,
            region_config=accepted.summary["region_config"],
            width=int(args.width),
            height=int(args.height),
        )
        if (
            closeup_camera != runtime_camera_contracts["source_beaker_closeup"]
            or pair_context_camera != runtime_camera_contracts["context"]
        ):
            raise RuntimeError("authored_camera_contract_mismatch")
        context_camera, closeup_camera = apply_replay_camera_policy(
            stage,
            pair_context_info=pair_context_camera,
            closeup_info=closeup_camera,
        )
        native_table_camera = dict(context_camera["native_provenance_camera"])
        native_table_camera["role"] = "native_table_context"
        authored_state = author_static_candidate_state(
            stage,
            accepted=accepted,
            candidate_contract=contract,
            material_path=material["material_path"],
        )
        if snapshot_sdf_layer(author_root_layer) != author_root_snapshot:
            raise RuntimeError("candidate_author_source_root_changed_before_freeze")
        static_usd = candidate_dir / f"{candidate_id}_static.usda"
        static_entry_export = export_static_candidate_entry(
            stage,
            presentation_layer=presentation_layer,
            session_layer_baseline=session_layer_baseline,
            source_usd_path=accepted.source_usd_path,
            expected_source_sha256=accepted.source_usd_sha256,
            expected_presentation_path=presentation_layer_path,
            static_usd_path=static_usd,
            required_presentation_prim_path=authored_state[
                "presentation_primitive_path"
            ],
            required_source_prim_path="/World/beaker2/mesh",
        )
        postexport_dependency_resolution = (
            build_render_diagnostic_exported_static_dependency_resolution(
                static_usd,
                cell_root=out_root,
                candidate_root=candidate_dir,
                material_closure_root=closure["closure_root"],
            )
        )
        if postexport_dependency_resolution["status"] != "PASS":
            raise RuntimeError(
                "exported_static_dependency_resolution_failed:"
                f"unresolved={postexport_dependency_resolution['unresolved']}:"
                "outside="
                f"{postexport_dependency_resolution['outside_allowed_roots']}"
            )
        static_entry_export = {
            **static_entry_export,
            "postexport_dependency_resolution": (
                postexport_dependency_resolution
            ),
        }
        frozen_presentation_sha256 = _sha256_file(presentation_layer_path)
        frozen_static_entry_sha256 = _sha256_file(static_usd)
        if presentation_layer.permissionToEdit or presentation_layer.permissionToSave:
            raise RuntimeError("presentation_layer_relock_lost_after_static_export")
        frozen_stage = Usd.Stage.Open(str(static_usd), Usd.Stage.LoadAll)
        if frozen_stage is None:
            raise RuntimeError("frozen_static_entry_plain_reopen_failed")
        frozen_normal_remediation = verify_beaker_normals_block(
            frozen_stage,
            contract=normal_remediation_contract,
        )
        frozen_world_fingerprint_audit = (
            write_composed_world_fingerprint_artifact(
                frozen_stage,
                candidate_dir / "frozen_composed_world_fingerprint.json.gz",
            )
        )
        frozen_world_fingerprint = frozen_world_fingerprint_audit[
            "fingerprint"
        ]
        del frozen_stage
        del stage

        mdl_log_cursor = native._capture_kit_log_cursor()
        args._active_capture_stage_root = str(static_usd.resolve())
        stage = _open_exact_stage(
            context=context,
            app=app,
            timeline=timeline,
            source_path=static_usd,
            warmup_updates=args.warmup_updates,
        )
        capture_frame_layer = begin_disposable_capture_frame_layer(
            stage,
            candidate_id=candidate_id,
        )
        persistent_layer_lock = lock_capture_persistent_layers(
            stage,
            frame_layer=capture_frame_layer,
            expected_file_sha256={
                str(static_usd.resolve()): frozen_static_entry_sha256,
                str(presentation_layer_path.resolve()): (
                    frozen_presentation_sha256
                ),
                str(accepted.source_usd_path): accepted.source_usd_sha256,
            },
            expected_baseline=static_entry_export[
                "capture_persistent_layer_baseline"
            ],
        )
        capture_session_baseline = snapshot_session_layer(stage)
        capture_root_baseline = snapshot_sdf_layer(stage.GetRootLayer())
        diagnostic_artifact_paths = {
            "kit_log_segment": candidate_dir / "kit_log_segment.txt",
            "capture_frame_bindings_json": (
                candidate_dir / "capture_frame_bindings.json"
            ),
            "frozen_composed_world_fingerprint_json": (
                candidate_dir / "frozen_composed_world_fingerprint.json.gz"
            ),
            "capture_composed_world_fingerprint_json": (
                candidate_dir / "capture_composed_world_fingerprint.json.gz"
            ),
            "reopened_composed_world_fingerprint_json": (
                candidate_dir / "reopened_composed_world_fingerprint.json.gz"
            ),
            "capture_session_baseline_usda": (
                candidate_dir / "capture_session_baseline.usda"
            ),
            "capture_session_baseline_json": (
                candidate_dir / "capture_session_baseline.json"
            ),
            "capture_session_post_cleanup_usda": (
                candidate_dir / "capture_session_post_cleanup.usda"
            ),
            "capture_session_post_cleanup_json": (
                candidate_dir / "capture_session_post_cleanup.json"
            ),
            "capture_root_baseline_usda": (
                candidate_dir / "capture_root_baseline.usda"
            ),
            "capture_root_baseline_json": (
                candidate_dir / "capture_root_baseline.json"
            ),
            "capture_root_post_cleanup_usda": (
                candidate_dir / "capture_root_post_cleanup.usda"
            ),
            "capture_root_post_cleanup_json": (
                candidate_dir / "capture_root_post_cleanup.json"
            ),
            "capture_frame_final_usda": (
                candidate_dir / "capture_frame_final.usda"
            ),
            "capture_frame_final_json": (
                candidate_dir / "capture_frame_final.json"
            ),
        }
        capture_session_baseline_audit = write_layer_audit_artifacts(
            stage.GetSessionLayer(),
            usda_path=diagnostic_artifact_paths[
                "capture_session_baseline_usda"
            ],
            json_path=diagnostic_artifact_paths[
                "capture_session_baseline_json"
            ],
        )
        capture_root_baseline_audit = write_layer_audit_artifacts(
            stage.GetRootLayer(),
            usda_path=diagnostic_artifact_paths["capture_root_baseline_usda"],
            json_path=diagnostic_artifact_paths["capture_root_baseline_json"],
        )
        cameras = {
            "context": context_camera,
            "source_beaker_closeup": closeup_camera,
            "native_table_context": native_table_camera,
        }
        if tuple(cameras) != CAPTURE_CAMERA_ROLES:
            raise RuntimeError("capture_camera_roles_diverged")
        context_dir = candidate_dir / "context_frames"
        closeup_dir = candidate_dir / "source_beaker_closeup_frames"
        native_context_dir = candidate_dir / "native_table_context_frames"
        context_paths: list[Path] = []
        closeup_paths: list[Path] = []
        native_context_paths: list[Path] = []
        camera_diagnostics: dict[str, Any] = {}
        frame_bindings: list[dict[str, Any]] = []
        replicator_orchestrator_steps = 0
        discarded_warmup_capture: dict[str, Any] | None = None
        warmup_observed_attributes_before = ""
        warmup_observed_attributes_after = ""
        capture_resources: dict[str, dict[str, Any]] = {}
        capture_error: BaseException | None = None
        cleanup_contract: dict[str, Any] = {
            "destroyed_roles": [],
            "cleanup_failures": {},
            "cleanup_complete": False,
        }
        try:
            capture_resources = create_replicator_capture_resources(
                rep,
                cameras=cameras,
                resolution=(int(args.width), int(args.height)),
            )
            warmup_observed_attributes_before = (
                usd_observed_default_time_point_attributes_sha256(stage)
            )
            rep.orchestrator.preview()
            for _ in range(args.camera_warmup_updates):
                require_stopped_timeline(timeline)
                app.update()
            warmup_observed_attributes_after = (
                usd_observed_default_time_point_attributes_sha256(stage)
            )
            if (
                warmup_observed_attributes_after
                != warmup_observed_attributes_before
            ):
                raise RuntimeError(
                    "static_render_warmup_changed_observed_default_time_usd_point_attributes"
                )
            if render_diagnostic_identity is not None:
                warmup_record = accepted.records[0]
                warmup_proxy = accepted.proxy_frame(
                    candidate_id,
                    frame_offset=0,
                )
                _set_presentation_frame(
                    stage,
                    warmup_proxy,
                    frame_index=int(warmup_record["step_index"]),
                )
                discarded_warmup_capture = (
                    capture_and_discard_render_diagnostic_warmup(
                        capture_function=capture_static_replicator_rgbs,
                        output_root=(
                            candidate_dir / "_discarded_warmup_capture"
                        ),
                        frame_index=int(warmup_record["step_index"]),
                        orchestrator=rep.orchestrator,
                        timeline=timeline,
                        annotators={
                            role: resource["annotator"]
                            for role, resource in capture_resources.items()
                        },
                        width=int(args.width),
                        height=int(args.height),
                        rt_subframes=int(
                            effective_look["render_settings"]["rt_subframes"]
                        ),
                        observed_default_time_usd_point_attributes_hash=(
                            lambda: usd_observed_default_time_point_attributes_sha256(
                                stage
                            )
                        ),
                    )
                )
                verify_presentation_frame_binding(
                    stage,
                    warmup_proxy,
                    frame_index=int(warmup_record["step_index"]),
                )
            for frame_offset, record in enumerate(accepted.records):
                proxy = accepted.proxy_frame(candidate_id, frame_offset=frame_offset)
                frame_index = int(record["step_index"])
                proxy_update = _set_presentation_frame(
                    stage,
                    proxy,
                    frame_index=frame_index,
                )
                frame_paths = {
                    "context": context_dir / f"frame_{frame_index:04d}.png",
                    "source_beaker_closeup": (
                        closeup_dir / f"frame_{frame_index:04d}.png"
                    ),
                    "native_table_context": (
                        native_context_dir / f"frame_{frame_index:04d}.png"
                    ),
                }
                capture = capture_static_replicator_rgbs(
                    orchestrator=rep.orchestrator,
                    timeline=timeline,
                    annotators={
                        role: resource["annotator"]
                        for role, resource in capture_resources.items()
                    },
                    output_paths=frame_paths,
                    width=int(args.width),
                    height=int(args.height),
                    rt_subframes=int(
                        effective_look["render_settings"]["rt_subframes"]
                    ),
                    observed_default_time_usd_point_attributes_hash=(
                        lambda: usd_observed_default_time_point_attributes_sha256(
                            stage
                        )
                    ),
                )
                replicator_orchestrator_steps += int(
                    capture["replicator_orchestrator_steps_executed"]
                )
                post_capture_geometry_binding = verify_presentation_frame_binding(
                    stage,
                    proxy,
                    frame_index=frame_index,
                )
                proxy_update = {
                    **proxy_update,
                    "usd_geometry_binding_after_capture": (
                        post_capture_geometry_binding
                    ),
                }
                for role, frame_path in frame_paths.items():
                    diagnostics = {
                        **capture["frames"][role],
                        "camera_path": cameras[role]["camera_path"],
                        "timeline_time_before": capture["timeline_time_before"],
                        "timeline_time_after": capture["timeline_time_after"],
                        "timeline_advanced": capture["timeline_advanced"],
                        "observed_default_time_usd_point_attributes_sha256_before": capture[
                            "observed_default_time_usd_point_attributes_sha256_before"
                        ],
                        "observed_default_time_usd_point_attributes_sha256_after": capture[
                            "observed_default_time_usd_point_attributes_sha256_after"
                        ],
                        "observed_default_time_usd_point_attributes_changed": capture[
                            "observed_default_time_usd_point_attributes_changed"
                        ],
                        "replicator_orchestrator_steps_executed": capture[
                            "replicator_orchestrator_steps_executed"
                        ],
                        "replicator_delta_time": capture["replicator_delta_time"],
                        "physics_step_count_instrumented": capture[
                            "physics_step_count_instrumented"
                        ],
                        "physics_steps_executed": capture["physics_steps_executed"],
                    }
                    camera_diagnostics[str(frame_path.relative_to(candidate_dir))] = (
                        diagnostics
                    )
                frame_binding = build_capture_frame_binding(
                    candidate_id=candidate_id,
                    frame_offset=frame_offset,
                    record=record,
                    physical_trace_sha256=accepted.physical_trace_identity[
                        "physical_trace_sha256"
                    ],
                    proxy_update=proxy_update,
                    image_paths=frame_paths,
                    effective_look_contract=effective_look,
                )
                for role, frame_path in frame_paths.items():
                    diagnostic = camera_diagnostics[
                        str(frame_path.relative_to(candidate_dir))
                    ]
                    if diagnostic.get("sha256") != frame_binding["image_sha256"][role]:
                        raise RuntimeError(
                            f"capture_frame_image_hash_binding_mismatch:{role}:"
                            f"{frame_index}"
                        )
                frame_bindings.append(frame_binding)
                context_paths.append(frame_paths["context"])
                closeup_paths.append(frame_paths["source_beaker_closeup"])
                native_context_paths.append(frame_paths["native_table_context"])
        except BaseException as exc:
            capture_error = exc
            raise
        finally:
            if isinstance(capture_error, ReplicatorResourceCreationError):
                cleanup_contract = deepcopy(capture_error.cleanup_contract)
            else:
                cleanup_contract = destroy_replicator_capture_resources(
                    capture_resources
                )
            args._last_replicator_cleanup = deepcopy(cleanup_contract)
            if capture_error is None:
                require_replicator_cleanup(cleanup_contract)
            elif cleanup_contract.get("cleanup_complete") is not True:
                carb.log_error(
                    "Replicator cleanup also failed while preserving the primary "
                    f"replay error: {cleanup_contract}"
                )

        capture_session_quiescence = quiesce_capture_session(
            stage,
            app=app,
            timeline=timeline,
            minimum_updates=2,
            maximum_updates=max(4, int(args.camera_warmup_updates)),
        )
        if not capture_session_quiescence["quiescence_status"].startswith(
            "PASS_"
        ):
            raise RuntimeError(
                "capture_session_failed_to_quiesce:"
                + json.dumps(capture_session_quiescence, sort_keys=True)
            )

        expected_frame_indices = list(
            accepted.physical_trace_identity["frame_indices"]
        )
        actual_frame_indices = [
            binding["physical_trace_frame_index"] for binding in frame_bindings
        ]
        if actual_frame_indices != expected_frame_indices:
            raise RuntimeError(
                "capture_frame_binding_indices_mismatch:"
                f"actual={actual_frame_indices}:expected={expected_frame_indices}"
            )
        frame_binding_payload = {
            "schema_version": 1,
            "candidate_id": candidate_id,
            "lighting_variant_id": effective_look["lighting_variant_id"],
            "effective_replay_look_contract": deepcopy(effective_look),
            "effective_replay_look_contract_sha256": effective_look[
                "effective_replay_look_contract_sha256"
            ],
            "physical_trace_sha256": accepted.physical_trace_identity[
                "physical_trace_sha256"
            ],
            "frame_indices": expected_frame_indices,
            "bindings": frame_bindings,
            "bindings_sha256": _json_sha256(frame_bindings),
        }
        atomic_write_json(
            diagnostic_artifact_paths["capture_frame_bindings_json"],
            frame_binding_payload,
        )

        final_proxy = accepted.proxy_frame(candidate_id, frame_offset=-1)
        final_presentation_binding = verify_presentation_frame_binding(
            stage,
            final_proxy,
            frame_index=int(accepted.records[-1]["step_index"]),
        )
        capture_session_post_cleanup_audit = write_layer_audit_artifacts(
            stage.GetSessionLayer(),
            usda_path=diagnostic_artifact_paths[
                "capture_session_post_cleanup_usda"
            ],
            json_path=diagnostic_artifact_paths[
                "capture_session_post_cleanup_json"
            ],
        )
        capture_root_post_cleanup_audit = write_layer_audit_artifacts(
            stage.GetRootLayer(),
            usda_path=diagnostic_artifact_paths[
                "capture_root_post_cleanup_usda"
            ],
            json_path=diagnostic_artifact_paths[
                "capture_root_post_cleanup_json"
            ],
        )
        capture_frame_final_audit = write_layer_audit_artifacts(
            capture_frame_layer,
            usda_path=diagnostic_artifact_paths["capture_frame_final_usda"],
            json_path=diagnostic_artifact_paths["capture_frame_final_json"],
        )
        capture_session_residue = build_capture_session_residue_contract(
            stage,
            baseline_snapshot=capture_session_baseline,
            frame_layer=capture_frame_layer,
        )
        if capture_session_residue["classification_gate_status"] != "PASS":
            raise SessionLayerValidationError(
                "capture_session_residue_unclassified:"
                f"{capture_session_residue['classification_failures']}",
                capture_session_residue,
            )
        capture_root_post_cleanup = snapshot_sdf_layer(stage.GetRootLayer())
        capture_root_diff = diff_layer_snapshots(
            capture_root_baseline,
            capture_root_post_cleanup,
        )
        if capture_root_diff["changed"]:
            raise RuntimeError(
                "locked_capture_root_changed_during_replicator:"
                + json.dumps(capture_root_diff, sort_keys=True)
            )
        persistent_layers_after_capture = (
            verify_capture_persistent_layers_unchanged(
                stage,
                persistent_layer_lock,
            )
        )
        capture_world_fingerprint_audit = (
            write_composed_world_fingerprint_artifact(
                stage,
                diagnostic_artifact_paths[
                    "capture_composed_world_fingerprint_json"
                ],
            )
        )
        capture_world_fingerprint = capture_world_fingerprint_audit[
            "fingerprint"
        ]
        fresh_static_stage = Usd.Stage.Open(str(static_usd), Usd.Stage.LoadAll)
        if fresh_static_stage is None:
            raise RuntimeError("static_entry_equivalence_reopen_failed")
        reopened_world_fingerprint_audit = (
            write_composed_world_fingerprint_artifact(
                fresh_static_stage,
                diagnostic_artifact_paths[
                    "reopened_composed_world_fingerprint_json"
                ],
            )
        )
        reopened_world_fingerprint = reopened_world_fingerprint_audit[
            "fingerprint"
        ]
        del fresh_static_stage
        if capture_world_fingerprint != reopened_world_fingerprint:
            raise RuntimeError(
                "capture_stage_static_entry_world_fingerprint_mismatch:"
                f"capture={capture_world_fingerprint}:"
                f"entry={reopened_world_fingerprint}"
            )
        if reopened_world_fingerprint != frozen_world_fingerprint:
            raise RuntimeError("frozen_static_entry_world_fingerprint_changed")
        capture_session_residue[
            "composed_world_default_time_property_snapshot_equivalence_"
            "excluding_known_physx_runtime_status"
        ] = "PASS"
        author_session_contract = static_entry_export[
            "session_layer_runtime_opinions"
        ]
        author_session_contract[
            "composed_world_default_time_property_snapshot_equivalence_"
            "excluding_known_physx_runtime_status"
        ] = "PASS"
        author_session_contract["allowed_claims"].append(
            "composed_world_default_time_property_snapshot_equivalence_"
            "excluding_known_physx_runtime_verified=true"
        )
        author_session_contract["blocked_claims"] = [
            claim
            for claim in author_session_contract["blocked_claims"]
            if claim
            != "composed_world_default_time_property_snapshot_equivalence_"
            "excluding_known_physx_runtime_verified=true"
        ]
        capture_stage_discard = discard_capture_stage(
            context=context,
            app=app,
            timeline=timeline,
            expected_root_path=static_usd,
            flush_updates=max(2, int(args.camera_warmup_updates)),
        )
        args._active_capture_stage_root = None
        capture_session_residue["capture_stage_disposition"] = "DISCARDED"
        args._last_session_restore = {
            "manual_restore_status": "NOT_RUN_DISPOSABLE_STAGE",
            "capture_stage_discarded": True,
        }
        mdl_runtime_validation = validate_replay_mdl_log_segment(
            native,
            cursor=mdl_log_cursor,
            log_artifact_path=candidate_dir / "kit_log_segment.txt",
            mdl_source_sha256=closure["required_file_sha256"],
        )
        material["mdl_compile_status"] = mdl_runtime_validation[
            "mdl_compile_status"
        ]
        material["mdl_error_scan_status"] = mdl_runtime_validation[
            "mdl_error_scan_status"
        ]
        material["mdl_compile_success_claim_allowed"] = False
        material["mdl_diagnostic_status_authority"] = (
            "run_scoped_kit_log_segment_after_capture_stage_discard_and_flush"
        )
        context_video = candidate_dir / "context.mp4"
        closeup_video = candidate_dir / "source_beaker_closeup.mp4"
        native_context_video = candidate_dir / "native_table_context.mp4"
        video_results = [
            native._write_mp4_from_frames(
                context_paths, context_video, fps=args.video_fps
            ),
            native._write_mp4_from_frames(
                closeup_paths, closeup_video, fps=args.video_fps
            ),
            native._write_mp4_from_frames(
                native_context_paths, native_context_video, fps=args.video_fps
            ),
        ]
        if not all(video_results):
            raise RuntimeError(f"omniglass_replay_video_encode_failed:{candidate_id}")
        material_closure_snapshot_after_candidate = (
            verify_material_closure_snapshot_unchanged(closure)
        )

        contract.update(
            {
                "generated_at_utc": _utc_now(),
                "material": material,
                "authored_material_validation": authored_material_validation,
                "mdl_runtime_validation": mdl_runtime_validation,
                "material_retarget": material_retarget,
                "material_closure": closure,
                "mdl_search_path_contract": deepcopy(
                    mdl_search_path_contract
                ),
                "runtime_dependency_resolution": deepcopy(
                    getattr(args, "_runtime_dependency_resolution", None)
                ),
                "material_closure_snapshot_before": (
                    material_closure_snapshot_before
                ),
                "material_closure_snapshot_after_candidate": (
                    material_closure_snapshot_after_candidate
                ),
                "version_matched_mdl_source": {
                    "source_root": closure["source_root"],
                    "runtime_prefix": closure["runtime_prefix"],
                    "runtime_version": closure["runtime_version"],
                    "source_root_under_runtime_prefix": closure[
                        "source_root_under_runtime_prefix"
                    ],
                    "required_file_sha256": closure["required_file_sha256"],
                    "source_file_sha256": closure["source_file_sha256"],
                    "source_tree_sha256": closure["source_tree_sha256"],
                },
                "beaker_override": {
                    "enabled": False,
                    "beaker_override_used": False,
                    "reason": "preserve_version_matched_native_beaker_material",
                },
                "beaker_material": beaker_material,
                "lighting": lighting,
                "authored_lighting_validation": authored_lighting_validation,
                "lighting_variant_id": effective_look[
                    "lighting_variant_id"
                ],
                "effective_replay_look_contract": deepcopy(effective_look),
                "effective_replay_look_contract_sha256": effective_look[
                    "effective_replay_look_contract_sha256"
                ],
                "render_settings": render_settings,
                "context_camera": context_camera,
                "source_beaker_closeup_camera": closeup_camera,
                "native_table_context_camera": native_table_camera,
                "camera_capture_diagnostics": camera_diagnostics,
                "capture_frame_bindings": frame_binding_payload,
                "render_output_contract": {
                    "width": int(args.width),
                    "height": int(args.height),
                    "fps": float(args.video_fps),
                    "expected_frame_indices": list(
                        accepted.physical_trace_identity["frame_indices"]
                    ),
                },
                "static_replicator_capture": {
                    "capture_backend": "replicator_render_products",
                    "camera_capture_count": len(camera_diagnostics),
                    "rt_subframes": int(
                        effective_look["render_settings"]["rt_subframes"]
                    ),
                    "timeline_advanced": False,
                    "observed_default_time_usd_point_attributes_changed": False,
                    "warmup_observed_default_time_usd_point_attributes_sha256_before": (
                        warmup_observed_attributes_before
                    ),
                    "warmup_observed_default_time_usd_point_attributes_sha256_after": (
                        warmup_observed_attributes_after
                    ),
                    "warmup_observed_default_time_usd_point_attributes_changed": False,
                    "gpu_or_fabric_physics_state_inspected": False,
                    "replicator_orchestrator_steps_executed": (
                        replicator_orchestrator_steps
                    ),
                    "replicator_delta_time": 0.0,
                    "physics_step_count_instrumented": False,
                    "physics_steps_executed": None,
                },
                "discarded_warmup_capture": discarded_warmup_capture,
                "replicator_resource_cleanup": cleanup_contract,
                "capture_stage_lifecycle": {
                    "author_and_freeze_before_replicator": True,
                    "persistent_layer_lock": persistent_layer_lock,
                    "persistent_layers_after_capture": (
                        persistent_layers_after_capture
                    ),
                    "session_residue": capture_session_residue,
                    "capture_session_quiescence": capture_session_quiescence,
                    "final_presentation_binding_after_quiescence": (
                        final_presentation_binding
                    ),
                    "capture_stage_discard": capture_stage_discard,
                    "capture_session_baseline_audit": (
                        capture_session_baseline_audit
                    ),
                    "capture_session_post_cleanup_audit": (
                        capture_session_post_cleanup_audit
                    ),
                    "capture_root_baseline_audit": capture_root_baseline_audit,
                    "capture_root_post_cleanup_audit": (
                        capture_root_post_cleanup_audit
                    ),
                    "capture_frame_final_audit": capture_frame_final_audit,
                    "capture_root_diff": capture_root_diff,
                    "frozen_world_fingerprint": frozen_world_fingerprint,
                    "capture_world_fingerprint": capture_world_fingerprint,
                    "reopened_world_fingerprint": reopened_world_fingerprint,
                    "frozen_world_fingerprint_audit": (
                        frozen_world_fingerprint_audit
                    ),
                    "capture_world_fingerprint_audit": (
                        capture_world_fingerprint_audit
                    ),
                    "reopened_world_fingerprint_audit": (
                        reopened_world_fingerprint_audit
                    ),
                    "frozen_presentation_sha256": frozen_presentation_sha256,
                    "frozen_static_entry_sha256": frozen_static_entry_sha256,
                },
                "static_stage_authoring": authored_state,
                "static_entry_export": static_entry_export,
                "beaker_normal_remediation": normal_remediation,
                "frozen_beaker_normal_remediation": frozen_normal_remediation,
                "static_render_physics_graph_preparation": physics_graph_preparation,
                "runtime_contract": {
                    **dict(contract["runtime_contract"]),
                    "capture_stage_discarded_after_candidate": True,
                    "observed_default_time_usd_point_attributes_changed": False,
                    "timeline_observed_stopped_at_all_checkpoints": True,
                },
            }
        )
        finalized = finalize_candidate_manifest(
            contract,
            accepted_replay=accepted,
            candidate_dir=candidate_dir,
            static_usd_path=static_usd,
            presentation_layer_path=presentation_layer_path,
            closeup_image_paths=closeup_paths,
            context_image_paths=context_paths,
            native_context_image_paths=native_context_paths,
            video_paths={
                "context": context_video,
                "source_beaker_closeup": closeup_video,
                "native_table_context": native_context_video,
            },
            diagnostic_artifact_paths={
                role: path for role, path in diagnostic_artifact_paths.items()
            },
        )
        candidate_manifest_path = candidate_dir / "candidate_manifest.json"
        atomic_write_json(candidate_manifest_path, finalized)
        finalized["candidate_manifest_path"] = str(candidate_manifest_path)
        finalized["candidate_manifest_sha256"] = _sha256_file(candidate_manifest_path)
        completed[candidate_id] = finalized
        args._completed_candidate_ids = list(completed)
        args._active_candidate_id = None

    input_snapshot_verification_after = verify_replay_input_snapshots_unchanged(
        accepted,
        matrix_authority,
    )
    material_closure_snapshot_after = verify_material_closure_snapshot_unchanged(
        closure
    )
    source_hash_after = input_snapshot_verification_after["verified_sha256"][
        "accepted_source_usd"
    ]
    identities = [item["input_identity"] for item in completed.values()]
    if any(identity != accepted.physical_trace_identity for identity in identities):
        raise RuntimeError("candidate_manifest_input_identity_diverged")
    visual_prototype_only = bool(
        getattr(args, "visual_prototype_display_fill_only", False)
    )
    run_scope = build_replay_scope_contract(
        tuple(completed),
        visual_prototype_only=visual_prototype_only,
    )
    run_scope["formal_five_candidate_replay_complete"] = bool(
        not visual_prototype_only
        and tuple(completed) == REFERENCE_CANDIDATE_IDS
    )
    render_diagnostic_identity = validate_render_diagnostic_cell_scope(args)
    render_diagnostic_projection = (
        build_effective_replay_look_matrix_projection(effective_look)
        if render_diagnostic_identity is not None
        else None
    )
    top_manifest = {
        "schema_version": 1,
        "manifest_type": "real_beaker_omniglass_reference_replay",
        "generated_at_utc": _utc_now(),
        "classification": replay_success_classification(effective_look),
        **run_scope,
        **(
            render_diagnostic_lifecycle_contract()
            if render_diagnostic_identity is not None
            else {}
        ),
        "execution_provenance": deepcopy(args._execution_provenance),
        "lighting_variant_id": effective_look["lighting_variant_id"],
        "render_diagnostic_variant_id": effective_look[
            "render_diagnostic_variant_id"
        ],
        "render_diagnostic_identity": deepcopy(render_diagnostic_identity),
        "effective_replay_look_matrix_projection_sha256": (
            render_diagnostic_projection["canonical_json_utf8_sha256"]
            if render_diagnostic_projection is not None
            else None
        ),
        "effective_replay_look_contract": deepcopy(effective_look),
        "effective_replay_look_contract_sha256": effective_look[
            "effective_replay_look_contract_sha256"
        ],
        "accepted_summary_path": str(accepted.summary_path),
        "accepted_trace_path": str(accepted.trace_path),
        "source_usd_path": str(accepted.source_usd_path),
        "source_usd_sha256": source_hash_after,
        "accepted_summary_sha256": accepted.summary_sha256,
        "accepted_trace_sha256": accepted.trace_sha256,
        "authoritative_physics_input": matrix_authority,
        "input_snapshot_verification_before": input_snapshot_verification_before,
        "input_snapshot_verification_after": input_snapshot_verification_after,
        "accepted_diagnostic_segment_provenance": deepcopy(
            accepted.diagnostic_segment_provenance
        ),
        "material_closure_snapshot_before": material_closure_snapshot_before,
        "material_closure_snapshot_after": material_closure_snapshot_after,
        "mdl_search_path_contract": deepcopy(mdl_search_path_contract),
        "runtime_dependency_resolution": deepcopy(
            getattr(args, "_runtime_dependency_resolution", None)
        ),
        "physical_trace_identity": deepcopy(accepted.physical_trace_identity),
        "camera_contracts_preflight": deepcopy(runtime_camera_contracts),
        "candidate_manifests": completed,
        "all_candidate_input_identities_equal": True,
        "runtime_contract": {
            "kit_version": str(
                getattr(args, "_kit_version", "NOT_AVAILABLE_ISAACSIM41")
            ),
            "render_delegate": str(
                getattr(args, "_render_delegate", "ISAAC_DEFAULT_UNCHANGED")
            ),
            "runtime_child_pid": int(
                getattr(args, "_runtime_child_pid", os.getpid())
            ),
            "exact_source_opened_for_every_author_stage": True,
            "frozen_static_entry_opened_for_every_capture_stage": True,
            "capture_stage_discarded_after_every_candidate": True,
            "physics_step_count_instrumented": False,
            "physics_steps_executed": None,
            "observed_default_time_usd_point_attributes_changed": False,
            "gpu_or_fabric_physics_state_inspected": False,
            "timeline_observed_stopped_at_all_checkpoints": True,
            "physical_and_debug_points_hidden": True,
        },
        "render_artifact_set_complete": True,
        "portable_dependency_closure_complete": False,
        "colleague_delivery_ready": False,
        "requires_localization_before_colleague_delivery": True,
        "visual_review_verdict": "PENDING_INDEPENDENT_REVIEW",
        "omniglass_reference_particle_look_selected": False,
    }
    if matrix_authority.get("authority_kind") == (
        "support_aligned_p4096_s2_accepted_authority"
    ):
        top_manifest["accepted_authority_input"] = matrix_authority
    else:
        top_manifest["authoritative_matrix_input"] = matrix_authority
    top_manifest["effective_replay_look_consistency_validation"] = (
        validate_replay_effective_look_consistency(top_manifest)
    )
    return top_manifest


def build_replay_runtime_failure_manifest(
    args: argparse.Namespace,
    accepted: AcceptedReplayInput,
    exc: BaseException,
    *,
    traceback_text: str,
) -> dict[str, Any]:
    effective_look = deepcopy(
        getattr(args, "_effective_replay_look_contract", None)
    )
    render_diagnostic_identity = validate_render_diagnostic_cell_scope(args)
    render_diagnostic_variant = (
        effective_look.get("render_diagnostic_variant_id")
        if isinstance(effective_look, Mapping)
        else None
    )
    render_diagnostic_projection_hash = (
        build_effective_replay_look_matrix_projection(effective_look)[
            "canonical_json_utf8_sha256"
        ]
        if render_diagnostic_variant is not None
        else None
    )
    checkpoint_observed = bool(
        getattr(args, "_timeline_checkpoint_observed", False)
    )
    runtime_failure_context = {
        "active_candidate_id": getattr(args, "_active_candidate_id", None),
        "completed_candidate_ids": list(
            getattr(args, "_completed_candidate_ids", [])
        ),
        "last_replicator_cleanup": deepcopy(
            getattr(args, "_last_replicator_cleanup", None)
        ),
    }
    last_session_restore = getattr(args, "_last_session_restore", None)
    if last_session_restore is not None:
        runtime_failure_context["last_session_restore"] = deepcopy(
            last_session_restore
        )
    emergency_discard = getattr(args, "_last_emergency_discard", None)
    if emergency_discard is not None:
        runtime_failure_context["emergency_capture_stage_discard"] = deepcopy(
            emergency_discard
        )
    session_layer_contract = getattr(exc, "session_layer_contract", None)
    if session_layer_contract is not None:
        runtime_failure_context["session_layer_validation"] = deepcopy(
            dict(session_layer_contract)
        )
    permission_recovery = getattr(
        exc,
        "presentation_layer_export_permission_recovery",
        None,
    )
    if permission_recovery is not None:
        runtime_failure_context[
            "presentation_layer_export_permission_recovery"
        ] = validate_presentation_layer_export_permission_recovery_contract(
            permission_recovery
        )
    return {
        "schema_version": 1,
        "manifest_type": "real_beaker_omniglass_reference_replay",
        "generated_at_utc": _utc_now(),
        "classification": "STOP_RUNTIME_ERROR",
        "execution_provenance": deepcopy(
            getattr(args, "_execution_provenance", None)
        ),
        "lighting_variant_id": (
            effective_look.get("lighting_variant_id")
            if isinstance(effective_look, Mapping)
            else None
        ),
        "render_diagnostic_variant_id": render_diagnostic_variant,
        "render_diagnostic_identity": deepcopy(render_diagnostic_identity),
        "effective_replay_look_matrix_projection_sha256": (
            render_diagnostic_projection_hash
        ),
        "effective_replay_look_contract": effective_look,
        "effective_replay_look_contract_sha256": (
            effective_look.get("effective_replay_look_contract_sha256")
            if isinstance(effective_look, Mapping)
            else None
        ),
        "fatal_error": {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback_text,
        },
        "physical_trace_identity": deepcopy(accepted.physical_trace_identity),
        "render_artifact_set_complete": False,
        **(
            render_diagnostic_lifecycle_contract()
            if render_diagnostic_identity is not None
            else {}
        ),
        "portable_dependency_closure_complete": False,
        "colleague_delivery_ready": False,
        "runtime_failure_context": runtime_failure_context,
        "visual_review_verdict": "NOT_RUN",
        "omniglass_reference_particle_look_selected": False,
        "runtime_contract": {
            "physics_step_count_instrumented": False,
            "physics_steps_executed": None,
            "timeline_checkpoint_observation_recorded": checkpoint_observed,
            "timeline_observed_stopped_at_recorded_checkpoints": (
                True if checkpoint_observed else None
            ),
        },
    }


def finalize_preclose_manifest_after_child_exit(
    preclose_manifest_path: str | os.PathLike[str],
    *,
    child_exit_code: int,
    manifest_path: str | os.PathLike[str],
) -> dict[str, Any]:
    """Promote a pre-close manifest only after the Kit child exits cleanly."""
    exit_code = _require_plain_int("child_process_exit_code", child_exit_code)
    if exit_code != 0:
        raise ValueError(f"child_process_exit_nonzero:{exit_code}")
    preclose_path = Path(preclose_manifest_path).expanduser().resolve()
    preclose = _load_json_object(
        preclose_path,
        label="replay_preclose_manifest",
    )
    if preclose.get("classification") != (
        "RENDER_COMPLETE_PENDING_APPLICATION_CLOSE"
    ):
        raise ValueError("preclose_manifest_classification_invalid")
    effective_look_validation = validate_replay_effective_look_consistency(
        preclose
    )
    provenance = preclose.get("execution_provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("preclose_execution_provenance_missing")
    source_verification = verify_execution_provenance_sources_unchanged(
        provenance
    )
    finalized = deepcopy(preclose)
    finalized_look = validate_effective_replay_look_contract(
        preclose.get("effective_replay_look_contract")  # type: ignore[arg-type]
    )
    finalized["classification"] = replay_success_classification(finalized_look)
    finalized["generated_at_utc"] = _utc_now()
    if finalized_look["render_diagnostic_variant_id"] is not None:
        finalized.update(render_diagnostic_lifecycle_contract())
    else:
        finalized["standalone_final_evidence_authority"] = True
    finalized["execution_source_end_verification_status"] = "PASS"
    finalized["execution_source_verification_after_application_close"] = (
        source_verification
    )
    finalized["effective_replay_look_consistency_validation"] = (
        effective_look_validation
    )
    finalized.setdefault("runtime_contract", {})[
        "application_close_status"
    ] = "PASS_CHILD_PROCESS_EXIT_ZERO_AFTER_SIMULATION_APP_CLOSE"
    finalized["child_process_contract"] = {
        "exit_code": exit_code,
        "preclose_manifest_path": str(preclose_path),
        "preclose_manifest_sha256": _sha256_file(preclose_path),
        "clean_exit_required": True,
        "clean_exit_observed": True,
    }
    scoped_manifest = preclose_path.parent / "replay_manifest.json"
    requested_manifest = Path(manifest_path).expanduser().resolve()
    atomic_write_json(scoped_manifest, finalized)
    if requested_manifest != scoped_manifest:
        atomic_write_json(requested_manifest, finalized)
    return finalized


def _run_runtime(
    args: argparse.Namespace,
    accepted: AcceptedReplayInput,
    contracts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    preboot_effective_look = _validated_effective_look_contract_for_args(args)
    render_diagnostic_identity = validate_render_diagnostic_cell_scope(args)
    installed_startup_arguments: list[str] = []
    installed_mdl_search_path_contract: dict[str, Any] | None = None
    if render_diagnostic_identity is not None:
        installed_startup_arguments = (
            install_effective_replay_kit_startup_arguments(
                sys.argv,
                preboot_effective_look,
            )
        )
        preboot_closure = getattr(args, "_preboot_material_closure", None)
        if not isinstance(preboot_closure, Mapping):
            raise RuntimeError("render_diagnostic_preboot_mdl_closure_missing")
        installed_mdl_search_path_contract = (
            install_render_diagnostic_mdl_startup_arguments(
                sys.argv,
                preboot_closure,
            )
        )
    args._render_diagnostic_kit_startup_arguments = list(
        installed_startup_arguments
    )
    args._render_diagnostic_mdl_search_path_contract = deepcopy(
        installed_mdl_search_path_contract
    )
    from isaacsim import SimulationApp

    out_root = Path(args._resolved_out_root)
    manifest_path = Path(args._resolved_manifest)
    args._active_candidate_id = None
    args._active_capture_stage_root = None
    args._completed_candidate_ids = []
    args._last_replicator_cleanup = None
    args._last_session_restore = None
    args._last_emergency_discard = None
    args._timeline_checkpoint_observed = False
    app: Any | None = None
    result: dict[str, Any] | None = None
    primary_error: BaseException | None = None
    application_close_status = "NOT_APPLICABLE_APP_NOT_CREATED"
    preclose_persist_error: BaseException | None = None
    try:
        try:
            app = SimulationApp(
                {
                    "headless": bool(args.headless),
                    "width": int(args.width),
                    "height": int(args.height),
                    **(
                        {"renderer": "RayTracedLighting"}
                        if render_diagnostic_identity is not None
                        else {}
                    ),
                }
            )
            args._runtime_child_pid = os.getpid()
            args._render_delegate = (
                "RayTracedLighting"
                if render_diagnostic_identity is not None
                else "ISAAC_DEFAULT_UNCHANGED"
            )
            try:
                import omni.kit.app

                kit_app = omni.kit.app.get_app()
                kit_version = None
                for method_name in ("get_build_version", "get_version"):
                    method = getattr(kit_app, method_name, None)
                    if callable(method):
                        value = method()
                        if value:
                            kit_version = str(value)
                            break
                args._kit_version = (
                    kit_version or "NOT_AVAILABLE_ISAACSIM41"
                )
            except BaseException:
                args._kit_version = "NOT_AVAILABLE_ISAACSIM41"
            if render_diagnostic_identity is not None:
                import carb

                mdl_search_contract = (
                    validate_render_diagnostic_mdl_search_path_readback(
                        carb.settings.get_settings(),
                        args._render_diagnostic_mdl_search_path_contract,
                    )
                )
                args._render_diagnostic_mdl_search_path_contract = deepcopy(
                    mdl_search_contract
                )
                material_closure_root = _absolute_path_without_symlink_resolution(
                    args._preboot_material_closure["closure_root"]
                )
                source_closure = validate_render_diagnostic_source_dependency_snapshot(
                    out_root,
                    args._source_dependency_closure,
                    additional_allowed_dependency_roots=(
                        material_closure_root,
                    ),
                )
                args._runtime_dependency_resolution = (
                    build_render_diagnostic_runtime_dependency_resolution(
                        out_root,
                        source_closure,
                        additional_allowed_dependency_roots=(
                            material_closure_root,
                        ),
                    )
                )
            runtime_effective_look = (
                _validated_effective_look_contract_for_args(args)
            )
            if runtime_effective_look != getattr(
                args, "_effective_replay_look_contract", None
            ):
                raise RuntimeError(
                    "effective_replay_look_changed_after_simulation_app_boot"
                )
            runtime_accepted, matrix_authority = load_replay_inputs_from_args(
                args,
                recompute_closure=True,
            )
            if (
                runtime_accepted.summary_sha256 != accepted.summary_sha256
                or runtime_accepted.trace_sha256 != accepted.trace_sha256
                or runtime_accepted.source_usd_sha256 != accepted.source_usd_sha256
                or runtime_accepted.physical_trace_identity
                != accepted.physical_trace_identity
                or runtime_accepted.accepted_authority_bundle_sha256
                != accepted.accepted_authority_bundle_sha256
            ):
                raise RuntimeError("accepted_replay_changed_after_simulation_app_boot")
            preflight_authority = dict(args._matrix_authority_preflight)
            comparable_fields = (
                "matrix_manifest_path",
                "matrix_manifest_sha256",
                "selected_cell_id",
                "selected_particle_count",
                "selected_seed",
                "accepted_summary_sha256",
                "accepted_trace_sha256",
                "accepted_source_usd_sha256",
                "physical_trace_identity",
                "matrix_run_identity_sha256",
            )
            if any(
                matrix_authority.get(field) != preflight_authority.get(field)
                for field in comparable_fields
            ):
                raise RuntimeError(
                    "matrix_authority_changed_after_simulation_app_boot"
                )
            verify_replay_input_snapshots_unchanged(accepted, matrix_authority)
            runtime_contracts = deepcopy(dict(contracts))
            for candidate_id, contract in runtime_contracts.items():
                if (
                    contract.get("lighting_variant_id")
                    != runtime_effective_look["lighting_variant_id"]
                    or contract.get("effective_replay_look_contract")
                    != runtime_effective_look
                    or contract.get("effective_replay_look_contract_sha256")
                    != runtime_effective_look[
                        "effective_replay_look_contract_sha256"
                    ]
                ):
                    raise RuntimeError(
                        "candidate_effective_look_changed_after_simulation_app_boot:"
                        f"{candidate_id}"
                    )
                contract["authoritative_physics_input"] = deepcopy(matrix_authority)
                if matrix_authority.get("authority_kind") == (
                    "support_aligned_p4096_s2_accepted_authority"
                ):
                    contract["accepted_authority_input"] = deepcopy(
                        matrix_authority
                    )
                else:
                    contract["authoritative_matrix_input"] = deepcopy(
                        matrix_authority
                    )
                contract["execution_provenance"] = deepcopy(
                    args._execution_provenance
                )
            args._matrix_authority = deepcopy(matrix_authority)
            result = _render_validated_replay(
                args,
                accepted,
                runtime_contracts,
                app=app,
                out_root=out_root,
                manifest_path=manifest_path,
            )
            if validate_render_diagnostic_cell_scope(args) is not None:
                result = attach_render_diagnostic_runtime_evidence(
                    result,
                    args=args,
                    cell_root=out_root,
                    implementation_identity=args._matrix_implementation_identity,
                )
        except BaseException as exc:  # pragma: no cover - Isaac runtime only.
            primary_error = exc
            primary_traceback = traceback.format_exc(limit=30)
            if app is not None:
                try:
                    import omni.timeline
                    import omni.usd

                    args._last_emergency_discard = (
                        emergency_discard_active_capture_stage(
                            args,
                            context=omni.usd.get_context(),
                            app=app,
                            timeline=omni.timeline.get_timeline_interface(),
                            flush_updates=max(
                                2,
                                int(getattr(args, "camera_warmup_updates", 2)),
                            ),
                        )
                    )
                except BaseException as discard_exc:
                    args._last_emergency_discard = {
                        "emergency_discard_status": "FAIL",
                        "discarded": False,
                        "root_path": getattr(
                            args, "_active_capture_stage_root", None
                        ),
                        "error": f"{type(discard_exc).__name__}:{discard_exc}",
                    }
            result = build_replay_runtime_failure_manifest(
                args,
                accepted,
                exc,
                traceback_text=primary_traceback,
            )
    finally:
        try:
            if result is not None:
                out_root.mkdir(parents=True, exist_ok=True)
                scoped_manifest_path = out_root / "replay_manifest.json"
                if result.get("classification") == "STOP_RUNTIME_ERROR":
                    atomic_write_json(out_root / "replay_failure.json", result)
                    atomic_write_json(scoped_manifest_path, result)
                    if manifest_path != scoped_manifest_path:
                        atomic_write_json(manifest_path, result)
                else:
                    preclose = deepcopy(result)
                    preclose["classification"] = (
                        "RENDER_COMPLETE_PENDING_APPLICATION_CLOSE"
                    )
                    preclose["standalone_final_evidence_authority"] = False
                    preclose["execution_source_end_verification_status"] = (
                        "PENDING_CHILD_PROCESS_EXIT"
                    )
                    preclose.setdefault("runtime_contract", {})[
                        "application_close_status"
                    ] = "PENDING"
                    atomic_write_json(
                        out_root / "replay_preclose_manifest.json",
                        preclose,
                    )
        except BaseException as persist_exc:
            preclose_persist_error = persist_exc
        finally:
            if app is not None:
                try:
                    app.close()
                    application_close_status = "PASS"
                except BaseException as close_exc:  # pragma: no cover - Isaac runtime only.
                    application_close_status = "FAIL"
                    close_traceback = traceback.format_exc(limit=30)
                    if primary_error is None:
                        result = build_replay_runtime_failure_manifest(
                            args,
                            accepted,
                            close_exc,
                            traceback_text=close_traceback,
                        )
                    else:
                        if result is None:
                            raise AssertionError("runtime_failure_result_missing")
                        result["fatal_error"]["secondary_app_close_failure"] = {
                            "type": type(close_exc).__name__,
                            "message": str(close_exc),
                            "traceback": close_traceback,
                        }
                        result["runtime_failure_context"][
                            "application_close_status"
                        ] = "FAIL"
    if preclose_persist_error is not None:
        raise preclose_persist_error
    if result is None:
        raise AssertionError("runtime_result_missing")
    result.setdefault("runtime_contract", {})[
        "application_close_status"
    ] = application_close_status
    if result.get("classification") in {
        "RENDER_COMPLETE_PENDING_VISUAL_REVIEW",
        "DIAGNOSTIC_RENDER_COMPLETE_PENDING_VISUAL_REVIEW",
    }:
        try:
            result["execution_source_verification_after_application_close"] = (
                verify_execution_provenance_sources_unchanged(
                    args._execution_provenance
                )
            )
            runtime_look = validate_effective_replay_look_contract(
                result.get("effective_replay_look_contract")  # type: ignore[arg-type]
            )
            if runtime_look["render_diagnostic_variant_id"] is not None:
                result.update(render_diagnostic_lifecycle_contract())
            else:
                result["standalone_final_evidence_authority"] = True
            result["execution_source_end_verification_status"] = "PASS"
        except BaseException as verification_exc:
            result = build_replay_runtime_failure_manifest(
                args,
                accepted,
                verification_exc,
                traceback_text=traceback.format_exc(limit=30),
            )
            result["runtime_failure_context"][
                "application_close_status"
            ] = application_close_status
            result["runtime_failure_context"][
                "execution_source_verification_after_application_close"
            ] = "FAIL"
    out_root.mkdir(parents=True, exist_ok=True)
    scoped_manifest_path = out_root / "replay_manifest.json"
    if result.get("classification") == "STOP_RUNTIME_ERROR":
        atomic_write_json(out_root / "replay_failure.json", result)
    atomic_write_json(scoped_manifest_path, result)
    if manifest_path != scoped_manifest_path:
        atomic_write_json(manifest_path, result)
    return result


def run_replay(args: argparse.Namespace) -> dict[str, Any]:
    if bool(args.dry_plan):
        raise ValueError("run_replay_does_not_execute_dry_plan")
    if bool(getattr(args, "runtime_child", False)):
        validate_runtime_child_invocation(args)
    args._effective_replay_look_contract = deepcopy(
        _effective_look_contract_from_args(args)
    )
    render_diagnostic_identity = validate_render_diagnostic_cell_scope(args)
    if render_diagnostic_identity is not None:
        cell_root = _reject_symlink_path_components(
            args.out_root,
            label="source_dependency_cell",
        )
        protected_snapshot = (
            load_and_verify_render_diagnostic_pre_freeze_snapshot()
        )
        args._render_diagnostic_protected_snapshot = deepcopy(
            protected_snapshot
        )
        source_dependency_closure = (
            publish_render_diagnostic_source_dependency_snapshot(
                cell_root,
                protected_snapshot=protected_snapshot,
                verify_usd_dependencies=False,
            )
        )
        snapshot_root = (
            cell_root / RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_DIRNAME
        )
        args._source_dependency_closure = deepcopy(
            source_dependency_closure
        )
        args._runtime_source_snapshot_entry = str(
            snapshot_root
            / source_dependency_closure[
                "snapshot_entry_source_usd_path"
            ]
        )
    candidate_ids = _candidate_ids_from_args(args)
    args._execution_provenance = build_execution_provenance(args)
    accepted, matrix_authority = load_replay_inputs_from_args(
        args,
        recompute_closure=False,
    )
    if render_diagnostic_identity is not None:
        if (
            accepted.accepted_authority_bundle_sha256
            != RENDER_DIAGNOSTIC_EXPECTED_AUTHORITY_SHA256
            or accepted.source_usd_sha256
            != RENDER_DIAGNOSTIC_EXPECTED_SOURCE_SHA256
            or accepted.physical_trace_identity.get("physical_trace_sha256")
            != RENDER_DIAGNOSTIC_EXPECTED_TRACE_SHA256
        ):
            raise ValueError("render_diagnostic_established_input_mismatch")
    verify_replay_input_snapshots_unchanged(accepted, matrix_authority)
    contracts = build_candidate_replay_contracts(
        accepted,
        candidate_ids,
        visual_prototype_only=bool(
            getattr(args, "visual_prototype_display_fill_only", False)
        ),
        effective_look_contract=args._effective_replay_look_contract,
    )
    args._camera_contracts_preflight = build_replay_camera_contracts(
        frame=accepted.frame,
        region_config=accepted.summary["region_config"],
        width=int(args.width),
        height=int(args.height),
    )
    out_root, manifest_path = _validate_output_scope(args)
    args._resolved_out_root = str(out_root)
    args._resolved_manifest = str(manifest_path)
    args._matrix_authority_preflight = deepcopy(matrix_authority)
    if render_diagnostic_identity is not None:
        from tools.labutopia_fluid import (
            run_colleague_native_usd_completed_pbd_step_video as native,
        )

        args._preboot_material_closure = deepcopy(
            _mirror_version_matched_mdl_closure(
                native,
                artifact_dir=out_root,
                protected_snapshot=args._render_diagnostic_protected_snapshot,
            )
        )
    return _run_runtime(args, accepted, contracts)


def _persist_render_diagnostic_parent_failure(
    *,
    out_root: Path,
    manifest_path: Path,
    child_command: Sequence[str],
    child_exit_code: int | None,
    failure_stage: str,
    error_type: str,
    error_message: str,
    partial_manifest_path: Path | None,
    render_diagnostic_identity: Mapping[str, Any] | None,
    implementation_identity: Mapping[str, Any] | None,
    launch_intent: Mapping[str, Any] | None,
    reverify_implementation: bool = True,
) -> dict[str, Any]:
    launcher_failure = {
        "schema_version": 1,
        "manifest_type": "real_beaker_omniglass_reference_replay_launcher",
        "generated_at_utc": _utc_now(),
        "classification": "STOP_RUNTIME_ERROR",
        "fatal_error": {
            "type": error_type,
            "message": error_message,
        },
        "child_process_contract": {
            "command": list(child_command),
            "exit_code": child_exit_code,
            "runtime_failure_manifest_observed": False,
            "preclose_manifest_observed": (
                partial_manifest_path is not None
                and partial_manifest_path.name
                == "replay_preclose_manifest.json"
            ),
        },
        "render_artifact_set_complete": False,
        "colleague_delivery_ready": False,
    }
    if render_diagnostic_identity is not None:
        launcher_failure.update(render_diagnostic_lifecycle_contract())
    out_root.mkdir(parents=True, exist_ok=True)
    failure_path = out_root / "replay_failure.json"
    atomic_write_json(failure_path, launcher_failure)
    atomic_write_json(out_root / "replay_manifest.json", launcher_failure)
    if manifest_path != out_root / "replay_manifest.json":
        atomic_write_json(manifest_path, launcher_failure)
    if render_diagnostic_identity is not None:
        if implementation_identity is None or launch_intent is None:
            raise AssertionError("render_diagnostic_failure_contract_missing")
        if reverify_implementation:
            verify_matrix_implementation_identity_unchanged(
                implementation_identity
            )
        failure_evidence = build_render_diagnostic_cell_failure_evidence(
            identity=render_diagnostic_identity,
            implementation_identity=implementation_identity,
            launch_intent=launch_intent,
            classification="STOP_RUNTIME_ERROR",
            child_exit_code=child_exit_code,
            failure_stage=failure_stage,
            error_type=error_type,
            error_message=error_message,
            partial_manifest_path=(
                partial_manifest_path
                if partial_manifest_path is not None
                else failure_path
            ),
        )
        write_render_diagnostic_cell_failure_evidence(
            cell_root=out_root,
            evidence=failure_evidence,
        )
    return launcher_failure


def verify_render_diagnostic_parent_anchor_unchanged(
    *,
    launch_intent: Mapping[str, Any],
    lock_descriptor: int,
) -> dict[str, Any]:
    try:
        root = _reject_symlink_path_components(
            RENDER_DIAGNOSTIC_AGGREGATE_ROOT,
            label="render_diagnostic_parent_anchor_root",
        )
        anchor = validate_render_diagnostic_experiment_anchor(
            _load_json_object(
                root / RENDER_DIAGNOSTIC_ANCHOR_BASENAME,
                label="render_diagnostic_parent_anchor",
            ),
            expected_root=root,
            expected_lock_path=_render_diagnostic_lock_path(),
        )
        lock_stat = os.fstat(lock_descriptor)
        if (
            anchor["anchor_sha256"] != launch_intent.get("anchor_sha256")
            or (lock_stat.st_dev, lock_stat.st_ino)
            != (anchor["lock_device"], anchor["lock_inode"])
        ):
            raise ValueError("anchor_or_lock_mismatch")
        return anchor
    except (OSError, TypeError, ValueError) as exc:
        raise RuntimeError(
            f"render_diagnostic_parent_anchor_changed_after_child:{exc}"
        ) from exc


def run_replay_parent_launcher(
    raw_argv: Sequence[str],
    args: argparse.Namespace,
) -> dict[str, Any]:
    validate_runtime_child_invocation(args)
    render_diagnostic_identity = validate_render_diagnostic_cell_scope(args)
    if render_diagnostic_identity is None:
        return _run_replay_parent_launcher_impl(
            raw_argv,
            args,
            lock_descriptor=None,
        )
    with acquire_render_diagnostic_experiment_lock() as descriptor:
        return _run_replay_parent_launcher_impl(
            raw_argv,
            args,
            lock_descriptor=descriptor,
        )


def _run_replay_parent_launcher_impl(
    raw_argv: Sequence[str],
    args: argparse.Namespace,
    *,
    lock_descriptor: int | None,
) -> dict[str, Any]:
    """Run Kit in a child process and finalize evidence after its clean exit."""
    args._effective_replay_look_contract = deepcopy(
        _effective_look_contract_from_args(args)
    )
    render_diagnostic_identity = validate_render_diagnostic_cell_scope(args)
    out_root, manifest_path = _validate_output_scope(args)
    matrix_implementation_identity: dict[str, Any] | None = None
    launch_intent: dict[str, Any] | None = None
    device_identity: dict[str, Any] | None = None
    runtime_archive_evidence: dict[str, Any] | None = None
    runtime_archive_bytes: bytes | None = None
    runtime_archive_descriptor: int | None = None
    child_command: list[str] = []
    if render_diagnostic_identity is not None:
        pre_freeze_verification = (
            verify_render_diagnostic_pre_freeze_unchanged()
        )
        matrix_implementation_identity = (
            load_and_verify_frozen_matrix_implementation_identity()
        )
        runtime_archive_evidence, runtime_archive_bytes = (
            build_render_diagnostic_runtime_implementation_archive(
                matrix_implementation_identity
            )
        )
        device_identity = build_render_diagnostic_device_identity()
        launch_intent = write_render_diagnostic_launch_intent(
            render_diagnostic_identity,
            implementation_identity_sha256=matrix_implementation_identity[
                "implementation_identity_sha256"
            ],
            expected_implementation_identity=matrix_implementation_identity,
            pre_freeze_sha256=pre_freeze_verification["sha256"],
            launcher_pid=os.getpid(),
            lock_descriptor=lock_descriptor,
        )
        try:
            out_root.mkdir(parents=True, exist_ok=False)
            _write_regular_bytes_create_exclusive(
                out_root / "runtime_implementation_archive.zip",
                runtime_archive_bytes,
            )
            _write_regular_bytes_create_exclusive(
                out_root / "runtime_bootstrap.py",
                RENDER_DIAGNOSTIC_RUNTIME_BOOTSTRAP_SOURCE.encode("utf-8"),
            )
            _fsync_directory(out_root)
            runtime_archive_descriptor = (
                create_render_diagnostic_sealed_archive_fd(
                    runtime_archive_bytes
                )
            )
            args._runtime_implementation_archive = deepcopy(
                runtime_archive_evidence
            )
        except BaseException as exc:
            if runtime_archive_descriptor is not None:
                os.close(runtime_archive_descriptor)
                runtime_archive_descriptor = None
            return _persist_render_diagnostic_parent_failure(
                out_root=out_root,
                manifest_path=manifest_path,
                child_command=child_command,
                child_exit_code=None,
                failure_stage="parent_launcher_pre_spawn_setup",
                error_type=type(exc).__name__,
                error_message=str(exc),
                partial_manifest_path=None,
                render_diagnostic_identity=render_diagnostic_identity,
                implementation_identity=matrix_implementation_identity,
                launch_intent=launch_intent,
            )
    if render_diagnostic_identity is None:
        child_command = [
            str(Path(sys.executable).resolve()),
            str(Path(__file__).resolve()),
            *[str(value) for value in raw_argv],
            "--runtime-child",
            "--runtime-parent-pid",
            str(os.getpid()),
        ]
    else:
        if runtime_archive_evidence is None:
            raise AssertionError("render_diagnostic_runtime_archive_missing")
        child_command = [
            str(Path(sys.executable).resolve()),
            "-I",
            "-S",
            "-c",
            RENDER_DIAGNOSTIC_RUNTIME_BOOTSTRAP_SOURCE,
            *[str(value) for value in raw_argv],
            "--runtime-child",
            "--runtime-parent-pid",
            str(os.getpid()),
            "--runtime-parent-lock-fd",
            str(lock_descriptor),
            "--runtime-parent-archive-fd",
            str(runtime_archive_descriptor),
            "--runtime-parent-archive-sha256",
            runtime_archive_evidence["archive_sha256"],
            "--runtime-bootstrap-sha256",
            RENDER_DIAGNOSTIC_RUNTIME_BOOTSTRAP_SHA256,
        ]
    child_kwargs: dict[str, Any] = {"cwd": REPO_ROOT, "check": False}
    if render_diagnostic_identity is not None:
        if lock_descriptor is None or runtime_archive_descriptor is None:
            raise AssertionError("render_diagnostic_parent_descriptor_missing")
        child_environment = os.environ.copy()
        for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE"):
            child_environment.pop(name, None)
        child_environment.update(
            {
                "PYTHONNOUSERSITE": "1",
                "LABUTOPIA_REPO_ROOT": str(REPO_ROOT),
                "LABUTOPIA_SEALED_RUNTIME": "1",
            }
        )
        child_kwargs.update(
            render_diagnostic_runtime_child_subprocess_kwargs(
                lock_descriptor=lock_descriptor,
                archive_descriptor=runtime_archive_descriptor,
            )
        )
        child_kwargs["env"] = child_environment
    try:
        child = subprocess.run(child_command, **child_kwargs)
    except OSError as exc:
        if render_diagnostic_identity is not None:
            verify_render_diagnostic_parent_anchor_unchanged(
                launch_intent=launch_intent,
                lock_descriptor=lock_descriptor,
            )
        return _persist_render_diagnostic_parent_failure(
            out_root=out_root,
            manifest_path=manifest_path,
            child_command=child_command,
            child_exit_code=None,
            failure_stage="parent_launcher_child_start",
            error_type=type(exc).__name__,
            error_message=str(exc),
            partial_manifest_path=None,
            render_diagnostic_identity=render_diagnostic_identity,
            implementation_identity=matrix_implementation_identity,
            launch_intent=launch_intent,
        )
    finally:
        if runtime_archive_descriptor is not None:
            os.close(runtime_archive_descriptor)
    if render_diagnostic_identity is not None:
        verify_render_diagnostic_parent_anchor_unchanged(
            launch_intent=launch_intent,
            lock_descriptor=lock_descriptor,
        )
        try:
            verify_render_diagnostic_pre_freeze_unchanged()
            load_and_verify_frozen_matrix_implementation_identity()
        except BaseException as exc:
            return _persist_render_diagnostic_parent_failure(
                out_root=out_root,
                manifest_path=manifest_path,
                child_command=child_command,
                child_exit_code=int(child.returncode),
                failure_stage="parent_launcher_post_child_freeze_verification",
                error_type=type(exc).__name__,
                error_message=str(exc),
                partial_manifest_path=(
                    out_root / "replay_preclose_manifest.json"
                    if (out_root / "replay_preclose_manifest.json").is_file()
                    else (
                        out_root / "replay_failure.json"
                        if (out_root / "replay_failure.json").is_file()
                        else None
                    )
                ),
                render_diagnostic_identity=render_diagnostic_identity,
                implementation_identity=matrix_implementation_identity,
                launch_intent=launch_intent,
                reverify_implementation=False,
            )
    failure_path = out_root / "replay_failure.json"
    preclose_path = out_root / "replay_preclose_manifest.json"
    if failure_path.is_file():
        failure = _load_json_object(failure_path, label="replay_failure")
        if failure.get("classification") != "STOP_RUNTIME_ERROR":
            raise RuntimeError("child_failure_manifest_classification_invalid")
        failure["child_process_contract"] = {
            "command": child_command,
            "exit_code": int(child.returncode),
            "runtime_failure_manifest_observed": True,
            "clean_exit_does_not_override_runtime_failure": True,
        }
        atomic_write_json(failure_path, failure)
        atomic_write_json(out_root / "replay_manifest.json", failure)
        if manifest_path != out_root / "replay_manifest.json":
            atomic_write_json(manifest_path, failure)
        if render_diagnostic_identity is not None:
            if matrix_implementation_identity is None or launch_intent is None:
                raise AssertionError("render_diagnostic_failure_contract_missing")
            verify_matrix_implementation_identity_unchanged(
                matrix_implementation_identity
            )
            fatal = failure.get("fatal_error") or {}
            failure_evidence = build_render_diagnostic_cell_failure_evidence(
                identity=render_diagnostic_identity,
                implementation_identity=matrix_implementation_identity,
                launch_intent=launch_intent,
                classification=str(failure["classification"]),
                child_exit_code=int(child.returncode),
                failure_stage="runtime_child",
                error_type=str(fatal.get("type", "RuntimeFailure")),
                error_message=str(fatal.get("message", "runtime child failed")),
                partial_manifest_path=failure_path,
            )
            write_render_diagnostic_cell_failure_evidence(
                cell_root=out_root,
                evidence=failure_evidence,
            )
        return failure
    if preclose_path.is_file():
        if int(child.returncode) != 0:
            return _persist_render_diagnostic_parent_failure(
                out_root=out_root,
                manifest_path=manifest_path,
                child_command=child_command,
                child_exit_code=int(child.returncode),
                failure_stage="parent_launcher_nonzero_after_preclose",
                error_type="ChildProcessNonzeroAfterPreclose",
                error_message=(
                    "Kit child wrote a preclose manifest but exited "
                    f"with code {int(child.returncode)}"
                ),
                partial_manifest_path=preclose_path,
                render_diagnostic_identity=render_diagnostic_identity,
                implementation_identity=matrix_implementation_identity,
                launch_intent=launch_intent,
            )
        try:
            finalized = finalize_preclose_manifest_after_child_exit(
                preclose_path,
                child_exit_code=int(child.returncode),
                manifest_path=manifest_path,
            )
        except BaseException as exc:
            return _persist_render_diagnostic_parent_failure(
                out_root=out_root,
                manifest_path=manifest_path,
                child_command=child_command,
                child_exit_code=int(child.returncode),
                failure_stage="parent_launcher_finalization",
                error_type=type(exc).__name__,
                error_message=str(exc),
                partial_manifest_path=preclose_path,
                render_diagnostic_identity=render_diagnostic_identity,
                implementation_identity=matrix_implementation_identity,
                launch_intent=launch_intent,
            )
        if render_diagnostic_identity is not None:
            try:
                if (
                    matrix_implementation_identity is None
                    or launch_intent is None
                    or device_identity is None
                ):
                    raise AssertionError(
                        "render_diagnostic_parent_contract_missing"
                    )
                verify_matrix_implementation_identity_unchanged(
                    matrix_implementation_identity
                )
                child_pid = finalized.get("runtime_contract", {}).get(
                    "runtime_child_pid"
                )
                sidecars = build_render_diagnostic_cell_sidecar_payloads(
                    final_manifest=finalized,
                    identity=render_diagnostic_identity,
                    implementation_identity=matrix_implementation_identity,
                    launch_intent=launch_intent,
                    launcher_pid=os.getpid(),
                    child_pid=child_pid,
                    device_identity=device_identity,
                )
                written_sidecars = write_render_diagnostic_cell_sidecars(
                    cell_root=out_root,
                    sidecars=sidecars,
                )
                finalized["render_diagnostic_launch_intent"] = deepcopy(
                    launch_intent
                )
                finalized["matrix_implementation_identity"] = deepcopy(
                    matrix_implementation_identity
                )
                finalized["matrix_sidecars"] = written_sidecars
                finalized["matrix_cell_evidence_sha256"] = sidecars[
                    "cell_evidence"
                ]["matrix_cell_evidence_sha256"]
                finalized["standalone_final_evidence_authority"] = False
                atomic_write_json(out_root / "replay_manifest.json", finalized)
                if manifest_path != out_root / "replay_manifest.json":
                    atomic_write_json(manifest_path, finalized)
            except BaseException as exc:
                return _persist_render_diagnostic_parent_failure(
                    out_root=out_root,
                    manifest_path=manifest_path,
                    child_command=child_command,
                    child_exit_code=int(child.returncode),
                    failure_stage="parent_launcher_sidecar_finalization",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    partial_manifest_path=preclose_path,
                    render_diagnostic_identity=render_diagnostic_identity,
                    implementation_identity=matrix_implementation_identity,
                    launch_intent=launch_intent,
                )
        return finalized
    launcher_failure = {
        "schema_version": 1,
        "manifest_type": "real_beaker_omniglass_reference_replay_launcher",
        "generated_at_utc": _utc_now(),
        "classification": "STOP_RUNTIME_ERROR",
        "fatal_error": {
            "type": "ChildProcessEvidenceMissing",
            "message": (
                "Kit child produced neither replay_failure.json nor "
                "replay_preclose_manifest.json"
            ),
        },
        "child_process_contract": {
            "command": child_command,
            "exit_code": int(child.returncode),
            "runtime_failure_manifest_observed": False,
            "preclose_manifest_observed": False,
        },
        "render_artifact_set_complete": False,
        "colleague_delivery_ready": False,
    }
    out_root.mkdir(parents=True, exist_ok=True)
    atomic_write_json(failure_path, launcher_failure)
    atomic_write_json(out_root / "replay_manifest.json", launcher_failure)
    if manifest_path != out_root / "replay_manifest.json":
        atomic_write_json(manifest_path, launcher_failure)
    if render_diagnostic_identity is not None:
        if matrix_implementation_identity is None or launch_intent is None:
            raise AssertionError("render_diagnostic_failure_contract_missing")
        verify_matrix_implementation_identity_unchanged(
            matrix_implementation_identity
        )
        failure_evidence = build_render_diagnostic_cell_failure_evidence(
            identity=render_diagnostic_identity,
            implementation_identity=matrix_implementation_identity,
            launch_intent=launch_intent,
            classification="STOP_RUNTIME_ERROR",
            child_exit_code=int(child.returncode),
            failure_stage="parent_launcher_missing_child_evidence",
            error_type="ChildProcessEvidenceMissing",
            error_message=str(launcher_failure["fatal_error"]["message"]),
            partial_manifest_path=failure_path,
        )
        write_render_diagnostic_cell_failure_evidence(
            cell_root=out_root,
            evidence=failure_evidence,
        )
    return launcher_failure


def _build_render_diagnostic_authority_publication_intent(
    *,
    aggregate_root: Path,
    publication_nonce: str,
    generated_at_utc: str,
) -> dict[str, Any]:
    if (
        len(publication_nonce) != 64
        or any(character not in "0123456789abcdef" for character in publication_nonce)
    ):
        raise ValueError("authority_publication_nonce_invalid")
    authority_path = (
        aggregate_root / RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME
    )
    staging_path = aggregate_root / (
        f".{RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME}."
        f"{publication_nonce}.staging"
    )
    payload = {
        "schema_version": 1,
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "authority_path": str(authority_path),
        "staging_path": str(staging_path),
        "publication_nonce": publication_nonce,
        "generated_at_utc": generated_at_utc,
    }
    hash_payload = {
        key: value for key, value in payload.items() if key != "generated_at_utc"
    }
    return {
        **payload,
        "publication_intent_sha256": canonical_json_sha256_v1(hash_payload),
    }


def _write_render_diagnostic_authority_journal(
    aggregate_root: Path,
    intent: Mapping[str, Any],
) -> Path:
    nonce = str(intent["publication_nonce"])
    temporary = aggregate_root / f".authority_publication_intent.{nonce}.tmp"
    fixed = aggregate_root / RENDER_DIAGNOSTIC_AUTHORITY_JOURNAL_BASENAME
    _write_json_create_exclusive(temporary, intent)
    _fsync_directory(aggregate_root)
    try:
        os.link(temporary, fixed, follow_symlinks=False)
        _fsync_directory(aggregate_root)
    except BaseException:
        if temporary.exists():
            temporary.unlink()
            _fsync_directory(aggregate_root)
        raise
    temporary.unlink()
    _fsync_directory(aggregate_root)
    return fixed


def _cleanup_pre_witness_decision_authority_staging(
    *,
    aggregate_root: Path,
    staging: Path,
    journal_path: Path,
    intent: Mapping[str, Any],
) -> None:
    if staging.is_symlink() or not staging.is_dir():
        raise ValueError("decision_authority_cleanup_staging_invalid")
    if _load_json_object(
        staging / "publication_intent.json",
        label="decision_authority_cleanup_embedded_intent",
    ) != _json_native_copy(dict(intent)):
        raise ValueError("decision_authority_cleanup_embedded_intent_mismatch")
    if journal_path.is_symlink() or not journal_path.is_file():
        raise ValueError("decision_authority_cleanup_journal_invalid")
    if _load_json_object(
        journal_path,
        label="decision_authority_cleanup_journal",
    ) != _json_native_copy(dict(intent)):
        raise ValueError("decision_authority_cleanup_journal_mismatch")
    _root, records = _snapshot_pinned_regular_tree(
        staging,
        label="decision_authority_cleanup_staging",
    )
    fixed_files = {
        "publication_intent.json",
        "matrix_decision.json",
        "decision_commit.json",
    }
    for record in records:
        relative = record["path"]
        if relative not in fixed_files and not (
            relative.startswith("final_closure/aggregate/")
            or relative.startswith("final_closure/external/")
            or relative == "final_closure/closure_manifest.json"
        ):
            raise ValueError(
                f"decision_authority_cleanup_unknown_member:{relative}"
            )
        metadata = os.lstat(staging / relative)
        if metadata.st_nlink != 1:
            raise ValueError(
                f"decision_authority_cleanup_link_count_invalid:{relative}"
            )
    for directory in sorted(
        [staging, *[path for path in staging.rglob("*") if path.is_dir()]],
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        if directory.is_symlink():
            raise ValueError("decision_authority_cleanup_symlink_invalid")
        directory.chmod(0o700)
    shutil.rmtree(staging)
    journal_path.unlink()
    _fsync_directory(aggregate_root)


def _build_render_diagnostic_decision_commit(
    *,
    decision: Mapping[str, Any],
    anchor: Mapping[str, Any],
    intent: Mapping[str, Any],
    authority_stat: os.stat_result,
    closure_snapshot_sha256: str | None,
    generated_at_utc: str,
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "authority_path": intent["authority_path"],
        "authority_device": authority_stat.st_dev,
        "authority_inode": authority_stat.st_ino,
        "decision_sha256": canonical_json_sha256_v1(decision),
        "anchor_sha256": anchor["anchor_sha256"],
        "closure_snapshot_sha256": closure_snapshot_sha256,
        "publication_intent_sha256": intent["publication_intent_sha256"],
        "publication_nonce": intent["publication_nonce"],
        "generated_at_utc": generated_at_utc,
    }
    hash_payload = {
        key: value for key, value in payload.items() if key != "generated_at_utc"
    }
    return {
        **payload,
        "decision_commit_sha256": canonical_json_sha256_v1(hash_payload),
    }


def _build_render_diagnostic_authority_witness(
    *,
    anchor: Mapping[str, Any],
    intent: Mapping[str, Any],
    commit: Mapping[str, Any],
    generated_at_utc: str,
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "record_type": "AUTHORITY_WITNESS",
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "experiment_binding_sha256": anchor["experiment_binding_sha256"],
        "authority_path": intent["authority_path"],
        "authority_device": commit["authority_device"],
        "authority_inode": commit["authority_inode"],
        "lock_device": anchor["lock_device"],
        "lock_inode": anchor["lock_inode"],
        "publication_intent_sha256": intent["publication_intent_sha256"],
        "decision_sha256": commit["decision_sha256"],
        "decision_commit_sha256": commit["decision_commit_sha256"],
        "closure_snapshot_sha256": commit["closure_snapshot_sha256"],
        "publication_nonce": intent["publication_nonce"],
        "generated_at_utc": generated_at_utc,
    }
    hash_payload = {
        key: value for key, value in payload.items() if key != "generated_at_utc"
    }
    return {
        **payload,
        "authority_witness_sha256": canonical_json_sha256_v1(hash_payload),
    }


def _append_render_diagnostic_authority_witness(
    lock_descriptor: int,
    *,
    anchor: Mapping[str, Any],
    witness: Mapping[str, Any],
) -> None:
    state = validate_render_diagnostic_lock_journal(
        lock_descriptor,
        anchor=anchor,
        authority_required=False,
    )
    offset = state["byte_count"]
    encoded = _compact_json_line(witness)
    if os.pwrite(lock_descriptor, encoded, offset) != len(encoded):
        raise OSError("authority_witness_short_write")
    os.fsync(lock_descriptor)
    validate_render_diagnostic_lock_journal(
        lock_descriptor,
        anchor=anchor,
        authority_required=True,
    )


def validate_render_diagnostic_decision_authority(
    *,
    aggregate_root: str | os.PathLike[str],
    anchor: Mapping[str, Any],
    lock: int | str | os.PathLike[str],
    semantic_validator: Any | None = None,
) -> dict[str, Any]:
    root = _reject_symlink_path_components(
        aggregate_root,
        label="decision_authority_aggregate_root",
    )
    authority = _reject_symlink_path_components(
        root / RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME,
        label="decision_authority_root",
    )
    if not authority.is_dir() or authority.is_symlink():
        raise ValueError("decision_authority_missing")
    names = {path.name for path in authority.iterdir()}
    required = {
        "matrix_decision.json",
        "decision_commit.json",
        "publication_intent.json",
    }
    has_closure = "final_closure" in names
    if names != required | ({"final_closure"} if has_closure else set()):
        raise ValueError("decision_authority_membership_invalid")
    intent = _load_json_object(
        authority / "publication_intent.json",
        label="decision_authority_intent",
    )
    external_intent = _load_json_object(
        root / RENDER_DIAGNOSTIC_AUTHORITY_JOURNAL_BASENAME,
        label="decision_authority_external_intent",
    )
    if intent != external_intent:
        raise ValueError("decision_authority_intent_mismatch")
    expected_intent = _build_render_diagnostic_authority_publication_intent(
        aggregate_root=root,
        publication_nonce=str(intent.get("publication_nonce", "")),
        generated_at_utc=str(intent.get("generated_at_utc", "")),
    )
    if intent != expected_intent:
        raise ValueError("decision_authority_intent_invalid")
    decision = _load_json_object(
        authority / "matrix_decision.json",
        label="decision_authority_decision",
    )
    commit = _load_json_object(
        authority / "decision_commit.json",
        label="decision_authority_commit",
    )
    authority_stat = os.stat(authority, follow_symlinks=False)
    closure_hash = None
    if has_closure:
        closure_hash = validate_render_diagnostic_final_closure_snapshot(
            authority / "final_closure"
        )["closure_snapshot_sha256"]
    expected_commit = _build_render_diagnostic_decision_commit(
        decision=decision,
        anchor=anchor,
        intent=intent,
        authority_stat=authority_stat,
        closure_snapshot_sha256=closure_hash,
        generated_at_utc=str(commit.get("generated_at_utc", "")),
    )
    if commit != expected_commit:
        raise ValueError("decision_authority_commit_invalid")
    journal = validate_render_diagnostic_lock_journal(
        lock,
        anchor=anchor,
        authority_required=True,
    )
    expected_witness = _build_render_diagnostic_authority_witness(
        anchor=anchor,
        intent=intent,
        commit=commit,
        generated_at_utc=str(
            journal["authority_witness"].get("generated_at_utc", "")
        ),
    )
    if journal["authority_witness"] != expected_witness:
        raise ValueError("decision_authority_witness_mismatch")
    if semantic_validator is not None:
        semantic_validator(
            decision,
            authority / "final_closure" if has_closure else None,
            None,
        )
    _validate_pinned_readonly_tree_modes(
        authority,
        label="decision_authority",
    )
    return {
        "decision": decision,
        "decision_commit": commit,
        "publication_intent": intent,
        "authority_witness": expected_witness,
        "closure_snapshot_sha256": closure_hash,
    }


def _finish_post_witness_decision_authority_recovery(
    *,
    root: Path,
    anchor: Mapping[str, Any],
    lock_descriptor: int,
    intent: Mapping[str, Any],
    requested_decision: Mapping[str, Any] | None,
    closure_expected: bool,
    publication_guard: Any | None,
    semantic_validator: Any | None,
) -> dict[str, Any]:
    staging = _reject_symlink_path_components(
        str(intent["staging_path"]),
        label="decision_authority_recovery_staging",
    )
    if not staging.is_dir() or staging.is_symlink():
        raise ValueError("decision_authority_recovery_staging_missing")
    names = {path.name for path in staging.iterdir()}
    required = {
        "matrix_decision.json",
        "decision_commit.json",
        "publication_intent.json",
    }
    has_closure = "final_closure" in names
    if (
        has_closure != closure_expected
        or names != required | ({"final_closure"} if has_closure else set())
    ):
        raise ValueError("decision_authority_recovery_membership_invalid")
    embedded_intent = _load_json_object(
        staging / "publication_intent.json",
        label="decision_authority_recovery_embedded_intent",
    )
    if embedded_intent != _json_native_copy(dict(intent)):
        raise ValueError("decision_authority_recovery_intent_mismatch")
    decision = _load_json_object(
        staging / "matrix_decision.json",
        label="decision_authority_recovery_decision",
    )
    if requested_decision is not None and decision != _json_native_copy(
        dict(requested_decision)
    ):
        raise ValueError("decision_authority_recovery_decision_mismatch")
    commit = _load_json_object(
        staging / "decision_commit.json",
        label="decision_authority_recovery_commit",
    )
    closure_hash = None
    if has_closure:
        closure_hash = validate_render_diagnostic_final_closure_snapshot(
            staging / "final_closure"
        )["closure_snapshot_sha256"]
    expected_commit = _build_render_diagnostic_decision_commit(
        decision=decision,
        anchor=anchor,
        intent=intent,
        authority_stat=os.stat(staging, follow_symlinks=False),
        closure_snapshot_sha256=closure_hash,
        generated_at_utc=str(commit.get("generated_at_utc", "")),
    )
    if commit != expected_commit:
        raise ValueError("decision_authority_recovery_commit_invalid")
    journal = validate_render_diagnostic_lock_journal(
        lock_descriptor,
        anchor=anchor,
        authority_required=True,
    )
    witness = _build_render_diagnostic_authority_witness(
        anchor=anchor,
        intent=intent,
        commit=commit,
        generated_at_utc=str(
            journal["authority_witness"].get("generated_at_utc", "")
        ),
    )
    if journal["authority_witness"] != witness:
        raise ValueError("decision_authority_recovery_witness_mismatch")
    _validate_pinned_readonly_tree_modes(
        staging,
        label="decision_authority_recovery_staging",
    )
    if semantic_validator is not None:
        semantic_validator(
            decision,
            staging / "final_closure" if has_closure else None,
            staging,
        )
    _before_root, before_records = _snapshot_pinned_regular_tree(
        staging,
        label="decision_authority_recovery_staging",
    )
    if publication_guard is not None:
        publication_guard()
    _after_root, after_records = _snapshot_pinned_regular_tree(
        staging,
        label="decision_authority_recovery_staging",
    )
    if before_records != after_records:
        raise RuntimeError("decision_authority_recovery_staging_changed")
    authority = root / RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME
    _atomic_rename_noreplace(staging, authority)
    _fsync_directory(root)
    return validate_render_diagnostic_decision_authority(
        aggregate_root=root,
        anchor=anchor,
        lock=lock_descriptor,
    )


def publish_render_diagnostic_decision_authority(
    *,
    aggregate_root: str | os.PathLike[str],
    decision: Mapping[str, Any] | None,
    anchor: Mapping[str, Any],
    lock_descriptor: int,
    closure_root: str | os.PathLike[str] | None,
    closure_external_files: Mapping[str, str | os.PathLike[str]] | None = None,
    decision_builder: Any | None = None,
    publication_nonce: str | None = None,
    generated_at_utc: str | None = None,
    publication_guard: Any | None = None,
    semantic_validator: Any | None = None,
) -> dict[str, Any]:
    root = _reject_symlink_path_components(
        aggregate_root,
        label="decision_authority_aggregate_root",
    )
    validated_anchor = validate_render_diagnostic_experiment_anchor(
        anchor,
        expected_root=root,
        expected_lock_path=_render_diagnostic_lock_path(),
    )
    authority = root / RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME
    if (decision is None) == (decision_builder is None):
        raise ValueError("decision_authority_decision_mode_invalid")
    if authority.is_dir() and not authority.is_symlink():
        return validate_render_diagnostic_decision_authority(
            aggregate_root=root,
            anchor=validated_anchor,
            lock=lock_descriptor,
            semantic_validator=semantic_validator,
        )
    if authority.exists() or authority.is_symlink():
        raise ValueError("decision_authority_path_invalid")
    journal_path = root / RENDER_DIAGNOSTIC_AUTHORITY_JOURNAL_BASENAME
    if journal_path.exists() or journal_path.is_symlink():
        recovered_intent = _load_json_object(
            journal_path,
            label="decision_authority_recovery_intent",
        )
        expected_recovered_intent = (
            _build_render_diagnostic_authority_publication_intent(
                aggregate_root=root,
                publication_nonce=str(
                    recovered_intent.get("publication_nonce", "")
                ),
                generated_at_utc=str(
                    recovered_intent.get("generated_at_utc", "")
                ),
            )
        )
        if recovered_intent != expected_recovered_intent:
            raise ValueError("decision_authority_recovery_intent_invalid")
        if (
            publication_nonce is not None
            and publication_nonce != recovered_intent["publication_nonce"]
        ) or (
            generated_at_utc is not None
            and generated_at_utc != recovered_intent["generated_at_utc"]
        ):
            raise ValueError("decision_authority_recovery_request_mismatch")
        lock_bytes = os.pread(
            lock_descriptor,
            os.fstat(lock_descriptor).st_size,
            0,
        )
        lock_record_count = lock_bytes.count(b"\n")
        if lock_record_count == 2:
            return _finish_post_witness_decision_authority_recovery(
                root=root,
                anchor=validated_anchor,
                lock_descriptor=lock_descriptor,
                intent=recovered_intent,
                requested_decision=decision,
                closure_expected=(
                    closure_root is not None
                    or closure_external_files is not None
                ),
                publication_guard=publication_guard,
                semantic_validator=semantic_validator,
            )
        if lock_record_count != 1:
            raise ValueError("decision_authority_recovery_lock_poisoned")
        validate_render_diagnostic_lock_journal(
            lock_descriptor,
            anchor=validated_anchor,
            authority_required=False,
        )
        recovered_staging = Path(recovered_intent["staging_path"])
        _cleanup_pre_witness_decision_authority_staging(
            aggregate_root=root,
            staging=recovered_staging,
            journal_path=journal_path,
            intent=recovered_intent,
        )
    elif any(
        entry.name.startswith(
            f".{RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME}."
        )
        and entry.name.endswith(".staging")
        for entry in root.iterdir()
    ):
        raise ValueError("decision_authority_orphan_staging")
    nonce = publication_nonce or secrets.token_hex(32)
    generated = generated_at_utc or _utc_now()
    intent = _build_render_diagnostic_authority_publication_intent(
        aggregate_root=root,
        publication_nonce=nonce,
        generated_at_utc=generated,
    )
    staging = Path(intent["staging_path"])
    if (
        staging.exists()
        or staging.is_symlink()
        or journal_path.exists()
        or journal_path.is_symlink()
    ):
        raise ValueError("decision_authority_preexisting_partial_state")
    staging.mkdir(mode=0o700)
    _fsync_directory(root)
    _write_json_create_exclusive(staging / "publication_intent.json", intent)
    _fsync_directory(staging)
    _write_render_diagnostic_authority_journal(root, intent)
    if closure_root is not None and closure_external_files is not None:
        raise ValueError("decision_authority_closure_mode_ambiguous")
    closure_hash = None
    if closure_external_files is not None:
        closure = staging / "final_closure"
        closure_manifest = create_render_diagnostic_final_closure_snapshot(
            aggregate_root=root,
            external_files=closure_external_files,
            closure_root_override=closure,
            excluded_aggregate_prefixes=(
                staging.name,
                RENDER_DIAGNOSTIC_AUTHORITY_JOURNAL_BASENAME,
            ),
        )
        closure_hash = closure_manifest["closure_snapshot_sha256"]
    elif closure_root is not None:
        closure = _reject_symlink_path_components(
            closure_root,
            label="decision_authority_closure",
        )
        if closure != staging / "final_closure":
            raise ValueError("decision_authority_closure_location_invalid")
        closure_hash = validate_render_diagnostic_final_closure_snapshot(
            closure
        )["closure_snapshot_sha256"]
    resolved_decision = (
        decision_builder(closure_hash)
        if decision_builder is not None
        else decision
    )
    if not isinstance(resolved_decision, Mapping):
        raise ValueError("decision_authority_decision_invalid")
    resolved_decision = _json_native_copy(dict(resolved_decision))
    _write_json_create_exclusive(
        staging / "matrix_decision.json",
        resolved_decision,
    )
    staging_stat = os.stat(staging, follow_symlinks=False)
    commit = _build_render_diagnostic_decision_commit(
        decision=resolved_decision,
        anchor=validated_anchor,
        intent=intent,
        authority_stat=staging_stat,
        closure_snapshot_sha256=closure_hash,
        generated_at_utc=generated,
    )
    _write_json_create_exclusive(staging / "decision_commit.json", commit)
    _fsync_directory(staging)
    if semantic_validator is not None:
        try:
            semantic_validator(
                resolved_decision,
                staging / "final_closure" if closure_hash is not None else None,
                staging,
            )
        except BaseException:
            _cleanup_pre_witness_decision_authority_staging(
                aggregate_root=root,
                staging=staging,
                journal_path=journal_path,
                intent=intent,
            )
            raise
    if publication_guard is not None:
        publication_guard()
    _before_root, before_records = _snapshot_pinned_regular_tree(
        staging,
        label="decision_authority_staging",
    )
    for path in staging.rglob("*"):
        if path.is_file():
            path.chmod(0o444)
    for directory in sorted(
        [path for path in staging.rglob("*") if path.is_dir()],
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        _fsync_directory(directory)
        directory.chmod(0o555)
    _fsync_directory(staging)
    staging.chmod(0o555)
    witness = _build_render_diagnostic_authority_witness(
        anchor=validated_anchor,
        intent=intent,
        commit=commit,
        generated_at_utc=generated,
    )
    _append_render_diagnostic_authority_witness(
        lock_descriptor,
        anchor=validated_anchor,
        witness=witness,
    )
    if publication_guard is not None:
        publication_guard()
    _after_root, after_records = _snapshot_pinned_regular_tree(
        staging,
        label="decision_authority_staging",
    )
    if before_records != after_records:
        raise RuntimeError("decision_authority_staging_changed_after_witness")
    _atomic_rename_noreplace(staging, authority)
    _fsync_directory(root)
    return validate_render_diagnostic_decision_authority(
        aggregate_root=root,
        anchor=validated_anchor,
        lock=lock_descriptor,
    )


def _render_diagnostic_unexpected_paths(
    root: Path,
    *,
    authority_publication_staging_root: str | os.PathLike[str] | None = None,
) -> list[str]:
    unexpected = []
    expected_top_level = {
        RENDER_DIAGNOSTIC_ANCHOR_BASENAME: "file",
        "cells": "directory",
        "launch_intents": "directory",
        "evidence": "directory",
        "review": "directory",
        RENDER_DIAGNOSTIC_POST_SEAL_BASENAME: "file",
        RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME: "directory",
        RENDER_DIAGNOSTIC_AUTHORITY_JOURNAL_BASENAME: "file",
    }
    if authority_publication_staging_root is not None:
        staging = _absolute_path_without_symlink_resolution(
            authority_publication_staging_root
        )
        prefix = f".{RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME}."
        suffix = ".staging"
        nonce = staging.name[len(prefix) : -len(suffix)]
        if (
            staging.parent != root
            or not staging.name.startswith(prefix)
            or not staging.name.endswith(suffix)
            or len(nonce) != 64
            or any(character not in "0123456789abcdef" for character in nonce)
            or staging.is_symlink()
            or not staging.is_dir()
        ):
            raise ValueError("render_diagnostic_authority_staging_scope_invalid")
        expected_top_level[staging.name] = "directory"
    top_before = _pinned_directory_entries(
        root,
        label="render_diagnostic_membership_root",
    )
    top_by_name = {entry["name"]: entry["kind"] for entry in top_before}
    for entry in top_before:
        expected_kind = expected_top_level.get(entry["name"])
        if expected_kind is None or entry["kind"] != expected_kind:
            unexpected.append(str(root / entry["name"]))
    expected_cells = {slot["cell_name"] for slot in render_diagnostic_slots()}
    expected_intents = {f"{name}.json" for name in expected_cells}
    for directory, allowed in (
        (root / "cells", expected_cells),
        (root / "launch_intents", expected_intents),
    ):
        directory_kind = top_by_name.get(directory.name)
        if directory_kind is None:
            continue
        if directory_kind != "directory":
            unexpected.append(str(directory))
            continue
        for entry in _pinned_directory_entries(
            directory,
            label=f"render_diagnostic_membership_{directory.name}",
        ):
            if entry["name"] not in allowed or (
                directory.name == "cells" and entry["kind"] != "directory"
            ) or (
                directory.name == "launch_intents" and entry["kind"] != "file"
            ):
                unexpected.append(str(directory / entry["name"]))
    top_after = _pinned_directory_entries(
        root,
        label="render_diagnostic_membership_root",
    )
    if top_after != top_before:
        raise ValueError("render_diagnostic_membership_changed")
    return sorted(set(unexpected))


def build_render_diagnostic_machine_verification(
    aggregate_root: str | os.PathLike[str],
    *,
    expected_implementation_identity: Mapping[str, Any] | None = None,
    expected_pre_freeze_sha256: str | None = None,
    authority_publication_staging_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    root = _reject_symlink_path_components(
        aggregate_root,
        label="render_diagnostic_machine_root",
    )
    status_index = build_render_diagnostic_cell_status_index(
        root,
        expected_implementation_identity=expected_implementation_identity,
        expected_pre_freeze_sha256=expected_pre_freeze_sha256,
    )
    launch_chain = None
    if (
        expected_implementation_identity is not None
        and expected_pre_freeze_sha256 is not None
    ):
        anchor = validate_render_diagnostic_experiment_anchor(
            _load_json_object(
                root / RENDER_DIAGNOSTIC_ANCHOR_BASENAME,
                label="render_diagnostic_machine_anchor",
            ),
            expected_root=root,
            expected_lock_path=_render_diagnostic_lock_path(),
        )
        launch_chain = validate_render_diagnostic_launch_chain(
            aggregate_root=root,
            anchor_sha256=anchor["anchor_sha256"],
            expected_implementation_identity_sha256=(
                expected_implementation_identity[
                    "implementation_identity_sha256"
                ]
            ),
            expected_pre_freeze_sha256=expected_pre_freeze_sha256,
            cell_status_index=status_index,
            require_artifact_closure=True,
            expected_implementation_identity=expected_implementation_identity,
        )
    unexpected_paths = _render_diagnostic_unexpected_paths(
        root,
        authority_publication_staging_root=authority_publication_staging_root,
    )
    statuses = [record["status"] for record in status_index["cells"]]
    launched_failure = any(
        status in {"LAUNCHED_EVIDENCE_MISSING", "FAILED"}
        for status in statuses
    )
    successful_evidence = []
    for record in status_index["cells"]:
        if record["status"] == "SUCCESS":
            successful_evidence.append(
                validate_render_diagnostic_matrix_cell_evidence(
                    _load_json_object(
                        Path(record["cell_evidence_path"]),
                        label="matrix_cell_evidence",
                    )
                )
            )
    matrix_validation = validate_render_diagnostic_matrix_closure(
        successful_evidence
    )
    if unexpected_paths:
        matrix_validation = deepcopy(matrix_validation)
        matrix_validation["status"] = "FAIL"
        matrix_validation["unexpected_paths"] = unexpected_paths
        payload = {
            key: value
            for key, value in matrix_validation.items()
            if key != "matrix_validation_evidence_sha256"
        }
        matrix_validation["matrix_validation_evidence_sha256"] = (
            canonical_json_sha256_v1(payload)
        )
    image_lookup: dict[tuple[str, str, str, int], str] = {}
    repeat_stability: dict[str, Any]
    if matrix_validation["status"] == "PASS":
        by_slot = {
            (cell["variant"], cell["replicate"]): cell
            for cell in successful_evidence
        }
        for variant in RENDER_DIAGNOSTIC_VARIANTS:
            for replicate in RENDER_DIAGNOSTIC_REPLICATES:
                cell = by_slot[(variant, replicate)]
                media_path = Path(cell["cell_root"]) / "matrix_media_index.json"
                media = _load_json_object(media_path, label="matrix_media_index")
                if media.get("media_index_sha256") != cell["media_index_sha256"]:
                    raise ValueError("matrix_media_index_hash_mismatch")
                for image_record in media.get("images", []):
                    key = (
                        variant,
                        replicate,
                        image_record.get("camera"),
                        image_record.get("frame"),
                    )
                    if (
                        key[2] in RENDER_DIAGNOSTIC_REVIEW_VIEWS
                        and key[3] in RENDER_DIAGNOSTIC_REVIEW_FRAMES
                    ):
                        image_lookup[key] = image_record["path"]
        repeat_stability = compute_render_diagnostic_repeat_stability(
            image_lookup
        )
    else:
        payload = {
            "schema_version": 1,
            "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
            "status": "NOT_REACHED",
            "thresholds": {"rgb_mae_max": 5.0, "psnr_db_min": 30.0},
            "comparisons": [],
        }
        repeat_stability = {
            **payload,
            "repeat_stability_evidence_sha256": canonical_json_sha256_v1(
                payload
            ),
        }
    return {
        "schema_version": 1,
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "cell_status_index": status_index,
        "cell_status_index_sha256": canonical_json_sha256_v1(status_index),
        "launch_chain": launch_chain,
        "all_launched_cells_successful": not launched_failure,
        "all_sixteen_cells_successful": all(
            status == "SUCCESS" for status in statuses
        ),
        "successful_cell_evidence": successful_evidence,
        "matrix_validation": matrix_validation,
        "repeat_stability": repeat_stability,
        "image_lookup": image_lookup,
    }


def _render_diagnostic_descriptive_contrasts(
    image_lookup: Mapping[tuple[str, str, str, int], str],
    configuration_gates: Mapping[str, str],
) -> list[dict[str, Any]]:
    import numpy as np
    from PIL import Image

    metric_cell_values: dict[str, dict[str, float]] = {
        "visual_pass_indicator": {
            variant: 1.0 if configuration_gates[variant] == "PASS" else 0.0
            for variant in RENDER_DIAGNOSTIC_VARIANTS
        }
    }
    metric_names = (
        "full_rgb_mean_u8",
        "cyan_channel_excess_u8",
        "rec709_luminance_u8",
    )
    for metric in metric_names:
        metric_cell_values[metric] = {}
    for variant in RENDER_DIAGNOSTIC_VARIANTS:
        replicate_metrics = {metric: [] for metric in metric_names}
        for replicate in RENDER_DIAGNOSTIC_REPLICATES:
            image_metrics = {metric: [] for metric in metric_names}
            for view in RENDER_DIAGNOSTIC_REVIEW_VIEWS:
                for frame in RENDER_DIAGNOSTIC_REVIEW_FRAMES:
                    path = Path(image_lookup[(variant, replicate, view, frame)])
                    with _open_image_file_snapshot(
                        path,
                        label="render_diagnostic_contrast_image",
                    ) as image:
                        array = np.asarray(
                            image.convert("RGB"),
                            dtype=np.float64,
                        )
                    red = array[:, :, 0]
                    green = array[:, :, 1]
                    blue = array[:, :, 2]
                    image_metrics["full_rgb_mean_u8"].append(float(array.mean()))
                    image_metrics["cyan_channel_excess_u8"].append(
                        float((((green + blue) / 2.0) - red).mean())
                    )
                    image_metrics["rec709_luminance_u8"].append(
                        float((0.2126 * red + 0.7152 * green + 0.0722 * blue).mean())
                    )
            for metric in metric_names:
                replicate_metrics[metric].append(
                    sum(image_metrics[metric]) / len(image_metrics[metric])
                )
        for metric in metric_names:
            metric_cell_values[metric][variant] = sum(
                replicate_metrics[metric]
            ) / len(replicate_metrics[metric])

    def estimates(values: Mapping[str, float]) -> dict[str, float]:
        p04 = values["AO0_RT4_CONTROL"]
        p012 = values["AO0_RT12"]
        p14 = values["AO1_RT4"]
        p112 = values["AO1_RT12"]
        return {
            "AO_ASSOCIATION": (p14 + p112 - p04 - p012) / 2.0,
            "RT_ASSOCIATION": (p012 + p112 - p04 - p14) / 2.0,
            "AO_RT_INTERACTION": p112 - p14 - p012 + p04,
        }

    records = []
    for metric, values in metric_cell_values.items():
        for contrast, estimate in estimates(values).items():
            records.append(
                {
                    "name": f"{metric}__{contrast}",
                    "metric": metric,
                    "cell_values": {
                        variant: values[variant]
                        for variant in RENDER_DIAGNOSTIC_VARIANTS
                    },
                    "estimate": estimate,
                }
            )
    return sorted(records, key=lambda record: record["name"])


def run_render_diagnostic_aggregate(args: argparse.Namespace) -> dict[str, Any]:
    scope = validate_render_diagnostic_aggregate_scope(args)
    if scope is None:
        raise ValueError("render_diagnostic_aggregate_scope_required")
    root = _reject_symlink_path_components(
        scope["experiment_root"],
        label="render_diagnostic_aggregate_root",
    )
    if root.is_symlink() or not root.is_dir():
        raise ValueError("render_diagnostic_aggregate_root_not_lawfully_created")
    with acquire_render_diagnostic_experiment_lock() as descriptor:
        anchor = validate_render_diagnostic_experiment_anchor(
            _load_json_object(
                root / RENDER_DIAGNOSTIC_ANCHOR_BASENAME,
                label="render_diagnostic_aggregate_anchor",
            ),
            expected_root=root,
            expected_lock_path=_render_diagnostic_lock_path(),
        )
        lock_stat = os.fstat(descriptor)
        if (lock_stat.st_dev, lock_stat.st_ino) != (
            anchor["lock_device"],
            anchor["lock_inode"],
        ):
            raise ValueError("render_diagnostic_aggregate_lock_anchor_mismatch")
        post_path = _absolute_path_without_symlink_resolution(
            scope["post_freeze"]
        )
        if not post_path.exists() and not post_path.is_symlink():
            try:
                pre_verification = verify_render_diagnostic_pre_freeze_unchanged()
                implementation = (
                    load_and_verify_frozen_matrix_implementation_identity()
                )
                if (
                    pre_verification["sha256"] != anchor["pre_freeze_sha256"]
                    or implementation["implementation_identity_sha256"]
                    != anchor["implementation_identity_sha256"]
                ):
                    raise ValueError(
                        "render_diagnostic_aggregate_freeze_anchor_mismatch"
                    )
                status_index = build_render_diagnostic_cell_status_index(root)
                validate_render_diagnostic_launch_chain(
                    aggregate_root=root,
                    anchor_sha256=anchor["anchor_sha256"],
                    expected_implementation_identity_sha256=anchor[
                        "implementation_identity_sha256"
                    ],
                    expected_pre_freeze_sha256=anchor["pre_freeze_sha256"],
                    cell_status_index=status_index,
                    require_artifact_closure=False,
                )
                envelope = build_render_diagnostic_post_freeze_envelope(
                    registry_snapshot=(
                        snapshot_default_render_diagnostic_protected_registry()
                    ),
                    anchor=anchor,
                    cell_status_index=status_index,
                )
                _write_json_create_exclusive(post_path, envelope)
            except (OSError, RuntimeError, TypeError, ValueError):
                pass
        return _run_render_diagnostic_aggregate_locked(
            args,
            anchor=anchor,
            lock_descriptor=descriptor,
        )


def _run_render_diagnostic_aggregate_locked(
    args: argparse.Namespace,
    *,
    anchor: Mapping[str, Any],
    lock_descriptor: int,
) -> dict[str, Any]:
    scope = validate_render_diagnostic_aggregate_scope(args)
    if scope is None:
        raise ValueError("render_diagnostic_aggregate_scope_required")
    root = Path(scope["experiment_root"])
    authority_path = Path(scope["authority_path"])

    def validate_authority_semantics(
        decision: Mapping[str, Any],
        closure_root: Path | None,
        staging_root: Path | None,
    ) -> dict[str, Any]:
        return validate_render_diagnostic_matrix_decision(
            decision,
            closure_root_override=closure_root,
            require_live_experiment_identity=(closure_root is None),
            authority_publication_staging_root=staging_root,
        )

    if authority_path.exists() or authority_path.is_symlink():
        validated_authority = validate_render_diagnostic_decision_authority(
            aggregate_root=root,
            anchor=anchor,
            lock=lock_descriptor,
            semantic_validator=validate_authority_semantics,
        )
        return validated_authority["decision"]
    pre_path = Path(scope["pre_freeze"])
    post_path = Path(scope["post_freeze"])
    status_for_freeze = build_render_diagnostic_cell_status_index(root)
    freeze = inspect_render_diagnostic_protected_freezes(
        pre_path=pre_path,
        post_path=post_path,
        anchor=anchor,
        cell_status_index=status_for_freeze,
    )
    protected_inputs_match = freeze["protected_inputs_match"]
    protected_failure = freeze["failure"]
    first_slot = render_diagnostic_slots()[0]
    first_intent_path = (
        root / "launch_intents" / f"{first_slot['cell_name']}.json"
    )
    if protected_inputs_match and first_intent_path.is_file():
        try:
            accepted_pre_hash = _load_launch_intent(
                first_intent_path,
                first_slot,
            )["pre_freeze_sha256"]
        except (OSError, TypeError, ValueError):
            accepted_pre_hash = None
        if (
            accepted_pre_hash is not None
            and accepted_pre_hash != freeze["pre_freeze_sha256"]
        ):
            protected_inputs_match = False
            protected_failure = build_render_diagnostic_protected_input_failure(
                failed_path=pre_path,
                failure_kind="CONTENT_CHANGED",
                expected_sha256=accepted_pre_hash,
                observed_sha256=freeze["pre_freeze_sha256"],
            )
    stale_failure_path = root / "evidence" / "protected_input_failure.json"
    if stale_failure_path.exists() or stale_failure_path.is_symlink():
        try:
            protected_failure = (
                validate_render_diagnostic_protected_input_failure(
                    _load_json_object(
                        stale_failure_path,
                        label="stale_protected_input_failure",
                    )
                )
            )
        except (OSError, TypeError, ValueError) as exc:
            protected_failure = build_render_diagnostic_protected_input_failure(
                failed_path=stale_failure_path,
                failure_kind=_protected_freeze_failure_kind(
                    stale_failure_path,
                    exc,
                ),
                expected_sha256=None,
                observed_sha256=_best_effort_regular_file_sha256(
                    stale_failure_path
                ),
            )
        protected_inputs_match = False
    implementation_hash = anchor["implementation_identity_sha256"]
    try:
        implementation_identity = (
            load_and_verify_frozen_matrix_implementation_identity()
        )
        if (
            implementation_identity["implementation_identity_sha256"]
            != implementation_hash
        ):
            raise RuntimeError("implementation_identity_anchor_mismatch")
    except (OSError, RuntimeError, ValueError) as exc:
        if protected_inputs_match:
            try:
                observed_implementation_hash = (
                    build_matrix_implementation_identity_v1()[
                        "implementation_identity_sha256"
                    ]
                )
            except (OSError, RuntimeError, ValueError):
                observed_implementation_hash = None
            protected_inputs_match = False
            protected_failure = build_render_diagnostic_protected_input_failure(
                failed_path=REPO_ROOT
                / "tools/labutopia_fluid/run_real_beaker_omniglass_replay.py",
                failure_kind=(
                    "IMPLEMENTATION_CHANGED"
                    if observed_implementation_hash is not None
                    else "UNREADABLE"
                ),
                expected_sha256=implementation_hash,
                observed_sha256=observed_implementation_hash,
            )
    if protected_inputs_match:
        machine = build_render_diagnostic_machine_verification(
            root,
            expected_implementation_identity=implementation_identity,
            expected_pre_freeze_sha256=freeze["pre_freeze_sha256"],
        )
    else:
        status_index = build_render_diagnostic_cell_status_index(root)
        statuses = [record["status"] for record in status_index["cells"]]
        machine = {
            "schema_version": 1,
            "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
            "cell_status_index": status_index,
            "cell_status_index_sha256": canonical_json_sha256_v1(
                status_index
            ),
            "all_launched_cells_successful": not any(
                status in {"LAUNCHED_EVIDENCE_MISSING", "FAILED"}
                for status in statuses
            ),
            "all_sixteen_cells_successful": False,
            "successful_cell_evidence": [],
            "image_lookup": {},
        }
    statuses = [
        record["status"] for record in machine["cell_status_index"]["cells"]
    ]
    launched_success = machine["all_launched_cells_successful"]
    post_seal_hash = None
    post_seal_path = root / RENDER_DIAGNOSTIC_POST_SEAL_BASENAME
    if protected_inputs_match and all(status == "SUCCESS" for status in statuses):
        post_envelope = freeze.get("post_freeze_envelope")
        if not isinstance(post_envelope, Mapping):
            raise ValueError("render_diagnostic_post_envelope_missing")
        if post_seal_path.exists() or post_seal_path.is_symlink():
            post_seal = validate_render_diagnostic_successful_post_seal(
                _load_json_object(
                    post_seal_path,
                    label="render_diagnostic_successful_post_seal",
                ),
                anchor=anchor,
                post_freeze_envelope=post_envelope,
                cell_status_index=machine["cell_status_index"],
                validated_launch_chain=machine["launch_chain"],
            )
        else:
            post_seal = build_render_diagnostic_successful_post_seal(
                anchor=anchor,
                post_freeze_envelope=post_envelope,
                cell_status_index=machine["cell_status_index"],
                validated_launch_chain=machine["launch_chain"],
            )
            _write_json_create_exclusive(post_seal_path, post_seal)
        post_seal_hash = post_seal["post_seal_sha256"]
    if not protected_inputs_match or not launched_success:
        matrix_status = "NOT_REACHED"
        repeat_status = "NOT_REACHED"
    else:
        matrix_status = machine["matrix_validation"]["status"]
        repeat_status = (
            machine["repeat_stability"]["status"]
            if matrix_status == "PASS"
            else "NOT_REACHED"
        )
    if matrix_status == "NOT_REACHED":
        matrix_payload = {
            "schema_version": 1,
            "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
            "status": "NOT_REACHED",
            "exact_slot_closure": None,
            "all_cells_successful": None,
            "unexpected_paths": [],
            "equality_checks": [],
            "projection_byte_equality": None,
            "projection_sha256": None,
        }
        matrix_evidence = {
            **matrix_payload,
            "matrix_validation_evidence_sha256": canonical_json_sha256_v1(
                matrix_payload
            ),
        }
    else:
        matrix_evidence = machine["matrix_validation"]
    if repeat_status == "NOT_REACHED":
        repeat_payload = {
            "schema_version": 1,
            "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
            "status": "NOT_REACHED",
            "thresholds": {"rgb_mae_max": 5.0, "psnr_db_min": 30.0},
            "comparisons": [],
        }
        repeat_evidence = {
            **repeat_payload,
            "repeat_stability_evidence_sha256": canonical_json_sha256_v1(
                repeat_payload
            ),
        }
    else:
        repeat_evidence = machine["repeat_stability"]
    review_record = None
    configuration_gates = None
    visual_gates = None
    review_path_value = scope["review_record"]
    if (
        protected_inputs_match
        and launched_success
        and matrix_status == "PASS"
        and repeat_status == "PASS"
        and review_path_value is not None
    ):
        try:
            review_record = validate_render_diagnostic_review_record(
                _load_json_object(
                    Path(review_path_value),
                    label="matrix_review_record",
                ),
                expected_image_lookup=machine["image_lookup"],
                expected_review_root=root / "review",
            )
            configuration_gates = review_record["configuration_gates"]
            visual_gates = {
                "panel_gates": review_record["panel_gates"],
                "replicate_gates": review_record["replicate_gates"],
                "configuration_gates": review_record[
                    "configuration_gates"
                ],
            }
        except (KeyError, OSError, TypeError, ValueError):
            review_record = None
            configuration_gates = None
            visual_gates = None
    if protected_inputs_match:
        final_freeze = inspect_render_diagnostic_protected_freezes(
            pre_path=pre_path,
            post_path=post_path,
            anchor=anchor,
            cell_status_index=machine["cell_status_index"],
        )
        final_implementation_failure = None
        try:
            final_implementation = (
                load_and_verify_frozen_matrix_implementation_identity()
            )
            if (
                final_implementation["implementation_identity_sha256"]
                != implementation_hash
            ):
                raise RuntimeError("implementation_identity_changed")
        except (OSError, RuntimeError, ValueError):
            try:
                observed_implementation_hash = (
                    build_matrix_implementation_identity_v1()[
                        "implementation_identity_sha256"
                    ]
                )
            except (OSError, RuntimeError, ValueError):
                observed_implementation_hash = None
            final_implementation_failure = (
                build_render_diagnostic_protected_input_failure(
                    failed_path=RENDER_DIAGNOSTIC_IMPLEMENTATION_FREEZE_PATH,
                    failure_kind=(
                        "IMPLEMENTATION_CHANGED"
                        if observed_implementation_hash is not None
                        else "UNREADABLE"
                    ),
                    expected_sha256=implementation_hash,
                    observed_sha256=observed_implementation_hash,
                )
            )
        if (
            not final_freeze["protected_inputs_match"]
            or final_implementation_failure is not None
        ):
            protected_inputs_match = False
            freeze = final_freeze
            protected_failure = (
                final_implementation_failure or final_freeze["failure"]
            )
            matrix_status = "NOT_REACHED"
            repeat_status = "NOT_REACHED"
            matrix_payload = {
                "schema_version": 1,
                "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
                "status": "NOT_REACHED",
                "exact_slot_closure": None,
                "all_cells_successful": None,
                "unexpected_paths": [],
                "equality_checks": [],
                "projection_byte_equality": None,
                "projection_sha256": None,
            }
            matrix_evidence = {
                **matrix_payload,
                "matrix_validation_evidence_sha256": (
                    canonical_json_sha256_v1(matrix_payload)
                ),
            }
            repeat_payload = {
                "schema_version": 1,
                "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
                "status": "NOT_REACHED",
                "thresholds": {"rgb_mae_max": 5.0, "psnr_db_min": 30.0},
                "comparisons": [],
            }
            repeat_evidence = {
                **repeat_payload,
                "repeat_stability_evidence_sha256": (
                    canonical_json_sha256_v1(repeat_payload)
                ),
            }
            review_record = None
            configuration_gates = None
            visual_gates = None
    evidence_root = root / "evidence"
    if evidence_root.is_symlink() or (
        evidence_root.exists() and not evidence_root.is_dir()
    ):
        raise ValueError("render_diagnostic_evidence_root_invalid")
    evidence_root.mkdir(parents=True, exist_ok=True)
    protected_failure_hash = None
    if protected_failure is not None:
        protected_failure = validate_render_diagnostic_protected_input_failure(
            protected_failure
        )
        atomic_write_json(
            evidence_root / "protected_input_failure.json",
            protected_failure,
        )
        protected_failure_hash = protected_failure[
            "protected_input_failure_evidence_sha256"
        ]
    cell_status_index_sha256 = canonical_json_sha256_v1(
        machine["cell_status_index"]
    )
    terminal = resolve_render_diagnostic_terminal_state(
        protected_inputs_match=protected_inputs_match,
        all_launched_cells_successful=launched_success,
        matrix_status=matrix_status,
        repeat_status=repeat_status,
        configuration_gates=configuration_gates,
        pre_freeze_sha256=freeze["pre_freeze_sha256"],
        post_freeze_sha256=freeze["post_freeze_sha256"],
        implementation_identity_sha256=implementation_hash,
        protected_input_failure_evidence_sha256=protected_failure_hash,
        cell_status_index_sha256=cell_status_index_sha256,
        matrix_validation_evidence_sha256=matrix_evidence[
            "matrix_validation_evidence_sha256"
        ],
        repeat_stability_evidence_sha256=repeat_evidence[
            "repeat_stability_evidence_sha256"
        ],
        review_record_sha256=(
            review_record["review_record_sha256"]
            if review_record is not None
            else None
        ),
        visual_gates=visual_gates,
    )
    atomic_write_json(
        evidence_root / "cell_status_index.json",
        machine["cell_status_index"],
    )
    atomic_write_json(
        evidence_root / "matrix_validation.json",
        matrix_evidence,
    )
    atomic_write_json(
        evidence_root / "repeat_stability.json",
        repeat_evidence,
    )
    successful_cells = sorted(
        machine["successful_cell_evidence"],
        key=lambda cell: (
            RENDER_DIAGNOSTIC_VARIANTS.index(cell["variant"]),
            RENDER_DIAGNOSTIC_REPLICATES.index(cell["replicate"]),
        ),
    )
    aggregate_cell_index = {
        "schema_version": 1,
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "cells": [
            {
                "variant": cell["variant"],
                "replicate": cell["replicate"],
                "execution_order_index": cell["execution_order_index"],
                "manifest_path": str(Path(cell["cell_root"]) / "replay_manifest.json"),
                "manifest_sha256": _sha256_file(
                    Path(cell["cell_root"]) / "replay_manifest.json"
                ),
                "implementation_identity_sha256": cell[
                    "implementation_identity_sha256"
                ],
                "effective_replay_look_contract_sha256": cell[
                    "effective_replay_look_contract_sha256"
                ],
            }
            for cell in successful_cells
        ],
    }
    if successful_cells and implementation_hash is not None and any(
        cell["implementation_identity_sha256"] != implementation_hash
        for cell in successful_cells
    ):
        raise ValueError("aggregate_implementation_identity_mismatch")
    terminal_code = terminal["code"]
    contrasts = (
        _render_diagnostic_descriptive_contrasts(
            machine["image_lookup"],
            configuration_gates,
        )
        if terminal_code
        in {
            "FAIL_NO_RENDER_SETTING_RECOVERY",
            "PASS_VISUALLY_PASSED_RENDER_DIAGNOSTIC",
        }
        else None
    )
    visually_passed = None
    if terminal_code == "PASS_VISUALLY_PASSED_RENDER_DIAGNOSTIC":
        visually_passed = next(
            variant
            for variant in RENDER_DIAGNOSTIC_VARIANTS
            if configuration_gates[variant] == "PASS"
        )
    interpretation_allowed = terminal_code in {
        "FAIL_NO_RENDER_SETTING_RECOVERY",
        "PASS_VISUALLY_PASSED_RENDER_DIAGNOSTIC",
    }
    decision_payload = {
        "schema_version": 1,
        "manifest_type": "real_beaker_render_diagnostic_matrix_decision",
        "experiment_id": RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "generated_at_utc": (
            "EVIDENCE_SHA256:" + terminal["evidence_sha256"]
        ),
        "terminal_state": terminal,
        "cell_status_index": machine["cell_status_index"],
        "aggregate_cell_index": aggregate_cell_index,
        "anchor_sha256": anchor["anchor_sha256"],
        "post_seal_sha256": post_seal_hash,
        "closure_snapshot_sha256": None,
        "pre_freeze_sha256": freeze["pre_freeze_sha256"],
        "post_freeze_sha256": freeze["post_freeze_sha256"],
        "implementation_identity_sha256": implementation_hash,
        "matrix_validation": {
            "status": matrix_status,
            "evidence_sha256": matrix_evidence[
                "matrix_validation_evidence_sha256"
            ],
        },
        "repeat_stability": {
            "status": repeat_status,
            "evidence_sha256": repeat_evidence[
                "repeat_stability_evidence_sha256"
            ],
        },
        "review_record_sha256": (
            review_record["review_record_sha256"]
            if review_record is not None
            else None
        ),
        "visual_gates": visual_gates,
        "descriptive_contrasts": contrasts,
        "operational_preference": [
            {
                "variant": variant,
                "score": [
                    int(RENDER_DIAGNOSTIC_VARIANT_SETTINGS[variant][0]),
                    RENDER_DIAGNOSTIC_VARIANT_SETTINGS[variant][1],
                ],
            }
            for variant in RENDER_DIAGNOSTIC_VARIANTS
        ],
        "visually_passed_configuration": visually_passed,
        "claim_boundary": {
            "allowed": (
                sorted(
                    [
                    "observed_pixel_association_under_tested_isaacsim41_configuration",
                    "next_reviewed_planning_action",
                    ]
                )
                if interpretation_allowed
                else []
            ),
            "blocked": sorted(
                [
                    "causal_renderer_consumption_claim",
                    "colleague_delivery",
                    "exporter_admission",
                    "formal_look_selection",
                    "package_localization",
                ]
            ),
        },
    }
    decision_holder: dict[str, Any] = {}

    def build_authority_decision(
        closure_snapshot_sha256: str | None,
    ) -> dict[str, Any]:
        payload = deepcopy(decision_payload)
        payload["closure_snapshot_sha256"] = closure_snapshot_sha256
        hash_payload = {
            key: value
            for key, value in payload.items()
            if key != "generated_at_utc"
        }
        built = {
            **payload,
            "matrix_decision_sha256": canonical_json_sha256_v1(hash_payload),
        }
        decision_holder.clear()
        decision_holder.update(built)
        return built

    def final_publication_guard() -> None:
        if not decision_holder:
            raise ValueError("matrix_decision_publication_decision_missing")
        guarded_decision = decision_holder
        guarded_anchor = validate_render_diagnostic_experiment_anchor(
            _load_json_object(
                root / RENDER_DIAGNOSTIC_ANCHOR_BASENAME,
                label="matrix_decision_publication_anchor",
            ),
            expected_root=root,
            expected_lock_path=_render_diagnostic_lock_path(),
        )
        guarded_lock = os.fstat(lock_descriptor)
        if (
            guarded_anchor["anchor_sha256"]
            != guarded_decision["anchor_sha256"]
            or (guarded_lock.st_dev, guarded_lock.st_ino)
            != (guarded_anchor["lock_device"], guarded_anchor["lock_inode"])
        ):
            raise ValueError("matrix_decision_publication_identity_changed")
        current_status = build_render_diagnostic_cell_status_index(root)
        if current_status != guarded_decision["cell_status_index"]:
            raise ValueError("matrix_decision_publication_status_changed")
        if protected_inputs_match:
            final_guard = inspect_render_diagnostic_protected_freezes(
                pre_path=pre_path,
                post_path=post_path,
                anchor=anchor,
                cell_status_index=current_status,
            )
            guarded_identity = (
                load_and_verify_frozen_matrix_implementation_identity()
            )
            if (
                not final_guard["protected_inputs_match"]
                or guarded_identity["implementation_identity_sha256"]
                != implementation_hash
            ):
                raise ValueError("matrix_decision_publication_freeze_changed")

    closure_external_files = (
        {
            "external/implementation_identity.json": (
                RENDER_DIAGNOSTIC_IMPLEMENTATION_FREEZE_PATH
            ),
            "external/pre_freeze.json": pre_path,
            "external/post_freeze.json": post_path,
        }
        if interpretation_allowed
        else None
    )
    published = publish_render_diagnostic_decision_authority(
        aggregate_root=root,
        decision=None,
        decision_builder=build_authority_decision,
        anchor=anchor,
        lock_descriptor=lock_descriptor,
        closure_root=None,
        closure_external_files=closure_external_files,
        publication_guard=final_publication_guard,
        semantic_validator=validate_authority_semantics,
    )
    decision = published["decision"]
    return decision


class _StoreOnceAction(argparse.Action):
    """Argparse store action that rejects repeated explicit values."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        marker = f"_{self.dest}_explicitly_set"
        if getattr(namespace, marker, False):
            parser.error(f"argument {option_string}: may not be repeated")
        setattr(namespace, marker, True)
        setattr(namespace, self.dest, values)


class _StoreTrueOnceAction(argparse.Action):
    def __init__(self, option_strings: Any, dest: str, **kwargs: Any) -> None:
        super().__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        marker = f"_{self.dest}_explicitly_set"
        if getattr(namespace, marker, False):
            parser.error(f"argument {option_string}: may not be repeated")
        setattr(namespace, marker, True)
        setattr(namespace, self.dest, True)


def validate_render_diagnostic_aggregate_scope(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    aggregate_only = bool(
        getattr(args, "render_diagnostic_aggregate_only", False)
    )
    aggregate_values = (
        getattr(args, "render_diagnostic_experiment_root", None),
        getattr(args, "render_diagnostic_pre_freeze", None),
        getattr(args, "render_diagnostic_post_freeze", None),
        getattr(args, "render_diagnostic_review_record", None),
    )
    if not aggregate_only:
        if any(value is not None for value in aggregate_values):
            raise ValueError("render_diagnostic_aggregate_scope_incomplete")
        return None
    experiment_root, pre_freeze, post_freeze, review_record = aggregate_values
    if experiment_root is None or pre_freeze is None or post_freeze is None:
        raise ValueError("render_diagnostic_aggregate_scope_incomplete")
    resolved_root = _reject_symlink_path_components(
        str(experiment_root),
        label="render_diagnostic_aggregate_root",
    )
    expected_root = _reject_symlink_path_components(
        RENDER_DIAGNOSTIC_AGGREGATE_ROOT,
        label="render_diagnostic_aggregate_root",
    )
    if expected_root.is_symlink() or resolved_root.is_symlink():
        raise ValueError("render_diagnostic_aggregate_root_symlink")
    if resolved_root != expected_root:
        raise ValueError("render_diagnostic_aggregate_scope_root_mismatch")
    resolved_pre = _reject_symlink_path_components(
        str(pre_freeze),
        label="render_diagnostic_pre_freeze",
    )
    resolved_post = _reject_symlink_path_components(
        str(post_freeze),
        label="render_diagnostic_post_freeze",
    )
    if (
        resolved_pre
        != _absolute_path_without_symlink_resolution(
            RENDER_DIAGNOSTIC_PRE_FREEZE_PATH
        )
        or resolved_post
        != _absolute_path_without_symlink_resolution(
            RENDER_DIAGNOSTIC_POST_FREEZE_PATH
        )
        or resolved_pre.is_symlink()
        or resolved_post.is_symlink()
    ):
        raise ValueError("render_diagnostic_aggregate_scope_freeze_path_mismatch")
    resolved_review = None
    if review_record is not None:
        resolved_review = _reject_symlink_path_components(
            str(review_record),
            label="render_diagnostic_review_record",
        )
        if resolved_review != resolved_root / "review" / "review_record.json":
            raise ValueError(
                "render_diagnostic_aggregate_scope_review_path_mismatch"
            )
    mixed = (
        any(
            bool(getattr(args, f"_{dest}_explicitly_set", False))
            for dest in (
                "accepted_authority_bundle",
                "accepted_summary",
                "accepted_matrix_manifest",
                "accepted_diagnostic_segment_archive",
                "out_root",
                "manifest",
                "candidates",
                "visual_prototype_lighting_variant",
                "visual_prototype_render_diagnostic_variant",
                "render_diagnostic_experiment_id",
                "render_diagnostic_replicate",
                "render_diagnostic_order_index",
                "width",
                "height",
                "video_fps",
                "warmup_updates",
                "camera_warmup_updates",
                "runtime_parent_pid",
                "runtime_parent_lock_fd",
            )
        )
        or
        getattr(args, "accepted_authority_bundle", None) is not None
        or getattr(args, "accepted_summary", None) is not None
        or getattr(args, "accepted_matrix_manifest", None) is not None
        or getattr(args, "accepted_diagnostic_segment_archive", None) is not None
        or getattr(args, "manifest", None) is not None
        or str(getattr(args, "out_root", "")) != str(DEFAULT_OUT_ROOT)
        or str(getattr(args, "candidates", "")) != DEFAULT_CANDIDATES
        or bool(getattr(args, "visual_prototype_display_fill_only", False))
        or getattr(args, "visual_prototype_lighting_variant", None)
        != LIGHTING_VARIANT_C_CONTROL
        or getattr(args, "visual_prototype_render_diagnostic_variant", None)
        is not None
        or getattr(args, "render_diagnostic_experiment_id", None) is not None
        or getattr(args, "render_diagnostic_replicate", None) is not None
        or getattr(args, "render_diagnostic_order_index", None) is not None
        or bool(getattr(args, "dry_plan", False))
        or bool(getattr(args, "headless", False))
        or bool(getattr(args, "runtime_child", False))
        or getattr(args, "runtime_parent_pid", None) is not None
        or getattr(args, "runtime_parent_lock_fd", None) is not None
        or getattr(args, "runtime_parent_archive_fd", None) is not None
        or getattr(args, "runtime_parent_archive_sha256", None) is not None
        or getattr(args, "runtime_bootstrap_sha256", None) is not None
        or int(getattr(args, "width", 960)) != 960
        or int(getattr(args, "height", 540)) != 540
        or float(getattr(args, "video_fps", 15.0)) != 15.0
        or int(getattr(args, "warmup_updates", 8)) != 8
        or int(getattr(args, "camera_warmup_updates", 8)) != 8
    )
    if mixed:
        raise ValueError("render_diagnostic_aggregate_scope_mixed_option")
    return {
        "experiment_root": str(resolved_root),
        "pre_freeze": str(resolved_pre),
        "post_freeze": str(resolved_post),
        "review_record": (
            str(resolved_review) if resolved_review is not None else None
        ),
        "authority_path": str(
            resolved_root / RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME
        ),
        "decision_path": str(
            resolved_root
            / RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME
            / "matrix_decision.json"
        ),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--accepted-authority-bundle", action=_StoreOnceAction, default=None
    )
    parser.add_argument("--accepted-summary", action=_StoreOnceAction, default=None)
    parser.add_argument(
        "--accepted-matrix-manifest", action=_StoreOnceAction, default=None
    )
    parser.add_argument(
        "--accepted-diagnostic-segment-archive",
        action=_StoreOnceAction,
        default=None,
    )
    parser.add_argument(
        "--render-diagnostic-aggregate-only",
        action=_StoreTrueOnceAction,
        default=False,
    )
    parser.add_argument(
        "--render-diagnostic-launch-preflight-only",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--render-diagnostic-experiment-root",
        action=_StoreOnceAction,
        default=None,
    )
    parser.add_argument(
        "--render-diagnostic-pre-freeze",
        action=_StoreOnceAction,
        default=None,
    )
    parser.add_argument(
        "--render-diagnostic-post-freeze",
        action=_StoreOnceAction,
        default=None,
    )
    parser.add_argument(
        "--render-diagnostic-review-record",
        action=_StoreOnceAction,
        default=None,
    )
    parser.add_argument(
        "--out-root", action=_StoreOnceAction, default=str(DEFAULT_OUT_ROOT)
    )
    parser.add_argument("--manifest", action=_StoreOnceAction, default=None)
    parser.add_argument(
        "--candidates",
        action=_StoreOnceAction,
        default=DEFAULT_CANDIDATES,
        help=(
            "Evidence gate: must be the complete canonical five-candidate list, "
            "except for the explicit display-fill visual prototype mode."
        ),
    )
    parser.add_argument(
        "--visual-prototype-display-fill-only",
        action="store_true",
        help=(
            "Run only OMNI_REF_DISPLAY_FILL as a non-deliverable visual prototype; "
            "requires an exact single-candidate --candidates value."
        ),
    )
    parser.add_argument(
        "--visual-prototype-lighting-variant",
        action=_StoreOnceAction,
        choices=ALLOWED_LIGHTING_VARIANTS,
        default=LIGHTING_VARIANT_C_CONTROL,
        help=(
            "Controlled lighting-only prototype variant. B_LIGHTING is legal "
            "only in exact display-fill visual-prototype scope."
        ),
    )
    parser.add_argument(
        "--visual-prototype-render-diagnostic-variant",
        action=_StoreOnceAction,
        choices=RENDER_DIAGNOSTIC_VARIANTS,
        default=None,
    )
    parser.add_argument(
        "--render-diagnostic-experiment-id",
        action=_StoreOnceAction,
        default=None,
    )
    parser.add_argument(
        "--render-diagnostic-replicate",
        action=_StoreOnceAction,
        choices=tuple(RENDER_DIAGNOSTIC_BALANCED_ORDER),
        default=None,
    )
    parser.add_argument(
        "--render-diagnostic-order-index",
        action=_StoreOnceAction,
        type=int,
        choices=(0, 1, 2, 3),
        default=None,
    )
    parser.add_argument("--dry-plan", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--width", action=_StoreOnceAction, type=int, default=960)
    parser.add_argument("--height", action=_StoreOnceAction, type=int, default=540)
    parser.add_argument(
        "--video-fps", action=_StoreOnceAction, type=float, default=15.0
    )
    parser.add_argument(
        "--warmup-updates", action=_StoreOnceAction, type=int, default=8
    )
    parser.add_argument(
        "--camera-warmup-updates",
        action=_StoreOnceAction,
        type=int,
        default=8,
    )
    parser.add_argument(
        "--runtime-child",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--runtime-parent-pid",
        action=_StoreOnceAction,
        type=int,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--runtime-parent-lock-fd",
        action=_StoreOnceAction,
        type=int,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--runtime-parent-archive-fd",
        action=_StoreOnceAction,
        type=int,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--runtime-parent-archive-sha256",
        action=_StoreOnceAction,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--runtime-bootstrap-sha256",
        action=_StoreOnceAction,
        default=None,
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = build_arg_parser().parse_args(raw_argv)
    args._execution_argv = [str(Path(__file__).resolve()), *raw_argv]
    if args.render_diagnostic_launch_preflight_only:
        print(json.dumps(run_render_diagnostic_launch_preflight(), indent=2))
        return 0
    aggregate_scope = validate_render_diagnostic_aggregate_scope(args)
    if aggregate_scope is not None:
        result = run_render_diagnostic_aggregate(args)
        print(json.dumps(result, indent=2))
        return 0
    if args.dry_plan:
        print(json.dumps(build_dry_plan(args), indent=2))
        return 0
    validate_runtime_child_invocation(args)
    result = (
        run_replay(args)
        if args.runtime_child
        else run_replay_parent_launcher(raw_argv, args)
    )
    if not args.runtime_child:
        print(json.dumps(result, indent=2))
    return (
        0
        if result.get("classification")
        in {
            "RENDER_COMPLETE_PENDING_VISUAL_REVIEW",
            "DIAGNOSTIC_RENDER_COMPLETE_PENDING_VISUAL_REVIEW",
        }
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
