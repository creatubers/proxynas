$ErrorActionPreference = 'Stop'
$workflow = Get-Content "$PSScriptRoot/.github/workflows/release.yml" -Raw
$extract = [regex]::Match($workflow, '(?ms)^          \$changelog = .*?(?=^          gh release view)').Value
if (-not $extract) { throw 'Release notes extraction not found' }
$env:RUNNER_TEMP = [IO.Path]::GetTempPath()
Push-Location $PSScriptRoot
try {
    foreach ($tag in @('v0.1.13', 'v0.1.12', 'v0.1.0')) {
        Invoke-Expression $extract
        $body = Get-Content -LiteralPath $notes -Raw
        if (-not $body.Trim() -or $body -match '### v|Install and troubleshooting') {
            throw "Incorrect release notes for $tag"
        }
    }
    $tag = 'v0.0.0'
    $rejected = $false
    try { Invoke-Expression $extract } catch { $rejected = $true }
    if (-not $rejected) { throw 'Missing changelog was accepted' }
    Write-Output 'test_release_notes: OK'
} finally {
    Pop-Location
}
