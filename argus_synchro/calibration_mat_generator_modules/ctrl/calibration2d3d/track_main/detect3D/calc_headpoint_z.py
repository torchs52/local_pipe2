import numpy as np
from numpy.typing import NDArray


class calc_headpoint_z:
    def __init__(
        self, xrange: tuple[float, float], yrange: tuple[float, float]
    ) -> None:
        self.clear(xrange=xrange, yrange=yrange)

    def clear(self, xrange: tuple[float, float], yrange: tuple[float, float]) -> None:
        self.xrange = xrange
        self.yrange = yrange

    def apply(self, corrpoint3d_set: NDArray[np.float64]) -> float:
        ph = corrpoint3d_set[:, 0, :]
        mask = (
            (ph[:, 0] > self.xrange[0])
            & (ph[:, 0] < self.xrange[1])
            & (ph[:, 1] > self.yrange[0])
            & (ph[:, 1] < self.yrange[1])
        )
        return float(np.median(ph[mask, 2]))
