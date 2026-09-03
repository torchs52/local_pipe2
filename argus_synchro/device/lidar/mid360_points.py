import socket
from typing import Final

import numpy as np
from numpy.typing import NDArray

from argus_synchro.common.app_logger import AppLogger, AppLoggerFactory
from argus_synchro.config.app_config import LidarConf


class MID360PointsFile:
    def __init__(
        self,
        index: int,
        lidar_file_path: str,
        lidar_conf: LidarConf,
        start_frame: int,
        app_logger_factory: AppLoggerFactory,
    ) -> None:
        self._logger: AppLogger = app_logger_factory.register_from_type(self.__class__)
        self.file: str = lidar_file_path
        self._accum_time = lidar_conf.accum_time
        self._ref_t = start_frame

    def connect(self) -> None:
        err_msg = f"class: {self.__class__.__name__}, method: connect()"
        raise NotImplementedError(err_msg)

    def disconnect(self) -> None:
        err_msg = f"class: {self.__class__.__name__}, method: disconnect()"
        raise NotImplementedError(err_msg)

    def change_file_name_index(self, file_name: str) -> None:
        self.file = file_name

    @staticmethod
    def _read_lidar_file(
        ref_t: int,
        lidar_path: str,
        tot_frames: int,
    ) -> NDArray[np.float64]:
        """
        評価モードでLiDARデータを読み込む
        """
        frame_numbers: list[str] = [f"{ref_t + idx:06d}" for idx in range(tot_frames)]

        # 構築された各フレームのファイルパスをリスト化
        lidar_files: list[str] = [f"{lidar_path}{frame}.npy" for frame in frame_numbers]

        # 各ファイルからデータを読み込み、リストに格納
        lidar_frames: list[NDArray[np.float64]] = [
            np.load(file, allow_pickle=True) for file in lidar_files
        ]

        # フレームが1つの場合はそのまま、複数の場合は結合
        if tot_frames == 1:
            xyz: NDArray[np.float64] = lidar_frames[0]
        else:
            xyz: NDArray[np.float64] = np.concatenate(lidar_frames, axis=0)

        return np.ascontiguousarray(xyz, dtype=np.float64)

    def get_points(
        self,
        ref_t: int | None = None,
    ) -> tuple[NDArray[np.float64], float]:
        # 変数初期化
        ts: Final[float] = 0.0
        tot_frames: Final[int] = 1
        if ref_t is not None:
            self._ref_t = ref_t

        # データ取得処理
        packet_data = self._read_lidar_file(
            self._ref_t,
            self.file,
            tot_frames,
        )

        return packet_data, ts


class MID360Points:
    def __init__(
        self,
        index: int,
        lidar_config: dict[str, str | int],
        app_logger_factory: AppLoggerFactory,
    ) -> None:
        self._logger: AppLogger = app_logger_factory.register_from_type(self.__class__)

        self._index = index
        self._host_ip: str = str(lidar_config["dest_ip"])
        self._port: int = int(lidar_config["port_pnt"])
        self._logger.info("Host: %s", self._host_ip)

        self._logger.info("Host: %s", self._host_ip)
        self._logger.info("Port(PNT): %s", self._port)

        # mid360クラスを宣言したタイミングでMID360にも接続する。
        # point: 点群データ受け取り用。
        self._socket: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.connect()

    def __del__(self) -> None:
        self.disconnect()

    def connect(self) -> None:
        self._socket.bind((self._host_ip, self._port))
        self._socket.settimeout(0.1)
        self._logger.info("CONNECTION: OK")

    def disconnect(self) -> None:
        self._socket.close()
        self._logger.info("DISCONNECT: OK")

    @staticmethod
    def _get_x(dst_byte: bytes, init_idx: int, offset: int, i: int) -> float:
        # xyz[mm]から[m]に変換するために/1000する
        return (
            int.from_bytes(
                dst_byte[init_idx + offset * i : init_idx + 4 + offset * i],
                "little",
                signed=True,
            )
            / 1e3
        )

    @staticmethod
    def _get_y(dst_byte: bytes, init_idx: int, offset: int, i: int) -> float:
        # xyz[mm]から[m]に変換するために/1000する
        return (
            int.from_bytes(
                dst_byte[init_idx + 4 + offset * i : init_idx + 8 + offset * i],
                "little",
                signed=True,
            )
            / 1e3
        )

    @staticmethod
    def _get_z(dst_byte: bytes, init_idx: int, offset: int, i: int) -> float:
        # xyz[mm]から[m]に変換するために/1000する
        return (
            int.from_bytes(
                dst_byte[init_idx + 8 + offset * i : init_idx + 12 + offset * i],
                "little",
                signed=True,
            )
            / 1e3
        )

    @staticmethod
    def _get_reflect(dst_byte: bytes, init_idx: int, offset: int, i: int) -> int:
        return int.from_bytes(
            dst_byte[init_idx + 4 * 3 + offset * i : init_idx + 4 * 3 + 1 + offset * i],
            "little",
            signed=True,
        )

    @staticmethod
    def _get_timestamp(dst_byte: bytes) -> float:
        # xyz[mm]から[m]に変換するために/1000する
        return (
            int.from_bytes(
                dst_byte[
                    (1 + 2 + 2 + 2 + 2 + 1 + 1 + 1 + 12 + 4) : (
                        1 + 2 + 2 + 2 + 2 + 1 + 1 + 1 + 12 + 4 + 8
                    )
                ],
                "little",
                signed=True,
            )
            / 1e9
        )

    @staticmethod
    def _get_point(
        dst_byte: bytes,
        init_idx: int,
        offset: int,
        i: int,
    ) -> tuple[float, float, float, int]:
        x: float = MID360Points._get_x(dst_byte, init_idx, offset, i)
        y: float = MID360Points._get_y(dst_byte, init_idx, offset, i)
        z: float = MID360Points._get_z(dst_byte, init_idx, offset, i)
        reflect: int = MID360Points._get_reflect(dst_byte, init_idx, offset, i)
        return x, y, z, reflect

    def get_points(self) -> tuple[list[tuple[float, float, float, int]], float]:
        # パケットデータを取得 全体1380byteだが、少し多めに
        init_idx: int = 36  # 先頭から36バイト目以降に点群データが格納されている
        offset: int = 14  # 1ポイント毎のバイト数
        dst_byte, _ = self._socket.recvfrom(1500)
        packet_data: list[tuple[float, float, float, int]] = []

        # 1フレームごとに 14*96 byteのデータが送信される(96点分).
        for i in range(96):
            x, y, z, reflect = self._get_point(dst_byte, init_idx, offset, i)
            packet_data.append((x, y, z, reflect))

        ts: float = self._get_timestamp(dst_byte)
        return packet_data, ts
