"""
LiDARの慣性データ取得プロセス

プロセスの概要

* 慣性データ取得プロセス
    * プロセス1: LiDAR1から慣性データを取得する (ファイル入力モード)
    * プロセス2: LiDAR2から慣性データを取得する (ファイル入力モード)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, final

import numpy as np

from argus_synchro.config.app_config import AppConfig, ScrutinizerConf
from argus_synchro.diagnosis.error_config import ErrorConfig
from argus_synchro.diagnosis.error_diagnosis import ResultDiagnosis
from argus_synchro.message.input_message import ImuData
from argus_synchro.process import InputProcess, MessageFlow
from argus_synchro.process.message import Producer
from argus_synchro.process.synchronizer import ProcessActivator
from argus_synchro.profiler import log_target
from argus_synchro.profiler.prof_mode import ProfCategory
from argus_synchro.shared_app_config import SharedAppConfig
from argus_synchro.shared_errors import ModuleErrorIndex, SharedErrors
from argus_synchro.shared_excepts import SharedIMUExcept

if TYPE_CHECKING:
    from argus_synchro.provider.imu import ImuProvider


@final
class ImuProviderProcess(InputProcess[ImuData]):
    __slots__ = (
        "_app_config",
        "_end_frame",
        "_err_config",
        "_index",
        "_last_updated",
        "_lidar_config",
        "_lidar_config_index_map",
        "_provider",
        "_sac",
        "_scrutinizer_conf",
        "_ser",
        "_unique_lidar_name",
    )

    def __init__(
        self,
        index: int,
        sec_imu: SharedIMUExcept,
        sac: SharedAppConfig,
        ser: SharedErrors,
        producer_flow: MessageFlow[ImuData],
        activator: ProcessActivator,
        name: str | None = None,
    ) -> None:
        super().__init__(producer_flow, sec_imu, activator, name)
        self._index: int = index
        self._sac: SharedAppConfig = sac
        self._ser: SharedErrors = ser
        self._provider: ImuProvider
        self._lidar_config: dict[str, dict[str, str | int]] = {}
        self._lidar_config_index_map: dict[int, str] = {}
        self._unique_lidar_name: str = ""

        # _startupで初期化
        self._err_config: ErrorConfig

    def _config_load(self) -> None:
        self._app_config: AppConfig = self._sac.read()
        self._last_updated: int = self._sac.last_updated
        self._scrutinizer_conf: ScrutinizerConf = self._app_config.Scrutinizer
        self._end_frame: int = self._app_config.Scrutinizer.e_frame

    def _err_config_load(self) -> None:
        self._err_config = self._ser.shared_err_conf.read()

        # NOTE: このプロセスで実施する全ての診断クラスのupdateをここに追加していく
        self._ser.module_errors[ModuleErrorIndex.IMU_MODULE_ERROR].update(
            self._err_config
        )

    def _log_register(self) -> None:
        super()._log_register()
        self._sac.log_register(self._app_logger_factory)
        self._ser.log_register(self._app_logger_factory)

    def _apply_parameters(self) -> None:
        pass

    def _startup(self) -> None:
        self._config_load()
        self._err_config_load()
        self._read_lidar_config()
        self._change_device()
        self.create_producer_and_consumer()

    def create_producer_and_consumer(self) -> None:
        self.producer: Producer[ImuData] = self._producer_flow.create_producer()

    def restart_completed(self) -> None:
        self.producer.restart_completed()

    def _start_restart(self) -> None:
        # TODO """必要に応じて実際にプロセスを落とさないで再起動で実行する処理を記載""" (NSW)
        pass

    def _read_lidar_config(self) -> None:
        with open(self._app_config.Lidar.path, encoding="utf-8") as f:
            self._lidar_config = json.loads(f.read())
        # 挿入順でキー一覧を取得
        keys = list(
            self._lidar_config.keys(),
        )  # ["MID3601", "MID3602", ...]
        # index→key マップ(これで_lidar_config_index_map[0] → "MID3601"が得られる)
        self._lidar_config_index_map = dict(enumerate(keys))

    def _shutdown(self) -> None:
        pass

    @log_target("IMU入力I/F", ProfCategory.Process)
    def _update(self) -> ImuData | None:
        imu_ring, t = self._provider.get_accum_point()

        # 最新状態（len ≤ 1000）を縦結合 → write_bufへコピー
        if imu_ring:
            cube = np.stack(imu_ring, axis=0)
            flat = cube.reshape(cube.shape[0], -1)
            return ImuData(0, t, flat)
        return ImuData(0, t, np.zeros((2, 2), dtype=np.float64))

    # @log_main()
    def _loop(self) -> None:
        while self.enable:
            if self._sac.last_updated > self._last_updated:
                self._config_load()
                self._apply_parameters()
            try:
                if not self.producer.wait():
                    continue
                output_data = self._update()
                if output_data is None:
                    continue

                self.producer.produce(output_data)
            except Exception as e:
                is_state_error_d_exception = self._ser.is_state_error_d_exception(
                    e, self._logger
                )
                if not is_state_error_d_exception:
                    if self._ser.module_errors[
                        ModuleErrorIndex.IMU_MODULE_ERROR
                    ].excepts_diagnosis(e):
                        self._ser.module_errors[
                            ModuleErrorIndex.IMU_MODULE_ERROR
                        ].log_output(
                            ResultDiagnosis.DETECTION,
                            ResultDiagnosis.DETECTION,
                            ModuleErrorIndex.IMU_MODULE_ERROR,
                            e,
                            self._index,
                        )
                    else:
                        raise e

    def _change_device(self) -> None:
        file_input: bool = self._app_config.DEFAULT.File_Input
        use_shi_lib: bool = self._app_config.DEFAULT.use_shi_lib

        if file_input:
            from argus_synchro.device.lidar.mid360_imu import MID360ImuFile
            from argus_synchro.provider.imu import Mid360ImuFileProvider

            # 課題:ファイル入力時のファイルデバイスの切り替え方法
            # 　　　現状のファイル形式はMID360のみなので決め打ちする
            device = MID360ImuFile(self._index, self._app_config)
            self._provider = Mid360ImuFileProvider(device)
        elif use_shi_lib:
            from argus_synchro.device.lidar.shi_lib_imu import ShiLibImu
            from argus_synchro.provider.imu import ShiLibImuProvider

            device = ShiLibImu(self._index, self._app_config)
            self._provider = ShiLibImuProvider(device)
        else:
            # 実機

            # LiDARコンフィグのlidar_nameを読み取り、デバイス/プロバイダーを切り替える
            self._unique_lidar_name = self._lidar_config_index_map[self._index]
            lidar_config: dict[str, str | int] = self._lidar_config[
                self._unique_lidar_name
            ]
            lidar_name = str(lidar_config["lidar_name"])

            if lidar_name == "MID360":
                from argus_synchro.device.lidar.mid360_imu import MID360Imu
                from argus_synchro.provider.imu import Mid360ImuProvider

                device = MID360Imu(self._index, lidar_config, self._app_logger_factory)
                self._provider = Mid360ImuProvider(device)
            elif lidar_name == "OS0128":
                from argus_synchro.device.lidar.os0128_imu import OS0128Imu
                from argus_synchro.provider.imu import Os0128ImuProvider

                device = OS0128Imu(self._index, self._app_config)
                self._provider = Os0128ImuProvider(device)
            elif lidar_name == "AIRY96":
                from argus_synchro.device.lidar.airy96_imu import AIRY96Imu
                from argus_synchro.provider.imu import Airy96ImuProvider

                device = AIRY96Imu(self._index, self._app_config)
                self._provider = Airy96ImuProvider(device)
            elif lidar_name == "AIRY192":
                from argus_synchro.device.lidar.airy192_imu import AIRY192Imu
                from argus_synchro.provider.imu import Airy192ImuProvider

                device = AIRY192Imu(self._index, self._app_config)
                self._provider = Airy192ImuProvider(device)
            else:
                err_msg = f"Unsupported LiDAR name: {lidar_config['lidar_name']}"
                raise ValueError(err_msg)
