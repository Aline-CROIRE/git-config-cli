<#
.SYNOPSIS
    Interactive demo of configctl's full lifecycle.

.DESCRIPTION
    Creates a throw-away configuration repository in a temporary folder and
    walks through: creating a draft, publishing it, updating it, rolling back,
    and causing and resolving a merge conflict. The script pauses after each
    step and explains what happened.

.EXAMPLE
    .\demo\demo.ps1
#>
param(
    [string]$Workspace = (Join-Path $env:TEMP "configctl-demo")
)

# --- Helpers ---------------------------------------------------------------

function Show-Step {
    # Print a step title and a short explanation.
    param([string]$Title, [string]$Explanation)
    Write-Host ""
    Write-Host "=== $Title ===" -ForegroundColor Cyan
    Write-Host $Explanation
}

function Invoke-Demo {
    # Print a command in yellow, then run it, so you see exactly what is typed.
    param([scriptblock]$Command)
    Write-Host ("> " + $Command.ToString().Trim()) -ForegroundColor Yellow
    & $Command
}

function Wait-ForUser {
    Write-Host ""
    Read-Host "Press Enter to continue" | Out-Null
}

# --- Setup -----------------------------------------------------------------

if (-not (Get-Command configctl -ErrorAction SilentlyContinue)) {
    throw "configctl was not found. Activate the virtual environment first: .\.venv\Scripts\Activate.ps1"
}

$repo = Join-Path $Workspace "configs"
$appJson = Join-Path $repo "app.json"

# Start from a clean, empty workspace every time the demo runs.
if (Test-Path $Workspace) {
    Remove-Item -Recurse -Force $Workspace
}
New-Item -ItemType Directory -Path $Workspace | Out-Null

# Every configctl command below uses these two settings.
$env:CONFIGCTL_REPO = $repo
$env:CONFIGCTL_LOG_FILE = Join-Path $Workspace "audit.log"

try {
    Show-Step "1. Create a configuration repository" `
        "configctl creates a Git repository on branch 'main' with one first commit."
    Invoke-Demo { configctl init }
    Invoke-Demo { git -C $repo log --oneline }
    Wait-ForUser

    Show-Step "2. Create a draft" `
        "A draft is a Git branch named draft/<name>. Changes stay there until published."
    Invoke-Demo { configctl draft first-version }
    Invoke-Demo { git -C $repo branch }
    Wait-ForUser

    Show-Step "3. Set values on the draft" `
        "Each 'set' switches to the draft, edits app.json, commits, and switches back to main."
    Invoke-Demo { configctl set first-version app.json timeout 30 }
    Invoke-Demo { configctl set first-version app.json database.host localhost }
    Invoke-Demo { configctl show app.json --draft first-version }
    Write-Host "main does not have app.json yet, so the next command fails on purpose:"
    Invoke-Demo { configctl show app.json }
    Wait-ForUser

    Show-Step "4. Publish the draft" `
        "Publishing merges the draft into main with a merge commit (git merge --no-ff)."
    Invoke-Demo { configctl publish first-version }
    Invoke-Demo { configctl show app.json }
    Invoke-Demo { git -C $repo log --oneline --graph --all }
    Wait-ForUser

    Show-Step "5. Update the configuration" `
        "Updates follow the same path: a new draft, a change, then publish."
    Invoke-Demo { configctl draft longer-timeout }
    Invoke-Demo { configctl set longer-timeout app.json timeout 60 }
    Invoke-Demo { configctl publish longer-timeout }
    Invoke-Demo { configctl show app.json }
    Wait-ForUser

    Show-Step "6. History and rollback" `
        "History lists the changes, newest first. Rollback restores an older version as a NEW commit."
    Invoke-Demo { configctl history app.json }
    # The second line of the history is the version before the update (timeout 30).
    $target = ((configctl history app.json) | Select-Object -Index 1).Split(" ")[0]
    Write-Host "Rolling back to $target (the version before the update):"
    Invoke-Demo { configctl rollback app.json $target }
    Invoke-Demo { configctl show app.json }
    Wait-ForUser

    Show-Step "7. Cause a merge conflict" `
        "Two drafts change the same value. The second publish conflicts, so the tool aborts the merge and explains how to fix it."
    Invoke-Demo { configctl draft fast }
    Invoke-Demo { configctl draft slow }
    Invoke-Demo { configctl set fast app.json timeout 10 }
    Invoke-Demo { configctl set slow app.json timeout 90 }
    Invoke-Demo { configctl publish fast }
    Write-Host "The next publish conflicts on purpose:"
    Invoke-Demo { configctl publish slow }
    Write-Host "main is unchanged (still timeout 10):"
    Invoke-Demo { configctl show app.json }
    Wait-ForUser

    Show-Step "8. Resolve the conflict" `
        "We follow the tool's own instructions: merge main into the draft, fix the file, commit, publish."
    Invoke-Demo { git -C $repo switch draft/slow }
    Invoke-Demo { git -C $repo merge main }
    Write-Host "The file now contains conflict markers:"
    Invoke-Demo { Get-Content $appJson }
    Write-Host "We keep timeout 90 and write valid JSON:"
    [System.IO.File]::WriteAllText($appJson, '{"database": {"host": "localhost"}, "timeout": 90}' + "`n")
    Invoke-Demo { git -C $repo add app.json }
    Invoke-Demo { git -C $repo commit -m "Resolve conflict: keep timeout 90" }
    Invoke-Demo { configctl publish slow }
    Invoke-Demo { configctl show app.json }
    Wait-ForUser

    Show-Step "9. The audit log" `
        "Every change and every error was written as one JSON line. Here it is as a table."
    Invoke-Demo {
        Get-Content $env:CONFIGCTL_LOG_FILE |
            ForEach-Object { $_ | ConvertFrom-Json } |
            Format-Table time, level, action, draft
    }

    Write-Host ""
    Write-Host "Demo finished. The demo repository is at: $repo" -ForegroundColor Green
}
finally {
    # Always remove the settings, even if the demo is stopped with Ctrl+C.
    Remove-Item Env:CONFIGCTL_REPO -ErrorAction SilentlyContinue
    Remove-Item Env:CONFIGCTL_LOG_FILE -ErrorAction SilentlyContinue
}
