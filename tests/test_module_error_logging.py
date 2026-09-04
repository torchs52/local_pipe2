from pathlib import Path

import argus_synchro.diagnosis.state_d_errors as state_d_errors
from argus_synchro.common.app_logger import DEBUG, AppLoggerFactory
from argus_synchro.diagnosis.error_config import ErrorConfig
from argus_synchro.diagnosis.error_diagnosis import ResultDiagnosis
from argus_synchro.diagnosis.state_d_errors import (
    AccumulationModuleError,
    CameraModuleError,
    LidarModuleError,
)
from argus_synchro.shared_errors import ModuleErrorIndex


def test_module_error_log_contains_caught_exception_traceback(tmp_path: Path) -> None:
    log_path = tmp_path / "module-error.log"
    diagnosis = CameraModuleError()
    logger_factory = AppLoggerFactory(
        to_console=False,
        to_file=str(log_path),
        level=DEBUG,
        compress=False,
    )
    diagnosis.log_register(logger_factory)
    logger_factory.update()

    try:
        raise RuntimeError("camera read failed")
    except RuntimeError as error:
        diagnosis.log_output(
            ResultDiagnosis.DETECTION,
            ResultDiagnosis.NORMAL,
            ModuleErrorIndex.CAMERA_MODULE_ERROR,
            error,
            2,
        )

    log_text = log_path.read_text(encoding="utf-8")
    assert "カメラ2モジュールエラー: RuntimeError: camera read failed" in log_text
    assert "Traceback (most recent call last):" in log_text
    assert "RuntimeError: camera read failed" in log_text


def test_camera_module_error_throttles_through_vendor_log_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_path = tmp_path / "throttled-module-error.log"
    diagnosis = CameraModuleError()
    error_config = ErrorConfig()
    error_config.camera_module_error.is_enabled = True
    error_config.camera_module_error.ongoing_log_interval_sec = 60.0
    diagnosis.update(error_config)
    logger_factory = AppLoggerFactory(
        to_console=False,
        to_file=str(log_path),
        level=DEBUG,
        compress=False,
    )
    diagnosis.log_register(logger_factory)
    logger_factory.update()
    now = iter((0.0, 1.0, 60.0, 61.0))
    monkeypatch.setattr(state_d_errors.time, "monotonic", lambda: next(now))

    try:
        raise RuntimeError("camera read failed")
    except RuntimeError as error:
        first_error = error
        diagnosis.log_output(
            ResultDiagnosis.DETECTION,
            ResultDiagnosis.DETECTION,
            ModuleErrorIndex.CAMERA_MODULE_ERROR,
            first_error,
            2,
        )
        diagnosis.log_output(
            ResultDiagnosis.DETECTION,
            ResultDiagnosis.DETECTION,
            ModuleErrorIndex.CAMERA_MODULE_ERROR,
            first_error,
            2,
        )
        diagnosis.log_output(
            ResultDiagnosis.DETECTION,
            ResultDiagnosis.DETECTION,
            ModuleErrorIndex.CAMERA_MODULE_ERROR,
            first_error,
            2,
        )
    try:
        raise ValueError("different failure")
    except ValueError as error:
        diagnosis.log_output(
            ResultDiagnosis.DETECTION,
            ResultDiagnosis.DETECTION,
            ModuleErrorIndex.CAMERA_MODULE_ERROR,
            error,
            2,
        )

    log_text = log_path.read_text(encoding="utf-8")
    assert log_text.count("カメラ2モジュールエラー") == 3
    assert log_text.count("Traceback (most recent call last):") == 2
    assert "NoneType: None" not in log_text


def test_lidar_module_error_throttles_through_vendor_log_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_path = tmp_path / "throttled-lidar-module-error.log"
    diagnosis = LidarModuleError()
    error_config = ErrorConfig()
    error_config.lidar_module_error.is_enabled = True
    error_config.lidar_module_error.ongoing_log_interval_sec = 60.0
    diagnosis.update(error_config)
    logger_factory = AppLoggerFactory(
        to_console=False,
        to_file=str(log_path),
        level=DEBUG,
        compress=False,
    )
    diagnosis.log_register(logger_factory)
    logger_factory.update()
    now = iter((0.0, 1.0, 60.0, 61.0))
    monkeypatch.setattr(state_d_errors.time, "monotonic", lambda: next(now))

    try:
        raise RuntimeError("LiDAR read failed")
    except RuntimeError as error:
        for _ in range(3):
            diagnosis.log_output(
                ResultDiagnosis.DETECTION,
                ResultDiagnosis.DETECTION,
                ModuleErrorIndex.LIDAR_MODULE_ERROR,
                error,
                1,
            )
    try:
        raise ValueError("different LiDAR failure")
    except ValueError as error:
        diagnosis.log_output(
            ResultDiagnosis.DETECTION,
            ResultDiagnosis.DETECTION,
            ModuleErrorIndex.LIDAR_MODULE_ERROR,
            error,
            1,
        )

    log_text = log_path.read_text(encoding="utf-8")
    assert log_text.count("LiDAR1モジュールエラー") == 3
    assert log_text.count("Traceback (most recent call last):") == 2
    assert "NoneType: None" not in log_text


def test_accumulation_module_error_throttles_through_vendor_log_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_path = tmp_path / "throttled-accumulation-module-error.log"
    diagnosis = AccumulationModuleError()
    error_config = ErrorConfig()
    error_config.storage_module_error.is_enabled = True
    error_config.storage_module_error.ongoing_log_interval_sec = 60.0
    diagnosis.update(error_config)
    logger_factory = AppLoggerFactory(
        to_console=False,
        to_file=str(log_path),
        level=DEBUG,
        compress=False,
    )
    diagnosis.log_register(logger_factory)
    logger_factory.update()
    now = iter((0.0, 1.0, 60.0, 61.0))
    monkeypatch.setattr(state_d_errors.time, "monotonic", lambda: next(now))

    try:
        raise RuntimeError("accumulation failed")
    except RuntimeError as error:
        for _ in range(3):
            diagnosis.log_output(
                ResultDiagnosis.DETECTION,
                ResultDiagnosis.DETECTION,
                ModuleErrorIndex.ACCUMULATION_MODULE_ERROR,
                error,
            )
    try:
        raise ValueError("different accumulation failure")
    except ValueError as error:
        diagnosis.log_output(
            ResultDiagnosis.DETECTION,
            ResultDiagnosis.DETECTION,
            ModuleErrorIndex.ACCUMULATION_MODULE_ERROR,
            error,
        )

    log_text = log_path.read_text(encoding="utf-8")
    assert log_text.count("蓄積モジュールエラー") == 3
    assert log_text.count("Traceback (most recent call last):") == 2
    assert "NoneType: None" not in log_text