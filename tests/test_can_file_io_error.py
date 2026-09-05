# pyright: reportAttributeAccessIssue=false

from types import SimpleNamespace

import pytest

from argus_synchro.device.can import can_receiver
from argus_synchro.diagnosis.error_diagnosis import ResultDiagnosis
from argus_synchro.process import can_process
from argus_synchro.process.can_process import CanDataProviderProcess
from argus_synchro.provider import can_data
from argus_synchro.shared_errors import ActionErrorIndex, StateErrorDIndex


class _FailingCanFile:
    def __init__(self, *args: object, **kwargs: object) -> None:
        raise OSError("CAN input CSV open failed")


class _SuccessfulCanFile:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass


class _FailingCanMapFile:
    def __init__(self, *args: object, **kwargs: object) -> None:
        raise can_receiver.CanIdMapError(
            "config/can_id_map.csv",
            FileNotFoundError("map missing"),
        )


class _FailingProvider:
    def change_file_name_index(self, file_path: str, index: int) -> None:
        raise ValueError("CAN input CSV parse failed")


class _SuccessfulProvider:
    def change_file_name_index(self, file_path: str, index: int) -> None:
        pass


class _RecordingDiagnosis:
    def __init__(self) -> None:
        self.diagnosis_calls: list[tuple[object, ...]] = []
        self.log_calls: list[tuple[object, ...]] = []

    def errors_diagnosis(
        self, *args: object
    ) -> tuple[ResultDiagnosis, ResultDiagnosis]:
        self.diagnosis_calls.append(args)
        return ResultDiagnosis.DETECTION, ResultDiagnosis.NORMAL

    def log_output(self, *args: object) -> None:
        self.log_calls.append(args)

    def excepts_diagnosis(self, error: Exception) -> bool:
        self.diagnosis_calls.append((error,))
        return True


def _process() -> tuple[CanDataProviderProcess, _RecordingDiagnosis]:
    diagnosis = _RecordingDiagnosis()
    state_errors_d: list[object | None] = [None] * (
        StateErrorDIndex.FILE_IO_ERROR + 1
    )
    state_errors_d[StateErrorDIndex.FILE_IO_ERROR] = diagnosis

    process = object.__new__(CanDataProviderProcess)
    process._app_config = SimpleNamespace(
        DEFAULT=SimpleNamespace(File_Input=True, use_shi_lib=False),
        UI_IF=SimpleNamespace(crane_model="SCX900-3"),
        CAN=SimpleNamespace(
            c_file="can_input.csv",
            can_id_map_file="config/can_id_map.csv",
        ),
        Scrutinizer=SimpleNamespace(s_frame=0),
    )
    process._ser = SimpleNamespace(
        action_errors_A_C={
            ActionErrorIndex.CONFIG_FILE_MISSING: _RecordingDiagnosis()
        },
        state_errors_D=state_errors_d,
    )
    process._app_logger_factory = SimpleNamespace()
    return process, diagnosis


def test_file_input_init_error_is_diagnosed_and_reraised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(can_receiver, "CanFile", _FailingCanFile)
    process, diagnosis = _process()

    with pytest.raises(OSError, match="CAN input CSV open failed"):
        process._change_device()

    assert diagnosis.diagnosis_calls == [(True,)]
    assert diagnosis.log_calls == [
        (
            ResultDiagnosis.DETECTION,
            ResultDiagnosis.NORMAL,
            StateErrorDIndex.FILE_IO_ERROR,
            "can_input.csv",
            "read file-input CAN CSV",
            "OSError: CAN input CSV open failed",
        )
    ]


def test_successful_file_input_init_updates_recovery_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(can_receiver, "CanFile", _SuccessfulCanFile)
    monkeypatch.setattr(
        can_data,
        "CanFileProvider",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    process, diagnosis = _process()

    process._change_device()

    assert diagnosis.diagnosis_calls == [(False,)]
    assert diagnosis.log_calls == []


def test_can_id_map_error_records_map_path_as_ce005(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(can_receiver, "CanFile", _FailingCanMapFile)
    process, file_io_diagnosis = _process()
    config_diagnosis = process._ser.action_errors_A_C[
        ActionErrorIndex.CONFIG_FILE_MISSING
    ]

    with pytest.raises(
        can_receiver.CanIdMapError,
        match=r"path=config/can_id_map\.csv",
    ):
        process._change_device()

    diagnosed_error = config_diagnosis.diagnosis_calls[0][0]
    assert isinstance(diagnosed_error, can_receiver.CanIdMapError)
    assert diagnosed_error.file_path == "config/can_id_map.csv"
    assert config_diagnosis.log_calls[0][0:3] == (
        True,
        False,
        ActionErrorIndex.CONFIG_FILE_MISSING,
    )
    assert config_diagnosis.log_calls[0][3] is diagnosed_error
    assert file_io_diagnosis.diagnosis_calls == []
    assert file_io_diagnosis.log_calls == []


def test_file_input_reload_error_is_diagnosed_and_reraised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(can_process, "CanFileProvider", _FailingProvider)
    process, diagnosis = _process()
    process._provider = _FailingProvider()

    with pytest.raises(ValueError, match="CAN input CSV parse failed"):
        process._change_file_input_file("next_can.csv", 10)

    assert diagnosis.diagnosis_calls == [(True,)]
    assert diagnosis.log_calls == [
        (
            ResultDiagnosis.DETECTION,
            ResultDiagnosis.NORMAL,
            StateErrorDIndex.FILE_IO_ERROR,
            "next_can.csv",
            "read file-input CAN CSV",
            "ValueError: CAN input CSV parse failed",
        )
    ]


def test_successful_file_input_reload_updates_recovery_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(can_process, "CanFileProvider", _SuccessfulProvider)
    process, diagnosis = _process()
    process._provider = _SuccessfulProvider()

    process._change_file_input_file("next_can.csv", 10)

    assert diagnosis.diagnosis_calls == [(False,)]
    assert diagnosis.log_calls == []