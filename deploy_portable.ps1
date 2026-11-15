$ErrorActionPreference = "Stop"
$root = "C:\Users\Thinkpad\tulip-factures"
$dist = Join-Path $root "dist38\TulipFactures"
$dest = "F:\zjob\TulipFactures-exe"

if (-not (Test-Path (Join-Path $dist "TulipFactures.exe"))) { throw "Build absent : $dist" }

Write-Host "Arret de l'application en cours..."
$procs = Get-Process -Name "TulipFactures" -ErrorAction SilentlyContinue
foreach ($p in $procs) { Stop-Process -Id $p.Id -Force; Write-Host "  arret PID $($p.Id)" }
Start-Sleep -Seconds 3

Write-Host "Copie du nouvel executable vers $dest ..."
robocopy $dist $dest /E /NFL /NDL /NJH /NJS /XF "*.log" | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Echec robocopy exe (code $LASTEXITCODE)" }

Write-Host "Copie des fichiers web (build a jour)..."
robocopy (Join-Path $root "backend\app\static") (Join-Path $dest "backend\app\static") /MIR /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Echec robocopy static (code $LASTEXITCODE)" }

Write-Host "Redemarrage..."
Start-Process -FilePath (Join-Path $dest "TulipFactures.exe") -WorkingDirectory $dest
Start-Sleep -Seconds 12
try {
  $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 10
  Write-Host "OK health: version $($health.version)"
} catch {
  Write-Host "ATTENTION: /api/health ne repond pas encore : $($_.Exception.Message)"
}
