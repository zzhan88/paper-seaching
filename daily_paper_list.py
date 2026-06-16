#!/usr/bin/env python3
"""AI+酶工程 每日文献清单生成器 (v3 - 每日更新版)"""
import json, logging, os, sys, time, traceback
from datetime import datetime, timedelta
from typing import Any, Optional
import requests

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(WORK_DIR, "output")
JOURNALS_DB = os.path.join(WORK_DIR, "journals_db.json")
SEEN_FILE = os.path.join(OUTPUT_DIR, "seen_papers.json")
OA_BASE = "https://api.openalex.org"
API_DELAY = 0.3
MAX_PAPERS = 10
SEARCH_DAYS = 30        # 搜索最近30天的论文
FALLBACK_DAYS = 90      # 如果不够则扩展到90天
MAX_SAME_VENUE = 3      # 同一期刊最多选3篇，避免扎堆顶刊

SEARCH_TOPICS = [
    "enzyme engineering machine learning",
    "deep learning protein design",
    "protein language model enzyme function prediction",
    "directed evolution machine learning protein",
    "computational enzyme design AI",
    "deep learning enzyme catalysis",
    "AI enzyme engineering protein engineering",
    "machine learning enzyme activity protein engineering",
    "deep learning protein structure enzyme design",
    "enzyme engineering biocatalysis biotransformation",
    "enzyme discovery characterization engineering",
    "protein evolution rational design engineering",
    "enzyme immobilization bioprocess",
    "substrate specificity enzyme engineering",
    "metabolic engineering enzyme pathway",
    "biosynthesis enzyme engineering",
    "enzyme production biochemical engineering",
    "protein engineering function optimization",
    "enzyme catalytic mechanism structure",
    "biocatalysis industrial enzyme application",
]

CORE_KEYWORDS = [
    "enzyme", "protein engineering", "protein design",
    "enzyme engineering", "enzyme design", "catalytic",
    "directed evolution", "protein structure", "protein function",
    "protein sequence", "biocatalysis", "enzyme activity",
    "enzyme catalysis", "binding affinity", "substrate",
    "active site", "enzyme optimization", "protein folding",
    "protein language model", "protein representation",
    "enzyme mechanism", "enzyme kinetics",
]

EXCLUDE_KEYWORDS = [
    "large language model", "llm", "chatgpt", "gpt-4",
    "neuroinflammation", "neurodegenerative", "extracellular vesicle",
    "medical image", "image segmentation", "autonomous agent",
    "social media", "clinical trial", "patient",
    "survey of large language", "hallucination",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

_session = requests.Session()
_session.headers.update({"User-Agent": "DailyPaperList/2.0 (mailto:daily-paper@bot.com)", "Accept": "application/json"})
_last_call = 0.0

def _rl():
    global _last_call
    e = time.time() - _last_call
    if e < API_DELAY: time.sleep(API_DELAY - e)
    _last_call = time.time()

def oa_get(url, params, retries=3):
    for a in range(retries):
        _rl()
        try:
            r = _session.get(url, params=params, timeout=20)
            if r.status_code == 429:
                w=(a+1)*5; log.warning(f"429 等待{w}s"); time.sleep(w); continue
            r.raise_for_status(); return r.json()
        except Exception as e:
            log.warning(f"请求失败({a+1}): {e}"); time.sleep(2*(a+1))
    return None

def load_json(p):
    with open(p,"r",encoding="utf-8") as f: return json.load(f)
def save_json(p,d):
    with open(p,"w",encoding="utf-8") as f: json.dump(d,f,ensure_ascii=False,indent=2)

def load_seen_papers():
    """加载已发送过的论文 DOI"""
    try:
        data = load_json(SEEN_FILE)
        return set(data.get("dois", [])), data.get("daily_log", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return set(), []

def save_seen_papers(all_dois, daily_log):
    """保存已发送论文，最多保留 200 条"""
    save_json(SEEN_FILE, {
        "dois": sorted(list(all_dois))[-200:],
        "daily_log": daily_log[-60:],  # 保留近60天记录
        "updated_at": datetime.now().isoformat()
    })

def load_journals_db(p):
    try: j=load_json(p); log.info(f"期刊数据库: {len(j)}条"); return j
    except FileNotFoundError: return []

def lookup_journal(venue, db):
    if not venue or not db: return None
    vl=venue.strip().lower()
    for j in db:
        for n in [j["name"]]+j.get("aliases",[]):
            if n.lower()==vl or n.lower() in vl or vl in n.lower():
                return {"name":j["name"],"if":j["if"],"cas_rank":j["cas_rank"]}
    return None

def reconstruct_abstract(inv_idx):
    if not inv_idx: return ""
    wp=[]
    for w,ps in inv_idx.items():
        for p in ps: wp.append((p,w))
    wp.sort(key=lambda x:x[0])
    return " ".join(w for _,w in wp)

def is_relevant(title, abstract):
    txt = (title + " " + abstract).lower()
    for ek in EXCLUDE_KEYWORDS:
        if ek in txt and "enzyme" not in txt:
            return False
    core_matches = sum(1 for kw in CORE_KEYWORDS if kw in txt)
    if core_matches >= 2: return True
    ai_kws = ["deep learning","machine learning","neural network","transformer",
              "artificial intelligence","computational","prediction"]
    bio_kws = ["protein","enzyme","catalytic","amino acid","sequence","molecular",
               "binding","folding","structure prediction"]
    has_ai = any(kw in txt for kw in ai_kws)
    has_bio = sum(1 for kw in bio_kws if kw in txt) >= 2
    return has_ai and has_bio

def search_works(query, from_date=None, to_date=None, limit=20):
    """按日期范围搜索"""
    if from_date is None:
        from_date = datetime.now().strftime("%Y-%m-%d")
    if to_date is None:
        to_date = datetime.now().strftime("%Y-%m-%d")
    data = oa_get(f"{OA_BASE}/works", {
        "search": query,
        "sort": "publication_date:desc",
        "per_page": min(limit,50),
        "filter": f"from_publication_date:{from_date},to_publication_date:{to_date},type:article,language:en",
        "select": "id,doi,title,authorships,primary_location,publication_date,abstract_inverted_index,concepts,cited_by_count,type_crossref,language",
    })
    results = data.get("results",[]) if data else []
    log.info(f"  >>> '{query[:45]}' ({from_date}~{to_date}) -> {len(results)}篇")
    return results

def get_venue(pl):
    if isinstance(pl,dict):
        s=pl.get("source")
        if s: return s.get("display_name","")
    return ""

def get_authors(authorships):
    if not authorships: return []
    ns=[]
    for a in authorships:
        au=a.get("author") if isinstance(a,dict) else None
        if au: ns.append(au.get("display_name",""))
    return [n for n in ns if n]

def get_concepts(w,n=3):
    cs=w.get("concepts") or []
    cs.sort(key=lambda c:c.get("score",0),reverse=True)
    return [c["display_name"] for c in cs[:n]]

def score_work(w, db):
    """评分：相关度 > 新颖性 > 期刊 > 引用"""
    txt = ((w.get("title") or "") + " " + reconstruct_abstract(w.get("abstract_inverted_index"))).lower()
    # 相关度 (0-60分)
    rel_score=0
    for kw in CORE_KEYWORDS:
        if kw in txt: rel_score+=6
    ai_kws=["deep learning","machine learning","neural network","transformer",
            "language model","diffusion","graph neural","artificial intelligence"]
    for kw in ai_kws:
        if kw in txt: rel_score+=8
    if "enzyme" in txt: rel_score+=10
    # 新颖性 (0-25分) — 越新分数越高
    pd_str = w.get("publication_date") or ""
    days_old = 999
    if pd_str:
        try:
            pub_date = datetime.strptime(pd_str[:10], "%Y-%m-%d")
            days_old = (datetime.now() - pub_date).days
        except: pass
    novelty_score = max(0, 25 - days_old * 0.8)
    # 引用 (0-10分)
    cite_score = min((w.get("cited_by_count") or 0)/50.0, 10.0)
    # 期刊 (0-5分)
    ji = lookup_journal(get_venue(w.get("primary_location")), db)
    journal_score = 0
    if ji:
        journal_score += min(ji["if"]/20.0, 3.0)
        journal_score += 2.0 if ji["cas_rank"]=="一区" else 1.0 if ji["cas_rank"]=="二区" else 0
    s = rel_score*1.5 + novelty_score + cite_score + journal_score
    return s

def build_entry(w, db, published_today=False):
    v=get_venue(w.get("primary_location"))
    ji=lookup_journal(v,db)
    pd=w.get("publication_date","") or ""
    py=pd[:4] if len(pd)>=4 else str(w.get("publication_year",""))
    pm=pd[5:7] if len(pd)>=7 else ""
    doi=(w.get("doi") or "").replace("https://doi.org/","")
    return {
        "id":w.get("id",""), "title":w.get("title","N/A"),
        "doi":doi, "url":f"https://doi.org/{doi}" if doi else "",
        "abstract":reconstruct_abstract(w.get("abstract_inverted_index")),
        "authors":get_authors(w.get("authorships")),
        "authors_short":", ".join(get_authors(w.get("authorships"))[:5])+(" et al." if len(get_authors(w.get("authorships")))>5 else ""),
        "venue":v, "journal_info":ji,
        "publication_date":pd, "year":py, "month":pm,
        "citations":w.get("cited_by_count") or 0,
        "concepts":get_concepts(w), "source":"OpenAlex",
        "published_today":published_today,
    }

def main():
    log.info("="*50); log.info("AI+酶工程 每日文献清单 v3"); log.info("="*50)
    db=load_journals_db(JOURNALS_DB)

    # 加载历史记录，排除已发过的论文
    seen_dois, daily_log = load_seen_papers()
    log.info(f"历史已发论文: {len(seen_dois)} 篇")

    # 两阶段搜索：先试30天，不够就扩展
    for days in [0, 30, 60, 90, 120, 180, 365]:
        all_works.setdefault("x", {})
        if days == 0:
            fd = datetime.now().strftime("%Y-%m-%d")
        else:
            fd = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        dedup_doi = set()
        for q in SEARCH_TOPICS:
            for w in search_works(q, from_date=fd, to_date=datetime.now().strftime("%Y-%m-%d")):
                wid=w.get("id",""); doi=w.get("doi","") or ""
                title=(w.get("title") or "").strip().lower()
                abstract=reconstruct_abstract(w.get("abstract_inverted_index"))
                if not wid or not title or not abstract: continue
                if doi in dedup_doi: continue
                if not is_relevant(title, abstract): continue
                dedup_doi.add(doi); all_works[wid]=w
        log.info(f"相关度过滤后 ({days}天): {len(all_works)} 篇")
        if len(all_works) >= MAX_PAPERS * 1.5: break
        if attempt == 1:
            log.info(f"论文不足，扩展搜索窗口至 {FALLBACK_DAYS} 天")

    if not all_works: log.warning("未获取到论文"); return

    # 排除已发论文
    new_works = {wid: w for wid, w in all_works.items()
                 if (w.get("doi") or "").replace("https://doi.org/","") not in seen_dois}
    if not new_works:
        log.warning("Nothing new")
        return
    log.info(f"After dedup: {len(new_works)}")

    # 评分 + 多样性筛选 + 同一期刊限制
    scored = sorted([(score_work(w,db),wid,w) for wid,w in new_works.items()], key=lambda x:x[0], reverse=True)

    selected = [scored[0]]
    ckws = set()
    venue_count = {}
    kwl = ["deep learning","language model","diffusion","graph","directed evolution",
           "protein design","enzyme catalysis","molecular dynamics","biocatalysis",
           "bioprocess","biosynthesis","metabolic engineering","fermentation"]


    # 更新首个论文的期刊计数
    first_venue = get_venue(scored[0][2].get("primary_location"))
    if first_venue: venue_count[first_venue] = 1

    for s, wid, w in scored[1:]:
        if len(selected) >= MAX_PAPERS: break
        # 同一期刊限制
        venue = get_venue(w.get("primary_location"))
        if venue and venue_count.get(venue, 0) >= MAX_SAME_VENUE:
            continue
        txt = ((w.get("title") or "") + " " + reconstruct_abstract(w.get("abstract_inverted_index") or {})).lower()
        pk = {k for k in kwl if k in txt}
        # 优先选不同技术方向的
        if pk - ckws or len(selected) < MAX_PAPERS:
            selected.append((s, wid, w))
            ckws.update(pk)
            if venue: venue_count[venue] = venue_count.get(venue, 0) + 1

    log.info(f"最终选取 {len(selected)} 篇")

    # 保存结果
    entries = [build_entry(w, db, published_today=(wid in today_wids)) for _,_,wid,w in selected]
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    jp = os.path.join(OUTPUT_DIR, f"papers_raw_{today}.json")
    save_json(jp, {
        "generated_at": datetime.now().isoformat(),
        "total_works": len(all_works),
        "search_days": days,
        "papers": entries
    })

    # 更新已发论文记录
    new_dois = set(e["doi"] for e in entries if e["doi"])
    seen_dois.update(new_dois)
    daily_log.append({"date": today, "count": len(entries), "dois": list(new_dois)})
    save_seen_papers(seen_dois, daily_log)

    print("\n" + "="*50)
    print(f"数据保存: {jp}")
    print(f"共 {len(entries)} 篇论文精选 (搜索{all_works}篇)")
    print("精选论文:")
    for i, e in enumerate(entries, 1):
        ji = e.get("journal_info")
        jn = ji["name"] if ji else (e.get("venue","")[:25] or "N/A")
        pub = e.get("publication_date", "")[:10]
        print(f"  {i}. [{pub}] {e['title'][:70]}... ({jn})")
    print("="*50)

if __name__=="__main__":
    try: main()
    except KeyboardInterrupt: sys.exit(1)
    except Exception as e: log.error(f"失败: {e}"); traceback.print_exc(); sys.exit(1)

