# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 ArchEnergy s.r.o.
param([Parameter(Mandatory=$true)][string]$Executable)
$ErrorActionPreference = 'Stop'
$launcherExe = (Resolve-Path -LiteralPath $Executable).Path
if (-not (Test-Path -LiteralPath $launcherExe -PathType Leaf)) {
    throw 'EnergySketch executable not found'
}
$launcherRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$launcherPath = Join-Path $launcherRoot 'EnergySketch-AKTUALNI.lnk'
$launcherShell = New-Object -ComObject WScript.Shell
$launcherShortcut = $launcherShell.CreateShortcut($launcherPath)
$launcherShortcut.TargetPath = $launcherExe
$launcherShortcut.WorkingDirectory = [System.IO.Path]::GetDirectoryName($launcherExe)
$launcherShortcut.IconLocation = $launcherExe + ',0'
$launcherShortcut.Description = 'EnergySketch - aktualni overene sestaveni'
$launcherShortcut.Save()
if ($launcherShell.CreateShortcut($launcherPath).TargetPath -ne $launcherExe) {
    throw 'EnergySketch launcher verification failed'
}
Write-Output $launcherPath
