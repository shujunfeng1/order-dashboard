# 在线业务数据看板

通过企业邮箱自动获取Excel附件，生成可公开访问的静态业务看板。项目由GitHub Actions运行，不依赖个人电脑开机。

## 线上看板

| 看板 | 地址 | 更新频率 |
|---|---|---|
| 卡单数据看板 | https://shujunfeng1.github.io/order-dashboard/ | 每日9:30、10:00（北京时间） |
| 客户登录、拜访及转化看板 | https://shujunfeng1.github.io/order-dashboard/customer-login-dashboard.html | 每日10:50、13:20、16:45（北京时间） |

两个页面顶部均提供看板切换入口，筛选、指标、图表和明细表保持一致的操作体验。

## 项目能力

- 通过IMAP SSL连接企业邮箱并下载指定Excel附件。
- 自动识别当天最新邮件，解析中文主题和附件名称。
- GitHub Actions按北京时间定时运行，电脑关机不影响更新。
- 自动清洗空值、按客户ID去重、聚合并生成静态JSON。
- GitHub Pages托管页面，数据更新后自动发布。
- 支持手动触发工作流和本地Excel回归验证。

## 数据链路

~~~text
企业邮箱
  ├─ 卡单邮件 → pipeline/run_pipeline.py
  │              └─ docs/dashboard_data.json + 可下载卡单明细
  └─ 今日登录客户明细 → pipeline/run_customer_login_pipeline.py
                         └─ docs/customer_login_data.json（仅聚合数据）
                                      ↓
                              GitHub Pages 双看板
~~~

登录客户附件包含客户ID、客户名称等业务信息。该附件只在GitHub Actions临时目录中处理，处理结束后自动销毁，仓库和GitHub Pages不会保存或公开原始客户明细。

## 邮件规则

### 卡单数据

配置位于 config/settings.json，当前按主题关键词获取卡单Excel附件。

### 客户登录、拜访及转化数据

配置位于 config/customer_login_settings.json：

- 发件人：hm.lu@ybm100.com
- 主题格式：【今日登录客户明细】YYYY-MM-DD-HH-MM
- 附件格式：今日登录客户明细_YYYY-MM-DD-HH-MM.xlsx
- 报表时间：10:45、13:15、16:40
- 获取时间：10:50、13:20、16:45

程序先按发件人与日期范围检索，再在本地解码中文主题，避免部分IMAP服务器对中文SUBJECT搜索支持不稳定。每个更新时段会校验对应报表是否已经到达；若邮件延迟，工作流会间隔60秒重试，仍未到达则明确失败并保留上一版线上数据。

## 登录看板指标口径

- 登录客户数：按客户ID去重。
- 拜访客户数：是否拜访、是否上门拜访、是否电话拜访任一为“是”。
- 加购客户数：去重客户中是否加购为“是”。
- 下单客户数：去重客户中是否下单为“是”。
- 拜访覆盖率：拜访客户数 / 登录客户数。
- 下单转化率：下单客户数 / 登录客户数。
- 业态：客户类型为“连锁”或“批发”时归入“连锁”，单体和诊所归入“单体”。
- 空白大区：统一归入“公海”。
- 重复客户：同一客户多行记录按行为字段取“或”，大区、省份和业态取最后一条记录。

## 项目结构

~~~text
.github/workflows/
  update-dashboard.yml                 卡单看板定时更新
  update-customer-login-dashboard.yml  登录看板每日三次更新
config/
  settings.json                        卡单配置
  customer_login_settings.json         登录看板邮件与Sheet配置
pipeline/
  email_reader.py                      卡单邮件读取
  run_pipeline.py                      卡单数据管道
  customer_login_email.py              登录邮件检索与附件下载
  customer_login_processor.py          登录数据去重与聚合
  run_customer_login_pipeline.py       登录看板管道入口
docs/
  index.html                           卡单数据看板
  dashboard_data.json                  卡单看板数据
  customer-login-dashboard.html        登录、拜访及转化看板
  customer_login_data.json             登录看板聚合数据
tests/
  test_customer_login_pipeline.py      登录管道单元测试
~~~

## GitHub Secrets

仓库Settings → Secrets and variables → Actions中需要配置：

| Secret | 说明 |
|---|---|
| IMAP_SERVER | 企业邮箱服务器 |
| IMAP_PORT | IMAP SSL端口，通常为993 |
| EMAIL_ACCOUNT | 邮箱账号 |
| EMAIL_PASSWORD | IMAP授权码，不是网页登录密码 |

授权码不得写入JSON、Python、README、日志或Git提交。

## GitHub Actions时间

GitHub Actions cron使用UTC时区：

| 工作流 | 北京时间 | UTC cron |
|---|---|---|
| 卡单看板 | 09:30 | 30 1 * * * |
| 卡单看板 | 10:00 | 0 2 * * * |
| 登录看板 | 10:50 | 50 2 * * * |
| 登录看板 | 13:20 | 20 5 * * * |
| 登录看板 | 16:45 | 45 8 * * * |

GitHub定时任务可能有数分钟排队延迟，页面显示的是邮件主题中的报表时间，不是Actions启动时间。

## 本地验证

安装依赖：

~~~bash
pip install -r requirements.txt
~~~

使用本地附件生成登录看板数据：

~~~bash
python pipeline/run_customer_login_pipeline.py "path/to/今日登录客户明细.xlsx" --output web/static/customer_login_data.json
~~~

使用IMAP读取真实邮件时，通过环境变量设置IMAP_SERVER、IMAP_PORT、EMAIL_ACCOUNT、EMAIL_PASSWORD，然后执行：

~~~bash
python pipeline/run_customer_login_pipeline.py --require-current-slot
~~~

运行测试：

~~~bash
python -m unittest discover -s tests -v
~~~

启动静态服务：

~~~bash
python -m http.server 8766 --directory web/static
~~~

访问 dashboard.html 或 customer-login-dashboard.html。

## 手动运行与排查

- GitHub仓库 → Actions → 选择对应工作流 → Run workflow。
- 登录看板工作流失败时，先检查邮件是否按时到达，再检查Secrets是否有效。
- 页面保留上一版JSON；新数据校验失败时不会覆盖线上可用版本。
- Actions日志只输出主题时间和聚合数量，不输出客户明细或授权码。

## 发布机制

工作流只在数据内容发生变化时提交新版本。GitHub Pages从docs目录发布；提交后通常需要几十秒到数分钟完成刷新。

## 2026-07-20 客户登录看板上线复盘

### 本次完成

- 将“客户登录、拜访及转化看板”从原型迁入GitHub Pages正式站点。
- 卡单看板与登录转化看板增加双向切换导航，并保留卡单看板已有的去重客户数指标。
- 使用企业邮箱IMAP授权码在GitHub Actions中直连邮箱，摆脱对个人电脑开机状态的依赖。
- 每天北京时间10:50、13:20、16:45获取对应的10:45、13:15、16:40报表。
- 真实附件60607行，经客户ID去重后60589人；拜访3377人、加购22264人、下单19103人。
- 登录看板只发布110组大区/省区/业态聚合数据，不发布客户ID、客户名称或原始附件。
- 首次线上手动运行成功，重复运行时能识别数据未变化并跳过提交。

### 已确认的业务与数据口径

| 项目 | 最终规则 |
|---|---|
| 客户去重 | 按客户ID全局去重，重复行的行为字段取“或” |
| 重复客户归属 | 大区、省份、业态取最后一条记录，与确认过的原型一致 |
| 拜访定义 | 是否拜访、是否上门拜访、是否电话拜访任一为“是” |
| 业态映射 | 客户类型为“连锁”或“批发”归入连锁；“单体”或“诊所”归入单体 |
| 空白大区 | 统一显示为“公海” |
| 页面时间 | 展示邮件主题/附件中的报表时间，同时在JSON保留实际收件时间 |
| 数据发布 | 只提交聚合JSON；原始Excel仅在Actions临时目录处理 |

### 实施中踩过的坑

| 问题 | 表现与原因 | 最终处理 |
|---|---|---|
| 中文IMAP主题搜索不稳定 | 直接使用SUBJECT检索时可能返回0封邮件 | 先按日期和发件人做ASCII检索，再在程序中解码并匹配中文主题 |
| 只核对总指标不够 | 总登录/拜访/加购/下单一致，但分组数量曾从原型110组变成186组 | 将真实管道输出与原型按“大区+省区+业态”逐组比较，校准业态映射和重复客户归属 |
| Excel大文件解析超时 | 通用工作簿解析器处理6MB、6万行文件连续超时 | 生产管道使用pandas/openpyxl；只读核验使用openpyxl read_only |
| Excel文件句柄未关闭 | Windows完成解析后无法删除临时附件 | 使用with pd.ExcelFile(...)确保工作簿及时关闭 |
| 中文路径/字面量乱码 | PowerShell管道内联Python时中文路径或字符串被错误编码 | 路径通过环境变量传入，比较值必要时使用Unicode转义 |
| 图表横轴自动省略标签 | 窄屏下北部大区、中部大区名称消失 | ECharts设置axisLabel.interval=0，分类较多时轻微旋转 |
| 主分支被自动任务更新 | 开发期间Actions更新main，PR出现冲突 | 以最新origin/main为基线重放功能提交，保留最新数据文件 |
| CRLF导致整页差异 | 合并HTML时换行格式变化，PR显示近千行无意义修改 | 保留原文件换行格式，只提交真实导航变更；后续建议用.gitattributes统一策略 |
| GitHub网络偶发超时 | git push第一次失败 | 保持提交不变后重试，使用force-with-lease仅更新已重写的功能分支 |
| Actions重复提交 | 同一邮件重复运行可能产生无意义提交 | JSON中的更新时间使用稳定的邮件收件时间；内容不变时跳过commit |

### 上线验证基线

以后修改邮件链路、指标口径或页面时，至少完成以下验证：

1. 使用真实邮件验证IMAP登录、主题筛选、当前时段校验和附件下载。
2. 校验附件只有一个Sheet，并检查必需字段是否齐全。
3. 核对原始行数、去重客户数、拜访/加购/下单人数。
4. 将聚合结果与已确认版本按“大区+省区+业态”逐组比较。
5. 检查customer_login_data.json仅包含允许的聚合字段。
6. 运行Python编译检查和tests目录下的单元测试。
7. 在桌面和约639px窄屏下验证导航、筛选、图表、表格和横向溢出。
8. 合并后手动触发GitHub Actions，确认Runner可通过Secrets独立完成更新。
9. 等待Pages部署成功后，直接访问线上两个页面做最终验收。

### 后续优化清单

- 增加工作流失败通知，邮件未到、字段变化或数据异常时主动提醒。
- 增加数据质量阈值，例如总行数突降、核心指标为0、字段缺失时阻止发布。
- 增加不含客户明细的更新时间历史，支持查看一天三次报表的趋势和变化量。
- 为聚合JSON增加schema_version，方便未来字段升级和前端兼容。
- 定期升级actions/checkout与actions/setup-python，消除GitHub Runner的Node版本弃用提示。
- 在仓库增加.gitattributes，统一HTML、Python、YAML和JSON的换行策略。
- 评估是否将两条邮件管道抽象成配置驱动的通用框架，减少重复代码。

## 相关链接

- GitHub仓库：https://github.com/shujunfeng1/order-dashboard
- GitHub Pages：https://shujunfeng1.github.io/order-dashboard/
- Actions：https://github.com/shujunfeng1/order-dashboard/actions
