from argus_synchro.diagnosis.reduced_load_mode import (
    PROC_SPEED_NORMAL,
    PROC_SPEED_SLOW,
    ReducedLoadMode,
)


def test_point_count_thresholds_require_five_consecutive_frames() -> None:
    mode = ReducedLoadMode()
    mode.update_proc_speed(PROC_SPEED_SLOW)

    mode.update_pcd_nums(ReducedLoadMode.MANY_POINTS_THRESHOLD)
    for _ in range(ReducedLoadMode.PCD_ENABLE_THRESHOLD):
        mode.update_state()
    assert not mode.enabled

    mode.update_pcd_nums(ReducedLoadMode.MANY_POINTS_THRESHOLD + 1)
    for _ in range(ReducedLoadMode.PCD_ENABLE_THRESHOLD - 1):
        mode.update_state()
        assert not mode.enabled
    mode.update_state()
    assert mode.enabled

    mode.update_proc_speed(PROC_SPEED_NORMAL)
    mode.update_pcd_nums(ReducedLoadMode.FEW_POINTS_THRESHOLD)
    for _ in range(ReducedLoadMode.DISABLE_THRESHOLD):
        mode.update_state()
    assert mode.enabled

    mode.update_pcd_nums(ReducedLoadMode.FEW_POINTS_THRESHOLD - 1)
    for _ in range(ReducedLoadMode.DISABLE_THRESHOLD - 1):
        mode.update_state()
        assert mode.enabled
    mode.update_state()
    assert not mode.enabled
