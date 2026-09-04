from __future__ import annotations

import json
import time
from configparser import (
    DuplicateOptionError,
    DuplicateSectionError,
    MissingSectionHeaderError,
    NoOptionError,
    NoSectionError,
    ParsingError,
)

import argus_synchro.diagnosis.error_config as err_conf
from argus_synchro.diagnosis.error_diagnosis import (
    ActionErrorDiagnosisA,
    ActionErrorDiagnosisB,
    ActionErrorDiagnosisC,
)
from argus_synchro.shared_excepts import SharedLidarShiftMonitorExcept


class LidarPositionMisalignmentDetectedDiagnosis(ActionErrorDiagnosisA):
    """LIDAR_POSITION_MISALIGNMENT_DETECTED: LiDAR位置ズレ検出"""

    def __init__(self) -> None:
        super().__init__()

    def update(self, err_conf: err_conf.ErrorConfig) -> None:
        self.param: err_conf.LidarPositionMisalignmentDetectedParameters = (
            err_conf.lidar_position_misalignment_detected
        )
        self.is_enabled = self.param.is_enabled

    def _parse_args(self, *args: object) -> SharedLidarShiftMonitorExcept:
        """
        args[0] (SharedLidarShiftMonitorExcept) :
        """
        if len(args) != 1:
            raise ValueError("args must be (sec_lidar_sm,)")
        sec_lidar_sm = args[0]

        if not isinstance(sec_lidar_sm, SharedLidarShiftMonitorExcept):
            raise ValueError("args must be (SharedLidarShiftMonitorExcept,)")

        return sec_lidar_sm

    def detect_error(self, *args: object) -> bool:
        sec_lidar_sm: SharedLidarShiftMonitorExcept = self._parse_args(*args)
        if sec_lidar_sm.has_not_calibrated:
            # NOTE: 校正未実施フラグが立っている場合は、LiDAR位置ズレ検出の診断を行わない
            return False

        if sec_lidar_sm.is_shifted_fast.value or sec_lidar_sm.is_shifted_slow.value:
            self.increment_counter()
            self.is_idle.value = True
            self.is_fail_safe.value = True
            sec_lidar_sm.write_has_not_calibrated(True)
            return True

        return False

    def detect_recovery_error(self, *args: object) -> bool:
        # 復帰条件が無いため、常にFalseを返す
        return False

    def detect_recovery_fail_safe(self, *args: object) -> bool:
        # 復帰条件が無いため、常にFalseを返す
        return False

    def log_output(self, err: bool, recover: bool, err_idx: int, *args: object) -> None:
        if err:
            self._error_log_output(err_idx, *args)

    def _error_log_output(self, err_idx: int, *args: object) -> None:
        self._logger.error(
            self.get_error_no(err_idx)
            + ": LIDAR_POSITION_MISALIGNMENT_DETECTED: LiDAR位置ズレ検出. LiDARの位置がずれていないかを確認してください。 "
        )


class SensorCalibrationRequiredDiagnosis(ActionErrorDiagnosisA):
    """SENSOR_CALIBRATION_REQUIRED: 要センサ校正"""

    def __init__(self) -> None:
        super().__init__()
        self._last_detect_error_pid: int = 0
        self._last_detect_recovery_fail_safe_pid: int = 0

    def update(self, err_conf: err_conf.ErrorConfig) -> None:
        self.param: err_conf.SensorCalibrationRequiredParameters = (
            err_conf.sensor_calibration_required
        )
        self.is_enabled = self.param.is_enabled

    def _parse_args(self, *args: object) -> tuple[SharedLidarShiftMonitorExcept, int]:
        """
        args[0] (SharedLidarShiftMonitorExcept) :
        args[1] (int) : 実行プロセスID
        """
        if len(args) != 2:
            raise ValueError("args must be (sec_lidar_sm, pid)")
        sec_lidar_sm = args[0]
        pid = args[1]

        if not isinstance(sec_lidar_sm, SharedLidarShiftMonitorExcept):
            raise ValueError("args must be (SharedLidarShiftMonitorExcept, pid)")

        if not isinstance(pid, int):
            raise ValueError("args must be (SharedLidarShiftMonitorExcept, int)")

        return sec_lidar_sm, pid

    def detect_error(self, *args: object) -> bool:
        # NOTE: この診断はプロセス起動毎に1回のみ行う

        sec_lidar_sm, pid = self._parse_args(*args)
        if pid == self._last_detect_error_pid:
            return False
        self._last_detect_error_pid = pid

        if sec_lidar_sm.has_not_calibrated:
            self.increment_counter()
            self.is_idle.value = True
            self.is_fail_safe.value = True
            return True
        return False

    def detect_recovery_error(self, *args: object) -> bool:
        # 復帰条件が無いため、常にFalseを返す
        return False

    def detect_recovery_fail_safe(self, *args: object) -> bool:
        # NOTE: この診断はプロセス起動毎に1回のみ行う
        sec_lidar_sm, pid = self._parse_args(*args)
        if pid == self._last_detect_recovery_fail_safe_pid:
            return False
        self._last_detect_recovery_fail_safe_pid = pid
        if not sec_lidar_sm.has_not_calibrated:
            self.is_idle.value = False
            self.is_fail_safe.value = False
            return True
        return False

    def log_output(self, err: bool, recover: bool, err_idx: int, *args: object) -> None:
        if err:
            self._error_log_output(err_idx)
        elif recover:
            self._fail_safe_recover_log_output(err_idx)

    def _error_log_output(self, err_idx: int, *args: object) -> None:
        self._logger.error(
            self.get_error_no(err_idx)
            + ": 要センサ校正: LiDARの校正を実施してください。"
        )

    def _fail_safe_recover_log_output(self, err_idx: int, *args: object) -> None:
        self._logger.warning(
            self.get_error_no(err_idx)
            + ": 要センサ校正: LiDARの校正完了を確認しました。"
        )


class ModelInfoMismatchDiagnosis(ActionErrorDiagnosisA):
    """MODEL_INFO_MISMATCH: 機種情報不一致"""

    def __init__(self) -> None:
        super().__init__()

    def detect_error(self, *args: object) -> bool:
        return False

    def detect_recovery_error(self, *args: object) -> bool:
        return True

    def detect_recovery_fail_safe(self, *args: object) -> bool:
        return True


class CraneModelFileMissingDiagnosis(ActionErrorDiagnosisA):
    """CRANE_MODEL_FILE_MISSING: 機体モデルファイル欠損/破損"""

    def __init__(self) -> None:
        super().__init__()

    def excepts_diagnosis(self, e: Exception) -> bool:
        is_target = isinstance(
            e,
            (
                FileNotFoundError,
                PermissionError,
                IsADirectoryError,
                NotADirectoryError,
                OSError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                ValueError,
                KeyError,
                RuntimeError,
            ),
        )
        if is_target:
            self.increment_counter()
        return is_target

    def detect_error(self, *args: object) -> bool:
        return False

    def detect_recovery_error(self, *args: object) -> bool:
        return True

    def detect_recovery_fail_safe(self, *args: object) -> bool:
        return True

    def log_output(self, err: bool, recover: bool, err_idx: int, *args: object) -> None:
        if err:
            self._error_log_output(err_idx, *args)

    def _error_log_output(self, err_idx: int, *args: object) -> None:
        if len(args) != 1 or not isinstance(args[0], Exception):
            raise ValueError("args must be (Exception,)")
        self._logger.error(
            self.get_error_no(err_idx)
            + f": CRANE_MODEL_FILE_MISSING: {args[0]!r}",
            exc_info=True,
        )


class ConfigFileMissingDiagnosis(ActionErrorDiagnosisA):
    """CONFIG_FILE_MISSING: 設定ファイル欠損/破損"""

    def __init__(self) -> None:
        super().__init__()
        self._last_counted_mono: float = 0.0
        self._last_counted_signature: tuple[str, str] | None = None
        self._counter_throttle_sec: float = 1.0

    def _io_error(self, e: Exception) -> bool:
        return bool(
            isinstance(
                e,
                (
                    FileNotFoundError,  # パスが存在しない。
                    PermissionError,  # 読み取り権限が無い。
                    IsADirectoryError,  # ファイルじゃなくディレクトリだった
                    NotADirectoryError,  # パスの一部がディレクトリじゃなかった
                    OSError,  # デバイス・I/O エラー、パス長、ファイルシステム不調など
                ),
            )
        )

    def _unicode_error(self, e: Exception) -> bool:
        return bool(
            isinstance(
                e,
                (
                    UnicodeDecodeError,  # バイナリだった
                    UnicodeError,  # 文字コード異常全般
                ),
            )
        )

    def _config_parse_error(self, e: Exception) -> bool:
        return bool(
            isinstance(
                e,
                (
                    NoOptionError,  # 要素が存在しない
                    NoSectionError,  # セクションが存在しない
                    MissingSectionHeaderError,  # セクションヘッダ欠損
                    ParsingError,  # ini構文エラー
                    DuplicateOptionError,  # option重複
                    DuplicateSectionError,  # section重複
                    ValueError,  # getboolean/getint などの型変換エラー
                ),
            )
        )

    def _should_increment_counter(self, e: Exception) -> bool:
        now_mono = time.monotonic()
        error_message = str(e)
        signature = (
            type(e).__name__,
            error_message.splitlines()[0] if error_message else "",
        )
        elapsed = now_mono - self._last_counted_mono

        if (
            self._last_counted_signature == signature
            and elapsed < self._counter_throttle_sec
        ):
            return False

        self._last_counted_mono = now_mono
        self._last_counted_signature = signature
        return True

    def excepts_diagnosis(self, e: Exception) -> bool:
        ret: bool = False
        ret = self._io_error(e) or self._unicode_error(e) or self._config_parse_error(e)
        if ret and self._should_increment_counter(e):
            self.increment_counter()
        return ret

    def detect_error(self, *args: object) -> bool:
        # 未使用
        return False

    def detect_recovery_error(self, *args: object) -> bool:
        # 未使用
        return True

    def detect_recovery_fail_safe(self, *args: object) -> bool:
        # 未使用
        return True

    def log_output(self, err: bool, recover: bool, err_idx: int, *args: object) -> None:
        if err:
            self._error_log_output(err_idx, *args)

    def _error_log_output(self, err_idx: int, *args: object) -> None:
        if len(args) != 1 or not isinstance(args[0], Exception):
            raise ValueError("args must be (Exception,)")
        error = args[0]
        error_message = str(error)
        self._logger.error(
            self.get_error_no(err_idx)
            + ": CONFIG_FILE_MISSING: "
            + f"{type(error).__name__}: "
            + (error_message.splitlines()[0] if error_message else ""),
            exc_info=True,
        )


class SensorCalibDataInvalidDiagnosis(ActionErrorDiagnosisB):
    """SENSOR_CALIB_DATA_INVALID: センサ校正データ不正"""

    def __init__(self) -> None:
        super().__init__()

    def detect_error(self, *args: object) -> bool:
        return False

    def detect_recovery_error(self, *args: object) -> bool:
        return True

    def detect_recovery_fail_safe(self, *args: object) -> bool:
        return True


class CameraXCalibDataInvalidDiagnosis(ActionErrorDiagnosisB):
    """CAMERA_N_CALIB_DATA_INVALID: カメラN校正データ不正"""

    def __init__(self) -> None:
        super().__init__()

    def detect_error(self, *args: object) -> bool:
        return False

    def detect_recovery_error(self, *args: object) -> bool:
        return True

    def detect_recovery_fail_safe(self, *args: object) -> bool:
        return True


class MmapReadWriteErrorDiagnosis(ActionErrorDiagnosisB):
    """MMAP_READ_WRITE_ERROR: MMAP read/writeエラー"""

    def __init__(self) -> None:
        super().__init__()

    def detect_error(self, *args: object) -> bool:
        return False

    def detect_recovery_error(self, *args: object) -> bool:
        return True

    def detect_recovery_fail_safe(self, *args: object) -> bool:
        return True


class RebootLoopDetectedDiagnosis(ActionErrorDiagnosisA):
    """REBOOT_LOOP_DETECTED: 再起動ループ検出"""

    def __init__(self) -> None:
        super().__init__()

    def detect_error(self, *args: object) -> bool:
        return False

    def detect_recovery_error(self, *args: object) -> bool:
        return True

    def detect_recovery_fail_safe(self, *args: object) -> bool:
        return True


class AiModelLoadFailed(ActionErrorDiagnosisB):
    """AI_MODEL_LOAD_FAILED: AIモデルロード失敗/破損"""

    def __init__(self) -> None:
        super().__init__()

    def excepts_diagnosis(self, e: Exception) -> bool:
        is_target = isinstance(
            e,
            (
                FileNotFoundError,
                PermissionError,
                OSError,
                RuntimeError,
                ValueError,
                ImportError,
                ModuleNotFoundError,
            ),
        )
        if is_target:
            self.increment_counter()
        return is_target

    def detect_error(self, *args: object) -> bool:
        return False

    def detect_recovery_error(self, *args: object) -> bool:
        return True

    def detect_recovery_fail_safe(self, *args: object) -> bool:
        return True

    def log_output(self, err: bool, recover: bool, err_idx: int, *args: object) -> None:
        if err:
            self._error_log_output(err_idx, *args)

    def _error_log_output(self, err_idx: int, *args: object) -> None:
        if len(args) != 1 or not isinstance(args[0], Exception):
            raise ValueError("args must be (Exception,)")
        self._logger.error(
            self.get_error_no(err_idx)
            + f": AI model initialization failed: {args[0]!r}"
        )


class OperationModeTransitionErrorDiagnosis(ActionErrorDiagnosisB):
    """OPERATION_MODE_TRANSITION_ERROR: 動作モード遷移エラー"""

    def __init__(self) -> None:
        super().__init__()

    def detect_error(self, *args: object) -> bool:
        return False

    def excepts_diagnosis(self, e: Exception) -> bool:
        ret = isinstance(e, RuntimeError)
        if ret:
            self.increment_counter()
        return ret

    def detect_recovery_error(self, *args: object) -> bool:
        return True

    def detect_recovery_fail_safe(self, *args: object) -> bool:
        return True

    def log_output(self, err: bool, recover: bool, err_idx: int, *args: object) -> None:
        if err:
            self._error_log_output(err_idx)

    def _error_log_output(self, err_idx: int, *args: object) -> None:
        self._logger.warning(
            self.get_error_no(err_idx)
            + ": 動作モード遷移エラー:動作モード遷移中にエラーが発生しました。再起動します。セットアップ実行中の場合は、初めからやり直して下さい。"
        )


class LogFileIoErrorDiagnosis(ActionErrorDiagnosisB):
    """LOG_FILE_IO_ERROR: ログファイルI/Oエラー"""

    def __init__(self) -> None:
        super().__init__()
        self._last_counted_mono: float = 0.0
        self._last_counted_signature: tuple[str, str] | None = None
        self._counter_throttle_sec: float = 1.0

    def _should_increment_counter(self, e: Exception) -> bool:
        now_mono = time.monotonic()
        signature = (type(e).__name__, str(e).splitlines()[0] if str(e) else "")
        elapsed = now_mono - self._last_counted_mono
        if (
            self._last_counted_signature == signature
            and elapsed < self._counter_throttle_sec
        ):
            return False
        self._last_counted_mono = now_mono
        self._last_counted_signature = signature
        return True

    def excepts_diagnosis(self, e: Exception) -> bool:
        if isinstance(e, OSError):
            if self._should_increment_counter(e):
                self.increment_counter()
            return True
        return False

    def detect_error(self, *args: object) -> bool:
        return False

    def detect_recovery_error(self, *args: object) -> bool:
        return True

    def detect_recovery_fail_safe(self, *args: object) -> bool:
        return True


class ReserveActionABC(ActionErrorDiagnosisC):
    def __init__(self) -> None:
        super().__init__()

    def detect_error(self, *args: object) -> bool:
        return False

    def detect_recovery_error(self, *args: object) -> bool:
        return True

    def detect_recovery_fail_safe(self, *args: object) -> bool:
        return True


class ProcessStartupErrorDiagnosis(ActionErrorDiagnosisB):
    """PROCESS_STARTUP_ERROR: プロセス起動エラー"""

    def __init__(self) -> None:
        super().__init__()

    def detect_error(self, *args: object) -> bool:
        return False

    def excepts_diagnosis(self, e: Exception) -> bool:
        ret = isinstance(e, RuntimeError)
        if ret:
            self.increment_counter()
        return ret

    def detect_recovery_error(self, *args: object) -> bool:
        return True

    def detect_recovery_fail_safe(self, *args: object) -> bool:
        return True

    def log_output(self, err: bool, recover: bool, err_idx: int, *args: object) -> None:
        if err:
            self._error_log_output(err_idx)

    def _error_log_output(self, err_idx: int, *args: object) -> None:
        self._logger.warning(
            self.get_error_no(err_idx)
            + ": プロセス起動エラー:プロセス起動中にエラーが発生しました。再起動します。セットアップ実行中の場合は、初めからやり直して下さい。"
        )
