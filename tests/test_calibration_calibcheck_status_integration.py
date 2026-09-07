# ruff: noqa: N802, SLF001

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import argus_synchro.calibration_mat_generator_modules.facade as facade_module
from argus_synchro.calibration_mat_generator_modules.ctrl.calibcheck2d3d import (
    calibcheck2d3d,
)
from argus_synchro.calibration_mat_generator_modules.facade import (
    CURRENTCAMERA_INIT,
    CalibrationCommonStatus,
    CalibrationUIGodot,
)
from argus_synchro.diagnosis.calibcheck2d3d_result_diagnosis import (
    CameraCalibCheckStatus,
    CameraCalibCheckStatusDiagnosis,
)


class _MonitorStub:
    def __init__(self) -> None:
        self.statuses: list[tuple[int, int]] = []

    def set_camera_calibcheck_status(
        self, camera_id: int, value: int | CameraCalibCheckStatus
    ) -> None:
        self.statuses.append((camera_id, int(value)))


class _WriterStub:
    def __init__(self) -> None:
        self.values: list[int] = []

    def WriteUInt8(self, value: int) -> None:
        self.values.append(value)


def test_score_results_are_converted_to_new_ui_statuses() -> None:
    controller = cast(calibcheck2d3d, object.__new__(calibcheck2d3d))
    controller._calibcheck_status_diagnosis = CameraCalibCheckStatusDiagnosis()
    monitor = _MonitorStub()

    controller.camera_evaluation_results_to_monitor(
        cast(CalibrationUIGodot, monitor),
        reason_camera_notvalid=[0, 0, 1],
        camera_evaluation_results=[True, False, False],
    )

    assert monitor.statuses == [(0, 0), (1, 2), (2, 3)]


def test_facade_setter_validates_and_stores_status() -> None:
    facade = cast(CalibrationUIGodot, object.__new__(CalibrationUIGodot))
    facade.output_log = False
    facade.camera_calibcheck_values = [0, 0, 0]

    facade.set_camera_calibcheck_status(
        1, CameraCalibCheckStatus.CALIBRATION_REQUIRED
    )

    assert facade.camera_calibcheck_values == [0, 2, 0]
    with pytest.raises(ValueError):
        facade.set_camera_calibcheck_status(1, CameraCalibCheckStatus.FORBIDDEN)


def test_facade_common_error_setter_normalizes_to_int() -> None:
    expected_error = 17
    facade = cast(CalibrationUIGodot, object.__new__(CalibrationUIGodot))
    facade.output_log = False

    facade.set_errors_calibcommon(cast(int, str(expected_error)))

    assert facade.errors_calibcommon == expected_error
    assert isinstance(facade.errors_calibcommon, int)


def test_facade_writer_transmits_writable_statuses_without_bit_conversion() -> None:
    facade = cast(CalibrationUIGodot, object.__new__(CalibrationUIGodot))
    facade.camera_num = 5
    writer = _WriterStub()
    facade.calibGodotInterfaceInst = writer

    facade._transmit_calibcheck_status([0, 2, 3, 4, 5])

    assert writer.values == [0, 2, 3, 4, 5]
    with pytest.raises(ValueError):
        facade._transmit_calibcheck_status([0, 1, 3, 4, 5])


def test_facade_initializes_calibcheck_status_as_insufficient_data() -> None:
    facade = cast(CalibrationUIGodot, object.__new__(CalibrationUIGodot))
    facade.output_log = False
    facade.camera_num = 3

    facade.initialize_internal_values(errorcode_pre=0)

    assert facade.status_calibcommon == int(CalibrationCommonStatus.INACTIVE)
    assert facade.currentcamera == CURRENTCAMERA_INIT
    assert facade.camera_calibcheck_values == [3, 3, 3]
    with pytest.raises(ValueError):
        facade.set_status_calibcommon(4)


def test_facade_dummydata_accepts_decimal_error_and_numeric_statuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected_error = 17
    expected_yaw = 12.5
    (tmp_path / "dummy_senddata.ini").write_text(
        """[DEFAULT]
errors_calibcommon = 17

[CalibCheckOverwrite]
values = [2,4,5]
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(facade_module.paths, "get_config_dir", lambda *_: tmp_path)
    monkeypatch.setattr(
        facade_module.paths,
        "normalize_path",
        lambda filename, directory: directory / filename,
    )
    logs: list[str] = []
    now = [100.0]
    monkeypatch.setattr(facade_module.time, "monotonic", lambda: now[0])
    facade = cast(CalibrationUIGodot, object.__new__(CalibrationUIGodot))
    facade._directory_config = object()
    facade._logger = SimpleNamespace(info=logs.append, warning=logs.append)
    facade.errorcode_pre = 0
    facade.errors_calibcommon = 0
    facade.yaw_value = expected_yaw
    facade.camera_calibcheck_values = [3, 3, 3]
    facade.camera_calibstatus_values = [0, 0, 0]

    facade.set_dummydata(
        enable_errorflag=True,
        enable_yawangle=True,
        overwrite_checkresult=True,
    )
    facade.set_dummydata(
        enable_errorflag=True,
        enable_yawangle=True,
        overwrite_checkresult=True,
    )

    assert facade.errors_calibcommon == expected_error
    assert facade.yaw_value == expected_yaw
    assert facade.camera_calibcheck_values == [2, 4, 5]
    assert len(logs) == 1
    assert logs[0].startswith("set_dummydata applied (alive):")
    assert "self.errors_calibcommon=17" in logs[0]

    now[0] += 5.0
    facade.set_dummydata(
        enable_errorflag=True,
        enable_yawangle=True,
        overwrite_checkresult=True,
    )

    assert len(logs) == 2
