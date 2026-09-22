<#
.SYNOPSIS
    Start, stop and inspect the bot process on this machine.

.DESCRIPTION
    The bot cannot start itself, so process control lives outside it.
    On a real server this job belongs to systemd; this script is its
    equivalent for a development machine.

    Pass -Test to drive the second instance from `.env.test` (#52) —
    its own token, database, logs and lock, so it can sit next to the
    regular bot. Never put the production BOT_TOKEN into `.env.test`.

.EXAMPLE
    .\manage.ps1 start
    .\manage.ps1 start -Test
    .\manage.ps1 start -Test -Web
    .\manage.ps1 web-stop
    .\manage.ps1 status
    .\manage.ps1 logs -Lines 50
    .\manage.ps1 dashboard -RefreshSeconds 5
    .\manage.ps1 watch -Test
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'restart', 'status', 'logs', 'menu', 'dashboard', 'web-stop', 'watch')]
    [string]$Command = 'status',

    [int]$Lines = 20,

    [int]$RefreshSeconds = 5,

    # Second bot from `.env.test` — own DB, logs, pid file, BOT_ENV_FILE.
    [switch]$Test,

    # Start Vite + Cloudflare tunnel (untun), inject MINI_APP_URL into the bot.
    [switch]$Web
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$LogDir = Join-Path $Root 'logs'
$WebappDir = Join-Path $Root 'webapp'
$TunnelUrlFile = Join-Path $Root 'data\mini-app-tunnel.url'
$WebPidFile = Join-Path $Root 'data\webapp.pid'
$WebLogFile = Join-Path $LogDir 'webapp.log'
$WebErrFile = Join-Path $LogDir 'webapp.err.log'

if ($Test) {
    $InstanceLabel = 'test bot'
    $EnvFile = Join-Path $Root '.env.test'
    $EnvFileName = '.env.test'
    $LogFile = Join-Path $LogDir 'bot.test.log'
    $ErrFile = Join-Path $LogDir 'bot.test.err.log'
    $PrevLogFile = Join-Path $LogDir 'bot.test.prev.log'
    $PidFile = Join-Path $Root 'data\bot.test.pid'
    $SiblingPidFile = Join-Path $Root 'data\bot.pid'
    $DefaultPort = 8081
    $DefaultDbPath = 'data/test.db'
} else {
    $InstanceLabel = 'bot'
    $EnvFile = Join-Path $Root '.env'
    $EnvFileName = '.env'
    $LogFile = Join-Path $LogDir 'bot.log'
    $ErrFile = Join-Path $LogDir 'bot.err.log'
    $PrevLogFile = Join-Path $LogDir 'bot.prev.log'
    $PidFile = Join-Path $Root 'data\bot.pid'
    $SiblingPidFile = Join-Path $Root 'data\bot.test.pid'
    $DefaultPort = 8080
    $DefaultDbPath = 'data/bot.db'
}

function Get-EnvFileValue {
    param([string]$Path, [string]$Key, [string]$Default)
    if (-not (Test-Path $Path)) { return $Default }
    $line = Get-Content $Path -ErrorAction SilentlyContinue |
        Where-Object { $_ -match ("^\s*{0}\s*=" -f [regex]::Escape($Key)) } |
        Select-Object -First 1
    if (-not $line) { return $Default }
    $value = ($line -split '=', 2)[1].Trim()
    # Drop an inline "# comment" that isn't inside quotes.
    if ($value -match '^([^#"''\s][^#]*?)\s+#') { $value = $Matches[1].Trim() }
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value
}

$Port = [int](Get-EnvFileValue -Path $EnvFile -Key 'OAUTH_LISTEN_PORT' -Default "$DefaultPort")
$DbRelPath = Get-EnvFileValue -Path $EnvFile -Key 'DB_PATH' -Default $DefaultDbPath
$DbPath = if ([System.IO.Path]::IsPathRooted($DbRelPath)) { $DbRelPath } else { Join-Path $Root $DbRelPath }

function Get-BotProcess {
    # Trust the PID file only after confirming the process is still ours:
    # PIDs get reused, and killing a stranger would be worse than not stopping.
    param([string]$Path = $PidFile)
    if (-not (Test-Path $Path)) { return $null }
    $recorded = (Get-Content $Path -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $recorded) { return $null }

    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$recorded" -ErrorAction SilentlyContinue
    if (-not $process) { return $null }
    if ($process.CommandLine -notmatch 'bot\.main') { return $null }
    return $process
}

function Get-BotTree {
    # One launch is two processes on Windows: .venv\Scripts\python.exe starts
    # the base interpreter as a child. Both must count as "ours", or the child
    # looks like a second bot and owns the port we think is free.
    param($Process)
    if (-not $Process) { return @() }
    $ids = @($Process.ProcessId)
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($Process.ProcessId)" -ErrorAction SilentlyContinue
    foreach ($child in $children) { $ids += $child.ProcessId }
    return $ids
}

function Test-ViteListening {
    $conn = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
    return [bool]$conn
}

function Get-TunnelUrl {
    if (-not (Test-Path $TunnelUrlFile)) { return $null }
    $url = (Get-Content $TunnelUrlFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    if ([string]::IsNullOrWhiteSpace($url)) { return $null }
    return $url
}

function Get-WebProcess {
    if (-not (Test-Path $WebPidFile)) { return $null }
    $recorded = (Get-Content $WebPidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $recorded) { return $null }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$recorded" -ErrorAction SilentlyContinue
    if (-not $process) { return $null }
    return $process
}

function Stop-Web {
    $process = Get-WebProcess
    if ($process) {
        # Kill the node tree (vite child included).
        foreach ($id in (Get-BotTree $process)) {
            Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
        }
        Write-Host ("Stopped web/tunnel, PID {0}." -f $process.ProcessId) -ForegroundColor Green
    } else {
        Write-Host 'Web/tunnel not running.' -ForegroundColor Yellow
    }
    Remove-Item $WebPidFile, $TunnelUrlFile -ErrorAction SilentlyContinue
}

function Start-Web {
    if (Get-WebProcess) {
        $existing = Get-TunnelUrl
        if ($existing) {
            Write-Host "Web/tunnel already running: $existing" -ForegroundColor Yellow
            return $existing
        }
        Write-Host 'Web PID exists but no tunnel URL yet — waiting…' -ForegroundColor Yellow
    } else {
        if (-not (Test-Path (Join-Path $WebappDir 'package.json'))) {
            throw "Missing webapp/. Run from the repo root after scaffolding the Mini App."
        }
        $viteBin = Join-Path $WebappDir 'node_modules\vite\package.json'
        if (-not (Test-Path $viteBin)) {
            # First-time or clean checkout — install deps once.
            Write-Host 'Installing webapp npm deps…' -ForegroundColor Cyan
            & npm.cmd install --prefix $WebappDir
            if ($LASTEXITCODE -ne 0) { throw 'npm install failed in webapp/' }
        }

        New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $WebPidFile) | Out-Null
        if (Test-Path $WebLogFile) {
            Move-Item $WebLogFile (Join-Path $LogDir 'webapp.prev.log') -Force
        }

        # node runs scripts/dev-tunnel.mjs which writes its own pid + tunnel URL.
        $node = (Get-Command node -ErrorAction Stop).Source
        $script = Join-Path $WebappDir 'scripts\dev-tunnel.mjs'
        $proc = Start-Process -FilePath $node -ArgumentList $script `
            -WorkingDirectory $WebappDir -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $WebLogFile -RedirectStandardError $WebErrFile
        # Temporary marker until the script overwrites with its own pid.
        $proc.Id | Set-Content $WebPidFile -Encoding ascii
        Write-Host "Starting Vite + Cloudflare tunnel (PID $($proc.Id))…" -ForegroundColor Cyan
    }

    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        $url = Get-TunnelUrl
        if ($url) {
            Write-Host "Tunnel ready: $url" -ForegroundColor Green
            return $url
        }
        $alive = Get-WebProcess
        if (-not $alive -and -not (Get-TunnelUrl)) {
            Write-Host 'Web/tunnel process exited. Last errors:' -ForegroundColor Red
            if (Test-Path $WebErrFile) { Get-Content $WebErrFile -Tail 20 }
            if (Test-Path $WebLogFile) { Get-Content $WebLogFile -Tail 20 }
            throw 'Failed to start web/tunnel'
        }
        Start-Sleep -Seconds 2
    }
    throw 'Timed out waiting for tunnel URL (cloudflared download can be slow the first time).'
}

function Start-Bot {
    if (Get-BotProcess) { Write-Host "Already running ($InstanceLabel)." -ForegroundColor Yellow; return }
    if (-not (Test-Path $Python)) { throw "Missing venv: $Python. Create it with: python -m venv .venv" }
    if (-not (Test-Path $EnvFile)) { throw "Missing $EnvFileName in the project root." }

    $miniUrl = $null
    if ($Web) {
        if (-not $Test) {
            throw '-Web is only supported with -Test (do not tunnel the production bot from a home PC).'
        }
        $miniUrl = Start-Web
    } elseif ($Test) {
        $miniUrl = Get-TunnelUrl
    }

    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $PidFile) | Out-Null
    # Keep the previous run readable: Start-Process truncates its target.
    if (Test-Path $LogFile) { Move-Item $LogFile $PrevLogFile -Force }

    # Child inherits the process environment; BOT_ENV_FILE is how Settings
    # picks `.env.test` over `.env` (bot/config.py). Restore afterwards so a
    # later status call in this same shell isn't left pointing at the wrong file.
    $previousEnvFile = $env:BOT_ENV_FILE
    $previousMini = $env:MINI_APP_URL
    $previousOauth = $env:OAUTH_REDIRECT_URL
    # Ambient process env overrides values from BOT_ENV_FILE in pydantic-
    # settings. A leftover BOT_TOKEN from another shell would make Mini App
    # initData fail with "bad hash" against the test bot's signatures.
    $clearedSecrets = @{}
    foreach ($name in @('BOT_TOKEN', 'FERNET_KEY', 'AZURE_CLIENT_SECRET', 'STEAM_API_KEY', 'ANTHROPIC_API_KEY')) {
        $clearedSecrets[$name] = Get-Item -Path "Env:$name" -ErrorAction SilentlyContinue
        Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
    }
    $env:BOT_ENV_FILE = $EnvFileName
    if ($miniUrl) {
        # Process env wins over .env for pydantic-settings — tunnel URL changes
        # every run, so we never bake it into .env.test permanently.
        $env:MINI_APP_URL = $miniUrl
        # Xbox OAuth needs a public HTTPS callback. Vite proxies /auth → :8081,
        # so the same Cloudflare origin works; Azure must list this URI too.
        $env:OAUTH_REDIRECT_URL = ($miniUrl.TrimEnd('/') + '/auth/callback')
    }
    try {
        $process = Start-Process -FilePath $Python -ArgumentList '-u', '-m', 'bot.main' `
            -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $LogFile -RedirectStandardError $ErrFile
    } finally {
        if ($null -eq $previousEnvFile) {
            Remove-Item Env:BOT_ENV_FILE -ErrorAction SilentlyContinue
        } else {
            $env:BOT_ENV_FILE = $previousEnvFile
        }
        if ($null -eq $previousMini) {
            Remove-Item Env:MINI_APP_URL -ErrorAction SilentlyContinue
        } else {
            $env:MINI_APP_URL = $previousMini
        }
        if ($null -eq $previousOauth) {
            Remove-Item Env:OAUTH_REDIRECT_URL -ErrorAction SilentlyContinue
        } else {
            $env:OAUTH_REDIRECT_URL = $previousOauth
        }
        foreach ($name in $clearedSecrets.Keys) {
            $item = $clearedSecrets[$name]
            if ($null -ne $item) {
                Set-Item -Path "Env:$name" -Value $item.Value
            }
        }
    }
    $process.Id | Set-Content $PidFile -Encoding ascii

    $logRel = if ($Test) { 'logs\bot.test.log' } else { 'logs\bot.log' }
    Start-Sleep -Seconds 3
    if (Get-BotProcess) {
        Write-Host ("Started ($InstanceLabel), PID {0}. Logs: {1}" -f $process.Id, $logRel) -ForegroundColor Green
        if ($miniUrl) {
            Write-Host ("  Mini App: {0}" -f $miniUrl) -ForegroundColor Cyan
            Write-Host ("  OAuth:    {0}/auth/callback" -f $miniUrl.TrimEnd('/')) -ForegroundColor Cyan
            if (-not (Test-ViteListening)) {
                Write-Host '  Vite :5173: not listening — tunnel is stale. Start with -Test -Web.' -ForegroundColor Yellow
            }
        }
    } else {
        Write-Host 'Process exited. Last error lines:' -ForegroundColor Red
        if (Test-Path $ErrFile) { Get-Content $ErrFile -Tail 15 }
        Remove-Item $PidFile -ErrorAction SilentlyContinue
    }
}

function Stop-Bot {
    $process = Get-BotProcess
    if (-not $process) { Write-Host "Not running ($InstanceLabel)." -ForegroundColor Yellow; return }
    foreach ($id in (Get-BotTree $process)) {
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $PidFile -ErrorAction SilentlyContinue
    Write-Host ("Stopped ($InstanceLabel), PID {0}." -f $process.ProcessId) -ForegroundColor Green
    if ($Web) { Stop-Web }
}

function Watch-Bot {
    Write-Host ("Watching 'bot/' for changes ({0})..." -f $InstanceLabel) -ForegroundColor Cyan
    Write-Host "Press Ctrl+C to stop watching." -ForegroundColor DarkGray
    if (-not (Get-BotProcess)) {
        Start-Bot
    }

    $botDir = Join-Path $Root 'bot'
    $watcher = New-Object System.IO.FileSystemWatcher
    $watcher.Path = $botDir
    $watcher.IncludeSubdirectories = $true
    $watcher.EnableRaisingEvents = $true
    $watcher.NotifyFilter = [System.IO.NotifyFilters]'FileName, LastWrite'

    $lastRestart = [DateTime]::MinValue
    $debounceMs = 1500

    try {
        while ($true) {
            $change = $watcher.WaitForChanged([System.IO.WatcherChangeTypes]::All, 1000)
            if (-not $change.TimedOut) {
                $ext = [System.IO.Path]::GetExtension($change.Name).ToLower()
                if ($ext -in @('.py', '.ftl', '.sql')) {
                    $now = [DateTime]::UtcNow
                    if (($now - $lastRestart).TotalMilliseconds -gt $debounceMs) {
                        $lastRestart = $now
                        Write-Host ("[watch] Change in {0} -> restarting {1}..." -f $change.Name, $InstanceLabel) -ForegroundColor Yellow
                        Stop-Bot
                        Start-Sleep -Milliseconds 500
                        Start-Bot
                    }
                }
            }
        }
    } finally {
        $watcher.Dispose()
    }
}

function Write-StatusBlock {
    # Shared by `status` (one shot) and `dashboard` (redrawn every tick), so
    # the two never drift into showing different things for the same state.
    $process = Get-BotProcess
    if ($process) {
        $started = $process.CreationDate
        $uptime = (Get-Date) - $started
        Write-Host "Running ($InstanceLabel)" -ForegroundColor Green
        Write-Host ("  PID:      {0}" -f $process.ProcessId)
        Write-Host ("  started:  {0:HH:mm:ss}, uptime {1:hh\:mm\:ss}" -f $started, $uptime)
        Write-Host ("  env:      {0}" -f $EnvFileName)
        $tunnel = Get-TunnelUrl
        if ($tunnel) {
            Write-Host ("  mini:     {0}" -f $tunnel)
            if (Test-ViteListening) {
                Write-Host '  vite:     :5173 listening'
            } else {
                Write-Host '  vite:     :5173 not listening (stale tunnel file; start with -Test -Web)' -ForegroundColor Yellow
            }
        }
    } else {
        Write-Host "Not running ($InstanceLabel)" -ForegroundColor Red
    }

    $web = Get-WebProcess
    if ($web) {
        Write-Host ("  web/tunnel PID: {0}" -f $web.ProcessId) -ForegroundColor DarkGray
    }

    $tree = @(Get-BotTree $process)
    # The other managed instance (main <-> test) is expected to coexist —
    # different tokens, different DB. Don't flag it as a token conflict.
    $sibling = Get-BotProcess -Path $SiblingPidFile
    $known = $tree + @(Get-BotTree $sibling)

    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        $mine = if ($tree -contains $listener.OwningProcess) { ', ours' } else { ', FOREIGN' }
        Write-Host ("  port {0}: listening (PID {1}{2})" -f $Port, $listener.OwningProcess, $mine)
    } else {
        Write-Host ("  port {0}: free" -f $Port)
    }

    # A second bot with the same token would fight this one for Telegram updates.
    $others = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match 'bot\.main' -and $known -notcontains $_.ProcessId })
    if ($others.Count -gt 0) {
        Write-Host ("  WARNING: other bot processes: {0}" -f
            ($others.ProcessId -join ', ')) -ForegroundColor Yellow
        Write-Host '  Two bots on one token fight over Telegram updates.' -ForegroundColor Yellow
    }

    if (Test-Path $Python) {
        Write-Host ''
        # -X utf8: keep console output readable under a non-UTF-8 code page.
        & $Python -X utf8 (Join-Path $Root 'scripts\db_status.py') $DbPath
    }
}

function Show-Status {
    Write-StatusBlock
    if (Test-Path $LogFile) {
        Write-Host ''
        Write-Host 'Recent log lines:' -ForegroundColor Cyan
        Get-Content $LogFile -Tail 5
    }
}

function Test-HotkeyPressed {
    # Reading the console can throw when there isn't one — piped output,
    # a non-interactive host. Dashboard mode degrades to a plain auto-refresh
    # in that case instead of crashing.
    try { return [Console]::KeyAvailable } catch { return $false }
}

function Show-Dashboard {
    # Clear-Host + full redraw, not cursor-position tricks: the flicker is a
    # non-issue at a multi-second cadence, and Clear-Host behaves the same in
    # cmd, PowerShell and every terminal host, which cursor repositioning does
    # not. CIM/port queries alone cost tens of milliseconds each — enough that
    # polling them many times a second would be wasteful for no visible gain.
    $tickMs = 200
    $title = if ($Test) { 'Xbox Achievement Bot (test)' } else { 'Xbox Achievement Bot' }
    try { [Console]::CursorVisible = $false } catch {}
    try {
        while ($true) {
            Clear-Host
            Write-Host ("=== {0} ===" -f $title) -ForegroundColor Cyan
            Write-Host (Get-Date -Format 'HH:mm:ss') -ForegroundColor DarkGray
            Write-Host ''
            Write-StatusBlock
            Write-Host ''
            Write-Host '[2] Start   [3] Stop   [4] Restart   [W] Watch   [Q] Quit' -ForegroundColor Cyan
            Write-Host ("Refresh every {0}s." -f $RefreshSeconds) -ForegroundColor DarkGray

            if (Test-Path $LogFile) {
                Write-Host ''
                Write-Host '--- Recent log lines ---' -ForegroundColor Cyan
                Get-Content $LogFile -Tail 12
            }

            $elapsedMs = 0
            $acted = $false
            while ($elapsedMs -lt ($RefreshSeconds * 1000) -and -not $acted) {
                if (Test-HotkeyPressed) {
                    $key = [Console]::ReadKey($true)
                    switch ($key.KeyChar) {
                        '2' { Write-Host ''; Start-Bot; $acted = $true }
                        '3' { Write-Host ''; Stop-Bot; $acted = $true }
                        '4' { Write-Host ''; Stop-Bot; Start-Sleep -Seconds 1; Start-Bot; $acted = $true }
                        'w' { Write-Host ''; Watch-Bot; $acted = $true }
                        'W' { Write-Host ''; Watch-Bot; $acted = $true }
                        'q' { return }
                        'Q' { return }
                        default {}
                    }
                }
                Start-Sleep -Milliseconds $tickMs
                $elapsedMs += $tickMs
            }
            # Let the operator read what the action itself printed before the
            # next redraw wipes it.
            if ($acted) { Start-Sleep -Seconds 2 }
        }
    } finally {
        try { [Console]::CursorVisible = $true } catch {}
    }
}

switch ($Command) {
    'menu'      { Show-Dashboard }
    'dashboard' { Show-Dashboard }
    'start'     { Start-Bot }
    'stop'      { Stop-Bot; if ($Web) { Stop-Web } }
    'restart'   { Stop-Bot; if ($Web) { Stop-Web }; Start-Sleep -Seconds 1; Start-Bot }
    'web-stop'  { Stop-Web }
    'status'    { Show-Status }
    'watch'     { Watch-Bot }
    'logs'      {
        if (-not (Test-Path $LogFile)) { Write-Host 'No logs yet.'; break }
        Get-Content $LogFile -Tail $Lines
        if ((Test-Path $ErrFile) -and (Get-Item $ErrFile).Length -gt 0) {
            Write-Host ''
            Write-Host ("Errors ({0}):" -f (Split-Path -Leaf $ErrFile)) -ForegroundColor Red
            Get-Content $ErrFile -Tail $Lines
        }
    }
}
