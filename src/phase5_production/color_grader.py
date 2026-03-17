"""
Phase 5 — Color Grader.

Ensures visual consistency across all scene images via:
  1. LUT-based cinematic color grading
  2. Reinhard color transfer for inter-scene consistency
"""

import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# LUT MAPPING (matches font_category from FontAnimationConfig)
# ════════════════════════════════════════════════════════════════

LUT_MAP: dict[str, str] = {
    "formal_news":   "documentary_neutral.cube",
    "dramatic":      "dramatic_teal_orange.cube",
    "historical":    "historical_sepia_warm.cube",
    "modern_tech":   "tech_cyberpunk.cube",
    "islamic":       "islamic_warm_gold.cube",
    "military":      "military_cold_steel.cube",
    "editorial":     "editorial_clean.cube",
    "storytelling":  "storytelling_warm.cube",
}

DEFAULT_LUT = "documentary_neutral.cube"


@dataclass
class ColorGradeConfig:
    luts_dir: str = "src/phase5_production/luts"
    reinhard_strength: float = 0.7  # 0=no transfer, 1=full transfer
    preserve_luminance: bool = True


@dataclass
class ColorGradeResult:
    success: bool
    graded_path: Optional[str] = None
    lut_applied: Optional[str] = None
    error: Optional[str] = None


class ColorGrader:
    """
    Applies cinematic color grading + inter-scene consistency.

    Pipeline:
    1. Apply mood-appropriate LUT to each image
    2. Reinhard-normalize all images to a "hero image"
    """

    def __init__(self, config: Optional[ColorGradeConfig] = None):
        self.config = config or ColorGradeConfig()

    # ─── Public API ────────────────────────────────────────

    def grade_image(
        self,
        image_path: str,
        output_path: str,
        font_category: str = "editorial",
        lut_override: Optional[str] = None,
    ) -> ColorGradeResult:
        """
        Apply LUT color grading to a single image.
        """
        try:
            import numpy as np
            from PIL import Image

            lut_name = lut_override or LUT_MAP.get(font_category, DEFAULT_LUT)
            lut_path = Path(self.config.luts_dir) / lut_name

            img = Image.open(image_path).convert("RGB")
            img_array = np.array(img, dtype=np.float32) / 255.0

            if lut_path.exists():
                lut = self._load_cube_lut(str(lut_path))
                img_array = self._apply_lut(img_array, lut)
                logger.debug(f"Applied LUT: {lut_name}")
            else:
                logger.warning(f"LUT not found: {lut_path}, skipping LUT application")
                lut_name = None

            # Clip and save
            img_array = np.clip(img_array * 255, 0, 255).astype(np.uint8)
            Image.fromarray(img_array).save(output_path, quality=95)

            return ColorGradeResult(
                success=True, graded_path=output_path, lut_applied=lut_name,
            )

        except Exception as e:
            logger.error(f"Color grading failed: {e}")
            return ColorGradeResult(success=False, error=str(e))

    def grade_all_images(
        self,
        image_paths: list[str],
        output_dir: str,
        font_category: str = "editorial",
        hero_index: Optional[int] = None,
    ) -> list[ColorGradeResult]:
        """
        Grade all scene images with LUT + Reinhard normalization.

        Args:
            image_paths: Ordered list of scene image paths.
            output_dir: Directory for graded outputs.
            font_category: Determines which LUT to use.
            hero_index: Index of the "hero" image for Reinhard reference.
                        If None, uses the first image.
        """
        import numpy as np
        from PIL import Image

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        results = []
        graded_arrays = []

        # Step 1: Apply LUT to all images
        for i, img_path in enumerate(image_paths):
            stem = Path(img_path).stem
            out_path = str(out_dir / f"{stem}_graded.png")

            result = self.grade_image(
                image_path=img_path,
                output_path=out_path,
                font_category=font_category,
            )
            results.append(result)

            if result.success:
                graded_arrays.append(
                    np.array(Image.open(out_path).convert("RGB"), dtype=np.float32)
                )
            else:
                graded_arrays.append(None)

        # Step 2: Reinhard color transfer to hero image
        if self.config.reinhard_strength > 0 and len(graded_arrays) > 1:
            hero_idx = hero_index if hero_index is not None else 0
            hero = graded_arrays[hero_idx]
            if hero is not None:
                hero_stats = self._compute_lab_stats(hero)

                for i, (arr, result) in enumerate(zip(graded_arrays, results)):
                    if arr is None or i == hero_idx:
                        continue
                    try:
                        normalized = self._reinhard_transfer(
                            arr, hero_stats, self.config.reinhard_strength
                        )
                        out_path = result.graded_path
                        Image.fromarray(
                            np.clip(normalized, 0, 255).astype(np.uint8)
                        ).save(out_path, quality=95)
                        logger.debug(f"Reinhard normalized image {i} to hero")
                    except Exception as e:
                        logger.warning(f"Reinhard transfer failed for image {i}: {e}")

        passed = sum(1 for r in results if r.success)
        logger.info(
            f"Color grading: {passed}/{len(image_paths)} images graded "
            f"(LUT={font_category})"
        )
        return results

    def grade_thumbnail(
        self, thumbnail_path: str, output_path: str, font_category: str = "editorial"
    ) -> ColorGradeResult:
        """Apply same color grade to thumbnail for brand consistency."""
        return self.grade_image(
            image_path=thumbnail_path,
            output_path=output_path,
            font_category=font_category,
        )

    # ─── LUT Loading & Application ─────────────────────────

    def _load_cube_lut(self, lut_path: str) -> dict:
        """
        Parse a .cube LUT file.
        Returns dict with 'size' and 'table' (flattened 3D array).
        """
        import numpy as np

        size = 0
        table = []

        with open(lut_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("LUT_3D_SIZE"):
                    size = int(line.split()[-1])
                elif line.startswith(("TITLE", "DOMAIN_MIN", "DOMAIN_MAX")):
                    continue
                else:
                    try:
                        r, g, b = map(float, line.split())
                        table.append([r, g, b])
                    except ValueError:
                        continue

        if size == 0:
            size = round(len(table) ** (1.0 / 3.0))

        return {
            "size": size,
            "table": np.array(table, dtype=np.float32).reshape(size, size, size, 3),
        }

    def _apply_lut(self, img: "np.ndarray", lut: dict) -> "np.ndarray":
        """
        Apply 3D LUT to an image using trilinear interpolation.

        img: float32 array (H, W, 3), range [0, 1]
        """
        import numpy as np

        size = lut["size"]
        table = lut["table"]

        # Scale to LUT index space
        scaled = img * (size - 1)
        floor = np.floor(scaled).astype(int)
        floor = np.clip(floor, 0, size - 2)
        frac = scaled - floor

        # Trilinear interpolation
        r, g, b = floor[..., 0], floor[..., 1], floor[..., 2]
        fr, fg, fb = frac[..., 0:1], frac[..., 1:2], frac[..., 2:3]

        c000 = table[r, g, b]
        c001 = table[r, g, b + 1]
        c010 = table[r, g + 1, b]
        c011 = table[r, g + 1, b + 1]
        c100 = table[r + 1, g, b]
        c101 = table[r + 1, g, b + 1]
        c110 = table[r + 1, g + 1, b]
        c111 = table[r + 1, g + 1, b + 1]

        c00 = c000 * (1 - fb) + c001 * fb
        c01 = c010 * (1 - fb) + c011 * fb
        c10 = c100 * (1 - fb) + c101 * fb
        c11 = c110 * (1 - fb) + c111 * fb

        c0 = c00 * (1 - fg) + c01 * fg
        c1 = c10 * (1 - fg) + c11 * fg

        result = c0 * (1 - fr) + c1 * fr
        return np.clip(result, 0, 1)

    # ─── Reinhard Color Transfer ───────────────────────────

    def _compute_lab_stats(self, img_rgb: "np.ndarray") -> dict:
        """Compute mean and std in LAB color space."""
        import numpy as np

        lab = self._rgb_to_lab(img_rgb / 255.0)
        return {
            "mean": np.mean(lab, axis=(0, 1)),
            "std": np.std(lab, axis=(0, 1)) + 1e-6,
        }

    def _reinhard_transfer(
        self, img_rgb: "np.ndarray", target_stats: dict, strength: float
    ) -> "np.ndarray":
        """
        Reinhard color transfer: match mean/std in LAB space.

        Args:
            img_rgb: Source image (float32, 0-255 range).
            target_stats: LAB stats from hero image.
            strength: Blend factor (0=no change, 1=full transfer).
        """
        import numpy as np

        lab = self._rgb_to_lab(img_rgb / 255.0)
        src_mean = np.mean(lab, axis=(0, 1))
        src_std = np.std(lab, axis=(0, 1)) + 1e-6

        # Transfer
        transferred = (lab - src_mean) * (target_stats["std"] / src_std) + target_stats["mean"]

        # Blend with original
        blended = lab * (1 - strength) + transferred * strength

        rgb = self._lab_to_rgb(blended) * 255.0
        return rgb

    def _rgb_to_lab(self, img: "np.ndarray") -> "np.ndarray":
        """Convert RGB [0,1] to CIELAB."""
        import numpy as np

        # sRGB → linear
        linear = np.where(img > 0.04045, ((img + 0.055) / 1.055) ** 2.4, img / 12.92)

        # Linear RGB → XYZ (D65)
        mat = np.array([
            [0.4124564, 0.3575761, 0.1804375],
            [0.2126729, 0.7151522, 0.0721750],
            [0.0193339, 0.1191920, 0.9503041],
        ])
        xyz = linear @ mat.T

        # XYZ → LAB
        ref = np.array([0.95047, 1.0, 1.08883])
        xyz_n = xyz / ref

        def f(t):
            delta = 6.0 / 29.0
            return np.where(t > delta**3, t ** (1.0 / 3.0), t / (3 * delta**2) + 4.0 / 29.0)

        fx, fy, fz = f(xyz_n[..., 0]), f(xyz_n[..., 1]), f(xyz_n[..., 2])

        L = 116.0 * fy - 16.0
        a = 500.0 * (fx - fy)
        b = 200.0 * (fy - fz)

        return np.stack([L, a, b], axis=-1)

    def _lab_to_rgb(self, lab: "np.ndarray") -> "np.ndarray":
        """Convert CIELAB to RGB [0,1]."""
        import numpy as np

        L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]

        fy = (L + 16.0) / 116.0
        fx = a / 500.0 + fy
        fz = fy - b / 200.0

        delta = 6.0 / 29.0

        def f_inv(t):
            return np.where(t > delta, t**3, 3 * delta**2 * (t - 4.0 / 29.0))

        ref = np.array([0.95047, 1.0, 1.08883])
        x = f_inv(fx) * ref[0]
        y = f_inv(fy) * ref[1]
        z = f_inv(fz) * ref[2]

        xyz = np.stack([x, y, z], axis=-1)

        # XYZ → linear RGB
        mat_inv = np.array([
            [ 3.2404542, -1.5371385, -0.4985314],
            [-0.9692660,  1.8760108,  0.0415560],
            [ 0.0556434, -0.2040259,  1.0572252],
        ])
        linear = xyz @ mat_inv.T

        # Linear → sRGB
        rgb = np.where(
            linear > 0.0031308,
            1.055 * np.power(np.clip(linear, 0, None), 1.0 / 2.4) - 0.055,
            12.92 * linear,
        )

        return np.clip(rgb, 0, 1)
