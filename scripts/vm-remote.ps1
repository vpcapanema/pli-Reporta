function Get-VmPlink {
    $plink = @(
        (Get-Command plink.exe -ErrorAction SilentlyContinue).Source,
        "$env:ProgramFiles\PuTTY\plink.exe"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $plink) { throw 'PuTTY plink.exe nao encontrado' }
    $ppk = @(
        'D:\REPOSITORIOS\sigma-pli\chave_ppk\SRV-SISTEMA-30001480.ppk',
        'D:\REPOSITORIOS\PLI-HazardTrack\SRV-SISTEMA-30001480.ppk'
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $ppk) { throw 'Arquivo .ppk da VM nao encontrado' }
    @{
        Plink = $plink
        Ppk = $ppk
        Args = @('-batch', '-P', '22', '-i', $ppk)
    }
}

function Invoke-VmRemote {
    param(
        [string]$VmHost = '56.125.163.194',
        [string]$VmUser = 'ubuntu',
        [string]$Command
    )
    $remote = Get-VmPlink
    $target = "${VmUser}@${VmHost}"
    $out = & $remote.Plink @remote.Args $target $Command 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Comando remoto falhou (exit $LASTEXITCODE): $out"
    }
    if ($out -is [array]) { return ($out -join "`n") }
    return [string]$out
}
