from __future__ import annotations

import contextlib

# 標準系
import copy
import datetime
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, final

from argus_synchro.common import paths
from argus_synchro.diagnosis.error_config import ErrorConfig
from argus_synchro.diagnosis.error_diagnosis import ResultDiagnosis
from argus_synchro.jetson_monitor.jetson_monitor import JetsonMonitor
from argus_synchro.jetson_monitor.jm.models import Metrics
from argus_synchro.machine_profile import MachineProfileHandler
from argus_synchro.process import ProcessBase
from argus_synchro.process.operation_mode import OPERATION_MODE as OPM
from argus_synchro.process.synchronizer import ProcessActivator
from argus_synchro.profiler import log_target
from argus_synchro.profiler.prof_mode import ProfCategory
from argus_synchro.shared_errors import (
    ModuleErrorIndex,
    SharedErrors,
    StateErrorDIndex,
    StateErrorIndex,
)

if TYPE_CHECKING:
    from watchdog.observers.api import BaseObserver

    from argus_synchro.config.app_config import AppConfig
    from argus_synchro.shared_app_config import SharedAppConfig
    from argus_synchro.shared_excepts import SharedExcepts


@final
class AppManagerProcess(ProcessBase):
    __slots__ = (
        "_activator",
        "_app_config",
        "_dt_start",
        "_err_config",
        "_interval",
        "_last_updated",
        "_logmode",
        "_logtime",
        "_num_lidars",
        "_observer",
        "_sac",
        "_scrut_activator",
        "_sec",
        "_ser",
        "_system_activator",
    )

    def __init__(
        self,
        sec: SharedExcepts,
        sac: SharedAppConfig,
        ser: SharedErrors,
        system_activator: ProcessActivator,
        scrut_activator: ProcessActivator,
        name: str | None = None,
    ) -> None:
        super().__init__(sec.AppMan_ex, system_activator, name)
        self._sec: SharedExcepts = sec
        self._sac: SharedAppConfig = sac
        self._ser: SharedErrors = ser
        self._last_updated: int = 0
        self._app_config: AppConfig
        self._logmode: int = 0
        self._logtime: float = 0.0
        self._interval: float = 0.0
        self._num_lidars: int = 0
        self._num_cameras: int = 0
        self._scrut_activator: ProcessActivator = scrut_activator
        self._system_activator: ProcessActivator = system_activator
        self._metrics: Metrics | None = None
        self._is_thermal_throttling: bool = False

        # _startupで初期化
        self._dt_start: datetime.datetime
        self._observer: BaseObserver
        self._js_th: JetsonMonitor | None = None
        self._err_config: ErrorConfig
        self._is_last_camera_diag_enabled: list[bool]
        self._is_last_can_diag_enabled: bool
        self._is_last_lidar_sm_diag_enabled: bool

    def _config_load(self) -> None:
        self._app_config: AppConfig = self._sac.read()
        self._last_updated = self._sac.last_updated

        # ログ取得時は1を設定.(default: 0)
        self._logmode = self._app_config.AppManager.logmode
        # ログ取得時間(sec)
        self._logtime = self._app_config.AppManager.logtime
        # 観測間隔(sec)
        self._interval = self._app_config.AppManager.interval
        self._num_lidars = self._app_config.Lidar.count
        self._num_cameras = self._app_config.camera.count
        self.file_input: bool = self._app_config.DEFAULT.File_Input

    def _err_config_load(self) -> None:
        self._err_config = self._ser.shared_err_conf.read()

        # NOTE: このプロセスで実施する全ての診断クラスのupdateをここに追加していく
        for i in range(self._num_cameras):
            self._ser.state_errors_A_C[
                StateErrorIndex.CAMERA0_CONNECTION_ERROR + i
            ].update(self._err_config)
        self._ser.state_errors_A_C[StateErrorIndex.CAN_CONNECTION_ERROR].update(
            self._err_config
        )
        self._ser.state_errors_A_C[
            StateErrorIndex.MONITOR_PROCESS_NOT_RESPONDING
        ].update(self._err_config)
        self._ser.state_errors_A_C[
            StateErrorIndex.LIDAR_POSITION_MISALIGNMENT_NOT_RESPONDING
        ].update(self._err_config)
        self._ser.state_errors_A_C[StateErrorIndex.STORAGE_SPACE_LOW].update(
            self._err_config
        )
        self._ser.state_errors_A_C[StateErrorIndex.OUT_OF_MEMORY].update(
            self._err_config
        )
        self._ser.state_errors_A_C[StateErrorIndex.GPU_PERFORMANCE_DEGRADED].update(
            self._err_config
        )
        self._ser.state_errors_A_C[StateErrorIndex.INTERNAL_TEMPERATURE_RISE].update(
            self._err_config
        )
        self._ser.state_errors_A_C[StateErrorIndex.TEMPERATURE_SENSOR_ABNORMAL].update(
            self._err_config
        )
        self._ser.state_errors_A_C[
            StateErrorIndex.TEMPERATURE_RISE_TREND_CONTINUES
        ].update(self._err_config)
        self._ser.state_errors_D[StateErrorDIndex.OTHER_HARDWARE_ERROR].update(
            self._err_config
        )
        self._ser.state_errors_D[StateErrorDIndex.MEMORY_LEAK_DETECTED].update(
            self._err_config
        )
        self._ser.module_errors[ModuleErrorIndex.APP_MANAGER_MODULE_ERROR].update(
            self._err_config
        )

    def _apply_parameters(self) -> None:
        pass

    def create_producer_and_consumer(self) -> None:
        pass

    def restart_completed(self) -> None:
        pass

    def _scrut_end_notification(self) -> None:
        """
        周辺監視モードのActivatorを停止
        """
        self._scrut_activator.disable()

    def _app_end_notification(self) -> None:
        """
        全てのActivatorを停止
        TODO リファクタリング後に校正モードのActivator追加 (NSW)
        """
        self._scrut_activator.disable()
        self._system_activator.disable()

    def _startup_observer(self) -> None:
        from watchdog.observers import Observer

        from argus_synchro.file_watch import (
            ChangeModelEventHandler,
            DebouncedEventHandler,
        )

        self._observer = Observer()

        path: Path = paths.get_config_dir(self._directory_config)
        event_handler = DebouncedEventHandler(
            sac=self._sac,
            sec=self._sec,
            ser=self._ser,
            logger=self._logger,
            regexes=(r".*(\\|/)settings.ini",),
            debounce_time=0.1,
        )
        self._observer.schedule(event_handler, path)
        monitored_file_path: Path | None = (
            MachineProfileHandler.get_model_specific_config_file_path(
                self._directory_config
            )
        )
        if isinstance(monitored_file_path, Path):
            monitored_file_name: str = monitored_file_path.name
            change_model_event_handler = ChangeModelEventHandler(
                # 更新の監視対象にする機種ごとの設定ファイル
                ser=self._ser,
                regexes=(rf".*(\\|/){monitored_file_name}",),
                debounce_time=0.1,
                app_logger_factory=self._app_logger_factory,
                directory_config=self._directory_config,
            )
            self._observer.schedule(change_model_event_handler, path)
        self._observer.start()

    def _startup_jetson_monitor(self) -> None:
        if self._app_config.jetson_monitor.is_applied:
            self._js_th = JetsonMonitor(
                sac=self._sac,
                ser=self._ser,
                app_logger_factory=self._app_logger_factory,
                diag_func=self._jetson_monitor_diag,
            )
            self._js_th.start()

    def _startup(self) -> None:
        self._config_load()
        self._err_config_load()

        self._is_last_camera_diag_enabled = [False] * self._num_cameras
        self._is_last_can_diag_enabled = False
        self._is_last_lidar_sm_diag_enabled = False

        result: tuple[ResultDiagnosis, ResultDiagnosis] = self._ser.state_errors_D[
            StateErrorDIndex.OTHER_HARDWARE_ERROR
        ].errors_diagnosis()
        self._ser.state_errors_D[StateErrorDIndex.OTHER_HARDWARE_ERROR].log_output(
            *result, StateErrorDIndex.OTHER_HARDWARE_ERROR
        )

        # チェック確認までしばらく待つ.
        time.sleep(5)
        # 開始時間
        self._dt_start: datetime.datetime = datetime.datetime.now()
        self._logger.info("開始時刻")
        #############################################
        # ここに記載のlog機能は、基本的に使わず、全面的に書き換える。
        if self._logmode == 1:
            #####必要に応じて変更(既存フォルダ指定)#######
            save_dir: str = self._app_config.AppManager.log_dir
            ###########################################
            date_str: str = self._dt_start.strftime("%Y%m%d%H%M")

            dir_path: str = f"{save_dir}/{date_str}"
            if not os.path.exists(dir_path):
                os.mkdir(dir_path)

        #############################################

        monitor_argus_last_heartbeat_path = (
            self._app_config.AppManager.monitor_argus_last_heartbeat_path
        )
        self._monitor_argus_last_heartbeat_path = Path(
            monitor_argus_last_heartbeat_path
        )

        self._startup_observer()
        self._startup_jetson_monitor()

    def _start_restart(self) -> None:
        # TODO """必要に応じて実際にプロセスを落とさないで再起動で実行する処理を記載""" (NSW)
        pass

    def _log_register(self) -> None:
        super()._log_register()
        self._sec.log_register(self._app_logger_factory)
        self._sac.log_register(self._app_logger_factory)
        self._ser.log_register(self._app_logger_factory)
        MachineProfileHandler.log_register(self._app_logger_factory)

    def _shutdown(self) -> None:
        with contextlib.suppress(Exception):
            if self._js_th is not None:
                self._js_th.stop()

    def _camera_healthy_check(self, now: float) -> None:
        for i in range(self._num_cameras):
            if self._sec.CAM_ex[i].is_received_enabled.value:
                camera_connection_error = self._ser.state_errors_A_C[
                    StateErrorIndex.CAMERA0_CONNECTION_ERROR + i
                ]
                if self._is_last_camera_diag_enabled[i] is False:
                    # NOTE: is_diagnosis_enabledがFalseからTrueに変化した場合は、診断用のインスタンス変数を初期化する
                    camera_connection_error.clear()

                result = camera_connection_error.errors_diagnosis(
                    now, self._sec.CAM_ex[i].last_received.value
                )
                camera_connection_error.log_output(
                    *result, StateErrorIndex.CAMERA0_CONNECTION_ERROR + i, i
                )

            self._is_last_camera_diag_enabled[i] = bool(
                self._sec.CAM_ex[i].is_received_enabled.value
            )

    def _can_healthy_check(self, now: float) -> None:
        if self._sec.CAN_ex.is_received_enabled.value:
            can_connection_error = self._ser.state_errors_A_C[
                StateErrorIndex.CAN_CONNECTION_ERROR
            ]
            if self._is_last_can_diag_enabled is False:
                # NOTE: is_diagnosis_enabledがFalseからTrueに変化した場合は、診断用のインスタンス変数を初期化する
                can_connection_error.clear()

            result = can_connection_error.errors_diagnosis(
                now, self._sec.CAN_ex.last_received.value
            )
            can_connection_error.log_output(
                *result, StateErrorIndex.CAN_CONNECTION_ERROR
            )
        self._is_last_can_diag_enabled = bool(
            self._sec.CAN_ex.is_received_enabled.value
        )

    def _lidar_shift_monitoring_healthy_check(self, now: float) -> None:
        if self._sec.Lidar_SM_ex.is_heartbeat_enabled.value:
            lidar_position_misalignment_not_responding = self._ser.state_errors_A_C[
                StateErrorIndex.LIDAR_POSITION_MISALIGNMENT_NOT_RESPONDING
            ]
            if self._is_last_lidar_sm_diag_enabled is False:
                # NOTE: is_diagnosis_enabledがFalseからTrueに変化した場合は、診断用のインスタンス変数を初期化する
                lidar_position_misalignment_not_responding.clear()

            result: tuple[ResultDiagnosis, ResultDiagnosis] = (
                lidar_position_misalignment_not_responding.errors_diagnosis(
                    now, self._sec.Lidar_SM_ex.last_heartbeat.value
                )
            )
            lidar_position_misalignment_not_responding.log_output(
                *result, StateErrorIndex.LIDAR_POSITION_MISALIGNMENT_NOT_RESPONDING
            )

        self._is_last_lidar_sm_diag_enabled = bool(
            self._sec.Lidar_SM_ex.is_heartbeat_enabled.value
        )

    def _sensor_healthy_check(self) -> None:
        now: float = time.perf_counter()
        self._camera_healthy_check(now)
        self._can_healthy_check(now)
        self._lidar_shift_monitoring_healthy_check(now)

    def _monitor_argus_healthy_check(self) -> None:
        now: float = time.perf_counter()
        monitor_argus_last_heartbeat: float | None = None
        try:
            with open(self._monitor_argus_last_heartbeat_path, "r") as f:
                monitor_argus_last_heartbeat = float(f.read().strip())
        except (FileNotFoundError, ValueError):
            pass

        monitor_process_not_responding = self._ser.state_errors_A_C[
            StateErrorIndex.MONITOR_PROCESS_NOT_RESPONDING
        ]
        result = monitor_process_not_responding.errors_diagnosis(
            now, monitor_argus_last_heartbeat
        )
        monitor_process_not_responding.log_output(
            *result, StateErrorIndex.MONITOR_PROCESS_NOT_RESPONDING
        )

    def _update_thermal_throttling_state(self, metrics: Metrics | None) -> None:
        """サーマルスロットリング状態を負荷低減モードの判定に使用するために更新"""
        if metrics is None:
            # NOTE: サーマルスロットリング状態が取得できない場合は、サーマルスロットリングによる負荷低減モードへは遷移しない
            self._is_thermal_throttling = False
        else:
            is_cpu_th = metrics.cpu_th > 0 if metrics.cpu_th is not None else False
            is_gpu_th = metrics.gpu_th > 0 if metrics.gpu_th is not None else False
            self._is_thermal_throttling = is_cpu_th or is_gpu_th

    def _jetson_monitor_diag(self, data: Metrics) -> None:
        # メトリクスをAppManagerProcessに出力する
        self._metrics = data
        self._update_thermal_throttling_state(data)

        # 診断開始
        now: float = time.perf_counter()
        storage_space_low = self._ser.state_errors_A_C[
            StateErrorIndex.STORAGE_SPACE_LOW
        ]
        result = storage_space_low.errors_diagnosis(
            data.disk_root_avail_gib, data.disk_data_avail_gib, now
        )
        storage_space_low.log_output(*result, StateErrorIndex.STORAGE_SPACE_LOW)

        out_of_memory = self._ser.state_errors_A_C[StateErrorIndex.OUT_OF_MEMORY]
        result = out_of_memory.errors_diagnosis(
            data.ram_used_mb,
            data.ram_total_mb,
            now,
        )
        out_of_memory.log_output(*result, StateErrorIndex.OUT_OF_MEMORY)

        memory_leak_detected = self._ser.state_errors_D[
            StateErrorDIndex.MEMORY_LEAK_DETECTED
        ]
        result = memory_leak_detected.errors_diagnosis(
            data.ram_used_mb,
            now,
        )
        memory_leak_detected.log_output(*result, StateErrorDIndex.MEMORY_LEAK_DETECTED)

        gpu_performance_degraded = self._ser.state_errors_A_C[
            StateErrorIndex.GPU_PERFORMANCE_DEGRADED
        ]
        result = gpu_performance_degraded.errors_diagnosis(now, data.gpu_th)
        gpu_performance_degraded.log_output(
            *result, StateErrorIndex.GPU_PERFORMANCE_DEGRADED
        )

        internal_temperature_rise = self._ser.state_errors_A_C[
            StateErrorIndex.INTERNAL_TEMPERATURE_RISE
        ]
        result = internal_temperature_rise.errors_diagnosis(
            now, data.tj_c, data.cpu_c, data.gpu_c
        )
        internal_temperature_rise.log_output(
            *result, StateErrorIndex.INTERNAL_TEMPERATURE_RISE
        )

        temperature_sensor_abnormal = self._ser.state_errors_A_C[
            StateErrorIndex.TEMPERATURE_SENSOR_ABNORMAL
        ]
        result = temperature_sensor_abnormal.errors_diagnosis(
            now, data.tj_c, data.cpu_c, data.gpu_c
        )
        temperature_sensor_abnormal.log_output(
            *result, StateErrorIndex.TEMPERATURE_SENSOR_ABNORMAL
        )

        temperature_rise_trend_continues = self._ser.state_errors_A_C[
            StateErrorIndex.TEMPERATURE_RISE_TREND_CONTINUES
        ]
        result = temperature_rise_trend_continues.errors_diagnosis(
            now, data.tj_c, data.cpu_c, data.gpu_c
        )
        temperature_rise_trend_continues.log_output(
            *result, StateErrorIndex.TEMPERATURE_RISE_TREND_CONTINUES
        )

    # @log_main()
    def _loop(self) -> None:
        ref_t: int = 0
        previous_scrut_frame: int = 0
        present_scrut_frame: int = 0
        not_active_count: int = 0
        try:
            while self._system_activator.value:
                if self._sac.last_updated > self._last_updated:
                    self._config_load()
                    self._apply_parameters()
                    self._logger.info(
                        f"config reloaded (last_updated={self._last_updated})"
                    )

                try:
                    # 指定秒置きに例外処理のチェックする.
                    time.sleep(self._interval)
                    self._logger.info("Checked!")
                    previous_scrut_frame, present_scrut_frame, not_active_count = (
                        self._update(
                            previous_scrut_frame, present_scrut_frame, not_active_count
                        )
                    )
                    ref_t += 1
                except Exception as e:
                    if not self._ser.is_state_error_d_exception(e, self._logger):
                        if self._ser.module_errors[
                            ModuleErrorIndex.APP_MANAGER_MODULE_ERROR
                        ].excepts_diagnosis(e):
                            self._ser.module_errors[
                                ModuleErrorIndex.APP_MANAGER_MODULE_ERROR
                            ].log_output(
                                ResultDiagnosis.DETECTION,
                                ResultDiagnosis.DETECTION,
                                ModuleErrorIndex.APP_MANAGER_MODULE_ERROR,
                                e,
                            )
                        else:
                            raise e

        except KeyboardInterrupt:
            # NOTE: Ctrl+Cを押下しても、shutdown_handler()にINT信号をとられるので、このパスに入らない
            self._logger.info("KeyboardInterrupt を検出して終了.")

        finally:
            self._app_end_notification()
            self._observer.stop()
            self._observer.join()
            self._sec.show_present_scrut_ex()
            self._sec.show_present_calib_ex()

    @log_target("AppManager", ProfCategory.Process)
    def _update(
        self,
        previous_scrut_frame: int,
        present_scrut_frame: int,
        not_active_count: int,
    ) -> tuple[int, int, int]:
        if self._app_config.General.operation_mode == OPM.SCRUT:
            # scrutinizerが動作しているかチェック. Appmanagerのカウンタだけ進行してたらおかしい.
            present_scrut_frame = int(self._sec.frame_number.value)
            # scrutinizerが更新するカウンタ
            if (
                not self._ser.is_idle_mode
                and present_scrut_frame == previous_scrut_frame
            ):
                self._logger.info("===============================================")
                self._logger.info("NotActive_count = %d", not_active_count)
                self._logger.info("ref_t = %s", str(self._sec.frame_number.value))
                not_active_count += 1
                if not_active_count > self._app_config.AppManager.JudegeStopThr:
                    self._logger.info("===============================================")
                    self._logger.info("Scrutinizer might be stopped.")
                    self._logger.info("===============================================")
                    # winsound.Beep(523, 2000) # 使用時はwinsoundのimportが必要.
                    self._scrut_end_notification()
            else:
                not_active_count = 0
            previous_scrut_frame = int(copy.copy(present_scrut_frame))

            if self._sec.check_scrut_mode_is_finished():
                # 起動モジュールのいずれかが終了していたら.
                self._scrut_end_notification()

            # センサー Healthy Check
            if not self._app_config.DEFAULT.File_Input:
                now: float = time.time()
                for i in range(self._num_lidars):
                    # センサーインスタンスのデータ更新時刻が指定秒以上変化ない場合
                    if (
                        self._sec.LiDAR_ex[i].is_heartbeat_enabled.value
                        and now - self._sec.LiDAR_ex[i].last_heartbeat.value > 5
                    ):
                        self._logger.warning(
                            f"LiDAR[{i}] is initializing or might be dead.",
                        )
                        self._sec.LiDAR_ex[i].IsDead.value = True
            self._sensor_healthy_check()
            self._monitor_argus_healthy_check()

            self._ser.reduced_load_mode.update_is_thermal_throttling(
                self._is_thermal_throttling
            )

            #############################################
            # 経過時間の計測
            dt_now: datetime.datetime = datetime.datetime.now()
            elapsed: datetime.timedelta = dt_now - self._dt_start
            if self._logmode and elapsed.seconds > self._logtime:
                self._logger.info("=======================================")
                self._logger.info(
                    "%dsec has elapsed. Stop the logging.",
                    elapsed.seconds,
                )
                self._logger.info("=======================================")
                self._scrut_end_notification()

            if self._sac.is_restart_required.value:
                self._sec.AppMan_ex.IsFinished.value = True
                self._app_end_notification()

            ##############################################
        return previous_scrut_frame, present_scrut_frame, not_active_count
