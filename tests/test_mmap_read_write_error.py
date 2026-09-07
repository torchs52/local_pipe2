from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from argus_synchro.__main__ import _write_status_safe
from argus_synchro.diagnosis.action_errors import MmapReadWriteErrorDiagnosis
from argus_synchro.process.error_monitor_process import ErrorMonitorProcess
from argus_synchro.process.visual_process import VisualProcess
from argus_synchro.shared_errors import ActionErrorIndex
from argus_synchro.SystemMonitor.status_mmap import StatusCode


@pytest.mark.parametrize(
    "error",
    (
        OSError("disk failure"),
        ValueError("closed mmap"),
        BufferError("exported buffer"),
        RuntimeError("writer failure"),
    ),
)
def test_mmap_read_write_error_counts_target_exceptions(error: Exception) -> None:
    diagnosis = MmapReadWriteErrorDiagnosis()

    assert diagnosis.excepts_diagnosis(error) is True
    assert diagnosis.err_cnt.value == 1


def test_mmap_read_write_error_ignores_non_target_exception() -> None:
    diagnosis = MmapReadWriteErrorDiagnosis()

    assert diagnosis.excepts_diagnosis(TypeError("unexpected")) is False
    assert diagnosis.err_cnt.value == 0


def test_mmap_read_write_error_owns_error_log_output() -> None:
    diagnosis = MmapReadWriteErrorDiagnosis()
    diagnosis._logger = MagicMock()
    error = ValueError("closed mmap")

    diagnosis.log_output(
        True,
        False,
        ActionErrorIndex.MMAP_READ_WRITE_ERROR,
        "status.mmap write failed",
        error,
    )

    diagnosis._logger.error.assert_called_once_with(
        "CE011: MMAP_READ_WRITE_ERROR: status.mmap write failed: "
        "ValueError('closed mmap')",
        exc_info=True,
    )


def test_error_monitor_dispatches_mmap_failure_and_continues() -> None:
    diagnosis = MmapReadWriteErrorDiagnosis()
    diagnosis._logger = MagicMock()
    process = object.__new__(ErrorMonitorProcess)
    process._is_last_app_manager_diag_enabled = False
    process._ser = SimpleNamespace(
        AppMan_ex=SimpleNamespace(
            is_heartbeat_enabled=SimpleNamespace(value=False)
        ),
        action_errors_A_C={ActionErrorIndex.MMAP_READ_WRITE_ERROR: diagnosis},
        state_errors=(),
        action_errors=(),
    )
    process._mmap = MagicMock()
    process._mmap.start_write.side_effect = BufferError("busy mmap")

    process._update()

    assert diagnosis.err_cnt.value == 1
    diagnosis._logger.error.assert_called_once_with(
        "CE011: MMAP_READ_WRITE_ERROR: ErrorMMapWriter transaction failed: "
        "BufferError('busy mmap')",
        exc_info=True,
    )


def test_visual_ui_dispatches_mmap_failure_and_reraises(monkeypatch) -> None:
    diagnosis = MmapReadWriteErrorDiagnosis()
    diagnosis._logger = MagicMock()
    process = object.__new__(VisualProcess)
    process._ProcessBase__process = None
    process._ser = SimpleNamespace(
        action_errors_A_C={ActionErrorIndex.MMAP_READ_WRITE_ERROR: diagnosis}
    )
    process._app_config = SimpleNamespace(
        Scrutinizer=SimpleNamespace(s_frame=0),
        General=SimpleNamespace(
            rotation_radius=1.0,
            has_external_guard=False,
            external_guard_offset=0.0,
        ),
        camera=SimpleNamespace(count=1),
    )
    process._directory_config = MagicMock()
    process._logger = MagicMock()
    error = OSError("status mmap unavailable")
    monkeypatch.setattr(
        "argus_synchro.process.visual_process.GodotUIVisualizer",
        MagicMock(side_effect=error),
    )

    with pytest.raises(OSError, match="status mmap unavailable"):
        process._create_visual_ui(MagicMock())

    assert diagnosis.err_cnt.value == 1
    diagnosis._logger.error.assert_called_once_with(
        "CE011: MMAP_READ_WRITE_ERROR: Godot UI MMAP initialization failed: "
        "OSError('status mmap unavailable')",
        exc_info=True,
    )


def test_main_status_write_dispatches_mmap_failure_and_continues() -> None:
    diagnosis = MmapReadWriteErrorDiagnosis()
    diagnosis._logger = MagicMock()
    status = MagicMock()
    status.write_status.side_effect = RuntimeError("status writer failed")
    ser = SimpleNamespace(
        action_errors_A_C={ActionErrorIndex.MMAP_READ_WRITE_ERROR: diagnosis}
    )

    _write_status_safe(status, StatusCode.REBOOT, ser)

    assert diagnosis.err_cnt.value == 1
    diagnosis._logger.error.assert_called_once_with(
        "CE011: MMAP_READ_WRITE_ERROR: status.mmap write failed (REBOOT): "
        "RuntimeError('status writer failed')",
        exc_info=True,
    )