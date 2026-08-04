import unittest

from recommendation_engine import (
    CROSSREF_TARGET_JOURNALS,
    PUBMED_TARGET_JOURNAL_GROUPS,
    SEARCH_TOPICS,
    assess_relevance,
    journal_fit,
    lookup_journal,
    merge_record,
    select_diverse,
)


class RecommendationEngineTests(unittest.TestCase):
    def test_pubmed_and_crossref_query_slice_contains_both_topics(self):
        first_eight = " ".join(SEARCH_TOPICS[:8]).lower()
        self.assertIn("enzyme engineering", first_eight)
        self.assertIn("protein language model", first_eight)
        self.assertIn("biocatalysis", first_eight)
        self.assertIn("protein ligand", first_eight)
        self.assertIn("Nature Methods", sum(PUBMED_TARGET_JOURNAL_GROUPS, ()))
        self.assertIn("ACS Catalysis", CROSSREF_TARGET_JOURNALS)

    def test_core_enzyme_engineering_paper_is_accepted(self):
        result = assess_relevance(
            "Machine learning-guided enzyme engineering improves thermostability",
            "Variants were expressed and experimentally validated using kinetic assays.",
        )
        self.assertTrue(result["eligible"])
        self.assertEqual(result["tier"], "core")
        self.assertTrue(result["is_ai_method"])

    def test_non_ai_enzyme_engineering_is_equal_core_topic(self):
        result = assess_relevance(
            "Engineering enzyme thermostability and substrate selectivity by mutagenesis",
            "Variants were expressed and validated by activity and kinetic assays.",
        )
        self.assertTrue(result["eligible"])
        self.assertEqual(result["tier"], "core")
        self.assertFalse(result["is_ai_method"])
        self.assertEqual(result["topic_family"], "enzyme_engineering")
        self.assertGreater(result["engineering_score"], 0)

    def test_protein_language_foundation_model_is_accepted(self):
        result = assess_relevance(
            "A multimodal protein language foundation model for sequence and structure",
            "We introduce a new transformer framework with self-supervised pretraining "
            "for protein function prediction and mutation-effect prediction.",
        )
        self.assertTrue(result["eligible"])
        self.assertTrue(result["is_ai_method"])
        self.assertEqual(result["track"], "foundation_models")
        self.assertGreater(result["method_score"], 0)

    def test_protein_protein_interaction_model_is_accepted(self):
        result = assess_relevance(
            "Geometric deep learning for protein-protein interaction prediction",
            "Our novel equivariant neural network predicts complex interfaces and "
            "binding sites from protein structures.",
        )
        self.assertTrue(result["eligible"])
        self.assertEqual(result["track"], "protein_interactions")

    def test_protein_ligand_binding_model_is_accepted(self):
        result = assess_relevance(
            "A diffusion framework for protein-ligand binding affinity prediction",
            "The deep learning method jointly represents proteins and small molecules "
            "for docking and virtual screening.",
        )
        self.assertTrue(result["eligible"])
        self.assertEqual(result["track"], "protein_ligand")

    def test_drug_target_representation_model_uses_ligand_track(self):
        result = assess_relevance(
            "A representation learning framework for drug-target interaction prediction",
            "The deep learning model represents small molecules and protein targets.",
        )
        self.assertTrue(result["eligible"])
        self.assertEqual(result["track"], "protein_ligand")

    def test_enzyme_property_prediction_model_is_accepted(self):
        result = assess_relevance(
            "Machine learning predicts enzyme activity stability and selectivity",
            "A new protein representation model predicts kcat, thermostability, "
            "substrate specificity and mutation effects.",
        )
        self.assertTrue(result["eligible"])
        self.assertEqual(result["track"], "property_prediction")

    def test_general_protein_database_paper_is_rejected(self):
        result = assess_relevance(
            "InterPro: the protein sequence classification resource in 2026",
            "A database for protein family annotation using artificial intelligence.",
        )
        self.assertFalse(result["eligible"])

    def test_general_ai_method_without_protein_task_is_rejected(self):
        result = assess_relevance(
            "A new transformer for scientific document classification",
            "The foundation model classifies papers and clinical notes.",
        )
        self.assertFalse(result["eligible"])

    def test_protein_interaction_database_is_rejected(self):
        result = assess_relevance(
            "MPLID: a membrane protein-lipid interaction database",
            "This experimental resource mentions deep learning models for "
            "downstream protein-ligand prediction.",
        )
        self.assertFalse(result["eligible"])

    def test_ai_only_mentioned_as_downstream_tool_is_rejected(self):
        result = assess_relevance(
            "A large-scale resource of residue-level protein contacts",
            "The dataset can support deep learning for protein interaction prediction.",
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
            "Top期刊·主题对口",
        )
        self.assertEqual(
            journal_fit(
                "Bioresource Technology",
                {"name": "Bioresource Technology"},
                "Enzyme engineering for lignocellulosic biomass biorefineries",
            )["level"],
            "场景高度对口",
        )

    def test_conditional_journal_does_not_receive_unconditional_bonus(self):
        fit = journal_fit(
            "Journal of Agricultural and Food Chemistry",
            {"name": "Journal of Agricultural and Food Chemistry"},
            "A protein language model for antibody design",
        )
        self.assertEqual(fit["priority_tier"], "general")
        self.assertEqual(fit["scope_score"], 4)

    def test_top_journals_are_reserved_when_qualified_candidates_exist(self):
        candidates = []
        for index in range(6):
            assessment = {
                "tier": "core", "track": f"track{index}",
                "is_ai_method": True, "is_review": False,
            }
            priority = "general" if index < 2 else "top"
            candidates.append((
                120 - index, f"k{index}", {"venue": f"J{index}"}, assessment,
                {"journal_priority": priority},
            ))
        selected = select_diverse(candidates)
        self.assertGreaterEqual(
            sum(item[4].get("journal_priority") == "top" for item in selected), 4
        )

    def test_diversity_limits_same_venue(self):
        candidates = []
        for index in range(4):
            assessment = {
                "tier": "core",
                "track": "enzyme_engineering" if index < 3 else "foundation_models",
                "is_ai_method": True,
            }
            record = {"venue": "Same Journal" if index < 3 else "Other Journal"}
            candidates.append((100 - index, f"k{index}", record, assessment, {}))
        selected = select_diverse(candidates)
        venues = [item[2]["venue"] for item in selected]
        self.assertEqual(venues.count("Same Journal"), 2)

    def test_non_ai_enzyme_papers_are_not_capped_to_two(self):
        candidates = []
        for index in range(6):
            assessment = {
                "tier": "core",
                "track": "legacy_enzyme",
                "is_ai_method": False,
                "is_review": False,
            }
            candidates.append((100 - index, f"k{index}", {"venue": f"J{index}"}, assessment, {}))
        selected = select_diverse(candidates)
        self.assertEqual(sum(not item[3]["is_ai_method"] for item in selected), 6)


if __name__ == "__main__":
    unittest.main()
