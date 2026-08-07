#!/usr/bin/env python3
"""Cross-environment shared-memory frame transport for fluid positions."""

from __future__ import annotations

import json
import socket
import struct
import zlib
from dataclasses import dataclass
from multiprocessing import resource_tracker, shared_memory
from typing import Any

import numpy as np

from tools.labutopia_fluid.fluid_benchmark_contract import (
    EXPECTED_PARTICLE_COUNT,
    canonical_json_bytes,
)


BRIDGE_SCHEMA = "labutopia.fluid_shm.v1"
RENDER_BRIDGE_SCHEMA = "labutopia.fluid_render_shm.v2"
MAGIC = b"LBFLSHM1"
RENDER_MAGIC = b"LBFRSHM2"
HEADER = struct.Struct("<8sIIqdII24x")
HEADER_SIZE = HEADER.size
POSITION_DTYPE = np.dtype("<f4")
POSITION_SHAPE = (EXPECTED_PARTICLE_COUNT, 3)
PAYLOAD_SIZE = int(np.prod(POSITION_SHAPE)) * POSITION_DTYPE.itemsize
BUFFER_SIZE = HEADER_SIZE + PAYLOAD_SIZE
LENGTH = struct.Struct("!I")
MAX_MESSAGE_BYTES = 1024 * 1024
_LOCALLY_OWNED_MEMORY_NAMES: set[str] = set()

RENDER_MODE_PARTICLES = 1
RENDER_MODE_SURFACE = 2
MAX_SURFACE_VERTICES = 32_768
MAX_SURFACE_INDICES = 196_608
MAX_RESIDUAL_PARTICLES = EXPECTED_PARTICLE_COUNT
RENDER_HEADER = struct.Struct("<8sIIqdIIIIII32x")
RENDER_HEADER_SIZE = RENDER_HEADER.size
RENDER_POSITION_BYTES = PAYLOAD_SIZE
RENDER_VERTEX_BYTES = MAX_SURFACE_VERTICES * 3 * POSITION_DTYPE.itemsize
RENDER_INDEX_DTYPE = np.dtype("<i4")
RENDER_INDEX_BYTES = MAX_SURFACE_INDICES * RENDER_INDEX_DTYPE.itemsize
RENDER_RESIDUAL_BYTES = MAX_RESIDUAL_PARTICLES * 3 * POSITION_DTYPE.itemsize
RENDER_VERTEX_OFFSET = RENDER_HEADER_SIZE + RENDER_POSITION_BYTES
RENDER_INDEX_OFFSET = RENDER_VERTEX_OFFSET + RENDER_VERTEX_BYTES
RENDER_RESIDUAL_OFFSET = RENDER_INDEX_OFFSET + RENDER_INDEX_BYTES
RENDER_BUFFER_SIZE = RENDER_RESIDUAL_OFFSET + RENDER_RESIDUAL_BYTES


def _recv_exact(connection: socket.socket, count: int) -> bytes:
    chunks: list[bytes] = []
    remaining = count
    while remaining:
        chunk = connection.recv(remaining)
        if not chunk:
            raise ConnectionError("bridge_socket_closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def send_message(connection: socket.socket, value: Any) -> None:
    payload = canonical_json_bytes(value)
    if len(payload) > MAX_MESSAGE_BYTES:
        raise ValueError("bridge_message_too_large")
    connection.sendall(LENGTH.pack(len(payload)) + payload)


def receive_message(connection: socket.socket) -> dict[str, Any]:
    (length,) = LENGTH.unpack(_recv_exact(connection, LENGTH.size))
    if length <= 0 or length > MAX_MESSAGE_BYTES:
        raise ValueError("bridge_message_length_invalid")
    value = json.loads(_recv_exact(connection, length).decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("bridge_message_not_object")
    return value


@dataclass
class SharedFluidFrame:
    memory: shared_memory.SharedMemory
    owner: bool

    @classmethod
    def create(cls, *, name: str | None = None) -> "SharedFluidFrame":
        memory = shared_memory.SharedMemory(
            name=name,
            create=True,
            size=BUFFER_SIZE,
        )
        _LOCALLY_OWNED_MEMORY_NAMES.add(memory._name)
        return cls(memory=memory, owner=True)

    @classmethod
    def attach(cls, name: str) -> "SharedFluidFrame":
        if not isinstance(name, str) or not name:
            raise ValueError("shared_memory_name_invalid")
        memory = shared_memory.SharedMemory(name=name, create=False)
        # Python 3.10/3.12 register every attachment with the process-local
        # resource tracker.  An attaching process must not unlink storage that
        # is owned by the matrix orchestrator when it exits.  Python 3.13 adds
        # an equivalent public ``track=False`` option; unregistering is the
        # compatible behavior for the sealed runtimes used here.
        if memory._name not in _LOCALLY_OWNED_MEMORY_NAMES:
            resource_tracker.unregister(memory._name, "shared_memory")
        if memory.size != BUFFER_SIZE:
            memory.close()
            raise ValueError(
                "shared_memory_size_mismatch:"
                f"expected={BUFFER_SIZE}:actual={memory.size}"
            )
        return cls(memory=memory, owner=False)

    @property
    def name(self) -> str:
        return self.memory.name

    def write(
        self,
        positions: Any,
        *,
        frame_index: int,
        simulation_time_s: float,
    ) -> int:
        values = np.asarray(positions, dtype=POSITION_DTYPE, order="C")
        if values.shape != POSITION_SHAPE or not np.isfinite(values).all():
            raise ValueError("bridge_positions_invalid")
        if isinstance(frame_index, bool) or not isinstance(frame_index, int):
            raise ValueError("bridge_frame_index_invalid")
        payload = values.tobytes(order="C")
        checksum = zlib.crc32(payload) & 0xFFFFFFFF
        self.memory.buf[HEADER_SIZE:BUFFER_SIZE] = payload
        self.memory.buf[:HEADER_SIZE] = HEADER.pack(
            MAGIC,
            1,
            EXPECTED_PARTICLE_COUNT,
            frame_index,
            float(simulation_time_s),
            checksum,
            PAYLOAD_SIZE,
        )
        return checksum

    def read(self, *, expected_frame_index: int | None = None) -> tuple[np.ndarray, dict[str, Any]]:
        (
            magic,
            version,
            particle_count,
            frame_index,
            simulation_time_s,
            expected_checksum,
            payload_size,
        ) = HEADER.unpack(bytes(self.memory.buf[:HEADER_SIZE]))
        if magic != MAGIC or version != 1:
            raise ValueError("bridge_header_identity_mismatch")
        if particle_count != EXPECTED_PARTICLE_COUNT or payload_size != PAYLOAD_SIZE:
            raise ValueError("bridge_header_shape_mismatch")
        if expected_frame_index is not None and frame_index != expected_frame_index:
            raise ValueError(
                "bridge_frame_index_mismatch:"
                f"expected={expected_frame_index}:actual={frame_index}"
            )
        payload = bytes(self.memory.buf[HEADER_SIZE:BUFFER_SIZE])
        actual_checksum = zlib.crc32(payload) & 0xFFFFFFFF
        if actual_checksum != expected_checksum:
            raise ValueError(
                "bridge_checksum_mismatch:"
                f"expected={expected_checksum}:actual={actual_checksum}"
            )
        positions = np.frombuffer(payload, dtype=POSITION_DTYPE).reshape(
            POSITION_SHAPE
        )
        return positions.copy(), {
            "schema": BRIDGE_SCHEMA,
            "frame_index": int(frame_index),
            "simulation_time_s": float(simulation_time_s),
            "checksum_crc32": int(actual_checksum),
        }

    def close(self) -> None:
        self.memory.close()

    def unlink(self) -> None:
        if not self.owner:
            raise RuntimeError("only_bridge_owner_may_unlink")
        self.memory.unlink()
        _LOCALLY_OWNED_MEMORY_NAMES.discard(self.memory._name)


@dataclass
class SharedFluidRenderFrame:
    """Fixed-capacity v2 transport for particle or reconstructed-surface frames."""

    memory: shared_memory.SharedMemory
    owner: bool

    @classmethod
    def create(cls, *, name: str | None = None) -> "SharedFluidRenderFrame":
        memory = shared_memory.SharedMemory(
            name=name,
            create=True,
            size=RENDER_BUFFER_SIZE,
        )
        _LOCALLY_OWNED_MEMORY_NAMES.add(memory._name)
        return cls(memory=memory, owner=True)

    @classmethod
    def attach(cls, name: str) -> "SharedFluidRenderFrame":
        if not isinstance(name, str) or not name:
            raise ValueError("render_shared_memory_name_invalid")
        memory = shared_memory.SharedMemory(name=name, create=False)
        if memory._name not in _LOCALLY_OWNED_MEMORY_NAMES:
            resource_tracker.unregister(memory._name, "shared_memory")
        if memory.size != RENDER_BUFFER_SIZE:
            memory.close()
            raise ValueError(
                "render_shared_memory_size_mismatch:"
                f"expected={RENDER_BUFFER_SIZE}:actual={memory.size}"
            )
        return cls(memory=memory, owner=False)

    @property
    def name(self) -> str:
        return self.memory.name

    def _write_header(
        self,
        *,
        mode: int,
        frame_index: int,
        simulation_time_s: float,
        particle_count: int,
        vertex_count: int,
        index_count: int,
        residual_count: int,
        payload: bytes,
    ) -> int:
        if isinstance(frame_index, bool) or not isinstance(frame_index, int):
            raise ValueError("render_frame_index_invalid")
        checksum = zlib.crc32(payload) & 0xFFFFFFFF
        self.memory.buf[:RENDER_HEADER_SIZE] = RENDER_HEADER.pack(
            RENDER_MAGIC,
            2,
            mode,
            frame_index,
            float(simulation_time_s),
            particle_count,
            vertex_count,
            index_count,
            residual_count,
            len(payload),
            checksum,
        )
        return checksum

    def write_particles(
        self,
        positions: Any,
        *,
        frame_index: int,
        simulation_time_s: float,
    ) -> int:
        values = np.asarray(positions, dtype=POSITION_DTYPE, order="C")
        if values.shape != POSITION_SHAPE or not np.isfinite(values).all():
            raise ValueError("render_particle_positions_invalid")
        payload = values.tobytes(order="C")
        start = RENDER_HEADER_SIZE
        self.memory.buf[start : start + len(payload)] = payload
        return self._write_header(
            mode=RENDER_MODE_PARTICLES,
            frame_index=frame_index,
            simulation_time_s=simulation_time_s,
            particle_count=EXPECTED_PARTICLE_COUNT,
            vertex_count=0,
            index_count=0,
            residual_count=0,
            payload=payload,
        )

    def write_surface(
        self,
        vertices: Any,
        indices: Any,
        residual_positions: Any,
        *,
        frame_index: int,
        simulation_time_s: float,
    ) -> int:
        vertex_values = np.asarray(vertices, dtype=POSITION_DTYPE, order="C")
        index_values = np.asarray(indices, dtype=RENDER_INDEX_DTYPE, order="C").reshape(-1)
        residual_values = np.asarray(
            residual_positions, dtype=POSITION_DTYPE, order="C"
        )
        if (
            vertex_values.ndim != 2
            or vertex_values.shape[1:] != (3,)
            or not np.isfinite(vertex_values).all()
        ):
            raise ValueError("render_surface_vertices_invalid")
        if (
            index_values.ndim != 1
            or len(index_values) % 3
            or (len(index_values) and (index_values.min() < 0 or index_values.max() >= len(vertex_values)))
        ):
            raise ValueError("render_surface_indices_invalid")
        if (
            residual_values.ndim != 2
            or residual_values.shape[1:] != (3,)
            or not np.isfinite(residual_values).all()
        ):
            raise ValueError("render_surface_residuals_invalid")
        if len(vertex_values) > MAX_SURFACE_VERTICES:
            raise ValueError("render_surface_vertex_capacity_exceeded")
        if len(index_values) > MAX_SURFACE_INDICES:
            raise ValueError("render_surface_index_capacity_exceeded")
        if len(residual_values) > MAX_RESIDUAL_PARTICLES:
            raise ValueError("render_surface_residual_capacity_exceeded")
        vertex_payload = vertex_values.tobytes(order="C")
        index_payload = index_values.tobytes(order="C")
        residual_payload = residual_values.tobytes(order="C")
        payload = vertex_payload + index_payload + residual_payload
        self.memory.buf[
            RENDER_VERTEX_OFFSET : RENDER_VERTEX_OFFSET + len(vertex_payload)
        ] = vertex_payload
        self.memory.buf[
            RENDER_INDEX_OFFSET : RENDER_INDEX_OFFSET + len(index_payload)
        ] = index_payload
        self.memory.buf[
            RENDER_RESIDUAL_OFFSET : RENDER_RESIDUAL_OFFSET + len(residual_payload)
        ] = residual_payload
        return self._write_header(
            mode=RENDER_MODE_SURFACE,
            frame_index=frame_index,
            simulation_time_s=simulation_time_s,
            particle_count=EXPECTED_PARTICLE_COUNT,
            vertex_count=len(vertex_values),
            index_count=len(index_values),
            residual_count=len(residual_values),
            payload=payload,
        )

    def read(self, *, expected_frame_index: int | None = None) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        (
            magic,
            version,
            mode,
            frame_index,
            simulation_time_s,
            particle_count,
            vertex_count,
            index_count,
            residual_count,
            payload_size,
            expected_checksum,
        ) = RENDER_HEADER.unpack(bytes(self.memory.buf[:RENDER_HEADER_SIZE]))
        if magic != RENDER_MAGIC or version != 2:
            raise ValueError("render_header_identity_mismatch")
        if expected_frame_index is not None and frame_index != expected_frame_index:
            raise ValueError(
                "render_frame_index_mismatch:"
                f"expected={expected_frame_index}:actual={frame_index}"
            )
        if particle_count != EXPECTED_PARTICLE_COUNT:
            raise ValueError("render_particle_count_mismatch")
        arrays: dict[str, np.ndarray]
        if mode == RENDER_MODE_PARTICLES:
            if vertex_count or index_count or residual_count or payload_size != PAYLOAD_SIZE:
                raise ValueError("render_particle_header_shape_mismatch")
            payload = bytes(
                self.memory.buf[RENDER_HEADER_SIZE : RENDER_HEADER_SIZE + PAYLOAD_SIZE]
            )
            arrays = {
                "positions": np.frombuffer(payload, dtype=POSITION_DTYPE)
                .reshape(POSITION_SHAPE)
                .copy()
            }
            representation = "particles"
        elif mode == RENDER_MODE_SURFACE:
            if (
                vertex_count > MAX_SURFACE_VERTICES
                or index_count > MAX_SURFACE_INDICES
                or index_count % 3
                or residual_count > MAX_RESIDUAL_PARTICLES
            ):
                raise ValueError("render_surface_header_capacity_invalid")
            vertex_size = vertex_count * 3 * POSITION_DTYPE.itemsize
            index_size = index_count * RENDER_INDEX_DTYPE.itemsize
            residual_size = residual_count * 3 * POSITION_DTYPE.itemsize
            if payload_size != vertex_size + index_size + residual_size:
                raise ValueError("render_surface_payload_size_mismatch")
            vertex_payload = bytes(
                self.memory.buf[RENDER_VERTEX_OFFSET : RENDER_VERTEX_OFFSET + vertex_size]
            )
            index_payload = bytes(
                self.memory.buf[RENDER_INDEX_OFFSET : RENDER_INDEX_OFFSET + index_size]
            )
            residual_payload = bytes(
                self.memory.buf[
                    RENDER_RESIDUAL_OFFSET : RENDER_RESIDUAL_OFFSET + residual_size
                ]
            )
            payload = vertex_payload + index_payload + residual_payload
            arrays = {
                "vertices": np.frombuffer(vertex_payload, dtype=POSITION_DTYPE)
                .reshape((vertex_count, 3))
                .copy(),
                "indices": np.frombuffer(index_payload, dtype=RENDER_INDEX_DTYPE).copy(),
                "residual_positions": np.frombuffer(
                    residual_payload, dtype=POSITION_DTYPE
                )
                .reshape((residual_count, 3))
                .copy(),
            }
            if index_count and arrays["indices"].max(initial=-1) >= vertex_count:
                raise ValueError("render_surface_index_out_of_range")
            representation = "surface_gpu"
        else:
            raise ValueError(f"render_mode_invalid:{mode}")
        actual_checksum = zlib.crc32(payload) & 0xFFFFFFFF
        if actual_checksum != expected_checksum:
            raise ValueError(
                "render_checksum_mismatch:"
                f"expected={expected_checksum}:actual={actual_checksum}"
            )
        return arrays, {
            "schema": RENDER_BRIDGE_SCHEMA,
            "representation": representation,
            "frame_index": int(frame_index),
            "simulation_time_s": float(simulation_time_s),
            "checksum_crc32": int(actual_checksum),
            "vertex_count": int(vertex_count),
            "index_count": int(index_count),
            "residual_count": int(residual_count),
        }

    def close(self) -> None:
        self.memory.close()

    def unlink(self) -> None:
        if not self.owner:
            raise RuntimeError("only_render_bridge_owner_may_unlink")
        self.memory.unlink()
        _LOCALLY_OWNED_MEMORY_NAMES.discard(self.memory._name)
