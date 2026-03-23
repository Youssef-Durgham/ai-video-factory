"""
Phase 5 — Image Generation via ComfyUI + FLUX.1-dev.

Generates 1920x1080 documentary-quality images from visual prompts.
All text rendering is done in post-production (PyCairo), NOT in images.
"""

import json
import time
import uuid
import logging
import requests
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# FLUX WORKFLOW TEMPLATE (ComfyUI API format)
# ════════════════════════════════════════════════════════════════

FLUX_WORKFLOW = {
    "4": {
        "class_type": "UNETLoader",
        "inputs": {
            "unet_name": "flux1-dev-fp8.safetensors",
            "weight_dtype": "fp8_e4m3fn",
        },
    },
    "11": {
        "class_type": "DualCLIPLoader",
        "inputs": {
            "clip_name1": "clip_l.safetensors",
            "clip_name2": "t5xxl_fp8_e4m3fn.safetensors",
            "type": "flux",
        },
    },
    "12": {
        "class_type": "VAELoader",
        "inputs": {"vae_name": "ae.safetensors"},
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "", "clip": ["11", 0]},
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "", "clip": ["11", 0]},
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 1280, "height": 720, "batch_size": 1},
    },
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 0,
            "steps": 20,
            "cfg": 1.0,
            "sampler_name": "euler",
            "scheduler": "simple",
            "denoise": 1.0,
            "model": ["4", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
        },
    },
    "8": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["3", 0], "vae": ["12", 0]},
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "flux_output", "images": ["8", 0]},
    },
}

# Negative prompt baseline — ALWAYS included
NEGATIVE_PROMPT_BASE = (
    "text, writing, letters, words, watermark, subtitle, caption, "
    "logo, signature, stamp, label, number overlay, "
    "blurry, low quality, distorted, deformed, ugly, "
    "extra fingers, extra limbs, mutated hands, bad anatomy"
)


COMFYUI_EXE = r"C:\Users\3d\AppData\Local\Programs\ComfyUI\ComfyUI.exe"
COMFYUI_DEFAULT_PORT = 8000  # ComfyUI Desktop uses port 8000


@dataclass
class ImageGenConfig:
    """Configuration for image generation."""
    comfyui_host: str = f"http://127.0.0.1:{COMFYUI_DEFAULT_PORT}"
    model_name: str = "flux1-dev-fp8.safetensors"
    width: int = 1280
    height: int = 720
    steps: int = 20
    cfg: float = 1.0
    sampler: str = "euler"
    scheduler: str = "normal"
    loras: list = field(default_factory=list)
    timeout_sec: int = 300
    poll_interval_sec: float = 1.0


@dataclass
class ImageGenResult:
    """Result of a single image generation."""
    success: bool
    image_path: Optional[str] = None
    seed: int = 0
    prompt: str = ""
    negative_prompt: str = ""
    generation_time_sec: float = 0.0
    error: Optional[str] = None


class ImageGenerator:
    """
    Generates images via ComfyUI FLUX.1-dev API.

    Usage:
        gen = ImageGenerator(config)
        result = gen.generate(
            prompt="Ancient Mesopotamian city at sunset, cinematic",
            negative_prompt="cartoon, anime",
            output_dir="output/job_001/images",
            filename="scene_001"
        )
    """

    def __init__(self, config: Optional[ImageGenConfig] = None):
        self.config = config or ImageGenConfig()
        self._session = requests.Session()

    # ─── Public API ────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        output_dir: str,
        filename: str = "image",
        negative_prompt: str = "",
        seed: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        lora_name: Optional[str] = None,
        lora_strength: float = 0.8,
    ) -> ImageGenResult:
        """
        Generate a single image from a text prompt.

        Args:
            prompt: Visual description (English, for FLUX).
            output_dir: Directory to save the output PNG.
            filename: Output filename (without extension).
            negative_prompt: Extra negatives (merged with base).
            seed: RNG seed (random if None).
            width/height: Override resolution.
            lora_name: Optional LoRA safetensors filename.
            lora_strength: LoRA influence (0.0–1.0).

        Returns:
            ImageGenResult with path to generated image.
        """
        if seed is None:
            seed = _random_seed()

        # Build full negative prompt
        full_negative = NEGATIVE_PROMPT_BASE
        if negative_prompt:
            full_negative = f"{full_negative}, {negative_prompt}"

        # Build workflow
        workflow = self._build_workflow(
            prompt=prompt,
            negative=full_negative,
            seed=seed,
            width=width or self.config.width,
            height=height or self.config.height,
            lora_name=lora_name,
            lora_strength=lora_strength,
        )

        start = time.time()
        try:
            # Queue prompt
            prompt_id = self._queue_prompt(workflow)
            logger.info(
                f"Queued FLUX generation: prompt_id={prompt_id}, seed={seed}"
            )

            # Poll for completion
            output_images = self._wait_for_completion(prompt_id)
            if not output_images:
                return ImageGenResult(
                    success=False,
                    seed=seed,
                    prompt=prompt,
                    negative_prompt=full_negative,
                    error="No output images returned from ComfyUI",
                )

            # Download image
            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)
            image_path = str(out_path / f"{filename}.png")

            self._download_image(output_images[0], image_path)

            elapsed = round(time.time() - start, 2)
            logger.info(
                f"Image generated: {image_path} ({elapsed}s, seed={seed})"
            )
            return ImageGenResult(
                success=True,
                image_path=image_path,
                seed=seed,
                prompt=prompt,
                negative_prompt=full_negative,
                generation_time_sec=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            logger.error(f"Image generation failed: {e}")
            return ImageGenResult(
                success=False,
                seed=seed,
                prompt=prompt,
                negative_prompt=full_negative,
                generation_time_sec=elapsed,
                error=str(e),
            )

    def generate_batch(
        self,
        scenes: list[dict],
        output_dir: str,
        channel_lora: Optional[str] = None,
    ) -> list[ImageGenResult]:
        """
        Generate images for a list of scenes (sequential, one GPU model).

        Each scene dict must have at minimum:
            - scene_index: int
            - visual_prompt: str (English)
        Optional:
            - negative_prompt: str
            - seed: int

        Returns list of ImageGenResult in scene order.
        """
        results = []
        total = len(scenes)
        for i, scene in enumerate(scenes):
            idx = scene.get("scene_index", i)
            logger.info(f"Generating image {i + 1}/{total} (scene {idx})")

            result = self.generate(
                prompt=scene["visual_prompt"],
                output_dir=output_dir,
                filename=f"scene_{idx:03d}",
                negative_prompt=scene.get("negative_prompt", ""),
                seed=scene.get("seed"),
                lora_name=channel_lora,
            )
            results.append(result)

        passed = sum(1 for r in results if r.success)
        logger.info(f"Batch complete: {passed}/{total} images generated")
        return results

    def check_server(self) -> bool:
        """Verify ComfyUI server is reachable."""
        try:
            r = self._session.get(
                f"{self.config.comfyui_host}/api/system_stats", timeout=5
            )
            return r.status_code == 200
        except Exception:
            return False

    def ensure_server(self, max_wait: int = 120) -> bool:
        """
        Ensure ComfyUI is running. If not, start it and wait until ready.
        Returns True if server is available, False if failed to start.
        """
        if self.check_server():
            logger.info("ComfyUI already running")
            return True

        logger.info("ComfyUI not running — starting it...")
        try:
            import subprocess
            subprocess.Popen(
                [COMFYUI_EXE],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x00000008,  # DETACHED_PROCESS on Windows
            )
            logger.info(f"ComfyUI process started, waiting up to {max_wait}s...")
        except Exception as e:
            logger.error(f"Failed to start ComfyUI: {e}")
            return False

        # Wait for server to become available
        deadline = time.time() + max_wait
        while time.time() < deadline:
            if self.check_server():
                logger.info("ComfyUI is ready!")
                return True
            time.sleep(3)

        logger.error(f"ComfyUI did not start within {max_wait}s")
        return False

    # ─── Internal Methods ──────────────────────────────────

    def _build_workflow(
        self,
        prompt: str,
        negative: str,
        seed: int,
        width: int,
        height: int,
        lora_name: Optional[str],
        lora_strength: float,
    ) -> dict:
        """Build ComfyUI workflow JSON from template."""
        wf = json.loads(json.dumps(FLUX_WORKFLOW))  # deep copy

        # Model
        wf["4"]["inputs"]["unet_name"] = self.config.model_name

        # Prompts
        wf["6"]["inputs"]["text"] = prompt
        wf["7"]["inputs"]["text"] = negative

        # Sampler
        wf["3"]["inputs"]["seed"] = seed
        wf["3"]["inputs"]["steps"] = self.config.steps
        wf["3"]["inputs"]["cfg"] = self.config.cfg
        wf["3"]["inputs"]["sampler_name"] = self.config.sampler
        wf["3"]["inputs"]["scheduler"] = self.config.scheduler

        # Resolution
        wf["5"]["inputs"]["width"] = width
        wf["5"]["inputs"]["height"] = height

        # LoRA injection (rewires model from UNETLoader)
        if lora_name:
            wf = self._inject_lora(wf, lora_name, lora_strength)

        # Unique filename prefix to avoid collisions
        wf["9"]["inputs"]["filename_prefix"] = f"flux_{uuid.uuid4().hex[:8]}"

        return wf

    def _inject_lora(
        self, wf: dict, lora_name: str, strength: float
    ) -> dict:
        """Insert a LoRA loader node between checkpoint and sampler."""
        lora_node_id = "10"
        wf[lora_node_id] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": lora_name,
                "strength_model": strength,
                "strength_clip": strength,
                "model": ["4", 0],
                "clip": ["11", 0],
            },
        }
        # Rewire sampler and CLIP nodes to use LoRA output
        wf["3"]["inputs"]["model"] = [lora_node_id, 0]
        wf["6"]["inputs"]["clip"] = [lora_node_id, 1]
        wf["7"]["inputs"]["clip"] = [lora_node_id, 1]
        return wf

    def _queue_prompt(self, workflow: dict) -> str:
        """Submit workflow to ComfyUI and return prompt_id."""
        client_id = uuid.uuid4().hex
        payload = {"prompt": workflow, "client_id": client_id}
        r = self._session.post(
            f"{self.config.comfyui_host}/api/prompt",
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        return data["prompt_id"]

    def _wait_for_completion(self, prompt_id: str) -> list[dict]:
        """
        Poll ComfyUI /history until the prompt is done.
        Returns list of output image references.
        """
        deadline = time.time() + self.config.timeout_sec
        while time.time() < deadline:
            try:
                r = self._session.get(
                    f"{self.config.comfyui_host}/api/history/{prompt_id}",
                    timeout=10,
                )
                if r.status_code == 200:
                    data = r.json()
                    if prompt_id in data:
                        outputs = data[prompt_id].get("outputs", {})
                        for node_id, node_out in outputs.items():
                            images = node_out.get("images", [])
                            if images:
                                return images
            except Exception:
                pass
            time.sleep(self.config.poll_interval_sec)

        raise TimeoutError(
            f"ComfyUI generation timed out after {self.config.timeout_sec}s"
        )

    def _download_image(self, image_ref: dict, save_path: str):
        """Download generated image from ComfyUI server."""
        filename = image_ref["filename"]
        subfolder = image_ref.get("subfolder", "")
        img_type = image_ref.get("type", "output")

        params = {
            "filename": filename,
            "subfolder": subfolder,
            "type": img_type,
        }
        r = self._session.get(
            f"{self.config.comfyui_host}/api/view",
            params=params,
            timeout=30,
        )
        r.raise_for_status()

        with open(save_path, "wb") as f:
            f.write(r.content)


# ─── Helpers ───────────────────────────────────────────────

def _random_seed() -> int:
    """Generate a random seed for reproducibility tracking."""
    import random
    return random.randint(0, 2**32 - 1)
