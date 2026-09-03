import cv2
import numpy as np
from numpy.typing import NDArray

from argus_synchro.config.app_config_calibration import AppConfigCalibration


class image_preprocess:
    def __init__(
        self, app_config_calib: AppConfigCalibration, camera_index: int
    ) -> None:
        self.enable_imgmask = app_config_calib.calib2d3d.Proc2d.enable_imgmask
        img = cv2.imread(
            app_config_calib.calib2d3d.Proc2d.camera_mask_images[camera_index]
        )
        assert img is not None, (
            f"{app_config_calib.calib2d3d.Proc2d.camera_mask_images[camera_index]} not loaded"
        )
        height = app_config_calib.dataCapture.Camera.sys_height
        width = app_config_calib.dataCapture.Camera.sys_width
        img = cv2.resize(img, dsize=(width, height))
        self.maskdata: NDArray[np.bool_] = img > 0

    def apply(self, image: NDArray[np.uint8]) -> NDArray[np.uint8]:
        if not self.enable_imgmask:
            return image

        res = image * self.maskdata
        # cv2.imshow("test", res)
        # cv2.waitKey(1)
        return res
