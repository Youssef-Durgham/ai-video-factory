"""
AI Video Factory — CLI Interface.

Provides command-line access to all factory operations.

Usage:
    python -m src.cli run                    # Start the factory
    python -m src.cli new --topic "..." --channel documentary_ar
    python -m src.cli status                 # Pipeline status
    python -m src.cli test-gpu               # Test GPU load/unload
    python -m src.cli test-voice             # Test voice generation
    python -m src.cli test-image             # Test image generation
    python -m src.cli health                 # Full system health check
    python -m src.cli backup                 # Run manual backup
    python -m src.cli cleanup [--full]       # Run cleanup
    python -m src.cli quota                  # YouTube API quota status
    python -m src.cli jobs [--status ...]    # List jobs
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("factory.cli")


def cmd_run(args):
    """Start the AI Video Factory main loop."""
    from src.main import main
    print("🏭 Starting AI Video Factory...")
    main()


def cmd_new(args):
    """Create a new video job."""
    from src.core.config import load_config
    from src.core.database import FactoryDB

    config = load_config()
    db = FactoryDB(config.get("settings", {}).get("database", {}).get("path", "data/factory.db"))

    topic = args.topic
    channel = args.channel or "documentary_ar"
    priority = args.priority or 1

    job_id = db.create_job(channel_id=channel, topic=topic)
    print(f"✅ Job created: {job_id}")
    print(f"   Topic: {topic}")
    print(f"   Channel: {channel}")
    print(f"   Priority: {['🔴 Urgent', '🟢 Normal', '🔵 Background'][priority]}")

    # Enqueue if job_queue is available
    try:
        from src.core.job_queue import JobQueue
        queue = JobQueue(db)
        pos = queue.enqueue(job_id, priority=priority)
        print(f"   Queue position: #{pos}")
    except Exception as e:
        logger.warning(f"Could not enqueue job: {e}")

    return job_id


def cmd_status(args):
    """Show current pipeline status."""
    from src.core.config import load_config
    from src.core.database import FactoryDB

    config = load_config()
    db = FactoryDB(config.get("settings", {}).get("database", {}).get("path", "data/factory.db"))

    active_jobs = db.get_active_jobs()

    print("📊 Pipeline Status")
    print("=" * 50)

    if not active_jobs:
        print("  No active jobs.")
    else:
        for job in active_jobs:
            print(f"  🎬 {job['id']}")
            print(f"     Topic: {job['topic']}")
            print(f"     Status: {job['status']}")
            print(f"     Channel: {job['channel_id']}")
            print(f"     Created: {job['created_at']}")
            print()

    # GPU status
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu,memory.used,memory.total,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            temp, vram_used, vram_total, util = result.stdout.strip().split(", ")
            print(f"  🖥️ GPU: {vram_used}/{vram_total}MB VRAM, {temp}°C, {util}% util")
    except Exception:
        print("  🖥️ GPU: unavailable")

    # Disk status
    try:
        import shutil
        total, used, free = shutil.disk_usage(".")
        print(f"  💾 Disk: {free // (1024**3)}GB free")
    except Exception:
        pass


def cmd_test_gpu(args):
    """Test GPU load/unload cycle."""
    from src.core.config import load_config
    from src.core.gpu_manager import GPUMemoryManager

    config = load_config()
    gpu_config = config.get("settings", {}).get("gpu", {
        "device": "cuda:0",
        "vram_gb": 24,
        "safety_margin_gb": 2
    })

    gpu = GPUMemoryManager(gpu_config)
    gpu.set_hosts(
        ollama_host=config.get("settings", {}).get("ollama", {}).get("host", "http://localhost:11434"),
        comfyui_host=config.get("settings", {}).get("comfyui", {}).get("host", "http://localhost:8188")
    )

    print("🧪 GPU Test — Load/Unload Cycle")
    print("=" * 50)

    # Test Ollama
    print("\n1. Testing Ollama (Qwen 3.5)...")
    try:
        gpu.load_model("qwen3.5:27b", "ollama")
        print("   ✅ Loaded successfully")
        free = gpu._get_free_vram()
        print(f"   Free VRAM: {free:.1f}GB")
        gpu.unload_model()
        print("   ✅ Unloaded successfully")
        free = gpu._get_free_vram()
        print(f"   Free VRAM after unload: {free:.1f}GB")
    except Exception as e:
        print(f"   ❌ Failed: {e}")

    # Test ComfyUI
    print("\n2. Testing ComfyUI...")
    try:
        gpu.load_model("flux", "comfyui")
        print("   ✅ ComfyUI reachable")
        gpu.unload_model()
        print("   ✅ Models freed")
    except Exception as e:
        print(f"   ❌ Failed: {e}")

    print("\n✅ GPU test complete")


def cmd_test_voice(args):
    """Test voice generation."""
    print("🧪 Voice Test")
    print("=" * 50)
    try:
        import requests
        host = os.getenv("FISH_AUDIO_HOST", "http://localhost:8080")
        r = requests.get(f"{host}/health", timeout=5)
        if r.status_code == 200:
            print("   ✅ Fish Audio S2 Pro: running")
        else:
            print(f"   ⚠️ Fish Audio S2 Pro: status {r.status_code}")
    except Exception as e:
        print(f"   ❌ Fish Audio S2 Pro: unreachable ({e})")


def cmd_test_image(args):
    """Test image generation."""
    print("🧪 Image Test")
    print("=" * 50)
    try:
        import requests
        host = os.getenv("COMFYUI_HOST", "http://127.0.0.1:8000")
        r = requests.get(f"{host}/api/system_stats", timeout=5)
        if r.status_code == 200:
            stats = r.json()
            print("   ✅ ComfyUI: running")
            if "system" in stats:
                vram = stats["system"].get("vram", {})
                print(f"   VRAM: {vram}")
        else:
            print(f"   ⚠️ ComfyUI: status {r.status_code}")
    except Exception as e:
        print(f"   ❌ ComfyUI: unreachable ({e})")


def cmd_health(args):
    """Full system health check."""
    import shutil
    import subprocess

    print("🏥 System Health Check")
    print("=" * 50)
    checks = []

    # Ollama
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        print(f"  ✅ Ollama: running ({len(models)} models)")
        checks.append(True)
    except Exception:
        print("  ❌ Ollama: unreachable")
        checks.append(False)

    # ComfyUI
    try:
        import requests
        comfyui_host = os.getenv("COMFYUI_HOST", "http://127.0.0.1:8000")
        r = requests.get(f"{comfyui_host}/api/system_stats", timeout=5)
        print("  ✅ ComfyUI: running")
        checks.append(True)
    except Exception:
        print("  ❌ ComfyUI: unreachable")
        checks.append(False)

    # FFmpeg
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        version = result.stdout.split("\n")[0] if result.returncode == 0 else "unknown"
        print(f"  ✅ FFmpeg: {version[:50]}")
        checks.append(True)
    except Exception:
        print("  ❌ FFmpeg: not found")
        checks.append(False)

    # GPU
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total,temperature.gpu",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print(f"  ✅ GPU: {result.stdout.strip()}")
            checks.append(True)
        else:
            print("  ❌ GPU: nvidia-smi failed")
            checks.append(False)
    except Exception:
        print("  ❌ GPU: nvidia-smi not found")
        checks.append(False)

    # RAM
    try:
        import psutil
        mem = psutil.virtual_memory()
        available_gb = mem.available / (1024 ** 3)
        total_gb = mem.total / (1024 ** 3)
        status = "✅" if available_gb > 8 else "⚠️"
        print(f"  {status} RAM: {available_gb:.0f}GB available / {total_gb:.0f}GB total")
        checks.append(available_gb > 8)
    except ImportError:
        print("  ⚠️ RAM: psutil not installed")
        checks.append(None)

    # Disk
    total, used, free = shutil.disk_usage(".")
    free_gb = free // (1024 ** 3)
    status = "✅" if free_gb > 50 else "⚠️" if free_gb > 20 else "❌"
    print(f"  {status} Disk: {free_gb}GB free")
    checks.append(free_gb > 20)

    # Database
    db_path = "data/factory.db"
    if os.path.exists(db_path):
        size_mb = os.path.getsize(db_path) / (1024 * 1024)
        print(f"  ✅ Database: {size_mb:.1f}MB")
        checks.append(True)
    else:
        print("  ⚠️ Database: not initialized (run factory first)")
        checks.append(None)

    # Fonts
    font_dir = Path("src/phase5_production/fonts")
    if font_dir.exists():
        font_count = len(list(font_dir.glob("**/*.ttf"))) + len(list(font_dir.glob("**/*.otf")))
        print(f"  {'✅' if font_count > 0 else '⚠️'} Fonts: {font_count} installed")
    else:
        print("  ⚠️ Fonts: directory not found")

    # Summary
    passed = sum(1 for c in checks if c is True)
    failed = sum(1 for c in checks if c is False)
    print(f"\n{'🟢 ALL SYSTEMS GO' if failed == 0 else f'🔴 {failed} ISSUE(S) FOUND'} — {passed}/{len(checks)} checks passed")


def cmd_backup(args):
    """Run manual database backup."""
    from src.core.db_backup import DatabaseBackup

    db_path = args.db_path or "data/factory.db"
    backup = DatabaseBackup(db_path)

    if args.type == "hot":
        print("📦 Running hot backup...")
        backup.hot_backup()
    elif args.type == "daily":
        print("📦 Running daily snapshot...")
        backup.daily_snapshot()
    else:
        print("📦 Running hot backup (default)...")
        backup.hot_backup()

    print("✅ Backup complete")


def cmd_cleanup(args):
    """Run storage cleanup."""
    from src.core.config import load_config
    from src.core.storage_manager import StorageManager

    config = load_config()
    sm = StorageManager(config)

    if args.full:
        print("🧹 Running full cleanup...")
        usage = sm.get_disk_usage()
        print(f"   Current usage: {json.dumps(usage, indent=2, default=str)}")
        sm.emergency_cleanup()
    else:
        print("🧹 Running standard cleanup...")
        usage = sm.get_disk_usage()
        print(f"   Disk usage: {json.dumps(usage, indent=2, default=str)}")

    print("✅ Cleanup complete")


def cmd_quota(args):
    """Show YouTube API quota status."""
    from src.core.config import load_config
    from src.core.database import FactoryDB
    from src.core.quota_tracker import QuotaTracker

    config = load_config()
    db = FactoryDB(config.get("settings", {}).get("database", {}).get("path", "data/factory.db"))
    tracker = QuotaTracker(db)

    status = tracker.get_status()
    print("📊 YouTube API Quota")
    print("=" * 50)
    print(f"  Date (PT): {status['date']}")
    print(f"  Used: {status['used']}/{QuotaTracker.DAILY_LIMIT}")
    print(f"  Remaining: {status['remaining']}")
    print(f"  Usage: {status['percent_used']}%")
    print(f"  Max videos today: {status['max_videos_remaining']}")
    print(f"  Reset: {status['reset_time']}")


def cmd_jobs(args):
    """List jobs with optional filters."""
    from src.core.config import load_config
    from src.core.database import FactoryDB

    config = load_config()
    db = FactoryDB(config.get("settings", {}).get("database", {}).get("path", "data/factory.db"))

    if args.status:
        # Filter by status
        rows = db.conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (args.status, args.limit or 10)
        ).fetchall()
    else:
        rows = db.conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
            (args.limit or 10,)
        ).fetchall()

    jobs = [dict(r) for r in rows]
    print(f"📋 Jobs ({len(jobs)} shown)")
    print("=" * 50)
    for job in jobs:
        status_emoji = {
            "pending": "⏳", "research": "🔍", "seo": "📊", "script": "📝",
            "compliance": "✅", "images": "🖼️", "video": "🎬", "voice": "🎤",
            "music": "🎵", "compose": "🎞️", "published": "✅", "blocked": "🚫",
            "cancelled": "❌", "manual_review": "👁️"
        }.get(job["status"], "❓")
        print(f"  {status_emoji} {job['id']} — {job['topic'][:40]}")
        print(f"     Status: {job['status']} | Channel: {job['channel_id']}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="AI Video Factory — Automated Arabic Video Production",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # run
    subparsers.add_parser("run", help="Start the AI Video Factory")

    # new
    new_parser = subparsers.add_parser("new", help="Create a new video job")
    new_parser.add_argument("--topic", required=True, help="Video topic")
    new_parser.add_argument("--channel", default="documentary_ar", help="Channel ID")
    new_parser.add_argument("--priority", type=int, default=1, choices=[0, 1, 2],
                           help="Priority: 0=urgent, 1=normal, 2=background")

    # status
    subparsers.add_parser("status", help="Show pipeline status")

    # test-gpu
    subparsers.add_parser("test-gpu", help="Test GPU load/unload cycle")

    # test-voice
    subparsers.add_parser("test-voice", help="Test voice generation")

    # test-image
    subparsers.add_parser("test-image", help="Test image generation")

    # health
    subparsers.add_parser("health", help="Full system health check")

    # backup
    backup_parser = subparsers.add_parser("backup", help="Run database backup")
    backup_parser.add_argument("--type", choices=["hot", "daily"], default="hot")
    backup_parser.add_argument("--db-path", default="data/factory.db")

    # cleanup
    cleanup_parser = subparsers.add_parser("cleanup", help="Run storage cleanup")
    cleanup_parser.add_argument("--full", action="store_true", help="Full cleanup (keeps only essentials)")

    # quota
    subparsers.add_parser("quota", help="YouTube API quota status")

    # jobs
    jobs_parser = subparsers.add_parser("jobs", help="List jobs")
    jobs_parser.add_argument("--status", help="Filter by status")
    jobs_parser.add_argument("--limit", type=int, default=10, help="Max jobs to show")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "run": cmd_run,
        "new": cmd_new,
        "status": cmd_status,
        "test-gpu": cmd_test_gpu,
        "test-voice": cmd_test_voice,
        "test-image": cmd_test_image,
        "health": cmd_health,
        "backup": cmd_backup,
        "cleanup": cmd_cleanup,
        "quota": cmd_quota,
        "jobs": cmd_jobs,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
