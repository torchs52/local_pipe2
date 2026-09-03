from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from argus_synchro.common.app_logger import AppLoggerFactory
from argus_synchro.config.app_config import AppConfig
from argus_synchro.detect2d import (
    TRT_MAX_WORKSPACE_SIZE,
    Detect2dDamoYoloOnnx,
    _OnnxRuntimeBackend,
    _detect_onnx_runtime_backend,
    trt_ep_options,
    trt_profile_shape,
)


class _FakeOnnxSession:
    def __init__(self, providers: list[str]) -> None:
        self._providers = providers

    def get_providers(self) -> list[str]:
        return self._providers


@pytest.mark.parametrize(
    ("providers", "expected"),
    [
        (["TensorrtExecutionProvider", "CUDAExecutionProvider"], _OnnxRuntimeBackend.TENSORRT),
        (["CUDAExecutionProvider", "CPUExecutionProvider"], _OnnxRuntimeBackend.CUDA),
        (["CPUExecutionProvider"], _OnnxRuntimeBackend.CPU),
    ],
)
def test_detect_onnx_runtime_backend(
    providers: list[str],
    expected: _OnnxRuntimeBackend,
) -> None:
    assert _detect_onnx_runtime_backend(_FakeOnnxSession(providers)) is expected


@pytest.mark.parametrize("batch_size", [1, 2, 3])
def test_trt_ep_options_reflects_performance_settings(
    tmp_path: Path,
    batch_size: int,
) -> None:
    onnx_file = tmp_path / "model.onnx"
    onnx_file.touch()

    options = trt_ep_options(str(onnx_file), batch_size)

    assert options["trt_max_workspace_size"] == TRT_MAX_WORKSPACE_SIZE
    assert options["trt_builder_optimization_level"] == 5
    assert options["trt_cuda_graph_enable"] is True
    assert options["trt_engine_cache_path"] == str(tmp_path)
    assert options["trt_timing_cache_path"] == str(tmp_path)
    assert options["trt_profile_min_shapes"] == trt_profile_shape(batch_size)
    assert options["trt_profile_opt_shapes"] == trt_profile_shape(batch_size)
    assert options["trt_profile_max_shapes"] == trt_profile_shape(batch_size)


@pytest.mark.parametrize("batch_size", [1, 2, 3])
def test_damoyolo_onnx_accepts_batch_on_tensorrt(
    app_config: AppConfig,
    batch_size: int,
) -> None:
    """TRTプロファイルをバッチ数に合わせた場合、batch=1/2/3 推論が通ることを確認する。"""

    model_path = Path(app_config.detect2d.onnx_model_path)
    if not model_path.is_absolute():
        model_path = Path.cwd() / model_path

    assert model_path.exists(), f"ONNXモデルが存在しません: {model_path}"

    detector = Detect2dDamoYoloOnnx(
        conf_thresh=app_config.detect2d.conf_thresh,
        nms_thresh=app_config.detect2d.nms_thresh,
        onnx_model_path=str(model_path),
        batch_size=batch_size,
        app_logger_factory=AppLoggerFactory(to_console=False),
    )

    if "TensorrtExecutionProvider" not in detector.model_sess.get_providers():
        pytest.skip("TensorrtExecutionProvider is not active in this environment")

    frames = np.zeros((batch_size, 640, 640, 3), dtype=np.uint8)
    bboxes, scores, class_ids, valid_detects = detector._inference(frames)  # noqa: SLF001

    assert bboxes.shape == (batch_size, 50, 4)
    assert scores.shape == (batch_size, 50)
    assert class_ids.shape == (batch_size, 50)
    assert valid_detects.shape == (batch_size,)
