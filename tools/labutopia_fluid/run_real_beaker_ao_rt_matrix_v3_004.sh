#!/usr/bin/env bash
set -uo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
isaac_python="/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python3.10"
runner="$repo_root/tools/labutopia_fluid/run_real_beaker_omniglass_replay.py"
pipe_wrapper="$repo_root/tools/labutopia_fluid/run_sealed_child_with_pipe_log.sh"
experiment_id="real_beaker_ao_rt_matrix_v3_20260712_004"
aggregate_root="$repo_root/docs/labutopia_lab_poc/evidence_manifests/$experiment_id"
authority_root="$repo_root/docs/labutopia_lab_poc/evidence_manifests/fluid_spike_real_beaker_static_hold_support_aligned_v1_20260712/accepted_authority_P4096_S2"
implementation_identity="$repo_root/docs/labutopia_lab_poc/evidence_manifests/real_beaker_ao_rt_matrix_v3_20260712_004_implementation_identity.json"
pre_freeze="$repo_root/docs/labutopia_lab_poc/evidence_manifests/real_beaker_ao_rt_matrix_v3_20260712_004_protected_tree_freeze_pre.json"

replicates=(
    A A A A
    B B B B
    C C C C
    D D D D
)
order_indices=(
    0 1 2 3
    0 1 2 3
    0 1 2 3
    0 1 2 3
)
variants=(
    AO0_RT4_CONTROL AO0_RT12 AO1_RT4 AO1_RT12
    AO1_RT12 AO1_RT4 AO0_RT12 AO0_RT4_CONTROL
    AO0_RT12 AO1_RT12 AO0_RT4_CONTROL AO1_RT4
    AO1_RT4 AO0_RT4_CONTROL AO1_RT12 AO0_RT12
)

usage() {
    printf 'usage: %s [--print-plan | --from <0..15>]\n' "$0" >&2
}

print_plan=false
from_index=0
case $# in
    0)
        ;;
    1)
        if [[ "$1" != "--print-plan" ]]; then
            usage
            exit 64
        fi
        print_plan=true
        ;;
    2)
        if [[ "$1" != "--from" || ! "$2" =~ ^([0-9]|1[0-5])$ ]]; then
            usage
            exit 64
        fi
        from_index=$2
        ;;
    *)
        usage
        exit 64
        ;;
esac

for sequence in "${!variants[@]}"; do
    replicate=${replicates[$sequence]}
    order_index=${order_indices[$sequence]}
    variant=${variants[$sequence]}
    cell_name="${replicate}_${order_index}_${variant}"
    cell_root="$aggregate_root/cells/$cell_name"
    log_path="/tmp/labutopia-formal-004-${cell_name}.log"
    if $print_plan; then
        printf 'PLAN\t%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$sequence" "$replicate" "$order_index" "$variant" \
            "$cell_root" "$log_path"
    fi
done

if $print_plan; then
    exit 0
fi

for required in "$isaac_python" "$runner" "$pipe_wrapper" "$implementation_identity" "$pre_freeze"; do
    if [[ ! -f "$required" || -L "$required" ]]; then
        printf 'formal regular input missing or symlinked: %s\n' "$required" >&2
        exit 66
    fi
done
if [[ ! -d "$authority_root" || -L "$authority_root" ]]; then
    printf 'formal authority missing or symlinked: %s\n' "$authority_root" >&2
    exit 66
fi
if ! "$isaac_python" "$runner" --render-diagnostic-launch-preflight-only >/dev/null; then
    printf 'formal identity or protected freeze verification failed\n' >&2
    exit 66
fi

for sequence in "${!variants[@]}"; do
    if (( sequence < from_index )); then
        continue
    fi
    replicate=${replicates[$sequence]}
    order_index=${order_indices[$sequence]}
    variant=${variants[$sequence]}
    cell_name="${replicate}_${order_index}_${variant}"
    cell_root="$aggregate_root/cells/$cell_name"
    log_path="/tmp/labutopia-formal-004-${cell_name}.log"

    printf 'CELL_START\t%s\t%s\n' "$sequence" "$cell_name"
    "$pipe_wrapper" --log "$log_path" -- \
        "$isaac_python" "$runner" \
        --accepted-authority-bundle "$authority_root" \
        --out-root "$cell_root" \
        --candidates OMNI_REF_DISPLAY_FILL \
        --visual-prototype-display-fill-only \
        --visual-prototype-lighting-variant C_CONTROL \
        --visual-prototype-render-diagnostic-variant "$variant" \
        --render-diagnostic-experiment-id "$experiment_id" \
        --render-diagnostic-replicate "$replicate" \
        --render-diagnostic-order-index "$order_index" \
        --headless \
        --width 960 \
        --height 540 \
        --video-fps 15 \
        --warmup-updates 8 \
        --camera-warmup-updates 8
    status=$?
    if (( status != 0 )); then
        printf 'CELL_FAIL\t%s\t%s\t%s\t%s\n' \
            "$sequence" "$cell_name" "$status" "$log_path" >&2
        exit "$status"
    fi
    printf 'CELL_DONE\t%s\t%s\t%s\n' "$sequence" "$cell_name" "$log_path"
done
