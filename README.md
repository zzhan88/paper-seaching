# 酶工程 + AI for Protein 每日文献推送

每天自动从多个学术数据源检索两个并列主题：**酶工程**或 **AI for Protein**。系统从两类合格候选中综合新近度、主题相关性和质量，选出 10 篇最新论文，通过邮件推送轻阅读日报。

## 推荐逻辑

系统不再把“出现 enzyme、protein 或 AI”直接视为相关。候选论文需要依次通过：

1. **多源召回**：OpenAlex、PubMed、Crossref 并行检索；单个来源失败不会中断其他来源。
2. **统一去重**：优先使用规范化 DOI；无 DOI 时使用规范化标题。
3. **双主题并列准入**：
   - 酶工程：包含酶/生物催化对象，以及设计、改造、定向进化、筛选、固定化或性能评价行为。
   - AI for Protein：包含蛋白质对象、AI 方法和明确的蛋白质任务。
4. **同尺度专业评分**：AI 论文按新模型、框架、预训练和表征学习评分；酶工程论文按改造行为、活性/稳定性/选择性和实验验证评分。两类论文均可进入前 10。
5. **任务覆盖**：覆盖蛋白质基础模型、生成式设计、蛋白–蛋白相互作用、蛋白–小分子结合、结构/功能预测、活性/稳定性/选择性预测和 AI 辅助酶工程。
6. **原创研究优先**：综述、观点和文献计量文章会降权，每天最多 2 篇。
7. **多样性控制**：同一期刊优先最多 2 篇、同一技术赛道优先最多 4 篇；如果不足 10 篇，则从其余合格候选按总分补足，不对酶工程设置数量上限。

每条推荐都会保存主题类别、技术赛道、期刊对口度、推荐理由，以及“主题/AI方法或酶工程/期刊/时效”分项得分，便于审查。

## 邮件阅读体验

- 首屏明确标注“酶工程 × AI for Protein”，并显示精选数量、对口候选数量和中文摘要数量。
- 目录可跳转到对应论文。
- 每篇论文先显示推荐理由和中文速读摘要，再提供 DOI 按钮。
- 不依赖 JavaScript 或兼容性不稳定的折叠交互，适配手机、QQ 邮箱、Gmail 和 Outlook。
- 测试邮件会添加 `[测试]` 前缀，不写回历史去重记录。

## 运行流程

```text
recommendation_engine.py  多源检索、去重、AI方法准入、评分与任务多样性选取
translate.py              使用 DeepSeek 翻译摘要
email_report.py           生成邮件兼容的 HTML 日报
format_wechat.py          生成微信公众号 Markdown
format_xiaohongshu.py     生成小红书文案
send_email.py             通过 QQ SMTP 发送
run_all.py                串联以上步骤
```

`daily_paper_list.py` 和 `format_html.py` 保留为现有工作流的兼容入口，分别调用新版推荐引擎和邮件生成器。

## GitHub Secrets

| Secret | 必需 | 用途 |
|---|---:|---|
| `QQ_EMAIL` | 是 | QQ 邮箱发件地址，同时作为 Crossref polite pool 联系邮箱 |
| `QQ_EMAIL_AUTH_CODE` | 是 | QQ 邮箱 SMTP 授权码 |
| `RECIPIENT_EMAIL` | 是 | 收件地址 |
| `DEEPSEEK_API_KEY` | 建议 | 中文摘要翻译；失败时邮件自动使用英文速读摘要 |
| `NCBI_API_KEY` | 否 | 提高 PubMed E-utilities 速率上限 |

不要把任何密钥、邮箱授权码或访问令牌写入代码、工作流文件或 Git remote URL。

## 本地验证

```bash
python -m py_compile *.py tests/*.py
python -m unittest discover -s tests -v
```

真实检索会访问外部学术 API：

```bash
set IGNORE_SEEN=1
python daily_paper_list.py
python format_html.py
```

## GitHub Actions

- 定时任务：每天北京时间 10:00 自动执行正式推送。
- 手动任务：在 Actions 中运行“每日文献推送”，默认启用测试模式。
- 测试模式：忽略历史论文但不修改 `seen_papers.json`，确保能够收到一封用于检查内容和版式的邮件。
