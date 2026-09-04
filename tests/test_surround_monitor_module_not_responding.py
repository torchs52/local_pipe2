from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from argus_synchro.diagnosis.error_diagnosis import ResultDiagnosis
from argus_synchro.diagnosis.state_errors import (
    SurroundMonitorModuleNotRespondingDiagnosis,
)
from argus_synchro.process.app_manager_process import AppManagerProcess
from argus_synchro.shared_excepts import INVALID_TIMESTAMP, SharedExcepts
from argus_synchro.shared_errors import StateErrorIndex


def _make_diagnosis() -> SurroundMonitorModuleNotRespondingDiagnosis:
    diagnosis = SurroundMonitorModuleNotRespondingDiagnosis()
    diagnosis.is_enabled = True
    diagnosis.param = SimpleNamespace(error_threshold_sec=5.0)
    return diagnosis


def test_surround_monitor_module_detects_any_elapsed_over_threshold() -> None:
    diagnosis = _make_diagnosis()

    assert diagnosis.errors_diagnosis([1.0, 5.0, -1.0, 5.1]) == (
        ResultDiagnosis.DETECTION,
        ResultDiagnosis.DETECTION,
    )
    assert diagnosis._last_max_elapsed_sec == 5.1


def test_surround_monitor_module_ignores_inactive_heartbeats() -> None:
    diagnosis = _make_diagnosis()

    assert diagnosis.errors_diagnosis([-1.0, -1.0]) == (
        ResultDiagnosis.NORMAL,
        ResultDiagnosis.NORMAL,
    )


def test_surround_monitor_module_recovers_when_all_active_modules_respond() -> None:
    diagnosis = _make_diagnosis()
    diagnosis.errors_diagnosis([6.0, 1.0])

    assert diagnosis.errors_diagnosis([0.1, 0.2]) == (
        ResultDiagnosis.RECOVERY,
        ResultDiagnosis.RECOVERY,
    )


@pytest.mark.parametrize("elapsed_list", ([], [1], ["1.0"]))
def test_surround_monitor_module_rejects_invalid_elapsed_list(elapsed_list) -> None:
    diagnosis = _make_diagnosis()

    with pytest.raises(ValueError):
        diagnosis.errors_diagnosis(elapsed_list)


def test_surround_monitor_module_owns_logs() -> None:
    diagnosis = _make_diagnosis()
    diagnosis._logger = MagicMock()
    diagnosis.errors_diagnosis([6.25])

    diagnosis.log_output(
        ResultDiagnosis.DETECTION,
        ResultDiagnosis.DETECTION,
        StateErrorIndex.SURROUND_MONITOR_MODULE_NOT_RESPONDING,
    )

    diagnosis._logger.error.assert_called_once_with(
        "SE037: SURROUND_MONITOR_MODULE_NOT_RESPONDING detected: "
        "max_elapsed=%.3f sec",
        6.25,
    )


def test_surround_monitor_processes_have_independent_heartbeats(app_config) -> None:
    shared = SharedExcepts(app_config)

    assert shared.ObjDet_ex is not shared.Scruti_ex
    assert shared.PointsRefine_ex is not shared.Scruti_ex
    assert shared.ObjDet_ex is not shared.PointsRefine_ex
    assert shared.getData_ex.last_heartbeat.value == INVALID_TIMESTAMP
    assert shared.ObjDet_ex.last_heartbeat.value == INVALID_TIMESTAMP
    assert shared.PointsRefine_ex.last_heartbeat.value == INVALID_TIMESTAMP
    assert shared.Visu_ex.last_heartbeat.value == INVALID_TIMESTAMP


def test_app_manager_dispatches_surround_monitor_elapsed(monkeypatch) -> None:
    diagnosis = MagicMock()
    diagnosis.errors_diagnosis.return_value = (
        ResultDiagnosis.DETECTION,
        ResultDiagnosis.DETECTION,
    )
    process = object.__new__(AppManagerProcess)
    process._sec = SimpleNamespace(
        getData_ex=SimpleNamespace(last_heartbeat=SimpleNamespace(value=8.0)),
        ObjDet_ex=SimpleNamespace(last_heartbeat=SimpleNamespace(value=9.0)),
        PointsRefine_ex=SimpleNamespace(
            last_heartbeat=SimpleNamespace(value=INVALID_TIMESTAMP)
        ),
        Visu_ex=SimpleNamespace(last_heartbeat=SimpleNamespace(value=7.0)),
    )
    process._ser = SimpleNamespace(
        state_errors_A_C={
            StateErrorIndex.SURROUND_MONITOR_MODULE_NOT_RESPONDING: diagnosis
        }
    )
    monkeypatch.setattr(
        "argus_synchro.process.app_manager_process.time.monotonic", lambda: 10.0
    )

    process._surround_monitor_modules_healthy_check()

    diagnosis.errors_diagnosis.assert_called_once_with([2.0, 1.0, -1.0, 3.0])
    diagnosis.log_output.assert_called_once_with(
        ResultDiagnosis.DETECTION,
        ResultDiagnosis.DETECTION,
        StateErrorIndex.SURROUND_MONITOR_MODULE_NOT_RESPONDING,
    )