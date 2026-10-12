# ============================================================
# Tests du moteur de règles
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
    EngineSettings,
)
from src.rule_engine import (
    analyse_requirements,
    build_llm_findings,
    compute_quality_score,
)

# Exigences correctement rédigées : aucune alerte attendue.
EXIGENCES_CORRECTES = [
    "The braking system shall stop the train within 250 m from "
    "80 km/h on dry rails, verified by test procedure TP-14.",
    "The supplier shall deliver the maintenance manual in PDF "
    "format before the Factory Acceptance Test.",
    "The cabinet shall weigh 45 kg plus or minus 2 kg, measured "
    "with a calibrated scale.",
    "The door shall open when the train speed is 0 km/h and the "
    "platform side is detected by sensor S12.",
    "The equipment shall comply with EN 61373 Category 1 "
    "Class B, as demonstrated by the vibration test report.",
]

# Exigences défectueuses : au moins une alerte attendue.
EXIGENCES_DEFECTUEUSES = [
    "The system should respond rapidly.",
    "The interface shall be user-friendly.",
    "The equipment shall be maximally modular.",
    "The supplier shall act as quickly as possible.",
    "The device shall handle errors appropriately.",
    "The system shall provide adequate performance.",
]


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


class TestDetection:
    """Comportement attendu sur des cas connus."""

    def test_exigences_correctes_non_signalees(self, rules) -> None:
        result = analyse_requirements(
            build_frame(EXIGENCES_CORRECTES),
            rules,
        )

        signalees = result["summary"][
            result["summary"]["Issue_Count"] > 0
        ]

        assert signalees.empty, (
            "Faux positifs sur : "
            + ", ".join(signalees["Evidence"].tolist())
        )

    def test_exigences_defectueuses_signalees(self, rules) -> None:
        result = analyse_requirements(
            build_frame(EXIGENCES_DEFECTUEUSES),
            rules,
        )

        assert (result["summary"]["Issue_Count"] > 0).all()

    def test_preuve_et_position_conservees(self, rules) -> None:
        result = analyse_requirements(
            build_frame(["The system should respond rapidly."]),
            rules,
        )

        findings = result["findings"]

        assert not findings.empty
        assert (findings["Evidence"].str.len() > 0).all()
        assert (findings["End_Position"] > findings["Start_Position"]).all()

    def test_texte_original_jamais_modifie(self, rules) -> None:
        texte = "The system should respond rapidly."

        result = analyse_requirements(build_frame([texte]), rules)

        assert result["summary"].at[0, CANONICAL_TEXT] == texte


class TestComptageEtScore:
    """Un défaut répété reste un seul défaut."""

    def test_issue_count_compte_les_regles_distinctes(
        self,
        rules,
    ) -> None:
        texte = (
            "The appropriate filter shall use appropriate "
            "settings in the appropriate mode."
        )

        result = analyse_requirements(build_frame([texte]), rules)
        ligne = result["summary"].iloc[0]

        assert ligne["Issue_Count"] == 1
        assert ligne["Occurrence_Count"] == 3

    def test_score_penalise_une_fois_par_regle(self, rules) -> None:
        phrase = "The system shall use appropriate filters."

        une_fois = analyse_requirements(
            build_frame([phrase]),
            rules,
        )["summary"]

        trois_fois = analyse_requirements(
            build_frame([" ".join([phrase] * 3)]),
            rules,
        )["summary"]

        # Même jeu de règles déclenchées de part et d'autre :
        # la comparaison de score est donc légitime.
        assert (
            une_fois.at[0, "Triggered_Rules"]
            == trois_fois.at[0, "Triggered_Rules"]
        )
        assert trois_fois.at[0, "Occurrence_Count"] == 3 * (
            une_fois.at[0, "Occurrence_Count"]
        )
        assert (
            une_fois.at[0, "Quality_Score"]
            == trois_fois.at[0, "Quality_Score"]
        )

    def test_score_parfait_sans_alerte(self, rules) -> None:
        result = analyse_requirements(
            build_frame([EXIGENCES_CORRECTES[0]]),
            rules,
        )

        assert result["summary"].at[0, "Quality_Score"] == 100

    def test_score_borne_a_zero(self) -> None:
        class FauxConstat:
            def __init__(self, rule_id: str) -> None:
                self.rule_id = rule_id
                self.severity = "CRITICAL"

        constats = [FauxConstat(f"R-{index}") for index in range(20)]

        assert compute_quality_score(constats) == 0


class TestStatutsEtRisque:
    """Statut et risque dépendent de la gravité, de façon réglable."""

    def test_statut_sans_alerte(self, rules) -> None:
        result = analyse_requirements(
            build_frame([EXIGENCES_CORRECTES[1]]),
            rules,
        )

        assert (
            result["summary"].at[0, "Quality_Status"]
            == config.STATUS_PRE_ANALYSIS_OK
        )

    def test_gravite_haute_demande_clarification(self, rules) -> None:
        result = analyse_requirements(
            build_frame(["The system shall respond rapidly."]),
            rules,
        )

        assert (
            result["summary"].at[0, "Quality_Status"]
            == config.STATUS_CLARIFICATION_REQUIRED
        )

    def test_seuil_de_risque_reglable(self, rules) -> None:
        frame = build_frame(["The system shall respond rapidly."])

        permissif = analyse_requirements(
            frame,
            rules,
            EngineSettings(risk_minimum_severity="LOW"),
        )

        strict = analyse_requirements(
            frame,
            rules,
            EngineSettings(
                risk_minimum_severity="CRITICAL",
                risk_minimum_category_count=99,
            ),
        )

        assert permissif["summary"].at[0, "Risk_To_Assess"] == "YES"
        assert strict["summary"].at[0, "Risk_To_Assess"] == "NO"

    def test_brouillon_de_risque_sans_valeur_inventee(
        self,
        rules,
    ) -> None:
        result = analyse_requirements(
            build_frame(["The system shall respond rapidly."]),
            rules,
        )

        brouillon = result["summary"].at[0, "Risk_Draft"]

        assert "HUMAN VALIDATION REQUIRED" in brouillon
        assert "DRAFT" in brouillon

        # Hors la ligne de titre, qui reprend l'identifiant de
        # l'exigence, aucun chiffre ne doit apparaître : le
        # moteur ne suppose ni seuil, ni coût, ni délai.
        corps = "\n".join(
            ligne
            for ligne in brouillon.splitlines()
            if not ligne.startswith("Title:")
        )

        assert not any(caractere.isdigit() for caractere in corps)


class TestPayloadLLM:
    """Déduplication des constats avant l'appel au modèle."""

    def test_une_seule_entree_par_regle(self, rules) -> None:
        texte = (
            "The appropriate filter shall use appropriate "
            "settings in the appropriate mode, appropriately."
        )

        result = analyse_requirements(build_frame([texte]), rules)

        payload = build_llm_findings(
            "T-001",
            result["findings"],
        )

        identifiants = [item["rule_id"] for item in payload]

        # Envoyer deux fois le même rule_id faisait rejeter
        # toute la réponse du modèle.
        assert len(identifiants) == len(set(identifiants))
        assert payload[0]["occurrence_count"] == 4
        assert len(payload[0]["evidence"]) >= 2

    def test_nombre_de_preuves_plafonne(self, rules) -> None:
        texte = " ".join(
            [
                "The system shall be appropriate.",
                "It shall remain appropriate.",
                "It shall stay appropriate.",
                "It shall become appropriate.",
                "It shall look appropriate.",
                "It shall seem appropriate.",
            ]
        )

        result = analyse_requirements(build_frame([texte]), rules)

        payload = build_llm_findings(
            "T-001",
            result["findings"],
            max_evidence_per_rule=2,
        )

        assert len(payload[0]["evidence"]) <= 2

    def test_exigence_sans_constat(self, rules) -> None:
        result = analyse_requirements(
            build_frame([EXIGENCES_CORRECTES[0]]),
            rules,
        )

        assert build_llm_findings("T-001", result["findings"]) == []


class TestEntreesInvalides:
    """Messages d'erreur utiles plutôt que traces techniques."""

    def test_tableau_non_normalise(self, rules) -> None:
        frame = pd.DataFrame({"foo": ["bar"]})

        with pytest.raises(ValueError, match="load_requirements"):
            analyse_requirements(frame, rules)

    def test_catalogue_vide(self) -> None:
        with pytest.raises(ValueError, match="Aucune règle active"):
            analyse_requirements(build_frame(["texte"]), [])

    def test_texte_vide_marque_non_analyse(self, rules) -> None:
        frame = build_frame(["x"])
        frame.loc[0, CANONICAL_TEXT] = ""

        result = analyse_requirements(frame, rules)

        assert (
            result["summary"].at[0, "Quality_Status"]
            == config.STATUS_NOT_ANALYSED
        )
