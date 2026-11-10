$ErrorActionPreference = 'Stop'

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $workspaceRoot '.venv\Scripts\python.exe'
$processes = @(Get-CimInstance Win32_Process)
$appProcesses = @($processes | Where-Object {
    $_.CommandLine -and
    $_.CommandLine.Contains($pythonPath, [System.StringComparison]::OrdinalIgnoreCase) -and
    $_.CommandLine -match '\s-m\s+uvicorn\s+app\.main:app(?:\s|$)'
})

if ($appProcesses.Count -eq 0) {
    Write-Host 'No running CoParenTime instance found for this workspace.'
    exit 0
}

$processIds = [System.Collections.Generic.HashSet[uint32]]::new()
foreach ($process in $appProcesses) {
    [void]$processIds.Add($process.ProcessId)
}

do {
    $added = $false
    foreach ($process in $processes) {
        if ($processIds.Contains($process.ParentProcessId) -and $processIds.Add($process.ProcessId)) {
            $added = $true
        }
    }
} while ($added)

# Stop reload supervisors before their workers so they cannot restart the app.
foreach ($process in @($appProcesses) + @($processes | Where-Object {
    $processIds.Contains($_.ProcessId) -and $_.ProcessId -notin $appProcesses.ProcessId
})) {
    $current = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.ProcessId)"
    if (-not $current -or $current.CreationDate -ne $process.CreationDate) {
        continue
    }
    try {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
        Write-Host "Stopped CoParenTime process $($process.ProcessId)."
    }
    catch [Microsoft.PowerShell.Commands.ProcessCommandException] {
        if (Get-CimInstance Win32_Process -Filter "ProcessId = $($process.ProcessId)") {
            throw
        }
        Write-Host "CoParenTime process $($process.ProcessId) has already exited."
    }
}
