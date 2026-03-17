"""
Phase 5 — Video Generation via ComfyUI + LTX-2.3 (image-to-video).

Generates 5–10 second video clips from approved FLUX images with
camera movements. Falls back to Ken Burns (FFmpeg) on failure.
"""

import json
import time
import uuid
import shutil
import logging
import subprocess
import requests
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# CAMERA MOVEMENT → LTX MOTION PROMPT MAP
# ════════════════════════════════════════════════════════════════

CAMERA_MOTION_MAP: dict[str, str] = {
    "slow_zoom_in": "camera slowly zooming in",
    "slow_zoom_out": "camera slowly zooming out",
    "pan_left": "camera panning left slowly",
    "pan_right": "camera panning right slowly",
    "tilt_up": "camera tilting upward",
    "tilt_down": "camera tilting downward",
    "dolly_forward": "camera moving forward smoothly",
    "dolly_back": "camera pulling back",
    "parallax": "subtle parallax motion, depth layers",
    "orbit_left": "camera orbiting subject from left",
    "orbit_right": "camera orbiting subject from right",
    "crane_up": "camera rising upward crane shot",
    "static": "very subtle camera sway, almost static",
    "handheld": "subtle handheld camera shake, documentary",
}

# Ken Burns FFmpeg presets (fallback)
KEN_BURNS_PRESETS: dict[str, str] = {
    "slow_zoom_in": "zoompan=z='min(zoom+0.0008,1.3)':d={dur}:s=1920x1080:fps=24",
    "slow_zoom_out": "zoompan=z='if(eq(on,1),1.3,max(zoom-0.0008,1.0))':d={dur}:s=1920x1080:fps=24",
    "pan_left": "zoompan=z='1.1':x='iw/2-(iw/zoom/2)+on*2':y='ih/2-(ih/zoom/2)':d={dur}:s=1920x1080:fps=24",
    "pan_right": "zoompan=z='1.1':x='iw/2-(iw/zoom/2)-on*2':y='ih/2-(ih/zoom/2)':d={dur}:s=1920x1080:fps=24",
    "tilt_up": "zoompan=z='1.1':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)+on*2':d={dur}:s=1920x1080:fps=24",
    "tilt_down": "zoompan=z='1.1':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)-on*2':d={dur}:s=1920x1080:fps=24",
    "static": "zoompan=z='min(zoom+0.0003,1.05)':d={dur}:s=1920x1080:fps=24",
}

DEFAULT_CAMERA = "slow_zoom_in"


@dataclass
class VideoGenConfig:
    comfyui_host: str = "http://localhost:8188"
    ltx_model: str = "ltx-video-2.3.safetensors"
    fps: int = 24
    default_duration_sec: float = 6.0
    max_duration_sec: float = 10.0
    timeout_sec: int = 300
    poll_interval_sec: float = 2.0
    ken_burns_ffmpeg: str = "ffmpeg"


@dataclass
class VideoGenResult:
    success: bool
    video_path: Optional[str] = None
    method: str = "ltx"  # "ltx" | "ken_burns"
    duration_sec: float = 0.0
    generation_time_sec: float = 0.0
    error: Optional[str] = None


class VideoGenerator:
    """
    Generates video clips via ComfyUI LTX-2.3 image-to-video.
    Falls back to Ken Burns (FFmpeg zoompan) on failure.
    """

    def __init__(self, config: Optional[VideoGenConfig] = None):
        self.config = config or VideoGenConfig()
        self._session = requests.Session()

    # ─── Public API ────────────────────────────────────────

    def generate(
        self,
        image_path: str,
        output_dir: str,
        filename: str = "clip",
        camera_movement: str = DEFAULT_CAMERA,
        visual_prompt: str = "",
        duration_sec: Optional[float] = None,
        max_retries: int = 2,
    ) -> VideoGenResult:
        """
        Generate a video clip from a source image.

        Tries LTX-2.3 first; falls back to Ken Burns on failure.
        """
        dur = min(
            duration_sec or self.config.default_duration_sec,
            self.config.max_duration_sec,
        )
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        video_path = str(out_path / f"{filename}.mp4")

        # Attempt LTX
        for attempt in range(1, max_retries + 1):
            result = self._generate_ltx(
                image_path=image_path,
                video_path=video_path,
                camera_movement=camera_movement,
                visual_prompt=visual_prompt,
                duration_sec=dur,
            )
            if result.success:
                return result
            logger.warning(
                f"LTX attempt {attempt}/{max_retries} failed: {result.error}"
            )

        # Fallback: Ken Burns
        logger.info(f"Falling back to Ken Burns for {filename}")
        return self._generate_ken_burns(
            image_path=image_path,
            video_path=video_path,
            camera_movement=camera_movement,
            duration_sec=dur,
        )

    def generate_batch(
        self,
        scenes: list[dict],
        images_dir: str,
        output_dir: str,
    ) -> list[VideoGenResult]:
        """
        Generate video clips for all scenes.

        Each scene dict should have:
            scene_index, camera_movement, visual_prompt, duration_seconds, image_path
        """
        results = []
        total = len(scenes)
        for i, scene in enumerate(scenes):
            idx = scene.get("scene_index", i)
            img = scene.get("image_path") or str(
                Path(images_dir) / f"scene_{idx:03d}.png"
            )
            logger.info(f"Generating video {i + 1}/{total} (scene {idx})")

            result = self.generate(
                image_path=img,
                output_dir=output_dir,
                filename=f"scene_{idx:03d}",
                camera_movement=scene.get("camera_movement", DEFAULT_CAMERA),
                visual_prompt=scene.get("visual_prompt", ""),
                duration_sec=scene.get("duration_seconds"),
            )
            results.append(result)

        passed = sum(1 for r in results if r.success)
        logger.info(f"Video batch: {passed}/{total} clips generated")
        return results

    # ─── LTX Generation ────────────────────────────────────

    def _generate_ltx(
        self,
        image_path: str,
        video_path: str,
        camera_movement: str,
        visual_prompt: str,
        duration_sec: float,
    ) -> VideoGenResult:
        """Generate via ComfyUI LTX-2.3 image-to-video."""
        start = time.time()
        try:
            # Upload source image
            image_name = self._upload_image(image_path)

            # Build motion prompt
            motion_text = CAMERA_MOTION_MAP.get(
                camera_movement, CAMERA_MOTION_MAP[DEFAULT_CAMERA]
            )
            full_prompt = f"{visual_prompt}, {motion_text}".strip(", ")

            # Calculate frames
            num_frames = max(int(duration_sec * self.config.fps), 24)

            # Build workflow
            workflow = self._build_ltx_workflow(
                image_name=image_name,
                prompt=full_prompt,
                num_frames=num_frames,
            )

            prompt_id = self._queue_prompt(workflow)
            output = self._wait_for_completion(prompt_id)

            if not output:
                return VideoGenResult(
                    success=False, method="ltx",
                    error="No output from LTX generation",
                )

            # Download result
            self._download_video(output[0], video_path)

            elapsed = round(time.time() - start, 2)
            return VideoGenResult(
                success=True,
                video_path=video_path,
                method="ltx",
                duration_sec=duration_sec,
                generation_time_sec=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            return VideoGenResult(
                success=False, method="ltx",
                generation_time_sec=elapsed,
                error=str(e),
            )

    def _build_ltx_workflow(
        self, image_name: str, prompt: str, num_frames: int
    ) -> dict:
        """Build a minimal ComfyUI workflow for LTX image-to-video."""
        # This is a simplified workflow structure — actual node IDs
        # depend on your ComfyUI LTX workflow JSON. Adjust as needed.
        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": self.config.ltx_model},
            },
            "2": {
                "class_type": "LoadImage",
                "inputs": {"image": image_name},
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": prompt, "clip": ["1", 1]},
            },
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": "blurry, distorted, text, watermark",
                    "clip": ["1", 1],
                },
            },
            "5": {
                "class_type": "LTXVSampler",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["3", 0],
                    "negative": ["4", 0],
                    "image": ["2", 0],
                    "num_frames": num_frames,
                    "steps": 30,
                    "cfg": 3.0,
                    "seed": _random_seed(),
                },
            },
            "6": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
            },
            "7": {
                "class_type": "SaveAnimatedWEBP",
                "inputs": {
                    "filename_prefix": f"ltx_{uuid.uuid4().hex[:8]}",
                    "images": ["6", 0],
                    "fps": self.config.fps,
                },
            },
        }

    # ─── Ken Burns Fallback ────────────────────────────────

    def _generate_ken_burns(
        self,
        image_path: str,
        video_path: str,
        camera_movement: str,
        duration_sec: float,
    ) -> VideoGenResult:
        """Generate Ken Burns pan/zoom clip via FFmpeg."""
        start = time.time()
        try:
            total_frames = int(duration_sec * self.config.fps)
            preset_key = camera_movement if camera_movement in KEN_BURNS_PRESETS else "static"
            vf = KEN_BURNS_PRESETS[preset_key].format(dur=total_frames)

            cmd = [
                self.config.ken_burns_ffmpeg,
                "-y",
                "-loop", "1",
                "-i", image_path,
                "-vf", vf,
                "-t", str(duration_sec),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "medium",
                "-crf", "18",
                video_path,
            ]

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if proc.returncode != 0:
                return VideoGenResult(
                    success=False,
                    method="ken_burns",
                    error=f"FFmpeg error: {proc.stderr[:300]}",
                )

            elapsed = round(time.time() - start, 2)
            return VideoGenResult(
                success=True,
                video_path=video_path,
                method="ken_burns",
                duration_sec=duration_sec,
                generation_time_sec=elapsed,
            )

        except Exception as e:
            return VideoGenResult(
                success=False, method="ken_burns", error=str(e)
            )

    # ─── ComfyUI helpers ───────────────────────────────────

    def _upload_image(self, image_path: str) -> str:
        """Upload image to ComfyUI and return the server-side filename."""
        with open(image_path, "rb") as f:
            r = self._session.post(
                f"{self.config.comfyui_host}/upload/image",
                files={"image": (Path(image_path).name, f, "image/png")},
                timeout=30,
            )
        r.raise_for_status()
        return r.json()["name"]

    def _queue_prompt(self, workflow: dict) -> str:
        client_id = uuid.uuid4().hex
        r = self._session.post(
            f"{self.config.comfyui_host}/prompt",
            json={"prompt": workflow, "client_id": client_id},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["prompt_id"]

    def _wait_for_completion(self, prompt_id: str) -> list[dict]:
        deadline = time.time() + self.config.timeout_sec
        while time.time() < deadline:
            try:
                r = self._session.get(
                    f"{self.config.comfyui_host}/history/{prompt_id}",
                    timeout=10,
                )
                if r.status_code == 200:
                    data = r.json()
                    if prompt_id in data:
                        outputs = data[prompt_id].get("outputs", {})
                        for node_out in outputs.values():
                            # Animated formats or videos
                            for key in ("gifs", "images", "videos"):
                                items = node_out.get(key, [])
                                if items:
                                    return items
            except Exception:
                pass
            time.sleep(self.config.poll_interval_sec)
        raise TimeoutError(f"LTX generation timed out ({self.config.timeout_sec}s)")

    def _download_video(self, ref: dict, save_path: str):
        """Download generated video/animation from ComfyUI."""
        filename = ref["filename"]
        subfolder = ref.get("subfolder", "")
        file_type = ref.get("type", "output")

        r = self._session.get(
            f"{self.config.comfyui_host}/view",
            params={"filename": filename, "subfolder": subfolder, "type": file_type},
            timeout=60,
        )
        r.raise_for_status()

        tmp_path = save_path + ".tmp"
        with open(tmp_path, "wb") as f:
            f.write(r.content)

        # If WebP/GIF, convert to MP4
        if filename.endswith((".webp", ".gif")):
            self._convert_to_mp4(tmp_path, save_path)
            Path(tmp_path).unlink(missing_ok=True)
        else:
            shutil.move(tmp_path, save_path)

    def _convert_to_mp4(self, input_path: str, output_path: str):
        cmd = [
            self.config.ken_burns_ffmpeg,
            "-y", "-i", input_path,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-preset", "medium", "-crf", "18",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True, timeout=60, check=True)


def _random_seed() -> int:
    import random
    return random.randint(0, 2**32 - 1)
