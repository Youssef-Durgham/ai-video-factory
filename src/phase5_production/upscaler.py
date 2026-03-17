"""
Phase 5 — Real-ESRGAN 4K Upscaling (CPU).

Upscales 1080p images to 4K (3840x2160) using Real-ESRGAN.
Runs on CPU so it can execute in parallel with GPU workloads.
"""

import logging
import time
import subprocess
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class UpscalerConfig:
    """Configuration for Real-ESRGAN upscaling."""
    model_name: str = "RealESRGAN_x4plus"
    scale: int = 4
    tile_size: int = 512
    tile_pad: int = 10
    half_precision: bool = False  # CPU doesn't support fp16
    output_format: str = "png"
    timeout_sec: int = 300
    # Path to realesrgan-ncnn-vulkan binary (if using CLI)
    binary_path: Optional[str] = None


@dataclass
class UpscaleResult:
    """Result of an upscale operation."""
    success: bool
    input_path: Optional[str] = None
    output_path: Optional[str] = None
    input_resolution: Optional[tuple[int, int]] = None
    output_resolution: Optional[tuple[int, int]] = None
    processing_time_sec: float = 0.0
    error: Optional[str] = None


class Upscaler:
    """
    Real-ESRGAN 4K upscaling for documentary images.

    Runs on CPU to avoid GPU contention with image/video generation.
    Can be called in parallel with GPU-bound operations.

    Supports two backends:
    1. Python API (realesrgan package)
    2. CLI binary (realesrgan-ncnn-vulkan)
    """

    def __init__(self, config: Optional[UpscalerConfig] = None):
        self.config = config or UpscalerConfig()
        self._model = None

    def upscale_image(
        self,
        input_path: str,
        output_path: str,
        scale: Optional[int] = None,
    ) -> UpscaleResult:
        """
        Upscale a single image (1080p → 4K).

        Args:
            input_path: Path to input image (PNG/JPG).
            output_path: Path for upscaled output.
            scale: Override scale factor (default: 4x).

        Returns:
            UpscaleResult with output path and resolution.
        """
        in_path = Path(input_path)
        if not in_path.exists():
            return UpscaleResult(
                success=False,
                input_path=input_path,
                error=f"Input file not found: {input_path}",
            )

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        effective_scale = scale or self.config.scale

        start = time.time()

        # Try Python API first, fall back to CLI
        try:
            result = self._upscale_python(input_path, output_path, effective_scale)
        except ImportError:
            logger.info("realesrgan package not available, trying CLI binary")
            try:
                result = self._upscale_cli(input_path, output_path, effective_scale)
            except Exception as e:
                elapsed = round(time.time() - start, 2)
                return UpscaleResult(
                    success=False,
                    input_path=input_path,
                    processing_time_sec=elapsed,
                    error=f"Both upscale methods failed: {e}",
                )

        result.processing_time_sec = round(time.time() - start, 2)
        if result.success:
            logger.info(
                f"Upscaled: {in_path.name} → {Path(output_path).name} "
                f"({result.processing_time_sec}s)"
            )
        return result

    def upscale_batch(
        self,
        input_paths: list[str],
        output_dir: str,
        suffix: str = "_4k",
    ) -> list[UpscaleResult]:
        """
        Upscale multiple images.

        Args:
            input_paths: List of input image paths.
            output_dir: Directory for upscaled outputs.
            suffix: Suffix to add to filenames (e.g. "_4k").

        Returns:
            List of UpscaleResult in input order.
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        results = []

        for i, in_path in enumerate(input_paths):
            name = Path(in_path).stem
            ext = Path(in_path).suffix or ".png"
            out_path = str(Path(output_dir) / f"{name}{suffix}{ext}")

            logger.info(f"Upscaling {i + 1}/{len(input_paths)}: {Path(in_path).name}")
            result = self.upscale_image(in_path, out_path)
            results.append(result)

        passed = sum(1 for r in results if r.success)
        logger.info(f"Batch upscale: {passed}/{len(input_paths)} completed")
        return results

    # ═══════════════════════════════════════════════════════
    # PYTHON API BACKEND
    # ═══════════════════════════════════════════════════════

    def _upscale_python(
        self, input_path: str, output_path: str, scale: int
    ) -> UpscaleResult:
        """Upscale using the realesrgan Python package (CPU)."""
        import cv2
        import numpy as np
        from realesrgan import RealESRGANer
        from basicsr.archs.rrdbnet_arch import RRDBNet

        # Load model on first use
        if self._model is None:
            model = RRDBNet(
                num_in_ch=3, num_out_ch=3, num_feat=64,
                num_block=23, num_grow_ch=32, scale=4,
            )
            self._model = RealESRGANer(
                scale=4,
                model_path=None,  # Auto-download
                model=model,
                tile=self.config.tile_size,
                tile_pad=self.config.tile_pad,
                pre_pad=0,
                half=False,  # CPU mode
                device="cpu",
            )

        # Read image
        img = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            return UpscaleResult(
                success=False,
                input_path=input_path,
                error=f"Failed to read image: {input_path}",
            )

        h, w = img.shape[:2]

        # Upscale
        output, _ = self._model.enhance(img, outscale=scale)

        # Save
        cv2.imwrite(output_path, output)

        oh, ow = output.shape[:2]
        return UpscaleResult(
            success=True,
            input_path=input_path,
            output_path=output_path,
            input_resolution=(w, h),
            output_resolution=(ow, oh),
        )

    # ═══════════════════════════════════════════════════════
    # CLI BINARY BACKEND
    # ═══════════════════════════════════════════════════════

    def _upscale_cli(
        self, input_path: str, output_path: str, scale: int
    ) -> UpscaleResult:
        """Upscale using realesrgan-ncnn-vulkan CLI binary."""
        binary = self.config.binary_path or "realesrgan-ncnn-vulkan"

        cmd = [
            binary,
            "-i", input_path,
            "-o", output_path,
            "-s", str(scale),
            "-n", self.config.model_name,
            "-t", str(self.config.tile_size),
            "-f", self.config.output_format,
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.config.timeout_sec,
        )

        if proc.returncode != 0:
            return UpscaleResult(
                success=False,
                input_path=input_path,
                error=f"CLI upscale failed: {proc.stderr[:300]}",
            )

        if not Path(output_path).exists():
            return UpscaleResult(
                success=False,
                input_path=input_path,
                error="CLI completed but output file not found",
            )

        # Get output resolution
        out_res = self._get_resolution(output_path)
        in_res = self._get_resolution(input_path)

        return UpscaleResult(
            success=True,
            input_path=input_path,
            output_path=output_path,
            input_resolution=in_res,
            output_resolution=out_res,
        )

    def _get_resolution(self, image_path: str) -> Optional[tuple[int, int]]:
        """Get image resolution using ffprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0:s=x",
                image_path,
            ]
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10,
            )
            parts = proc.stdout.strip().split("x")
            if len(parts) == 2:
                return (int(parts[0]), int(parts[1]))
        except Exception:
            pass
        return None
