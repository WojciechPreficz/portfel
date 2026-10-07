$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$frontendPath = Join-Path $repoRoot "frontend"
$frontendDistPath = Join-Path $frontendPath "dist"
$backendPath = Join-Path $repoRoot "backend"
$backendFrontendDistPath = Join-Path $backendPath "frontend_dist"
$releasePath = Join-Path $repoRoot "release.zip"
$stagingRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "portfel-release-" + [guid]::NewGuid().ToString("N")
)
$stagingBackendPath = Join-Path $stagingRoot "backend"

if (-not (Test-Path -LiteralPath (Join-Path $frontendPath "package.json"))) {
    throw "Nie znaleziono frontend/package.json."
}
if (-not (Test-Path -LiteralPath (Join-Path $backendPath "requirements.txt"))) {
    throw "Nie znaleziono backend/requirements.txt."
}

Push-Location $frontendPath
try {
    npm ci
    if ($LASTEXITCODE -ne 0) {
        throw "npm ci failed (exit code $LASTEXITCODE)."
    }

    npm run build
    if ($LASTEXITCODE -ne 0) {
        throw "npm run build failed (exit code $LASTEXITCODE)."
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $frontendDistPath -PathType Container)) {
    throw "Build did not create frontend/dist."
}

if (Test-Path -LiteralPath $backendFrontendDistPath) {
    Remove-Item -LiteralPath $backendFrontendDistPath -Recurse -Force
}
New-Item -ItemType Directory -Path $backendFrontendDistPath -Force | Out-Null
Get-ChildItem -LiteralPath $frontendDistPath -Force |
    Copy-Item -Destination $backendFrontendDistPath -Recurse -Force

$excludedDirectoryNames = @(
    ".git",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    "tests"
)
$includedFiles = @()

foreach ($file in Get-ChildItem -LiteralPath $backendPath -Recurse -File -Force) {
    $relativePath = $file.FullName.Substring($backendPath.Length).TrimStart("\", "/")
    $pathParts = $relativePath -split "[\\/]"
    $excludeFile = $false

    foreach ($part in $pathParts) {
        if (($part -like ".venv*") -or ($excludedDirectoryNames -contains $part)) {
            $excludeFile = $true
            break
        }
    }

    if (
        $excludeFile -or
        (($file.Name -like ".env*") -and ($file.Name -ne ".env.example")) -or
        ($file.Name -like "*.db") -or
        ($file.Name -like "test_*.py") -or
        ($file.Name -like "*_test.py")
    ) {
        continue
    }

    $includedFiles += [PSCustomObject]@{
        Source = $file.FullName
        RelativePath = $relativePath
    }
}

if ($includedFiles.Count -eq 0) {
    throw "No backend files were found to include in the archive."
}

New-Item -ItemType Directory -Path $stagingBackendPath -Force | Out-Null
foreach ($file in $includedFiles) {
    $destination = Join-Path $stagingBackendPath $file.RelativePath
    $destinationDirectory = Split-Path -Parent $destination
    New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
    Copy-Item -LiteralPath $file.Source -Destination $destination -Force
}

try {
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $stagedArchivePath = Join-Path $stagingRoot "release.zip"
    $archive = [System.IO.Compression.ZipFile]::Open(
        $stagedArchivePath,
        [System.IO.Compression.ZipArchiveMode]::Create
    )
    try {
        foreach ($file in $includedFiles) {
            $stagedFilePath = Join-Path $stagingBackendPath $file.RelativePath
            $entryName = "backend/" + ($file.RelativePath -replace "\\", "/")
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $archive,
                $stagedFilePath,
                $entryName,
                [System.IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
        }
    }
    finally {
        $archive.Dispose()
    }
    Move-Item -LiteralPath $stagedArchivePath -Destination $releasePath -Force
}
finally {
    if (Test-Path -LiteralPath $stagingRoot) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}

$archiveSize = (Get-Item -LiteralPath $releasePath).Length
$archiveEntries = $includedFiles |
    Sort-Object RelativePath |
    ForEach-Object { "backend/$($_.RelativePath -replace '\\', '/')" }

Write-Host ""
Write-Host "Created: $releasePath"
Write-Host ("Size: {0:N2} MB" -f ($archiveSize / 1MB))
Write-Host ("Backend file count: {0}" -f $includedFiles.Count)
Write-Host "Archive contents:"
$archiveEntries | ForEach-Object { Write-Host "  $_" }
