"""Tests for GPUMemoryManager — model load/unload, VRAM tracking, emergency cleanup."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock
from src.core.gpu_manager import GPUMemoryManager


@pytest.fixture
def gpu_config():
    return {
        "device": "cuda:0",
        "vram_gb": 24,
        "safety_margin_gb": 2,
        "max_temperature_c": 85,
        "monitor_interval_sec": 5,
    }


@pytest.fixture
def manager(gpu_config):
    with patch("src.core.gpu_manager.torch") as mock_torch:
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.mem_get_info.return_value = (20e9, 24e9)  # 20GB free
        mgr = GPUMemoryManager(gpu_config)
        mgr.set_hosts("http://localhost:11434", "http://localhost:8188")
        yield mgr


class TestModelLoading:
    @patch("src.core.gpu_manager.requests")
    @patch("src.core.gpu_manager.torch")
    def test_load_ollama_model(self, mock_torch, mock_requests, gpu_config):
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.mem_get_info.return_value = (20e9, 24e9)
        mock_requests.post.return_value = MagicMock(status_code=200)

        mgr = GPUMemoryManager(gpu_config)
        mgr.set_hosts("http://localhost:11434", "http://localhost:8188")
        mgr.load_model("qwen3.5:27b", model_type="ollama")

        assert mgr.current_model == "qwen3.5:27b"
        assert mgr.current_type == "ollama"

    @patch("src.core.gpu_manager.requests")
    @patch("src.core.gpu_manager.torch")
    def test_load_comfyui_model(self, mock_torch, mock_requests, gpu_config):
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.mem_get_info.return_value = (20e9, 24e9)
        mock_requests.get.return_value = MagicMock(status_code=200)

        mgr = GPUMemoryManager(gpu_config)
        mgr.set_hosts("http://localhost:11434", "http://localhost:8188")
        mgr.load_model("flux", model_type="comfyui")

        assert mgr.current_model == "flux"
        assert mgr.current_type == "comfyui"

    @patch("src.core.gpu_manager.requests")
    @patch("src.core.gpu_manager.torch")
    def test_insufficient_vram_raises(self, mock_torch, mock_requests, gpu_config):
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.mem_get_info.return_value = (2e9, 24e9)  # Only 2GB free

        mgr = GPUMemoryManager(gpu_config)
        mgr.set_hosts("http://localhost:11434", "http://localhost:8188")
        with pytest.raises(RuntimeError, match="Insufficient VRAM"):
            mgr.load_model("qwen3.5:27b", model_type="ollama")


class TestModelUnloading:
    @patch("src.core.gpu_manager.requests")
    @patch("src.core.gpu_manager.torch")
    @patch("src.core.gpu_manager.time")
    def test_unload_clears_state(self, mock_time, mock_torch, mock_requests, gpu_config):
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.mem_get_info.return_value = (20e9, 24e9)
        mock_requests.post.return_value = MagicMock(status_code=200)

        mgr = GPUMemoryManager(gpu_config)
        mgr.set_hosts("http://localhost:11434", "http://localhost:8188")
        mgr.load_model("qwen3.5:27b", model_type="ollama")
        mgr.unload_model()

        assert mgr.current_model is None
        assert mgr.current_type is None

    @patch("src.core.gpu_manager.torch")
    @patch("src.core.gpu_manager.time")
    def test_unload_noop_when_empty(self, mock_time, mock_torch, gpu_config):
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.mem_get_info.return_value = (20e9, 24e9)

        mgr = GPUMemoryManager(gpu_config)
        mgr.unload_model()  # Should not raise
        assert mgr.current_model is None

    @patch("src.core.gpu_manager.requests")
    @patch("src.core.gpu_manager.torch")
    @patch("src.core.gpu_manager.time")
    def test_swap_models(self, mock_time, mock_torch, mock_requests, gpu_config):
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.mem_get_info.return_value = (20e9, 24e9)
        mock_requests.post.return_value = MagicMock(status_code=200)
        mock_requests.get.return_value = MagicMock(status_code=200)

        mgr = GPUMemoryManager(gpu_config)
        mgr.set_hosts("http://localhost:11434", "http://localhost:8188")
        mgr.load_model("qwen3.5:27b", model_type="ollama")
        mgr.load_model("flux", model_type="comfyui")

        assert mgr.current_model == "flux"
        assert mgr.current_type == "comfyui"


class TestVRAMTracking:
    @patch("src.core.gpu_manager.torch")
    def test_get_free_vram(self, mock_torch, gpu_config):
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.mem_get_info.return_value = (15e9, 24e9)

        mgr = GPUMemoryManager(gpu_config)
        free = mgr._get_free_vram()
        assert abs(free - 15.0) < 0.1

    @patch("src.core.gpu_manager.torch")
    def test_get_free_vram_no_cuda(self, mock_torch, gpu_config):
        mock_torch.cuda.is_available.return_value = False

        mgr = GPUMemoryManager(gpu_config)
        assert mgr._get_free_vram() == 0.0


class TestEmergencyCleanup:
    @patch("src.core.gpu_manager.subprocess")
    @patch("src.core.gpu_manager.torch")
    @patch("src.core.gpu_manager.gc")
    @patch("src.core.gpu_manager.time")
    def test_emergency_cleanup(self, mock_time, mock_gc, mock_torch, mock_sub, gpu_config):
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.mem_get_info.return_value = (20e9, 24e9)

        mgr = GPUMemoryManager(gpu_config)
        mgr.current_model = "qwen3.5:27b"
        mgr.current_type = "ollama"
        mgr.emergency_cleanup()

        assert mgr.current_model is None
        assert mgr.current_type is None
        mock_torch.cuda.empty_cache.assert_called()
        mock_gc.collect.assert_called()
        mock_sub.run.assert_called()


class TestBatchDetection:
    def test_model_vram_requirements(self, gpu_config):
        with patch("src.core.gpu_manager.torch"):
            mgr = GPUMemoryManager(gpu_config)
            # Verify known models have VRAM estimates
            assert "flux" in mgr.MODEL_VRAM
            assert "ltx" in mgr.MODEL_VRAM
            assert mgr.MODEL_VRAM["flux"] > 0


class TestGPULogger:
    @patch("src.core.gpu_manager.requests")
    @patch("src.core.gpu_manager.torch")
    def test_load_with_logger(self, mock_torch, mock_requests, gpu_config):
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.mem_get_info.return_value = (20e9, 24e9)
        mock_requests.post.return_value = MagicMock(status_code=200)

        mock_logger = MagicMock()
        mock_logger.log_model_load_start.return_value = 0

        mgr = GPUMemoryManager(gpu_config)
        mgr.set_hosts("http://localhost:11434", "http://localhost:8188")
        mgr.load_model("qwen3.5:27b", model_type="ollama", gpu_logger=mock_logger)

        mock_logger.log_model_load_start.assert_called_once()
        mock_logger.log_model_load_end.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
