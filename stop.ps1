# stop.ps1 — Kill Django dev server and Celery worker processes
# Usage: .\stop.ps1

Write-Host "Stopping Django dev server ..." -ForegroundColor Yellow
Get-Process -Name "python" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*manage.py runserver*" } |
    Stop-Process -Force -ErrorAction SilentlyContinue

# Fallback: kill any python process running manage.py (works when CommandLine is unavailable)
Get-WmiObject Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*manage.py*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Host "Stopping Celery worker ..." -ForegroundColor Yellow
Get-WmiObject Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*celery*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# Also catch the celery.exe launcher if it spawned separately
Get-Process -Name "celery" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

Write-Host "All services stopped." -ForegroundColor Green
