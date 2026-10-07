# 全量抓取流程（自己跑）

抓取 SIS 目录中**全部 114 个学科、约 3400 门课程**在
2025-26 Term 1 / 2025-26 Term 2 / 2026-27 Term 1 的
Session / Tutorial / 先修互斥信息，并导出三份 Excel。

预计耗时 **约 2–4 小时**（串行回发，视网络与课程班次数而定）。

---

## 0. 前置条件

| 要求 | 说明 |
|---|---|
| 网络 | **校内网或 VPN**。`sis.cuhk.edu.cn` 解析到 `10.20.232.57`，公网不可达 |
| Python | 3.10+，需要 `requests`、`beautifulsoup4`、`lxml`、`openpyxl` |
| 账号 | 你自己的 CUHK-SZ 账号（走 ADFS 单点登录，可能含 MFA） |
| 磁盘 | 约 200 MB（原始 JSON + Excel） |

先进入项目目录（下面所有命令都在这个目录里执行）：

```powershell
cd <仓库目录>\cuhk-sis-scraper
```

> 若在 DSH agent 的终端里执行，启动浏览器需要 `danger-full-access`；
> 在**普通 PowerShell 窗口**里执行则不需要任何额外授权，推荐后者。

---

## 1. 环境自检

```powershell
python check_ready.py
```

会逐层检查并打印结果：Python 依赖 → DNS → TCP → TLS → 浏览器 → 登录态。
核心项全部 `[ OK ]` 才继续。

常见输出含义：

- `[FAIL] DNS 解析` / `TCP 443 连通` → 没连校内网/VPN
- `[FAIL] TLS 握手 (legacy RSA)` → 网络中间有设备改写了 TLS（换网络重试）
- `[WARN] 调试浏览器未运行` → 只是警告；已有 Cookie 仍能抓，但长时间跑建议开着浏览器
- `[FAIL] SIS 登录态` → Cookie 过期，做第 2、3 步

---

## 2. 启动浏览器并登录（只需一次）

```powershell
python browser_launch.py
```

会弹出一个 Edge 窗口并打开 Browse Course Catalog。**在这个窗口里用你的 CUHK-SZ
账号完成 SSO 登录**，直到能正常看到课程目录页面。

- 用的是独立 profile（`_browser_profile/`），不影响你日常的浏览器
- 登录状态会保存在这个 profile 里，下次启动通常不用再登
- **整个抓取过程请保持这个窗口开着** —— 会话过期时脚本会自动从它重新取 Cookie

---

## 3. 导出登录 Cookie

```powershell
python grab_cookies.py
```

看到 `saved ...\_cookies.json` 即可。可再跑一次 `python check_ready.py` 确认登录态。

---

## 4. 全量抓取

先确认一遍要抓哪些学科（不会真的抓）：

```powershell
python run_scrape.py --all-subjects --skip-existing --dry-run
```

会输出 `skip-existing: 19 already done, 95 to go`（当前 CSC 等 19 个学科已完成）
以及待抓学科清单。确认无误后正式开始：

```powershell
python run_scrape.py --all-subjects --skip-existing 2>&1 | Tee-Object -FilePath _full_run.log
```

- `--all-subjects`：遍历目录里全部学科
- `--skip-existing`：**已有 `data/<学科>.json` 的学科直接跳过**（断点续跑的关键）
- `Tee-Object`：同时在屏幕显示并写入日志文件

每个学科会打印一行进度：

```
=== CSC (Computer Science) ===
    CSC (Computer Science): 151 courses
      [  1/151] CSC 1001     career=Undergraduate  secs= 24 posts=44
      ...
  -> 151 courses (56 UG), 295 sections, 0 errors, 0 not-in-catalog | saved CSC.json
```

**中途断了怎么办**：直接重新执行同一条命令。已完成的学科会跳过，从断点继续。
每个学科的 JSON 都是**先写临时文件再原子改名**，所以不会出现半截文件。

### 分批跑（可选）

不想一次跑几小时，可以按字母分批，每批跑完随时停：

```powershell
python run_scrape.py --all-subjects --skip-existing --letters A,B,C
python run_scrape.py --all-subjects --skip-existing --letters D,E,F,G
python run_scrape.py --all-subjects --skip-existing --letters H,I,J,K,L,M
python run_scrape.py --all-subjects --skip-existing --letters N,O,P,Q,R,S
python run_scrape.py --all-subjects --skip-existing --letters T,U,V,W,X,Y,Z,0,1,2,3,4,5,6,7,8,9
```

分批时同样带 `--skip-existing`，重复执行也不会重抓。

### 看看还剩多少

```powershell
(Get-ChildItem data\*.json).Count      # 已完成学科数（目标 114）
```

---

## 5. 导出 Excel

全部抓完后：

```powershell
python export_excel.py --all --prefix ALL_UG
```

`--all` 会自动读取 `data/` 下所有学科，产出**每学期一份**共三个文件：

```
output\ALL_UG_SIS_2025-26_Term_1.xlsx
output\ALL_UG_SIS_2025-26_Term_2.xlsx
output\ALL_UG_SIS_2026-27_Term_1.xlsx
```

每份含 5 个 sheet：

| Sheet | 内容 |
|---|---|
| `Sessions (课程安排)` | 非 Tutorial 班次：课程代码 / 课程名称 / Session序号 / Session编号 / Class Nbr / 周几 / 时间段 / 地点 / 老师 / 类型 / 状态 / 上课日期 / Career |
| `Tutorials (辅导课)` | TUT 班次（同样字段，另附老师） |
| `Enrollment (先修与互斥)` | Prerequisite 先修 / Exclusion 互斥 / 原始文本 |
| `Courses (全部UG课程)` | 全部本科课程基本信息与简介 |
| `说明 README` | 数据来源、统计、字段口径 |

> 全量导出时 `Sessions`/`Tutorials` 会有数万行、文件约 5–20 MB，Excel 打开稍慢属正常。
> 只想要某个学科时用 `--subject MAT,PHY`（见下）。

---

## 6. 只想导出一部分

```powershell
python export_excel.py --subject MAT,PHY,STA --prefix MATH_PHY
python export_excel.py --data-dir data --outdir output --all --prefix ALL_UG   # 等价于 --all
```

---

## 7. 抓完后的自检

```powershell
python verify_final.py     # 逐份打印 sheet 行数、各学科班次数、AIE/ECE 覆盖
```

或快速统计：

```powershell
python -c "import json,glob; d=[json.load(open(f,encoding='utf-8')) for f in glob.glob('data/*.json')]; print('学科',len(d),'课程',sum(len(x['courses']) for x in d),'本科',sum(1 for x in d for c in x['courses'] if c.get('career')=='Undergraduate'))"
```

---

## 8. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| `SIS session expired` / 一直重试 | Cookie 过期且浏览器已关闭。重跑第 2、3 步，保持浏览器开着 |
| 某学科 `!! ... failed` 后继续 | 该学科整体失败，其余不受影响。再跑一次 `--skip-existing` 会重试它 |
| 某门课 `!! CSC xxxx failed` | 单课失败会被记录在 JSON 的 `error` 字段里，不影响其它课 |
| 抓取很慢 | 正常。串行回发约 2.4 门课/秒下限，全量 2–4 小时 |
| 导出报 `invalid sheet title` | 已处理（自动清洗非法字符），若仍出现请把报错发我 |
| 想重抓某个学科 | 删掉 `data\<学科>.json` 再跑，例如 `Remove-Item data\MAT.json` |

---

## 9. 各阶段对应的文件

| 阶段 | 脚本 | 产物 |
|---|---|---|
| 自检 | `check_ready.py` | 控制台报告 |
| 登录 | `browser_launch.py` | `_browser_profile/` |
| 取 Cookie | `grab_cookies.py` | `_cookies.json` |
| 抓取 | `run_scrape.py` | `data/<学科>.json` |
| 导出 | `export_excel.py` | `output/*.xlsx` |
| 自检结果 | `verify_final.py` / `audit.py` | 控制台报告 |

更多技术细节（TLS、登录机制、字段口径、已知限制）见 `README.md`。
