# Verifica e sincroniza laptop <-> GitHub <-> VM (Git + rebuild/teste do container).
# Uso: powershell -File scripts/ensure-sync.ps1 [-CommitMessage "mensagem"]

param(
    [string]$VmHost = '56.125.163.194',
    [string]$VmUser = 'ubuntu',
    [string]$Branch = 'main',
    [string]$AppDir = '/opt/pli-reporta',
    [string]$VmBaseUrl = 'https://pli-reporta.56-125-163-194.sslip.io',
    [string]$VmHealthUrl = 'https://pli-reporta.56-125-163-194.sslip.io/healthz',
    [string]$CommitMessage = ''
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'sync-lib.ps1')

function Write-Step {
    param([string]$Message)
    Write-Host ''
    Write-Host ('=== ' + $Message + ' ===') -ForegroundColor Cyan
}

function Test-WorkingTreeClean {
    $dirty = git status --porcelain
    return -not $dirty
}

function Get-DefaultCommitMessage {
    $files = git status --porcelain | ForEach-Object { $_.Substring(3).Trim() }
    $count = @($files).Count
    if ($count -eq 1) {
        return 'sync: atualiza ' + $files[0]
    }
    return 'sync: publica ' + $count + ' arquivos locais'
}

function Invoke-LocalCommit {
    param([string]$Message)

    if (Test-WorkingTreeClean) {
        Write-Host '  Nada para commitar' -ForegroundColor DarkGray
        return $false
    }

    if (-not $Message) {
        $Message = Get-DefaultCommitMessage
    }

    Write-Host ('  Commit: ' + $Message) -ForegroundColor Yellow
    git add -A
    if ($LASTEXITCODE -ne 0) { throw 'git add falhou' }

    git commit -m $Message
    if ($LASTEXITCODE -ne 0) { throw 'git commit falhou' }

    Write-Host '  OK  alteracoes locais commitadas' -ForegroundColor Green
    return $true
}

function Invoke-LaptopGitHubAlign {
    param([string]$BranchName)

    $state = Get-SyncState -VmHost $VmHost -VmUser $VmUser -Branch $BranchName -AppDir $AppDir
    $action = Get-LaptopSyncAction -LocalSha $state.Local -GitHubSha $state.GitHub

    if ($action -eq 'diverged') {
        throw 'Laptop e GitHub divergiram. Resolva manualmente (merge/rebase) antes de sincronizar.'
    }

    if ($action -eq 'push') {
        Write-Host ('  Acao: git push origin ' + $BranchName) -ForegroundColor Yellow
        git push origin $BranchName
        if ($LASTEXITCODE -ne 0) { throw 'git push falhou' }
        Write-Host '  OK  laptop enviado ao GitHub' -ForegroundColor Green
        return
    }

    if ($action -eq 'pull') {
        if (-not (Test-WorkingTreeClean)) {
            throw 'Ha alteracoes locais nao commitadas. Faca commit ou stash antes do pull.'
        }
        Write-Host ('  Acao: git pull --ff-only origin ' + $BranchName) -ForegroundColor Yellow
        git pull --ff-only origin $BranchName
        if ($LASTEXITCODE -ne 0) { throw 'git pull --ff-only falhou' }
        Write-Host '  OK  laptop atualizado do GitHub' -ForegroundColor Green
        return
    }

    Write-Host '  OK  laptop ja alinhado com GitHub' -ForegroundColor Green
}

$updatedVm = $false

Write-Step '1/6 Estado atual (Git central)'
$state = Get-SyncState -VmHost $VmHost -VmUser $VmUser -Branch $Branch -AppDir $AppDir
Write-SyncStatus $state
if (-not (Test-WorkingTreeClean)) {
    Write-Host '  AVISO  ha alteracoes locais nao commitadas' -ForegroundColor Yellow
}
if (Test-VmRuntimeStale -BaseUrl $VmBaseUrl) {
    Write-Host '  AVISO  container na VM desatualizado (git pode estar OK)' -ForegroundColor Yellow
}

Write-Step '2/6 Commit das alteracoes locais'
$null = Invoke-LocalCommit -Message $CommitMessage

Write-Step '3/6 Alinhando laptop com GitHub'
Invoke-LaptopGitHubAlign -BranchName $Branch

Write-Step '4/6 VM — git pull, rebuild do container e testes'
$state = Get-SyncState -VmHost $VmHost -VmUser $VmUser -Branch $Branch -AppDir $AppDir
$runtimeStale = Test-VmRuntimeStale -BaseUrl $VmBaseUrl
$needsVmDeploy = ($state.Vm -ne $state.GitHub) -or $runtimeStale

if ($needsVmDeploy) {
    if ($state.Vm -eq $state.GitHub -and $runtimeStale) {
        Write-Host '  Git alinhado — rebuild e teste do container na VM' -ForegroundColor Yellow
    } else {
        Write-Host '  Acao: sync-vm.ps1 (pull + rebuild + healthcheck + manifesto)' -ForegroundColor Yellow
    }
    & (Join-Path $PSScriptRoot 'sync-vm.ps1') `
        -VmHost $VmHost -VmUser $VmUser -Branch $Branch -AppDir $AppDir `
        -VmBaseUrl $VmBaseUrl -VmHealthUrl $VmHealthUrl
    if ($LASTEXITCODE -ne 0) { throw 'sync-vm.ps1 falhou' }
    $updatedVm = $true
    Write-Host '  OK  VM atualizada (git + container)' -ForegroundColor Green
} else {
    Write-Host '  OK  git e container ja atualizados na VM' -ForegroundColor Green
}

Write-Step '5/6 Verificacao Git final'
if (-not (Test-WorkingTreeClean)) {
    throw 'Ainda existem alteracoes locais nao commitadas.'
}

$state = Get-SyncState -VmHost $VmHost -VmUser $VmUser -Branch $Branch -AppDir $AppDir
Write-SyncStatus $state
if (-not $state.IsSynced) {
    throw 'Sincronizacao Git incompleta apos as correcoes automaticas.'
}

Write-Step '6/6 Teste do container na VM (health + manifesto + pagina)'
if (-not $updatedVm) {
    $null = Test-VmRuntime -BaseUrl $VmBaseUrl -HealthUrl $VmHealthUrl -Label 'VM' -MaxAttempts 6 -DelaySeconds 5
} else {
    Write-Host '  OK  testes ja executados no passo 4/6' -ForegroundColor Green
}

Write-Host ''
Write-Host 'SINCRONIZADO — laptop, GitHub, VM (git + container testado)' -ForegroundColor Green
Write-Host ('  commit: ' + $state.Local) -ForegroundColor DarkGray
Write-Host ('  VM:     ' + $VmBaseUrl) -ForegroundColor DarkGray
Open-AppInBrowser -BaseUrl $VmBaseUrl -Label 'VM'
