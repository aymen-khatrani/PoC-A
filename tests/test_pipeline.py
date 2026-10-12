# ============================================================
# Tests de bout en bout
# ============================================================
#
# Ces tests exécutent le pipeline réel sur les classeurs de
# test, sans LLM, et vérifient le contenu du rapport produit.
#
# ============================================================

import pandas as pd
import pytest

from evaluate import compute_metrics, parse_expected_value
from run_analysis import build_argument_parser, run_pipeline

FORMATS = [
    "format_doors.xlsx",
    "format_colonnes_renommees.xlsx",
    "format_intitule_separe.xlsx",
    "format_csv.csv",
]

FEUILLES_ATTENDUES = {
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
