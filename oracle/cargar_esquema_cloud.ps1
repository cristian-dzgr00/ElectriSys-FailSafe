<#
 Carga el esquema ElectriSys en Oracle Cloud (Autonomous AI Database) desde Windows.
 Requiere SQL*Plus en el PATH y el wallet descargado (Wallet_ELECTRISYS.zip).
 Uso (desde la carpeta oracle):
   .\cargar_esquema_cloud.ps1 -WalletZip "C:\ruta\Wallet_ELECTRISYS.zip"
 Pide por teclado la clave de ADMIN y la clave nueva de ELECTRISYS (no quedan en disco
 ni en la linea de comandos). NO ejecuta 16_normalizacion_3fn_fase2.sql: esa fase elimina
 vehiculos.marca/modelo y el backend actual aun las usa. Solo corre una vez: en una base ya cargada fallara con
 ORA-00955 a proposito, igual que cargar_esquema.sh.
#>
param(
    [Parameter(Mandatory = $true)][string]$WalletZip,
    [string]$Servicio = "electrisys_tp"
)
$ErrorActionPreference = "Stop"
$DirScripts = $PSScriptRoot
# UTF-8 sin BOM hacia sqlplus: con BOM, sqlplus rechaza la primera linea (SP2-0734).
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)

function Leer-Secreto([string]$mensaje) {
    $s = Read-Host $mensaje -AsSecureString
    $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
    try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
}

if (-not (Get-Command sqlplus -ErrorAction SilentlyContinue)) { throw "No se encontro sqlplus en el PATH." }
if (-not (Test-Path $WalletZip)) { throw "No existe el wallet: $WalletZip" }

# Wallet: se extrae fuera del repo y se corrige la ruta en sqlnet.ora
$walletDir = Join-Path $env:LOCALAPPDATA "electrisys_wallet"
Expand-Archive -Path $WalletZip -DestinationPath $walletDir -Force
$sqlnet = Join-Path $walletDir "sqlnet.ora"
(Get-Content $sqlnet -Raw).Replace("?/network/admin", $walletDir) | Set-Content $sqlnet -Encoding ASCII
$env:TNS_ADMIN = $walletDir
$env:NLS_LANG = "AMERICAN_AMERICA.AL32UTF8"   # los .sql estan en UTF-8

# Modo no interactivo: si existen ELECTRISYS_ADMIN_PASS / ELECTRISYS_APP_PASS en el
# entorno se usan tal cual; si no, se piden por teclado.
$claveAdmin = $env:ELECTRISYS_ADMIN_PASS
if (-not $claveAdmin) { $claveAdmin = Leer-Secreto "Clave de ADMIN" }
$claveApp = $env:ELECTRISYS_APP_PASS
if (-not $claveApp) { $claveApp = Leer-Secreto "Clave NUEVA para ELECTRISYS (12-30 caracteres, mayuscula, minuscula y numero)" }
if ($claveApp.Length -lt 12 -or $claveApp.Length -gt 30 -or $claveApp -match '["'']') {
    throw "Clave invalida: 12-30 caracteres y sin comillas."
}

$logDir = Join-Path $DirScripts "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("carga_cloud_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

function Ejecutar([string]$usuario, [string]$clave, [string]$archivo, [string]$parametro = "") {
    $ruta = Join-Path $DirScripts $archivo
    if (-not (Test-Path $ruta)) { throw "No existe $ruta" }
    $linea = "@`"$ruta`""
    if ($parametro) { $linea += " `"$parametro`"" }
    $entrada = "CONNECT $usuario/`"$clave`"@$Servicio`n$linea`nEXIT`n"
    Write-Host ">> [$usuario] $archivo"
    $salida = $entrada | & sqlplus -S /nolog 2>&1
    "=== $archivo ===" | Out-File $log -Append -Encoding utf8
    $salida | Out-File $log -Append -Encoding utf8
    $n = @($salida | Select-String -Pattern "ORA-|SP2-|PLS-").Count
    if ($n -gt 0) { Write-Warning "$archivo : $n linea(s) con error (ver $log)" }
}

Ejecutar "ADMIN" $claveAdmin "01_usuario_y_esquema_cloud.sql" $claveApp
foreach ($f in "02_ddl_tablas.sql","03_indices.sql","04_triggers.sql","05_seed.sql",
               "10_pedidos.sql","11_cotizaciones_estados.sql","12_nlp_dataset.sql",
               "13_posibles_errores.sql","14_seed_posibles_errores.sql",
               "15_normalizacion_3fn.sql",
               "06_packages_plsql.sql","07_vistas.sql","08_roles_privilegios.sql") {
    Ejecutar "ELECTRISYS" $claveApp $f
}
Ejecutar "ADMIN" $claveAdmin "09_usuarios_demo_cloud.sql"
Ejecutar "ADMIN" $claveAdmin "backup/10_directorio_backup_cloud.sql"
Ejecutar "ELECTRISYS" $claveApp "backup/11_pkg_backup_plsql.sql"

Write-Host "Terminado. Revisa el log: $log"
