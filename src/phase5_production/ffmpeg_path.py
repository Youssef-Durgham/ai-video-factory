"""Shared ffmpeg path resolver — use FFMPEG from this module everywhere."""
import shutil
from pathlib import Path

def _find_ffmpeg() -> str:
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass
    for p in [Path(r"C:\ffmpeg\bin\ffmpeg.exe"), Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe")]:
        if p.exists():
            return str(p)
    return "ffmpeg"

FFMPEG = _find_ffmpeg()
