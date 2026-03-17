"""
Phase 5: Production Engine.

Sub-pipeline with three coordinators:
  • AssetCoordinator  — Images + Video (visual assets)
  • AudioCoordinator  — Voice + Music + SFX (audio assets)
  • VideoComposer     — FFmpeg assembly (final composition)

Plus supporting modules:
  • ImageGenerator, ImagePromptEnhancer
  • VideoGenerator
  • VoiceGenerator
  • MusicGenerator
  • SFXGenerator
  • ContentIDGuard
  • ColorGrader
  • TextAnimationRenderer
"""

from .image_gen import ImageGenerator, ImageGenConfig, ImageGenResult
from .image_prompt import enhance_prompt, enhance_scenes
from .video_gen import VideoGenerator, VideoGenConfig, VideoGenResult
from .voice_gen import VoiceGenerator, VoiceGenConfig, VoiceGenResult
from .music_gen import MusicGenerator, MusicGenConfig, MusicGenResult
from .sfx_gen import SFXGenerator, SFXGenConfig, SFXGenResult
from .content_id_guard import ContentIDGuard, ContentIDConfig, ContentIDResult
from .color_grader import ColorGrader, ColorGradeConfig, ColorGradeResult
from .text_animator import (
    TextAnimationRenderer,
    ArabicTextRenderer,
    TextOverlayConfig,
    AnimationStyle,
)
from .composer import VideoComposer, ComposerConfig, ComposerResult
from .asset_coordinator import AssetCoordinator, AssetCoordinatorConfig
from .audio_coordinator import AudioCoordinator, AudioCoordinatorConfig
from .video_composer import VideoComposerCoordinator, VideoComposerCoordinatorConfig
from .voice_clone import VoiceCloner, VoiceCloneConfig, VoiceCloneResult
from .voice_selector import VoiceSelector, VoiceProfile
from .font_selector import FontSelector, FontAnimationConfig
from .upscaler import Upscaler, UpscalerConfig, UpscaleResult

__all__ = [
    # Image
    "ImageGenerator", "ImageGenConfig", "ImageGenResult",
    "enhance_prompt", "enhance_scenes",
    # Video
    "VideoGenerator", "VideoGenConfig", "VideoGenResult",
    # Voice
    "VoiceGenerator", "VoiceGenConfig", "VoiceGenResult",
    # Music
    "MusicGenerator", "MusicGenConfig", "MusicGenResult",
    # SFX
    "SFXGenerator", "SFXGenConfig", "SFXGenResult",
    # Content ID
    "ContentIDGuard", "ContentIDConfig", "ContentIDResult",
    # Color Grading
    "ColorGrader", "ColorGradeConfig", "ColorGradeResult",
    # Text Animation
    "TextAnimationRenderer", "ArabicTextRenderer",
    "TextOverlayConfig", "AnimationStyle",
    # Composer
    "VideoComposer", "ComposerConfig", "ComposerResult",
    # Coordinators
    "AssetCoordinator", "AssetCoordinatorConfig",
    "AudioCoordinator", "AudioCoordinatorConfig",
    "VideoComposerCoordinator", "VideoComposerCoordinatorConfig",
    # Voice Cloning
    "VoiceCloner", "VoiceCloneConfig", "VoiceCloneResult",
    # Voice Selection
    "VoiceSelector", "VoiceProfile",
    # Font Selection
    "FontSelector", "FontAnimationConfig",
    # Upscaling
    "Upscaler", "UpscalerConfig", "UpscaleResult",
]
