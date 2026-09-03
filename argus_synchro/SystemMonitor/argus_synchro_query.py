from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import PackageNotFoundError, version

from argus_synchro.SystemMonitor.info_mmap import ArgusInfoMMAP

DEFAULT_INFO_PATH = "./log/argus_info.mmap"


def _get_version_text(dist_name: str = "argus_synchro") -> str:
    try:
        return version(dist_name)
    except PackageNotFoundError:
        # エラー時も仮のバージョンを返す.(暫定)
        return "0.0.0"


def main() -> int:
    ap = argparse.ArgumentParser(prog="argus_synchro_query")
    ap.add_argument(
        "cmd",
        choices=["version", "cam_connect", "lidar_connect", "connect", "json"],
        help="query command",
    )
    ap.add_argument(
        "--mmap", default="./log/argus_info.mmap", help="path to argus_info.mmap"
    )
    args = ap.parse_args()

    # version は mmap を読まずに返す
    if args.cmd == "version":
        print(_get_version_text())
        return 0

    # mmap から snapshot を読む
    argus_info: ArgusInfoMMAP | None = None
    try:
        argus_info = ArgusInfoMMAP(args.mmap, create=False)
        snap = argus_info.read_info()
    except Exception as e:
        print(f"mmap error: {e}", file=sys.stderr)
        return 1
    finally:
        if argus_info is not None:
            try:
                argus_info.close()
            except Exception:
                pass

    cam_connect = int(snap.cam_connect) & 0xFFFF
    lidar_connect = int(snap.lidar_connect) & 0xFFFF

    if args.cmd == "cam_connect":
        print(cam_connect)
        return 0

    if args.cmd == "lidar_connect":
        print(lidar_connect)
        return 0

    if args.cmd == "connect":
        # スペース区切り
        print(f"{cam_connect} {lidar_connect}")
        return 0

    # json
    payload = {
        "version": _get_version_text(),
        "cam_count": int(snap.cam_count),
        "lidar_count": int(snap.lidar_count),
        "cam_connect": cam_connect,
        "lidar_connect": lidar_connect,
    }
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
