# AI Video Factory — Smart auto-start (single instance only)
$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"
$dir = "C:\Users\3d\clawd\ai-video-factory"
$pidFile = "$dir\data\bot.pid"
$lockFile = "$dir\data\bot.lock"

# Check if another instance is already running
if (Test-Path $pidFile) {
    $oldPid = Get-Content $pidFile -ErrorAction SilentlyContinue
    $proc = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
    if ($proc -and $proc.ProcessName -eq "python") {
        Add-Content "$dir\logs\bot-service.log" "$(Get-Date -Format 'HH:mm:ss') Already running (PID $oldPid) - exiting"
        exit 0
    }
}

# Lock file to prevent race conditions
if (Test-Path $lockFile) {
    $lockAge = ((Get-Date) - (Get-Item $lockFile).LastWriteTime).TotalSeconds
    if ($lockAge -lt 60) {
        Add-Content "$dir\logs\bot-service.log" "$(Get-Date -Format 'HH:mm:ss') Lock file exists (${lockAge}s old) - exiting"
        exit 0
    }
}
"locked" | Set-Content $lockFile

New-Item -ItemType Directory -Force -Path "$dir\logs" | Out-Null

function Stop-OldBot {
    if (Test-Path $pidFile) {
        $p = Get-Content $pidFile -ErrorAction SilentlyContinue
        if ($p) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}

function Start-NewBot {
    # Wait for Telegram to release old polling session
    Add-Content "$dir\logs\bot-service.log" "$(Get-Date -Format 'HH:mm:ss') Waiting 10s for clean start..."
    Start-Sleep 10
    $proc = Start-Process python -ArgumentList "-m","src.main" -WorkingDirectory $dir -PassThru -NoNewWindow -RedirectStandardOutput "$dir\logs\stdout.log" -RedirectStandardError "$dir\logs\stderr.log"
    $proc.Id | Set-Content $pidFile
    Add-Content "$dir\logs\bot-service.log" "$(Get-Date -Format 'HH:mm:ss') Started PID $($proc.Id)"
    return $proc
}

Stop-OldBot
$bot = Start-NewBot

# File watcher for auto-restart on code changes
$w = New-Object System.IO.FileSystemWatcher
$w.Path = "$dir\src"
$w.Filter = "*.py"
$w.IncludeSubdirectories = $true
$last = Get-Date

while ($true) {
    # Crash recovery
    if ($bot.HasExited) {
        Add-Content "$dir\logs\bot-service.log" "$(Get-Date -Format 'HH:mm:ss') Crashed (exit $($bot.ExitCode)) - restarting in 30s"
        Start-Sleep 30
        $bot = Start-NewBot
        $last = Get-Date
    }

    # Watch for code changes (debounce 15s)
    $w.EnableRaisingEvents = $true
    $ch = $w.WaitForChanged(6, 5000)
    $w.EnableRaisingEvents = $false
    if (-not $ch.TimedOut) {
        if (((Get-Date) - $last).TotalSeconds -gt 15) {
            Add-Content "$dir\logs\bot-service.log" "$(Get-Date -Format 'HH:mm:ss') Code changed: $($ch.Name) - restarting in 10s"
            Stop-OldBot
            Start-Sleep 10
            $bot = Start-NewBot
            $last = Get-Date
        }
    }
}
