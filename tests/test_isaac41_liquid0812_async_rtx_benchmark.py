from tools.labutopia_fluid import run_isaac41_liquid0812_async_rtx_benchmark as benchmark


def test_50hz_render_schedule_covers_all_30hz_physics_states() -> None:
    render_count = benchmark._target_render_count(benchmark.EXPECTED_OBSERVATIONS)
    assert render_count == 1589
    mapping = [benchmark._physics_index_for_render(index) for index in range(render_count)]
    assert mapping[0] == 0
    assert mapping[-1] == benchmark.EXPECTED_OBSERVATIONS - 1
    assert set(mapping) == set(range(benchmark.EXPECTED_OBSERVATIONS))
    assert all(right >= left for left, right in zip(mapping, mapping[1:]))


def test_benchmark_defaults_to_reproducible_session_camera() -> None:
    args = benchmark.build_parser().parse_args([])
    assert args.camera_policy == "benchmark"
    assert args.width == 256
    assert args.height == 256
    assert args.save_full_video is False


def test_full_video_cuda_store_size_is_bounded() -> None:
    render_count = benchmark._target_render_count(benchmark.EXPECTED_OBSERVATIONS)
    byte_count = render_count * 3 * benchmark.DEFAULT_WIDTH * benchmark.DEFAULT_HEIGHT
    assert byte_count == 312_410_112
    assert byte_count < 300 * 1024 * 1024
