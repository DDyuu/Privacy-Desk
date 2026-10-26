# 隐盾 PrivacyDesk 一键构建脚本（Windows PowerShell）
# 产物：release/ 下的 NSIS 安装包与免安装文件。
$ErrorActionPreference = "Stop"

# 国内网络下加速 Electron 与 electron-builder 二进制下载（已设置则尊重现有值）
if (-not $env:ELECTRON_MIRROR) {
    $env:ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"
}
if (-not $env:ELECTRON_BUILDER_BINARIES_MIRROR) {
    $env:ELECTRON_BUILDER_BINARIES_MIRROR = "https://npmmirror.com/mirrors/electron-builder-binaries/"
}

$Root = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $Root "frontend"
$Backend = Join-Path $Root "backend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
$PyInstaller = Join-Path $Backend ".venv\Scripts\pyinstaller.exe"
$Npm = "npm.cmd"
$Npx = "npx.cmd"

function Fail {
    param([string]$Step)
    Write-Host "构建失败：$Step" -ForegroundColor Red
    exit 1
}

function Assert-Exit {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        Fail $Step
    }
}

if (-not (Test-Path $Python)) {
    Fail "未找到后端虚拟环境：$Python（请先创建 backend\.venv 并安装依赖）"
}
if (-not (Test-Path $PyInstaller)) {
    Fail "未找到 PyInstaller：$PyInstaller（请执行 pip install -e "".[dev]""）"
}

Write-Host "[1/10] 安装前端依赖" -ForegroundColor Cyan
Push-Location $Frontend
if (Test-Path (Join-Path $Frontend "package-lock.json")) {
    & $Npm ci --no-audit --no-fund
} else {
    & $Npm install --no-audit --no-fund
}
Assert-Exit "前端依赖安装"
Pop-Location

Write-Host "[2/10] 构建前端静态资源" -ForegroundColor Cyan
Push-Location $Frontend
& $Npm run build
Assert-Exit "前端构建"
Pop-Location

Write-Host "[3/10] 运行后端全量测试" -ForegroundColor Cyan
Push-Location $Backend
& $Python -m pytest -q
Assert-Exit "后端测试"
Pop-Location

Write-Host "[4/10] 生成加密资源 rules.enc 与源码清单" -ForegroundColor Cyan
Push-Location $Backend
& $Python "build\encrypt_resources.py"
Assert-Exit "加密资源生成"
Pop-Location

Write-Host "[5/10] PyInstaller 打包后端" -ForegroundColor Cyan
Push-Location $Backend
& $PyInstaller "build\pyinstaller.spec" --noconfirm
Assert-Exit "PyInstaller 打包"
Pop-Location

Write-Host "[6/10] 复制加密资源并为冻结产物生成完整性清单" -ForegroundColor Cyan
Push-Location $Backend
& $Python "build\encrypt_resources.py" "dist\privacy-backend"
Assert-Exit "冻结产物清单"
Pop-Location

Write-Host "[7/10] 校验完整性清单" -ForegroundColor Cyan
$ManifestInternal = Join-Path $Backend "dist\privacy-backend\_internal\manifest.json"
$EncryptedRules = Join-Path $Backend "dist\privacy-backend\_internal\resources\rules.enc"
if (-not (Test-Path $ManifestInternal)) {
    Fail "未找到冻结产物清单：$ManifestInternal"
}
if (-not (Test-Path $EncryptedRules)) {
    Fail "未找到加密资源：$EncryptedRules"
}
$Exe = Join-Path $Backend "dist\privacy-backend\privacy-backend.exe"
if (-not (Test-Path $Exe)) {
    Fail "未找到后端可执行文件：$Exe"
}
Write-Host "    manifest: $ManifestInternal" -ForegroundColor DarkGray

Write-Host "[8/10] 安装 Electron 依赖" -ForegroundColor Cyan
Push-Location $Root
if (Test-Path (Join-Path $Root "package-lock.json")) {
    & $Npm ci --no-audit --no-fund
} else {
    & $Npm install --no-audit --no-fund
}
Assert-Exit "Electron 依赖安装"
Pop-Location

Write-Host "[9/10] electron-builder 生成 Windows 安装包" -ForegroundColor Cyan
Push-Location $Root
& $Npx electron-builder --win --x64 --config.win.signAndEditExecutable=false
Assert-Exit "electron-builder"
Pop-Location

Write-Host "[10/10] 输出产物目录" -ForegroundColor Cyan
$Release = Join-Path $Root "release"
if (-not (Test-Path $Release)) {
    Fail "未生成 release 目录"
}
Get-ChildItem $Release | Select-Object Name, Length
Write-Host "构建完成：$Release" -ForegroundColor Green
