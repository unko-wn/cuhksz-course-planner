# 把本仓库推送到 GitHub
# 用法：在**你自己的 PowerShell 窗口**里运行（不要在受限沙箱里跑，沙箱会拦截 TLS 凭据）
#   powershell -ExecutionPolicy Bypass -File .\push-to-github.ps1
#
# 前提：先在 https://github.com/new 建一个**空**仓库（不要勾选 README / .gitignore / License），
#       名字建议 cuhk-course-planner，可见性按你的选择（public 或 private）。

$ErrorActionPreference = 'Stop'
$repoName = 'cuhk-course-planner'
$owner    = Read-Host "GitHub 用户名（例如 unko-wn）"
$visibility = Read-Host "仓库可见性 public/private（你之前选了 public，直接回车即可）"
if ([string]::IsNullOrWhiteSpace($visibility)) { $visibility = 'public' }

$url = "https://github.com/$owner/$repoName.git"
Write-Host "`n将推送到 $url`n" -ForegroundColor Cyan

# 1) 若还没有 remote，加上
if (-not (git remote get-url origin 2>$null)) {
    git remote add origin $url
} else {
    git remote set-url origin $url
}

# 2) 推送（第一次会弹出 GitHub 登录窗口或要求 Personal Access Token）
git push -u origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n完成：https://github.com/$owner/$repoName" -ForegroundColor Green
} else {
    Write-Host "`n推送失败。常见原因与处理：" -ForegroundColor Yellow
    Write-Host "  - 仓库不存在：先去 https://github.com/new 建一个空的 $repoName"
    Write-Host "  - 认证失败：用 Personal Access Token 当密码，或 `git config --global credential.helper manager`"
    Write-Host "  - 远端已有提交：git pull --rebase origin main 后重试"
}
