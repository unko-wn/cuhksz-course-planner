# 课程目录解析报告 / Catalog build report

- 生成时间: 2026-10-07
- 课程总数: **926**
- 有课时数据的课程: 920 门（按学期见下表）
- 三个 xlsx 提及（含 Units/Language/Target Students）的课程: 662
- 通识课（Target Students = All UG Students，或前缀属于 CEC/GEA/GEB/GEC/GED/PED）: 198
- GEA/GEB/GEC/GED 系列: 73 门（统一 Y2-Y4 + 共修 GFH 1000 或 GFN 1000）；GFH/GFN 的 Y1 桥梁专业: MSAIN_DMP/JTMSN_JOT
- 学院限制来自 Target Students 原文的课程: 221（开设学院与限制学院不同的课程: 22）
- 仅点名专业/方向、可自由选课但需提示的课程（majorOnly）: 385
- 先修限制传递（先修全是学院限定课 -> 本课也受限）新增: 44 门（迭代 3 轮）
- 课程级覆盖: PED 全部限 Y1-Y1、CEC/CHI 系列改中文授课、PED 1101 清空先修

## 各学期

| 学期 | 可选 | xlsx 课时课程 | xlsx 辅导课课程 | 目录中有课时的课程 |
|---|---|---|---|---|
| 2025-26-T1 | 是 | 479 | 228 | 479 |
| 2025-26-T2 | 是 | 482 | 217 | 482 |
| 2026-27-T1 | 是 | 518 | 241 | 523 |
| 2026-27-T2 | 否 | 0 | 0 | 0 |

## 标签词表

- 特殊学生类型: INDAN, INDAZ, ASEIN, ASEIZ, MASEN, MASEZ
- 特殊专业/方向（93 个）: ACT, ACT-ADA, AESIN, AIE, AIE_MATH, APP_ECON, ASDSN_CDM, ASECN_CDM, ASEEN_CDM, ASEI_HSS, ASGRN_CDM, ASMEN_CDM, ASNEN_CDM, ASPYN_CDM, ASUMN_CDM, BDMA, BIFC, BIOL, BME, CHEM, CHM, CMED, CSE, CSE_IDA, DSBDT, DSBDT_ASEI, ECE, ECE-CE, ECE-EE, ECE-MESE, ECEN_IDA, ECO, ECO-ES_H, ECON_BE, EDU_PSY, EIE, EIE-EE, ENER, ENG, ENG_COMM, ENG_MEDIA, ENG_TECH, ENG_TRA, FE, FE-FT, FE-QF, FE_IDA, FIN, GBM, GBS, GSC, INCSN_CDM, INECN_CDM, INFEN_CDM, INSAN_CDM, INSTN_CDM, INTERNATIONAL, IOGG, JTMSN_JOT, MAT, MAT-FM, MATH, MATH_IDA, MATH_JOT, MKT, MSAIN_DMP, MSE, MSEN, MUSC, MUSM, MUSP, MUSP_BRAS, MUSP_COND, MUSP_PERC, MUSP_PIAN, MUSP_STGS, MUSP_VOCE, MUSP_WWDS, NSE, NSE-IEE, NSE-NEE, ORG_PSY, PHAM, PHY, PHYS_ASEI, PSY, SMU, STA, STAT, STAT_IDA, STA_IDA, TRA, UMGT

## 数据质量

- GE Target Students cells that spilled onto the next row: rejoined 1, row re-labelled 1
- major list: 31 programmes from build/major_map.json
- PDF1 rows=465 distinct codes=465; PDF2 rows=537 distinct codes=537
- 2025-26-T1: session courses=351 tutorial courses=161 catalog=1129
- 2025-26-T2: session courses=335 tutorial courses=131 catalog=1129
- 2026-27-T1: session courses=363 tutorial courses=159 catalog=1129
- supplement: 258 courses merged from SUPPLEMENT_sessions_tutorials.xlsx (columns: type at index 2)
- excluded placeholder records (Dummy/Exemption): 43 -> DUM 1000, DUM 1001, EXGBE 1001, EXGBE 1002, EXGBI 1001, EXGBI 1002 …
- deleted no-data courses from NO_DATA_courses.xlsx: 431 codes (431 of them existed in the catalogue)
- course universe = 926 (PDF1 465 + PDF2 537 + xlsx-only 529)
- durations present in data: [20, 30, 50, 80, 105, 110, 140, 170, 200, 230, 260]
- selectable=false sessions (IDV/RSC/CLN/EXM/THE): 614
- weekend (Sat/Sun) weekly slots: 24
- per-date overlapping slots collapsed to the widest one: 2 -> MED 2301A/L01 19:00-19:50, MED 2302A/L01 19:00-19:50
- 未能解析的 Target Students 字符串 1 种：
    - ×2 `S`
