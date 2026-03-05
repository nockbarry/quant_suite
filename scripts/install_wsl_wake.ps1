# Install Windows Task Scheduler task to wake WSL for Athena trading.
#
# Run from PowerShell (Admin):
#   powershell -ExecutionPolicy Bypass -File \\wsl$\Ubuntu\home\nock\projects\quant_suite\scripts\install_wsl_wake.ps1
#
# Or copy to Windows and run:
#   Right-click > Run with PowerShell

$taskName = "Athena WSL Wake"
$description = "Wake WSL for autonomous trading day (Project Athena)"

# Remove existing task if present
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# Action: start WSL and log
$action = New-ScheduledTaskAction `
    -Execute "wsl.exe" `
    -Argument "-d Ubuntu -e bash -c `"echo '[$(date)] WSL woken by Task Scheduler' >> ~/quant_results/logs/wsl_wake.log && systemctl is-active cron >> ~/quant_results/logs/wsl_wake.log 2>&1`""

# Trigger: 5:50 AM weekdays
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "5:50AM"

# Settings: wake computer, run whether logged in or not
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -WakeToRun `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

# Principal: run as current user
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Highest

# Register the task
Register-ScheduledTask `
    -TaskName $taskName `
    -Description $description `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal

Write-Host ""
Write-Host "Task '$taskName' installed successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Schedule: 5:50 AM Mon-Fri"
Write-Host "Action: Wake PC, start WSL, verify cron is running"
Write-Host "Wake: YES (will wake from sleep)"
Write-Host ""
Write-Host "Verify with: Get-ScheduledTask -TaskName '$taskName' | Format-List"
Write-Host "Test with:   Start-ScheduledTask -TaskName '$taskName'"
