from dataclasses import dataclass
from pathlib import Path

import numpy as np

from argus_synchro.config.app_config import CalibrationConf
from argus_synchro.diagnosis.error_config import SensorCalibDataInvalidParameters


@dataclass(frozen=True, slots=True)
class LidarCalibValidationIssue:
    matrix_kind: str
    matrix_path: str
    detail: str


class LidarCalibValidator:
    def __init__(self, param: SensorCalibDataInvalidParameters) -> None:
        self._param = param

    def validate(
        self, calibration_conf: CalibrationConf
    ) -> tuple[LidarCalibValidationIssue, ...]:
        targets: list[tuple[str, str]] = []
        if self._param.check_lidar2lidar:
            targets.append(("lidar2lidar", calibration_conf.BothLidars))
        if self._param.check_lidar2crane:
            targets.extend(
                ("lidar2crane", path)
                for path in calibration_conf.Lidar_calib_files
            )

        issues: list[LidarCalibValidationIssue] = []
        for matrix_kind, matrix_path in targets:
            path = Path(matrix_path)
            try:
                matrix = np.loadtxt(path, delimiter=",", dtype=np.float64)
            except (OSError, UnicodeError, ValueError) as error:
                issues.append(
                    LidarCalibValidationIssue(
                        matrix_kind,
                        str(path),
                        f"failed to load CSV: {type(error).__name__}: {error}",
                    )
                )
                continue

            if self._param.enforce_shape_4x4 and matrix.shape != (4, 4):
                issues.append(
                    LidarCalibValidationIssue(
                        matrix_kind,
                        str(path),
                        f"matrix shape must be (4, 4), actual={matrix.shape}",
                    )
                )
            if self._param.finite_value_only and not bool(np.isfinite(matrix).all()):
                issues.append(
                    LidarCalibValidationIssue(
                        matrix_kind,
                        str(path),
                        "matrix contains non-finite values",
                    )
                )

        return tuple(issues)