import copy
from os import path
from pathlib import Path
from time import sleep

import cv2
import numpy as np
from numpy.typing import NDArray

from argus_synchro.calibration_mat_generator_modules.ctrl.calibcheck2d3d import (
    calibcheck_detection_2d3d,
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

# 型定義のみ
from argus_synchro.calibration_mat_generator_modules.ctrl.data_capture import (
    data_capture,
)
from argus_synchro.calibration_mat_generator_modules.ctrl.data_capture.datacapture_local import (
    datacapture_class,
)
from argus_synchro.calibration_mat_generator_modules.facade import CalibrationUIGodot
from argus_synchro.calibration_mat_generator_modules.utils import utils3d

# ARGUSシステム制御関連
from argus_synchro.common import paths
from argus_synchro.common.app_logger import AppLogger, AppLoggerFactory
from argus_synchro.config.app_config_calibration import (
    AppConfigCalibration,
    CalibCheck2d3dConf,
    DataCaptureConf,
)
from argus_synchro.detect2d import Detect2dDamoYoloOnnx
from argus_synchro.diagnosis.error_diagnosis import ResultDiagnosis
from argus_synchro.message.calib_fifo_message import FIFOData
from argus_synchro.provider.image import Mcde7000UndistortImageProvider
from argus_synchro.shared_app_config import SharedAppConfig
from argus_synchro.shared_errors import SharedErrors, StateErrorDIndex
from argus_synchro.shared_excepts import SharedExcepts

_logger: AppLogger = AppLoggerFactory.from_name("calibcheck2d3d")


def log_register(app_logger_factory: AppLoggerFactory) -> None:
    app_logger_factory.append_logger(_logger)
    calibcheck_detection_2d3d.log_register(app_logger_factory)


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

        self.calibcheck2d3d_conf: CalibCheck2d3dConf = app_config_calib.calibCheck2d3d
        self.dataCapture_conf: DataCaptureConf = app_config_calib.dataCapture
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
        monitor.transmit_setdata(sec=sec, ref_t=None)
        for camera_ix, camera_values in enumerate(self.camera_scores_rawdata):
            resultstr = "Unknown"
            camera_score = 0
            if (
                len(camera_values)
                >= self.calibcheck2d3d_conf.score_accept_count_threshold
            ):
                camera_score = np.median(camera_values)
                if camera_score >= self.calibcheck2d3d_conf.score_value_threshold:
                    resultstr = "OK"
                else:
                    resultstr = "NG"

            with open(self.calibcheck2d3d_conf.resultfiles[camera_ix], "w") as wf:
                print(resultstr, file=wf)
            self._logger.info(
                f"Camera{camera_ix} result: {resultstr}, camera_score:{camera_score}, score_count:{len(camera_values)}",
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
        for camera_ix, camera_values in enumerate(self.camera_scores_rawdata):
            resultval: int = 0b00
            camera_score = 0
            if (
                len(camera_values)
                >= self.calibcheck2d3d_conf.score_accept_count_threshold
            ):
                camera_score = np.median(camera_values)
                if camera_score >= self.calibcheck2d3d_conf.score_value_threshold:
                    resultval = 0b11
                else:
                    resultval = 0b01

            monitor.set_camera_calibcheck_status(camera_ix, resultval)

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
