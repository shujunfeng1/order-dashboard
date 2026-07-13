# 卡单数据看板

每日自动从企业邮箱读取带 Excel 附件的邮件，解析数据后生成可视化看板，部署为公网可访问的网页，支持筛选、下载明细。电脑关机也能自动更新。

---

## 项目背景

业务团队每天早上会收到一封包含卡单（异常订单）数据的 Excel 附件邮件。之前需要人工下载附件、用 Excel 做透视表、截图发群，效率低且容易遗漏。

本项目将整个流程自动化：定时读取邮件 → 解析 Excel → 生成数据看板 → 自动更新网页，团队成员直接打开链接即可查看最新数据。

---

## 线上地址

| 环境 | 地址 | 说明 |
|------|------|------|
| **GitHub Pages（主）** | https://shujunfeng1.github.io/order-dashboard/ | 永久链接，电脑关机也能自动更新 |
| 本地开发 | http://localhost:5000 | Flask 开发服务器 |

---

## 技术方案

### 整体架构

```
企业邮箱 (IMAP)
    │
    │  每日 9:30 / 10:00 自动触发
    ▼
GitHub Actions (Ubuntu Runner)
    │
    ├── 1. 连接邮箱 (imaplib, SSL, UTF-8)
    ├── 2. 搜索主题含「【卡单】【数据】」的当天邮件
    ├── 3. 下载 .xlsx 附件
    ├── 4. pandas 解析 + 字段映射 + 空白填充
    ├── 5. 聚合计算 (KPI + 图表 + 聚合表 + 明细)
    ├── 6. 输出 JSON + Excel 到 docs/
    └── 7. git commit & push → GitHub Pages 自动更新
```

### 技术栈

| 模块 | 技术 | 说明 |
|------|------|------|
| 邮件读取 | Python `imaplib` + `email` | IMAP SSL，支持中文主题搜索 |
| Excel 解析 | `pandas` + `openpyxl` | 读取 .xlsx，字段映射，数据清洗 |
| 数据处理 | `pandas` | 多维聚合，去重计数，GMV 求和 |
| 看板前端 | HTML + ECharts 5.5 (CDN) | 纯静态，无框架依赖 |
| 字体 | Noto Serif SC (Google Fonts) | 衬线体标题，商务风格 |
| 定时调度 | GitHub Actions (cron) | UTC 时区，北京时间 +8 |
| 网页托管 | GitHub Pages | 从 docs/ 目录自动部署 |
| 本地开发 | Flask | 开发调试用，非生产 |

### 项目结构

```
order-dashboard/
├── .env.example                     # 凭据模板（复制为 .env 使用）
├── .gitignore                       # 排除 .env、运行时数据
├── requirements.txt                 # Python 依赖（含 python-dotenv）
├── run_all.py                       # 一键执行：管道 + Flask
├── sync_to_github.py                # 同步脚本：根目录 -> github/
├── config/
│   └── settings.json                # 字段映射、看板配置（不含密码）
├── pipeline/                        # 数据管道（主代码）
│   ├── email_reader.py              #   IMAP 邮件读取 + 附件下载
│   ├── excel_parser.py              #   Excel 解析 + 字段映射 + 清洗
│   ├── data_processor.py            #   聚合计算 + JSON 生成
│   └── run_pipeline.py              #   管道主入口
├── web/                             # Flask 本地开发
│   ├── app.py                       #   Flask 服务
│   ├── static/dashboard.html        #   静态看板主文件（GitHub Pages 源）
│   ├── templates/dashboard.html     #   Flask 版看板模板
│   └── static/                      #   本地数据文件
├── skill/                           # 可复用技能包
│   └── ...
└── github/                          # 远程仓库源（由 sync_to_github.py 同步）
    ├── .github/workflows/update-dashboard.yml
    ├── config/settings.json         #   脱敏版
    ├── docs/                        #   GitHub Pages 根目录
    │   ├── index.html               #   由 sync 生成
    │   └── dashboard_data.json
    ├── pipeline/                    #   由 sync 同步
    └── requirements.txt
```

> **同步机制**：根目录为开发主目录，改完代码后运行 `python sync_to_github.py` 一键同步到 `github/`，再从 `github/` 推送到远程仓库。

---

## 数据字段说明

### Excel 原始字段映射

数据来源：邮件附件 Excel，Sheet 名「累计卡单」，约 850 条/天。

| 看板字段 | Excel 列 | 列名 | 取值逻辑 | 备注 |
|---------|---------|------|---------|------|
| 大区 | T 列 | `大区` | 直接取值，空白→"公海" | 约 15 条空白 |
| 省区 | D 列 | `客户省份` | 直接取值，空白→"公海" | 当前无空白 |
| 组别 | S 列 | `下单BD组别` | 直接取值，空白→"公海" | 约 15 条空白 |
| 客户数 | A 列 | `客户ID` | 按分组**去重计数** | 全局约 797 |
| 卡单订单数 | E 列 | `订单编号` | **计数**（非去重） | 全局 850，无重复 |
| 涉及销售数 | Q 列 | `下单BD工号` | 按分组**去重计数** | 全局约 434 |
| 涉及实付GMV | G 列 | `实付GMV` | **求和**，保留 2 位小数 | 全局约 ¥102 万 |
| 业绩归属 | O 列 | `业绩归属` | 直接取值，用于筛选和饼图 | POP / 自营 / 控销 |
| 异常原因分类 | N 列 | `异常原因分类` | 直接取值，用于筛选和柱状图 | 客户异常/资质过期 等 |

### KPI 卡片

| KPI | 计算方式 |
|-----|---------|
| 卡单订单数 | `len(df)` 或 `订单编号.count()` |
| 客户数 | `客户ID.nunique()` |
| 涉及销售数 | `下单BD工号.nunique()` |
| 涉及实付GMV | `实付GMV.sum()`，保留 2 位小数 |

### 聚合表

按 `大区 → 客户省份 → 下单BD组别` 三级分组，每组计算：
- 客户数（去重）
- 卡单订单数（计数）
- 涉及销售数（去重）
- 涉及实付GMV（求和）

### 筛选器联动

三个筛选器（大区 / 业绩归属 / 异常原因分类）选择后，KPI 卡片、图表、聚合表、明细表全部同步刷新。筛选在前端 JS 完成，无需请求后端。

---

## 看板设计

### 页面布局

```
┌─────────────────────────────────────────────────┐
│  Header: 卡单数据看板 | 更新时间 | 下载明细 | 导出  │
├──────────┬──────────┬──────────┬─────────────────┤
│ 卡单订单数 │  客户数   │ 涉及销售数 │  涉及实付GMV    │
├──────────┴──────────┴──────────┴─────────────────┤
│  筛选器: 大区 | 业绩归属 | 异常原因 | 重置          │
├──────────────┬──────────────┬────────────────────┤
│ 大区卡单分布   │ 异常原因分类   │   业绩归属分布      │
│ (柱状图)      │ (横向柱状图)   │   (环形图)         │
├──────────────┴──────────────┴────────────────────┤
│  Tab: 聚合表 | 明细数据                           │
│  ┌────────────────────────────────────────────┐  │
│  │  数据表格（排序、分页、搜索）                  │  │
│  └────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### 设计规范

- **配色**：白底 + 深蓝 `#1A365D` + 金色 `#C4A35A` + 橙色 `#C04A1A`
- **字体**：标题和数字用 Noto Serif SC（衬线体），正文用系统无衬线字体
- **布局**：细线分隔代替阴影，无圆角，编辑风格
- **表格**：深蓝表头白字、隔行浅灰 `#F5F5F5`、首列衬线体深蓝色
- **图表**：深蓝柱状图、金色横向柱状图、环形图配底部图例
- **响应式**：1024px 以下平板适配，640px 以下手机适配

---

## 邮箱配置

### IMAP 连接参数

| 参数 | 值 |
|------|------|
| IMAP 服务器 | `mail.ybm100.com` |
| 端口 | 993 (SSL) |
| 账号 | `shujunfeng@ybm100.com` |
| 认证方式 | IMAP 授权码（非登录密码） |
| 主题关键词 | `【卡单】【数据】` |
| 附件关键词 | `.xlsx` |
| 邮件到达时间 | 每日约 09:03 |

### GitHub Secrets 配置

在仓库 Settings → Secrets and variables → Actions 中设置：

| Secret 名称 | 值 |
|-------------|------|
| `IMAP_SERVER` | mail.ybm100.com |
| `IMAP_PORT` | 993 |
| `EMAIL_ACCOUNT` | shujunfeng@ybm100.com |
| `EMAIL_PASSWORD` | IMAP 授权码 |

> **注意**：本地开发时，凭据写在 `config/settings.json` 中（已加入 .gitignore 不上传）。GitHub Actions 中通过环境变量注入，代码会优先读取环境变量。

---

## GitHub Actions 工作流

### 触发时间

| 触发时间（北京时间） | Cron (UTC) | 说明 |
|---------------------|------------|------|
| 09:30 | `30 1 * * *` | 首次尝试 |
| 10:00 | `0 2 * * *` | 兜底（9:30 邮件未到时补跑） |

### 工作流步骤

1. 检出代码 (`actions/checkout@v4`)
2. 设置 Python 3.11 (`actions/setup-python@v5`)
3. 安装依赖 (`pip install -r requirements.txt`)
4. 执行数据管道（环境变量注入邮箱凭据）
5. 提交更新的 JSON 和 Excel 文件（`git commit & push`）

### 手动触发

在 GitHub 仓库 → Actions → "更新卡单看板数据" → Run workflow 可手动触发。

### 查看运行日志

```
gh run list --workflow=update-dashboard.yml
gh run view <run-id>
```

---

## 本地开发

### 环境要求

- Python 3.11+
- pip

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置邮箱凭据

```bash
cp .env.example .env
# 编辑 .env，填入真实的 IMAP 授权码
```

> `.env` 已在 `.gitignore` 中排除，不会提交到 Git。GitHub Actions 通过 Secrets 注入。

### 本地运行管道（使用本地 Excel 文件）

```bash
cd order-dashboard
python pipeline/run_pipeline.py "path/to/excel.xlsx"
```

### 本地运行管道（从邮箱读取）

确保 `.env` 已配置，然后：

```bash
python pipeline/run_pipeline.py
```

### 启动 Flask 开发服务器

```bash
python web/app.py
# 访问 http://localhost:5000
```

### 同步代码到 GitHub 仓库

改完根目录代码后，同步到 `github/` 远程仓库目录：

```bash
python sync_to_github.py          # 同步
python sync_to_github.py --check  # 仅检查差异
```

同步后进入 `github/` 目录提交并推送即可。

### 修改看板样式

编辑 `web/templates/dashboard.html`（Flask 版）或 `docs/index.html`（GitHub Pages 版），两个文件保持同步。

主要修改点：
- **颜色变量**：CSS `:root` 中的 `--dark-blue`、`--gold`、`--accent` 等
- **图表配色**：JS 中的 `CHART_COLORS` 数组
- **字段/列**：HTML 中的 `<th>` 和 JS 中的 `updateAggTable`、`updateDetailTable` 函数

---

## 踩坑记录

### 1. IMAP 中文主题搜索

**问题**：`imaplib` 默认使用 ASCII 编码，搜索中文邮件主题时报错 `could not parse command`。

**解决**：
```python
mail._encoding = "utf-8"
mail.search("UTF-8", "SUBJECT", '"【卡单】【数据】"')
```

### 2. 日期搜索的时区问题

**问题**：IMAP 的 `ON` 日期搜索使用服务器时区，GitHub Actions runner 是 UTC 时区，北京时间 9:30 对应 UTC 1:30，此时 IMAP 服务器的"今天"可能还是昨天。

**解决**：搜索逻辑加了三层兜底——先搜今天，没结果搜昨天，再没结果取最近所有匹配邮件的最新一封。

### 3. GitHub Actions 定时时区

**问题**：GitHub Actions 的 cron 使用 UTC 时区，需要转换。

**解决**：北京时间 = UTC + 8。9:30 北京 = `30 1 * * *` UTC，10:00 北京 = `0 2 * * *` UTC。

### 4. GitHub Pages 首次部署延迟

**问题**：首次启用 Pages 后，页面可能需要 1-2 分钟才能访问。

**解决**：通过 GitHub API 检查 Pages 状态，`status: "built"` 表示部署完成。

### 5. 端口占用（本地开发）

**问题**：Flask 开发服务器异常退出后，端口 5000 被旧进程占用。

**解决**：用 PowerShell `Get-NetTCPConnection -LocalPort 5000` 查找占用进程，`Stop-Process -Id <pid> -Force` 杀掉。

### 6. 空白值处理

**问题**：Excel 中大区、组别等字段有空白值，导致聚合时出现 `NaN`。

**解决**：在 `excel_parser.py` 中统一处理——`fillna("公海")` + `replace("", "公海")` + `replace("nan", "公海")`。

### 7. JSON 序列化

**问题**：pandas 的 `NaN`、`Timestamp` 等类型无法直接 JSON 序列化。

**解决**：在 `data_processor.py` 中逐行处理，`NaN` 转空字符串，`float` 保留 2 位小数，其他转为 Python 原生类型。

### 8. 饼图标签重叠

**问题**：异常原因分类的标签较长（如"客户异常/资质过期"），饼图图例和饼图本身重叠。

**解决**：将异常原因从饼图改为横向柱状图，标签放在 Y 轴，数值标在柱状条右侧。

---

## 扩展方向

| 方向 | 说明 | 实现思路 |
|------|------|---------|
| 历史趋势 | 展示多日数据变化趋势 | 引入 SQLite，每日数据入库，看板增加折线图 |
| 多日对比 | 选择日期范围对比 | 日期选择器 + 后端聚合 API |
| 权限控制 | 看板需要密码访问 | 前端 JS 简单密码验证 或 GitHub Pages 加密 |
| 邮件通知 | 看板更新后发通知 | GitHub Actions 中增加发邮件步骤 |
| 多邮件源 | 支持多封邮件汇总 | email_reader 支持配置多个搜索条件 |
| 数据校验 | 自动检查数据异常 | pipeline 中增加数据质量检查步骤 |

---

## 相关链接

- **GitHub 仓库**：https://github.com/shujunfeng1/order-dashboard
- **GitHub Pages 看板**：https://shujunfeng1.github.io/order-dashboard/
- **Actions 运行记录**：https://github.com/shujunfeng1/order-dashboard/actions
- **ECharts 文档**：https://echarts.apache.org/zh/index.html
- **GitHub Actions 文档**：https://docs.github.com/en/actions
