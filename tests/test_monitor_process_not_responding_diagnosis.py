from __future__ import annotations

import argus_synchro.diagnosis.error_config as ErrConf
from argus_synchro.diagnosis.state_errors import MonitorProcessNotRespondingDiagnosis


def _create_diagnosis(
    *,
    error_threshold_sec: float = 5.0,
    recovery_receive_interval_sec: float = 1.0,
) -> MonitorProcessNotRespondingDiagnosis:
    diagnosis = MonitorProcessNotRespondingDiagnosis()
    err_conf = ErrConf.ErrorConfig().load_from_dict(
        {
            "monitor_process_not_responding": {
                "is_enabled": True,
                "error_threshold_sec": error_threshold_sec,
                "error_recovery_confirm_duration_sec": 5.0,
                "failsafe_recovery_confirm_duration_sec": 5.0,
                "recovery_receive_interval_sec": recovery_receive_interval_sec,
            }
        }
    )
    diagnosis.update(err_conf)
    return diagnosis


def test_errors_diagnosis_detects_error_when_none_continues_from_initial() -> None:
    diagnosis = _create_diagnosis(error_threshold_sec=5.0)

    assert diagnosis.errors_diagnosis(10.0, None) == (False, False, False)
    assert diagnosis.errors_diagnosis(14.9, None) == (False, False, False)
    assert diagnosis.errors_diagnosis(15.0, None) == (True, False, False)


def test_errors_diagnosis_detects_error_when_same_heartbeat_continues() -> None:
    diagnosis = _create_diagnosis(error_threshold_sec=5.0)

    assert diagnosis.errors_diagnosis(1.0, 1000.0) == (False, False, False)
    assert diagnosis.errors_diagnosis(2.0, 1000.0) == (False, False, False)
    assert diagnosis.errors_diagnosis(6.9, 1000.0) == (False, False, False)
    assert diagnosis.errors_diagnosis(7.0, 1000.0) == (True, False, False)


def test_errors_diagnosis_detects_error_when_heartbeat_gap_is_5sec_or_more() -> None:
    diagnosis = _create_diagnosis(error_threshold_sec=5.0)

    assert diagnosis.errors_diagnosis(1.0, 1000.0) == (False, False, False)
    assert diagnosis.errors_diagnosis(2.0, 1006.0) == (True, False, False)


def test_errors_diagnosis_resets_stale_timer_when_heartbeat_updates() -> None:
    diagnosis = _create_diagnosis(error_threshold_sec=5.0)

    assert diagnosis.errors_diagnosis(1.0, 2000.0) == (False, False, False)
    assert diagnosis.errors_diagnosis(2.0, 2000.0) == (False, False, False)
    # ハートビート更新で未更新継続判定をリセットする。
    assert diagnosis.errors_diagnosis(3.0, 2001.0) == (False, False, False)
    assert diagnosis.errors_diagnosis(7.9, 2001.0) == (False, False, False)
    assert diagnosis.errors_diagnosis(12.8, 2001.0) == (False, False, False)
    assert diagnosis.errors_diagnosis(12.9, 2001.0) == (True, False, False)


def test_errors_diagnosis_handles_unsynchronized_clocks_with_none_staleness() -> None:
    diagnosis = _create_diagnosis(error_threshold_sec=5.0)

    # nowとlast_heartbeatは別プロセスで更新されるため、絶対値比較ではなく
    # 「前回値から更新されたか」を使って判定できることを確認する。
    assert diagnosis.errors_diagnosis(10.0, 1000.0) == (False, False, False)
    assert diagnosis.errors_diagnosis(11.0, 1000.0) == (False, False, False)
    assert diagnosis.errors_diagnosis(13.0, 1000.0) == (False, False, False)
    assert diagnosis.errors_diagnosis(16.0, 1000.0) == (True, False, False)


def test_errors_diagnosis_error_recovery_and_reerror() -> None:
    diagnosis = _create_diagnosis(error_threshold_sec=5.0)

    # 同一heartbeatが継続してエラー発生。
    assert diagnosis.errors_diagnosis(1.0, 1000.0) == (False, False, False)
    assert diagnosis.errors_diagnosis(2.0, 1000.0) == (False, False, False)
    assert diagnosis.errors_diagnosis(7.0, 1000.0) == (True, False, False)

    # heartbeat更新を継続し、エラー復帰とフェールセーフ復帰が同時に成立する。
    # 併せて、detect_error と detect_recovery_error は同時にTrueにならないこと、
    # detect_recovery_error と detect_recovery_fail_safe は同じ仕様で動くことを検証する。
    recovery_phase = [
        (8.0, 1000.5),
        (9.0, 1001.0),
        (10.0, 1002.0),
        (11.0, 1003.0),
        (12.0, 1004.0),
        (13.0, 1005.0),
        (14.0, 1006.0),
    ]
    recovery_results: list[tuple[bool, bool, bool]] = []
    for now, hb in recovery_phase:
        err, fail_safe_recover, error_recover = diagnosis.errors_diagnosis(now, hb)
        recovery_results.append((err, fail_safe_recover, error_recover))
        assert not (err and error_recover)
        assert fail_safe_recover == error_recover

    # 復帰成立点では (False, True, True) になる。
    assert (False, True, True) in recovery_results

    # 復帰後に再びheartbeat未更新が継続すると、再度エラーになる。
    assert diagnosis.errors_diagnosis(15.0, 1006.0) == (False, False, False)
    assert diagnosis.errors_diagnosis(19.0, 1006.0) == (False, False, False)
    assert diagnosis.errors_diagnosis(20.0, 1006.0) == (True, False, False)
