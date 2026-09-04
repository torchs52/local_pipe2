from configparser import (
    DuplicateOptionError,
    DuplicateSectionError,
    MissingSectionHeaderError,
    NoOptionError,
    NoSectionError,
    ParsingError,
)
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from argus_synchro import __main__ as app_main
from argus_synchro.diagnosis.action_errors import (
    ConfigFileMissingDiagnosis,
    SensorCalibDataInvalidDiagnosis,
)
from argus_synchro.diagnosis.error_config import ErrorConfig
from argus_synchro.shared_errors import ActionErrorIndex


@pytest.mark.parametrize(
    "error",
    (
        FileNotFoundError("missing"),
        PermissionError("denied"),
        IsADirectoryError("directory"),
        NotADirectoryError("not a directory"),
        OSError("io"),
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid"),
        UnicodeEncodeError("ascii", "\N{HIRAGANA LETTER A}", 0, 1, "invalid"),
        NoOptionError("option", "section"),
        NoSectionError("section"),
        MissingSectionHeaderError("config.ini", 1, "invalid"),
        ParsingError("config.ini"),
        DuplicateOptionError("section", "option", "config.ini", 2),
        DuplicateSectionError("section", "config.ini", 2),
        ValueError("invalid integer"),
    ),
)
def test_config_file_missing_counts_target_exceptions(error: Exception) -> None:
    diagnosis = ConfigFileMissingDiagnosis()

    assert diagnosis.excepts_diagnosis(error) is True
    assert diagnosis.err_cnt.value == 1


def test_config_file_missing_ignores_non_target_exception() -> None:
    diagnosis = ConfigFileMissingDiagnosis()

    assert diagnosis.excepts_diagnosis(TypeError("unexpected")) is False
    assert diagnosis.err_cnt.value == 0


def test_config_file_missing_accepts_empty_target_exception_message() -> None:
    diagnosis = ConfigFileMissingDiagnosis()
    diagnosis._logger = MagicMock()
    error = ValueError()

    assert diagnosis.excepts_diagnosis(error) is True
    diagnosis.log_output(True, False, ActionErrorIndex.CONFIG_FILE_MISSING, error)

    assert diagnosis.err_cnt.value == 1
    diagnosis._logger.error.assert_called_once_with(
        "CE005: CONFIG_FILE_MISSING: ValueError: ",
        exc_info=True,
    )


def test_config_file_missing_throttles_same_exception_signature(monkeypatch) -> None:
    diagnosis = ConfigFileMissingDiagnosis()
    monotonic_values = iter((10.0, 10.5, 11.0))
    monkeypatch.setattr(
        "argus_synchro.diagnosis.action_errors.time.monotonic",
        lambda: next(monotonic_values),
    )

    assert diagnosis.excepts_diagnosis(FileNotFoundError("missing")) is True
    assert diagnosis.excepts_diagnosis(FileNotFoundError("missing")) is True
    assert diagnosis.err_cnt.value == 1

    assert diagnosis.excepts_diagnosis(FileNotFoundError("missing")) is True
    assert diagnosis.err_cnt.value == 2


def test_config_file_missing_counts_changed_signature_within_throttle(monkeypatch) -> None:
    diagnosis = ConfigFileMissingDiagnosis()
    monotonic_values = iter((10.0, 10.1))
    monkeypatch.setattr(
        "argus_synchro.diagnosis.action_errors.time.monotonic",
        lambda: next(monotonic_values),
    )

    assert diagnosis.excepts_diagnosis(FileNotFoundError("first")) is True
    assert diagnosis.excepts_diagnosis(FileNotFoundError("second")) is True
    assert diagnosis.err_cnt.value == 2


def test_config_file_missing_owns_error_log_output() -> None:
    diagnosis = ConfigFileMissingDiagnosis()
    diagnosis._logger = MagicMock()
    error = FileNotFoundError("settings.ini")

    diagnosis.log_output(True, False, ActionErrorIndex.CONFIG_FILE_MISSING, error)

    diagnosis._logger.error.assert_called_once_with(
        "CE005: CONFIG_FILE_MISSING: FileNotFoundError: settings.ini",
        exc_info=True,
    )


def test_load_config_dispatches_target_exception_to_diagnosis(monkeypatch) -> None:
    diagnosis = ConfigFileMissingDiagnosis()
    diagnosis._logger = MagicMock()
    sensor_calib_diagnosis = SensorCalibDataInvalidDiagnosis()
    main_logger = MagicMock()
    app_manager_ex = object()
    shared_errors = SimpleNamespace(
        action_errors_A_C={
            ActionErrorIndex.CONFIG_FILE_MISSING: diagnosis,
            ActionErrorIndex.SENSOR_CALIB_DATA_INVALID: sensor_calib_diagnosis,
        },
        AppMan_ex=app_manager_ex,
        shared_err_conf=SimpleNamespace(read=ErrorConfig),
    )
    app_config = SimpleNamespace(
        calibration=SimpleNamespace(BothLidars="", Lidar_calib_files=[])
    )
    shared_app_config = MagicMock()
    shared_app_config.read.return_value = app_config
    shared_excepts = object()
    shared_calibration = object()
    profile_handler = MagicMock()
    profile_handler.apply_model_specific_config.side_effect = (
        FileNotFoundError("settings.ini"),
        None,
    )

    monkeypatch.setattr(
        app_main.machine_profile,
        "MachineProfileHandler",
        MagicMock(return_value=profile_handler),
    )
    monkeypatch.setattr(
        app_main, "SharedAppConfig", MagicMock(return_value=shared_app_config)
    )
    shared_excepts_factory = MagicMock(return_value=shared_excepts)
    monkeypatch.setattr(app_main, "SharedExcepts", shared_excepts_factory)
    monkeypatch.setattr(
        app_main,
        "SharedAppConfigCalibration",
        MagicMock(return_value=shared_calibration),
    )
    monkeypatch.setattr(app_main.paths, "normalize_path", lambda *args: Path("x"))

    result = app_main.load_config(
        shared_errors,
        main_logger,
        SimpleNamespace(config_dir=Path("config")),
    )

    assert result == (
        shared_app_config,
        shared_excepts,
        app_config,
        shared_calibration,
    )
    assert diagnosis.err_cnt.value == 1
    diagnosis._logger.error.assert_called_once_with(
        "CE005: CONFIG_FILE_MISSING: FileNotFoundError: settings.ini",
        exc_info=True,
    )
    main_logger.error.assert_not_called()
    shared_excepts_factory.assert_called_once_with(
        app_config=app_config,
        app_manager_ex=app_manager_ex,
    )


def test_load_config_reports_ce006_without_ce005_retry(
    monkeypatch, tmp_path: Path
) -> None:
    config_diagnosis = ConfigFileMissingDiagnosis()
    sensor_calib_diagnosis = SensorCalibDataInvalidDiagnosis()
    sensor_calib_diagnosis._logger = MagicMock()
    shared_errors = SimpleNamespace(
        action_errors_A_C={
            ActionErrorIndex.CONFIG_FILE_MISSING: config_diagnosis,
            ActionErrorIndex.SENSOR_CALIB_DATA_INVALID: sensor_calib_diagnosis,
        },
        AppMan_ex=object(),
        shared_err_conf=SimpleNamespace(read=ErrorConfig),
    )
    app_config = SimpleNamespace(
        calibration=SimpleNamespace(
            BothLidars=str(tmp_path / "missing_both.csv"),
            Lidar_calib_files=[str(tmp_path / "missing_lidar0.csv")],
        )
    )
    shared_app_config = MagicMock()
    shared_app_config.read.return_value = app_config
    shared_excepts = object()
    shared_calibration = object()
    profile_handler = MagicMock()

    monkeypatch.setattr(
        app_main.machine_profile,
        "MachineProfileHandler",
        MagicMock(return_value=profile_handler),
    )
    monkeypatch.setattr(
        app_main, "SharedAppConfig", MagicMock(return_value=shared_app_config)
    )
    monkeypatch.setattr(
        app_main, "SharedExcepts", MagicMock(return_value=shared_excepts)
    )
    monkeypatch.setattr(
        app_main,
        "SharedAppConfigCalibration",
        MagicMock(return_value=shared_calibration),
    )
    monkeypatch.setattr(app_main.paths, "normalize_path", lambda *args: Path("x"))

    result = app_main.load_config(
        shared_errors,
        MagicMock(),
        SimpleNamespace(config_dir=Path("config")),
    )

    assert result == (
        shared_app_config,
        shared_excepts,
        app_config,
        shared_calibration,
    )
    assert sensor_calib_diagnosis.err_cnt.value == 1
    assert config_diagnosis.err_cnt.value == 0
    sensor_calib_diagnosis._logger.error.assert_called_once()
    profile_handler.apply_model_specific_config.assert_called_once()