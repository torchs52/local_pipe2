# ruff: noqa: PLR2004, SLF001

from __future__ import annotations

from typing import Any, cast

import numpy as np

from argus_synchro.calibration_mat_generator_modules.ctrl.calibcheck2d3d import (
    calibcheck2d3d,
)


class _LoggerStub:
    def info(self, message: str) -> None:
        del message


def _controller() -> calibcheck2d3d:
    controller = cast(calibcheck2d3d, object.__new__(calibcheck2d3d))
    controller._logger = cast(Any, _LoggerStub())
    controller._evaluation_camera_count = 3
    controller.FRAME_INFO_MAXLEN = 10
    controller.THRESH_3DBBOX_COUNT_PER_FRAME = 1
    controller.THRESH_3DBBOX_COUNT_MEAN_RATIO = 0.5
    controller.THRESH_2DBBOX_COUNT_PER_FRAME = 1
    controller.THRESH_2DBBOX_COUNT_MEAN_RATIO = 0.5
    controller.frame_info = []
    return controller


def _yoloresult(valid_count: int) -> list[np.ndarray]:
    return [
        np.zeros((1, 4), dtype=np.float32),
        np.zeros(1, dtype=np.float32),
        np.zeros(1, dtype=np.float32),
        np.array(valid_count, dtype=np.int32),
    ]


def test_bbox_log_validation_reports_missing_3d_for_all_cameras() -> None:
    controller = _controller()
    controller.record_bbox1f(
        np.zeros((0, 6), dtype=np.float64),
        [_yoloresult(1), _yoloresult(1), _yoloresult(1)],
    )

    assert controller.validate_recorded_bbox_logs() == [2, 2, 2]


def test_bbox_log_validation_reports_missing_2d_per_camera() -> None:
    controller = _controller()
    controller.record_bbox1f(
        np.ones((1, 6), dtype=np.float64),
        [_yoloresult(1), _yoloresult(0), _yoloresult(1)],
    )

    assert controller.validate_recorded_bbox_logs() == [0, 3, 0]


def test_bbox_log_recording_keeps_configured_tail() -> None:
    controller = _controller()
    controller.FRAME_INFO_MAXLEN = 2
    for valid_count in range(3):
        controller.record_bbox1f(
            np.ones((1, 6), dtype=np.float64),
            [_yoloresult(valid_count)] * 3,
        )

    assert len(controller.frame_info) == 2
    assert int(controller.frame_info[0][0][0][3]) == 1
    assert int(controller.frame_info[1][0][0][3]) == 2


def test_reason_mappings_match_shi_contract() -> None:
    controller = _controller()

    assert controller.error_reason_to_string(11) == "カメラとLiDARの評価可能な対象物なし"
    assert [controller.error_reason_to_ui_errornum(reason) for reason in range(1, 12)] == [
        3,
        3,
        3,
        5,
        5,
        5,
        5,
        5,
        4,
        3,
        4,
    ]
