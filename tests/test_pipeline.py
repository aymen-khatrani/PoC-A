# ============================================================
# Tests de bout en bout
# ============================================================
#
# Ces tests exécutent le pipeline réel sur les classeurs de
# test, sans LLM, et vérifient le contenu du rapport produit.
#
# ============================================================

from pathlib import Path

import pandas as pd
import pytest

from evaluate import compute_metrics, parse_expected_value
from run_analysis import build_argument_parser, run_pipeline
from src import config
from src.reporting import (
    OVERVIEW_SHEET_NAME,
    QUESTIONS_SHEET_NAME,
    REQUIREMENTS_SHEET_NAME,
    REQUIREMENTS_COLUMNS,
    RISKS_SHEET_NAME,
    SMART_DETAIL_SHEET_NAME,
)

FORMATS = [
    "format_doors.xlsx",
    "format_colonnes_renommees.xlsx",
    "format_intitule_separe.xlsx",
    "format_csv.csv",
]

FEUILLES_ATTENDUES = {
    OVERVIEW_SHEET_NAME,
    REQUIREMENTS_SHEET_NAME,
    SMART_DETAIL_SHEET_NAME,
    QUESTIONS_SHEET_NAME,
    RISKS_SHEET_NAME,
    "Analysis_Results",
    "Rule_Findings",
    "Excluded_Rows",
    "Diagnostics",
    "Run_Information",
    "Rules_Used",
}


def lancer(fichier, sortie, options=None):
    """Exécute le pipeline avec les arguments de la ligne de commande."""

    arguments = build_argument_parser().parse_args(
        [
            "--input",
            str(fichier),
            "--output",
            str(sortie),
            "--sample",
            "0",
            *(options or []),
        ]
    )

    return run_pipeline(arguments)


class TestPipelineComplet:
    """Le pipeline doit produire le même résultat pour tous les formats."""

    @pytest.mark.parametrize("nom_fichier", FORMATS)
    def test_resultat_identique_quel_que_soit_le_format(
        self,
        fixture_directory,
        tmp_path,
        nom_fichier,
    ) -> None:
        result = lancer(
            fixture_directory / nom_fichier,
            tmp_path / "rapport.xlsx",
        )

        diagnostics = result["analysis"]["diagnostics"]

        assert diagnostics["analysed_requirement_count"] == 8
        assert diagnostics["requirements_with_issues"] == 4

    def test_feuilles_du_rapport(
        self,
        fixture_directory,
        tmp_path,
    ) -> None:
        sortie = tmp_path / "rapport.xlsx"

        lancer(fixture_directory / "format_doors.xlsx", sortie)

        assert sortie.exists()

        feuilles = set(pd.ExcelFile(sortie).sheet_names)

        assert FEUILLES_ATTENDUES.issubset(feuilles)

    def test_le_rapport_est_relisible(
        self,
        fixture_directory,
        tmp_path,
    ) -> None:
        sortie = tmp_path / "rapport.xlsx"

        lancer(fixture_directory / "format_doors.xlsx", sortie)

        resultats = pd.read_excel(
            sortie,
            sheet_name="Analysis_Results",
        )

        assert len(resultats) == 8
        assert "Quality_Score" in resultats.columns
        assert resultats["Quality_Score"].between(0, 100).all()

    def test_lignes_ecartees_tracees_dans_le_rapport(
        self,
        fixture_directory,
        tmp_path,
    ) -> None:
        sortie = tmp_path / "rapport.xlsx"

        lancer(fixture_directory / "format_doors.xlsx", sortie)

        ecartees = pd.read_excel(sortie, sheet_name="Excluded_Rows")

        # Aucune ligne ne doit disparaître sans explication.
        assert len(ecartees) == 2
        assert ecartees["Import_Reason"].notna().all()

    def test_colonnes_forcees_en_ligne_de_commande(
        self,
        fixture_directory,
        tmp_path,
    ) -> None:
        result = lancer(
            fixture_directory / "format_intitule_separe.xlsx",
            tmp_path / "rapport.xlsx",
            ["--text-column", "Object Text", "--no-combine-heading"],
        )

        assert (
            result["import"]["column_mapping"]["text"]
            == "Object Text"
        )

    def test_filtre_de_type(
        self,
        fixture_directory,
        tmp_path,
    ) -> None:
        result = lancer(
            fixture_directory / "format_doors.xlsx",
            tmp_path / "rapport.xlsx",
            ["--include-types", "Technical Req"],
        )

        types = set(
            result["summary"]["Requirement_Type"].unique()
        )

        assert types == {"Technical Req"}

    def test_fichier_sans_exigence_message_clair(
        self,
        tmp_path,
    ) -> None:
        chemin = tmp_path / "entete_seule.xlsx"

        pd.DataFrame(
            {
                "ID": [],
                "Requirement Text": [],
                "ObjectType": [],
            }
        ).to_excel(chemin, index=False)

        with pytest.raises(ValueError):
            lancer(chemin, tmp_path / "rapport.xlsx")

    def test_le_llm_est_optionnel(
        self,
        fixture_directory,
        tmp_path,
    ) -> None:
        sortie = tmp_path / "rapport.xlsx"

        lancer(fixture_directory / "format_doors.xlsx", sortie)

        resultats = pd.read_excel(
            sortie,
            sheet_name="Analysis_Results",
        )

        # Sans --llm, aucune colonne LLM n'est ajoutée et le
        # paquet ollama n'est pas requis.
        assert not any(
            colonne.startswith("LLM_")
            for colonne in resultats.columns
        )


@pytest.fixture(scope="module")
def rapport(fixture_directory, tmp_path_factory) -> Path:
    """Rapport produit une seule fois pour les tests de pages."""

    sortie = tmp_path_factory.mktemp("pages") / "rapport.xlsx"

    lancer(fixture_directory / "format_doors.xlsx", sortie)

    return sortie


class TestPagesDeTete:
    """Les trois premières feuilles doivent être lisibles seules."""

    def test_la_synthese_est_la_premiere_feuille(
        self,
        rapport,
    ) -> None:
        assert (
            pd.ExcelFile(rapport).sheet_names[0]
            == OVERVIEW_SHEET_NAME
        )

    def test_la_synthese_tient_en_deux_colonnes(
        self,
        rapport,
    ) -> None:
        synthese = pd.read_excel(
            rapport,
            sheet_name=OVERVIEW_SHEET_NAME,
            header=None,
        )

        assert synthese.shape[1] == 2

        # La synthèse donne des chiffres et une légende, jamais
        # un identifiant d'exigence ni une preuve brute.
        contenu = synthese.to_string()

        assert "CUS-201" not in contenu
        assert "Score SMART moyen" in contenu

    def test_la_synthese_ne_montre_aucune_constante_technique(
        self,
        rapport,
    ) -> None:
        contenu = pd.read_excel(
            rapport,
            sheet_name=OVERVIEW_SHEET_NAME,
            header=None,
        ).to_string()

        for statut in config.STATUS_LABELS:
            assert statut not in contenu

    def test_la_page_des_exigences_ne_garde_que_l_essentiel(
        self,
        rapport,
    ) -> None:
        exigences = pd.read_excel(
            rapport,
            sheet_name=REQUIREMENTS_SHEET_NAME,
        )

        assert list(exigences.columns) == REQUIREMENTS_COLUMNS
        assert len(exigences) == 8

        # Les colonnes techniques restent dans Analysis_Results.
        assert "Triggered_Rules" not in exigences.columns
        assert "Risk_Draft" not in exigences.columns

    def test_les_exigences_sont_triees_par_priorite(
        self,
        rapport,
    ) -> None:
        exigences = pd.read_excel(
            rapport,
            sheet_name=REQUIREMENTS_SHEET_NAME,
        )

        premier = exigences.iloc[0]["Verdict"]
        dernier = exigences.iloc[-1]["Verdict"]

        assert premier == config.STATUS_LABELS[
            config.STATUS_CLARIFICATION_REQUIRED
        ]
        assert dernier == config.STATUS_LABELS[
            config.STATUS_PRE_ANALYSIS_OK
        ]

    def test_le_detail_ne_liste_que_les_axes_en_defaut(
        self,
        rapport,
    ) -> None:
        detail = pd.read_excel(
            rapport,
            sheet_name=SMART_DETAIL_SHEET_NAME,
        )

        assert not detail.empty

        conforme = config.SMART_VERDICT_LABELS[
            config.SMART_VERDICT_OK
        ]

        assert conforme not in detail["Verdict"].tolist()

        # Chaque ligne doit porter une question exploitable.
        assert detail["Question à poser"].astype(str).str.len().gt(
            0
        ).all()


class TestSingulariteEtDoublons:
    """Le fichier dédié couvre les cas que les autres n'ont pas."""

    @staticmethod
    def analyser(fixture_directory, tmp_path):
        sortie = tmp_path / "rapport.xlsx"

        resultat = lancer(
            fixture_directory / "format_singularite.xlsx",
            sortie,
        )

        return resultat, sortie

    def test_enonce_multiple_escalade_le_statut(
        self,
        fixture_directory,
        tmp_path,
    ) -> None:
        resultat, _ = self.analyser(fixture_directory, tmp_path)

        summary = resultat["summary"].set_index("Requirement_ID")

        ligne = summary.loc["SING-001"]

        assert (
            ligne["Singularity_Status"]
            == config.SINGULARITY_TO_SPLIT
        )
        assert ligne["Estimated_Requirement_Count"] == 2
        assert (
            ligne["Quality_Status"]
            == config.STATUS_REVIEW_REQUIRED
        )

    def test_enumeration_comptee(
        self,
        fixture_directory,
        tmp_path,
    ) -> None:
        resultat, _ = self.analyser(fixture_directory, tmp_path)

        summary = resultat["summary"].set_index("Requirement_ID")

        assert (
            summary.loc["SING-002"]["Estimated_Requirement_Count"]
            == 3
        )

    def test_obligation_citee_reste_une_seule_exigence(
        self,
        fixture_directory,
        tmp_path,
    ) -> None:
        resultat, _ = self.analyser(fixture_directory, tmp_path)

        summary = resultat["summary"].set_index("Requirement_ID")

        ligne = summary.loc["SING-003"]

        # « which states that ... must ... » cite une obligation
        # définie ailleurs : l'exigence reste unique, et son
        # statut ne doit pas être relevé.
        assert (
            ligne["Singularity_Status"] == config.SINGULARITY_UNIQUE
        )
        assert (
            ligne["Quality_Status"] == config.STATUS_PRE_ANALYSIS_OK
        )

    def test_doublon_de_texte_signale_des_deux_cotes(
        self,
        fixture_directory,
        tmp_path,
    ) -> None:
        resultat, _ = self.analyser(fixture_directory, tmp_path)

        summary = resultat["summary"].set_index("Requirement_ID")

        for identifiant, autre in (
            ("SING-004", "SING-005"),
            ("SING-005", "SING-004"),
        ):
            ligne = summary.loc[identifiant]

            assert (
                ligne["Duplicate_Status"]
                == config.DUPLICATE_IDENTICAL
            )
            assert ligne["Duplicate_With"] == autre
            assert "Doublon" in ligne["Recommended_Action"]
            assert (
                ligne["Quality_Status"]
                == config.STATUS_REVIEW_REQUIRED
            )

    def test_ligne_sans_texte_ecartee_et_tracee(
        self,
        fixture_directory,
        tmp_path,
    ) -> None:
        resultat, _ = self.analyser(fixture_directory, tmp_path)

        exclues = resultat["import"]["excluded"]

        assert len(exclues) == 1
        assert "MISSING_TEXT" in exclues["Import_Status"].tolist()

    def test_risque_ouvert_pour_un_enonce_a_scinder(
        self,
        fixture_directory,
        tmp_path,
    ) -> None:
        _, sortie = self.analyser(fixture_directory, tmp_path)

        risques = pd.read_excel(sortie, sheet_name=RISKS_SHEET_NAME)

        assert "SING-001" in risques["Exigence"].tolist()

        brouillon = risques.set_index("Exigence").loc[
            "SING-001"
        ]["Brouillon de risque"]

        assert "more than one obligation" in brouillon
        assert "HUMAN VALIDATION REQUIRED" in brouillon

    def test_page_des_questions_montre_le_texte_annote(
        self,
        fixture_directory,
        tmp_path,
    ) -> None:
        _, sortie = self.analyser(fixture_directory, tmp_path)

        questions = pd.read_excel(
            sortie,
            sheet_name=QUESTIONS_SHEET_NAME,
        )

        colonne = "Texte du client (passages en cause encadrés)"

        assert not questions.empty
        assert questions[colonne].astype(str).str.contains(
            "《"
        ).any()


class TestEvaluation:
    """Indicateurs d'évaluation."""

    def test_attendu_sur_colonne(self, fixture_directory) -> None:
        import evaluate

        arguments = evaluate.build_argument_parser().parse_args(
            [
                "--input",
                str(fixture_directory / "format_doors.xlsx"),
                "--expected-column",
                "Expected_Flag",
                "--output",
                str(fixture_directory / ".." / "metriques.xlsx"),
            ]
        )

        result = evaluate.run_evaluation(arguments)
        metrics = result["metrics"][0]

        assert metrics["label"] == "Rule_Engine"
        assert metrics["recall"] == 1.0
        assert metrics["precision"] == 1.0
        assert metrics["precision_is_measurable"] is True

        result["output_path"].unlink(missing_ok=True)

    def test_attendu_sans_cas_negatif_signale(self) -> None:
        metrics = compute_metrics(
            expected=pd.Series([True, True, True]),
            predicted=pd.Series([True, True, False]),
            label="test",
        )

        # Un jeu uniquement positif ne permet pas de mesurer la
        # précision : l'indicateur doit le dire.
        assert metrics["precision_is_measurable"] is False
        assert metrics["recall"] == pytest.approx(2 / 3, abs=1e-4)

    def test_attendu_illisible_exclu_du_calcul(self) -> None:
        metrics = compute_metrics(
            expected=pd.Series([True, None, False]),
            predicted=pd.Series([True, True, False]),
            label="test",
        )

        assert metrics["evaluated_count"] == 2
        assert metrics["precision"] == 1.0

    @pytest.mark.parametrize(
        "valeur, attendu",
        [
            ("YES", True),
            ("oui", True),
            ("1", True),
            ("KO", True),
            ("NO", False),
            ("non", False),
            ("OK", False),
            ("", None),
            ("peut-être", None),
        ],
    )
    def test_lecture_des_valeurs_attendues(
        self,
        valeur,
        attendu,
    ) -> None:
        assert parse_expected_value(valeur) is attendu
