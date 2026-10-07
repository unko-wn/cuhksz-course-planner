# 把本仓库推送到 GitHub
# 用法（在**你自己的** PowerShell 窗口里运行，不要在受限沙箱里跑）：
#   powershell -ExecutionPolicy Bypass -File .\push-to-github.ps1
#   powershell -ExecutionPolicy Bypass -File .\push-to-github.ps1 -Owner unko-wn
#
# 前提：先在 https://github.com/new 建一个**空**仓库（不要勾选 README / .gitignore / License）。

param(
    [string]$Owner,
    [string]$RepoName = 'cuhk-course-planner'
)

# 关键：不要用 'Stop'。git 在正常分支（例如 remote 还不存在）也会往 stderr 写 error，
# 配合 Stop 会被当成终止性错误把脚本打断——上一版报 "No such remote 'origin'" 就是这个原因。
# 统一改成显式检查 $LASTEXITCODE。
$ErrorActionPreference = 'Continue'

if (-not (git rev-parse --is-inside-work-tree 2>$null)) {
    Write-Host '当前目录不是 git 仓库，请在仓库根目录（含 course-planner.html 那层）运行。' -ForegroundColor Red
    exit 1
}

if (-not $Owner) { $Owner = (Read-Host 'GitHub 用户名（例如 unko-wn）').Trim() }
if (-not $Owner) { Write-Host '未填写用户名。' -ForegroundColor Red; exit 1 }

$branch = git branch --show-current
if (-not $branch) { $branch = 'main' }
$url = "https://github.com/$Owner/$RepoName.git"

Write-Host ''
Write-Host "仓库：  $url"
Write-Host "分支：  $branch（HEAD $(git rev-parse --short HEAD)）"
Write-Host ''

# 1) 配置 remote：用 git remote 的列表判断，而不是 git remote get-url
$remotes = @(git remote)
if ($remotes -contains 'origin') {
    git remote set-url origin $url
    Write-Host "已更新 origin -> $url"
} else {
    git remote add origin $url
    Write-Host "已添加 origin -> $url"
}

# 2) 推送（首次会弹 GitHub 登录窗口，或要求 Personal Access Token 作为密码）
Write-Host '正在推送…'
git push -u origin $branch

if ($LASTEXITCODE -eq 0) {
    Write-Host ''
    Write-Host "完成：https://github.com/$Owner/$RepoName" -ForegroundColor Green
    exit 0
}

Write-Host ''
Write-Host '推送失败，按提示对照处理：' -ForegroundColor Yellow
Write-Host "  1) 远端仓库不存在 -> 先去 https://github.com/new 建一个空的 $RepoName（不要初始化 README）"
Write-Host '  2) 认证失败 401/403 -> 用 Personal Access Token 当密码，或先执行：'
Write-Host '       git config --global credential.helper manager'
Write-Host "  3) 远端已有提交 -> 先 git pull --rebase origin $branch 再重试"
Write-Host '  4) 仍报 schannel / SEC_E_NO_CREDENTIALS -> 当前终端也在受限环境里，改用开始菜单里的普通 PowerShell'
exit 1
