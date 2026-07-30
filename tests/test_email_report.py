import unittest
from datetime import datetime

from email_report import compact, gen_html


class EmailReportTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "total_works": 28,
            "enabled_sources": ["openalex", "pubmed", "crossref"],
            "track_summary": {"AI辅助酶设计": 1},
            "source_failures": {},
            "papers": [{
                "title": "AI-guided & experimentally validated enzyme design",
                "url": "https://doi.org/10.1000/test",
                "doi": "10.1000/test",
                "abstract": "English abstract.",
                "abstract_cn": "这是一段便于快速阅读的中文摘要。",
                "authors_short": "A. Author, B. Author",
                "venue": "ACS Catalysis",
                "journal_info": {"name": "ACS Catalysis", "cas_rank": "一区", "if": 12.9},
                "journal_fit": {"level": "高度对口", "scope_score": 10},
                "publication_date": "2026-07-29",
                "citations": 2,
                "sources": ["OpenAlex", "PubMed"],
                "track": "ai_design",
                "track_label": "AI辅助酶设计",
                "article_kind": "研究论文",
                "recommendation_reason": "标题聚焦酶；包含实验验证",
                "score_breakdown": {"topic": 45, "journal_scope": 10, "recency": 19},
            }],
        }

    def test_email_has_navigation_and_readable_card(self):
        result = gen_html(self.data, datetime(2026, 7, 30, 9, 0))
        self.assertIn('href="#paper-1"', result)
        self.assertIn('id="paper-1"', result)
        self.assertIn("为什么推荐", result)
        self.assertIn("中文摘要速读", result)
        self.assertIn("打开论文 / DOI", result)
        self.assertNotIn("<details", result)

    def test_untrusted_text_is_escaped(self):
        self.data["papers"][0]["title"] = "<script>alert(1)</script>"
        result = gen_html(self.data)
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)

    def test_compact_prefers_sentence_boundary(self):
        value = "第一句内容。" + "第二句内容很长。" * 30
        shortened = compact(value, 60)
        self.assertLessEqual(len(shortened), 61)
        self.assertTrue(shortened.endswith("……"))


if __name__ == "__main__":
    unittest.main()
