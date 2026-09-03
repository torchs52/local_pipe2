from abc import ABC, abstractmethod
from typing import Final, final

import numpy as np
from numpy.typing import NDArray
import time

from argus_synchro.common.error import NotStartedError
from argus_synchro.device.can.can_receiver import Can, CanFile
from argus_synchro.device.can.shi_lib_can_receiver import ShiLibCan
from argus_synchro.shared_errors import SharedErrors, StateErrorIndex


class CanDataProvider(ABC):
    CANID_ANGLE_OLD: Final[str] = "18FCE402"
    CANID_ANGLE: Final[str] = "18FFD1D1"
    CANID_LEVER: Final[str] = "18FC4401"

    def __init__(self) -> None:
        super().__init__()
        self._yaw_angle_deg: float = 0.0
        self._lever_pressure: NDArray[np.float64] = np.array(
            [np.nan, np.nan, np.nan, np.nan]
        )

    @abstractmethod
    def receive_can_data(self) -> tuple[float, NDArray[np.float64]]:
        err_msg = f"class: {self.__class__.__name__}, method: receive_can_data()"
        raise NotImplementedError(err_msg)

    @property
    def yaw_angle_deg(self) -> float:
        """yaw_angle_deg(ヨー角度)を取得する"""
        return self._yaw_angle_deg

    @property
    def lever_pressure(self) -> NDArray[np.float64]:
        """lever_pressure(レバー圧)を取得する"""
        return self._lever_pressure


@final
class NotStartedCanDataProvider(CanDataProvider):
    def receive_can_data(self) -> tuple[float, NDArray[np.float64]]:
        raise NotStartedError


@final
class CanFileProvider(CanDataProvider):
    def __init__(self, device: CanFile, start_frame: int) -> None:
        super().__init__()
        self._device: CanFile = device
        self._ref_t = start_frame
        self.update()

    def update(self) -> None:
        pass

    def receive_can_data(self) -> tuple[float, NDArray[np.float64]]:
        can_id: str
        can_data: tuple[float, ...]
        can_id, can_data = self._device.receive_can_data(self._ref_t)

        if (
            can_id in (self.CANID_ANGLE_OLD, self.CANID_ANGLE)
            and type(can_data[0]) is float
        ):
            # 角度データ更新
            self._yaw_angle_deg = can_data[0]
        elif can_id == self.CANID_LEVER and type(can_data) is tuple[float, ...]:
            # レバーデータ更新
            self._lever_pressure = np.array(can_data)

        self._ref_t += 1

        return self._yaw_angle_deg, self._lever_pressure

    def change_file_name_index(self, file_path: str, index: int) -> None:
        self._device.change_file_name_index(file_path)
        self._ref_t = index


@final
class CanReceiverProvider(CanDataProvider):
    def __init__(self, device: Can, ser: SharedErrors) -> None:
        super().__init__()
        self._device: Can = device
        self._ser: SharedErrors = ser
        self._err_config_load()
        self._timestamp: float | None = None

    def _err_config_load(self) -> None:
        self._err_config = self._ser.shared_err_conf.read()

        self._ser.state_errors_A_C[
                StateErrorIndex.YAW_ANGLE_INFO_ERROR
            ].update(self._err_config)

    def receive_can_data(self) -> tuple[float, NDArray[np.float64]]:
        can_id: str
        can_data: tuple[float, ...] | None
        can_id, can_data = self._device.receive_can_data()
        now =time.perf_counter()
        if can_data is None:
            # 処理なし
            pass
        elif (
            can_id in (self.CANID_ANGLE_OLD, self.CANID_ANGLE)
            and type(can_data[0]) is float
        ):
            # 角度データ更新
            self._yaw_angle_deg = can_data[0]
            self._timestamp = now
        elif can_id == self.CANID_LEVER and type(can_data) is tuple[float, ...]:
            # レバーデータ更新
            self._lever_pressure = np.array(can_data)

        yaw_angle_info_error = self._ser.state_errors_A_C[
            StateErrorIndex.YAW_ANGLE_INFO_ERROR
        ]
        result = yaw_angle_info_error.errors_diagnosis(
            self._timestamp, now
        )
        yaw_angle_info_error.log_output(
            *result, StateErrorIndex.YAW_ANGLE_INFO_ERROR
        )

        return self._yaw_angle_deg, self._lever_pressure


@final
class ShiLibCanProvider(CanDataProvider):
    def __init__(self, device: ShiLibCan) -> None:
        super().__init__()
        self._device: ShiLibCan = device

    def receive_can_data(self) -> tuple[float, NDArray[np.float64]]:
        can_id: str
        can_data: tuple[float, ...] | None
        can_id, can_data = self._device.receive_can_data()
        if can_data is None:
            # 処理なし
            pass
        elif (
            can_id in (self.CANID_ANGLE_OLD, self.CANID_ANGLE)
            and type(can_data[0]) is float
        ):
            # 角度データ更新
            self._yaw_angle_deg = can_data[0]
        elif can_id == self.CANID_LEVER and type(can_data) is tuple[float, ...]:
            # レバーデータ更新
            self._lever_pressure = np.array(can_data)

        return self._yaw_angle_deg, self._lever_pressure
