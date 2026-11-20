# Run once as admin. TrendCollector then runs 2 min after every boot (logged in or not, S4U: no password stored),
# and every 24h after that while the PC stays on. Repeat runs are safe: writes are idempotent, Google requests rotate.
$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.Delay = 'PT2M'  # give the network time to come up
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Days 1)).Repetition
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited
Set-ScheduledTask -TaskName TrendCollector -Trigger $trigger -Principal $principal | Out-Null
$task = Get-ScheduledTask TrendCollector
$task.Triggers | Select-Object @{n='Trigger';e={$_.CimClass.CimClassName}}, Delay, @{n='Repeat';e={$_.Repetition.Interval}}
$task.Principal | Select-Object UserId, LogonType
