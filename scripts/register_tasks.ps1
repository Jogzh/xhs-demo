# 一键注册/查看/删除 Windows 计划任务（管理员 PowerShell 运行）
#   powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1 -Action register
#   powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1 -Action remove
param([ValidateSet("register", "remove", "list")][string]$Action = "register")

$ErrorActionPreference = "Stop"
$proj = "D:\Desktop\py_proj\xhs-demo"

# 发布任务：每天 10:30；回流任务：每天 09:05
$tasks = @(
    @{ Name = "xhs-agent-daily-publish"; Time = "10:30"; Bat = "run_daily.bat" },
    @{ Name = "xhs-agent-daily-metrics"; Time = "09:05"; Bat = "run_metrics.bat" }
)

switch ($Action) {
    "register" {
        foreach ($t in $tasks) {
            $exists = schtasks /Query /TN $t.Name 2>$null
            if ($LASTEXITCODE -eq 0) {
                schtasks /Change /TN $t.Name /TR "`"$proj\scripts\$($t.Bat)`"" /ST $t.Time | Out-Null
                Write-Host "已更新: $($t.Name) -> 每天 $($t.Time)"
            } else {
                schtasks /Create /TN $t.Name /TR "`"$proj\scripts\$($t.Bat)`"" `
                    /SC DAILY /ST $t.Time /F | Out-Null
                Write-Host "已注册: $($t.Name) -> 每天 $($t.Time)"
            }
        }
        Write-Host "`n注意：任务默认交互运行（弹浏览器窗口），风控更稳。"
        Write-Host "立即手动验证：schtasks /Run /TN xhs-agent-daily-metrics"
    }
    "remove" {
        foreach ($t in $tasks) { schtasks /Delete /TN $t.Name /F 2>$null; Write-Host "已删除: $($t.Name)" }
    }
    "list" {
        foreach ($t in $tasks) { schtasks /Query /TN $t.Name /V /FO LIST 2>$null | Select-String "任务名|状态|下次运行|要运行的任务|TaskName|Status|Next Run|Task To Run" }
    }
}
