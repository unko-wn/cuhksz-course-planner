# CUHK-SZ SIS 课程数据爬虫

爬取香港中文大学（深圳）SIS（PeopleSoft）**Browse Course Catalog** 中的课程
session / tutorial / 先修互斥信息，并导出为 Excel。

---

## 一、可行性结论

**可行，但必须先登录。** 关键事实（均已实测验证）：

| 项目 | 结论 |
|---|---|
| 网络可达性 | `sis.cuhk.edu.cn` → `10.20.232.57`（**校内网 / VPN 才能访问**，公网 IP 不可达） |
| TLS | 服务端**只支持静态 RSA 密钥交换且不支持 TLS 1.3**；Python 3.13 默认 cipher list 已移除静态 RSA 套件，因此默认 `requests` 会 `SSLV3_ALERT_HANDSHAKE_FAILURE` |
| 游客访问 | **不可行**。门户外壳（Browse Catalog）可以匿名渲染，但 TargetContent iframe 内的组件始终被弹回门户外壳，0 个检索字段、无 `ICAction` |
| 认证方式 | CUHK-SZ **ADFS 单点登录**（`sts.cuhk.edu.cn/adfs/oauth2/authorize` → `myid.cuhk.edu.cn`，很可能含 MFA），无本地 PeopleSoft 账密表单 |
| 数据可得性 | 登录后 `SSS_BROWSE_CATLG` 组件**完全可用**：课程详情含 Enrollment Requirement（先修/互斥）与 Course Schedule（按学期列出 LEC/TUT 的星期、时间、地点、教师） |

因此：**数据本身完全可以爬，唯一的前提是复用你本人已登录的 SIS 会话。**

---

## 二、两个必须绕过的技术障碍

### 1. 旧版 TLS

服务端只接受静态 RSA 密钥交换（`AES128-GCM-SHA256` 这类），不支持 ECDHE，也不支持 TLS 1.3。
`sis_http.py` 中用一个自定义 `HTTPAdapter` 解决：

```python
ctx.set_ciphers("DEFAULT@SECLEVEL=1")          # 放开静态 RSA 套件
ctx.maximum_version = ssl.TLSVersion.TLSv1_2   # 服务端不支持 TLS1.3
```

### 2. 沙箱限制浏览器

DSH 沙箱（workspace-write）会拦截 Chromium 的 mojo 命名管道
（`platform_channel.cc: Check failed ... 拒绝访问 (0x5)`），浏览器**无法启动**。
因此启动 Edge 需要一次 `danger-full-access` 授权：

```powershell
python browser_launch.py          # 需要完整权限
```

浏览器只用于**登录一次**；之后的抓取全部走纯 HTTP（`requests`），速度快且无需授权。

---

## 三、实测结果

### 批次一：CSC 全量（测试批）

| 项目 | 结果 |
|---|---|
| CSC 课程总数 | 151（其中 **Undergraduate 56**，其余为 Postgraduate Taught） |
| 抓取耗时 | 248 秒 / 623 次 postback / **0 错误** |
| CSC UG 班次行数 | 三个学期共 **225** 行 |
| **准确性交叉验证** | 用真实浏览器点击得到的 CSC 1001（2025-26 T1）19 条记录与 HTTP 管线结果**逐字段完全一致（19/19）** |

### 批次二：培养方案（PDF）指定课程

按 `Study scheme - AI` 与 `Study Scheme - CSE` 两份 PDF 表格定向抓取，**不做全量**，
CSC 复用批次一结果不重复抓取，AIE 仅取指定 6 门。

| 项目 | 结果 |
|---|---|
| PDF 提取 | 无外部依赖自研解析器；AI 4 页 95 个课号，CSE 3 页 79 个课号 |
| 去重后目标 | 18 个学科 / **85 个课号**（已排除 34 个 CSC、21 个非白名单 AIE） |
| 实际抓取 | **80 门本科课程**，0 错误 |
| 合并后总量 | **231 门课程（136 门本科）**，三学期 **959** 条本科班次记录 |
| 完整性校验 | PDF 中无被空格拆散或漏掉的课号；137 个课号与 SIS 课程名逐条比对，仅 1 处为**课程改名**（非错配） |

### 三份 Excel 交付内容

| 学期 | Sessions | Tutorials | 覆盖学科 |
|---|---|---|---|
| 2025-26 Term 1 | 136 | 238 | CSC + 17 个培养方案学科 |
| 2025-26 Term 2 | 128 | 158 | 同上 |
| 2026-27 Term 1 | 139 | 160 | 同上（BIM/BIO 该学期无排课） |

---

## 四、工作原理

```
browser_launch.py   启动 Edge（持久 profile）→ 你手动完成 ADFS 登录
        │
grab_cookies.py     通过 CDP 从浏览器取出 Cookie（含 PS_TOKEN / PS_DEVICEFEATURES）
        │           → _cookies.json
        ▼
sis_scraper.py      用 Cookie 直接 POST PeopleSoft 组件，重放 ICAction 回发
        │           解析 CLASS_SECTION / MTGPAT_* / DERIVED_CRSECAT_DESCR254A
        ▼
data/<SUBJECT>.json 原始结构化数据
        │
export_excel.py     → 每个学期一个 xlsx
```

浏览器与 `requests` 共享同一套 Cookie，因此共享同一个 PeopleSoft 服务端会话；
`ICStateNum` / `ICSID` 由每次响应回传的值串起来，实现无界面连续翻页。

---

## 五、文件说明

| 文件 | 作用 |
|---|---|
| `sis_http.py` | requests 会话工厂（旧版 TLS 适配） |
| `cdp.py` / `browser_launch.py` | Chrome DevTools Protocol 驱动、启动带调试端口的 Edge |
| `browser_status.py` / `sisui.py` | 读取浏览器状态、在页面内执行 JS（探索与排错用） |
| `grab_cookies.py` | 从浏览器导出 SIS Cookie |
| `ps_fast.py` | Cookie 装载 + PeopleSoft 表单序列化 |
| `sis_scraper.py` | **核心抓取器**：目录导航、课程详情、按学期解析班次 |
| `run_scrape.py` | 命令行入口：按学科或按目标清单抓取并写 JSON |
| `export_excel.py` | 生成 Excel（每学期一份，含 5 个 sheet） |
| `pdf_extract.py` | 自研 PDF 文本提取（对象流 / Form XObject / CMap） |
| `extract_codes.py` / `build_targets.py` | 从培养方案 PDF 提取课号并生成 `targets.json` |
| `build_catalog_index.py` | 生成全目录索引 `catalog_index.json` |
| `validate_targets.py` | 逐条比对 PDF 课名与 SIS 课名，发现错配/改名 |
| `crossvalidate.py` | 用浏览器渲染结果交叉验证 HTTP 管线 |
| `data/*.json` | 抓取结果（按学科） |
| `targets.json` / `catalog_index.json` | 目标清单 / 目录索引 |
| `output/*.xlsx` | 最终交付的 Excel |

---

## 六、使用步骤

```powershell
# 1) 启动浏览器并登录（需要 danger-full-access 授权）
python browser_launch.py
#    在弹出的 Edge 窗口里用 CUHK-SZ 账号完成 SSO 登录，
#    确认能看到 Browse Course Catalog 页面

# 2) 导出登录 Cookie
python grab_cookies.py

# 3) 抓取（先跑 CSC 测试）
python run_scrape.py --subjects CSC
#    抓全部本科课程：  python run_scrape.py --all-subjects

# 4) 导出 Excel（每学期一份）
python export_excel.py --subject CSC
```

抓取脚本会在会话过期时**自动重新读取浏览器 Cookie** 并续跑。

---

## 七、按培养方案（PDF）定向抓取

只抓 PDF 表格里列出的课程，不做全量。

```powershell
# 1) 从 PDF 提取课号（自研解析器，无需安装任何库）
python extract_codes.py          # -> _pdf_codes.json
python build_targets.py          # 应用规则 -> targets.json

# 2) 定向抓取（仅这些课号）
python run_scrape.py --targets targets.json

# 3) 导出（CSC + 培养方案学科合并成三份）
python export_excel.py --prefix UG_Courses --data-dir data --outdir output `
       --subject ACT,AIE,BIM,BIO,BMA,CHM,CSC,DDA,ECE,ECO,EIE,ERG,FIN,MAT,MGT,MKT,MSE,PHY,STA
```

`targets.json` 形如 `{"MAT": ["1001","1011"], "AIE": ["1001","1901"]}`；
`scrape_subject(..., only={...})` 只访问列表内的课号，未在目录中的课号会单独汇总报告。

### PDF 课号提取

PDF 为 PDF 1.6，使用交叉引用流 + 对象流（ObjStm），正文在 Form XObject 内，
且中文列字体缺 ToUnicode 映射（中文显示为乱码）。`pdf_extract.py` 因此实现了：
对象流展开 → 资源字典解析 → Form XObject 递归 → 字体 CMap 解码。
英文课名与课号完整可靠，中文课名部分乱码（不影响课号提取）。

### 目录索引

`build_catalog_index.py` 生成 `catalog_index.json`（114 学科 / 3429 门课），
用于把 PDF 课号对照到 SIS 实际课程。**每次展开学科前必须重新解析链接 id**，
因为 PeopleSoft 的链接 id 是按位置生成的，任何一次回发后都会失效。

---

## 八、输出字段

每个学期一个工作簿，包含 4 个 sheet：

**Sessions（课程安排）** — 非 Tutorial 的教学班次
`课程代码 / 课程名称 / Session序号 / Session编号 / Class Nbr / 周几 / 时间段 / 地点(Room) / 老师(Instructor) / 类型 / 开课状态 / 上课日期 / Career`

**Tutorials（辅导课）** — TUT 班次
`课程代码 / 课程名称 / Session序号 / Session编号 / Class Nbr / 周几 / 时间段 / 地点(Room) / 老师 / 开课状态 / 上课日期`

**Enrollment（先修与互斥）**
`课程代码 / 课程名称 / Career / 学分 / Prerequisite 先修 / Exclusion 互斥 / Enrollment Requirement 原始文本`

**Courses（全部UG课程）**
`课程代码 / 课程名称 / Career / 学分 / 开课学院 / 授课语言 / 课程简介`

---

## 九、字段口径与注意事项

- **只导出 `Career = Undergraduate`** 的课程；研究生课程会被过滤。
- **Session序号** 是 PeopleSoft 的 session number（通常为 1）；
  **Session编号** 形如 `L01-LEC` / `T01-TUT`，才是区分班次的标识。
- 一个班次若有**多个上课时段**（例如 CSC 3001 某班一周两次不同时间），会**输出多行**，
  以保证「周几-时间段-地点」三者严格对应。
- 时间段统一为 **24 小时制 `HH:MM-HH:MM`**。SIS 在不同渲染路径下会返回
  `08:30` 或 `8:30AM`，脚本已统一；未排课的班次显示为 `TBA`。
- 上课日期统一为 **ISO `YYYY-MM-DD - YYYY-MM-DD`**。SIS 返回的是
  `09/01/2025 - 12/12/2025` 这类美式格式，容易误读，脚本已转换。
- 仅包含该课程在所选学期**确实开课**的班次；未开课的学期不会出现在该表中。
- `PS_TOKEN` 有有效期。长时间抓取时若失效，脚本会自动从仍开着的浏览器重新取 Cookie；
  若浏览器被关闭，则需重新执行第 1、2 步。
- 抓取为**串行**且带 0.12s 间隔，对 SIS 压力很小；全量抓取会耗时较久，建议分批。

---

## 十、已知限制

1. **CSC 5010（Artificial Intelligence）无法抓取。** 该课程标注 `*** view multiple offerings`，
   即同一课号存在多个 career 的 offering。**真实浏览器点击同样只会退回课程列表**
   （已实测确认），属于 SIS 自身的交互缺陷，非爬虫问题。因此该课在 CSC 批次中
   `career` 为空并被排除在 Excel 之外。
2. **未排课的课程不产生班次行。** 例如 CSC 3102 的详情页显示
   `*** This course has not been scheduled. ***`，因此只有先修/互斥信息，没有班次。
   56 门 UG 课程中有 22 门在目标三学期内没有排课记录，属正常情况。
3. 抓取依赖登录会话。若长期未操作导致 `PS_TOKEN` 失效，脚本会自动从浏览器重新取 Cookie；
   若浏览器已关闭则需重跑第 1、2 步。

### 培养方案（PDF）与 SIS 目录不一致的课程

两份培养方案里有 5 个课号在 SIS 目录中**不存在**，逐个核查结果如下：

| PDF 中的课号 | 课程名 | 核查结论 |
|---|---|---|
| `EIE3280` | Networks: Technology, Economics and Society | **已改挂 ECE 3280**（课名完全一致）→ 已按 `ECE 3280` 抓取 |
| `EIE4512` | Digital Image Processing | **已改挂 ECE 4512**（课名完全一致）→ 已按 `ECE 4512` 抓取 |
| `BMA3001` | Data Analytics for Business | 全目录 3429 门课中**不存在**；BMA 学科下仅有 BMA 2010 |
| `BMA3011` | Introduction to System Analysis and Design | 全目录**不存在** |
| `ECE4320` | Hardware Acceleration for Efficient AI Computing | 全目录**不存在**（应尚未开课/未入库） |

另有 1 处**课程改名**（课号不变）：`FIN3380` 培养方案写 *Introduction to Financial Data Analysis*，
SIS 现为 *Financial Data Analysis with AI Tools* —— 已按 SIS 现行名称抓取。

---

## 十一、扩展到全部学科

`run_scrape.py --all-subjects` 会遍历目录里的全部学科（当前 114 个）。
已确认的学科列表可由 `discover_subjects()` 输出。
由于 PeopleSoft 是状态机、必须串行回发，全量抓取耗时较长，可按字母或学院分批执行：

```powershell
python run_scrape.py --subjects CSC,CIE,ECE,MAT,PHY   # 分批
python export_excel.py --subject CSC,CIE,ECE,MAT,PHY  # 合并导出
```
