from __future__ import annotations

import mmap
import os
import struct
from dataclasses import dataclass
from pathlib import Path

# =========================================================
# Layout
#
# offset  size  type
#
# 0       2     uint16   cam_count
# 2       2     uint16   lidar_count
# 4       2     uint16   cam_connect
# 6       2     uint16   lidar_connect
#
# total = 8 bytes
# =========================================================

_STRUCT_FORMAT = "<HHHH"
_STRUCT_SIZE = struct.calcsize(_STRUCT_FORMAT)


@dataclass(slots=True)
class ArgusInfo:
    cam_count: int
    lidar_count: int
    cam_connect: int
    lidar_connect: int


class ArgusInfoMMAP:
    __slots__ = ("_file", "_mmap", "_path")

    # -----------------------------------------------------
    # initialize mmap
    # -----------------------------------------------------
    @staticmethod
    def initialize(
        path: str,
        cam_count: int,
        lidar_count: int,
        mode: int = 0o644,
        create: bool = False,
    ) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        if p.exists() and not create:
            return

        # create=True の場合も含め、作り直す
        with open(p, "wb") as f:
            f.write(b"\x00" * _STRUCT_SIZE)

        os.chmod(p, mode)

        with open(p, "r+b") as f:
            mm = mmap.mmap(f.fileno(), _STRUCT_SIZE)
            data = struct.pack(
                _STRUCT_FORMAT,
                int(cam_count) & 0xFFFF,
                int(lidar_count) & 0xFFFF,
                7,
                3,
            )
            mm.seek(0)
            mm.write(data)
            mm.flush()
            mm.close()

    # -----------------------------------------------------
    # constructor
    # -----------------------------------------------------
    def __init__(
        self,
        path: str,
        create: bool = False,
        cam_count: int = 0,
        lidar_count: int = 0,
    ) -> None:
        self._path = Path(path)

        if create:
            self.initialize(path, cam_count, lidar_count)

        if not self._path.exists():
            raise FileNotFoundError(f"mmap not found: {self._path}")

        self._file = open(self._path, "r+b")
        self._mmap = mmap.mmap(self._file.fileno(), _STRUCT_SIZE)

    # -----------------------------------------------------
    # read info
    # -----------------------------------------------------
    def read_info(self) -> ArgusInfo:
        self._mmap.seek(0)

        (
            cam_count,
            lidar_count,
            cam_connect,
            lidar_connect,
        ) = struct.unpack(_STRUCT_FORMAT, self._mmap.read(_STRUCT_SIZE))

        return ArgusInfo(
            cam_count=cam_count,
            lidar_count=lidar_count,
            cam_connect=cam_connect,
            lidar_connect=lidar_connect,
        )

    # -----------------------------------------------------
    # write snapshot
    # -----------------------------------------------------
    def write_info(self, snap: ArgusInfo) -> None:
        data = struct.pack(
            _STRUCT_FORMAT,
            int(snap.cam_count) & 0xFFFF,
            int(snap.lidar_count) & 0xFFFF,
            int(snap.cam_connect) & 0xFFFF,
            int(snap.lidar_connect) & 0xFFFF,
        )

        self._mmap.seek(0)
        self._mmap.write(data)
        self._mmap.flush()

    # -----------------------------------------------------
    # close
    # -----------------------------------------------------
    def close(self) -> None:
        try:
            self._mmap.close()
        finally:
            self._file.close()
