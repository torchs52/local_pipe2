from pathlib import Path

from argus_synchro.common import paths
from argus_synchro.config.app_config_calibration import AppConfigCalibration

from directory_config_helper import dev_directory_config


def test_outputdir_root_uses_cli_log_dir_for_relative_setting() -> None:
    repo_root = Path.cwd()
    directory_config = paths.DirectoryConfig(
        config_dir=paths.normalize_path("./config", repo_root),
        log_dir=paths.normalize_path("/tmp/log", repo_root),
        mmap_dir=paths.DEFAULT_MMAP_DIR,
    )
    directory_config, _ = paths.load_directory_config_from_ini(directory_config)
    app_config = AppConfigCalibration(
        configpath="config/calib_settings.ini",
        arglist=[],
        directory_config=directory_config,
    )

    assert app_config.default.outputdir_root == "/tmp/log/tmpCalib"
    assert app_config.filepath_io.Calib3d3dmat_lidars[0] == (
        "/tmp/log/tmpCalib/3d-3d/lidar2crane_trans_mat_0.csv"
    )
    assert app_config.calibCheck2d3d.resultfiles[0] == (
        "/tmp/log/tmpCalib/calibcheck2d3d_results_camera0.txt"
    )


def test_outputdir_root_uses_dev_cli_log_dir() -> None:
    app_config = AppConfigCalibration(
        configpath="config/calib_settings.ini",
        arglist=[],
        directory_config=dev_directory_config(),
    )
    expected_root = str(Path.cwd().resolve() / "log" / "tmpCalib")
    assert app_config.default.outputdir_root == expected_root
