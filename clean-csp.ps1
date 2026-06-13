<#
.SYNOPSIS
Aggressively removes Clip Studio Paint leftovers on Windows.

.DESCRIPTION
This is intentionally destructive: it kills likely CSP processes, removes CSP
user data, install leftovers, shortcuts, and common CELSYS registry keys.
No backups are created.

.EXAMPLE
.\clean-csp.ps1

.EXAMPLE
.\clean-csp.ps1 -WhatIf
#>

[CmdletBinding()]
param(
    [switch]$WhatIf,
    [switch]$SkipProcessKill,
    [switch]$SkipRegistry
)

$ErrorActionPreference = "Continue"

function Get-ExistingFileTarget {
    param([Parameter(Mandatory = $true)][string[]]$Paths)

    foreach ($path in $Paths) {
        $expandedPath = [Environment]::ExpandEnvironmentVariables($path)
        if ([string]::IsNullOrWhiteSpace($expandedPath)) {
            continue
        }

        if ($expandedPath.Contains("*")) {
            Resolve-Path -Path $expandedPath -ErrorAction SilentlyContinue |
                ForEach-Object { $_.Path }
            continue
        }

        if (Test-Path -LiteralPath $expandedPath) {
            $expandedPath
        }
    }
}

function Remove-NukeTarget {
    param([Parameter(Mandatory = $true)][string]$Path)

    if ($WhatIf) {
        Write-Host "[what-if] remove $Path"
        return
    }

    Write-Host "Removing $Path"
    Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Continue
}

function Remove-NukeRegistryTarget {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    if ($WhatIf) {
        Write-Host "[what-if] remove registry $Path"
        return
    }

    Write-Host "Removing registry $Path"
    Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Continue
}

$processPatterns = @(
    "CLIPStudio*",
    "ClipStudio*",
    "CLIPStudioPaint*",
    "ClipStudioPaint*",
    "Celsys*",
    "CSP*"
)

$fileTargets = @(
    "%USERPROFILE%\Documents\CELSYS",
    "%USERPROFILE%\Documents\CELSYS_EN",
    "%APPDATA%\CELSYS",
    "%APPDATA%\CELSYSUserData",
    "%LOCALAPPDATA%\CELSYS",
    "%LOCALAPPDATA%\CELSYSUserData",
    "%LOCALAPPDATA%\CLIPStudioPaint",
    "%LOCALAPPDATA%\CLIP STUDIO PAINT",
    "%PROGRAMDATA%\CELSYS",
    "%ProgramFiles%\CELSYS",
    "%ProgramFiles(x86)%\CELSYS",
    "%APPDATA%\Microsoft\Windows\Start Menu\Programs\*CLIP STUDIO*",
    "%APPDATA%\Microsoft\Windows\Start Menu\Programs\*CELSYS*",
    "%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\*CLIP STUDIO*",
    "%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\*CELSYS*",
    "%USERPROFILE%\Desktop\*CLIP STUDIO*.lnk",
    "%PUBLIC%\Desktop\*CLIP STUDIO*.lnk"
)

$registryTargets = @(
    "HKCU:\Software\CELSYS",
    "HKCU:\Software\CLIP STUDIO",
    "HKCU:\Software\CLIPStudioPaint",
    "HKLM:\Software\CELSYS",
    "HKLM:\Software\WOW6432Node\CELSYS",
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\CLIP STUDIO*",
    "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\CLIP STUDIO*"
)

Write-Warning "NUKE MODE: this removes CSP/CELSYS data with no backups."

if (-not $SkipProcessKill) {
    foreach ($pattern in $processPatterns) {
        $processes = @(Get-Process -Name $pattern -ErrorAction SilentlyContinue)
        foreach ($process in $processes) {
            if ($WhatIf) {
                Write-Host "[what-if] stop process $($process.ProcessName) ($($process.Id))"
                continue
            }

            Write-Host "Stopping process $($process.ProcessName) ($($process.Id))"
            Stop-Process -Id $process.Id -Force -ErrorAction Continue
        }
    }
}

Write-Host ""
Write-Host "Removing files and folders..."
$existingFileTargets = @(Get-ExistingFileTarget -Paths $fileTargets | Sort-Object -Unique)
foreach ($target in $existingFileTargets) {
    Remove-NukeTarget -Path $target
}

if (-not $SkipRegistry) {
    Write-Host ""
    Write-Host "Removing registry keys..."
    foreach ($target in $registryTargets) {
        if ($target.Contains("*")) {
            Resolve-Path -Path $target -ErrorAction SilentlyContinue |
                ForEach-Object { Remove-NukeRegistryTarget -Path $_.Path }
            continue
        }

        Remove-NukeRegistryTarget -Path $target
    }
}

Write-Host ""
Write-Host "CSP nuke cleanup complete. Reboot before reinstalling."
