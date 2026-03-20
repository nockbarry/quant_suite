# Athena Trading System — Windows Task Scheduler Setup
# Run this in PowerShell as Administrator:
#   powershell -ExecutionPolicy Bypass -File \\wsl.localhost\Ubuntu\home\nock\projects\quant_suite\scripts\setup_windows_tasks.ps1

$wslCommand = "wsl -d Ubuntu -- echo alive"

# Wake WSL before each critical cron window
# 5:50 AM: Wakes WSL so the 5:55 AM sentinel start and 6:00 AM data collection run
# 5:53 AM: Kept for backward compat (sentinel starts at 5:55)
$tasks = @(
    @{ Name="Athena-Wake-WSL-Early";  Time="05:50"; Days="Monday,Tuesday,Wednesday,Thursday,Friday"; Desc="Wake WSL 5 min before sentinel start (5:55 AM) to ensure cron is running" },
    @{ Name="Athena-Wake-PreMarket";  Time="05:53"; Days="Monday,Tuesday,Wednesday,Thursday,Friday"; Desc="Wake WSL for 5:55AM sentinel + 6:30AM briefing" },
    @{ Name="Athena-Wake-Sunday";     Time="16:55"; Days="Sunday"; Desc="Wake WSL for Sunday hypothesis-gen, thesis, brainstorm, theorist (5-8PM)" }
)

foreach ($task in $tasks) {
    $action = New-ScheduledTaskAction -Execute "wsl.exe" -Argument "-d Ubuntu -- bash -c 'echo athena-wake $(date +%Y-%m-%d_%H:%M) >> /home/nock/quant_results/logs/wsl_wake.log 2>&1'"
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $task.Days.Split(",") -At $task.Time
    $settings = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

    # Remove existing task if present
    Unregister-ScheduledTask -TaskName $task.Name -Confirm:$false -ErrorAction SilentlyContinue

    Register-ScheduledTask -TaskName $task.Name -Action $action -Trigger $trigger -Settings $settings -Description $task.Desc
    Write-Host "Created task: $($task.Name) at $($task.Time) on $($task.Days)"
}

Write-Host "`nDone. Tasks will wake WSL before critical trading automations."
Write-Host "Verify with: Get-ScheduledTask -TaskName 'Athena-*' | Format-Table TaskName,State"
