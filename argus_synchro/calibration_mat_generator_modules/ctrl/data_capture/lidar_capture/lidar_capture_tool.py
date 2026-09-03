import numpy as np


def read_singleLidar_file(ref_t, nameprefix, digits=6):
    if ref_t < 0:
        print("Warning: ref_t is ", ref_t)
        return None

    frame = f"{ref_t}".zfill(digits)
    lidar_file = nameprefix + frame + ".npy"
    try:
        xyz = np.load(lidar_file, allow_pickle=True)
        xyz = xyz[xyz[:, 3] != 0]  # 輝度ゼロの点を消去
    except FileNotFoundError:
        print("Warning: File ", lidar_file, " is not found!")
        return None

    return xyz
