"""UI status codes for 2D-3D calibration results."""

from enum import IntEnum


class Calib2d3dErrorCommon(IntEnum):
    DEFAULT = 0
    CALIBRATION_SUCCEEDED = 1
    WALKING_RANGE_INVALID = 2
    WALKING_PERSON_COUNT_INVALID = 3
    POOR_PERSON_DETECTION = 4
    POOR_TRACKING_3D = 5
    POOR_TRACKING_2D = 6
    UNSUITABLE_CONDITION = 7
    RESERVED_8 = 8
    RESERVED_9 = 9
    RESERVED_10 = 10
    RESERVED_11 = 11
    RESERVED_12 = 12
    RESERVED_13 = 13
    RESERVED_14 = 14
    RESERVED_15 = 15
    LONG_DURATION_CALIBRATION = 16
    PERSON_DETECTION_IMPOSSIBLE = 17
    TRACKING_IMPOSSIBLE = 18
    RESERVED_19 = 19
    RESERVED_20 = 20
    RESERVED_21 = 21
    RESERVED_22 = 22
    RESERVED_23 = 23
    RESERVED_24 = 24
    RESERVED_25 = 25
    RESERVED_26 = 26
    RESERVED_27 = 27
    RESERVED_28 = 28
    RESERVED_29 = 29
    RESERVED_30 = 30
    RESERVED_31 = 31


class Calib2d3dResultDiagnosis:
    def diagnose(self, *args: object) -> Calib2d3dErrorCommon:
        return Calib2d3dErrorCommon.DEFAULT


class CameraCalibrationStatus(IntEnum):
    DEFAULT = 0
    CALIBRATION_SUCCEEDED = 1
    POOR_SENSOR_CORRESPONDENCE = 2
    WALKING_PERSON_COUNT_INVALID = 3
    POOR_TRACKING_3D = 4
    POOR_TRACKING_2D = 5
    CALIBRATION_MATRIX_INVALID = 6
    RESERVED_7 = 7


class CameraCalibrationStatusDiagnosis:
    def diagnose(self, *args: object) -> CameraCalibrationStatus:
        return CameraCalibrationStatus.DEFAULT