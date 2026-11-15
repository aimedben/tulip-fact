@echo off
chcp 1252 >nul
title Configuration Tulip Factures
if /i "%~1"=="selftest" set "TULIP_SELFTEST=1"
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { $bp='%~f0'; $bt=[IO.File]::ReadAllText($bp); $bm='#===PS'+'-START==='; $bi=$bt.IndexOf($bm); if($bi -lt 0){Write-Host 'ERREUR: marqueur introuvable'; exit 1}; $global:TULIP_APP=(Split-Path -Parent $bp); Invoke-Expression $bt.Substring($bi+$bm.Length) }"
echo.
pause
exit /b
#===PS-START===
# =====================================================================
#  CONFIGURATION AUTOMATIQUE DE TULIPFACTURES
#  Lit le registre Tulip, trouve la base .TFE sur le serveur,
#  teste la connexion, puis ecrit le fichier .env.
#  Compatible Windows 7 (PowerShell 2.0) a Windows 11.
# =====================================================================

$ErrorActionPreference = 'Continue'

$appDir  = $global:TULIP_APP
$envPath = Join-Path $appDir '.env'
$outPath = Join-Path $appDir 'CONNEXION-TULIP.txt'

# --- localisation de isql.exe (l arborescence varie selon le conditionnement)
$isqlList = @(
    (Join-Path $appDir 'firebird\bin\isql.exe'),
    (Join-Path $appDir 'vendor\firebird\bin\isql.exe'),
    (Join-Path $appDir '_internal\firebird\bin\isql.exe'),
    (Join-Path $appDir 'firebird\isql.exe'),
    (Join-Path $appDir 'isql.exe')
)
$isql = ''
foreach ($c in $isqlList) { if (Test-Path $c) { $isql = $c; break } }
if ($isql -eq '' -and (Test-Path $envPath)) {
    foreach ($l in (Get-Content $envPath)) {
        if ($l -match '^\s*TULIP_FB_ISQL_PATH\s*=\s*(.+)$') {
            $cand = $Matches[1].Trim()
            if (Test-Path $cand) { $isql = $cand }
        }
    }
}
if ($isql -eq '') { $isql = $isqlList[0] }
$isqlDir = Split-Path -Parent $isql
if ((Split-Path -Leaf $isqlDir) -eq 'bin') { $fbHome = Split-Path -Parent $isqlDir } else { $fbHome = $isqlDir }

$log = New-Object System.Text.StringBuilder

function Log([string]$s) {
    [void]$log.AppendLine($s)
    Write-Host $s
}

function Finish([string]$titre, [string]$message) {
    Log ''
    Log '================================================='
    Log $titre
    Log '================================================='
    Log $message
    Log ''
    Log ('Rapport enregistre dans : ' + $outPath)
    try { [IO.File]::WriteAllText($outPath, $log.ToString(), [Text.Encoding]::ASCII) } catch { }
    Start-Process -FilePath 'notepad.exe' -ArgumentList ('"' + $outPath + '"')
    exit
}

# ---------------------------------------------------------------- parsing
function Get-Targets([string]$pth, [string]$dossier) {
    $res = New-Object System.Collections.ArrayList
    $p = $pth.Trim()
    if ($p -eq '') { return $res }
    if ($p -match '^\\\\') {
        $t = $p.TrimStart('\').TrimEnd('\')
        $parts = $t.Split('\')
        if ($parts.Length -lt 2) { return $res }
        $srv   = $parts[0]
        $share = $parts[1]
        $sub   = ''
        if ($parts.Length -gt 2) {
            $sub = [string]::Join('\', $parts, 2, ($parts.Length - 2))
        }
        $sub = $sub.Trim('\')
        if ($share -match '^[A-Za-z]$') {
            $base = $share + ':\'
            if ($sub -ne '') { $base = $base + $sub + '\' }
            [void]$res.Add(@{ Server = $srv; Path = ($base + $dossier + '.TFE') })
            [void]$res.Add(@{ Server = $srv; Path = ($base + $dossier + '.FDB') })
            [void]$res.Add(@{ Server = $srv; Path = ($share + ':\' + $dossier + '.TFE') })
            [void]$res.Add(@{ Server = $srv; Path = ($share + ':\Gestion\' + $dossier + '.TFE') })
            [void]$res.Add(@{ Server = $srv; Path = ($share + ':\Tulip\' + $dossier + '.TFE') })
        }
        $unc = '\\' + $srv + '\' + $share
        if ($sub -ne '') { $unc = $unc + '\' + $sub }
        [void]$res.Add(@{ Server = $srv; Path = ($unc + '\' + $dossier + '.TFE') })
    } else {
        $base = $p.TrimEnd('\')
        if ($base -match '\.(tfe|fdb|gdb)$') {
            [void]$res.Add(@{ Server = 'localhost'; Path = $base })
        } else {
            [void]$res.Add(@{ Server = 'localhost'; Path = ($base + '\' + $dossier + '.TFE') })
            [void]$res.Add(@{ Server = 'localhost'; Path = ($base + '\' + $dossier + '.FDB') })
        }
    }
    return $res
}

function Resolve-Host([string]$name) {
    if ($name -eq '' -or $name -eq 'localhost') { return 'localhost' }
    try {
        $ips = [System.Net.Dns]::GetHostAddresses($name)
        foreach ($ip in $ips) {
            if ($ip.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork) { return $ip.ToString() }
        }
    } catch { }
    return $name
}

# ------------------------------------------------------------ test de base
function Test-Db([string]$hostName, [string]$db, [string]$user, [string]$pass) {
    $sqlFile = Join-Path $env:TEMP 'tulip_probe.sql'
    $q = "set list on;`r`nselect count(*) as nb_be from be;`r`nselect max(opdate) as dernier_bon from be;`r`n"
    try { [IO.File]::WriteAllText($sqlFile, $q, [Text.Encoding]::ASCII) } catch { }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $isql
    $psi.Arguments = '-user ' + $user + ' -password ' + $pass + ' "' + $hostName + '/3050:' + $db + '" -i "' + $sqlFile + '"'
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $pr = [System.Diagnostics.Process]::Start($psi)
    if (-not $pr.WaitForExit(25000)) {
        try { $pr.Kill() } catch { }
        return @{ Ok = $false; Raw = 'TIMEOUT'; Nb = ''; Date = '' }
    }
    $raw = $pr.StandardOutput.ReadToEnd() + "`n" + $pr.StandardError.ReadToEnd()
    $nb = ''
    $dt = ''
    foreach ($line in $raw.Split("`n")) {
        $s = $line.Trim()
        if ($s -match '^NB_BE\s+(.+)$') { $nb = $Matches[1].Trim() }
        if ($s -match '^DERNIER_BON\s+(.+)$') { $dt = $Matches[1].Trim() }
    }
    return @{ Ok = ($nb -ne ''); Raw = $raw; Nb = $nb; Date = $dt }
}

# --------------------------------------------------------- lecture registre
function Get-RegVal([string]$hive, [string]$path, [string]$name) {
    try {
        if ($hive -eq 'HKCU') { $root = [Microsoft.Win32.Registry]::CurrentUser } else { $root = [Microsoft.Win32.Registry]::LocalMachine }
        $k = $root.OpenSubKey($path)
        if ($k -ne $null) {
            $v = $k.GetValue($name)
            $k.Close()
            if ($v -ne $null) {
                $sv = ([string]$v).Trim()
                if ($sv -ne '') { return $sv }
            }
        }
    } catch { }
    return ''
}

function Find-TulipReg([string]$name) {
    $paths = @('Software\TH\TFZ', 'Software\Wow6432Node\TH\TFZ', 'Software\TH', 'Software\Wow6432Node\TH')
    foreach ($h in @('HKCU', 'HKLM')) {
        foreach ($pth in $paths) {
            $v = Get-RegVal $h $pth $name
            if ($v -ne '') { return $v }
            try {
                if ($h -eq 'HKCU') { $root = [Microsoft.Win32.Registry]::CurrentUser } else { $root = [Microsoft.Win32.Registry]::LocalMachine }
                $k = $root.OpenSubKey($pth)
                if ($k -ne $null) {
                    foreach ($sk in $k.GetSubKeyNames()) {
                        $v2 = Get-RegVal $h ($pth + '\' + $sk) $name
                        if ($v2 -ne '') { $k.Close(); return $v2 }
                        $k2 = $k.OpenSubKey($sk)
                        if ($k2 -ne $null) {
                            foreach ($sk2 in $k2.GetSubKeyNames()) {
                                $v3 = Get-RegVal $h ($pth + '\' + $sk + '\' + $sk2) $name
                                if ($v3 -ne '') { $k2.Close(); $k.Close(); return $v3 }
                            }
                            $k2.Close()
                        }
                    }
                    $k.Close()
                }
            } catch { }
        }
    }
    return ''
}

# ------------------------------------------------------------------ .env
function Set-EnvKey([string[]]$src, [string]$key, [string]$val) {
    $res = New-Object System.Collections.ArrayList
    $done = $false
    foreach ($l in $src) {
        if ($l -match ('^\s*' + [regex]::Escape($key) + '\s*=')) {
            if (-not $done) { [void]$res.Add($key + '=' + $val); $done = $true }
        } else {
            [void]$res.Add($l)
        }
    }
    if (-not $done) { [void]$res.Add($key + '=' + $val) }
    return $res.ToArray()
}

# =====================================================================
#  MODE AUTOTEST (pour verifier le fichier sans client)
# =====================================================================
if ($env:TULIP_SELFTEST -eq '1') {
    $cases = @(
        @('\\THINKCENTER-PC\D\Gestion\', 'SUPERETTE'),
        @('\\SRV\E\Tulip\Bases\',        'CLIENT1'),
        @('\\SRV\Partage\',              'MAISON'),
        @('\\PC\C\Tulip\',               'BASE'),
        @('C:\Tulip\',                   'LOCAL')
    )
    Write-Host '=== AUTOTEST DE LECTURE DES CHEMINS ==='
    Write-Host ('Dossier application : ' + $appDir)
    Write-Host ('isql attendu        : ' + $isql)
    Write-Host ('isql present        : ' + (Test-Path $isql))
    foreach ($c in $cases) {
        Write-Host ''
        Write-Host ('Pth=' + $c[0] + '   Dossier=' + $c[1])
        $r = Get-Targets $c[0] $c[1]
        foreach ($x in $r) { Write-Host ('    ' + $x.Server + '  ->  ' + $x.Path) }
    }
    Write-Host ''
    Write-Host 'FIN AUTOTEST'
    exit
}

# =====================================================================
#  DEBUT
# =====================================================================
Log '================================================='
Log '   CONFIGURATION AUTOMATIQUE - TULIPFACTURES'
Log ('   Date : ' + (Get-Date -Format 'dd/MM/yyyy HH:mm:ss'))
Log '================================================='
Log ''

Log '[0] DOSSIER DE L APPLICATION'
Log ('    ' + $appDir)
if (-not (Test-Path (Join-Path $appDir 'TulipFactures.exe'))) {
    Log '    ATTENTION : TulipFactures.exe n a pas ete trouve dans ce dossier.'
}
if (-not (Test-Path $isql)) {
    Finish '*** ECHEC ***' ('isql.exe est introuvable.' + "`r`n" + "`r`n" + 'Emplacements testes :' + "`r`n" + ($isqlList -join "`r`n") + "`r`n" + "`r`n" + 'Ce fichier doit etre place DANS le dossier de TulipFactures,' + "`r`n" + 'a cote de TulipFactures.exe.')
}
Log ''

# --- identifiants deja presents
$fbUser = 'SYSDBA'
$fbPass = 'masterkey'
if (Test-Path $envPath) {
    foreach ($l in (Get-Content $envPath)) {
        if ($l -match '^\s*TULIP_FB_USER\s*=\s*(.+)$')     { $fbUser = $Matches[1].Trim() }
        if ($l -match '^\s*TULIP_FB_PASSWORD\s*=\s*(.+)$') { $fbPass = $Matches[1].Trim() }
    }
}

# --- registre
Log '[1] LECTURE DU REGISTRE TULIP (TH\TFZ)'
$regPth = Find-TulipReg 'Pth'
$regDos = Find-TulipReg 'Dossier'
if ($regPth -ne '') { Log ('    Pth     = ' + $regPth) } else { Log '    Pth     = (non trouve)' }
if ($regDos -ne '') { Log ('    Dossier = ' + $regDos) } else { Log '    Dossier = (non trouve)' }
Log ''

$found  = $null
$cands  = New-Object System.Collections.ArrayList

if ($regPth -ne '' -and $regDos -ne '') {
    $all = Get-Targets $regPth $regDos
    $seen = @{}
    foreach ($c in $all) {
        $k = ($c.Server + '|' + $c.Path).ToLower()
        if (-not $seen.ContainsKey($k)) { $seen[$k] = $true; [void]$cands.Add($c) }
    }
}

if ($cands.Count -eq 0) {
    Log '[2] RECHERCHE AUTOMATIQUE IMPOSSIBLE'
    Log '    La cle de registre Tulip n a pas ete trouvee sur ce PC.'
    Log '    (Elle existe seulement sur le PC ou Tulip GC est configure.)'
} else {
    Log ('[2] TEST DE ' + $cands.Count + ' CHEMIN(S) POSSIBLE(S)')
    Log ''
    $authFail = $false
    $tour = 0
    while ($null -eq $found -and $tour -lt 2) {
        $authFail = $false
        foreach ($c in $cands) {
            $h = Resolve-Host $c.Server
            Log ('    essai : ' + $c.Server + ' (' + $h + ')')
            Log ('            ' + $c.Path)
            $r = Test-Db $h $c.Path $fbUser $fbPass
            if ($r.Ok) {
                $found = @{ Host = $h; Server = $c.Server; Path = $c.Path; Nb = $r.Nb; Date = $r.Date }
                break
            }
            if ($r.Raw -match 'TIMEOUT') { Log '            -> pas de reponse (25 s)' }
            elseif ($r.Raw -match 'not defined|user name and password|Your user name') {
                Log '            -> mot de passe refuse'
                $authFail = $true
            }
            elseif ($r.Raw -match 'introuvable|not found|cannot open') { Log '            -> chemin inexistant' }
            else { Log '            -> echec' }
        }
        if ($null -eq $found -and $authFail -and $tour -eq 0) {
            Log ''
            Write-Host '    Le compte SYSDBA est refuse.' -ForegroundColor Yellow
            $saisie = Read-Host '    Mot de passe SYSDBA (Entree = masterkey)'
            if ($saisie -ne '') { $fbPass = $saisie } else { $fbPass = 'masterkey' }
            $tour++
            continue
        }
        break
    }
}

# --- saisie manuelle de secours
if ($null -eq $found) {
    Log ''
    Log '[2b] SAISIE MANUELLE'
    Log '     Entrez les informations du serveur (laisser vide pour arreter).'
    for ($k = 1; $k -le 3; $k++) {
        $s = Read-Host '     Nom ou IP du serveur Tulip'
        if ($s -eq '') { break }
        $d = Read-Host '     Chemin COMPLET du .TFE vu du serveur (ex: D:\Gestion\CLIENT.TFE)'
        if ($d -eq '') { break }
        $h = Resolve-Host $s
        Log ('     essai : ' + $s + ' (' + $h + ') -> ' + $d)
        $r = Test-Db $h $d $fbUser $fbPass
        if ($r.Ok) {
            $found = @{ Host = $h; Server = $s; Path = $d; Nb = $r.Nb; Date = $r.Date }
            break
        }
        Log '     echec :'
        foreach ($line in $r.Raw.Split("`n")) {
            if ($line.Trim() -ne '') { Log ('       ' + $line.Trim()) }
        }
    }
}

if ($null -eq $found) {
    Finish '*** ECHEC ***' ('Aucune base Tulip n a pu etre ouverte.' + "`r`n" + "`r`n" + 'Verifier :' + "`r`n" + '  - le serveur est allume et joint sur le reseau' + "`r`n" + '  - le port 3050 est ouvert sur le serveur (pare-feu)' + "`r`n" + '  - Tulip GC est bien installe sur ce PC (cle TH\TFZ)' + "`r`n" + '  - consultez la section 8 du GUIDE-TULIPFACTURES.txt')
}

# --- resultat
Log ''
Log '[3] BASE TROUVEE'
Log ('    Serveur (saisi)  : ' + $found.Server)
Log ('    Adresse utilisee : ' + $found.Host)
Log ('    Fichier .TFE     : ' + $found.Path)
Log ('    Bons d entree    : ' + $found.Nb)
Log ('    Dernier bon      : ' + $found.Date)
Log ''

# --- sauvegarde + ecriture .env
Log '[4] ECRITURE DU FICHIER .env'
if (Test-Path $envPath) {
    Copy-Item -LiteralPath $envPath -Destination ($envPath + '.avant') -Force
    Copy-Item -LiteralPath $envPath -Destination ($envPath + '.avant-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) -Force
    Log '    Sauvegarde : .env.avant'
    $lines = @(Get-Content $envPath)
} else {
    $lines = @('# Configuration Tulip - generee par 1-REGLER-CONNEXION-TULIP.bat')
    Log '    Aucun .env existant : creation.'
}

$lines = @(Set-EnvKey $lines 'TULIP_FB_ENABLED'       'true')
$lines = @(Set-EnvKey $lines 'TULIP_FB_WRITE_ENABLED' 'true')
$lines = @(Set-EnvKey $lines 'TULIP_FB_HOST'          $found.Host)
$lines = @(Set-EnvKey $lines 'TULIP_FB_PORT'          '3050')
$lines = @(Set-EnvKey $lines 'TULIP_FB_DATABASE'      $found.Path)
$lines = @(Set-EnvKey $lines 'TULIP_FB_USER'          $fbUser)
$lines = @(Set-EnvKey $lines 'TULIP_FB_PASSWORD'      $fbPass)
$lines = @(Set-EnvKey $lines 'TULIP_FB_ISQL_PATH'     $isql)
$lines = @(Set-EnvKey $lines 'TULIP_FB_HOME'          $fbHome)
$lines = @(Set-EnvKey $lines 'TULIP_FB_CHARSET'       'WIN1252')
$lines = @(Set-EnvKey $lines 'TULIP_FB_TIMEOUT'       '60')
$lines = @(Set-EnvKey $lines 'TULIP_GOT_OCR_ENABLED'  'false')
$lines = @(Set-EnvKey $lines 'TULIP_LLM_ENABLED'      'false')

try {
    [IO.File]::WriteAllLines($envPath, $lines, [Text.Encoding]::ASCII)
} catch {
    Finish '*** ECHEC ***' ('Impossible d ecrire le fichier .env :' + "`r`n" + $_.Exception.Message + "`r`n" + 'Verifier que le dossier n est pas protege en ecriture.')
}
foreach ($l in (Get-Content $envPath)) {
    if ($l -match '^TULIP_FB_(ENABLED|WRITE_ENABLED|HOST|PORT|DATABASE|USER|CHARSET)') { Log ('    ' + $l) }
}
Log ''

# --- verification finale relue depuis le .env
Log '[5] VERIFICATION FINALE (relecture du .env)'
$vHost = ''; $vDb = ''; $vUser = 'SYSDBA'; $vPass = 'masterkey'
foreach ($l in (Get-Content $envPath)) {
    if ($l -match '^\s*TULIP_FB_HOST\s*=\s*(.+)$')     { $vHost = $Matches[1].Trim() }
    if ($l -match '^\s*TULIP_FB_DATABASE\s*=\s*(.+)$') { $vDb   = $Matches[1].Trim() }
    if ($l -match '^\s*TULIP_FB_USER\s*=\s*(.+)$')     { $vUser = $Matches[1].Trim() }
    if ($l -match '^\s*TULIP_FB_PASSWORD\s*=\s*(.+)$') { $vPass = $Matches[1].Trim() }
}
$verif = Test-Db $vHost $vDb $vUser $vPass
if ($verif.Ok) {
    Log '    OK : la base repond avec les valeurs du .env.'
    Log ('    NB_BE = ' + $verif.Nb + '   /   dernier bon = ' + $verif.Date)
} else {
    Finish '*** ECHEC APRES ECRITURE ***' 'Le .env a ete ecrit mais la connexion ne repond plus. Relancez ce fichier.'
}
Log ''

# --- etat accessoire
Log '[6] ETAT DU PC'
$fw = ''
$oldEap = $ErrorActionPreference
$ErrorActionPreference = 'SilentlyContinue'
try { $fw = (& netsh advfirewall firewall show rule name="Tulip Factures (LAN)" 2>&1 | Out-String) } catch { }
$ErrorActionPreference = $oldEap
if ($fw -match '8000') { Log '    Pare-feu port 8000 : REGLE PRESENTE' }
else { Log '    Pare-feu port 8000 : REGLE ABSENTE -> lancer AUTORISER-TELEPHONE.bat (clic droit, administrateur)' }

$proc = $null
try { $proc = Get-Process -Name 'TulipFactures' -ErrorAction SilentlyContinue } catch { }
if ($proc -ne $null) { Log '    ATTENTION : TulipFactures.exe tourne encore -> le fermer puis le relancer.' }
else { Log '    TulipFactures.exe : arrete (pret a demarrer)' }

$ips = ''
try {
    $nip = [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName())
    foreach ($ip in $nip) {
        if ($ip.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork) {
            if ($ips -ne '') { $ips = $ips + ' / ' }
            $ips = $ips + $ip.ToString()
        }
    }
} catch { }
Log ('    Adresses de ce PC : ' + $ips)
Log ''

Finish '   CONFIGURATION TERMINEE AVEC SUCCES' ('Ce qui a ete fait :' + "`r`n" + '  - base Tulip localisee et testee' + "`r`n" + '  - fichier .env ecrit et verifie' + "`r`n" + "`r`n" + 'A FAIRE MAINTENANT :' + "`r`n" + '  1. Fermer completement TulipFactures s il est ouvert' + "`r`n" + '  2. Relancer TulipFactures.exe (le .env n est lu qu au demarrage)' + "`r`n" + '  3. Envoyer UNE facture et verifier qu elle apparait dans Tulip GC' + "`r`n" + '  4. Pour le telephone : AUTORISER-TELEPHONE.bat en administrateur')
