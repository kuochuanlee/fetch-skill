# Global Python SSL Fix (Permanent Path)

$ErrorActionPreference = "Stop"
Write-Host "Starting Global SSL Certificate Configuration..." -ForegroundColor Cyan

# 1. Permanent Path (Using dynamic $HOME)
$certDir = Join-Path $HOME ".python-certs"
$certPath = Join-Path $certDir "cacert.pem"

if (-Not (Test-Path $certDir)) {
    New-Item -ItemType Directory -Path $certDir -Force | Out-Null
    Write-Host "Created permanent certificate directory: $certDir"
}

# 2. Fetch Certificate
Write-Host "Downloading latest CA cert from curl.se..."
$webClient = New-Object System.Net.WebClient
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $webClient.DownloadFile("https://curl.se/ca/cacert.pem", $certPath)
    Write-Host "Certificate successfully stored at: $certPath" -ForegroundColor Green
} catch {
    Write-Host "Download failed!" -ForegroundColor Red
    throw $_
}

# 3. Permanent Environment Variable
Write-Host "Setting Windows Environment Variable SSL_CERT_FILE..."
[Environment]::SetEnvironmentVariable("SSL_CERT_FILE", $certPath, "User")
$env:SSL_CERT_FILE = $certPath

Write-Host "SUCCESS: SSL fixed once and for all!" -ForegroundColor Green
Write-Host "Location: $certPath"
