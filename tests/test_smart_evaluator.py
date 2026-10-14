# ============================================================
# Tests de l'évaluation SMART et de la singularité
# ============================================================

import pandas as pd
import pytest

from src import config
from src.config import (
    CANONICAL_ID,
    CANONICAL_TEXT,
    CANONICAL_TYPE,
    SOURCE_ROW,
    SOURCE_SHEET,
)
from src.rule_engine import (
    analyse_requirements,
    escalate_status_for_singularity,
    smart_column_name,
)
from src.smart_evaluator import (
    build_recommended_action,
    compute_smart_score,
    evaluate_dimensions,
    evaluate_requirement,
    evaluate_singularity,
)


class ConstatFactice:
    """Constat minimal, conforme au contrat attendu par le module."""

    def __init__(
        self,
        rule_id: str,
        severity: str,
        smart_dimension: str,
        category: str = "AMBIGUITY",
        evidence: str = "preuve",
    ) -> None:
        self.rule_id = rule_id
        self.severity = severity
        self.smart_dimension = smart_dimension
        self.category = category
        self.evidence = evidence
        self.clarification_question = "Question ?"
        self.rewrite_template = "The system shall [X]."


def build_frame(textes: list[str]) -> pd.DataFrame:
    """Construit un tableau normalisé pour les tests."""

    return pd.DataFrame(
        [
            {
                CANONICAL_ID: f"T-{position:03d}",
                CANONICAL_TEXT: texte,
                CANONICAL_TYPE: "Technical Req",
                SOURCE_ROW: position + 1,
                SOURCE_SHEET: "test",
            }
            for position, texte in enumerate(textes, start=1)
        ]
    )


# ============================================================
# Les cinq axes
# ============================================================

class TestAxesSmart:
    """Chaque constat doit peser sur le bon axe."""

    def test_sans_constat_tous_les_axes_sont_conformes(self) -> None:
        resultat = evaluate_requirement(
            text="The door shall close within 3 s.",
            findings=[],
        )

        assert resultat["score"] == config.SMART_MAXIMUM_SCORE
        assert resultat["compliant_count"] == len(
            config.SMART_DIMENSIONS
        )
        assert resultat["not_met"] == []

    def test_gravite_haute_rend_l_axe_non_conforme(self) -> None:
        dimensions = evaluate_dimensions(
            [
                ConstatFactice(
                    rule_id="VER-001",
                    severity="HIGH",
                    smart_dimension=config.SMART_TIME_BOUND,
                )
            ]
        )

        assert (
            dimensions[config.SMART_TIME_BOUND]["verdict"]
            == config.SMART_VERDICT_NOT_MET
        )
        assert (
            dimensions[config.SMART_SPECIFIC]["verdict"]
            == config.SMART_VERDICT_OK
        )

    def test_gravite_moyenne_demande_une_verification(self) -> None:
        dimensions = evaluate_dimensions(
            [
                ConstatFactice(
                    rule_id="AMB-002",
                    severity="MEDIUM",
                    smart_dimension=config.SMART_SPECIFIC,
                )
            ]
        )

        assert (
            dimensions[config.SMART_SPECIFIC]["verdict"]
            == config.SMART_VERDICT_TO_CHECK
        )

    def test_la_gravite_la_plus_elevee_decide(self) -> None:
        dimensions = evaluate_dimensions(
            [
                ConstatFactice(
                    rule_id="AMB-002",
                    severity="LOW",
                    smart_dimension=config.SMART_SPECIFIC,
                ),
                ConstatFactice(
                    rule_id="COND-005",
                    severity="HIGH",
                    smart_dimension=config.SMART_SPECIFIC,
                ),
            ]
        )

        assert (
            dimensions[config.SMART_SPECIFIC]["verdict"]
            == config.SMART_VERDICT_NOT_MET
        )
        assert (
            dimensions[config.SMART_SPECIFIC]["highest_severity"]
            == "HIGH"
        )

    def test_un_axe_non_conforme_coute_vingt_points(self) -> None:
        dimensions = evaluate_dimensions(
            [
                ConstatFactice(
                    rule_id="VER-001",
                    severity="HIGH",
                    smart_dimension=config.SMART_TIME_BOUND,
                )
            ]
        )

        assert compute_smart_score(dimensions) == (
            config.SMART_MAXIMUM_SCORE - 20
        )

    def test_constat_sans_axe_retombe_sur_sa_categorie(self) -> None:
        dimensions = evaluate_dimensions(
            [
                ConstatFactice(
                    rule_id="OLD-001",
                    severity="HIGH",
                    smart_dimension="",
                    category="NOT_VERIFIABLE",
                )
            ]
        )

        assert (
            dimensions[config.SMART_MEASURABLE]["verdict"]
            == config.SMART_VERDICT_NOT_MET
        )

    def test_texte_vide_n_est_pas_declare_conforme(self) -> None:
        resultat = evaluate_requirement(text="", findings=[])

        for dimension in config.SMART_DIMENSIONS:
            assert (
                resultat["dimensions"][dimension]["verdict"]
                == config.SMART_VERDICT_NOT_ASSESSED
            )

        assert resultat["score"] == 0
        assert "Compléter" in resultat["action"]


# ============================================================
# Singularité
# ============================================================

class TestSingularite:
    """Une exigence, une obligation."""

    def test_une_seule_obligation_est_unique(self) -> None:
        resultat = evaluate_singularity(
            "The door shall close within 3 s."
        )

        assert resultat["status"] == config.SINGULARITY_UNIQUE
        assert resultat["estimated_count"] == 1

    def test_deux_obligations_demandent_un_decoupage(self) -> None:
        resultat = evaluate_singularity(
            "The system shall display the speed and the "
            "controller shall log every event."
        )

        assert resultat["status"] == config.SINGULARITY_TO_SPLIT
        assert resultat["obligation_count"] == 2
        assert resultat["estimated_count"] == 2
        assert resultat["reasons"]

    def test_enumeration_demande_un_decoupage(self) -> None:
        resultat = evaluate_singularity(
            "The gateway shall support:\n"
            "- Ethernet\n"
            "- CAN bus\n"
            "- serial link"
        )

        assert resultat["status"] == config.SINGULARITY_TO_SPLIT
        assert resultat["estimated_count"] >= 3

    def test_connecteur_additif_demande_une_verification(
        self,
    ) -> None:
        resultat = evaluate_singularity(
            "The system shall be available as well as "
            "maintainable."
        )

        assert resultat["status"] == config.SINGULARITY_TO_CHECK
        assert resultat["evidence"]

    def test_chapelet_de_points_virgules_signale_une_liste(
        self,
    ) -> None:
        resultat = evaluate_singularity(
            "The system shall log the event; the record is kept "
            "for 90 days; the operator is notified."
        )

        assert resultat["status"] == config.SINGULARITY_TO_CHECK

    def test_texte_vide_n_est_pas_evalue(self) -> None:
        resultat = evaluate_singularity("")

        assert resultat["status"] == config.SINGULARITY_NOT_ASSESSED
        assert resultat["estimated_count"] == 0

    def test_constat_de_non_atomicite_pris_en_compte(self) -> None:
        resultat = evaluate_singularity(
            "The system shall provide a report and a log.",
            findings=[
                ConstatFactice(
                    rule_id="ATOM-002",
                    severity="LOW",
                    smart_dimension=config.SINGULARITY_AXIS,
                    category="POTENTIALLY_NON_ATOMIC",
                    evidence="shall provide a report and a log",
                )
            ],
        )

        assert resultat["status"] == config.SINGULARITY_TO_CHECK
        assert "ATOM-002" in " ".join(resultat["reasons"])

    def test_la_singularite_n_entre_pas_dans_le_score(self) -> None:
        resultat = evaluate_requirement(
            "The system shall display the speed and the "
            "controller shall log every event."
        )

        # Aucune règle de rédaction n'est en défaut : le score
        # SMART reste plein, seule l'unicité est en cause.
        assert resultat["score"] == config.SMART_MAXIMUM_SCORE
        assert (
            resultat["singularity"]["status"]
            == config.SINGULARITY_TO_SPLIT
        )


# ============================================================
# Action recommandée
# ============================================================

class TestActionRecommandee:
    """L'action dit quoi faire, dans l'ordre du travail réel."""

    def test_le_decoupage_passe_avant_la_redaction(self) -> None:
        dimensions = evaluate_dimensions(
            [
                ConstatFactice(
                    rule_id="VER-001",
                    severity="HIGH",
                    smart_dimension=config.SMART_TIME_BOUND,
                )
            ]
        )

        action = build_recommended_action(
            dimensions=dimensions,
            singularity={
                "status": config.SINGULARITY_TO_SPLIT,
                "estimated_count": 3,
            },
        )

        assert "Scinder en 3" in action

    def test_axe_non_conforme_avant_axe_a_verifier(self) -> None:
        dimensions = evaluate_dimensions(
            [
                ConstatFactice(
                    rule_id="VER-001",
                    severity="HIGH",
                    smart_dimension=config.SMART_TIME_BOUND,
                ),
                ConstatFactice(
                    rule_id="AMB-002",
                    severity="MEDIUM",
                    smart_dimension=config.SMART_SPECIFIC,
                ),
            ]
        )

        action = build_recommended_action(
            dimensions=dimensions,
            singularity={
                "status": config.SINGULARITY_UNIQUE,
                "estimated_count": 1,
            },
        )

        assert action.startswith("Corriger")
        assert (
            config.SMART_DIMENSION_ACTIONS[config.SMART_TIME_BOUND]
            in action
        )


# ============================================================
# Intégration dans le moteur
# ============================================================

class TestIntegrationMoteur:
    """Le résumé doit porter la lecture SMART."""

    def test_colonnes_smart_presentes(self, rules) -> None:
        resultat = analyse_requirements(
            build_frame(["The door shall close within 3 s."]),
            rules,
        )

        colonnes = resultat["summary"].columns

        assert "SMART_Score" in colonnes
        assert "SMART_Profile" in colonnes
        assert "Singularity_Status" in colonnes
        assert "Recommended_Action" in colonnes

        for dimension in config.SMART_DIMENSIONS:
            assert smart_column_name(dimension) in colonnes

    def test_axe_du_constat_trace_dans_le_rapport(
        self,
        rules,
    ) -> None:
        resultat = analyse_requirements(
            build_frame(["The system shall respond rapidly."]),
            rules,
        )

        constats = resultat["findings"]

        assert "SMART_Dimension" in constats.columns
        assert (
            config.SMART_TIME_BOUND
            in constats["SMART_Dimension"].tolist()
        )

    def test_exigence_a_scinder_ne_reste_pas_conforme(
        self,
        rules,
    ) -> None:
        resultat = analyse_requirements(
            build_frame(
                [
                    "The system shall display the speed and the "
                    "controller shall log every event."
                ]
            ),
            rules,
        )

        ligne = resultat["summary"].iloc[0]

        assert (
            ligne["Singularity_Status"]
            == config.SINGULARITY_TO_SPLIT
        )
        assert (
            ligne["Quality_Status"] == config.STATUS_REVIEW_REQUIRED
        )

    def test_diagnostics_smart(self, rules) -> None:
        resultat = analyse_requirements(
            build_frame(
                [
                    "The door shall close within 3 s.",
                    "The system shall respond rapidly.",
                ]
            ),
            rules,
        )

        diagnostics = resultat["diagnostics"]

        assert diagnostics["average_smart_score"] <= (
            config.SMART_MAXIMUM_SCORE
        )
        assert diagnostics["fully_smart_count"] == 1
        assert diagnostics["requirements_to_split"] == 0
        assert (
            diagnostics["smart_axis_not_met_counts"][
                config.SMART_DIMENSION_LABELS[
                    config.SMART_TIME_BOUND
                ]
            ]
            == 1
        )

    @pytest.mark.parametrize(
        "statut_initial, attendu",
        [
            (
                config.STATUS_PRE_ANALYSIS_OK,
                config.STATUS_REVIEW_REQUIRED,
            ),
            (
                config.STATUS_REVIEW_RECOMMENDED,
                config.STATUS_REVIEW_REQUIRED,
            ),
            (
                config.STATUS_CLARIFICATION_REQUIRED,
                config.STATUS_CLARIFICATION_REQUIRED,
            ),
        ],
    )
    def test_escalade_du_statut(
        self,
        statut_initial,
        attendu,
    ) -> None:
        assert (
            escalate_status_for_singularity(
                quality_status=statut_initial,
                singularity_status=config.SINGULARITY_TO_SPLIT,
            )
            == attendu
        )

    def test_statut_inchange_si_exigence_unique(self) -> None:
        assert (
            escalate_status_for_singularity(
                quality_status=config.STATUS_PRE_ANALYSIS_OK,
                singularity_status=config.SINGULARITY_UNIQUE,
            )
            == config.STATUS_PRE_ANALYSIS_OK
        )
