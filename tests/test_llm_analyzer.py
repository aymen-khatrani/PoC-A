# ============================================================
# Tests de l'analyseur LLM
# ============================================================
#
# Aucun test ne contacte Ollama : un client factice renvoie des
# réponses choisies, ce qui permet de vérifier la logique de
# contrôle, la reprise et la tolérance aux réponses abîmées.
#
# ============================================================

import json

import pandas as pd
import pytest

from src.config import CANONICAL_ID, CANONICAL_TEXT, CANONICAL_TYPE
from src.llm_analyzer import (
    DECISION_CONFIRMED,
    DECISION_ERROR,
    DECISION_FALSE_POSITIVE,
    DECISION_NEEDS_EXPERT_REVIEW,
    DECISION_PARTIALLY_CONFIRMED,
    LLMAnalyzer,
    LLMSettings,
    build_response_schema,
    build_system_prompt,
    build_user_prompt,
    calculate_decision,
    merge_llm_results,
    parse_json_response,
    select_llm_candidates,
)

CONSTATS = [
    {
        "rule_id": "AMB-001",
        "category": "AMBIGUITY",
        "severity": "HIGH",
        "evidence": ["rapidly"],
        "occurrence_count": 2,
        "explanation": "Not measurable.",
    }
]


def reponse_valide(
    identifiants: list[str],
    presents: list[bool],
    risque: bool = False,
) -> str:
    """Construit une réponse JSON conforme au schéma."""

    return json.dumps(
        {
            "findings_assessment": [
                {
                    "rule_id": identifiant,
                    "issue_present": present,
                    "reason": "raison",
                }
                for identifiant, present in zip(
                    identifiants,
                    presents,
                )
            ],
            "missing_information": ["maximum response time"],
            "clarification_questions": ["What is the limit?"],
            "proposed_rewrite": (
                "The system shall respond within "
                "[MAXIMUM RESPONSE TIME TO BE CONFIRMED]."
            ),
            "risk_recommended": risque,
            "risk_draft": {
                "title": "titre" if risque else "",
                "cause": "cause" if risque else "",
                "event": "evenement" if risque else "",
                "consequences": ["rework"] if risque else [],
            },
        }
    )


class ClientFactice:
    """Client ollama simulé."""

    def __init__(self, reponses: list) -> None:
        self.reponses = reponses
        self.appels = 0

    def list(self) -> dict:
        return {"models": [{"model": "qwen2.5:3b"}]}

    def chat(self, **_) -> dict:
        self.appels += 1
        reponse = self.reponses[
            min(self.appels - 1, len(self.reponses) - 1)
        ]

        if isinstance(reponse, Exception):
            raise reponse

        return {
            "message": {"content": reponse},
            "eval_count": 120,
            "prompt_eval_count": 600,
            "eval_duration": 8_000_000_000,
        }


def analyseur(reponses: list) -> LLMAnalyzer:
    """Prépare un analyseur branché sur le client factice."""

    instance = LLMAnalyzer(LLMSettings())
    instance._client = ClientFactice(reponses)

    return instance


class TestDecisionCalculeeEnPython:
    """La décision globale n'est jamais demandée au modèle."""

    def test_tous_confirmes(self) -> None:
        assert (
            calculate_decision(
                [{"rule_id": "A", "issue_present": True, "reason": ""}]
            )
            == DECISION_CONFIRMED
        )

    def test_mixte(self) -> None:
        assert (
            calculate_decision(
                [
                    {"rule_id": "A", "issue_present": True, "reason": ""},
                    {"rule_id": "B", "issue_present": False, "reason": ""},
                ]
            )
            == DECISION_PARTIALLY_CONFIRMED
        )

    def test_tous_rejetes(self) -> None:
        assert (
            calculate_decision(
                [{"rule_id": "A", "issue_present": False, "reason": ""}]
            )
            == DECISION_FALSE_POSITIVE
        )

    def test_valeur_illisible(self) -> None:
        assert (
            calculate_decision(
                [{"rule_id": "A", "issue_present": None, "reason": ""}]
            )
            == DECISION_NEEDS_EXPERT_REVIEW
        )

    def test_aucune_evaluation(self) -> None:
        assert calculate_decision([]) == DECISION_NEEDS_EXPERT_REVIEW


class TestLectureDesReponses:
    """Tolérance aux réponses mal emballées."""

    def test_bloc_markdown(self) -> None:
        assert parse_json_response('```json\n{"a": 1}\n```')["a"] == 1

    def test_texte_autour_du_json(self) -> None:
        brut = 'Voici le résultat :\n{"a": 2}\nFin.'

        assert parse_json_response(brut)["a"] == 2

    def test_json_irrecuperable(self) -> None:
        with pytest.raises(ValueError):
            parse_json_response("pas de json ici")

    def test_liste_refusee(self) -> None:
        with pytest.raises(ValueError, match="objet"):
            parse_json_response("[1, 2, 3]")


class TestAnalyseUneExigence:
    """Comportement de bout en bout sur une exigence."""

    def test_cas_nominal(self) -> None:
        instance = analyseur(
            [reponse_valide(["AMB-001"], [True], risque=True)]
        )

        result = instance.analyze_requirement(
            requirement_id="R-1",
            requirement_text="The system should respond rapidly.",
            object_type="Technical Req",
            findings=CONSTATS,
        )

        assert result.analyzed is True
        assert result.decision == DECISION_CONFIRMED
        assert result.attempts == 1
        assert result.confirmed_findings[0]["rule_id"] == "AMB-001"
        assert result.risk_recommended is True
        assert "[MAXIMUM RESPONSE TIME" in result.proposed_rewrite

    def test_reprise_unique_sur_json_tronque(self) -> None:
        instance = analyseur(
            [
                '{"findings_assessment": [{"rule_id": "AMB-0',
                reponse_valide(["AMB-001"], [True]),
            ]
        )

        result = instance.analyze_requirement(
            requirement_id="R-2",
            requirement_text="The system should respond rapidly.",
            findings=CONSTATS,
        )

        assert result.analyzed is True
        assert result.attempts == 2

    def test_pas_plus_d_une_reprise(self) -> None:
        instance = analyseur(["réponse invalide"])

        result = instance.analyze_requirement(
            requirement_id="R-3",
            requirement_text="The system should respond rapidly.",
            findings=CONSTATS,
        )

        assert result.analyzed is False
        assert result.decision == DECISION_ERROR
        assert result.attempts == 2
        assert instance._client.appels == 2

    def test_regle_inventee_rejetee(self) -> None:
        instance = analyseur([reponse_valide(["INVENTEE-999"], [True])])

        result = instance.analyze_requirement(
            requirement_id="R-4",
            requirement_text="The system should respond rapidly.",
            findings=CONSTATS,
        )

        assert result.decision == DECISION_ERROR
        assert "inconnues" in result.error

    def test_doublon_du_modele_fusionne(self) -> None:
        instance = analyseur(
            [reponse_valide(["AMB-001", "AMB-001"], [True, True])]
        )

        result = instance.analyze_requirement(
            requirement_id="R-5",
            requirement_text="The system should respond rapidly.",
            findings=CONSTATS,
        )

        # Une évaluation en doublon ne doit plus faire perdre
        # toute la réponse.
        assert result.analyzed is True
        assert result.decision == DECISION_CONFIRMED

    def test_risque_non_recommande_vide_les_champs(self) -> None:
        instance = analyseur(
            [reponse_valide(["AMB-001"], [False], risque=False)]
        )

        result = instance.analyze_requirement(
            requirement_id="R-6",
            requirement_text="The system should respond rapidly.",
            findings=CONSTATS,
        )

        assert result.risk_recommended is False
        assert result.risk_draft.title == ""
        assert result.risk_draft.consequences == []

    def test_erreur_contenue_sans_interrompre(self) -> None:
        instance = analyseur([RuntimeError("service indisponible")])

        result = instance.analyze_requirement(
            requirement_id="R-7",
            requirement_text="The system should respond rapidly.",
            findings=CONSTATS,
        )

        assert result.decision == DECISION_ERROR
        assert "service indisponible" in result.error

    def test_texte_vide(self) -> None:
        result = analyseur([]).analyze_requirement(
            requirement_id="R-8",
            requirement_text="",
            findings=CONSTATS,
        )

        assert result.decision == DECISION_ERROR
        assert "vide" in result.error

    def test_revue_complete_sans_constat(self) -> None:
        instance = analyseur(
            [reponse_valide(["FULL-REVIEW"], [False])]
        )

        result = instance.analyze_requirement(
            requirement_id="R-9",
            requirement_text=(
                "The braking system shall stop within 250 m."
            ),
            findings=[],
        )

        assert result.review_mode == "FULL_CONTEXT_REVIEW"
        assert result.decision == DECISION_FALSE_POSITIVE


class TestPrompt:
    """Le prompt doit rester indépendant du domaine."""

    def test_aucun_exemple_metier_dans_le_prompt(self) -> None:
        texte = (
            build_system_prompt()
            + build_user_prompt(
                requirement_id="R-1",
                requirement_text="texte",
                object_type="Technical Req",
                findings=CONSTATS,
                schema=build_response_schema(["AMB-001"]),
            )
        )

        # Un exemple de temps de réponse contaminait les
        # analyses d'exigences sans rapport.
        assert "respond rapidly" not in texte
        assert "MAXIMUM RESPONSE TIME" not in texte

    def test_schema_interdit_les_regles_inventees(self) -> None:
        schema = build_response_schema(["AMB-001", "WEAK-001"])

        enumeration = schema["properties"]["findings_assessment"][
            "items"
        ]["properties"]["rule_id"]["enum"]

        assert enumeration == ["AMB-001", "WEAK-001"]
        assert (
            schema["properties"]["findings_assessment"]["maxItems"]
            == 2
        )


class TestSelectionEtFusion:
    """Sélection des candidats et fusion des résultats."""

    def build_summary(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    CANONICAL_ID: "A",
                    CANONICAL_TEXT: "texte a",
                    CANONICAL_TYPE: "Technical Req",
                    "Issue_Count": 2,
                    "Highest_Severity": "HIGH",
                    "Quality_Score": 70,
                },
                {
                    CANONICAL_ID: "B",
                    CANONICAL_TEXT: "texte b",
                    CANONICAL_TYPE: "Technical Req",
                    "Issue_Count": 1,
                    "Highest_Severity": "LOW",
                    "Quality_Score": 95,
                },
                {
                    CANONICAL_ID: "C",
                    CANONICAL_TEXT: "texte c",
                    CANONICAL_TYPE: "Technical Req",
                    "Issue_Count": 0,
                    "Highest_Severity": "NONE",
                    "Quality_Score": 100,
                },
            ]
        )

    def test_gravite_minimale_respectee(self) -> None:
        candidats = select_llm_candidates(
            self.build_summary(),
            minimum_severity="MEDIUM",
        )

        assert list(candidats[CANONICAL_ID]) == ["A"]

    def test_les_cas_propres_peuvent_etre_inclus(self) -> None:
        candidats = select_llm_candidates(
            self.build_summary(),
            minimum_severity="MEDIUM",
            include_clean=True,
        )

        assert set(candidats[CANONICAL_ID]) == {"A", "C"}

    def test_limite_respectee(self) -> None:
        candidats = select_llm_candidates(
            self.build_summary(),
            limit=1,
            minimum_severity="LOW",
        )

        assert len(candidats) == 1

    def test_fusion_marque_les_exigences_non_soumises(self) -> None:
        summary = self.build_summary()

        llm_frame = pd.DataFrame(
            [
                {
                    CANONICAL_ID: "A",
                    "Review_Mode": "VALIDATE_RULE_FINDINGS",
                    "LLM_Analyzed": "YES",
                    "LLM_Decision": DECISION_CONFIRMED,
                }
            ]
        )

        fusion = merge_llm_results(summary, llm_frame)

        decisions = dict(
            zip(fusion[CANONICAL_ID], fusion["LLM_Decision"])
        )

        # Une absence d'avis ne doit jamais ressembler à un avis
        # favorable.
        assert decisions["A"] == DECISION_CONFIRMED
        assert decisions["B"] == "NOT_RUN"
        assert decisions["C"] == "NOT_RUN"

    def test_fusion_sans_resultat_llm(self) -> None:
        fusion = merge_llm_results(
            self.build_summary(),
            pd.DataFrame(),
        )

        assert (fusion["LLM_Decision"] == "NOT_RUN").all()
        assert len(fusion) == 3
