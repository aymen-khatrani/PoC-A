# ============================================================
# Tests des pages du rapport
# ============================================================
#
# Les pages de tête sont le produit livré : elles méritent
# d'être testées pour elles-mêmes, et pas seulement à travers
# le pipeline.
#
# ============================================================

import pandas as pd
import pytest

from src import config
from src.config import CANONICAL_ID, CANONICAL_TEXT, SOURCE_ROW
from src.reporting import (
    QUESTIONS_COLUMNS,
    REQUIREMENTS_COLUMNS,
    RISKS_COLUMNS,
    SMART_DETAIL_COLUMNS,
    build_import_rows,
    build_llm_risk_summary,
    build_overview_frame,
    build_questions_frame,
    build_requirements_frame,
    build_risks_frame,
    build_smart_detail_frame,
    display_severity,
    format_share,
    llm_was_consulted,
    pluralize,
    prepare_frame_for_excel,
    sort_by_priority,
    write_report,
)
from src.rule_engine import FINDING_COLUMNS, SUMMARY_COLUMNS


def build_summary(lignes: list[dict]) -> pd.DataFrame:
    """Construit un résumé complet à partir de valeurs partielles."""

    defaut = {
        CANONICAL_ID: "R-001",
        CANONICAL_TEXT: "The door shall close within 3 s.",
        SOURCE_ROW: 2,
        "Quality_Status": config.STATUS_PRE_ANALYSIS_OK,
        "Quality_Score": 100,
        "SMART_Score": config.SMART_MAXIMUM_SCORE,
        "SMART_Profile": "S:OK M:OK A:OK R:OK T:OK",
        "SMART_Compliant_Axes": "5/5",
        "Singularity_Status": config.SINGULARITY_UNIQUE,
        "Estimated_Requirement_Count": 1,
        "Duplicate_Status": config.DUPLICATE_NONE,
        "Recommended_Action": "Aucune action.",
        "Risk_To_Assess": "NO",
        "Issue_Count": 0,
    }

    for dimension in config.SMART_DIMENSIONS:
        defaut[config.SMART_DIMENSION_COLUMNS[dimension]] = (
            config.SMART_VERDICT_OK
        )

    return pd.DataFrame(
        [{**defaut, **ligne} for ligne in lignes],
        columns=SUMMARY_COLUMNS,
    )


# ============================================================
# Utilitaires d'affichage
# ============================================================

class TestUtilitaires:
    """Les petits formatages portent le sens de la page."""

    @pytest.mark.parametrize(
        "nombre, attendu",
        [
            # « Zéro » commande le singulier.
            (0, "0 conforme"),
            (1, "1 conforme"),
            (4, "4 conformes"),
        ],
    )
    def test_accord_en_nombre(self, nombre, attendu) -> None:
        assert (
            pluralize(nombre, "conforme", "conformes") == attendu
        )

    def test_part_du_lot(self) -> None:
        assert format_share(3, 8) == "3 (38%)"

    def test_part_sans_lot_ne_divise_pas_par_zero(self) -> None:
        assert format_share(0, 0) == "0"

    def test_gravite_absente_laisse_la_cellule_vide(self) -> None:
        assert display_severity([]) == ""
        assert display_severity(["LOW", "HIGH"]) == "HIGH"

    def test_tri_par_priorite(self) -> None:
        summary = build_summary(
            [
                {
                    CANONICAL_ID: "A",
                    "Quality_Status": (
                        config.STATUS_PRE_ANALYSIS_OK
                    ),
                },
                {
                    CANONICAL_ID: "B",
                    "Quality_Status": (
                        config.STATUS_CLARIFICATION_REQUIRED
                    ),
                },
                {
                    CANONICAL_ID: "C",
                    "Quality_Status": (
                        config.STATUS_REVIEW_REQUIRED
                    ),
                },
            ]
        )

        ordre = list(sort_by_priority(summary)[CANONICAL_ID])

        assert ordre == ["B", "C", "A"]

    def test_tri_d_un_lot_vide(self) -> None:
        vide = pd.DataFrame(columns=SUMMARY_COLUMNS)

        assert sort_by_priority(vide).empty


# ============================================================
# Page 1 : la synthèse
# ============================================================

class TestSynthese:
    """La page de décision."""

    def test_lot_vide_ne_casse_pas_la_page(self) -> None:
        page = build_overview_frame(
            summary_frame=pd.DataFrame(columns=SUMMARY_COLUMNS),
            diagnostics={"analysed_requirement_count": 0},
        )

        assert not page.empty
        assert list(page.columns) == ["Indicateur", "Valeur"]

    def test_lignes_ecartees_annoncees(self) -> None:
        page = build_overview_frame(
            summary_frame=pd.DataFrame(columns=SUMMARY_COLUMNS),
            diagnostics={"analysed_requirement_count": 8},
            import_diagnostics={
                "total_rows": 10,
                "excluded_rows": 2,
            },
        )

        contenu = page.to_string()

        # Un rapport qui annonce huit exigences sans dire que le
        # fichier en contenait dix ne permet pas de savoir si
        # l'analyse a porté sur le bon périmètre.
        assert "Lignes lues dans la feuille" in contenu
        assert "Lignes écartées" in contenu

    def test_anomalies_d_import_remontees(self) -> None:
        lignes = build_import_rows(
            {
                "total_rows": 5,
                "excluded_rows": 0,
                "generated_ids": 3,
                "duplicate_ids": 2,
                "language_verdict": "other_language",
                "warnings": ["Colonne de texte douteuse."],
            }
        )

        contenu = " ".join(
            str(ligne["Indicateur"]) + str(ligne["Valeur"])
            for ligne in lignes
        )

        assert "Identifiants générés" in contenu
        assert "Identifiants dupliqués" in contenu
        assert "Langue détectée" in contenu
        assert "Colonne de texte douteuse." in contenu

    def test_anomalies_absentes_non_affichees(self) -> None:
        lignes = build_import_rows(
            {
                "total_rows": 5,
                "excluded_rows": 0,
                "generated_ids": 0,
                "duplicate_ids": 0,
                "language_verdict": "english",
                "warnings": [],
            }
        )

        libelles = [ligne["Indicateur"] for ligne in lignes]

        assert "Identifiants générés" not in libelles
        assert "Langue détectée" not in libelles

    def test_avis_du_modele_resume_quand_il_a_tourne(self) -> None:
        page = build_overview_frame(
            summary_frame=pd.DataFrame(columns=SUMMARY_COLUMNS),
            diagnostics={"analysed_requirement_count": 4},
            llm_diagnostics={
                "llm_enabled": True,
                "selected_count": 2,
                "decision_counts": {"CONFIRMED": 1, "ERROR": 1},
            },
        )

        contenu = page.to_string()

        assert "CE QUE LE MODÈLE A REVU" in contenu
        assert (
            config.LLM_DECISION_LABELS["CONFIRMED"] in contenu
        )
        # Une absence d'avis ne doit jamais passer pour un avis
        # favorable.
        assert "n'est pas un avis favorable" in contenu

    def test_aucune_section_modele_sans_llm(self) -> None:
        page = build_overview_frame(
            summary_frame=pd.DataFrame(columns=SUMMARY_COLUMNS),
            diagnostics={"analysed_requirement_count": 4},
            llm_diagnostics={"llm_enabled": False},
        )

        assert "CE QUE LE MODÈLE A REVU" not in page.to_string()

    def test_la_grille_est_expliquee(self) -> None:
        page = build_overview_frame(
            summary_frame=pd.DataFrame(columns=SUMMARY_COLUMNS),
            diagnostics={"analysed_requirement_count": 1},
        )

        contenu = page.to_string()

        # La légende vient de la configuration : une seule
        # formulation à maintenir.
        for question in config.SMART_DIMENSION_QUESTIONS.values():
            assert question[:40] in contenu


# ============================================================
# Page 2 : une ligne par exigence
# ============================================================

class TestPageDesExigences:
    """La page de travail de l'ingénieur."""

    def test_colonnes_sans_llm(self) -> None:
        page = build_requirements_frame(build_summary([{}]))

        assert list(page.columns) == REQUIREMENTS_COLUMNS
        assert "Avis du modèle" not in page.columns

    def test_colonne_du_modele_ajoutee_apres_analyse(self) -> None:
        summary = build_summary([{}, {CANONICAL_ID: "R-002"}])
        summary["LLM_Decision"] = ["CONFIRMED", "NOT_RUN"]

        page = build_requirements_frame(summary)

        assert "Avis du modèle" in page.columns
        assert config.LLM_DECISION_LABELS["NOT_RUN"] in list(
            page["Avis du modèle"]
        )

    def test_colonne_du_modele_absente_si_jamais_consulte(
        self,
    ) -> None:
        summary = build_summary([{}])
        summary["LLM_Decision"] = ["NOT_RUN"]

        assert llm_was_consulted(summary) is False
        assert "Avis du modèle" not in build_requirements_frame(
            summary
        )

    def test_symboles_des_axes(self) -> None:
        summary = build_summary(
            [
                {
                    config.SMART_DIMENSION_COLUMNS[
                        config.SMART_TIME_BOUND
                    ]: config.SMART_VERDICT_NOT_MET,
                }
            ]
        )

        page = build_requirements_frame(summary)

        assert page.at[0, "T"] == config.SMART_VERDICT_SYMBOLS[
            config.SMART_VERDICT_NOT_MET
        ]
        assert page.at[0, "S"] == config.SMART_VERDICT_SYMBOLS[
            config.SMART_VERDICT_OK
        ]


# ============================================================
# Page 3 : le détail par axe
# ============================================================

class TestDetailParAxe:
    """Seul le travail à faire est listé."""

    def test_axes_conformes_absents(self) -> None:
        page = build_smart_detail_frame(
            summary_frame=build_summary([{}]),
            findings_frame=pd.DataFrame(columns=FINDING_COLUMNS),
        )

        assert page.empty
        assert list(page.columns) == SMART_DETAIL_COLUMNS

    def test_axe_en_defaut_avec_sa_preuve(self) -> None:
        summary = build_summary(
            [
                {
                    config.SMART_DIMENSION_COLUMNS[
                        config.SMART_TIME_BOUND
                    ]: config.SMART_VERDICT_NOT_MET,
                }
            ]
        )

        findings = pd.DataFrame(
            [
                {
                    "Requirement_ID": "R-001",
                    "Rule_ID": "VER-001",
                    "Category": "NOT_VERIFIABLE",
                    "SMART_Dimension": config.SMART_TIME_BOUND,
                    "Severity": "HIGH",
                    "Evidence": "as soon as possible",
                    "Clarification_Question": "Quel délai ?",
                    "Rewrite_Template": "The system shall [X].",
                }
            ],
            columns=FINDING_COLUMNS,
        )

        page = build_smart_detail_frame(summary, findings)

        assert len(page) == 1
        assert page.at[0, "Gravité"] == "HIGH"
        assert page.at[0, "Preuves relevées"] == (
            "as soon as possible"
        )
        assert page.at[0, "Question à poser"] == "Quel délai ?"

    def test_unicite_traitee_comme_un_axe(self) -> None:
        summary = build_summary(
            [
                {
                    "Singularity_Status": (
                        config.SINGULARITY_TO_SPLIT
                    ),
                    "Estimated_Requirement_Count": 2,
                    "Singularity_Reason": "2 verbes d'obligation",
                }
            ]
        )

        page = build_smart_detail_frame(
            summary_frame=summary,
            findings_frame=pd.DataFrame(columns=FINDING_COLUMNS),
        )

        assert len(page) == 1
        assert page.at[0, "Axe"] == config.SMART_DIMENSION_LABELS[
            config.SINGULARITY_AXIS
        ]
        assert "2 exigences" in page.at[0, "Question à poser"]


# ============================================================
# Pages 4 et 5 : ce qui part au client
# ============================================================

class TestPagesLivrables:
    """Questions et risques : des brouillons à valider."""

    def test_seules_les_exigences_a_clarifier(self) -> None:
        summary = build_summary(
            [
                {CANONICAL_ID: "R-001"},
                {
                    CANONICAL_ID: "R-002",
                    "Clarification_Questions": "Quel délai ?",
                },
            ]
        )

        page = build_questions_frame(summary)

        assert list(page["Exigence"]) == ["R-002"]
        assert list(page.columns) == QUESTIONS_COLUMNS

    def test_le_texte_annote_est_prefere_au_texte_brut(
        self,
    ) -> None:
        summary = build_summary(
            [
                {
                    "Clarification_Questions": "Quel délai ?",
                    "Annotated_Text": (
                        "The door shall close "
                        "《rapidly》."
                    ),
                }
            ]
        )

        page = build_questions_frame(summary)

        assert "《rapidly》" in page.at[
            0,
            "Texte du client (passages en cause encadrés)",
        ]

    def test_colonnes_de_validation_vides(self) -> None:
        summary = build_summary(
            [{"Clarification_Questions": "Quel délai ?"}]
        )

        page = build_questions_frame(summary)

        # La validation humaine se trace à la main : l'outil ne
        # la préremplit jamais.
        for colonne in (
            "Décision de l'ingénieur",
            "Question retenue ou reformulée",
            "Validé par",
        ):
            assert page.at[0, colonne] == ""

    def test_seuls_les_risques_retenus(self) -> None:
        summary = build_summary(
            [
                {CANONICAL_ID: "R-001"},
                {
                    CANONICAL_ID: "R-002",
                    "Risk_To_Assess": "YES",
                    "Risk_Draft": "Title: ...",
                },
            ]
        )

        page = build_risks_frame(summary)

        assert list(page["Exigence"]) == ["R-002"]
        assert list(page.columns) == RISKS_COLUMNS

    def test_risque_du_modele_assemble(self) -> None:
        row = pd.Series(
            {
                "LLM_Risk_Recommended": "YES",
                "LLM_Risk_Title": "Ambiguous response time",
                "LLM_Risk_Cause": "No limit is given.",
                "LLM_Risk_Event": "Diverging interpretation.",
                "LLM_Risk_Consequences": "Rework.",
            }
        )

        resume = build_llm_risk_summary(row)

        assert "Title: Ambiguous response time" in resume
        assert "HUMAN VALIDATION REQUIRED" in resume

    def test_aucun_risque_du_modele_si_non_recommande(self) -> None:
        row = pd.Series(
            {
                "LLM_Risk_Recommended": "NO",
                "LLM_Risk_Title": "Ambiguous response time",
            }
        )

        assert build_llm_risk_summary(row) == ""


# ============================================================
# Écriture du classeur
# ============================================================

class TestEcriture:
    """Le classeur doit rester lisible et valide."""

    def test_feuille_de_synthese_sans_filtre(self, tmp_path):
        from openpyxl import load_workbook

        chemin = write_report(
            output_path=tmp_path / "rapport.xlsx",
            sheets={
                "1. Synthese": build_overview_frame(
                    summary_frame=pd.DataFrame(
                        columns=SUMMARY_COLUMNS
                    ),
                    diagnostics={"analysed_requirement_count": 0},
                ),
                "Analysis_Results": build_summary([{}]),
            },
            overview_sheets=["1. Synthese"],
        )

        classeur = load_workbook(chemin)

        synthese = classeur["1. Synthese"]
        resultats = classeur["Analysis_Results"]

        assert synthese.auto_filter.ref is None
        assert synthese.sheet_view.showGridLines is False

        # La page technique garde son filtre et son volet figé.
        assert resultats.auto_filter.ref is not None
        assert resultats.freeze_panes == "A2"

    def test_extension_imposee(self, tmp_path) -> None:
        with pytest.raises(ValueError, match="\\.xlsx"):
            write_report(
                output_path=tmp_path / "rapport.csv",
                sheets={"Feuille": build_summary([{}])},
            )

    def test_cellule_trop_longue_tronquee(self) -> None:
        frame = pd.DataFrame([{"Texte": "a" * 40000}])

        prepared = prepare_frame_for_excel(frame)

        assert len(prepared.at[0, "Texte"]) < 40000
        assert "tronqué" in prepared.at[0, "Texte"]
