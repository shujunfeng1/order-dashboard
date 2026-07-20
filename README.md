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

## 相关链接

- GitHub仓库：https://github.com/shujunfeng1/order-dashboard
- GitHub Pages：https://shujunfeng1.github.io/order-dashboard/
- Actions：https://github.com/shujunfeng1/order-dashboard/actions
