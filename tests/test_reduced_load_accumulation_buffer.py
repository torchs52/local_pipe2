from collections import deque
from types import SimpleNamespace

import numpy as np

from argus_synchro.AccumulatePoints import trim_accumulated_frames
from argus_synchro.SubScrutinizer import initialize_accum_counter


def test_reduced_load_trim_keeps_newest_frames() -> None:
    frames = deque(
        (np.array([[frame]], dtype=np.float64) for frame in range(4)),
        maxlen=4,
    )

    trim_accumulated_frames(frames, 2)

    assert [frame.item() for frame in frames] == [2.0, 3.0]
    assert frames.maxlen == 4

    frames.append(np.array([[4]], dtype=np.float64))
    frames.append(np.array([[5]], dtype=np.float64))
    assert [frame.item() for frame in frames] == [2.0, 3.0, 4.0, 5.0]


def test_accumulation_buffers_use_larger_physical_limit() -> None:
    lidar_grid = SimpleNamespace(
        side_max=1.0,
        side_min=-1.0,
        fwd_max=1.0,
        fwd_min=-1.0,
        grid_size=1.0,
    )
    accumulation = SimpleNamespace(
        max_accumulated_frames=4,
        max_accumulated_frames_reduced_load=2,
        max_accumulated_frames_ground=3,
        max_accumulated_frames_ground_reduced_load=5,
    )

    _, _, _, points, ground, _ = initialize_accum_counter(
        lidar_grid,
        accumulation,
    )

    assert points.maxlen == 4
    assert ground.maxlen == 5


def test_trim_rejects_non_positive_limit() -> None:
    frames: deque[np.ndarray] = deque()

    try:
        trim_accumulated_frames(frames, 0)
    except ValueError as error:
        assert str(error) == "max accumulated frames must be greater than zero"
    else:
        raise AssertionError("zero max frames must be rejected")