<#
.SYNOPSIS
    두 폴더의 파일을 재귀적으로 비교. 한쪽에만 있는 파일 / 내용이 다른 파일을 리포트.
.EXAMPLE
    .\Compare-SqlFolders.ps1 -Left "D:\내PC\sql" -Right "C:\배포\sql"
    .\Compare-SqlFolders.ps1 -Left A -Right B -Filter *.sql -IgnoreWhitespace -ShowDiff
.NOTES
    종료코드: 0 = 완전 동일, 1 = 차이 있음  (배치/자동화에서 활용)
#>
param(
    [Parameter(Mandatory=$true)][string]$Left,
    [Parameter(Mandatory=$true)][string]$Right,
    [string]$Filter = "*.sql",       # 비교 대상 (전체 파일이면 *)
    [switch]$IgnoreWhitespace,        # CRLF/LF·줄끝 공백·BOM·빈줄 차이 무시
    [switch]$ShowDiff                 # 다른 파일은 실제 라인 차이까지 출력
)

function Get-NormHash([string]$path, [bool]$ignoreWs) {
    if (-not $ignoreWs) {
        return (Get-FileHash -Path $path -Algorithm SHA256).Hash
    }
    # 공백/개행 정규화: BOM 제거 → 각 줄 오른쪽 공백 제거 → LF 통일 → 끝 빈줄 제거
    $text = [System.IO.File]::ReadAllText($path)
    $text = $text -replace "^\uFEFF", ""
    $lines = $text -split "\r?\n" | ForEach-Object { $_.TrimEnd() }
    $joined = ($lines -join "`n").TrimEnd()
    $bytes  = [System.Text.Encoding]::UTF8.GetBytes($joined)
    $sha    = [System.Security.Cryptography.SHA256]::Create()
    return ([BitConverter]::ToString($sha.ComputeHash($bytes)) -replace "-", "")
}

foreach ($p in @($Left, $Right)) {
    if (-not (Test-Path $p)) { Write-Error "경로 없음: $p"; exit 2 }
}

$leftRoot  = (Resolve-Path $Left).Path
$rightRoot = (Resolve-Path $Right).Path

# 상대경로 기준 맵 구성 (대소문자 무시)
function Get-Map([string]$root) {
    $map = @{}
    Get-ChildItem -Path $root -Recurse -File -Filter $Filter | ForEach-Object {
        $rel = $_.FullName.Substring($root.Length).TrimStart('\','/')
        $map[$rel.ToLower()] = $_.FullName
    }
    return $map
}

$L = Get-Map $leftRoot
$R = Get-Map $rightRoot

$onlyLeft  = @()
$onlyRight = @()
$different = @()
$same      = 0

foreach ($rel in ($L.Keys + $R.Keys | Sort-Object -Unique)) {
    $inL = $L.ContainsKey($rel)
    $inR = $R.ContainsKey($rel)
    if ($inL -and -not $inR) { $onlyLeft  += $rel; continue }
    if ($inR -and -not $inL) { $onlyRight += $rel; continue }

    $hL = Get-NormHash $L[$rel] $IgnoreWhitespace
    $hR = Get-NormHash $R[$rel] $IgnoreWhitespace
    if ($hL -eq $hR) { $same++ }
    else { $different += $rel }
}

# ---- 리포트 ----
Write-Host ""
Write-Host "====== 폴더 비교 결과 ======" -ForegroundColor Cyan
Write-Host "LEFT : $leftRoot"
Write-Host "RIGHT: $rightRoot"
Write-Host "필터 : $Filter   공백무시: $IgnoreWhitespace"
Write-Host ""
Write-Host ("동일        : {0}" -f $same) -ForegroundColor Green
Write-Host ("내용 다름   : {0}" -f $different.Count) -ForegroundColor Yellow
Write-Host ("LEFT에만    : {0}" -f $onlyLeft.Count)  -ForegroundColor Magenta
Write-Host ("RIGHT에만   : {0}" -f $onlyRight.Count) -ForegroundColor Magenta
Write-Host ""

if ($different.Count) {
    Write-Host "--- 내용 다른 파일 ---" -ForegroundColor Yellow
    $different | ForEach-Object { Write-Host "  ~ $_" }
}
if ($onlyLeft.Count) {
    Write-Host "--- LEFT에만 있는 파일 ---" -ForegroundColor Magenta
    $onlyLeft | ForEach-Object { Write-Host "  < $_" }
}
if ($onlyRight.Count) {
    Write-Host "--- RIGHT에만 있는 파일 ---" -ForegroundColor Magenta
    $onlyRight | ForEach-Object { Write-Host "  > $_" }
}

if ($ShowDiff -and $different.Count) {
    Write-Host ""
    Write-Host "====== 라인 차이 상세 ======" -ForegroundColor Cyan
    foreach ($rel in $different) {
        Write-Host ""
        Write-Host "### $rel" -ForegroundColor Yellow
        $a = Get-Content $L[$rel]
        $b = Get-Content $R[$rel]
        Compare-Object $a $b -SyncWindow 3 |
            ForEach-Object {
                $side = if ($_.SideIndicator -eq '<=') { 'L' } else { 'R' }
                Write-Host ("  [{0}] {1}" -f $side, $_.InputObject)
            }
    }
}

Write-Host ""
if ($different.Count -or $onlyLeft.Count -or $onlyRight.Count) {
    Write-Host "=> 차이 있음" -ForegroundColor Red
    exit 1
} else {
    Write-Host "=> 두 폴더 완전 동일" -ForegroundColor Green
    exit 0
}
