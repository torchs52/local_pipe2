from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from argus_synchro import __main__ as app_main
from argus_synchro.core.closable import CompositeClosable


@pytest.mark.parametrize(
    ("file_input", "mode", "expected"),
    (
        (True, "CALIB", True),
        (False, "CALIB", False),
        (True, "SCRUT", False),
        (False, "SCRUT", False),
    ),
)
def test_automated_calibration_run_requires_calib_file_input(
    file_input: bool, mode: str, expected: bool
) -> None:
    app_config = SimpleNamespace(DEFAULT=SimpleNamespace(File_Input=file_input))

    assert app_main.is_automated_calibration_run(app_config, mode) is expected


def test_automated_calibration_stop_only_disables_and_closes() -> None:
    closables = MagicMock()
    current_activator = MagicMock()
    new_activator = MagicMock()

    with patch.object(
        app_main, "ProcessActivator", return_value=new_activator
    ) as activator_factory:
        new_closables, returned_activator = (
            app_main.stop_automated_calibration_pipeline(
                closables, current_activator
            )
        )

    current_activator.disable.assert_called_once_with()
    closables.close.assert_called_once_with()
    activator_factory.assert_called_once_with()
    new_activator.disable.assert_called_once_with()
    assert isinstance(new_closables, CompositeClosable)
    assert returned_activator is new_activator