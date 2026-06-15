# Funcoes compartilhadas: verify-sync.ps1 e ensure-sync.ps1

$script:SyncLibScriptsDir = $PSScriptRoot
if (-not $script:SyncLibScriptsDir) {
    $script:SyncLibScriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
$script:SyncLibRoot = Split-Path -Parent $script:SyncLibScriptsDir
Set-Location $script:SyncLibRoot
. (Join-Path $script:SyncLibScriptsDir 'vm-remote.ps1')

function Initialize-SyncLib {
    if (-not $script:SyncLibRoot) {
        throw 'sync-lib.ps1 nao foi carregado corretamente'
    }
}

function Get-ShortSha {
    param([string]$Sha)
    if ($Sha.Length -ge 7) { return $Sha.Substring(0, 7) }
    return $Sha
}

function Invoke-GitFetch {
    param([string]$Branch = 'main')
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    git fetch origin $Branch 2>&1 | Out-Null
    $ErrorActionPreference = $prevEap
    if ($LASTEXITCODE -ne 0) {
        throw "git fetch origin $Branch falhou"
    }
}

function Get-VmCommitSha {
    param(
        [string]$VmHost,
        [string]$VmUser,
        [string]$AppDir
    )
    $bashParts = @(
        'if [ -d ''', $AppDir, '/.git'' ]; then git -C ''', $AppDir, ''' rev-parse HEAD; ',
        'elif [ -f ''', $AppDir, '/.deploy/last_deploy_sha'' ]; then cat ''', $AppDir, '/.deploy/last_deploy_sha''; ',
        'else echo MISSING; fi'
    )
    $bashCmd = -join $bashParts
    $raw = Invoke-VmRemote -VmHost $VmHost -VmUser $VmUser -Command $bashCmd
    return ($raw -split [Environment]::NewLine)[-1].Trim()
}

function Get-SyncState {
    param(
        [string]$VmHost = '56.125.163.194',
        [string]$VmUser = 'ubuntu',
        [string]$Branch = 'main',
        [string]$AppDir = '/opt/pli-reporta'
    )

    Initialize-SyncLib
    Invoke-GitFetch -Branch $Branch

    $localSha = (git rev-parse HEAD).Trim()
    $githubSha = (git rev-parse ('origin/' + $Branch)).Trim()
    $vmSha = Get-VmCommitSha -VmHost $VmHost -VmUser $VmUser -AppDir $AppDir

    [PSCustomObject]@{
        Branch    = $Branch
        Local     = $localSha
        GitHub    = $githubSha
        Vm        = $vmSha
        IsSynced  = ($localSha -eq $githubSha -and $githubSha -eq $vmSha)
    }
}

function Write-SyncStatus {
    param($State)
    Write-Host ''
    Write-Host ('  Laptop : ' + (Get-ShortSha $State.Local) + '  ' + $State.Local)
    Write-Host ('  GitHub : ' + (Get-ShortSha $State.GitHub) + '  ' + $State.GitHub)
    Write-Host ('  VM     : ' + (Get-ShortSha $State.Vm) + '  ' + $State.Vm)
    Write-Host ''
}

function Get-LaptopSyncAction {
    param(
        [string]$LocalSha,
        [string]$GitHubSha
    )

    if ($LocalSha -eq $GitHubSha) { return 'none' }

    $ahead = [int](git rev-list --count ($GitHubSha + '..' + $LocalSha))
    $behind = [int](git rev-list --count ($LocalSha + '..' + $GitHubSha))

    if ($ahead -gt 0 -and $behind -gt 0) { return 'diverged' }
    if ($ahead -gt 0) { return 'push' }
    if ($behind -gt 0) { return 'pull' }
    return 'none'
}

function Test-AppHealth {
    param(
        [string]$Url,
        [string]$Label,
        [int]$MaxAttempts = 6,
        [int]$DelaySeconds = 10
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            $response = Invoke-RestMethod -Uri $Url -TimeoutSec 45
            if ($response.status -eq 'ok' -and $response.db -eq 'ok') {
                Write-Host ('  OK  ' + $Label + ' (' + $Url + ')') -ForegroundColor Green
                return $true
            }
            Write-Host ('  !!  ' + $Label + ' respondeu mas db/status invalido (tentativa ' + $attempt + ')') -ForegroundColor Yellow
        }
        catch {
            Write-Host ('  ..  ' + $Label + ' aguardando (tentativa ' + $attempt + '/' + $MaxAttempts + ')') -ForegroundColor DarkGray
        }
        if ($attempt -lt $MaxAttempts) {
            Start-Sleep -Seconds $DelaySeconds
        }
    }

    throw ($Label + ' falhou no healthcheck: ' + $Url)
}
