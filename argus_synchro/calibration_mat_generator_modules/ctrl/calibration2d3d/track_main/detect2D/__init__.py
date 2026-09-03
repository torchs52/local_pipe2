import os
import pickle
from typing import Optional

import numpy as np
from numpy.typing import NDArray

# from argus_synchro.calibration_mat_generator_modules.ctrl.calibration2d3d.track_main.calib_person_tracker.calib_person_selector2d import proc_set
from argus_synchro.calibration_mat_generator_modules.ctrl.calibration2d3d.track_main.detect2D import (
    detect2d_2d3dcalib,
)
from argus_synchro.calibration_mat_generator_modules.ctrl.calibration2d3d.track_main.detect2D.bbox2D_postprocess import (
    bbox2D_postprocess,
)
from argus_synchro.calibration_mat_generator_modules.ctrl.calibration2d3d.track_main.detect2D.detect2d_axis_faster import (
    Detect2dAxisFaster,
)
from argus_synchro.calibration_mat_generator_modules.ctrl.calibration2d3d.track_main.detect2D.image_preprocess import (
    image_preprocess,
)
from argus_synchro.calibration_mat_generator_modules.ctrl.calibration2d3d.track_main.detect2D.person_tracker_SORT_2d import (
    proc2d_bboxtracker_recorder,
)
from argus_synchro.calibration_mat_generator_modules.ctrl.calibration2d3d.track_main.target_selector import (
    Tracking2dDataInterface,
    find_target_trajectory,
    reshape_bboxlist,
)
from argus_synchro.calibration_mat_generator_modules.utils.debugdata_store import (
    debug_store,
)
from argus_synchro.common.app_logger import AppLogger, AppLoggerFactory
from argus_synchro.config.app_config_calibration import AppConfigCalibration
from argus_synchro.detect2d import Detect2dDamoYoloOnnx


class detect2d_class:
    def __init__(
        self,
        Mc: NDArray[np.float64],
        app_config_calib: AppConfigCalibration,
        camera_index: int,
        app_logger_factory: AppLoggerFactory,
    ) -> None:
        self._logger: AppLogger = app_logger_factory.register_from_type(self.__class__)
        self.app_config_calib: AppConfigCalibration = app_config_calib
        self.verbose = not self.app_config_calib.default.print_disabled
        self.Mc = Mc

        # 内部状態リセット＆変数作成
        self.reset()

        # 画像事前処理
        self.image_preprocess_inst = image_preprocess(
            app_config_calib=app_config_calib, camera_index=camera_index
        )

        # YOLO人検知
        inference_config = detect2d_2d3dcalib.detect2d(
            onnx_model_path=app_config_calib.calib2d3d.Proc2d.yolo_modelpath
        )
        self._detect2d_batch_size: int = app_config_calib.dataCapture.Camera.count
        self.YOLOinst = Detect2dDamoYoloOnnx(
            conf_thresh=inference_config.conf_thresh,
            nms_thresh=inference_config.nms_thresh,
            onnx_model_path=inference_config.onnx_model_path,
            batch_size=self._detect2d_batch_size,
            app_logger_factory=app_logger_factory,
        )

        # BBox追跡、記録
        self.bbox_track_and_record = proc2d_bboxtracker_recorder(
            app_config_calib=app_config_calib,
            image_size_hw=(
                app_config_calib.dataCapture.Camera.sys_height,
                app_config_calib.dataCapture.Camera.sys_width,
            ),
            onnx_model_path=app_config_calib.calib2d3d.Proc2d.yolo_modelpath,
            camera_index=camera_index,
        )

        # bbox追跡後フィルタ処理
        self.bbox2d_postproc = bbox2D_postprocess(
            app_config_calib=app_config_calib,
            Mc=Mc,
            camera_index=camera_index,
            app_logger_factory=app_logger_factory,
        )

        # 人の軸推定
        self.detect2d_axis = Detect2dAxisFaster(
            Mc=Mc, debugflag=False, app_logger_factory=app_logger_factory
        )

        self.final_framesize = None

    def reset(self):
        self.last_bbox: NDArray[np.float64] | None = None
        self.yoloBB_all_yoloformat: list[NDArray[np.float64]] | None = None

    # -- 毎フレーム実行系 --

    def detect(self, data2d: tuple[NDArray[np.uint8], int]):
        # より適切な名前があるなら替えたい  timestamp_imgとdebug_indexの違いは？統一可能？
        (frame, timestamp_img) = data2d
        self.final_framesize = frame.shape

        # 画像事前処理
        debug_store("detect2d_frame", frame.copy(), timestamp_img)
        frame = self.image_preprocess_inst.apply(frame)
        debug_store("detect2d_frame_pred", frame.copy(), timestamp_img)
        # 人検知
        # DAMO-YOLOが3枚入力であるため、画像を複製
        frames: NDArray[np.uint8] = np.stack([frame] * self._detect2d_batch_size)
        yoloBB_all_yolofor_tuple = self.YOLOinst._inference(frames)
        # n_batch>1の場合、dummyの画像を入れて推論しているだけなので、最初の一つ目の結果だけ取り出す
        # batch sizeはscore(yoloresult_whole_tuple[1].shape[0])から取得
        if yoloBB_all_yolofor_tuple[1].shape[0] > 1:
            self.yoloBB_all_yoloformat = [
                yoloBB_all_yolofor_tuple[0][0],
                yoloBB_all_yolofor_tuple[1][0],
                yoloBB_all_yolofor_tuple[2][0],
                yoloBB_all_yolofor_tuple[3][0],
            ]
        else:
            self.yoloBB_all_yoloformat = list(yoloBB_all_yolofor_tuple)
        debug_store("yoloBB_all_yoloformat", self.yoloBB_all_yoloformat, timestamp_img)
        # bbox追跡前事前処理フィルタ
        self.yoloBB_all_yoloformat = self.bbox2d_postproc.filter_bbox(
            self.yoloBB_all_yoloformat,
        )
        debug_store(
            "yoloBB_all_yoloformat_filtered", self.yoloBB_all_yoloformat, timestamp_img
        )
        assert self.yoloBB_all_yoloformat is not None
        # bbox追跡・記録
        self.bbox_track_and_record.update(self.yoloBB_all_yoloformat, timestamp_img)

    def get_last_singleyoloBB(self) -> list[NDArray[np.float64]] | None:
        if self.yoloBB_all_yoloformat is None:
            return self.yoloBB_all_yoloformat
        return self.yoloBB_all_yoloformat[0][0][0]

    def get_tracking_results(self) -> Tracking2dDataInterface:
        res = self.bbox_track_and_record.get_rawresults()
        return Tracking2dDataInterface(
            trackingIDmetadata=res[0], trackingIDbboxlog=res[1]
        )

    def get_target_bbox(
        self, tracker_result_interface: Tracking2dDataInterface, frame_ix: int
    ) -> tuple[NDArray[np.float64], NDArray[np.int32]]:
        """
        使用bbox選択・取得
          追跡後フィルタ処理、校正作業者判定、bbox補正処理が終了した後のTracking2dDataInterface参照先データから
          bboxを選択、タイムスタンプと共に複数軌跡を統合して出力
        """
        idlist = find_target_trajectory(
            tracker_result_interface=tracker_result_interface, frame_index=frame_ix
        )

        return reshape_bboxlist(
            target_bboxhistory={
                key: data
                for key, data in tracker_result_interface.trackingIDbboxlog.items()
                if key in idlist
            }
        )

    # -- 対応点抽出系 --

    # 返り値：bbox中央座標のリスト、タイムスタンプ
    def extract_fromyolobb(
        self, tracker_result2d_interface: Tracking2dDataInterface, frame_ix: int
    ) -> tuple[NDArray[np.float64], NDArray[np.int32]]:
        # bbox_points, bbox_timestamps = self._extract_targetbbox_core(selectdata)
        bbox_points, bbox_timestamps = self.get_target_bbox(
            tracker_result_interface=tracker_result2d_interface, frame_ix=frame_ix
        )
        if len(bbox_points) == 0:
            return np.zeros((0, 4)), np.zeros(0, dtype=np.int32)
        # bbox_points: x1, y1, x2, y2形式
        assert len(bbox_points.shape) == 2, f"{bbox_points.shape=}"
        assert bbox_points.shape[1] == 4, f"{bbox_points.shape=}"
        corner2d = np.hstack(
            [
                bbox_points[:, [0, 2]].mean(axis=1).reshape(-1, 1),
                bbox_points[:, [1, 3]].mean(axis=1).reshape(-1, 1),
            ]
        )
        return corner2d, bbox_timestamps

    def extract_withaxis(
        self,
        rvec,
        tvec,
        tracker_result2d_interface: Tracking2dDataInterface,
        frame_ix: int,
    ) -> tuple[NDArray[np.float64], NDArray[np.int32]]:
        assert self.final_framesize is not None

        bbox_points, bbox_timestamps = self.get_target_bbox(
            tracker_result_interface=tracker_result2d_interface, frame_ix=frame_ix
        )
        # bbox_points: x1, y1, x2, y2形式
        assert len(bbox_points.shape) == 2
        assert bbox_points.shape[1] == 4

        # bbox: x1, x2, y1, y2形式を期待
        (cornerlist2d, tslist2d) = self.detect2d_axis.extract_results_core(
            rvec=rvec,
            tvec=tvec,
            width=self.final_framesize[1],
            height=self.final_framesize[0],
            margin=5,
            accum_bbox=bbox_points[:, [0, 2, 1, 3]],
            accum_bbox_ts=bbox_timestamps,
            Mc=self.Mc,
        )
        return (cornerlist2d, tslist2d)

    def make_monitorimage(
        self, data2d: tuple[NDArray[np.uint8], int]
    ) -> NDArray[np.uint8]:
        frame_draw = data2d[0].copy()

        frame_draw = proc2d_bboxtracker_recorder.draw_detection(
            yoloresult_whole=self.yoloBB_all_yoloformat,
            frame=frame_draw,
            image_size_hw=(frame_draw.shape[0], frame_draw.shape[1]),
        )
        frame_draw = self.bbox_track_and_record.draw_mot(frame_sortview=frame_draw)
        return frame_draw

    def save_debugdata(self, openflag: str = "wb"):
        # 追跡情報保存
        self.bbox_track_and_record.save_results_debug(openflag=openflag)
        # 結果bboxデータ保存
        with open("bbox_results.pickle", mode=openflag) as wbf:
            pickle.dump(self.bbox_track_and_record.get_rawresults(), wbf)
