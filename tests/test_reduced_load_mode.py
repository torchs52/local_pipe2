from argus_synchro.diagnosis.reduced_load_mode import (
    PROC_SPEED_NORMAL,
    PROC_SPEED_SLOW,
    ReducedLoadMode,
)


def test_point_count_thresholds_require_five_consecutive_frames() -> None:
    mode = ReducedLoadMode()
    mode.update_proc_speed(PROC_SPEED_SLOW)

    mode.update_pcd_nums(mode.many_points_threshold)
    for _ in range(ReducedLoadMode.PCD_ENABLE_THRESHOLD):
        mode.update_state()
    assert not mode.enabled

    mode.update_pcd_nums(mode.many_points_threshold + 1)
    for _ in range(ReducedLoadMode.PCD_ENABLE_THRESHOLD - 1):
        mode.update_state()
        assert not mode.enabled
    mode.update_state()
    assert mode.enabled

    mode.update_proc_speed(PROC_SPEED_NORMAL)
    mode.update_pcd_nums(mode.few_points_threshold)
    for _ in range(ReducedLoadMode.DISABLE_THRESHOLD):
        mode.update_state()
    assert mode.enabled

    mode.update_pcd_nums(mode.few_points_threshold - 1)
    for _ in range(ReducedLoadMode.DISABLE_THRESHOLD - 1):
        mode.update_state()
        assert mode.enabled
    mode.update_state()
    assert not mode.enabled


def test_point_count_thresholds_are_configurable_ratios() -> None:
    mode = ReducedLoadMode()
    expected_many_points = 20_000
    expected_few_points = 10_000

    mode.configure(0.5, 0.25)

    assert mode.many_points_threshold == expected_many_points
    assert mode.few_points_threshold == expected_few_points
