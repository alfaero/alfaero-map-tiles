# Registra a tarefa agendada das cartas raster dos EUA (spec 008).
# Roda todo dia as 06:40 com o usuario logado (o Docker Desktop precisa da sessao); se o PC estava
# desligado no horario, roda assim que ligar. Uma rodada por vez; a geracao leva umas 6 h.
#
# Uso: powershell -ExecutionPolicy Bypass -File register_task.ps1
#      powershell -ExecutionPolicy Bypass -File register_task.ps1 -Remove
param([switch]$Remove)

$Name = "Alfaero cartas EUA"
if ($Remove) {
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false
    return
}

$Python = (Get-Command python).Source
$Script = Join-Path $PSScriptRoot "auto_edition.py"
$Action = New-ScheduledTaskAction -Execute $Python -Argument "-I `"$Script`" run" -WorkingDirectory $env:LOCALAPPDATA
$Trigger = New-ScheduledTaskTrigger -Daily -At "06:40"
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 20) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal `
    -Description "Gera e publica as cartas raster dos EUA a cada edicao da FAA (alfaero-map-tiles/scripts/us-charts, spec 008)" -Force
