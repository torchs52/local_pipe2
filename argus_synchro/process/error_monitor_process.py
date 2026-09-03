from __future__ import annotations

import time
from multiprocessing.sharedctypes import Synchronized
from pathlib import Path
from typing import Literal, final

from argus_synchro_lib.error_mmap_writer import ErrorMMapWriter

from argus_synchro.common import paths
from argus_synchro.common.paths import normalize_path
from argus_synchro.process import ProcessBase
from argus_synchro.process.synchronizer import ProcessActivator
from argus_synchro.shared_data import create_shared_single_data
from argus_synchro.shared_errors import SharedErrors


@final
class ErrorMonitorProcess(ProcessBase):
    """
    エラー監視プロセス
    """

    __slots__ = (
        "_cycle",
        "_paths",
        "_ser",
        "_system_activator",
    )

    def __init__(
        self,
        ser: SharedErrors,
        system_activator: ProcessActivator,
        directory_config: paths.DirectoryConfig,
        cycle: float = 1 / 5,
        name: str | None = None,
    ) -> None:
        super().__init__(ser.ErrMoni_ex, system_activator, name=name)
        self._directory_config = directory_config
        self._ser: SharedErrors = ser
        self._system_activator: ProcessActivator = system_activator
        self._cycle: float = cycle  # fpsの逆数(秒)
        log_dir: Path = paths.get_mmap_dir(self._directory_config)
        err0_path: Path = normalize_path("./err0.dat", log_dir)
        err1_path: Path = normalize_path("./err1.dat", log_dir)
        self._paths: list[str] = [str(err0_path), str(err1_path)]
        # startupで宣言
        self._mmap: ErrorMMapWriter
        self.affinity_cores = [0]

    def _config_load(self) -> None:
        pass

    def create_producer_and_consumer(self) -> None:
        pass

    def restart_completed(self) -> None:
        pass

    def _startup(self) -> None:
        self._config_load()
        self._mmap = ErrorMMapWriter(
            self._paths, lambda level, msg: self._logger.log(int(level), msg)
        )
        self._mmap.init()

    def _log_register(self) -> None:
        super()._log_register()
        self._ser.log_register(self._app_logger_factory)

    def _shutdown(self) -> None:
        self._mmap.close()

    def _loop(self) -> None:
        while self._system_activator.value:
            self._update()
            time.sleep(self._cycle)

    def _update(self) -> None:
        self._mmap.start_write()
        state_err: bytes = self._make_state_error_bits(self._ser.state_errors)
        self._mmap.write_state_error(state_err)
        action_err: bytes = self._make_action_error_bits(self._ser.action_errors)
        self._mmap.write_action_error(action_err)

        camera_connected: tuple[bool, ...] = self._ser.get_cameras_connected()
        lidar_connected: tuple[bool, ...] = self._ser.get_lidars_connected()
        status: bytes = self._make_status_bits(
            self._ser,
            camera_connected=camera_connected,
            lidar_connected=lidar_connected,
        )
        self._mmap.write_status(status)
        self._mmap.rotate_if_busy()

    def _start_restart(self) -> None:
        pass

    def _make_state_error_bits(
        self,
        error_list: tuple[Synchronized[bool], ...],
        byteorder: Literal["little", "big"] = "little",
        num_bytes: int = 16,
    ) -> bytes:
        """
        状態エラーリストからエラーフラグのビット列を作成する
        """
        err_bits: int = sum((int(err.value) << i) for i, err in enumerate(error_list))
        # 念のため範囲外のbitをマスク
        err_bits &= (1 << (num_bytes * 8)) - 1
        return err_bits.to_bytes(num_bytes, byteorder)

    def _make_action_error_bits(
        self,
        error_list: tuple[Synchronized[int], ...],
        byteorder: Literal["little", "big"] = "little",
        num_bytes: int = 32,
    ) -> bytes:
        """
        動作エラーリストからエラーカウンタのビット列を作成する
        """
        err_bits: int = sum((err.value << (i * 8)) for i, err in enumerate(error_list))
        err_bits &= (1 << (num_bytes * 8)) - 1
        return err_bits.to_bytes(num_bytes, byteorder)

    def _make_status_bits(
        self,
        ser: SharedErrors,
        camera_connected: tuple[bool, ...],
        lidar_connected: tuple[bool, ...],
        byteorder: Literal["little", "big"] = "little",
        num_bytes: int = 3,
    ) -> bytes:
        """
        各状態からステータスのビット列を作成する
        """
        reduced_load_mode_bits: int = int(ser.reduced_load_mode.enabled)
        camera_connected_bits: int = sum(
            (int(connected) << i) for i, connected in enumerate(camera_connected)
        )
        lidar_connected_bits: int = sum(
            (int(connected) << i) for i, connected in enumerate(lidar_connected)
        )

        self._logger.debug(
            f"Reduced Load Mode: {reduced_load_mode_bits}, "
            f"Camera Connected: {camera_connected_bits:08b}, "
            f"Lidar Connected: {lidar_connected_bits:08b}"
        )

        statuses: tuple[int, ...] = (
            reduced_load_mode_bits,
            camera_connected_bits,
            lidar_connected_bits,
        )
        return b"".join(statuses[i].to_bytes(1, byteorder) for i in range(num_bytes))
