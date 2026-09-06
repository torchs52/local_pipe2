import copy
from os import path
from pathlib import Path
from time import sleep
from collections.abc import Callable

import cv2
import numpy as np
from numpy.typing import NDArray

from argus_synchro.calibration_mat_generator_modules.ctrl.calibcheck2d3d import (
    calibcheck_detection_2d3d,
)
from argus_synchro.calibration_mat_generator_modules.ctrl.calibcheck2d3d.SceneDesc import (
    Scene,
)

# デバッグ用パラメータ設定
from argus_synchro.calibration_mat_generator_modules.ctrl.calibcheck2d3d.debuginfo_and_functions import (
    conbine3d3d,
    conv_intarr,
    draw_multibbox,
    internal_make_BB,
    read_rtvec,
)
from argus_synchro.calibration_mat_generator_modules.ctrl.calibration2d3d.track_main.detect2D.detect2d_2d3dcalib import (
    detect2d,
)
from argus_synchro.calibration_mat_generator_modules.ctrl.calibration2d3d.track_main.detect2D.person_tracker_SORT_2d import (
    bbox2d_mot_tracker_wrapper,
)
from argus_synchro.calibration_mat_generator_modules.ctrl.calibration2d3d.track_main.detect3D.person_tracker_SORT_3d import (
    bbox3d_mot_tracker_wrapper,
)
from argus_synchro.calibration_mat_generator_modules.ctrl.calibration2d3d.track_main.interface_definition import (
    Tracking2dDataInterface,
    Tracking3dDataInterface,
    tracking2d_dataclass,
    tracking3d_dataclass,
)

# 型定義のみ
from argus_synchro.calibration_mat_generator_modules.ctrl.data_capture import (
    data_capture,
)
from argus_synchro.calibration_mat_generator_modules.ctrl.data_capture.datacapture_local import (
    datacapture_class,
)
from argus_synchro.calibration_mat_generator_modules.facade import CalibrationUIGodot
from argus_synchro.calibration_mat_generator_modules.utils import utils3d
from argus_synchro.calibration_mat_generator_modules.utils.GrayImageLUT import (
    GrayImageLUT,
)

# ARGUSシステム制御関連
from argus_synchro.common import paths
from argus_synchro.common.app_logger import AppLogger, AppLoggerFactory
from argus_synchro.config.app_config import SceneDescriptionConf
from argus_synchro.config.app_config_calibration import (
    AppConfigCalibration,
    CalibCheck2d3dConf,
    DataCaptureConf,
)
from argus_synchro.device.camera.helper import CameraHelper
from argus_synchro.detect2d import Detect2dDamoYoloOnnx
from argus_synchro.diagnosis.calibcheck2d3d_result_diagnosis import (
    CameraCalibCheckStatusDiagnosis,
)
from argus_synchro.diagnosis.error_diagnosis import ResultDiagnosis
from argus_synchro.message.calib_fifo_message import FIFOData
from argus_synchro.provider.image import Mcde7000UndistortImageProvider
from argus_synchro.shared_app_config import SharedAppConfig
from argus_synchro.shared_errors import SharedErrors, StateErrorDIndex
from argus_synchro.shared_excepts import SharedExcepts

_logger: AppLogger = AppLoggerFactory.from_name("calibcheck2d3d")

VIRTUAL_BBOX_XY_OFFSETS: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (-3.0, 0.0),
    (3.0, 0.0),
    (0.0, -3.0),
    (0.0, 3.0),
)
BBOX_SHRINK_FACTOR: float = 1.0
BBOX_CENTER_DIFF_RATIO_THRESHOLD: float = 0.7


def log_register(app_logger_factory: AppLoggerFactory) -> None:
    app_logger_factory.append_logger(_logger)
    calibcheck_detection_2d3d.log_register(app_logger_factory)


class Scene_CalibCheck2d3d(Scene):
    def __init__(
        self,
        scene_conf: SceneDescriptionConf,
        app_config_calib: AppConfigCalibration,
        file_io_error_reporter: Callable[[str, str, Exception], None] | None = None,
    ) -> None:
        super().__init__(scene_conf)
        self.app_config_calib: AppConfigCalibration = app_config_calib
        self._image_width = app_config_calib.calibCheck2d3d.image_w
        self._image_height = app_config_calib.calibCheck2d3d.image_h

        camera_intrinsics_path = self.app_config_calib.calibCheck2d3d.camera_intrinsics_path
        try:
            (
                _,
                _,
                _,
                _,
                self._ncm1,
            ) = CameraHelper.read_fisheye_param(camera_intrinsics_path)
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
            if file_io_error_reporter is not None:
                file_io_error_reporter(
                    camera_intrinsics_path,
                    "read calibcheck2d3d camera intrinsics JSON",
                    error,
                )
            raise

    @classmethod
    def create_for_evaluation(
        cls,
        scene_conf: SceneDescriptionConf,
        camera_intrinsics: NDArray[np.float32],
        image_width: int,
        image_height: int,
    ) -> "Scene_CalibCheck2d3d":
        instance = cls.__new__(cls)
        Scene.__init__(instance, scene_conf)
        instance._ncm1 = camera_intrinsics
        instance._image_width = image_width
        instance._image_height = image_height
        return instance

    def integrate2d3d_calibcheck(
        self,
        rvec: NDArray[np.float64],
        tvec: NDArray[np.float64],
        boxpoints: NDArray[np.float64],
        minmax3ds: NDArray[np.float64],
        bbox2d: NDArray[np.float32],
        yolo_classes: NDArray[np.int32],
        n_clusters: int,
        bbox2d_detection_count: int,
        method: str = "center",
    ) -> dict[int, str]:
        width: int = self._image_width
        height: int = self._image_height
        ncm1: NDArray[np.float32] = self._ncm1

        integrated_retults_2d3d: dict[int, str] = {}

        box3ds_reproj: NDArray[np.float64] = np.zeros(
            (n_clusters * 8, 2), dtype=np.float64
        )
        if n_clusters != 0:
            box3ds_reproj = cv2.projectPoints(
                np.array([boxpoints]),
                rvec,
                tvec,
                ncm1,
                np.zeros((1, 5)),
            )[0].squeeze(1)
            assert np.array([boxpoints]).shape[0] == 1

            extrinsic_matrix = np.hstack(
                [cv2.Rodrigues(rvec)[0], tvec.reshape(3, 1)]
            )
            homogeneous_points = np.hstack(
                [boxpoints, np.ones((boxpoints.shape[0], 1))]
            ).T
            camera_coordinate_pts = extrinsic_matrix @ homogeneous_points
            camera_coordin_z = camera_coordinate_pts[2]

            BBOX_VERTEX_POINTS = 8
            camera_coordin_z_bboxset = camera_coordin_z.reshape(
                -1, BBOX_VERTEX_POINTS
            )
            camera_coordin_z_bboxset_flag = np.all(
                camera_coordin_z_bboxset > 0, axis=1
            )
            box3ds_zfilter = np.repeat(
                camera_coordin_z_bboxset_flag, BBOX_VERTEX_POINTS
            )

            box3ds_reproj[box3ds_zfilter == 0] = -1e6

            for i in range(int(bbox2d_detection_count)):
                if yolo_classes[i] == 0:
                    box2d_single: NDArray[np.float32] = bbox2d[i]
                    index: int = self.get_human_3bb(
                        box2d_single,
                        int(width),
                        int(height),
                        box3ds_reproj,
                        n_clusters,
                        method,
                    )
                    if index >= 0:
                        if self.use_human_gate:
                            if self.passes_human_size(minmax3ds[index]):
                                integrated_retults_2d3d[index] = "HUMAN"
                        else:
                            integrated_retults_2d3d[index] = "HUMAN"

        return integrated_retults_2d3d


class calibcheck2d_bboxtracker_recorder:
    def __init__(
        self,
        app_config_calib: AppConfigCalibration,
        image_size_hw: tuple[int, int],
        camera_index: int,
    ) -> None:
        proc2d_conf = app_config_calib.calib2d3d.Proc2d
        self.mot_tracker = bbox2d_mot_tracker_wrapper(
            lost_track_buffer=int(proc2d_conf.lost_track_buffer),
            frame_rate=proc2d_conf.tracking_frame_rate,
            track_activation_threshold=proc2d_conf.track_activation_threshold,
            minimum_consecutive_frames=int(proc2d_conf.minimum_consecutive_frames),
            minimum_iou_threshold=proc2d_conf.minimum_iou_threshold,
        )
        self.image_size_hw = image_size_hw
        self.trackingID_data = {}
        self.trackingID_bboxlog = {}
        self.evLUT2D = GrayImageLUT(
            A_X=proc2d_conf.cam_workareadef_img_coord_A_X[camera_index],
            B_X=proc2d_conf.cam_workareadef_img_coord_B_X[camera_index],
            A_Y=proc2d_conf.cam_workareadef_img_coord_A_Y[camera_index],
            B_Y=proc2d_conf.cam_workareadef_img_coord_B_Y[camera_index],
            IMAGE_PATH=proc2d_conf.cam_workareadef_img_path[camera_index],
            A_ETA=proc2d_conf.cam_workareadef_img_coord_A_ETA[camera_index],
            B_ETA=proc2d_conf.cam_workareadef_img_coord_B_ETA[camera_index],
            DEFAULT_VALUE=proc2d_conf.cam_workareadef_img_val_DEFAULT[camera_index],
        )

    @staticmethod
    def _calc_L2norm(a: tuple[float, float], b: tuple[float, float]) -> float:
        return float(np.sqrt(np.sum((np.array(a) - np.array(b)) ** 2)))

    def update(self, yoloresult_whole: list[NDArray], frame_ix: int) -> None:
        tracker_result, _ = self.mot_tracker.update(
            yoloresult_whole=yoloresult_whole,
            image_w=self.image_size_hw[1],
            image_h=self.image_size_hw[0],
            frame_ix=frame_ix,
        )
        for x1, y1, x2, y2, _prob, tracker_id in tracker_result:
            xc, yc = (x1 + x2) / 2, (y1 + y2) / 2
            is_workarea = 1 if self.evLUT2D.evaluate(xc, yc) else 0
            if tracker_id not in self.trackingID_data:
                self.trackingID_data[tracker_id] = tracking2d_dataclass(
                    accum_track_length=0,
                    final_xy=(xc, yc),
                    xymin=(min(x1, x2), min(y1, y2)),
                    xymax=(max(x1, x2), max(y1, y2)),
                    frame_ix_min=frame_ix,
                    frame_ix_max=frame_ix,
                    frame_ix_lastmove=frame_ix,
                    frame_evval_min=float(is_workarea),
                    frame_evval_max=float(is_workarea),
                    workarea_count=is_workarea,
                    is_alive=True,
                    is_tracking_target=True,
                )
                self.trackingID_bboxlog[tracker_id] = []
            else:
                metadata = self.trackingID_data[tracker_id]
                frame_movelen = self._calc_L2norm(metadata.final_xy, (xc, yc))
                metadata.accum_track_length += frame_movelen
                metadata.final_xy = (xc, yc)
                metadata.frame_ix_max = frame_ix
                if frame_movelen > 1e-6:
                    metadata.frame_ix_lastmove = frame_ix
                metadata.workarea_count += is_workarea
            self.trackingID_bboxlog[tracker_id].append(
                (frame_ix, (x1, y1, x2, y2))
            )

    def get_rawresults(self) -> Tracking2dDataInterface:
        return Tracking2dDataInterface(self.trackingID_data, self.trackingID_bboxlog)


class calibcheck3d_bboxtracker_recorder:
    def __init__(
        self,
        app_config_calib: AppConfigCalibration,
        camera_index: int,
    ) -> None:
        proc3d_conf = app_config_calib.calib2d3d.Proc3d
        self.mot_tracker = bbox3d_mot_tracker_wrapper(
            lost_track_buffer=int(proc3d_conf.lost_track_buffer),
            frame_rate=proc3d_conf.tracking_frame_rate,
            track_activation_threshold=proc3d_conf.track_activation_threshold,
            minimum_consecutive_frames=int(proc3d_conf.minimum_consecutive_frames),
            minimum_iou_threshold=proc3d_conf.minimum_iou_threshold,
        )
        self.trackingID_data = {}
        self.trackingID_bboxlog = {}
        self.evLUT3D = GrayImageLUT(
            A_X=proc3d_conf.lid_workareadef_img_coord_A_X[camera_index],
            B_X=proc3d_conf.lid_workareadef_img_coord_B_X[camera_index],
            A_Y=proc3d_conf.lid_workareadef_img_coord_A_Y[camera_index],
            B_Y=proc3d_conf.lid_workareadef_img_coord_B_Y[camera_index],
            IMAGE_PATH=proc3d_conf.lid_workareadef_img_path[camera_index],
            A_ETA=proc3d_conf.lid_workareadef_img_coord_A_ETA[camera_index],
            B_ETA=proc3d_conf.lid_workareadef_img_coord_B_ETA[camera_index],
            DEFAULT_VALUE=proc3d_conf.lid_workareadef_img_val_DEFAULT[camera_index],
        )

    def update(self, bbox_multi_minmax: NDArray, frame_ix: int) -> None:
        tracker_result = self.mot_tracker.update(bbox_multi_minmax=bbox_multi_minmax)
        for x1, y1, x2, y2, _prob, tracker_id in tracker_result:
            xc, yc = (x1 + x2) / 2, (y1 + y2) / 2
            distance = float(np.hypot(xc, yc))
            is_workarea = 1 if self.evLUT3D.evaluate(xc, yc) > 0 else 0
            if tracker_id not in self.trackingID_data:
                self.trackingID_data[tracker_id] = tracking3d_dataclass(
                    accum_track_length=0,
                    final_xy=(xc, yc),
                    dist_from_camera_min=distance,
                    dist_from_camera_max=distance,
                    frame_ix_min=frame_ix,
                    frame_ix_max=frame_ix,
                    frame_ix_lastmove=frame_ix,
                    frame_evval_min=distance,
                    frame_evval_max=distance,
                    workarea_count=is_workarea,
                    is_alive=True,
                    is_tracking_target=True,
                )
                self.trackingID_bboxlog[tracker_id] = []
            else:
                metadata = self.trackingID_data[tracker_id]
                frame_movelen = float(
                    np.hypot(metadata.final_xy[0] - xc, metadata.final_xy[1] - yc)
                )
                metadata.accum_track_length += frame_movelen
                metadata.final_xy = (xc, yc)
                metadata.frame_ix_max = frame_ix
                if frame_movelen > 1e-6:
                    metadata.frame_ix_lastmove = frame_ix
                metadata.workarea_count += is_workarea
                metadata.dist_from_camera_min = min(
                    metadata.dist_from_camera_min, distance
                )
                metadata.dist_from_camera_max = max(
                    metadata.dist_from_camera_max, distance
                )
            self.trackingID_bboxlog[tracker_id].append(
                (frame_ix, (x1, y1, x2, y2))
            )

    def get_rawresults(self) -> Tracking3dDataInterface:
        return Tracking3dDataInterface(self.trackingID_data, self.trackingID_bboxlog)


class calibcheck2d3d:
    def __init__(
        self,
        app_config_calib: AppConfigCalibration,
        sac: SharedAppConfig,
        app_logger_factory: AppLoggerFactory,
        shared_errors: SharedErrors,
    ) -> None:
        self._logger: AppLogger = app_logger_factory.register_from_type(self.__class__)
        self.sac = sac
        self.app_config_calib = app_config_calib
        self._ser: SharedErrors = shared_errors
        self._calibcheck_status_diagnosis = CameraCalibCheckStatusDiagnosis()

        self.calibcheck2d3d_conf: CalibCheck2d3dConf = app_config_calib.calibCheck2d3d
        self.dataCapture_conf: DataCaptureConf = app_config_calib.dataCapture
        self._evaluation_camera_count = self.calibcheck2d3d_conf.camera_count
        self.FRAME_INFO_MAXLEN = self.calibcheck2d3d_conf.frame_info_maxlen
        self.THRESH_3DBBOX_COUNT_PER_FRAME = (
            self.calibcheck2d3d_conf.thresh_3dbbox_count_per_frame
        )
        self.THRESH_3DBBOX_COUNT_MEAN_RATIO = (
            self.calibcheck2d3d_conf.thresh_3dbbox_count_mean_ratio
        )
        self.THRESH_2DBBOX_COUNT_PER_FRAME = (
            self.calibcheck2d3d_conf.thresh_2dbbox_count_per_frame
        )
        self.THRESH_2DBBOX_COUNT_MEAN_RATIO = (
            self.calibcheck2d3d_conf.thresh_2dbbox_count_mean_ratio
        )
        self.THRESH_3DBBOX_TRACKING_IDCOUNT = (
            self.calibcheck2d3d_conf.thresh_3dbbox_tracking_idcount
        )
        self.THRESH_2DBBOX_TRACKING_IDCOUNT = (
            self.calibcheck2d3d_conf.thresh_2dbbox_tracking_idcount
        )
        detect2d_config = detect2d(
            onnx_model_path=self.calibcheck2d3d_conf.onnx_model_path
        )

        self.damoyolo = Detect2dDamoYoloOnnx(
            conf_thresh=detect2d_config.conf_thresh,
            nms_thresh=detect2d_config.nms_thresh,
            onnx_model_path=detect2d_config.onnx_model_path,
            batch_size=self.calibcheck2d3d_conf.camera_count,
            app_logger_factory=app_logger_factory,
        )

        self.ud: Mcde7000UndistortImageProvider = Mcde7000UndistortImageProvider(
            camera_intrinsics_path=self.calibcheck2d3d_conf.camera_intrinsics_path,
            sys_width=self.calibcheck2d3d_conf.image_w,
            sys_height=self.calibcheck2d3d_conf.image_h,
        )
        self.width = self.calibcheck2d3d_conf.image_w
        self.height = self.calibcheck2d3d_conf.image_h
        self._evaluation_intrinsics = self.ud.ncm1
        self.EVAL_FRAME_STRIDE = self.calibcheck2d3d_conf.eval_frame_stride
        self.USE_LEGACY_LIKE_METRIC = (
            self.calibcheck2d3d_conf.use_legacy_like_metric
        )
        self.EVAL_ZVALUES = self.calibcheck2d3d_conf.eval_zvalues
        self.VIRTUAL_BBOX_XY_OFFSETS = VIRTUAL_BBOX_XY_OFFSETS
        self.scenedesc_calibcheck = Scene_CalibCheck2d3d.create_for_evaluation(
            scene_conf=self.sac.read().SceneDescription,
            camera_intrinsics=self._evaluation_intrinsics,
            image_width=self.width,
            image_height=self.height,
        )

        # 各クラスコンストラクタ呼び出し
        self.proccap = datacapture_class(
            app_config_calib=self.app_config_calib,
            sac=self.sac,
            app_logger_factory=app_logger_factory,
            shared_errors=self._ser,
        )

        self.debug_index = 0
        self.monitor_data = {}
        self.verbose = not app_config_calib.default.print_disabled

    def input_settings(self):
        # TODO: 同期入力別プロセスのモジュールに入替

        self.trans_mat3D3D_eachlidar = []
        for path in self.calibcheck2d3d_conf.lidar_calib_files:
            self._logger.info(f"[input_settings] path:{path}")
            self._logger.info(f"loadtxt: {np.loadtxt(path, delimiter=',')}")
            self.trans_mat3D3D_eachlidar.append(np.loadtxt(path, delimiter=","))

        self.rtvec_mat = [
            read_rtvec(
                rvec_convmat_path=p,
                new_axis_mode=self.calibcheck2d3d_conf.new_axis_mode,
                points_inverted=True,
            )
            for p in self.calibcheck2d3d_conf.camera_calib_files
        ]

    def pre_app_loopmain(
        self,
        monitor: CalibrationUIGodot,
        sec: SharedExcepts,
        sac: SharedAppConfig,
    ) -> None:
        self._logger.info(f"frame index: {self.debug_index}")

        self.input_settings()

        # CalibStatus:D1/D2 もう一度送信
        monitor.set_status_calibcommon(1)
        monitor.set_dummydata(
            enable_systemerrorflag=True,
            enable_errorflag=True,
            overwrite_checkresult=True,
            enable_yawangle=True,
        )
        monitor.transmit_setdata(
            sec=sec, ref_t=None, is_firstframe=True, mmap_erase_rest=True
        )  # GUI共有メモリ書き込み。未書き込みエリアを初期化する(開始時1回だけ）

        self.checked_points3d = []
        self.checked_points3d_score = []
        self.checked_points2d = []
        self.checked_points2d_score = []

        self.camera_scores_rawdata: list[list[float]] = [
            [] for _ in range(self.calibcheck2d3d_conf.camera_count)
        ]  # カメラごとのbbox評価値のリスト
        self.frame_info = []
        readfailed_count = 0
        self.read_count = 0

    def app_loopmain(
        self,
        fifo_data: FIFOData,
        monitor: CalibrationUIGodot,
        sec: SharedExcepts,
        sac: SharedAppConfig,
    ) -> bool:
        # try:
        # self._logger.info(f"frame index: {self.debug_index}")

        # self.input_settings()

        # # CalibStatus:D1/D2 もう一度送信
        # monitor.set_status_calibcommon(1)
        # monitor.set_dummydata(
        #     enable_systemerrorflag=True,
        #     enable_errorflag=True,
        #     overwrite_checkresult=True,
        #     enable_yawangle=True,
        # )
        # monitor.transmit_setdata(sec=sec, ref_t=None, is_firstframe=True)

        # self.checked_points3d = []
        # self.checked_points3d_score = []
        # self.checked_points2d = []
        # self.checked_points2d_score = []

        # self.camera_scores_rawdata: list[list[float]] = [
        #     [] for _ in range(self.calibcheck2d3d_conf.camera_count)
        # ]  # カメラごとのbbox評価値のリスト
        # try:
        #     readfailed_count = 0
        #     while (
        #         not sec.CalMatGen_ex.IsFinished.value
        #         and sac.read().CalibMode.isRunning2D3Dcheck
        #         and (not sac.read().CalibMode.start2D3DCheckCalc)
        #     ):
        # CalibStatus:D2 現状はstart2D3DCheckCalcが入り次第while loopから抜ける

        return self.dataproc(fifo_data, monitor, sec)

    # except KeyboardInterrupt as e:
    #     self._logger.info(f"{e}, calibcheck2d3d app_loopmain ended")
    # except Exception as ea:
    #     self._logger.error(
    #         f"app_loopmain: exception! {ea} - \n{traceback.format_exc()}"
    #     )
    #     monitor.set_errorcode_unexpected_exception(True)
    # finally:

    # # CalibStatus:D3
    # monitor.set_status_calibcommon(2)
    # monitor.set_dummydata(
    #     enable_systemerrorflag=True,
    #     enable_errorflag=True,
    #     overwrite_checkresult=True,
    #     enable_yawangle=True,
    # )
    # monitor.transmit_setdata(sec=sec, ref_t=None)
    # for camera_ix, camera_values in enumerate(self.camera_scores_rawdata):
    #     resultstr = "Unknown"
    #     camera_score = 0
    #     if (
    #         len(camera_values)
    #         >= self.calibcheck2d3d_conf.score_accept_count_threshold
    #     ):
    #         camera_score = np.median(camera_values)
    #         if (
    #             camera_score
    #             >= self.calibcheck2d3d_conf.score_value_threshold
    #         ):
    #             resultstr = "OK"
    #         else:
    #             resultstr = "NG"

    #     with open(
    #         self.calibcheck2d3d_conf.resultfiles[camera_ix], "w"
    #     ) as wf:
    #         print(resultstr, file=wf)
    #     self._logger.info(
    #         f"Camera{camera_ix} result: {resultstr}, camera_score:{camera_score}, score_count:{len(camera_values)}",
    #     )

    # with open(
    #     "argus_synchro/calibration_mat_generator_modules/temp/calibcheck2d3d_results.txt",
    #     "w",
    # ) as wf:
    #     print("checked_points3d", file=wf)
    #     for v in self.checked_points3d:
    #         print(v, file=wf)
    #     print("checked_points3d_score", file=wf)
    #     for v in self.checked_points3d_score:
    #         print(v, file=wf)
    #     print("checked_points2d", file=wf)
    #     for v in self.checked_points2d:
    #         print(v, file=wf)
    #     print("checked_points2d_score", file=wf)
    #     for v in self.checked_points2d_score:
    #         print(v, file=wf)

    # except Exception as ea:
    #     self._logger.error(
    #         f"app_loopmain (status D3~): exception! {ea} - \n{traceback.format_exc()}",
    #     )
    #     monitor.set_errorcode_unexpected_exception(True)

    # self.end_wait(sec, sac, monitor)

    def post_app_loopmain(
        self,
        monitor: CalibrationUIGodot,
        sec: SharedExcepts,
        sac: SharedAppConfig,
    ) -> None:
        # CalibStatus:D3
        monitor.set_status_calibcommon(2)
        monitor.set_dummydata(
            enable_systemerrorflag=True,
            enable_errorflag=True,
            overwrite_checkresult=True,
            enable_yawangle=True,
        )
        reason_camera_notvalid, camera_evaluation_results = (
            self.data_evaluation_process()
        )
        self.camera_evaluation_results_to_monitor(
            monitor,
            reason_camera_notvalid,
            camera_evaluation_results,
        )
        monitor.transmit_setdata(sec=sec, ref_t=None)
        for camera_ix, result in enumerate(camera_evaluation_results):
            resultstr = "Unknown" if reason_camera_notvalid[camera_ix] else (
                "OK" if result else "NG"
            )

            with open(self.calibcheck2d3d_conf.resultfiles[camera_ix], "w") as wf:
                print(resultstr, file=wf)
            self._logger.info(
                f"Camera{camera_ix} result: {resultstr}, reason:{reason_camera_notvalid[camera_ix]}",
            )

        result_path: Path = Path(
            path.join(
                self.app_config_calib.default.outputdir_root,
                "calibcheck2d3d_results.txt",
            ),
        )

        with open(
            result_path,
            "w",
        ) as wf:
            print("checked_points3d", file=wf)
            for v in self.checked_points3d:
                print(v, file=wf)
            print("checked_points3d_score", file=wf)
            for v in self.checked_points3d_score:
                print(v, file=wf)
            print("checked_points2d", file=wf)
            for v in self.checked_points2d:
                print(v, file=wf)
            print("checked_points2d_score", file=wf)
            for v in self.checked_points2d_score:
                print(v, file=wf)

    # except Exception as ea:
    #     self._logger.error(
    #         f"app_loopmain (status D3~): exception! {ea} - \n{traceback.format_exc()}",
    #     )
    #     monitor.set_errorcode_unexpected_exception(True)

    # self.end_wait(sec, sac, monitor)

    @classmethod
    def end_wait(
        cls,
        timercount: int,
        sec: SharedExcepts,
        sac: SharedAppConfig,
        monitor: CalibrationUIGodot,
    ) -> int:
        monitor.set_status_calibcommon(3)
        monitor.set_dummydata(
            enable_systemerrorflag=True,
            enable_errorflag=True,
            overwrite_checkresult=True,
            enable_yawangle=True,
        )
        monitor.transmit_setdata(sec=sec, ref_t=None)

        timercount += 1

        if timercount > 10:
            timercount = 0
            _logger.info("========================")
            _logger.info("CalibCheck2d3d end")
            _logger.info("========================")

        sleep(0.1)
        return timercount

    @classmethod
    def send_end_wait(
        cls,
        sec: SharedExcepts,
        sac: SharedAppConfig,
        monitor: CalibrationUIGodot,
    ) -> None:
        monitor.set_status_calibcommon(0)
        monitor.set_dummydata(
            enable_systemerrorflag=True,
            enable_errorflag=True,
            overwrite_checkresult=True,
            enable_yawangle=True,
        )
        monitor.transmit_setdata(sec=sec, ref_t=None)

    def input_data_diagnosis(
        self,
        camera_datalist: list[tuple[NDArray[np.uint8], int, float] | None],
        lidar_datalist: list[tuple[NDArray[np.float32], int, float] | None],
        can_data: object,
    ) -> bool:
        invalid_data_input = self._ser.state_errors_D[
            StateErrorDIndex.INVALID_DATA_INPUT
        ]
        result, failsafe_result = invalid_data_input.errors_diagnosis(
            (camera_datalist, lidar_datalist, can_data)
        )
        invalid_data_input.log_output(
            result, failsafe_result, StateErrorDIndex.INVALID_DATA_INPUT
        )
        if result == ResultDiagnosis.DETECTION:
            return True

        # NOTE: 静的解析の指摘が出ているが、手前の不正データ入力の診断でNoneで無いことは担保出来ている
        images = tuple(camera_data[0] for camera_data in camera_datalist)
        min_xyz_columns = 3
        # NOTE: 静的解析の指摘が出ているが、手前の不正データ入力の診断でNoneで無いことは担保出来ている
        pcds_point_cloud = tuple(
            lidar_data[0][:, :min_xyz_columns] for lidar_data in lidar_datalist
        )
        array_shape_error = self._ser.state_errors_D[StateErrorDIndex.ARRAY_SHAPE_ERROR]
        result, failsafe_result = array_shape_error.errors_diagnosis(
            ("images", images),
            ("pcds_point_cloud", pcds_point_cloud),
        )
        array_shape_error.log_output(
            result, failsafe_result, StateErrorDIndex.ARRAY_SHAPE_ERROR
        )
        return result == ResultDiagnosis.DETECTION

    def camera_evaluation_results_to_monitor(
        self,
        monitor: CalibrationUIGodot,
        reason_camera_notvalid: list[int],
        camera_evaluation_results: list[bool],
    ) -> None:
        for camera_ix, (reason, result) in enumerate(
            zip(reason_camera_notvalid, camera_evaluation_results, strict=False)
        ):
            status = self._calibcheck_status_diagnosis.diagnose(
                reason_code=reason,
                calibration_is_acceptable=result,
            )
            monitor.set_camera_calibcheck_status(camera_ix, status)

    def record_bbox1f(
        self,
        multi_minmax: NDArray[np.float64],
        yoloresult_whole_list: list[list[NDArray]],
    ) -> None:
        if len(self.frame_info) >= self.FRAME_INFO_MAXLEN:
            self.frame_info.pop(0)
        self.frame_info.append((yoloresult_whole_list, multi_minmax))

    def validate_3dbbox_log(self) -> bool:
        framecount_3dbbox_valid = 0
        for _, multi_minmax in self.frame_info:
            if (
                multi_minmax is not None
                and len(multi_minmax) >= self.THRESH_3DBBOX_COUNT_PER_FRAME
            ):
                framecount_3dbbox_valid += 1
        self._logger.info(
            f"validate_3dbbox_log: framecount_3dbbox_valid={framecount_3dbbox_valid}, total_frames={len(self.frame_info)}, ratio={framecount_3dbbox_valid / len(self.frame_info) if self.frame_info else 0.0}",
        )
        return (
            framecount_3dbbox_valid / len(self.frame_info)
            >= self.THRESH_3DBBOX_COUNT_MEAN_RATIO
            if self.frame_info
            else False
        )

    def validate_2dbbox_log(self) -> list[bool]:
        framecount_2dbbox_valid_percamera = [
            0 for _ in range(self._evaluation_camera_count)
        ]
        for yoloresult_whole_list, _ in self.frame_info:
            for camera_ix, yoloresult_whole in enumerate(yoloresult_whole_list):
                if (
                    yoloresult_whole is not None
                    and yoloresult_whole[3] >= self.THRESH_2DBBOX_COUNT_PER_FRAME
                ):
                    framecount_2dbbox_valid_percamera[camera_ix] += 1

        self._logger.info(
            f"validate_2dbbox_log: framecount_2dbbox_valid_percamera={framecount_2dbbox_valid_percamera}, total_frames={len(self.frame_info)}, ratio={[framecount_2dbbox_valid_percamera[camera_ix] / len(self.frame_info) if self.frame_info else 0.0 for camera_ix in range(self._evaluation_camera_count)]}",
        )
        return [
            framecount_2dbbox_valid_percamera[camera_ix]
            >= self.THRESH_2DBBOX_COUNT_MEAN_RATIO * len(self.frame_info)
            if self.frame_info
            else False
            for camera_ix in range(self._evaluation_camera_count)
        ]

    def validate_recorded_bbox_logs(self) -> list[int]:
        if self.validate_3dbbox_log() is False:
            return [2 for _ in range(self._evaluation_camera_count)]

        return [
            0 if validation_result else 3
            for validation_result in self.validate_2dbbox_log()
        ]

    def track_3dbbox(self) -> Tracking3dDataInterface:
        bbox_track_and_record_3d = calibcheck3d_bboxtracker_recorder(
            app_config_calib=self.app_config_calib,
            camera_index=self.sac.read().CalibMode.cameraID,
        )
        for frame_ix, (_, multi_minmax) in enumerate(self.frame_info):
            bbox_track_and_record_3d.update(multi_minmax, frame_ix)
        return bbox_track_and_record_3d.get_rawresults()

    def track_2dbbox(self) -> list[Tracking2dDataInterface]:
        bbox_track_and_record_2d_allcamera = [
            calibcheck2d_bboxtracker_recorder(
                app_config_calib=self.app_config_calib,
                image_size_hw=(
                    self.calibcheck2d3d_conf.image_h,
                    self.calibcheck2d3d_conf.image_w,
                ),
                camera_index=camera_ix,
            )
            for camera_ix in range(self._evaluation_camera_count)
        ]

        for frame_ix, (yoloresult_whole_list, _) in enumerate(self.frame_info):
            for camera_ix, yoloresult_whole in enumerate(yoloresult_whole_list):
                bbox_track_and_record_2d_allcamera[camera_ix].update(
                    yoloresult_whole, frame_ix
                )

        return [
            recorder.get_rawresults()
            for recorder in bbox_track_and_record_2d_allcamera
        ]

    def select_3dbbox_tracking_results(
        self, tracking_3d_data_interface: Tracking3dDataInterface
    ) -> Tracking3dDataInterface:
        for id, metadata in tracking_3d_data_interface.trackingIDmetadata.items():
            frame_ix_length = metadata.frame_ix_max - metadata.frame_ix_min
            accum_track_length = metadata.accum_track_length
            workarea_count = metadata.workarea_count
            self._logger.info(
                f"select_3dbbox_tracking_results: id={id}, frame_ix_length={frame_ix_length}, accum_track_length={accum_track_length}, workarea_count={workarea_count}",
            )

            if frame_ix_length < 30:
                tracking_3d_data_interface.trackingIDmetadata[id].is_alive = False
            if accum_track_length < 3.0:
                tracking_3d_data_interface.trackingIDmetadata[id].is_alive = False
            if workarea_count < frame_ix_length * 0.1 or workarea_count < 30:
                tracking_3d_data_interface.trackingIDmetadata[id].is_alive = False

        return tracking_3d_data_interface

    def validate_3dbbox_tracking_results(
        self, tracking_3d_data_interface: Tracking3dDataInterface
    ) -> bool:
        count = 0
        if (
            len(tracking_3d_data_interface.trackingIDmetadata)
            >= self.THRESH_3DBBOX_TRACKING_IDCOUNT
        ):
            for _id, metadata in tracking_3d_data_interface.trackingIDmetadata.items():
                if metadata.is_alive:
                    count += 1
            if count >= self.THRESH_3DBBOX_TRACKING_IDCOUNT:
                return True
        self._logger.info(
            f"validate_3dbbox_tracking_results: count={count}, threshold={self.THRESH_3DBBOX_TRACKING_IDCOUNT}, return False",
        )
        return False

    def select_2dbbox_tracking_results(
        self, tracking_2d_data_interfaces: list[Tracking2dDataInterface]
    ) -> list[Tracking2dDataInterface]:
        for camera_ix, tracking_2d_data_interface in enumerate(
            tracking_2d_data_interfaces
        ):
            for id, metadata in tracking_2d_data_interface.trackingIDmetadata.items():
                frame_ix_length = metadata.frame_ix_max - metadata.frame_ix_min
                accum_track_length = metadata.accum_track_length
                self._logger.info(
                    f"select_2dbbox_tracking_results: camera_ix={camera_ix}, id={id}, frame_ix_length={frame_ix_length}, accum_track_length={accum_track_length}",
                )
                if frame_ix_length < 10:
                    tracking_2d_data_interfaces[camera_ix].trackingIDmetadata[
                        id
                    ].is_alive = False
                if accum_track_length < 50:
                    tracking_2d_data_interfaces[camera_ix].trackingIDmetadata[
                        id
                    ].is_alive = False

        return tracking_2d_data_interfaces

    def validate_2dbbox_tracking_results(
        self, tracking_2d_data_interfaces: list[Tracking2dDataInterface]
    ) -> list[bool]:
        results: list[bool] = []
        for tracking_2d_data_interface in tracking_2d_data_interfaces:
            count = sum(
                1
                for metadata in tracking_2d_data_interface.trackingIDmetadata.values()
                if metadata.is_alive
            )
            results.append(count >= self.THRESH_2DBBOX_TRACKING_IDCOUNT)
        return results

    def validate_tracked_bboxes(
        self,
        tracking_3d_data_interface: Tracking3dDataInterface,
        tracking_2d_data_interfaces: list[Tracking2dDataInterface],
    ) -> list[int]:
        tracking_3d_data_interface = self.select_3dbbox_tracking_results(
            tracking_3d_data_interface
        )
        if self.validate_3dbbox_tracking_results(tracking_3d_data_interface) is False:
            return [4 for _ in range(self._evaluation_camera_count)]

        tracking_2d_data_interfaces = self.select_2dbbox_tracking_results(
            tracking_2d_data_interfaces
        )
        return [
            0 if validation_result else 5
            for validation_result in self.validate_2dbbox_tracking_results(
                tracking_2d_data_interfaces
            )
        ]

    def project_3dbbox_core(
        self,
        bbox3d: NDArray[np.float32],
        camera_index: int,
        require_points_in_image: bool = False,
    ) -> NDArray[np.float32] | None:
        camera_extrinsics = self.rtvec_mat[camera_index][2]
        camera_intrinsics = self._evaluation_intrinsics

        bbox3d_corners = np.array(
            [
                [bbox3d[0], bbox3d[1], bbox3d[2]],
                [bbox3d[0], bbox3d[1], bbox3d[5]],
                [bbox3d[0], bbox3d[4], bbox3d[2]],
                [bbox3d[0], bbox3d[4], bbox3d[5]],
                [bbox3d[3], bbox3d[1], bbox3d[2]],
                [bbox3d[3], bbox3d[1], bbox3d[5]],
                [bbox3d[3], bbox3d[4], bbox3d[2]],
                [bbox3d[3], bbox3d[4], bbox3d[5]],
            ],
            dtype=np.float32,
        )
        bbox3d_corners_homogeneous = np.hstack(
            (bbox3d_corners, np.ones((bbox3d_corners.shape[0], 1), dtype=np.float32))
        )
        bbox3d_corners_camera = (
            camera_extrinsics @ bbox3d_corners_homogeneous.T
        ).T[:, :3]
        if np.any(bbox3d_corners_camera[:, 2] <= 0):
            return None

        bbox3d_corners_image = (
            camera_intrinsics @ bbox3d_corners_camera.T
        ).T
        bbox3d_corners_image = (
            bbox3d_corners_image[:, :2] / bbox3d_corners_image[:, 2:3]
        )
        if require_points_in_image:
            x_in = (bbox3d_corners_image[:, 0] >= 0.0) & (
                bbox3d_corners_image[:, 0] <= float(self.width - 1)
            )
            y_in = (bbox3d_corners_image[:, 1] >= 0.0) & (
                bbox3d_corners_image[:, 1] <= float(self.height - 1)
            )
            if not np.all(x_in & y_in):
                return None

        return np.array(
            [
                np.min(bbox3d_corners_image[:, 0]),
                np.min(bbox3d_corners_image[:, 1]),
                np.max(bbox3d_corners_image[:, 0]),
                np.max(bbox3d_corners_image[:, 1]),
            ],
            dtype=np.float32,
        )

    @staticmethod
    def _shrink_bbox2d(
        bbox2d: NDArray[np.float32], factor: float
    ) -> NDArray[np.float32]:
        center_x = (bbox2d[0] + bbox2d[2]) / 2.0
        center_y = (bbox2d[1] + bbox2d[3]) / 2.0
        half_width = (bbox2d[2] - bbox2d[0]) * factor / 2.0
        half_height = (bbox2d[3] - bbox2d[1]) * factor / 2.0
        return np.array(
            [
                center_x - half_width,
                center_y - half_height,
                center_x + half_width,
                center_y + half_height,
            ],
            dtype=np.float32,
        )

    @classmethod
    def _passes_center_diff_gate(
        cls,
        bbox_a: NDArray[np.float32],
        bbox_b: NDArray[np.float32],
    ) -> bool:
        shrunk_a = cls._shrink_bbox2d(bbox_a, BBOX_SHRINK_FACTOR)
        shrunk_b = cls._shrink_bbox2d(bbox_b, BBOX_SHRINK_FACTOR)
        width_a, height_a = shrunk_a[2] - shrunk_a[0], shrunk_a[3] - shrunk_a[1]
        width_b, height_b = shrunk_b[2] - shrunk_b[0], shrunk_b[3] - shrunk_b[1]
        center_a = (
            (shrunk_a[0] + shrunk_a[2]) / 2.0,
            (shrunk_a[1] + shrunk_a[3]) / 2.0,
        )
        center_b = (
            (shrunk_b[0] + shrunk_b[2]) / 2.0,
            (shrunk_b[1] + shrunk_b[3]) / 2.0,
        )
        average_width = max((width_a + width_b) / 2.0, 1e-6)
        average_height = max((height_a + height_b) / 2.0, 1e-6)
        normalized_x = (center_a[0] - center_b[0]) / average_width
        normalized_y = (center_a[1] - center_b[1]) / average_height
        return (
            float(np.hypot(normalized_x, normalized_y))
            <= BBOX_CENTER_DIFF_RATIO_THRESHOLD
        )

    @staticmethod
    def _has_positive_2d_intersection(
        bbox_a: NDArray[np.float32],
        bbox_b: NDArray[np.float32],
    ) -> bool:
        ax1, ay1 = min(bbox_a[0], bbox_a[2]), min(bbox_a[1], bbox_a[3])
        ax2, ay2 = max(bbox_a[0], bbox_a[2]), max(bbox_a[1], bbox_a[3])
        bx1, by1 = min(bbox_b[0], bbox_b[2]), min(bbox_b[1], bbox_b[3])
        bx2, by2 = max(bbox_b[0], bbox_b[2]), max(bbox_b[1], bbox_b[3])
        return min(ax2, bx2) - max(ax1, bx1) > 0.0 and min(ay2, by2) - max(
            ay1, by1
        ) > 0.0

    def evaluate_bbox_overlap_scenedesc(
        self,
        bbox3d: NDArray[np.float32],
        bbox2d: NDArray[np.float32],
        camera_index: int,
    ) -> float | None:
        projected_bbox2d = self.project_3dbbox_core(bbox3d, camera_index)
        if projected_bbox2d is not None and not self._passes_center_diff_gate(
            projected_bbox2d, bbox2d
        ):
            return 0.0

        candidate_minmax_list: list[NDArray[np.float32]] = []
        candidate_corners_list: list[NDArray[np.float32]] = []
        for offset_x, offset_y in self.VIRTUAL_BBOX_XY_OFFSETS:
            candidate_bbox3d = bbox3d.copy()
            candidate_bbox3d[[0, 3]] += offset_x
            candidate_bbox3d[[1, 4]] += offset_y
            candidate_minmax = np.array(
                [
                    candidate_bbox3d[0],
                    candidate_bbox3d[3],
                    candidate_bbox3d[1],
                    candidate_bbox3d[4],
                    candidate_bbox3d[2],
                    candidate_bbox3d[5],
                ],
                dtype=np.float32,
            )
            candidate_minmax_list.append(candidate_minmax)
            candidate_corners_list.append(
                np.array(
                    [
                        [candidate_minmax[0], candidate_minmax[2], candidate_minmax[4]],
                        [candidate_minmax[1], candidate_minmax[2], candidate_minmax[4]],
                        [candidate_minmax[0], candidate_minmax[3], candidate_minmax[4]],
                        [candidate_minmax[1], candidate_minmax[3], candidate_minmax[4]],
                        [candidate_minmax[0], candidate_minmax[2], candidate_minmax[5]],
                        [candidate_minmax[1], candidate_minmax[2], candidate_minmax[5]],
                        [candidate_minmax[0], candidate_minmax[3], candidate_minmax[5]],
                        [candidate_minmax[1], candidate_minmax[3], candidate_minmax[5]],
                    ],
                    dtype=np.float32,
                )
            )

        bbox_class = self.scenedesc_calibcheck.integrate2d3d_calibcheck(
            rvec=self.rtvec_mat[camera_index][0],
            tvec=self.rtvec_mat[camera_index][1],
            boxpoints=np.concatenate(candidate_corners_list),
            bbox2d=np.array(
                [
                    [
                        bbox2d[1] / self.height,
                        bbox2d[0] / self.width,
                        bbox2d[3] / self.height,
                        bbox2d[2] / self.width,
                    ]
                ],
                dtype=np.float32,
            ),
            minmax3ds=np.stack(candidate_minmax_list),
            yolo_classes=np.array([0], dtype=np.int32),
            n_clusters=len(self.VIRTUAL_BBOX_XY_OFFSETS),
            bbox2d_detection_count=1,
            method="center",
        )
        return 1.0 if bbox_class.get(0) == "HUMAN" else 0.0

    def evaluate_2d3d(
        self,
        tracking_3d_data_interface: Tracking3dDataInterface,
        tracking_2d_data_interfaces: list[Tracking2dDataInterface],
        zvalues: tuple[float, float],
    ) -> tuple[list[float], list[int]]:
        mean_scores_per_camera = [
            0.0 for _ in range(self._evaluation_camera_count)
        ]
        reason_camera_notvalid = [
            0 for _ in range(self._evaluation_camera_count)
        ]

        for camera_ix, tracking_2d_data_interface in enumerate(
            tracking_2d_data_interfaces
        ):
            camera_has_inframe = False
            camera_has_timematch = False
            camera_has_valid = False
            camera_numerator = 0
            camera_denominator = 0
            camera_legacy_numerator = 0.0
            camera_legacy_denominator = 0
            alive_2d_ids = [
                track_id
                for track_id, metadata in tracking_2d_data_interface.trackingIDmetadata.items()
                if metadata.is_alive
            ]

            for track_id_3d, metadata_3d in (
                tracking_3d_data_interface.trackingIDmetadata.items()
            ):
                if not metadata_3d.is_alive:
                    continue
                bboxlog_3d = tracking_3d_data_interface.trackingIDbboxlog.get(
                    track_id_3d, []
                )
                visible_frames: dict[
                    int, tuple[NDArray[np.float32], NDArray[np.float32]]
                ] = {}
                for frame_ix, bbox3d_xy in bboxlog_3d:
                    bbox3d_full = np.array(
                        [
                            bbox3d_xy[0],
                            bbox3d_xy[1],
                            zvalues[0],
                            bbox3d_xy[2],
                            bbox3d_xy[3],
                            zvalues[1],
                        ],
                        dtype=np.float32,
                    )
                    projected_bbox2d = self.project_3dbbox_core(
                        bbox3d_full,
                        camera_ix,
                        require_points_in_image=True,
                    )
                    if projected_bbox2d is not None:
                        visible_frames[frame_ix] = (bbox3d_full, projected_bbox2d)

                if not visible_frames:
                    continue
                camera_has_inframe = True
                sampled_frame_ixs = {
                    frame_ix
                    for sample_index, frame_ix in enumerate(visible_frames)
                    if sample_index % self.EVAL_FRAME_STRIDE == 0
                }
                sampled_frame_ixs.add(next(reversed(visible_frames)))
                camera_denominator += len(sampled_frame_ixs)
                hit_frame_ixs: set[int] = set()
                legacy_frame_best_score: dict[int, float] = {}
                visible_frame_min = min(visible_frames)
                visible_frame_max = max(visible_frames)

                for track_id_2d in alive_2d_ids:
                    metadata_2d = tracking_2d_data_interface.trackingIDmetadata[
                        track_id_2d
                    ]
                    if (
                        metadata_2d.frame_ix_max < visible_frame_min
                        or metadata_2d.frame_ix_min > visible_frame_max
                    ):
                        continue
                    for frame_ix, bbox2d in (
                        tracking_2d_data_interface.trackingIDbboxlog.get(
                            track_id_2d, []
                        )
                    ):
                        if frame_ix not in visible_frames:
                            continue
                        camera_has_timematch = True
                        if frame_ix not in sampled_frame_ixs or frame_ix in hit_frame_ixs:
                            continue
                        bbox3d_full, projected_bbox2d = visible_frames[frame_ix]
                        bbox2d_array = np.array(bbox2d, dtype=np.float32)
                        if BBOX_SHRINK_FACTOR < 1.0:
                            bbox2d_array = self._shrink_bbox2d(
                                bbox2d_array, BBOX_SHRINK_FACTOR
                            )
                        if not self._has_positive_2d_intersection(
                            projected_bbox2d, bbox2d_array
                        ):
                            camera_has_valid = True
                            legacy_frame_best_score.setdefault(frame_ix, 0.0)
                            continue
                        score = self.evaluate_bbox_overlap_scenedesc(
                            bbox3d_full,
                            bbox2d_array,
                            camera_ix,
                        )
                        if score is None:
                            continue
                        camera_has_valid = True
                        legacy_frame_best_score[frame_ix] = max(
                            legacy_frame_best_score.get(frame_ix, 0.0), score
                        )
                        if score > 0.0:
                            hit_frame_ixs.add(frame_ix)

                camera_numerator += len(hit_frame_ixs & sampled_frame_ixs)
                camera_legacy_numerator += sum(legacy_frame_best_score.values())
                camera_legacy_denominator += len(legacy_frame_best_score)

            if not camera_has_inframe:
                reason_camera_notvalid[camera_ix] = 9
            elif not camera_has_timematch:
                reason_camera_notvalid[camera_ix] = 10
            elif not camera_has_valid:
                reason_camera_notvalid[camera_ix] = 11
            elif self.USE_LEGACY_LIKE_METRIC:
                mean_scores_per_camera[camera_ix] = (
                    camera_legacy_numerator / camera_legacy_denominator
                    if camera_legacy_denominator > 0
                    else 0.0
                )
            else:
                mean_scores_per_camera[camera_ix] = (
                    camera_numerator / camera_denominator
                    if camera_denominator > 0
                    else 0.0
                )

        return mean_scores_per_camera, reason_camera_notvalid

    def judge_calibration_result(
        self, evaluation_statistics: list[float], threshold: float = 0.1
    ) -> list[bool]:
        return [score >= threshold for score in evaluation_statistics]

    def data_evaluation_process(self) -> tuple[list[int], list[bool]]:
        reason_camera_notvalid = self.validate_recorded_bbox_logs()
        camera_evaluation_results = [
            False for _ in range(self._evaluation_camera_count)
        ]
        if all(reason_camera_notvalid):
            return reason_camera_notvalid, camera_evaluation_results

        tracking_3d_data_interface = self.track_3dbbox()
        tracking_2d_data_interfaces = self.track_2dbbox()
        tracking_reasons = self.validate_tracked_bboxes(
            tracking_3d_data_interface,
            tracking_2d_data_interfaces,
        )
        reason_camera_notvalid = [
            current_reason if current_reason else tracking_reasons[camera_ix]
            for camera_ix, current_reason in enumerate(reason_camera_notvalid)
        ]
        if all(reason_camera_notvalid):
            return reason_camera_notvalid, camera_evaluation_results

        evaluation_statistics, evaluation_reasons = self.evaluate_2d3d(
            tracking_3d_data_interface,
            tracking_2d_data_interfaces,
            zvalues=self.EVAL_ZVALUES,
        )
        evaluated_results = self.judge_calibration_result(
            evaluation_statistics,
            threshold=self.calibcheck2d3d_conf.score_value_threshold,
        )
        for camera_ix, current_reason in enumerate(reason_camera_notvalid):
            if current_reason == 0:
                reason_camera_notvalid[camera_ix] = evaluation_reasons[camera_ix]
                camera_evaluation_results[camera_ix] = evaluated_results[camera_ix]

        return reason_camera_notvalid, camera_evaluation_results

    def error_reason_to_string(self, reason: int) -> str:
        reason_map = {
            0: "OK",
            1: "情報取得時エラー",
            2: "3D bboxログが不正",
            3: "2D bboxログが不正",
            4: "3D bboxトラッキング結果が不正/不足",
            5: "2D bboxトラッキング結果が不正/不足",
            6: "2D3D評価結果が不正",
            7: "評価統計計算が不正",
            8: "校正判定が不正",
            9: "カメラ内に対象物なし",
            10: "カメラとLiDARの時間同期なし",
            11: "カメラとLiDARの評価可能な対象物なし",
        }
        return reason_map.get(reason, f"Unknown reason code {reason}")

    def error_reason_to_ui_errornum(self, reason: int) -> int:
        reason_map = {
            1: 3,
            2: 3,
            3: 3,
            4: 5,
            5: 5,
            6: 5,
            7: 5,
            8: 5,
            9: 4,
            10: 3,
            11: 4,
        }
        return reason_map.get(reason, -1)

    def dataproc(
        self,
        readresult_pop: FIFOData,
        monitor: CalibrationUIGodot,
        sec: SharedExcepts,
    ) -> bool:  # 継続可否を返す Falseで終了
        # readresults = self.proccap.read(data_capture_inst)
        comparemode = "max"
        # データ入力
        # 10回ごとに入力を受け付け
        self.read_count += 1
        if self.read_count % 10 != 0:
            return True

        # for _ in range(10):
        #     readresult_pop  # 同期センサデータ入力
        # if readresult_pop is None:
        #     return False

        # データ入力 - カメラ入力
        camera_datalist, lidar_datalist, can_data, framecounter = readresult_pop
        if self.input_data_diagnosis(
            camera_datalist,
            lidar_datalist,
            can_data,
        ):
            return False

        frame_cameras: list[NDArray[np.uint8]] = []
        yoloresult_whole_list = []
        for ix, camera_rawdatatuple in enumerate(camera_datalist):
            if camera_rawdatatuple is None:
                self._logger.info(f"frame {ix} is invalid, skip")
                continue
            frame = camera_rawdatatuple[0]
            frame = self.ud.get_undistort_image(frame)
            frame_cameras.append(frame)

            # yoloresult_whole_list.append(self.YOLOinst.predict(frame))

        yoloresult_whole_tuple = self.damoyolo._inference(frame_cameras)
        # n_batch>1の場合、dummyの画像を入れて推論しているだけなので、最初の一つ目の結果だけ取り出す
        # batch sizeはscore(yoloresult_whole_tuple[1].shape[0])から取得
        yoloresult_whole_list = [
            [
                yoloresult_whole_tuple[0][i],
                yoloresult_whole_tuple[1][i],
                yoloresult_whole_tuple[2][i],
                yoloresult_whole_tuple[3][i],
            ]
            for i in range(yoloresult_whole_tuple[1].shape[0])
        ]

        for ix, frame in enumerate(frame_cameras):
            yoloresult_whole = yoloresult_whole_list[ix]
            frame, _ = draw_multibbox(frame, yoloresult_whole)

            bbox_for_ui: list[list[int]] = []
            image_h, image_w, _ = frame.shape
            for result_ix in range(int(yoloresult_whole[3])):
                coor = yoloresult_whole[0].reshape((-1, 4))[result_ix]
                # prob = yoloresult_whole[1][result_ix]
                # cls_id = yoloresult_whole[2][result_ix]

                # メインアプリ core - utils.py - draw_bbox 関数より編集
                bbox_ymin = coor[0] * image_h
                bbox_ymax = coor[2] * image_h
                bbox_xmin = coor[1] * image_w
                bbox_xmax = coor[3] * image_w

                bbox_for_ui.append([bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax])

            monitor.set_2Dbbox(ix, np.array(bbox_for_ui, dtype=np.int32))

        del yoloresult_whole
        del frame

        # データ入力 - LiDAR入力
        lidar_data = [x[0] for x in lidar_datalist if x is not None]

        if len(lidar_data) == 0:
            return False

        for x in range(len(lidar_data)):
            lidar_data[x] = np.array(lidar_data[x], dtype=np.float32)
            # lidar_data[x][:, :3] *= np.ones((len(lidar_data[x]), 3), dtype=np.float32) * debuginfo_and_functions.point_scale

        pts = conbine3d3d(
            xyz_data=lidar_data, trans_mat3D3D_eachlidar=self.trans_mat3D3D_eachlidar
        )

        # pts[:, 3] = np.where(pts[:, 3] < 0, pts[:, 3] + 256, pts[:, 3])
        # pts = pts[pts[:, 3] > 0]
        pts[:, 1] = -pts[:, 1]
        pts[:, 2] = -pts[:, 2]  # yz反転
        points = pts
        del pts

        # 点群処理：　地面点群除去と点群クラスタリング

        th = self.calibcheck2d3d_conf.z_threshold
        points = points[points[:, 2] > th]

        pts_obj_lim = np.array(
            utils3d.np_to_pcd(points[:, :3]).voxel_down_sample(0.2).points
        )
        (multi_points, multi_lines, multi_minmax), pcd_limited, db = internal_make_BB(
            pts_obj_lim
        )
        self.record_bbox1f(multi_minmax, yoloresult_whole_list)

        # 評価

        # integrated_retults_2d3d_old = None
        evaluate_results = []  # integrated_retults_2d3d, box3ds_reproj_list をカメラ個数分
        integrated_retults_2d3d_allcamera = []
        for camera_ix in range(3):
            # YOLO推定結果を取得
            yoloresult_whole = yoloresult_whole_list[camera_ix]

            # YOLO結果と3D bboxを入力し3D bboxごとの評価結果を得る。
            evaluate_results.append(
                calibcheck_detection_2d3d.evaluate2d3d(
                    width=self.calibcheck2d3d_conf.image_w,
                    height=self.calibcheck2d3d_conf.image_h,
                    multi_points=multi_points,
                    linkmethod="iou",
                    yoloresult_whole=yoloresult_whole,
                    rvec=self.rtvec_mat[camera_ix][0],
                    tvec=self.rtvec_mat[camera_ix][1],
                    ncm1=self.ud.ncm1,
                    integrated_retults_2d3d_old=None,  # integrated_retults_2d3d_old
                    # ここでoldを指定するとこの3D bboxごとの属性リストに上書きする形で登録。カメラごとの結果を知りたい場合はnoneにして混ぜないようにする
                )
            )

            # 直前にappendした要素からintegrated_retults_2d3d（3D bboxごとの評価結果リスト）を取り出し、カメラごとに人のbboxの評価値を取得し記録する。
            integrated_retults_2d3d = evaluate_results[-1][0]
            for elem_ix, elem in enumerate(integrated_retults_2d3d):
                if elem[0] == "human":
                    self.camera_scores_rawdata[camera_ix].append(
                        elem[2]
                    )  # カメラごとの評価値を記録しておく（後で統計を取る

            # integrated_retults_2d3d_old = evaluate_results[-1][0]

            # 3カメラ分の結果を統合　カメラ0の結果を土台に、同じcluster_ixでよりスコアの高い結果を上書きする。　←統合してはいけない　【Todo】
            if camera_ix == 0:
                integrated_retults_2d3d_allcamera = copy.deepcopy(
                    integrated_retults_2d3d
                )
            else:
                for cluster_ix, Z in enumerate(integrated_retults_2d3d):
                    (category, bbox_ix, score, box3ds_reproj_box, box2d) = Z
                    if category == "human":
                        if comparemode == "min":
                            eval_result: bool = (
                                score < integrated_retults_2d3d_allcamera[cluster_ix][2]
                            )
                        else:
                            eval_result: bool = (
                                score > integrated_retults_2d3d_allcamera[cluster_ix][2]
                            )
                        if eval_result:
                            # 該当3dBBの情報を書き換え
                            integrated_retults_2d3d_allcamera[cluster_ix] = (
                                copy.deepcopy(Z)
                            )

        # 評価値をUI送信用に加工
        reason_camera_notvalid: list[int] = []
        camera_evaluation_results: list[bool] = []
        for camera_values in self.camera_scores_rawdata:
            reason = 1
            result = False
            if (
                len(camera_values)
                >= self.calibcheck2d3d_conf.score_accept_count_threshold
            ):
                reason = 0
                camera_score = np.median(camera_values)
                result = (
                    camera_score >= self.calibcheck2d3d_conf.score_value_threshold
                )

            reason_camera_notvalid.append(reason)
            camera_evaluation_results.append(result)

        self.camera_evaluation_results_to_monitor(
            monitor,
            reason_camera_notvalid,
            camera_evaluation_results,
        )

        del yoloresult_whole
        del integrated_retults_2d3d

        # 以下描画用の処理

        integrated_retults_2d3d = integrated_retults_2d3d_allcamera
        for camera_ix in range(3):
            # yoloresult_whole = yoloresult_whole_list[camera_ix]
            frame: NDArray[np.uint8] = frame_cameras[camera_ix]
            box3ds_reproj = evaluate_results[camera_ix][1]

            for ix, (lines, attr) in enumerate(
                zip(
                    multi_lines.reshape(-1, 12, 2),
                    integrated_retults_2d3d,
                    strict=False,
                )
            ):
                if attr[0] == "human":
                    boxcolor = (0, 0, 255)
                    self.checked_points3d.append(
                        multi_points[int(ix * 8) : int(ix * 8) + 8].mean(axis=0)
                    )
                    self.checked_points3d_score.append(attr[2])
                    self.checked_points2d.append(attr[3].mean(axis=0))
                    self.checked_points2d_score.append(attr[2])
                    # print(f"ix: {ix}, human, {multi_points[int(ix/8):int(ix/8)+8]}, {multi_points[int(ix/8):int(ix/8)+8].mean(axis=0)}, score: {attr[2]}")

                else:
                    boxcolor = (10, 10, 10)

                for pt1ix, pt2ix in lines:
                    cv2.line(
                        frame,
                        conv_intarr(box3ds_reproj[pt1ix]),
                        conv_intarr(box3ds_reproj[pt2ix]),
                        boxcolor,
                        2,
                    )

                cv2.putText(
                    frame,
                    f"{ix}",
                    conv_intarr(box3ds_reproj[pt1ix]),
                    fontFace=cv2.FONT_HERSHEY_SIMPLEX,
                    fontScale=1.0,
                    color=boxcolor,
                    thickness=2,
                    lineType=cv2.LINE_4,
                )

            # human_scores = np.array(
            #    [x[2] for x in integrated_retults_2d3d if x[0] == "human"]
            # )

            # cv2.imshow(f"frame{camera_ix}", cv2.resize(frame, dsize=None, fx=0.25, fy=0.25))

            # monitor.put_data(
            #    "dataproc",
            #    f"detect2d_image{camera_ix}",
            #    cv2.resize(frame, dsize=None, fx=0.25, fy=0.25),
            # )
            monitor.set_image(camera_ix, frame)

        # monitor.put_data("dataproc", "detect3d_points_raw", (pcd_limited, 0))
        if pcd_limited.shape[-1] == 4:
            monitor.set_points(
                pcd_limited[:, :3],
                monitor.convert_intensity_to_color(pcd_limited[:, 3]),
            )
        elif pcd_limited.shape[-1] == 3:
            monitor.set_points(
                pcd_limited, np.tile([0.2, 0.2, 0.2], (pcd_limited.shape[0], 1))
            )
        else:
            monitor.set_points(
                np.zeros((0, 3), dtype=np.float32), np.zeros((0, 3), dtype=np.float32)
            )
        # monitor.put_data("dataproc", "detect3d_multipoints", multi_points)
        monitor.set_boxes(
            points_multipoints=multi_points, points_multi_lines=multi_lines
        )
        # monitor.put_data("dataproc", "detect3d_multi_lines", multi_lines)

        if len(self.checked_points3d) > 0:
            scores = np.array(
                self.checked_points3d_score
            )  # checked_points3dと同じ長さのスコア情報 max1
            # monitor.put_data(
            #    "dataproc", f"3dobj_{0}_pts", np.array(self.checked_points3d)
            # )
            monitor.set_cornerpoints(
                np.array(self.checked_points3d),
                np.outer(scores, [0, 1, 0]) + np.outer(1 - scores, [1, 0, 0]),
            )
            # monitor.put_data(
            #    "dataproc",
            #    f"3dobj_{0}_clr",
            #    ,
            # )

        monitor.set_dummydata(
            enable_systemerrorflag=True,
            enable_errorflag=True,
            overwrite_checkresult=True,
            enable_yawangle=True,
        )
        monitor.transmit_setdata(sec=sec, ref_t=self.debug_index)

        self.debug_index += 1
        return True
