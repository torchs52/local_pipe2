# ruff: noqa: SLF001

from __future__ import annotations

from typing import Any, cast

import numpy as np

from argus_synchro.calibration_mat_generator_modules.ctrl.calibcheck2d3d import (
    Scene_CalibCheck2d3d,
    calibcheck2d3d,
)
from argus_synchro.calibration_mat_generator_modules.ctrl.calibration2d3d.track_main.interface_definition import (
    Tracking2dDataInterface,
    Tracking3dDataInterface,
    tracking2d_dataclass,
    tracking3d_dataclass,
)
from argus_synchro.config.app_config import SceneDescriptionConf


class _LoggerStub:
    def info(self, message: str) -> None:
        del message


def _controller(camera_count: int = 1) -> calibcheck2d3d:
    controller = cast(calibcheck2d3d, object.__new__(calibcheck2d3d))
    controller._logger = cast(Any, _LoggerStub())
    controller._evaluation_camera_count = camera_count
    controller.width = 100
    controller.height = 100
    controller._evaluation_intrinsics = np.array(
        [[100.0, 0.0, 50.0], [0.0, 100.0, 50.0], [0.0, 0.0, 1.0]],
        dtype=np.float32,
    )
    controller.rtvec_mat = [
        (
            np.zeros((3, 1), dtype=np.float64),
            np.zeros((3, 1), dtype=np.float64),
            np.eye(4, dtype=np.float64),
        )
        for _ in range(camera_count)
    ]
    controller.EVAL_FRAME_STRIDE = 1
    controller.USE_LEGACY_LIKE_METRIC = True
    return controller


def _tracking_3d(
    frame_ix: int, bbox: tuple[float, float, float, float]
) -> Tracking3dDataInterface:
    metadata = tracking3d_dataclass(
        accum_track_length=3.0,
        final_xy=(0.0, 0.0),
        dist_from_camera_min=1.0,
        dist_from_camera_max=2.0,
        frame_ix_min=frame_ix,
        frame_ix_max=frame_ix,
        frame_ix_lastmove=frame_ix,
        frame_evval_min=0.0,
        frame_evval_max=1.0,
        workarea_count=30,
        is_alive=True,
    )
    return Tracking3dDataInterface({1: metadata}, {1: [(frame_ix, bbox)]})


def _tracking_2d(
    frame_ix: int, bbox: tuple[float, float, float, float]
) -> Tracking2dDataInterface:
    metadata = tracking2d_dataclass(
        accum_track_length=50.0,
        final_xy=(0.0, 0.0),
        xymin=(bbox[0], bbox[1]),
        xymax=(bbox[2], bbox[3]),
        frame_ix_min=frame_ix,
        frame_ix_max=frame_ix,
        frame_ix_lastmove=frame_ix,
        frame_evval_min=0.0,
        frame_evval_max=1.0,
        workarea_count=10,
        is_alive=True,
    )
    return Tracking2dDataInterface({1: metadata}, {1: [(frame_ix, bbox)]})


def test_evaluate_2d3d_reports_reason_9_when_3d_is_out_of_view() -> None:
    controller = _controller()

    scores, reasons = controller.evaluate_2d3d(
        _tracking_3d(0, (10.0, -1.0, 12.0, 1.0)),
        [_tracking_2d(0, (30.0, 30.0, 70.0, 70.0))],
        zvalues=(5.0, 10.0),
    )

    assert scores == [0.0]
    assert reasons == [9]


def test_evaluate_2d3d_reports_reason_10_without_common_frame() -> None:
    controller = _controller()

    scores, reasons = controller.evaluate_2d3d(
        _tracking_3d(0, (-1.0, -1.0, 1.0, 1.0)),
        [_tracking_2d(1, (30.0, 30.0, 70.0, 70.0))],
        zvalues=(5.0, 10.0),
    )

    assert scores == [0.0]
    assert reasons == [10]


def test_evaluate_2d3d_scores_common_overlapping_frame() -> None:
    controller = _controller()
    controller.evaluate_bbox_overlap_scenedesc = lambda *_args: 1.0

    scores, reasons = controller.evaluate_2d3d(
        _tracking_3d(0, (-1.0, -1.0, 1.0, 1.0)),
        [_tracking_2d(0, (30.0, 30.0, 70.0, 70.0))],
        zvalues=(5.0, 10.0),
    )

    assert scores == [1.0]
    assert reasons == [0]
    assert controller.judge_calibration_result(scores, threshold=0.5) == [True]


def test_evaluate_2d3d_reports_reason_11_without_valid_score() -> None:
    controller = _controller()
    controller.evaluate_bbox_overlap_scenedesc = cast(Any, lambda *_args: None)

    scores, reasons = controller.evaluate_2d3d(
        _tracking_3d(0, (-1.0, -1.0, 1.0, 1.0)),
        [_tracking_2d(0, (30.0, 30.0, 70.0, 70.0))],
        zvalues=(5.0, 10.0),
    )

    assert scores == [0.0]
    assert reasons == [11]


def test_bbox_overlap_evaluation_uses_real_scene_matching() -> None:
    controller = _controller()
    controller.VIRTUAL_BBOX_XY_OFFSETS = ((0.0, 0.0),)
    controller.scenedesc_calibcheck = Scene_CalibCheck2d3d.create_for_evaluation(
        scene_conf=SceneDescriptionConf(
            coarse_lo=0.01,
            coarse_hi=100.0,
            k_min=0.3,
            h_ref_px=80,
            lo_gain=1.0,
            hi_gain=1.0,
            lo_floor=0.01,
            hi_ceil=100.0,
            vertical_w_iou=0.0,
            vertical_w_scale=0.0,
            vertical_w_phi=0.0,
            final_threshold=1000.0,
            use_human_gate=False,
            H_min=1.2,
            H_max=2.2,
            W_min=0.2,
            W_max=1.0,
            D_min=0.2,
            D_max=1.0,
            tall_ratio_min=1.5,
        ),
        camera_intrinsics=controller._evaluation_intrinsics,
        image_width=controller.width,
        image_height=controller.height,
    )

    score = controller.evaluate_bbox_overlap_scenedesc(
        np.array([-1.0, -1.0, 5.0, 1.0, 1.0, 6.0], dtype=np.float32),
        np.array([30.0, 30.0, 70.0, 70.0], dtype=np.float32),
        camera_index=0,
    )

    assert score == 1.0


def test_data_evaluation_preserves_earlier_per_camera_reason() -> None:
    controller = _controller(camera_count=2)
    controller.calibcheck2d3d_conf = cast(
        Any, type("Config", (), {"score_value_threshold": 0.5})()
    )
    controller.EVAL_ZVALUES = (5.0, 10.0)
    tracking_3d = _tracking_3d(0, (-1.0, -1.0, 1.0, 1.0))
    tracking_2d = [
        _tracking_2d(0, (30.0, 30.0, 70.0, 70.0)),
        _tracking_2d(0, (30.0, 30.0, 70.0, 70.0)),
    ]
    controller.validate_recorded_bbox_logs = lambda: [3, 0]
    controller.track_3dbbox = lambda: tracking_3d
    controller.track_2dbbox = lambda: tracking_2d
    controller.validate_tracked_bboxes = lambda *_args: [0, 0]
    controller.evaluate_2d3d = lambda *_args, **_kwargs: ([1.0, 1.0], [0, 0])

    reasons, results = controller.data_evaluation_process()

    assert reasons == [3, 0]
    assert results == [False, True]
