import unittest

from recommendation_engine import (
    assess_relevance,
    journal_fit,
    lookup_journal,
    merge_record,
    select_diverse,
)


class RecommendationEngineTests(unittest.TestCase):
    def test_core_enzyme_engineering_paper_is_accepted(self):
        result = assess_relevance(
            "Machine learning-guided enzyme engineering improves thermostability",
            "Variants were expressed and experimentally validated using kinetic assays.",
        )
        self.assertTrue(result["eligible"])
        self.assertEqual(result["tier"], "core")
        self.assertIn("AI", result["reason"])

    def test_general_protein_database_paper_is_rejected(self):
        result = assess_relevance(
            "InterPro: the protein sequence classification resource in 2026",
            "A database for protein family annotation using artificial intelligence.",
        )
        self.assertFalse(result["eligible"])

    def test_nanozyme_therapy_paper_is_rejected(self):
        result = assess_relevance(
            "Metal nanozymes for tumor catalytic therapy",
            "The enzyme-like nanoparticles improve cancer treatment.",
        )
        self.assertFalse(result["eligible"])

    def test_ecology_enzyme_catalog_is_rejected_without_engineering_action(self):
        result = assess_relevance(
            "Carbohydrate-active enzymes of soil prophages enhance global carbon cycling",
            "Deep learning models identify enzyme families across a global gene catalogue.",
        )
        self.assertFalse(result["eligible"])

    def test_material_catalyst_is_rejected_even_if_abstract_mentions_enzymes(self):
        result = assess_relevance(
            "Intrinsic phonons control catalytic reactivity in 2D materials",
            "The mechanism is compared with enzymatic catalytic activity.",
        )
        self.assertFalse(result["eligible"])

    def test_nature_subjournal_exact_match_wins(self):
        database = [
            {"name": "Nature", "if": 60, "cas_rank": "一区", "aliases": ["Nature"]},
            {
                "name": "Nature Methods",
                "if": 30,
                "cas_rank": "一区",
                "aliases": ["Nat Methods", "Nature Methods"],
            },
        ]
        match = lookup_journal("Nature Methods", database)
        self.assertEqual(match["name"], "Nature Methods")

    def test_cross_source_records_merge_by_richer_metadata(self):
        base = {
            "doi": "10.1000/test",
            "title": "Enzyme design",
            "abstract": "",
            "authors": ["A"],
            "venue": "",
            "publication_date": "2026-01-01",
            "citations": 2,
            "concepts": [],
            "sources": ["Crossref"],
        }
        incoming = {
            **base,
            "abstract": "A detailed abstract.",
            "authors": ["A", "B"],
            "venue": "ACS Catalysis",
            "citations": 5,
            "sources": ["PubMed"],
        }
        merged = merge_record(base, incoming)
        self.assertEqual(merged["abstract"], "A detailed abstract.")
        self.assertEqual(merged["citations"], 5)
        self.assertEqual(merged["sources"], ["Crossref", "PubMed"])

    def test_journal_scope_separates_fit_from_prestige(self):
        self.assertEqual(
            journal_fit("ACS Catalysis", {"name": "ACS Catalysis"})["level"],
            "高度对口",
        )
        self.assertEqual(
            journal_fit("Nature", {"name": "Nature"})["level"],
            "综合期刊·按主题入选",
        )
        self.assertEqual(
            journal_fit("Bioresource Technology", {"name": "Bioresource Technology"})["level"],
            "高度对口",
        )

    def test_diversity_limits_same_venue(self):
        candidates = []
        for index in range(4):
            assessment = {
                "tier": "core",
                "track": "enzyme_engineering" if index < 3 else "biocatalysis",
            }
            record = {"venue": "Same Journal" if index < 3 else "Other Journal"}
            candidates.append((100 - index, f"k{index}", record, assessment, {}))
        selected = select_diverse(candidates)
        venues = [item[2]["venue"] for item in selected]
        self.assertEqual(venues.count("Same Journal"), 2)


if __name__ == "__main__":
    unittest.main()
