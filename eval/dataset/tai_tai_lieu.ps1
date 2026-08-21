# Tải tài liệu kiểm thử từ nguồn công khai.
#
# Chỉ tải văn bản pháp quy và quy chế công khai — xem docs/CHUAN-BI-DU-LIEU.md §3.
# Tệp gốc KHÔNG commit; xuất xứ ghi vào eval/dataset/NGUON.md.
#
#   pwsh eval/dataset/tai_tai_lieu.ps1
#   pwsh eval/dataset/tai_tai_lieu.ps1 -DanhSach my-list.csv

param(
    [string]$DanhSach = "$PSScriptRoot\nguon.csv",
    [string]$DichThuMuc = "$PSScriptRoot\documents",
    [int]$TimeoutSec = 60
)

$ErrorActionPreference = 'Continue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

if (-not (Test-Path $DanhSach)) {
    Write-Host "Không thấy danh sách: $DanhSach" -ForegroundColor Red
    exit 1
}

$rows = Import-Csv $DanhSach
$ok = @(); $fail = @()

foreach ($r in $rows) {
    $dir = Join-Path $DichThuMuc $r.nhom
    New-Item -ItemType Directory -Force $dir | Out-Null
    $dest = Join-Path $dir $r.ten

    if (Test-Path $dest) {
        Write-Host "  [bỏ qua] $($r.ten) — đã có" -ForegroundColor DarkGray
        $ok += [pscustomobject]@{ten=$r.ten; nhom=$r.nhom; url=$r.url; kb=[math]::Round((Get-Item $dest).Length/1KB)}
        continue
    }

    try {
        Invoke-WebRequest -Uri $r.url -OutFile $dest -TimeoutSec $TimeoutSec `
            -UserAgent "Mozilla/5.0 (compatible; DocuMind-research/1.0)" `
            -MaximumRedirection 5 -ErrorAction Stop | Out-Null
    }
    catch {
        Write-Host "  [LỖI]    $($r.ten) — $($_.Exception.Message)" -ForegroundColor Red
        $fail += [pscustomobject]@{ten=$r.ten; url=$r.url; loi=$_.Exception.Message}
        if (Test-Path $dest) { Remove-Item $dest -Force }
        continue
    }

    # Xác minh theo NỘI DUNG, không theo phần mở rộng — cùng nguyên tắc với
    # US-006 AC-5. Nhiều trang trả về trang HTML báo lỗi với đuôi .pdf.
    $head = [System.IO.File]::ReadAllBytes($dest)[0..4]
    $magic = -join ($head | ForEach-Object { [char]$_ })
    $kb = [math]::Round((Get-Item $dest).Length / 1KB)

    if ($magic -ne '%PDF-' -and $r.ten -like '*.pdf') {
        Write-Host "  [KHÔNG PHẢI PDF] $($r.ten) — nhận được '$magic' ($kb KB)" -ForegroundColor Yellow
        $fail += [pscustomobject]@{ten=$r.ten; url=$r.url; loi="không phải PDF (magic='$magic')"}
        Remove-Item $dest -Force
        continue
    }
    if ($kb -lt 20) {
        Write-Host "  [QUÁ NHỎ] $($r.ten) — $kb KB, nghi là trang lỗi" -ForegroundColor Yellow
        $fail += [pscustomobject]@{ten=$r.ten; url=$r.url; loi="chỉ $kb KB"}
        Remove-Item $dest -Force
        continue
    }

    Write-Host "  [OK]     $($r.ten) — $kb KB" -ForegroundColor Green
    $ok += [pscustomobject]@{ten=$r.ten; nhom=$r.nhom; url=$r.url; kb=$kb}
}

Write-Host ""
Write-Host "Tải được $($ok.Count)/$($rows.Count) tệp." -ForegroundColor Cyan
if ($fail.Count) {
    Write-Host "Thất bại $($fail.Count):" -ForegroundColor Yellow
    $fail | ForEach-Object { Write-Host "  $($_.ten): $($_.loi)" }
    Write-Host "Những tệp này cần tải tay từ trình duyệt." -ForegroundColor Yellow
}

$ok | Export-Csv "$PSScriptRoot\da_tai.csv" -NoTypeInformation -Encoding UTF8
Write-Host "Danh sách đã tải → eval/dataset/da_tai.csv"
