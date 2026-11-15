param([switch]$Elevated)

$ErrorActionPreference = "Stop"
$ruleName = "Tulip Factures (LAN)"

$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existing) { exit 0 }

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)

if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    if ($Elevated) { exit 1 }
    $argumentList = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Elevated"
    Start-Process powershell.exe -Verb RunAs -ArgumentList $argumentList -WindowStyle Hidden
    exit 0
}

New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Any -RemoteAddress LocalSubnet | Out-Null
exit 0
