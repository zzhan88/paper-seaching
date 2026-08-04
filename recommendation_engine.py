#!/usr/bin/env python3
"""多源、可解释的酶工程 + AI for Protein 文献推荐引擎。"""

from __future__ import annotations

import html
import json
import logging
import math
import os
import re
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

try:
    import requests
except ModuleNotFoundError:  # 允许不安装网络依赖时运行纯离线单元测试
    requests = None

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(WORK_DIR, "output")
JOURNALS_DB = os.path.join(WORK_DIR, "journals_db.json")
SEEN_FILE = os.path.join(OUTPUT_DIR, "seen_papers.json")
MAX_PAPERS = 10
MAX_SAME_VENUE = 2
MAX_SAME_TRACK = 4
MAX_REVIEWS = 2
MIN_TOP_JOURNAL_TARGET = 4
SEARCH_WINDOWS = (7, 30, 90, 180, 365)
IGNORE_SEEN = os.environ.get("IGNORE_SEEN", "").lower() in {"1", "true", "yes"}
ENABLED_SOURCES = tuple(
    source.strip().lower()
    for source in os.environ.get("LITERATURE_SOURCES", "openalex,pubmed,crossref").split(",")
    if source.strip()
)

SEARCH_TOPICS = (
    "protein language model foundation model",
    "enzyme engineering thermostability activity specificity",
    "generative AI protein design diffusion",
    "directed evolution protein engineering enzyme optimization",
    "deep learning protein protein interaction prediction",
    "biocatalysis enzyme design catalytic efficiency",
    "AI protein ligand binding affinity prediction",
    "enzyme discovery characterization industrial biocatalysis",
    "machine learning enzyme activity stability selectivity prediction",
    "geometric deep learning protein structure function",
    "self supervised protein representation learning",
    "AI protein engineering experimental validation",
    "multimodal protein sequence structure model",
    "deep learning protein small molecule docking scoring",
    "generative AI antibody peptide protein design",
    "computational enzyme design AI catalytic activity",
    "protein mutation effect stability function prediction",
    "multi enzyme cascade biotransformation engineering",
    "enzyme immobilization stability activity engineering",
)

PRIORITY_TOPIC_QUERY = (
    "enzyme engineering protein engineering biocatalysis protein design "
    "protein language model generative protein enzyme activity stability selectivity"
)
PUBMED_PRIORITY_TOPIC_QUERY = (
    '"enzyme engineering"[Title/Abstract] OR "protein engineering"[Title/Abstract] OR '
    'biocatalysis[Title/Abstract] OR "protein design"[Title/Abstract] OR '
    '"protein language model"[Title/Abstract] OR "generative protein"[Title/Abstract] OR '
    '(enzyme[Title/Abstract] AND (activity[Title/Abstract] OR stability[Title/Abstract] '
    'OR selectivity[Title/Abstract]))'
)
PUBMED_TARGET_JOURNAL_GROUPS = (
    ("Nature", "Science", "Cell", "Proceedings of the National Academy of Sciences",
     "Nature Biotechnology", "Nature Methods"),
    ("Nature Machine Intelligence", "Nature Computational Science", "Nature Chemical Biology",
     "Nature Structural & Molecular Biology", "Nature Catalysis", "Nature Communications"),
    ("Science Advances", "Molecular Cell", "Cell Systems", "Cell Chemical Biology",
     "Journal of the American Chemical Society", "Angewandte Chemie International Edition"),
    ("ACS Catalysis", "ACS Synthetic Biology", "ACS Chemical Biology", "Chemical Science",
     "Protein Science", "Structure"),
    ("Green Chemistry", "ChemCatChem", "ChemSusChem", "Bioresource Technology",
     "Bioresources and Bioprocessing", "Biotechnology Advances"),
)
CROSSREF_TARGET_JOURNALS = (
    "Nature Biotechnology", "Nature Methods", "Nature Machine Intelligence",
    "Nature Computational Science", "Nature Chemical Biology", "Nature Catalysis",
    "ACS Catalysis", "Journal of the American Chemical Society",
    "Angewandte Chemie International Edition", "Cell Systems",
    "ACS Synthetic Biology", "ACS Chemical Biology", "ACS Sustainable Chemistry & Engineering",
    "Journal of Agricultural and Food Chemistry", "Green Chemistry", "ChemCatChem",
    "ChemSusChem", "Bioresource Technology", "Bioresources and Bioprocessing",
    "Biotechnology Advances", "Chemical Engineering Journal", "Advanced Science",
)

PROTEIN_TERMS = (
    "protein", "proteome", "peptide", "antibody", "enzyme", "enzymatic",
    "biocatal", "amino acid sequence", "protein sequence", "protein structure",
)
ENZYME_TERMS = (
    "enzyme", "enzymatic", "biocatal", "catalytic protein", "active site",
    "catalytic activity", "catalytic efficiency", "kcat",
)
MODIFICATION_TERMS = (
    "engineer", "protein design", "enzyme design", "rational design",
    "directed evolution", "mutagen", "mutation", "variant", "screening",
    "fitness landscape", "optimiz", "reprogram", "redesign",
    "immobiliz", "characterization", "enzyme discovery",
)
PERFORMANCE_TERMS = (
    "improv", "enhanc", "stability", "thermostability", "activity",
    "specificity", "selectivity", "catalytic efficiency", "kcat", "yield",
)
BIOCAT_APPLICATION_TERMS = (
    "biocatal", "enzymatic synthesis", "chemoenzymatic synthesis",
    "enzyme cascade", "multi enzyme cascade", "biotransformation",
)
AI_TERMS = (
    "machine learning", "deep learning", "artificial intelligence",
    "neural network", "transformer", "language model", "diffusion",
    "generative", "graph neural", "geometric deep learning",
    "equivariant", "foundation model", "representation learning",
    "self supervised", "multimodal", "proteinmpnn", "alphafold",
)
METHOD_TERMS = (
    "new model", "novel model", "model architecture", "framework", "method",
    "pretrain", "fine tuning", "zero shot", "few shot", "foundation model",
    "representation learning", "self supervised", "multimodal", "benchmark",
    "generaliz", "transfer learning", "contrastive learning", "equivariant",
    "geometric deep learning", "diffusion", "transformer",
)
AI_TASK_TERMS = (
    "protein design", "sequence design", "structure prediction",
    "function prediction", "property prediction", "mutation effect",
    "variant effect", "fitness landscape", "protein protein interaction",
    "protein interaction", "binding site", "binding affinity", "protein ligand",
    "small molecule", "docking", "virtual screening", "activity prediction",
    "drug target", "drug protein",
    "stability prediction", "thermostability", "specificity", "selectivity",
    "enzyme activity", "catalytic activity", "kinetic", "kcat",
)
EXPERIMENT_TERMS = (
    "experimental", "assay", "validated", "validation", "expressed",
    "purified", "kinetic", "kcat", " km ", "yield", "conversion",
)
HARD_EXCLUDE_TITLE = (
    "nanozyme", "enzyme-like nanoparticle", "medical image",
    "clinical trial", "knowledgebase", "database resource",
    "protein sequence classification resource", "proteome resource",
    "protein structure database", "protein knowledge base",
    "interaction database", "protein database", "peptide database",
    "nanocatalyst", "sonocatal", "photocatal", "2d material",
    "colorimetric detection", "colorimetric sensor",
)
OFF_TOPIC_TERMS = (
    "patient", "tumor", "cancer therapy", "neurodegenerative",
    "clinical", "drug delivery", "diagnostic", "peptide inhibitor",
    "antibody therapy", "medical imaging",
)
REVIEW_TERMS = ("review", "perspective", "outlook", "opportunities and challenges")

TRACKS = {
    "foundation_models": (
        "蛋白质基础模型",
        ("language model", "foundation model", "pretrain", "representation learning",
         "self supervised", "multimodal", "transformer"),
    ),
    "generative_design": (
        "生成式蛋白设计",
        ("generative", "diffusion", "protein design", "sequence design", "proteinmpnn"),
    ),
    "protein_interactions": (
        "蛋白质相互作用",
        ("protein protein interaction", "protein interaction", "protein rna",
         "protein peptide", "complex", "interface", "antibody", "peptide binding"),
    ),
    "protein_ligand": (
        "蛋白–小分子结合",
        ("protein ligand", "small molecule", "binding affinity", "docking",
         "virtual screening", "binding site", "drug target", "drug protein"),
    ),
    "property_prediction": (
        "活性·稳定性·选择性预测",
        ("activity prediction", "stability prediction", "thermostability",
         "specificity", "selectivity", "mutation effect", "variant effect", "kcat"),
    ),
    "structure_function": (
        "结构与功能预测",
        ("structure prediction", "function prediction", "folding", "structure function",
         "geometric deep learning", "equivariant"),
    ),
    "ml_evolution": (
        "机器学习与定向进化",
        ("machine learning", "directed evolution", "fitness landscape", "screening"),
    ),
    "enzyme_engineering": (
        "AI辅助酶工程",
        ("enzyme engineering", "enzyme design", "biocatal", "catalytic activity",
         "directed evolution", "fitness landscape"),
    ),
    "legacy_enzyme": (
        "酶工程与生物催化",
        ("enzyme engineering", "protein engineering", "biocatal", "mutagen",
         "variant", "characterization"),
    ),
}

TOP_PRIORITY_JOURNALS = {
    "Nature", "Science", "Cell", "PNAS", "Nature Biotechnology", "Nature Methods",
    "Nature Machine Intelligence", "Nature Computational Science", "Nature Chemical Biology",
    "Nature Structural & Molecular Biology", "Nature Chemistry", "Nature Catalysis",
    "Nature Communications", "Science Advances", "Molecular Cell", "Cell Systems",
    "Cell Chemical Biology", "Patterns", "Journal of the American Chemical Society",
    "Angewandte Chemie International Edition", "ACS Central Science", "Chemical Science",
    "Advanced Science",
}
CORE_SCOPE_JOURNALS = {
    "Bioinformatics",
    "PLOS Computational Biology", "Briefings in Bioinformatics",
    "Journal of Computational Biology", "Machine Learning: Science and Technology",
    "ACS Catalysis", "Enzyme and Microbial Technology",
    "Protein Engineering, Design and Selection", "Biotechnology and Bioengineering",
    "Applied Microbiology and Biotechnology", "Journal of Biotechnology",
    "Biochemical Engineering Journal", "Process Biochemistry",
    "Catalysis Science & Technology", "Biotechnology Journal",
    "Microbial Cell Factories", "Metabolic Engineering", "ACS Synthetic Biology",
    "RSC Chemical Biology", "ACS Chemical Biology", "ChemBioChem",
    "Synthetic and Systems Biotechnology", "ChemCatChem", "npj Biocatalysis",
    "Bioresources and Bioprocessing", "Green Chemistry", "ChemSusChem",
}
ADJACENT_SCOPE_JOURNALS = {
    "Journal of Biological Chemistry",
    "Protein Science", "Structure", "Journal of Molecular Biology",
    "Journal of Chemical Information and Modeling",
    "Journal of Chemical Theory and Computation",
    "Nucleic Acids Research", "Bioinformatics", "Journal of Cheminformatics",
    "Computational and Structural Biotechnology Journal",
    "International Journal of Biological Macromolecules",
    "Journal of Agricultural and Food Chemistry",
    "Frontiers in Bioengineering and Biotechnology",
    "Computational Biology and Chemistry", "FEBS Journal",
    "Biotechnology Advances", "Applied and Environmental Microbiology", "ACS Omega",
}
BROAD_SCOPE_JOURNALS = {
    "Communications Biology", "Communications Chemistry", "iScience", "Scientific Reports",
}

CONDITIONAL_JOURNAL_RULES = {
    "ACS Sustainable Chemistry & Engineering": (
        "sustainab", "green chemistry", "biobased", "bio based", "biomass", "waste",
        "circular", "life cycle", "carbon efficiency", "renewable",
    ),
    "Green Chemistry": (
        "sustainab", "green chemistry", "biobased", "bio based", "biomass", "waste",
        "renewable", "atom economy", "environmental factor",
    ),
    "ChemSusChem": (
        "sustainab", "green chemistry", "biobased", "bio based", "biomass", "waste",
        "renewable", "circular",
    ),
    "Journal of Agricultural and Food Chemistry": (
        "food", "agricultur", "crop", "plant", "flavor", "nutrition", "feed",
        "pesticide", "food processing",
    ),
    "Bioresource Technology": (
        "biomass", "bioresource", "biorefinery", "waste", "fermentation", "biofuel",
        "bioprocess", "lignocellulos", "industrial biocatal",
    ),
    "Bioresources and Bioprocessing": (
        "biomass", "bioresource", "biorefinery", "waste", "fermentation", "bioprocess",
        "industrial biocatal", "biomanufactur",
    ),
    "Chemical Engineering Journal": (
        "industrial", "scale up", "scale-up", "bioprocess", "reactor", "process engineering",
        "biomanufactur", "immobiliz", "continuous flow",
    ),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def normalize_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (text or "").lower())).strip()


def normalize_doi(doi: str | None) -> str:
    value = (doi or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if value.startswith(prefix):
            value = value[len(prefix):]
    return value.rstrip(".,;)")


def strip_markup(text: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def first_text(node: ET.Element | None, paths: tuple[str, ...]) -> str:
    if node is None:
        return ""
    for path in paths:
        found = node.find(path)
        if found is not None:
            value = "".join(found.itertext()).strip()
            if value:
                return value
    return ""


def request_json(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    source: str,
    retries: int = 3,
) -> dict[str, Any] | None:
    for attempt in range(retries):
        try:
            response = session.get(url, params=params, timeout=30)
            if response.status_code == 429:
                time.sleep(3 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            log.warning("%s 请求失败(%s/%s): %s", source, attempt + 1, retries, exc)
            time.sleep(2 * (attempt + 1))
    return None


def request_text(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    source: str,
    retries: int = 3,
) -> str | None:
    for attempt in range(retries):
        try:
            response = session.get(url, params=params, timeout=30)
            if response.status_code == 429:
                time.sleep(3 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.text
        except Exception as exc:
            log.warning("%s 请求失败(%s/%s): %s", source, attempt + 1, retries, exc)
            time.sleep(2 * (attempt + 1))
    return None


def inverted_abstract(index: dict[str, list[int]] | None) -> str:
    positions = []
    for word, indexes in (index or {}).items():
        positions.extend((position, word) for position in indexes)
    return " ".join(word for _, word in sorted(positions))


def openalex_batch(queries: tuple[str, ...], start_date: str, end_date: str) -> list[dict]:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "DailyPaperList/5.0 (mailto:daily-paper@bot.com)",
        "Accept": "application/json",
    })
    records = []
    for query in queries:
        data = request_json(session, "https://api.openalex.org/works", {
            "search": query,
            "sort": "publication_date:desc",
            "per_page": 25,
            "filter": (
                f"from_publication_date:{start_date},to_publication_date:{end_date},"
                "language:en"
            ),
            "select": (
                "id,doi,title,authorships,primary_location,publication_date,"
                "abstract_inverted_index,concepts,cited_by_count"
            ),
        }, "OpenAlex")
        for work in (data or {}).get("results", []):
            primary = work.get("primary_location") or {}
            source = primary.get("source") or {}
            records.append({
                "id": work.get("id", ""),
                "doi": normalize_doi(work.get("doi")),
                "title": work.get("title", ""),
                "abstract": inverted_abstract(work.get("abstract_inverted_index")),
                "authors": [
                    item.get("author", {}).get("display_name", "")
                    for item in work.get("authorships") or []
                    if item.get("author", {}).get("display_name")
                ],
                "venue": source.get("display_name", ""),
                "publication_date": work.get("publication_date", ""),
                "citations": work.get("cited_by_count") or 0,
                "concepts": [
                    concept.get("display_name", "")
                    for concept in sorted(
                        work.get("concepts") or [],
                        key=lambda item: item.get("score", 0),
                        reverse=True,
                    )[:3]
                ],
                "sources": ["OpenAlex"],
            })
        time.sleep(0.25)
    return records


def parse_pubmed_article(article: ET.Element) -> dict:
    medline = article.find("./MedlineCitation")
    article_node = medline.find("./Article") if medline is not None else None
    journal_node = article_node.find("./Journal") if article_node is not None else None
    pmid = first_text(medline, ("./PMID",))
    title = first_text(article_node, ("./ArticleTitle",))
    abstract_parts = []
    if article_node is not None:
        for abstract_node in article_node.findall("./Abstract/AbstractText"):
            label = abstract_node.attrib.get("Label", "")
            text = "".join(abstract_node.itertext()).strip()
            abstract_parts.append(f"{label}: {text}" if label else text)
    authors = []
    if article_node is not None:
        for author in article_node.findall("./AuthorList/Author"):
            collective = first_text(author, ("./CollectiveName",))
            personal = " ".join(filter(None, (
                first_text(author, ("./ForeName", "./Initials")),
                first_text(author, ("./LastName",)),
            )))
            if collective or personal:
                authors.append(collective or personal)
    doi = ""
    for article_id in article.findall("./PubmedData/ArticleIdList/ArticleId"):
        if article_id.attrib.get("IdType") == "doi":
            doi = normalize_doi(article_id.text)
            break
    year = first_text(article_node, ("./ArticleDate/Year",)) or first_text(journal_node, (
        "./JournalIssue/PubDate/Year",
        "./JournalIssue/PubDate/MedlineDate",
    ))[:4]
    month = first_text(article_node, ("./ArticleDate/Month",)) or first_text(
        journal_node, ("./JournalIssue/PubDate/Month",)
    )
    day = first_text(article_node, ("./ArticleDate/Day",)) or "01"
    month_map = {
        "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
        "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
    }
    normalized_month = month.zfill(2) if month.isdigit() else month_map.get(month, "01")
    normalized_day = day.zfill(2) if day.isdigit() else "01"
    publication_date = f"{year}-{normalized_month}-{normalized_day}" if year else ""
    return {
        "id": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        "doi": doi,
        "title": title,
        "abstract": " ".join(abstract_parts),
        "authors": authors,
        "venue": first_text(journal_node, ("./Title", "./ISOAbbreviation")),
        "publication_date": publication_date,
        "citations": 0,
        "concepts": [],
        "sources": ["PubMed"],
    }


def pubmed_batch(queries: tuple[str, ...], start_date: str, end_date: str) -> list[dict]:
    session = requests.Session()
    session.headers.update({"User-Agent": "DailyPaperList/5.0 daily-paper@bot.com"})
    api_key = os.environ.get("NCBI_API_KEY", "")
    records = []
    targeted_queries = tuple(
        f"({PUBMED_PRIORITY_TOPIC_QUERY}) AND (" + " OR ".join(
            f'"{journal}"[jour]' for journal in group
        ) + ")"
        for group in PUBMED_TARGET_JOURNAL_GROUPS
    )
    for query in tuple(queries[:8]) + targeted_queries:
        term = (
            f"({query}) AND "
            f"(\"{start_date.replace('-', '/')}\"[Date - Publication] : "
            f"\"{end_date.replace('-', '/')}\"[Date - Publication])"
        )
        params = {"db": "pubmed", "term": term, "retmode": "json", "retmax": 25, "sort": "date"}
        if api_key:
            params["api_key"] = api_key
        data = request_json(
            session,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params,
            "PubMed",
        )
        ids = (data or {}).get("esearchresult", {}).get("idlist", [])
        if ids:
            fetch_params = {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}
            if api_key:
                fetch_params["api_key"] = api_key
            xml_text = request_text(
                session,
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                fetch_params,
                "PubMed",
            )
            if xml_text:
                try:
                    root = ET.fromstring(xml_text)
                    records.extend(parse_pubmed_article(item) for item in root.findall("./PubmedArticle"))
                except ET.ParseError as exc:
                    log.warning("PubMed XML 解析失败: %s", exc)
        time.sleep(0.34 if not api_key else 0.12)
    return records


def crossref_date(item: dict) -> str:
    for field in ("published-online", "published-print", "issued"):
        parts = (item.get(field) or {}).get("date-parts") or []
        if parts and parts[0]:
            values = list(parts[0]) + [1, 1]
            return f"{values[0]:04d}-{values[1]:02d}-{values[2]:02d}"
    return ""


def crossref_batch(queries: tuple[str, ...], start_date: str, end_date: str) -> list[dict]:
    session = requests.Session()
    mailto = os.environ.get("CROSSREF_MAILTO", "daily-paper@bot.com")
    session.headers.update({"User-Agent": f"DailyPaperList/5.0 (mailto:{mailto})"})
    records = []
    query_specs = [
        {"query.bibliographic": query}
        for query in queries[:8]
    ] + [
        {
            "query.bibliographic": PRIORITY_TOPIC_QUERY,
            "query.container-title": journal,
        }
        for journal in CROSSREF_TARGET_JOURNALS
    ]
    for query_spec in query_specs:
        params = {
            "filter": f"from-pub-date:{start_date},until-pub-date:{end_date}",
            "rows": 25,
            "sort": "published",
            "order": "desc",
            "mailto": mailto,
        }
        params.update(query_spec)
        data = request_json(session, "https://api.crossref.org/works", params, "Crossref")
        for item in (data or {}).get("message", {}).get("items", []):
            titles = item.get("title") or []
            venues = item.get("container-title") or []
            records.append({
                "id": item.get("URL", ""),
                "doi": normalize_doi(item.get("DOI")),
                "title": strip_markup(titles[0]) if titles else "",
                "abstract": strip_markup(item.get("abstract")),
                "authors": [
                    " ".join(filter(None, (author.get("given"), author.get("family"))))
                    for author in item.get("author") or []
                ],
                "venue": venues[0] if venues else "",
                "publication_date": crossref_date(item),
                "citations": item.get("is-referenced-by-count") or 0,
                "concepts": item.get("subject") or [],
                "sources": ["Crossref"],
            })
        time.sleep(0.2)
    return records


SOURCE_FETCHERS = {
    "openalex": openalex_batch,
    "pubmed": pubmed_batch,
    "crossref": crossref_batch,
}


def record_key(record: dict) -> str:
    doi = normalize_doi(record.get("doi"))
    if doi:
        return f"doi:{doi}"
    return f"title:{normalize_text(record.get('title'))}"


def merge_record(existing: dict | None, incoming: dict) -> dict:
    if not existing:
        return incoming.copy()
    merged = existing.copy()
    merged["sources"] = sorted(set(existing.get("sources", [])) | set(incoming.get("sources", [])))
    for field in ("title", "abstract", "venue", "publication_date", "id"):
        if len(str(incoming.get(field) or "")) > len(str(merged.get(field) or "")):
            merged[field] = incoming[field]
    if len(incoming.get("authors") or []) > len(merged.get("authors") or []):
        merged["authors"] = incoming["authors"]
    merged["citations"] = max(existing.get("citations") or 0, incoming.get("citations") or 0)
    merged["concepts"] = list(dict.fromkeys(
        (existing.get("concepts") or []) + (incoming.get("concepts") or [])
    ))[:5]
    if not merged.get("doi") and incoming.get("doi"):
        merged["doi"] = incoming["doi"]
    return merged


def search_all_sources(start_date: str, end_date: str) -> tuple[dict[str, dict], dict[str, str]]:
    if requests is None:
        raise RuntimeError("真实检索需要安装 requests：pip install -r requirements.txt")
    records: dict[str, dict] = {}
    failures: dict[str, str] = {}
    sources = [source for source in ENABLED_SOURCES if source in SOURCE_FETCHERS]
    with ThreadPoolExecutor(max_workers=max(1, len(sources))) as executor:
        futures = {
            executor.submit(SOURCE_FETCHERS[source], SEARCH_TOPICS, start_date, end_date): source
            for source in sources
        }
        for future in as_completed(futures):
            source = futures[future]
            try:
                source_records = future.result()
                log.info("%s 返回 %s 条记录", source, len(source_records))
                for incoming in source_records:
                    key = record_key(incoming)
                    if key not in {"title:", "doi:"}:
                        records[key] = merge_record(records.get(key), incoming)
            except Exception as exc:
                failures[source] = str(exc)
                log.exception("%s 检索失败，继续使用其他来源", source)
    return records, failures


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def load_seen_papers() -> tuple[set[str], list[dict]]:
    try:
        data = load_json(SEEN_FILE)
        return {normalize_doi(item) for item in data.get("dois", [])}, data.get("daily_log", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return set(), []


def save_seen_papers(all_dois: set[str], daily_log: list[dict]) -> None:
    save_json(SEEN_FILE, {
        "dois": sorted(all_dois)[-500:],
        "daily_log": daily_log[-90:],
        "updated_at": datetime.now().isoformat(),
    })


def lookup_journal(venue: str, database: list[dict]) -> dict | None:
    """使用最长的规范化精确名称匹配，避免综合刊名称污染子刊。"""
    normalized_venue = normalize_text(venue)
    aliases = []
    for journal in database:
        for alias in [journal["name"], *journal.get("aliases", [])]:
            aliases.append((normalize_text(alias), journal))
    for alias, journal in sorted(aliases, key=lambda item: len(item[0]), reverse=True):
        if alias == normalized_venue:
            return {
                "name": journal["name"],
                "if": journal["if"],
                "cas_rank": journal["cas_rank"],
            }
    return None


def phrase_hits(text: str, phrases: tuple[str, ...]) -> set[str]:
    return {phrase for phrase in phrases if normalize_text(phrase) in text}


def choose_track(text: str, title_text: str = "") -> str:
    priority = (
        "protein_interactions",
        "protein_ligand",
        "property_prediction",
        "generative_design",
        "ml_evolution",
        "enzyme_engineering",
        "structure_function",
        "foundation_models",
    )
    for haystack in (title_text, text):
        if not haystack:
            continue
        for key in priority:
            if phrase_hits(haystack, TRACKS[key][1]):
                return key
    scores = {
        key: len(phrase_hits(text, phrases))
        for key, (_, phrases) in TRACKS.items()
    }
    if phrase_hits(text, AI_TERMS):
        scores["legacy_enzyme"] = -1
    else:
        return "legacy_enzyme"
    return max(scores, key=scores.get) if max(scores.values()) else "foundation_models"


def assess_relevance(title: str, abstract: str) -> dict:
    title_text = normalize_text(title)
    abstract_text = f" {normalize_text(abstract)} "
    full_text = f"{title_text} {abstract_text}"
    hard_exclusions = phrase_hits(title_text, HARD_EXCLUDE_TITLE)
    if hard_exclusions:
        return {
            "eligible": False, "tier": "excluded", "topic_score": 0,
            "track": "excluded", "track_label": "排除",
            "reason": f"标题命中排除主题：{sorted(hard_exclusions)[0]}",
        }

    protein_title = phrase_hits(title_text, PROTEIN_TERMS)
    protein_all = phrase_hits(full_text, PROTEIN_TERMS)
    enzyme_title = phrase_hits(title_text, ENZYME_TERMS)
    enzyme_all = phrase_hits(full_text, ENZYME_TERMS)
    modification_title = phrase_hits(title_text, MODIFICATION_TERMS)
    modification_all = phrase_hits(full_text, MODIFICATION_TERMS)
    performance_title = phrase_hits(title_text, PERFORMANCE_TERMS)
    performance_all = phrase_hits(full_text, PERFORMANCE_TERMS)
    biocatalysis_title = phrase_hits(title_text, BIOCAT_APPLICATION_TERMS)
    biocatalysis_all = phrase_hits(full_text, BIOCAT_APPLICATION_TERMS)
    ai_title = phrase_hits(title_text, AI_TERMS)
    ai_all = phrase_hits(full_text, AI_TERMS)
    method_title = phrase_hits(title_text, METHOD_TERMS)
    method_all = phrase_hits(full_text, METHOD_TERMS)
    task_title = phrase_hits(title_text, AI_TASK_TERMS)
    task_all = phrase_hits(full_text, AI_TASK_TERMS)
    experiment_all = phrase_hits(full_text, EXPERIMENT_TERMS)
    off_topic = phrase_hits(full_text, OFF_TOPIC_TERMS)
    medical_title = phrase_hits(title_text, ("cancer", "tumor", "therapy", "clinical", "patient"))

    if not protein_all:
        return {
            "eligible": False, "tier": "excluded", "topic_score": 0,
            "track": "excluded", "track_label": "排除",
            "reason": "缺少明确的蛋白质、肽、抗体或酶研究对象",
        }

    has_ai_method = bool(ai_all and task_all and (ai_title or method_all))
    has_legacy_engineering = bool(
        enzyme_all
        and (
        modification_all
        or (
            enzyme_title
            and performance_all
            and experiment_all
        )
        or (
            biocatalysis_title
            and (experiment_all or performance_all)
        )
        )
    )
    if not has_ai_method and not has_legacy_engineering:
        return {
            "eligible": False, "tier": "excluded", "topic_score": 0,
            "track": "excluded", "track_label": "排除",
            "reason": "缺少AI方法及蛋白质任务，或缺少明确的酶工程行为",
        }
    if medical_title and not (ai_title and task_title) and not modification_title:
        return {
            "eligible": False, "tier": "excluded", "topic_score": 0,
            "track": "excluded", "track_label": "排除",
            "reason": "医学/治疗主题占主导且标题未体现蛋白质AI方法",
        }
    if len(off_topic) >= 2 and not protein_title and not ai_title:
        return {
            "eligible": False, "tier": "excluded", "topic_score": 0,
            "track": "excluded", "track_label": "排除",
            "reason": "医学/治疗主题占主导且标题未体现蛋白质AI方法",
        }

    topic_score = (
        min(12, len(protein_title) * 5 + len(protein_all))
        + min(16, len(ai_title) * 6 + len(ai_all) * 2)
        + min(14, len(task_title) * 5 + len(task_all) * 2)
        + min(8, len(modification_title) * 3 + len(modification_all))
        + min(4, len(experiment_all))
        - min(10, len(off_topic) * 3)
    )
    topic_score = max(1, min(50, topic_score))
    method_score = min(
        20,
        len(method_title) * 6 + len(method_all) * 2 + (5 if ai_title else 0),
    ) if has_ai_method else 0
    engineering_score = min(
        20,
        len(modification_title) * 6
        + len(modification_all) * 2
        + len(performance_title) * 4
        + len(biocatalysis_title) * 3
        + len(experiment_all),
    ) if has_legacy_engineering else 0
    is_review = bool(phrase_hits(title_text, REVIEW_TERMS + ("retrospective", "bibliometric")))
    tier = "core"
    track = choose_track(full_text, title_text)
    evidence = []
    if method_title:
        evidence.append("标题突出新模型、框架或学习方法")
    elif has_ai_method:
        evidence.append("AI方法面向明确的蛋白质任务")
    if task_title:
        evidence.append("标题聚焦" + TRACKS[track][0])
    elif protein_title:
        evidence.append("标题明确聚焦蛋白质领域")
    if experiment_all:
        evidence.append("包含实验或动力学验证")
    if not evidence:
        evidence.append("保留的传统酶工程/生物催化论文")
    return {
        "eligible": True,
        "tier": tier,
        "topic_score": topic_score,
        "method_score": method_score,
        "engineering_score": engineering_score,
        "is_ai_method": has_ai_method,
        "topic_family": "ai_for_protein" if has_ai_method else "enzyme_engineering",
        "is_review": is_review,
        "track": track,
        "track_label": TRACKS[track][0],
        "reason": "；".join(evidence[:3]),
    }


def journal_fit(
    venue: str,
    journal_info: dict | None,
    title: str = "",
    abstract: str = "",
) -> dict:
    name = journal_info["name"] if journal_info else venue
    if name in TOP_PRIORITY_JOURNALS:
        return {
            "level": "Top期刊·主题对口",
            "scope_score": 16,
            "priority_tier": "top",
        }
    if name in CONDITIONAL_JOURNAL_RULES:
        context = normalize_text(f"{title} {abstract}")
        if phrase_hits(context, CONDITIONAL_JOURNAL_RULES[name]):
            return {
                "level": "场景高度对口",
                "scope_score": 10,
                "priority_tier": "conditional",
            }
        return {
            "level": "期刊相关·场景一般",
            "scope_score": 4,
            "priority_tier": "general",
        }
    if name in CORE_SCOPE_JOURNALS:
        return {"level": "高度对口", "scope_score": 11, "priority_tier": "core"}
    if name in ADJACENT_SCOPE_JOURNALS:
        return {"level": "方向对口", "scope_score": 8, "priority_tier": "adjacent"}
    if name in BROAD_SCOPE_JOURNALS:
        return {"level": "综合期刊·按主题入选", "scope_score": 5, "priority_tier": "general"}
    normalized = normalize_text(name)
    if any(term in normalized for term in (
        "enzyme", "catal", "biotech", "protein", "biochem", "bioinform",
        "computational biology", "machine learning", "artificial intelligence",
    )):
        return {"level": "方向对口", "scope_score": 6, "priority_tier": "adjacent"}
    return {"level": "交叉方向", "scope_score": 2, "priority_tier": "general"}


def score_record(record: dict, database: list[dict], assessment: dict) -> tuple[float, dict]:
    publication_date = record.get("publication_date") or ""
    days_old = 365
    try:
        published = datetime.strptime(publication_date[:10], "%Y-%m-%d")
        days_old = max(0, (datetime.now() - published).days)
    except (TypeError, ValueError):
        pass
    recency_score = max(0.0, 20.0 * (1.0 - min(days_old, 365) / 365.0))
    citation_velocity = (record.get("citations") or 0) / max(days_old / 365.0, 0.25)
    citation_score = min(6.0, math.log1p(citation_velocity) * 1.5)
    info = lookup_journal(record.get("venue", ""), database)
    fit = journal_fit(
        record.get("venue", ""), info, record.get("title", ""), record.get("abstract", "")
    )
    quality_score = 0.0
    if info:
        quality_score += min(2.5, math.log1p(max(0, info["if"])) / 1.5)
        quality_score += {"一区": 1.5, "二区": 1.0, "三区": 0.5}.get(info["cas_rank"], 0)
    topic_component = assessment["topic_score"]
    method_component = assessment.get("method_score", 0) * 1.5
    engineering_component = assessment.get("engineering_score", 0) * 1.5
    specialty_component = max(method_component, engineering_component)
    total = (
        topic_component + specialty_component + recency_score
        + citation_score + fit["scope_score"] + quality_score
    )
    if assessment.get("is_review"):
        total -= 15
    breakdown = {
        "topic": round(topic_component, 1),
        "methodology": round(method_component, 1),
        "engineering": round(engineering_component, 1),
        "recency": round(recency_score, 1),
        "citation": round(citation_score, 1),
        "journal_scope": fit["scope_score"],
        "journal_priority": fit["priority_tier"],
        "journal_quality": round(quality_score, 1),
        "total": round(total, 1),
    }
    return round(total, 2), breakdown


def build_entry(record: dict, database: list[dict], assessment: dict, score: float, breakdown: dict) -> dict:
    info = lookup_journal(record.get("venue", ""), database)
    fit = journal_fit(
        record.get("venue", ""), info, record.get("title", ""), record.get("abstract", "")
    )
    authors = record.get("authors") or []
    doi = normalize_doi(record.get("doi"))
    title = record.get("title") or "N/A"
    return {
        "id": record.get("id", ""),
        "title": title,
        "doi": doi,
        "url": f"https://doi.org/{doi}" if doi else record.get("id", ""),
        "abstract": record.get("abstract", ""),
        "authors": authors,
        "authors_short": ", ".join(authors[:5]) + (" et al." if len(authors) > 5 else ""),
        "venue": record.get("venue", ""),
        "journal_info": info,
        "journal_fit": fit,
        "publication_date": record.get("publication_date", ""),
        "year": (record.get("publication_date") or "")[:4],
        "month": (record.get("publication_date") or "")[5:7],
        "citations": record.get("citations") or 0,
        "concepts": (record.get("concepts") or [])[:3],
        "sources": record.get("sources") or [],
        "source": " + ".join(record.get("sources") or []),
        "relevance_tier": assessment["tier"],
        "is_ai_method": assessment.get("is_ai_method", False),
        "topic_family": assessment.get("topic_family", ""),
        "track": assessment["track"],
        "track_label": assessment["track_label"],
        "recommendation_reason": assessment["reason"],
        "recommendation_score": score,
        "score_breakdown": breakdown,
        "article_kind": (
            "综述/观点"
            if assessment.get("is_review")
            else "研究论文"
        ),
    }


def select_diverse(candidates: list[tuple]) -> list[tuple]:
    selected = []
    selected_keys = set()
    venue_counts = Counter()
    track_counts = Counter()
    review_count = 0

    def can_add(item: tuple, enforce_track: bool = True) -> bool:
        _, key, record, assessment, _ = item
        venue = normalize_text(record.get("venue")) or "unknown"
        if key in selected_keys or venue_counts[venue] >= MAX_SAME_VENUE:
            return False
        if enforce_track and track_counts[assessment["track"]] >= MAX_SAME_TRACK:
            return False
        if assessment.get("is_review") and review_count >= MAX_REVIEWS:
            return False
        return True

    def add(item: tuple) -> None:
        nonlocal review_count
        _, key, record, assessment, _ = item
        venue = normalize_text(record.get("venue")) or "unknown"
        selected.append(item)
        selected_keys.add(key)
        venue_counts[venue] += 1
        track_counts[assessment["track"]] += 1
        review_count += assessment.get("is_review", False)

    top_candidates = [
        item for item in candidates
        if item[4].get("journal_priority") == "top"
    ]
    for item in top_candidates:
        if can_add(item):
            add(item)
        if len(selected) >= min(MIN_TOP_JOURNAL_TARGET, len(top_candidates)):
            break

    for item in candidates:
        if can_add(item):
            add(item)
        if len(selected) == MAX_PAPERS:
            return selected
    for item in candidates:
        if can_add(item, enforce_track=False):
            add(item)
        if len(selected) == MAX_PAPERS:
            break
    if len(candidates) >= MAX_PAPERS and len(selected) < MAX_PAPERS:
        selected_keys = {item[1] for item in selected}
        for item in candidates:
            if item[1] in selected_keys:
                continue
            add(item)
            if len(selected) == MAX_PAPERS:
                break
    return selected


def main() -> None:
    log.info("=" * 62)
    log.info("酶工程 + AI for Protein 每日文献 v8：双主题 + Top期刊优先")
    log.info("来源: %s；忽略历史: %s", ", ".join(ENABLED_SOURCES), IGNORE_SEEN)
    log.info("=" * 62)
    database = load_json(JOURNALS_DB)
    seen_dois, daily_log = load_seen_papers()
    today = datetime.now()
    today_tag = today.strftime("%Y-%m-%d")
    eligible: dict[str, dict] = {}
    assessments: dict[str, dict] = {}
    failures: dict[str, str] = {}
    rejection_counts = Counter()
    search_days = 0

    for days in SEARCH_WINDOWS:
        start_date = (today - timedelta(days=days)).strftime("%Y-%m-%d")
        raw_records, source_failures = search_all_sources(start_date, today_tag)
        failures.update(source_failures)
        for key, record in raw_records.items():
            if not record.get("title") or not record.get("abstract"):
                rejection_counts["元数据不完整或缺少摘要"] += 1
                continue
            assessment = assess_relevance(record["title"], record["abstract"])
            if not assessment["eligible"]:
                rejection_counts[assessment["reason"]] += 1
                continue
            eligible[key] = merge_record(eligible.get(key), record)
            assessments[key] = assessment
        search_days = days
        log.info("%s天窗口：多源去重后 %s 篇，通过主题准入 %s 篇", days, len(raw_records), len(eligible))
        if len(eligible) >= MAX_PAPERS * 3:
            break

    if not eligible:
        raise RuntimeError("所有可用来源均未产生通过主题准入的论文")
    new_records = {
        key: record for key, record in eligible.items()
        if IGNORE_SEEN or normalize_doi(record.get("doi")) not in seen_dois
    }
    if not new_records:
        raise RuntimeError("没有未推送的新论文；手动测试时可启用忽略历史")

    candidates = []
    for key, record in new_records.items():
        assessment = assess_relevance(record["title"], record["abstract"])
        score, breakdown = score_record(record, database, assessment)
        candidates.append((score, key, record, assessment, breakdown))
    candidates.sort(key=lambda item: item[0], reverse=True)
    selected = select_diverse(candidates)
    if not selected:
        raise RuntimeError("候选存在，但多样性筛选后没有可推送结果")

    entries = [
        build_entry(record, database, assessment, score, breakdown)
        for score, _, record, assessment, breakdown in selected
    ]
    track_summary = dict(Counter(entry["track_label"] for entry in entries))
    family_summary = dict(Counter(
        "AI for Protein" if entry.get("topic_family") == "ai_for_protein" else "酶工程"
        for entry in entries
    ))
    source_summary = dict(Counter(
        source for entry in entries for source in entry.get("sources", [])
    ))
    top_journal_count = sum(
        (entry.get("journal_fit") or {}).get("priority_tier") == "top"
        for entry in entries
    )
    output = {
        "generated_at": datetime.now().isoformat(),
        "total_works": len(eligible),
        "eligible_new_works": len(new_records),
        "search_days": search_days,
        "selection_method": "multi-source+target-journals+enzyme-or-ai-protein-gate-v8",
        "enabled_sources": list(ENABLED_SOURCES),
        "source_summary": source_summary,
        "source_failures": failures,
        "track_summary": track_summary,
        "family_summary": family_summary,
        "top_journal_count": top_journal_count,
        "tier_summary": dict(Counter(entry["relevance_tier"] for entry in entries)),
        "rejection_summary": dict(rejection_counts.most_common(8)),
        "papers": entries,
    }
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, f"papers_raw_{today_tag}.json")
    save_json(output_path, output)

    if IGNORE_SEEN:
        log.info("测试模式：未更新 seen_papers.json")
    else:
        new_dois = {entry["doi"] for entry in entries if entry["doi"]}
        seen_dois.update(new_dois)
        daily_log.append({"date": today_tag, "count": len(entries), "dois": sorted(new_dois)})
        save_seen_papers(seen_dois, daily_log)

    log.info(
        "最终精选 %s 篇；Top期刊=%s；主题=%s；赛道=%s；来源=%s",
        len(entries), top_journal_count, family_summary, track_summary, source_summary,
    )
    print(f"数据保存: {output_path}")
    for index, entry in enumerate(entries, 1):
        print(
            f"{index:02d}. [{entry['track_label']}] {entry['title'][:68]} "
            f"({entry['venue']}, {entry['recommendation_score']:.1f})"
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
    except Exception as exc:
        log.error("失败: %s", exc)
        traceback.print_exc()
        sys.exit(1)
