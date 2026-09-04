from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from argus_synchro.file_watch import DebouncedEventHandler
from argus_synchro.shared_errors import ActionErrorIndex


def _event_handler(write_side_effect: object) -> tuple[
    DebouncedEventHandler, MagicMock, MagicMock, MagicMock
]:
    shared_app_config = MagicMock()
    shared_app_config.write.side_effect = write_side_effect
    diagnosis = MagicMock()
    shared_errors = SimpleNamespace(
        action_errors_A_C={ActionErrorIndex.CONFIG_FILE_MISSING: diagnosis}
    )
    logger = MagicMock()
    handler = DebouncedEventHandler(
        sac=shared_app_config,
        sec=MagicMock(),
        ser=shared_errors,
        logger=logger,
    )
    return handler, shared_app_config, diagnosis, logger


def test_reload_retry_absorbs_transient_atomic_save_failure() -> None:
    handler, shared_app_config, diagnosis, logger = _event_handler(
        [FileNotFoundError("settings.ini"), OSError("writing"), None]
    )
    path = "config/settings.ini"
    handler.events[path] = MagicMock()

    with patch("argus_synchro.file_watch.time.sleep") as sleep:
        handler.process_event(path)

    assert shared_app_config.write.call_count == 3
    assert sleep.call_args_list == [call(0.2), call(0.2)]
    diagnosis.excepts_diagnosis.assert_not_called()
    logger.error.assert_not_called()
    assert path not in handler.events


def test_reload_retry_reports_ce005_after_all_attempts_fail() -> None:
    handler, shared_app_config, diagnosis, logger = _event_handler(
        FileNotFoundError("settings.ini")
    )
    diagnosis.excepts_diagnosis.return_value = True

    with patch("argus_synchro.file_watch.time.sleep") as sleep:
        handler.process_event("config/settings.ini")

    assert shared_app_config.write.call_count == 3
    assert sleep.call_args_list == [call(0.2), call(0.2)]
    diagnosis.excepts_diagnosis.assert_called_once()
    logger.error.assert_called_once()
    assert logger.error.call_args.args[0].startswith("file open error:")