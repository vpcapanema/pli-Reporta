# Publica alteracoes locais no GitHub e sincroniza a VM (deploy incremental).
# Uso: powershell -ExecutionPolicy Bypass -File scripts/commit-push-deploy-vm.ps1
#      powershell -ExecutionPolicy Bypass -File scripts/commit-push-deploy-vm.ps1 -CommitMessage "Minha mensagem"

param(
    [string]$CommitMessage = '',
    [string]$Branch = 'main',
    [string]$VmHost = '56.125.163.194',
    [string]$VmUser = 'ubuntu',
    [string]$AppDir = '/opt/pli-reporta',
    [string]$VmBaseUrl = 'https://pli-reporta.56-125-163-194.sslip.io',
    [string]$VmHealthUrl = 'https://pli-reporta.56-125-163-194.sslip.io/healthz',
    [switch]$SkipOpenBrowser
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
. (Join-Path $PSScriptRoot 'sync-lib.ps1')

function Write-Banner {
    Write-Host ''
    Write-Host '  PLI Reporta — publicar e atualizar a VM' -ForegroundColor Cyan
    Write-Host '  ----------------------------------------' -ForegroundColor DarkGray
    Write-Host ''
}

function Write-Stage {
    param(
        [int]$Number,
        [int]$Total,
        [string]$Title
    )
    Write-Host ''
    Write-Host ("  [{0}/{1}] {2}" -f $Number, $Total, $Title) -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host ("    OK  {0}" -f $Message) -ForegroundColor Green
}

function Write-Info([string]$Message) {
    Write-Host ("    ..  {0}" -f $Message) -ForegroundColor DarkGray
}

function Write-Warn([string]$Message) {
    Write-Host ("    !!  {0}" -f $Message) -ForegroundColor Yellow
}

function Get-AutoCommitMessage {
    $lines = @(git status --porcelain)
    if (-not $lines.Count) { return $null }

    $areas = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($line in $lines) {
        if ($line.Length -lt 4) { continue }
        $path = $line.Substring(3).Trim().Trim('"')
        if (-not $path) { continue }
        $top = ($path -replace '\\', '/' -split '/')[0]
        if ($top) { [void]$areas.Add($top) }
    }

    $list = @($areas | Sort-Object)
    if (-not $list.Count) {
        return 'Publica alteracoes locais.'
    }
    if ($list.Count -le 4) {
        return ('Publica alteracoes em {0}.' -f ($list -join ', '))
    }
    return ('Publica alteracoes em {0} e mais {1} area(s).' -f ($list[0..2] -join ', '), ($list.Count - 3))
}

function Invoke-VmRemoteStream {
    param(
        [string]$Command
    )
    $remote = Get-VmPlink
    $target = "${VmUser}@${VmHost}"
    $plinkArgs = $remote.Args + @($target, $Command)
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $remote.Plink @plinkArgs
    $exit = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    if ($exit -ne 0) {
        throw "Comando remoto falhou (codigo $exit)."
    }
}

function Test-SecretPaths {
    param([string[]]$Paths)
    foreach ($path in $Paths) {
        $name = Split-Path -Leaf $path
        if ($name -match '^\.env(\.|$)') {
            throw "Arquivo sensivel detectado ($path). Remova do stage antes de commitar."
        }
    }
}

$TotalStages = 6
Write-Banner

Write-Stage 1 $TotalStages 'Revisando o que mudou no projeto'
$changes = @(git status --porcelain)
if ($changes.Count -eq 0) {
    Write-Info 'Nenhuma alteracao local para commitar — seguimos para conferir GitHub e VM.'
} else {
    Write-Info ('{0} arquivo(s) com alteracao no controle de codigo:' -f $changes.Count)
    foreach ($line in $changes | Select-Object -First 12) {
        Write-Host ("         {0}" -f $line) -ForegroundColor DarkGray
    }
    if ($changes.Count -gt 12) {
        Write-Info ('... e mais {0} arquivo(s).' -f ($changes.Count - 12))
    }
}

Write-Stage 2 $TotalStages 'Gravando commit e enviando ao GitHub'
if ($changes.Count -gt 0) {
    if (-not $CommitMessage) {
        $CommitMessage = Get-AutoCommitMessage
        Write-Info ('Mensagem automatica: "{0}"' -f $CommitMessage)
    } else {
        Write-Info ('Mensagem informada: "{0}"' -f $CommitMessage)
    }

    git add -A
    if ($LASTEXITCODE -ne 0) { throw 'git add falhou.' }

    $staged = @(git diff --cached --name-only)
    Test-SecretPaths $staged

    git commit -m $CommitMessage
    if ($LASTEXITCODE -ne 0) { throw 'git commit falhou.' }
    Write-Ok ('Commit criado ({0}).' -f (git rev-parse --short HEAD))
} else {
    Write-Info 'Commit ignorado — nada novo para gravar.'
}

Write-Info 'Enviando branch para o GitHub...'
git push origin $Branch
if ($LASTEXITCODE -ne 0) { throw 'git push falhou — verifique rede e credenciais.' }
Write-Ok ('GitHub atualizado em {0}.' -f (git rev-parse --short HEAD))

Write-Stage 3 $TotalStages 'Alinhando o codigo na VM com o GitHub'
$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
git fetch origin $Branch 2>&1 | Out-Null
$ErrorActionPreference = $prevEap
$localSha = (git rev-parse HEAD).Trim()
$remoteSha = (git rev-parse "origin/$Branch").Trim()
if ($localSha -ne $remoteSha) {
    throw 'Laptop e GitHub ainda diferem apos o push — abortando deploy.'
}
Write-Ok ('Laptop e GitHub em {0}.' -f $localSha.Substring(0, 7))

Write-Info 'Conectando na VM e atualizando o repositorio...'
$pullCmd = "cd '$AppDir' && git fetch origin $Branch && git reset --hard origin/$Branch"
Invoke-VmRemoteStream -Command $pullCmd
Write-Ok 'Codigo na VM igual ao GitHub.'

Write-Stage 4 $TotalStages 'Aplicando deploy na VM (somente o que mudou)'
Write-Info 'Rodando update_vm.sh — rebuild do container so se necessario...'
Write-Host ''
$updateCmd = "cd '$AppDir' && bash '$AppDir/.deploy/update_vm.sh'"
Invoke-VmRemoteStream -Command $updateCmd
Write-Host ''
Write-Ok 'Script de deploy na VM concluido.'

Write-Stage 5 $TotalStages 'Aguardando o container ficar saudavel'
Write-Info 'Monitorando /healthz e paginas publicas...'
$runtimeOk = Test-VmRuntime -BaseUrl $VmBaseUrl -HealthUrl $VmHealthUrl -Label 'VM' -MaxAttempts 18 -DelaySeconds 5
if (-not $runtimeOk) {
    throw 'A VM respondeu, mas o container nao passou nos testes de saude.'
}
Write-Ok 'Container healthy e servicos publicos OK.'

Write-Stage 6 $TotalStages 'Conferindo sincronia final'
try {
    $vmSha = Get-VmCommitSha -VmHost $VmHost -VmUser $VmUser -AppDir $AppDir
    $deploySha = (Invoke-VmRemote -VmHost $VmHost -VmUser $VmUser -Command "tr -d '[:space:]' < $AppDir/.deploy/last_deploy_sha 2>/dev/null || echo MISSING").Trim()
    if ($vmSha -eq $localSha) {
        Write-Ok ('Git na VM: {0}' -f $vmSha.Substring(0, 7))
    } else {
        Write-Warn ('Git na VM ({0}) difere do GitHub ({1}).' -f $vmSha.Substring(0, 7), $localSha.Substring(0, 7))
    }
    if ($deploySha -eq $localSha) {
        Write-Ok ('Marcador de deploy: {0}' -f $deploySha.Substring(0, 7))
    } else {
        Write-Warn ('Marcador de deploy ({0}) difere do GitHub ({1}).' -f $deploySha.Substring(0, 7), $localSha.Substring(0, 7))
    }
} catch {
    Write-Warn ('Nao foi possivel confirmar SHA na VM: {0}' -f $_.Exception.Message)
    Write-Info 'O healthcheck passou — o deploy provavelmente esta correto.'
}

Write-Host ''
Write-Host '  Tudo pronto! VM sincronizada com o GitHub.' -ForegroundColor Green
Write-Host ("  Pagina inicial: {0}/" -f $VmBaseUrl.TrimEnd('/')) -ForegroundColor Green
Write-Host ("  Mapa publico:   {0}/mapa" -f $VmBaseUrl.TrimEnd('/')) -ForegroundColor DarkGray
Write-Host ''

if (-not $SkipOpenBrowser) {
    Open-AppInBrowser -BaseUrl $VmBaseUrl -Label 'PLI Reporta'
}

exit 0
