# Athena Trading System — Windows Task Scheduler Setup
# Run this in PowerShell as Administrator:
#   powershell -ExecutionPolicy Bypass -File \\wsl.localhost\Ubuntu\home\nock\projects\quant_suite\scripts\setup_windows_tasks.ps1

$wslCommand = "wsl -d Ubuntu -- echo alive"

# Wake WSL 2 minutes before each critical cron window
$tasks = @(
    @{ Name="Athena-Wake-PreMarket";  Time="05:53"; Days="Monday,Tuesday,Wednesday,Thursday,Friday"; Desc="Wake WSL for 5:55AM sentinel + 6:30AM briefing" },
    @{ Name="Athena-Wake-Sunday";     Time="16:55"; Days="Sunday"; Desc="Wake WSL for Sunday hypothesis-gen, thesis, brainstorm, theorist (5-8PM)" }
)

foreach ($task in $tasks) {
    $action = New-ScheduledTaskAction -Execute "wsl.exe" -Argument "-d Ubuntu -- echo athena-wake $(Get-Date -Format 'yyyy-MM-dd HH:mm') >> /home/nock/quant_results/logs/wsl_wake.log"
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $task.Days.Split(",") -At $task.Time
    $settings = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    
    # Remove existing task if present
    Unregister-ScheduledTask -TaskName $task.Name -Confirm:$false -ErrorAction SilentlyContinue
    
    Register-ScheduledTask -TaskName $task.Name -Action $action -Trigger $trigger -Settings $settings -Description $task.Desc
    Write-Host "Created task: $($task.Name) at $($task.Time) on $($task.Days)"
}

Write-Host "`nDone. Tasks will wake WSL before critical trading automations."
Write-Host "Verify with: Get-ScheduledTask -TaskName 'Athena-*' | Format-Table TaskName,State"
