from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

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

            issues.extend(self._validate_matrix(matrix_kind, str(path), matrix))

        return tuple(issues)

    def validate_matrices(
        self,
        matrices: list[NDArray[np.float64]] | NDArray[np.float64],
        matrix_paths: list[str] | None = None,
        matrix_kind: str = "lidar2crane",
    ) -> list[LidarCalibValidationIssue]:
        array = np.asarray(matrices, dtype=np.float64)
        if array.ndim == 2:
            matrix_list = [array]
        elif array.ndim == 3:
            matrix_list = [array[index] for index in range(array.shape[0])]
        else:
            raise ValueError("matrices must have shape (4, 4) or (N, 4, 4)")

        if matrix_paths is None:
            paths = [f"<generated:{index}>" for index in range(len(matrix_list))]
        else:
            paths = matrix_paths
        if len(paths) != len(matrix_list):
            raise ValueError("matrix_paths must have the same length as matrices")
        issues: list[LidarCalibValidationIssue] = []
        for index, matrix in enumerate(matrix_list):
            issues.extend(self._validate_matrix(matrix_kind, paths[index], matrix))
        return issues

    def _validate_matrix(
        self,
        matrix_kind: str,
        matrix_path: str,
        matrix: NDArray[np.float64],
    ) -> list[LidarCalibValidationIssue]:
        issues: list[LidarCalibValidationIssue] = []
        if self._param.enforce_shape_4x4 and matrix.shape != (4, 4):
            issues.append(
                LidarCalibValidationIssue(
                    matrix_kind,
                    matrix_path,
                    f"matrix shape must be (4, 4), actual={matrix.shape}",
                )
            )
        if self._param.finite_value_only and not bool(np.isfinite(matrix).all()):
            issues.append(
                LidarCalibValidationIssue(
                    matrix_kind,
                    matrix_path,
                    "matrix contains non-finite values",
                )
            )
        return issues