from __future__ import annotations

import socket
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Final

import numpy as np
from numpy.typing import NDArray

from argus_synchro.common.app_logger import AppLogger, AppLoggerFactory
from argus_synchro.config.app_config import CANConf
from argus_synchro.diagnosis.error_diagnosis import ResultDiagnosis
from argus_synchro.shared_errors import SharedErrors, StateErrorIndex
from argus_synchro.shared_excepts import SharedCANExcept

if TYPE_CHECKING:
    import pandas as pd

CONVERTER_IP = "192.168.1.100"
CONVERTER_PORT = 2000
MASK_PGN = 0x1F


def handle_on_new_receive_return_canstr(
    bin_str: bytes,
    ip_address: str,
    port: int,
) -> tuple[bool, str, str]:
    """
    Parameters
    ----------
    bin_str : bytes
        J1939 コンバータから受信した生バイト列
    ip_address : str
        送信元 IP
    port : int
        送信元ポート

    Returns
    -------
    tuple[bool, Optional[str], Optional[str]]
        (成功フラグ, PGN 文字列, CAN データ文字列)
        マッチしない場合は (False, None, None)
    """

    # global pre_rotation_degree
    # CONVERTER_IP = ip_address #localhost経由でテストする際コメントアウト
    # CONVERTER_PORT = port
    if ip_address == CONVERTER_IP and port == CONVERTER_PORT:
        # バイト列 → 可変長リスト[int]
        bin_table: list[int] = list(bin_str)

        # Mask for deleting extra bit which is added by J1939 converter
        bin_table[0] &= MASK_PGN

        # Check PGNs (Priority, Reserved, Data Page, PDU Format, PDU Specific)

        # TODO: ここ常にTrueで良い?
        is_pgn1_matched: bool = (
            True  # all(bin_table[j] == HSC_CRANE_PGN1[j] for j in range(4))
        )
        is_pgn2_matched: bool = (
            True  # all(bin_table[j] == HSC_CRANE_PGN2[j] for j in range(4))
        )

        # Process rotation angle data
        if not (is_pgn1_matched or is_pgn2_matched):
            return (False, None, None)

        # 0-3 バイト: PGN, 4-7 バイト: データ
        pgn_string: str = "".join(f"{byte:02X}" for byte in bin_table[0:4])
        can_string: str = "".join(f"{byte:02X}" for byte in bin_table[4:])

        return (True, pgn_string, can_string)
    return (False, "", "")


class Can:
    def __init__(
        self,
        index: int,
        can: CANConf,
        app_logger_factory: AppLoggerFactory,
        ser: SharedErrors,
        sec_can: SharedCANExcept,
        canid_angle: str,  # TODO(NSW): AppConfigから取得するように変更する
        canid_lever: str,  # TODO(NSW): AppConfigから取得するように変更する
    ) -> None:
        self._logger: AppLogger = app_logger_factory.register_from_type(self.__class__)
        self._index: int = index
        self._handler: CanHandler = CanHandler(can, app_logger_factory)
        self.failedcount = 0
        self.udp_socket: socket.socket = self._create_udp_socket()
        self._ser: SharedErrors = ser
        self._sec_can: SharedCANExcept = sec_can
        self._last_received_time: float = 0.0
        self._timestamp: float | None = None
        self._canid_angle: str = canid_angle
        self._canid_lever: str = canid_lever
        self._err_config_load()

    def _err_config_load(self) -> None:
        self._err_config = self._ser.shared_err_conf.read()

        self._ser.state_errors_A_C[StateErrorIndex.CAN_COMM_QUALITY_DEGRADED].update(
            self._err_config
        )
        self._ser.state_errors_A_C[StateErrorIndex.CAN_COMM_QUALITY_ERROR].update(
            self._err_config
        )
        self._ser.state_errors_A_C[StateErrorIndex.CAN_INVALID_DATA_DIAGNOSIS].update(
            self._err_config
        )
        self._ser.state_errors_A_C[StateErrorIndex.CAN_INVALID_DATA_DIAGNOSIS].update(
            self._err_config
        )

    def _create_udp_socket(self) -> socket.socket:
        # Set up UDP
        sock: socket.socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )
        sock.bind(("0.0.0.0", 2000))  # Bind to all interfaces
        sock.settimeout(0.1)
        return sock

    def receive_can_data(self) -> tuple[str, tuple[float, ...] | None]:
        """
        Returns
        -------
        can_id_str : str
            受信したCANIDを16進数で表した文字列
        recv_data : tuple[float]
            受信したデータを物理値にした値のタプル(1メッセージから複数の値を取得する場合のためタプル)
        """
        # self._logger.info("receive_start_without_lib start")
        can_id_str = "00000000"
        recv_data = None
        data: bytes = b""
        (ip_address, port) = ("", 0)

        sucsess: bool = False
        is_data_received: bool = False
        canid: str = ""
        candata: str = ""
        try:
            data, (ip_address, port) = self.udp_socket.recvfrom(1024)
        except TimeoutError:
            self.failedcount += 1
        else:
            sucsess = True
            self.failedcount = 0
            self._timestamp = time.perf_counter()
            self._sec_can.last_received.value = self._timestamp
            is_data_received, canid, candata = handle_on_new_receive_return_canstr(
                data,
                ip_address,
                port,
            )

        now: float = time.perf_counter()
        can_comm_quality_degraded = self._ser.state_errors_A_C[
            StateErrorIndex.CAN_COMM_QUALITY_DEGRADED
        ]
        result = can_comm_quality_degraded.errors_diagnosis(
            canid,
            self.failedcount,
            self._timestamp,
            now,
        )
        can_comm_quality_degraded.log_output(
            *result, StateErrorIndex.CAN_COMM_QUALITY_DEGRADED
        )

        can_comm_quality_error = self._ser.state_errors_A_C[
            StateErrorIndex.CAN_COMM_QUALITY_ERROR
        ]
        result = can_comm_quality_error.errors_diagnosis(
            canid,
            self.failedcount,
            self._timestamp,
            now,
        )
        can_comm_quality_error.log_output(
            *result, StateErrorIndex.CAN_COMM_QUALITY_ERROR
        )

        if sucsess:
            can_invalid_data = self._ser.state_errors_A_C[
                StateErrorIndex.CAN_INVALID_DATA_DIAGNOSIS
            ]
            result: tuple[ResultDiagnosis, ResultDiagnosis] = (
                can_invalid_data.errors_diagnosis(canid, candata, now)
            )
            can_invalid_data.log_output(
                *result, StateErrorIndex.CAN_INVALID_DATA_DIAGNOSIS
            )
            candata_invalid: ResultDiagnosis = result[0]

            if is_data_received and candata_invalid in (
                ResultDiagnosis.NORMAL,
                ResultDiagnosis.RECOVERY,
            ):
                # resultdatから対応するアドレスのhandlerを呼び出してdecodeする
                can_id_str, recv_data = self._handler.dispatch(canid, candata)
            else:
                pass
                # rts = "udp_socket - handle_on_new_receive error"
                # self._logger.info("setRecordState error. status:%d", rts)

        return can_id_str, recv_data

    def get_yaw_angle_deg(self) -> int:
        err_msg = f"class: {self.__class__.__name__}, method: get_yaw_angle_deg()"
        raise NotImplementedError(err_msg)


class CanHandler:
    """
    CANフレームを受信し、IDごとに登録されたハンドラへディスパッチする
    """

    def __init__(
        self,
        can_conf: CANConf,
        app_logger_factory: AppLoggerFactory,
    ) -> None:
        self._logger: AppLogger = app_logger_factory.register_from_type(self.__class__)
        self.update(can_conf)
        self.__RESULT_INDEX_CANID: Final[int] = 0
        self.__RESULT_INDEX_CANDATA: Final[int] = 1

    def update(self, can_conf: CANConf) -> None:
        import pandas as pd

        self._logger.info("CanHandler start")

        # CAN ID→ハンドラ関数のマッピングを構築
        can_id_map: pd.DataFrame = pd.read_csv(  # type: ignore
            can_conf.can_id_map_file,
            header=None,
        )
        self._yaw_offset_deg: float = can_conf.yaw_offset_deg

        self._logger.info(f"CanHandler - can_id_map: {can_id_map}")

        # can_id_mapの列1をkeyとして列2をkeyに対応するメソッドとする辞書を作成
        # { "18FC4003": self.handle_angle_oldcan, ... }
        self._handler_map: dict[str, Callable[[Sequence[str]], tuple[float, ...]]] = {}

        for key, funcname in [
            (k[0], k[1])
            for k in can_id_map.to_dict(orient="records")  # type: ignore
        ]:
            self._logger.info(f"CanHandler - (key,funcname): ({key}, {funcname})")
            method: Callable[[Sequence[str]], tuple[float, ...]] = getattr(
                self,
                funcname,
            )
            self._logger.info(f"CanHandler - setup: ({key}, {funcname})")
            self._handler_map[key.upper().lstrip("0X")] = method

        self._logger.info(f"CanHandler - self._handler_map: {self._handler_map}")

    def dispatch(self, can_id: str, data: str) -> tuple[str, tuple[float, ...] | None]:
        """受信フレームを適切なハンドラへ振り分け"""
        can_id_str: str = can_id.upper().lstrip("0X")
        received_data: tuple[float, ...] | None

        # 登録済みハンドラーに存在すれば呼び出し
        handler = self._handler_map.get(can_id_str)
        received_data = handler((can_id, data)) if handler else None

        return can_id_str, received_data

    def handle_angle_oldcan(self, resultdat: Sequence[str]) -> tuple[float]:
        """
        旋回角度取得(old_can)
        """
        raw_data: str = resultdat[self.__RESULT_INDEX_CANDATA]
        current_degree: float = 360.0 - (int(raw_data[4:8], 16) / 10.0)

        yaw_angle_deg = current_degree - self._yaw_offset_deg
        self._logger.info(
            "handle_angle_oldcan, can deg(old, handler): %f",
            yaw_angle_deg,
        )

        return (yaw_angle_deg,)

    def handle_angle_newcan(self, resultdat: Sequence[str]) -> tuple[float]:
        """
        旋回角度取得(new_can)
        """
        tmp_string: str = resultdat[self.__RESULT_INDEX_CANDATA]
        current_degree: float = (
            int(tmp_string[:2], 16) + int(tmp_string[2:4], 16) * 255
        ) / (13400.0 / 360.0)

        yaw_angle_deg = current_degree - self._yaw_offset_deg
        self._logger.info(
            "handle_angle_newcan, can deg(new, handler): %f",
            yaw_angle_deg,
        )

        return (yaw_angle_deg,)

    def handle_lever(self, resultdat: Sequence[str]) -> tuple[float, ...]:
        """
        レバー圧力取得
        """
        msg_data: str = resultdat[self.__RESULT_INDEX_CANDATA]
        self._logger.info(
            "handle_lever, lever handler data: %s, %s",
            resultdat[self.__RESULT_INDEX_CANID],
            resultdat[self.__RESULT_INDEX_CANDATA],
        )

        payload: str = msg_data[:-2]  # 末尾2桁は DLC
        b: bytes = bytes.fromhex(payload)
        lever_pressure: tuple[float, ...] = tuple(
            int.from_bytes(b[i : i + 2], "big") * 0.001  # 無符号 16 bit ×0.001
            for i in (0, 2, 4, 6)
        )

        self._logger.info(
            "handle_lever, lever handler data: %f, %f, %f, %f",
            *lever_pressure[0:4],
        )

        return lever_pressure

    # ...同様に必要があれば他のIDごとにメソッドを追加...


class LoadTableDataInterface(ABC):
    @abstractmethod
    def get_angle_data(
        self,
        can_data: pd.DataFrame,
        is_old: bool,
    ) -> pd.Series: ...

    @abstractmethod
    def get_raw_table_data(self, c_filepath: str) -> pd.DataFrame: ...

    @abstractmethod
    def get_lever_data(self, can_data: pd.DataFrame) -> pd.Series: ...


class LoadFileTableData(LoadTableDataInterface):
    def get_angle_data(
        self,
        can_data: pd.DataFrame,
        is_old: bool,
    ) -> pd.Series:
        import pandas as pd

        if can_data.empty:
            angle_data: pd.Series = pd.Series()

        else:
            angle_data = self._get_angle_data(
                can_data,
                is_old,
            )

        return angle_data

    def _get_angle_data(self, can_df: pd.DataFrame, is_old: bool) -> pd.Series:
        if is_old:
            angle_data: pd.Series = can_df["o_msg"]
        else:
            angle_data: pd.Series = can_df["n_msg"]

        return angle_data

    def get_raw_table_data(
        self,
        c_filepath: str,
    ) -> pd.DataFrame:
        import pandas as pd

        if c_filepath != "None":
            angle_data: pd.DataFrame = pd.read_csv(c_filepath)  # type: ignore
        else:
            # ファイル名Noneの時
            angle_data = pd.DataFrame()
        return angle_data

    def get_lever_data(self, can_data: pd.DataFrame) -> pd.Series:
        import pandas as pd

        if "lever_msg" in can_data.columns:
            lever_data: pd.Series = can_data["lever_msg"]
        else:
            lever_data = pd.Series()
        return lever_data


class CanFile:
    def __init__(
        self,
        can_conf: CANConf,
        app_logger_factory: AppLoggerFactory,
    ) -> None:
        """
        argus_synchro
        Scrutinizerクラスの__init__を参考に
        """
        self.update(can_conf)
        self._logger: AppLogger = app_logger_factory.register_from_type(self.__class__)
        # ファイル読み込みの時は、最初にテーブルデータ読み込み.
        self.load_table_data: LoadTableDataInterface = LoadFileTableData()

        can_data: pd.DataFrame = self.load_table_data.get_raw_table_data(
            self.c_filepath,
        )
        self.angle_data: pd.Series = self.load_table_data.get_angle_data(
            can_data=can_data,
            is_old=self.is_old,
        )

    def update(self, can_conf: CANConf) -> None:
        """CAN設定を更新する"""
        self._yaw_offset_deg: float = can_conf.yaw_offset_deg

        self.is_old = can_conf.IsOld
        self.c_filepath = can_conf.c_file

    def _can_msg_to_data(self, can_msg: str) -> NDArray[np.uint8]:
        """16 進文字列 → 8 byte NDArray[uint8] へ変換"""
        # str = "100234addf45893408"
        msg = can_msg
        data: NDArray[np.uint8] = np.zeros(8).astype(np.uint8)
        for i in range(8):
            data[i] = int(msg[i * 2 : (i + 1) * 2], 16)
            # AppLogger.info("{:02X}".format(data[i]))
        return data

    def pick_row(self, df: pd.Series, row_num: int) -> str:
        return df[row_num]

    def receive_can_data(self, ref_t: int) -> tuple[str, tuple[float, ...]]:
        """
        ファイルからyaw_angle_dataを呼んで角度を返す

        Scrutinizerクラスの607行目でコールしている関数・クラスを参考に
        """

        """
        Parameters
        ----------
        sc_can : SharedClasses.Shared_can
            共有メモリ (yaw 角などを保持)
        can_conf : CANConf
            システム設定
        ls_can_det : LShared_can
            呼び出し元保持の構造体 (結果を書き戻す)
        angle_data : pandas.DataFrame
            CANログを読み込んだDataFrame
        ref_t : int
            何行目をデコードするか

        Returns
        -------
        LShared_can
            更新済み構造体
        """
        can_id = "00000000"
        # 1) ログが空ならオフセットだけ設定して終了
        if self.angle_data.empty:
            return can_id, (self._yaw_offset_deg,)

        # 3) 対象行を抽出しmsg文字列を取り出す (列名はサブクラス依存)
        raw_msg: str = self.pick_row(self.angle_data, ref_t)
        # raw_msg: str = row_dict[self.msg_col]

        # 4) 文字列 → 8byte配列
        msg_bytes: NDArray[np.uint8] = self._can_msg_to_data(raw_msg)

        if self.is_old:
            """
                旋回角度取得(old_can)
                """
            can_id = "18FCE402"
            # 0-16
            # AppLogger.info(f'CAN-ID:{self.msg.id:x}, TIMESTAMP:{self.msg.timestamp_ms}, SIZE:{self.msg.size}, DATA:{msg_data[0:8]}',file=self.fresult)
            # scに旋回角度を格納(0,1:右側旋回ポテンショ[10*V]、2,3:左側旋回ポテンショ[10*V]、4,5:旋回位置[10*deg]、6,7:現在旋回速度[10*rad/sec])
            tmp_string: str = f"{msg_bytes[2]:02X}{msg_bytes[3]:02X}"
            current_degree = 360 - int(tmp_string, 16) / 10.0
            can_data = ((current_degree + self._yaw_offset_deg),)
            self._logger.info(
                "handle_angle_oldcan, can deg(old, handler): %f",
                can_data[0],
            )
        else:
            """
                旋回角度取得(new_can)
                """
            can_id = "18FFD1D1"
            tmp_string: str = f"{msg_bytes[0]:02X}{msg_bytes[1]:02X}{msg_bytes[2]:02X}{msg_bytes[3]:02X}"
            current_degree = (
                int(tmp_string[:2], 16) + int(tmp_string[2:4], 16) * 255
            ) / (13400.0 / 360.0)
            can_data = ((current_degree - self._yaw_offset_deg),)
            self._logger.info(
                "handle_angle_newcan, can deg(new, handler): %f",
                can_data[0],
            )
        return can_id, can_data

    def change_file_name_index(self, file_name: str) -> None:
        self.c_filepath = file_name
        can_data: pd.DataFrame = self.load_table_data.get_raw_table_data(
            self.c_filepath,
        )
        self.angle_data: pd.Series = self.load_table_data.get_angle_data(
            can_data=can_data,
            is_old=self.is_old,
        )
