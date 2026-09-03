from __future__ import annotations

import builtins
import contextlib
from typing import TYPE_CHECKING

from argus_synchro.common.app_logger import AppLogger, AppLoggerFactory
from argus_synchro.config.app_config import CANConf

if TYPE_CHECKING:
    import pybind_shi_sensor_lib as shi
with contextlib.suppress(builtins.BaseException):
    import pybind_shi_sensor_lib as shi


class ShiLibCan:
    def __init__(
        self,
        index: int,
        can_conf: CANConf,
        app_logger_factory: AppLoggerFactory,
    ) -> None:
        self._logger: AppLogger = app_logger_factory.register_from_type(self.__class__)
        self.can_dev = shi.Can()
        self._index = index
        self.can_recv_msg = shi.CanMessageData()

        self.handle = 0
        self.isLatest = True

        self.old_can_id = "18FCE402"
        self.new_can_id = "18FFD1D1"
        self.lever_id = "18FC4401"
        self.is_old = False
        self.update(can_conf)

    def receive_can_data(self) -> tuple[str, tuple[float, ...] | None]:
        can_id, data = self._get_data()
        return can_id, data

    def update(self, can_conf: CANConf) -> None:
        self._yaw_offset_deg: float = can_conf.yaw_offset_deg

    def _get_data(self) -> tuple[str, tuple[float, ...] | None]:
        can_id: str = "00000000"
        timestamp_us = 1000000
        isLatest = True
        handle: int = self._index
        rts = self.can_dev.getSensorData(
            handle,
            self.can_recv_msg,
            timestamp_us,
            isLatest,
        )
        if rts == shi.ApiStatus.SUCCESS:
            can_id: str = self.can_recv_msg.id
            self._logger.info(
                "CAN-ID:%x, TIMESTAMP:%d, SIZE:%d, DATA:%s",
                self.can_recv_msg.id,
                self.can_recv_msg.timestamp_ms,
                self.can_recv_msg.size,
                self.can_recv_msg.data[0:8],
            )
            # CANIDの新旧で処理を分岐して共有メモリに書き込み続ける
            if self.can_recv_msg.id == int(self.old_can_id, 16):
                self.is_old = True
                # "1818FFD1D1"
                # 0-16
                # AppLogger.info(f'CAN-ID:{self.can_recv_msg.id:x}, TIMESTAMP:{self.can_recv_msg.timestamp_ms}, SIZE:{self.can_recv_msg.size}, DATA:{self.can_recv_msg.data[0:8]}',file=self.fresult)
                # scに旋回角度を格納(0,1:右側旋回ポテンショ[10*V]、2,3:左側旋回ポテンショ[10*V]、4,5:旋回位置[10*deg]、6,7:現在旋回速度[10*rad/sec])
                tmp_string = (
                    f"{self.can_recv_msg.data[2]:02X}{self.can_recv_msg.data[3]:02X}"
                )
                current_degree = 360 - int(tmp_string, 16) / 10.0
                # ここでsc.can_signalと同じ場所に格納

                # 新版と角度の正方向と合わせるために、360から角度を引く。＋オフセット分の角度を足す。オフセットなので引きたくなるが、新版に合わせるために足す必要がある。
                # 逆に新版ではオフセットを引けばよい
                can_data = ((current_degree + self._yaw_offset_deg),)
                self._logger.info("%f", can_data[0])
            elif self.can_recv_msg.id == int(self.new_can_id, 16):
                # "1818FFD1D1"
                # 360度を13400分割した結果がカウントとしてデータが送られるため、角度に変換するためにデータを13400/360で割る
                tmp_string = f"{self.can_recv_msg.data[0]:02X}{self.can_recv_msg.data[1]:02X}{self.can_recv_msg.data[2]:02X}{self.can_recv_msg.data[3]:02X}"
                current_degree = (
                    int(tmp_string[:2], 16) + int(tmp_string[2:4], 16) * 255
                ) / (13400 / 360)
                # ここでsc.can_signalと同じ場所に格納
                can_data = ((current_degree - self._yaw_offset_deg),)
                self._logger.info("%f", can_data[0])
            elif self.can_recv_msg.id == int(self.lever_id, 16):
                """
                レバー圧力取得
                """
                msg_data: bytes = self.can_recv_msg.data[:-1]
                can_data = tuple(
                    int.from_bytes(msg_data[i : i + 2], "big")
                    * 0.001  # 無符号 16 bit ×0.001
                    for i in (0, 2, 4, 6)
                )

                self._logger.info(
                    "handle_lever, lever handler data:%f %f %f %f",
                    *can_data[0:4],
                )

            else:
                can_data = None
        else:
            self._logger.info("get can mesg error. status:%s", rts)
            can_data = None

        return can_id, can_data
