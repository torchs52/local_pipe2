# ruff: noqa: SLF001

from __future__ import annotations

from typing import Any, cast

from argus_synchro.calibration_mat_generator_modules.ctrl.calibcheck2d3d import (
    calibcheck2d3d,
)
from argus_synchro.calibration_mat_generator_modules.ctrl.calibration2d3d.track_main.interface_definition import (
    Tracking2dDataInterface,
    Tracking3dDataInterface,
    tracking2d_dataclass,
    tracking3d_dataclass,
)


class _LoggerStub:
    def info(self, message: str) -> None:
        del message


def _controller() -> calibcheck2d3d:
    controller = cast(calibcheck2d3d, object.__new__(calibcheck2d3d))
    controller._logger = cast(Any, _LoggerStub())
    controller._evaluation_camera_count = 3
    controller.THRESH_3DBBOX_TRACKING_IDCOUNT = 1
    controller.THRESH_2DBBOX_TRACKING_IDCOUNT = 1
    return controller


def _tracking_3d(
    *, frames: int, movement: float, workarea_count: int
) -> Tracking3dDataInterface:
    metadata = tracking3d_dataclass(
        accum_track_length=movement,
        final_xy=(movement, 0.0),
        dist_from_camera_min=1.0,
        dist_from_camera_max=2.0,
        frame_ix_min=0,
        frame_ix_max=frames,
        frame_ix_lastmove=frames,
        frame_evval_min=0.0,
        frame_evval_max=1.0,
        workarea_count=workarea_count,
        is_alive=True,
    )
    return Tracking3dDataInterface({1: metadata}, {1: []})


def _tracking_2d(*, frames: int, movement: float) -> Tracking2dDataInterface:
    metadata = tracking2d_dataclass(
        accum_track_length=movement,
        final_xy=(movement, 0.0),
        xymin=(0.0, 0.0),
        xymax=(movement, 1.0),
        frame_ix_min=0,
        frame_ix_max=frames,
        frame_ix_lastmove=frames,
        frame_evval_min=0.0,
        frame_evval_max=1.0,
        workarea_count=frames,
        is_alive=True,
    )
    return Tracking2dDataInterface({1: metadata}, {1: []})


def test_tracking_validation_reports_reason_4_for_short_3d_track() -> None:
    controller = _controller()

    reasons = controller.validate_tracked_bboxes(
        _tracking_3d(frames=29, movement=3.0, workarea_count=30),
        [_tracking_2d(frames=10, movement=50.0) for _ in range(3)],
    )

    assert reasons == [4, 4, 4]


def test_tracking_validation_reports_reason_5_per_camera() -> None:
    controller = _controller()

    reasons = controller.validate_tracked_bboxes(
        _tracking_3d(frames=30, movement=3.0, workarea_count=30),
        [
            _tracking_2d(frames=10, movement=50.0),
            _tracking_2d(frames=9, movement=50.0),
            _tracking_2d(frames=10, movement=49.0),
        ],
    )

    assert reasons == [0, 5, 5]
