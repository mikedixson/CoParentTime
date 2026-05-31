param(
    [switch]$TrackedOnly
)

$ErrorActionPreference = 'Stop'

function Get-GitCommand {
    $gitCmd = Get-Command git -ErrorAction SilentlyContinue
    if ($gitCmd) {
        return $gitCmd.Source
    }

    $defaultGit = 'C:\Program Files\Git\cmd\git.exe'
    if (Test-Path $defaultGit) {
        return $defaultGit
    }

    return $null
}

$rules = @(
    @{ Name = 'Email address'; Pattern = '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' },
    @{ Name = 'Meeting password line'; Pattern = '(?i)meeting password\s*:' },
    @{ Name = 'Zoom meeting URL'; Pattern = 'https?://[^\s]*zoom\.us/j/' },
    @{ Name = 'Webex URL'; Pattern = 'https?://[^\s]*webex\.com/' },
    @{ Name = 'Private key header'; Pattern = '-----BEGIN [A-Z ]*PRIVATE KEY-----' },
    @{ Name = 'Sensitive URL query token'; Pattern = '(?i)(\?|&)(pwd|token|cid|auth|access_token|refresh_token)=([A-Za-z0-9._%\-]{4,})' }
)

function Is-AllowedSyntheticFinding {
    param(
        [string]$Rule,
        [string]$Snippet
    )

    if ($Rule -eq 'Email address' -and $Snippet -match '@(example\.invalid|example\.com|example\.org)\b') {
        return $true
    }

    if (
        $Rule -eq 'Sensitive URL query token' -and
        $Snippet -match '(?i)(synthetic|\*\*\*|%2A%2A%2A|\.\.\.|private-token|test/basic\.ics|cid=abc|nocache=123)'
    ) {
        return $true
    }

    return $false
}

$excludePathParts = @(
    '.git',
    '.venv',
    '.pytest_cache',
    'artifacts',
    '__pycache__'
)

$workspaceRoot = Get-Location
$files = @()

if ($TrackedOnly) {
    $gitPath = Get-GitCommand
    if (-not $gitPath) {
        Write-Error 'TrackedOnly was specified but git is not available on PATH and default install path was not found.'
    }

    $files = & $gitPath ls-files
    $files = $files | Where-Object { $_ -and (Test-Path $_) }
} else {
    $files = Get-ChildItem -Path . -Recurse -File | ForEach-Object { $_.FullName }
    $files = $files | Where-Object {
        $full = $_
        -not ($excludePathParts | ForEach-Object { $full -like "*\$_\*" } | Where-Object { $_ })
    }
}

$findings = @()

foreach ($file in $files) {
    $relative = Resolve-Path -LiteralPath $file | ForEach-Object {
        $_.Path.Substring($workspaceRoot.Path.Length).TrimStart('\\')
    }

    foreach ($rule in $rules) {
        $matches = Select-String -Path $file -Pattern $rule.Pattern -AllMatches -ErrorAction SilentlyContinue
        foreach ($m in $matches) {
            if (Is-AllowedSyntheticFinding -Rule $rule.Name -Snippet $m.Line.Trim()) {
                continue
            }

            $findings += [PSCustomObject]@{
                Rule = $rule.Name
                File = $relative
                Line = $m.LineNumber
                Snippet = $m.Line.Trim()
            }
        }
    }
}

if ($findings.Count -eq 0) {
    Write-Host 'No publish-safety findings detected.'
    exit 0
}

Write-Host "Found $($findings.Count) potential publish-safety issue(s):"
$findings | Sort-Object File, Line, Rule | Format-Table -AutoSize
exit 1
