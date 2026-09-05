from collections.abc import Callable
from typing import TypeAlias

from argus_synchro.common.app_logger import AppLogger

DecoderFn: TypeAlias = Callable[[str, float, AppLogger], tuple[float, ...]]


def handle_angle_oldcan(
    raw_can_data: str, yaw_offset_deg: float, logger: AppLogger
) -> tuple[float]:
    current_degree = 360.0 - (int(raw_can_data[4:8], 16) / 10.0)
    yaw_angle_deg = current_degree + yaw_offset_deg
    logger.info("handle_angle_oldcan, can deg(old, handler): %f", yaw_angle_deg)
    return (yaw_angle_deg,)


def handle_angle_newcan(
    raw_can_data: str, yaw_offset_deg: float, logger: AppLogger
) -> tuple[float]:
    current_degree = (
        int(raw_can_data[:2], 16) + int(raw_can_data[2:4], 16) * 255
    ) / (13400.0 / 360.0)
    yaw_angle_deg = current_degree - yaw_offset_deg
    logger.info("handle_angle_newcan, can deg(new, handler): %f", yaw_angle_deg)
    return (yaw_angle_deg,)


def handle_angle_newcan_inverted(
    raw_can_data: str, yaw_offset_deg: float, logger: AppLogger
) -> tuple[float]:
    current_degree = (
        int(raw_can_data[:2], 16) + int(raw_can_data[2:4], 16) * 255
    ) / (13400.0 / 360.0)
    current_degree = (360.0 - current_degree) % 360.0
    yaw_angle_deg = current_degree - yaw_offset_deg
    logger.info(
        "handle_angle_newcan_inverted, can deg(new, handler): %f",
        yaw_angle_deg,
    )
    return (yaw_angle_deg,)


def handle_lever(
    raw_can_data: str, _yaw_offset_deg: float, logger: AppLogger
) -> tuple[float, ...]:
    logger.info("handle_lever, lever handler data: %s", raw_can_data)
    payload = raw_can_data[:-2]
    payload_bytes = bytes.fromhex(payload)
    lever_pressure = tuple(
        int.from_bytes(payload_bytes[index : index + 2], "big") * 0.001
        for index in (0, 2, 4, 6)
    )
    logger.info(
        "handle_lever, lever handler data: %f, %f, %f, %f",
        *lever_pressure,
    )
    return lever_pressure


def handle_angle_can_scx2000(
    raw_can_data: str, yaw_offset_deg: float, logger: AppLogger
) -> tuple[float]:
    raw_angle = raw_can_data[14:16] + raw_can_data[12:14]
    current_degree = int(raw_angle, 16) / 10.0
    yaw_angle_deg = (-(current_degree - yaw_offset_deg)) % 360.0
    logger.info(
        "handle_angle_can_scx2000, can deg(can scx2000, handler): %f",
        yaw_angle_deg,
    )
    return (yaw_angle_deg,)


DECODER_REGISTRY: dict[str, DecoderFn] = {
    "handle_angle_oldcan": handle_angle_oldcan,
    "handle_angle_newcan": handle_angle_newcan,
    "handle_angle_newcan_inverted": handle_angle_newcan_inverted,
    "handle_lever": handle_lever,
    "handle_angle_can_scx2000": handle_angle_can_scx2000,
}
