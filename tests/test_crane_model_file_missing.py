import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from argus_synchro.diagnosis.action_errors import CraneModelFileMissingDiagnosis
from argus_synchro.process.points_refine_process import PointsRefineProcess
from argus_synchro.process.visual_process import VisualProcess
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
        json.JSONDecodeError("invalid json", "{", 1),
        ValueError("invalid value"),
        KeyError("required key"),
        RuntimeError("model loader failed"),
    ),
)
def test_crane_model_file_missing_counts_target_exceptions(error: Exception) -> None:
    diagnosis = CraneModelFileMissingDiagnosis()

    assert diagnosis.excepts_diagnosis(error) is True
    assert diagnosis.err_cnt.value == 1


def test_crane_model_file_missing_ignores_non_target_exception() -> None:
    diagnosis = CraneModelFileMissingDiagnosis()

    assert diagnosis.excepts_diagnosis(TypeError("unexpected")) is False
    assert diagnosis.err_cnt.value == 0


def test_crane_model_file_missing_owns_error_log_output() -> None:
    diagnosis = CraneModelFileMissingDiagnosis()
    diagnosis._logger = MagicMock()
    error = FileNotFoundError("machine.jsonc")

    diagnosis.log_output(
        True,
        False,
        ActionErrorIndex.CRANE_MODEL_FILE_MISSING,
        error,
    )

    diagnosis._logger.error.assert_called_once_with(
        "CE004: CRANE_MODEL_FILE_MISSING: FileNotFoundError('machine.jsonc')",
        exc_info=True,
    )


def test_points_refine_startup_remove_dispatches_and_reraises(monkeypatch) -> None:
    diagnosis = CraneModelFileMissingDiagnosis()
    diagnosis._logger = MagicMock()
    process = object.__new__(PointsRefineProcess)
    process._ProcessBase__process = None
    process._ser = SimpleNamespace(
        action_errors_A_C={ActionErrorIndex.CRANE_MODEL_FILE_MISSING: diagnosis}
    )
    process._app_config = SimpleNamespace(
        OctoTree=SimpleNamespace(
            col_machine_dir="machine",
            json_col_machine_file="model.jsonc",
        ),
        LiDARPosition=object(),
    )
    error = FileNotFoundError("model.jsonc")
    monkeypatch.setattr(
        "argus_synchro.process.points_refine_process.SubScrutinizer.create_machine_points",
        MagicMock(side_effect=error),
    )

    with pytest.raises(FileNotFoundError, match="model.jsonc"):
        process._create_machine_points()

    assert diagnosis.err_cnt.value == 1
    diagnosis._logger.error.assert_called_once_with(
        "CE004: CRANE_MODEL_FILE_MISSING: FileNotFoundError('model.jsonc')",
        exc_info=True,
    )


def test_visual_machine_load_dispatches_and_reraises(monkeypatch) -> None:
    diagnosis = CraneModelFileMissingDiagnosis()
    diagnosis._logger = MagicMock()
    process = object.__new__(VisualProcess)
    process._ProcessBase__process = None
    process._ser = SimpleNamespace(
        action_errors_A_C={ActionErrorIndex.CRANE_MODEL_FILE_MISSING: diagnosis}
    )
    process._app_config = SimpleNamespace(
        OctoTree=SimpleNamespace(
            col_machine_dir="machine",
            json_col_machine_file="model.jsonc",
        ),
        LiDARPosition=object(),
    )
    error = json.JSONDecodeError("invalid model", "{", 1)
    monkeypatch.setattr(
        "argus_synchro.process.visual_process.SubScrutinizer.create_machine_points",
        MagicMock(side_effect=error),
    )

    with pytest.raises(json.JSONDecodeError, match="invalid model"):
        process._create_machine_points()

    assert diagnosis.err_cnt.value == 1
    diagnosis._logger.error.assert_called_once_with(
        "CE004: CRANE_MODEL_FILE_MISSING: "
        "JSONDecodeError('invalid model: line 1 column 2 (char 1)')",
        exc_info=True,
    )