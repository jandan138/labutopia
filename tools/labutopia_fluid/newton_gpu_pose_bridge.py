#!/usr/bin/env python3
"""Device-only pose composition for the Newton robot/fluid bridge.

Pure orchestration must not import this module.  The sealed Newton runtime
child loads it lazily through ``FrankaDynamicsController``.
"""

from __future__ import annotations

import warp as wp


@wp.kernel
def compose_body_local_pose(
    body_q: wp.array(dtype=wp.transform),
    body_index: int,
    local_pose: wp.transform,
    output_pose: wp.array(dtype=wp.transform),
):
    output_pose[0] = wp.transform_multiply(body_q[body_index], local_pose)
