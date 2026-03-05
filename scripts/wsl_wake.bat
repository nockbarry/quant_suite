@echo off
REM Wake WSL for Athena autonomous trading day.
REM
REM Schedule this in Windows Task Scheduler:
REM   Trigger: Daily at 5:50 AM (Mon-Fri)
REM   Action: Run this script
REM   Settings: "Wake the computer to run this task" = checked
REM             "Run whether user is logged on or not" = checked
REM
REM To install:
REM   1. Open Task Scheduler (taskschd.msc)
REM   2. Create Task (not Basic Task)
REM   3. General: "Athena WSL Wake", Run whether user is logged on or not
REM   4. Triggers: New > Daily 5:50 AM, repeat M-F only
REM   5. Actions: Start a program > Browse to this .bat file
REM   6. Conditions: Check "Wake the computer to run this task"
REM   7. Settings: Allow task to be run on demand

echo [%date% %time%] Waking WSL for Athena trading day...

REM Start WSL (this launches systemd which starts cron)
wsl -d Ubuntu -e bash -c "echo 'WSL started at $(date)' >> ~/quant_results/logs/wsl_wake.log"

REM Give cron a moment to start
timeout /t 5 /nobreak > nul

REM Verify cron is running
wsl -d Ubuntu -e bash -c "systemctl is-active cron >> ~/quant_results/logs/wsl_wake.log 2>&1"

echo [%date% %time%] WSL wake complete
