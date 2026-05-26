# start.ps1 — Start Django dev server + Celery worker in separate windows
# Usage: .\start.ps1 [-Port 8080]

param(
    [int]$Port = 8080
)

$root   = $PSScriptRoot
$python = "$root\.venv\Scripts\python.exe"
$celery = "$root\.venv\Scripts\celery.exe"

# ── Redis (via Docker) ────────────────────────────────────────────────────────
Write-Host "Ensuring Redis is running ..." -ForegroundColor Cyan
$redisRunning = docker ps --filter "name=redis-dev" --filter "status=running" -q
if ($redisRunning) {
    Write-Host "  Redis already running." -ForegroundColor Green
} else {
    $redisStopped = docker ps -a --filter "name=redis-dev" -q
    if ($redisStopped) {
        docker start redis-dev | Out-Null
        Write-Host "  Redis container restarted." -ForegroundColor Green
    } else {
        docker run -d --name redis-dev -p 6379:6379 redis:alpine | Out-Null
        Write-Host "  Redis container created and started." -ForegroundColor Green
    }
}

# ── Django ────────────────────────────────────────────────────────────────────
Write-Host "Starting Django on http://127.0.0.1:$Port ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList `
    "-NoExit", "-Command", `
    "cd '$root'; & '$python' manage.py runserver $Port" `
    -WindowStyle Normal

# ── Celery worker ─────────────────────────────────────────────────────────────
# --pool=solo avoids Windows PermissionError with billiard shared semaphores
Write-Host "Starting Celery worker (queues: seo_checks) ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList `
    "-NoExit", "-Command", `
    "cd '$root'; & '$celery' -A config worker -Q seo_checks -l info --pool=solo" `
    -WindowStyle Normal

Write-Host ""
Write-Host "All services started." -ForegroundColor Green
Write-Host "  App  → http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "  Stop → .\stop.ps1" -ForegroundColor Yellow
