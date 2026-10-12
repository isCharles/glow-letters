param([ValidateSet('Install','Uninstall')][string]$Mode = 'Install', [string]$ExePath)
$ErrorActionPreference = 'Stop'
$taskNames = @('GlowLetters-Sunset', 'GlowLetters-Sunrise')
if ($Mode -eq 'Uninstall') {
    foreach ($name in $taskNames) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    }
    exit 0
}
if (-not (Test-Path -LiteralPath $ExePath)) { throw 'GlowLetters.exe was not found' }
$definitions = @(
    @{Name='GlowLetters-Sunset'; Time='15:00'; Event='today-sunset'},
    @{Name='GlowLetters-Sunrise'; Time='21:00'; Event='tomorrow-sunrise'}
)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -StartWhenAvailable
foreach ($item in $definitions) {
    $action = New-ScheduledTaskAction -Execute $ExePath -Argument "--notify --event $($item.Event)"
    $trigger = New-ScheduledTaskTrigger -Daily -At $item.Time
    Register-ScheduledTask -TaskName $item.Name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
}
