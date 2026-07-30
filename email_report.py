#!/usr/bin/env python3
"""生成兼容主流邮件客户端的轻阅读 HTML 日报。"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import sys
from collections import Counter
from datetime import datetime

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(WORK_DIR, "output")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

TRACK_COLORS = {
    "foundation_models": ("#4f46e5", "#eef2ff"),
    "generative_design": ("#7c3aed", "#f5f3ff"),
    "protein_interactions": ("#be123c", "#fff1f2"),
    "protein_ligand": ("#c2410c", "#fff7ed"),
    "property_prediction": ("#b45309", "#fffbeb"),
    "structure_function": ("#0369a1", "#f0f9ff"),
    "ml_evolution": ("#7c3aed", "#f5f3ff"),
    "enzyme_engineering": ("#0f766e", "#f0fdfa"),
    "legacy_enzyme": ("#047857", "#ecfdf5"),
}


def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


def compact(text: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", text or "").strip()
    if len(value) <= limit:
        return value
    clipped = value[:limit]
    breakpoints = [clipped.rfind(mark) for mark in ("。", "；", ". ", "; ")]
    stop = max(breakpoints)
    if stop >= int(limit * 0.6):
        clipped = clipped[:stop + 1]
    else:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.rstrip("。.;； ") + "……"


def latest_data_file() -> str:
    candidates = []
    for prefix, priority in (("papers_raw_", 0), ("papers_translated_", 1)):
        for filename in os.listdir(OUTPUT_DIR):
            if filename.startswith(prefix) and filename.endswith(".json"):
                date_tag = filename[len(prefix):-5]
                path = os.path.join(OUTPUT_DIR, filename)
                candidates.append((os.path.getmtime(path), date_tag, priority, path))
    if not candidates:
        raise FileNotFoundError("未找到 papers_raw_*.json 或 papers_translated_*.json")
    return max(candidates)[3]


def load_latest_data() -> tuple[dict, str]:
    path = latest_data_file()
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle), path


def journal_text(paper: dict) -> str:
    info = paper.get("journal_info")
    if info:
        return f"{info['name']} · 中科院{info['cas_rank']} · IF {info['if']}"
    return paper.get("venue") or "期刊信息待核验"


def source_text(data: dict) -> str:
    enabled = data.get("enabled_sources") or []
    names = {"openalex": "OpenAlex", "pubmed": "PubMed", "crossref": "Crossref"}
    return "、".join(names.get(item, item) for item in enabled) if enabled else "OpenAlex"


def score_chips(paper: dict) -> str:
    breakdown = paper.get("score_breakdown") or {}
    chips = [("主题", breakdown.get("topic"))]
    if breakdown.get("methodology"):
        chips.append(("AI方法", breakdown["methodology"]))
    if breakdown.get("engineering"):
        chips.append(("酶工程", breakdown["engineering"]))
    chips.extend((
        ("期刊", breakdown.get("journal_scope")),
        ("新颖", breakdown.get("recency")),
    ))
    return "".join(
        f'<span class="score-chip">{esc(label)} {esc(value)}</span>'
        for label, value in chips if value is not None
    )


def gen_html(data: dict, now: datetime | None = None) -> str:
    now = now or datetime.now()
    papers = data.get("papers") or []
    date_tag = now.strftime("%Y-%m-%d")
    date_cn = now.strftime("%Y年%m月%d日")
    track_summary = data.get("track_summary") or dict(
        Counter(paper.get("track_label", "其他") for paper in papers)
    )
    family_summary = data.get("family_summary") or dict(Counter(
        "AI for Protein" if paper.get("topic_family") == "ai_for_protein" else "酶工程"
        for paper in papers
    ))
    failures = data.get("source_failures") or {}
    source_notice = ""
    if failures:
        source_notice = (
            '<div class="notice">部分数据源暂时不可用，本期已使用其余来源完成推荐：'
            + "、".join(esc(name) for name in failures)
            + "</div>"
        )

    overview_rows = []
    for index, paper in enumerate(papers, 1):
        color, pale = TRACK_COLORS.get(paper.get("track"), ("#475569", "#f1f5f9"))
        overview_rows.append(f"""
        <tr>
          <td class="overview-num">{index:02d}</td>
          <td class="overview-main">
            <a href="#paper-{index}" class="overview-title">{esc(paper.get('title'))}</a>
            <div class="overview-meta">
              <span style="color:{color};background:{pale}" class="mini-tag">{esc(paper.get('track_label'))}</span>
              {esc(paper.get('venue'))}
            </div>
          </td>
          <td class="overview-link"><a href="#paper-{index}">阅读</a></td>
        </tr>""")

    cards = []
    for index, paper in enumerate(papers, 1):
        color, pale = TRACK_COLORS.get(paper.get("track"), ("#475569", "#f1f5f9"))
        translated = paper.get("abstract_cn")
        if translated and translated != "[翻译失败]":
            abstract_label = "中文摘要速读"
            abstract_value = compact(translated, 460)
        else:
            abstract_label = "英文摘要速读"
            abstract_value = compact(paper.get("abstract", ""), 560)
        fit_level = (paper.get("journal_fit") or {}).get("level", "交叉方向")
        sources = " + ".join(paper.get("sources") or [paper.get("source", "")])
        link = paper.get("url") or (f"https://doi.org/{paper['doi']}" if paper.get("doi") else "")
        title = esc(paper.get("title"))
        title_html = f'<a href="{esc(link)}" target="_blank">{title}</a>' if link else title
        action = (
            f'<a class="doi-button" href="{esc(link)}" target="_blank">打开论文 / DOI&nbsp; →</a>'
            if link else ""
        )
        cards.append(f"""
        <div class="paper-card" id="paper-{index}">
          <div class="paper-topline" style="background:{color}"></div>
          <div class="paper-body">
            <div class="paper-kicker">
              <span class="rank" style="background:{color}">{index:02d}</span>
              <span class="track" style="color:{color};background:{pale}">{esc(paper.get('track_label'))}</span>
              <span class="kind">{esc(paper.get('article_kind', '研究论文'))}</span>
            </div>
            <h2>{title_html}</h2>
            <div class="meta">
              <strong>{esc(journal_text(paper))}</strong><br>
              {esc(paper.get('publication_date') or paper.get('year'))}
              &nbsp;·&nbsp; 引用 {esc(paper.get('citations', 0))}
              &nbsp;·&nbsp; {esc(fit_level)}
            </div>
            <div class="why" style="border-left-color:{color};background:{pale}">
              <div class="why-label" style="color:{color}">为什么推荐</div>
              <div>{esc(paper.get('recommendation_reason', 'AI方法与蛋白质任务匹配'))}</div>
              <div class="chips">{score_chips(paper)}</div>
            </div>
            <div class="abstract">
              <div class="section-label">{abstract_label}</div>
              <p>{esc(abstract_value) or '摘要暂未提供。'}</p>
            </div>
            <div class="authors"><strong>作者</strong>　{esc(paper.get('authors_short') or 'N/A')}</div>
            <div class="source-line">元数据来源：{esc(sources)}</div>
            <div class="actions">{action}<a class="back" href="#top">返回目录 ↑</a></div>
          </div>
        </div>""")

    track_chips = "".join(
        f'<span class="summary-chip">{esc(label)} <strong>{count}</strong></span>'
        for label, count in track_summary.items()
    )
    family_chips = "".join(
        f'<span class="summary-chip family-chip">{esc(label)} <strong>{count}</strong></span>'
        for label, count in family_summary.items()
    )
    translated_count = sum(
        bool(paper.get("abstract_cn") and paper.get("abstract_cn") != "[翻译失败]")
        for paper in papers
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>酶工程 + AI for Protein 每日文献 {date_tag}</title>
  <style>
    *{{box-sizing:border-box}} body{{margin:0;background:#eef2f7;color:#172033;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",Arial,sans-serif;font-size:16px;line-height:1.75}}
    a{{color:#1d4ed8;text-decoration:none}} .shell{{width:100%;padding:24px 10px}} .container{{max-width:720px;margin:0 auto}}
    .hero{{background:#102a43;color:#fff;border-radius:20px;padding:34px 30px 28px;box-shadow:0 10px 30px rgba(15,42,67,.18)}}
    .eyebrow{{font-size:12px;letter-spacing:1.8px;color:#9fd4ff;font-weight:700}} .hero h1{{margin:8px 0 6px;font-size:28px;line-height:1.3}}
    .hero-sub{{margin:0;color:#c9d8e8;font-size:14px}} .stats{{width:100%;margin-top:24px;border-collapse:separate;border-spacing:8px}}
    .stats td{{width:33.33%;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.12);border-radius:12px;padding:11px 8px;text-align:center;font-size:12px;color:#c9d8e8}}
    .stats strong{{display:block;color:#fff;font-size:21px;line-height:1.2}} .intro,.overview{{background:#fff;border:1px solid #dfe7f0;border-radius:16px;padding:22px;margin-top:16px}}
    .intro h2,.overview h2{{font-size:18px;margin:0 0 8px;color:#102a43}} .intro p{{margin:0;color:#526477;font-size:14px}}
    .summary-chips{{margin-top:13px}} .summary-chip{{display:inline-block;background:#f1f5f9;color:#334155;border-radius:999px;padding:4px 10px;margin:3px 5px 3px 0;font-size:12px}}
    .family-chip{{background:#e0f2fe;color:#075985;font-size:13px}}
    .notice{{margin-top:14px;background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;padding:10px 12px;border-radius:10px;font-size:13px}}
    .overview table{{width:100%;border-collapse:collapse}} .overview td{{border-top:1px solid #edf1f5;padding:11px 4px;vertical-align:middle}} .overview tr:first-child td{{border-top:0}}
    .overview-num{{width:38px;color:#64748b;font-weight:700}} .overview-title{{display:block;color:#1e293b;font-weight:700;line-height:1.45}}
    .overview-meta{{margin-top:4px;color:#64748b;font-size:12px}} .mini-tag{{display:inline-block;border-radius:999px;padding:1px 7px;margin-right:5px;font-weight:700}}
    .overview-link{{width:44px;text-align:right;font-size:13px;font-weight:700}} .paper-card{{background:#fff;border:1px solid #dfe7f0;border-radius:16px;margin-top:18px;overflow:hidden;box-shadow:0 4px 14px rgba(30,41,59,.05)}}
    .paper-topline{{height:5px}} .paper-body{{padding:24px 25px 22px}} .paper-kicker{{margin-bottom:11px}}
    .rank{{display:inline-block;color:#fff;border-radius:7px;padding:2px 8px;font-size:12px;font-weight:800;margin-right:5px}}
    .track,.kind{{display:inline-block;border-radius:999px;padding:2px 9px;font-size:12px;font-weight:700;margin:2px 4px 2px 0}} .kind{{background:#f1f5f9;color:#475569}}
    .paper-card h2{{font-size:21px;line-height:1.45;margin:0 0 10px;color:#172033}} .paper-card h2 a{{color:#172033}}
    .meta{{color:#607184;font-size:13px;line-height:1.7}} .meta strong{{color:#314256}}
    .why{{border-left:4px solid;border-radius:0 10px 10px 0;padding:12px 14px;margin:18px 0 15px;color:#27364a;font-size:14px}}
    .why-label,.section-label{{font-size:12px;font-weight:800;letter-spacing:.4px;margin-bottom:3px}} .chips{{margin-top:8px}}
    .score-chip{{display:inline-block;background:rgba(255,255,255,.72);border:1px solid rgba(100,116,139,.15);border-radius:6px;padding:1px 7px;margin:2px 5px 0 0;font-size:11px;color:#475569}}
    .abstract{{background:#f8fafc;border:1px solid #e7edf3;border-radius:11px;padding:14px 15px}} .section-label{{color:#475569}}
    .abstract p{{margin:2px 0 0;color:#334155;font-size:15px;line-height:1.8}} .authors{{margin-top:14px;color:#526477;font-size:13px}}
    .source-line{{margin-top:5px;color:#94a3b8;font-size:11px}} .actions{{margin-top:18px}}
    .doi-button{{display:inline-block;background:#1d4ed8;color:#fff!important;border-radius:9px;padding:9px 15px;font-weight:700;font-size:14px}}
    .back{{float:right;color:#64748b;font-size:12px;padding:9px 0}} .footer{{padding:24px 10px;text-align:center;color:#7b8b9b;font-size:12px}}
    @media(max-width:560px){{body{{font-size:15px}}.shell{{padding:10px 6px}}.hero{{padding:27px 20px 22px;border-radius:15px}}.hero h1{{font-size:23px}}
      .stats{{border-spacing:4px}}.stats td{{padding:9px 4px}}.intro,.overview{{padding:17px 15px;border-radius:13px}}.paper-body{{padding:20px 17px}}
      .paper-card h2{{font-size:18px}}.overview-link{{display:none}}.abstract p{{font-size:14px}}.back{{float:none;display:inline-block;margin-left:14px}}}}
  </style>
</head>
<body>
  <div class="shell"><div class="container" id="top">
    <div class="hero">
      <div class="eyebrow">DAILY RESEARCH BRIEF</div>
      <h1>酶工程 × AI for Protein</h1>
      <p class="hero-sub">{date_cn}　·　两个并列主题的最新 {len(papers)} 篇文献</p>
      <table class="stats" role="presentation"><tr>
        <td><strong>{len(papers)}</strong>今日精选</td>
        <td><strong>{esc(data.get('total_works', 0))}</strong>对口候选</td>
        <td><strong>{translated_count}</strong>中文速读</td>
      </tr></table>
    </div>
    <div class="intro">
      <h2>先看结论，再决定是否阅读全文</h2>
      <p>本期从 {esc(source_text(data))} 聚合候选，同时检索酶设计、改造、定向进化、生物催化和性能优化，以及蛋白质基础模型、生成式设计、相互作用、结合与性质预测。两类主题并列参与排序，共同选出最新 {len(papers)} 篇。</p>
      <div class="summary-chips">{family_chips}</div>
      <div class="summary-chips">{track_chips}</div>{source_notice}
    </div>
    <div class="overview"><h2>今日目录</h2><table role="presentation">{''.join(overview_rows)}</table></div>
    {''.join(cards)}
    <div class="footer">生成于 {now.strftime('%Y-%m-%d %H:%M')} · 自动推荐仅用于科研信息筛选<br>酶工程 + AI for Protein 每日文献系统</div>
  </div></div>
</body>
</html>"""


def main() -> None:
    data, source_path = load_latest_data()
    report = gen_html(data)
    date_tag = datetime.now().strftime("%Y-%m-%d")
    output_path = os.path.join(OUTPUT_DIR, f"daily_report_{date_tag}.html")
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(report)
    log.info("加载 %s；生成 %s", os.path.basename(source_path), output_path)
    print(f"[OK] HTML -> {output_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
    except Exception as exc:
        log.exception("HTML生成失败: %s", exc)
        sys.exit(1)
