# Compara versoes: laptop | GitHub | VM
# Uso: powershell -File scripts/verify-sync.ps1

param(
    [string]$VmHost = '56.125.163.194',
    [string]$VmUser = 'ubuntu',
    [string]$Branch = 'main',
    [string]$AppDir = '/opt/pli-reporta'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
. (Join-Path $PSScriptRoot 'vm-remote.ps1')

function Get-ShortSha {
    param([string]$Sha)
    if ($Sha.Length -ge 7) {
        return $Sha.Substring(0, 7)
    }
    return $Sha
}

function Get-VmCommitSha {
    param(
        [string]$HostName,
        [string]$UserName,
        [string]$AppPath
    )

    $bashParts = @(
        'if [ -d ''', $AppPath, '/.git'' ]; then git -C ''', $AppPath, ''' rev-parse HEAD; ',
        'elif [ -f ''', $AppPath, '/.deploy/last_deploy_sha'' ]; then cat ''', $AppPath, '/.deploy/last_deploy_sha''; ',
        'else echo MISSING; fi'
    )
    $bashCmd = -join $bashParts
    $raw = Invoke-VmRemote -VmHost $HostName -VmUser $UserName -Command $bashCmd
    return ($raw -split [Environment]::NewLine)[-1].Trim()
}

function Test-RepoSync {
    param(
        [string]$HostName,
        [string]$UserName,
        [string]$BranchName,
        [string]$AppPath
    )

    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    git fetch origin $BranchName 2>&1 | Out-Null
    $ErrorActionPreference = $prevEap

    $localSha = (git rev-parse HEAD).Trim()
    $githubSha = (git rev-parse ('origin/' + $BranchName)).Trim()
    $vmSha = Get-VmCommitSha -HostName $HostName -UserName $UserName -AppPath $AppPath

    $shortLocal = Get-ShortSha $localSha
    $shortGithub = Get-ShortSha $githubSha
    $shortVm = Get-ShortSha $vmSha

    Write-Host ''
    Write-Host ('  Laptop : ' + $shortLocal + '  ' + $localSha)
    Write-Host ('  GitHub : ' + $shortGithub + '  ' + $githubSha)
    Write-Host ('  VM     : ' + $shortVm + '  ' + $vmSha)
    Write-Host ''

    if ($localSha -eq $githubSha -and $githubSha -eq $vmSha) {
        Write-Host -ForegroundColor Green '  SINCRONIZADO - os tres ambientes no mesmo commit'
        return 0
    }

    $status = 0
    if ($localSha -ne $githubSha) {
        $pushMsg = '  DESALINHADO - rode: git push origin ' + $BranchName
        Write-Host -ForegroundColor Yellow $pushMsg
        $status = 1
    }
    if ($githubSha -ne $vmSha) {
        $syncMsg = '  DESALINHADO - rode: powershell -File scripts/sync-vm.ps1'
        Write-Host -ForegroundColor Yellow $syncMsg
        $status = 1
    }
    return $status
}

$code = Test-RepoSync -HostName $VmHost -UserName $VmUser -BranchName $Branch -AppPath $AppDir
exit $code
