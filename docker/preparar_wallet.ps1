<#
 Extrae el wallet de Oracle Cloud en docker\wallet y apunta su sqlnet.ora a la ruta
 que tiene dentro del contenedor (/opt/oracle/wallet).
 Uso (desde la carpeta docker):
   .\preparar_wallet.ps1 -WalletZip "C:\Users\crist\Downloads\Wallet_ELECTRISYS.zip"
 Crea tambien docker\wallet\.gitignore para que Git ignore el wallet.
#>
param([Parameter(Mandatory = $true)][string]$WalletZip)
$ErrorActionPreference = "Stop"
if (-not (Test-Path $WalletZip)) { throw "No existe el wallet: $WalletZip" }
$destino = Join-Path $PSScriptRoot "wallet"
Expand-Archive -Path $WalletZip -DestinationPath $destino -Force
$sqlnet = Join-Path $destino "sqlnet.ora"
$texto = [IO.File]::ReadAllText($sqlnet).Replace("?/network/admin", "/opt/oracle/wallet")
[IO.File]::WriteAllText($sqlnet, $texto, (New-Object Text.UTF8Encoding($false)))
[IO.File]::WriteAllText((Join-Path $destino ".gitignore"), "*`n")
Write-Host "Wallet listo en $destino"
Select-String -Path $sqlnet -Pattern "DIRECTORY"
