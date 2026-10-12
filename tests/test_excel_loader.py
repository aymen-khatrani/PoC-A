# ============================================================
# Tests du chargement générique
# ============================================================
#
# Le même jeu d'exigences est décliné dans plusieurs formats.
# Le chargeur doit produire le même résultat analytique pour
# tous, sans configuration.
#
# ============================================================

import pandas as pd
import pytest

from src.config import (
    CANONICAL_ID,
    CANONICAL_TEXT,
    CANONICAL_TYPE,
    LoaderSettings,
)
from src.excel_loader import load_requirements

FORMATS_EQUIVALENTS = [
    "format_doors.xlsx",
    "format_colonnes_renommees.xlsx",
    "format_intitule_separe.xlsx",
    "format_csv.csv",
]


class TestFormatsEquivalents:
    """Un même contenu, six présentations, un seul résultat."""

    @pytest.mark.parametrize("nom_fichier", FORMATS_EQUIVALENTS)
    def test_meme_nombre_d_exigences(
        self,
        fixture_directory,
        nom_fichier,
    ) -> None:
        result = load_requirements(fixture_directory / nom_fichier)

        assert len(result["requirements"]) == 8
        assert len(result["excluded"]) == 2

    @pytest.mark.parametrize("nom_fichier", FORMATS_EQUIVALENTS)
    def test_colonnes_canoniques_presentes(
        self,
        fixture_directory,
        nom_fichier,
    ) -> None:
        requirements = load_requirements(
            fixture_directory / nom_fichier
        )["requirements"]

        for colonne in (CANONICAL_ID, CANONICAL_TEXT, CANONICAL_TYPE):
            assert colonne in requirements.columns

    @pytest.mark.parametrize("nom_fichier", FORMATS_EQUIVALENTS)
    def test_aucun_texte_vide_parmi_les_exigences(
        self,
        fixture_directory,
        nom_fichier,
    ) -> None:
        requirements = load_requirements(
            fixture_directory / nom_fichier
        )["requirements"]

        assert (requirements[CANONICAL_TEXT].str.len() > 0).all()


class TestEnteteDecalee:
    """Un en-tête précédé de métadonnées doit être trouvé."""

    def test_ligne_d_entete_detectee(self, fixture_directory) -> None:
        result = load_requirements(
            fixture_directory / "format_colonnes_renommees.xlsx"
        )

        # Trois lignes de préambule, en-tête en ligne 4.
        assert result["diagnostics"]["header_excel_row"] == 4

    def test_tracabilite_de_la_ligne_source(
        self,
        fixture_directory,
    ) -> None:
        result = load_requirements(
            fixture_directory / "format_colonnes_renommees.xlsx"
        )

        premiere = result["requirements"].iloc[0]

        # En-tête en ligne 4, intitulé en ligne 5, première
        # exigence en ligne 6.
        assert premiere["Source_Excel_Row"] == 6


class TestFichierSansIdentifiantNiType:
    """Le chargeur doit rester utilisable sans métadonnées."""

    def test_identifiants_generes(self, fixture_directory) -> None:
        result = load_requirements(
            fixture_directory / "format_sans_id_ni_type.xlsx"
        )

        assert result["diagnostics"]["generated_ids"] > 0
        assert (
            result["requirements"][CANONICAL_ID]
            .str.startswith("ROW-")
            .all()
        )

    def test_avertissements_explicites(
        self,
        fixture_directory,
    ) -> None:
        warnings = load_requirements(
            fixture_directory / "format_sans_id_ni_type.xlsx"
        )["diagnostics"]["warnings"]

        texte = " ".join(warnings)

        assert "identifiant" in texte
        assert "type" in texte


class TestDetectionDeLangue:
    """
    Trois situations à ne pas confondre.

    Les exigences réelles de ce projet sont en anglais, souvent
    en style technique. Un avertissement de langue à tort y
    serait du bruit trompeur : la distinction est donc testée
    dans les deux sens.
    """

    def test_anglais_redige_sans_avertissement(
        self,
        fixture_directory,
    ) -> None:
        result = load_requirements(
            fixture_directory / "format_doors.xlsx"
        )

        assert result["diagnostics"]["language_verdict"] == "english"
        assert not any(
            "anglais" in warning or "télégraphique" in warning
            for warning in result["diagnostics"]["warnings"]
        )

    def test_anglais_telegraphique_non_signale_comme_autre_langue(
        self,
        fixture_directory,
    ) -> None:
        result = load_requirements(
            fixture_directory / "format_telegraphique.xlsx"
        )

        diagnostics = result["diagnostics"]

        assert diagnostics["language_verdict"] == "telegraphic"

        avertissements = " ".join(diagnostics["warnings"])

        # Le message doit parler de style d'écriture, jamais
        # affirmer que le texte n'est pas en anglais.
        assert "télégraphique" in avertissements
        assert "ne semble pas rédigé en anglais" not in avertissements

    def test_autre_langue_signalee(self, fixture_directory) -> None:
        result = load_requirements(
            fixture_directory / "format_francais.xlsx"
        )

        diagnostics = result["diagnostics"]

        assert diagnostics["language_verdict"] == "other_language"
        assert len(result["requirements"]) == 5
        assert any(
            "ne semble pas rédigé en anglais" in warning
            for warning in diagnostics["warnings"]
        )

    def test_echantillon_trop_court_aucun_verdict(
        self,
        tmp_path,
    ) -> None:
        chemin = tmp_path / "court.xlsx"

        pd.DataFrame(
            {
                "ID": ["A-1"],
                "Requirement Text": ["Short statement."],
                "ObjectType": ["Technical Req"],
            }
        ).to_excel(chemin, index=False)

        result = load_requirements(chemin)

        # Conclure sur une seule ligne serait arbitraire.
        assert (
            result["diagnostics"]["language_verdict"]
            == "undetermined"
        )


class TestFiltrage:
    """Les filtres de type sont tolérants et explicites."""

    def test_include_types_insensible_a_la_casse(
        self,
        fixture_directory,
    ) -> None:
        result = load_requirements(
            fixture_directory / "format_doors.xlsx",
            LoaderSettings(include_types=("technical req",)),
        )

        assert len(result["requirements"]) > 0
        assert (
            result["requirements"][CANONICAL_TYPE]
            .eq("Technical Req")
            .all()
        )

    def test_exclude_types(self, fixture_directory) -> None:
        result = load_requirements(
            fixture_directory / "format_doors.xlsx",
            LoaderSettings(exclude_types=("Non-Technical Req",)),
        )

        assert (
            "Non-Technical Req"
            not in result["requirements"][CANONICAL_TYPE].values
        )

    def test_chaque_ligne_ecartee_porte_un_motif(
        self,
        fixture_directory,
    ) -> None:
        excluded = load_requirements(
            fixture_directory / "format_doors.xlsx"
        )["excluded"]

        assert not excluded.empty
        assert (excluded["Import_Reason"].str.len() > 0).all()


class TestColonnesForcees:
    """L'utilisateur garde le dernier mot sur la détection."""

    def test_colonne_texte_forcee(self, fixture_directory) -> None:
        result = load_requirements(
            fixture_directory / "format_intitule_separe.xlsx",
            LoaderSettings(text_column="Object Heading"),
        )

        assert (
            result["column_mapping"]["text"] == "Object Heading"
        )

    def test_colonne_inexistante_message_clair(
        self,
        fixture_directory,
    ) -> None:
        with pytest.raises(ValueError, match="Colonnes disponibles"):
            load_requirements(
                fixture_directory / "format_doors.xlsx",
                LoaderSettings(text_column="Colonne Fantome"),
            )


class TestRobustesse:
    """Cas limites qui faisaient échouer la version précédente."""

    def test_identifiants_dupliques_conserves(self, tmp_path) -> None:
        frame = pd.DataFrame(
            {
                "ID": ["A-1", "A-1"],
                "Requirement Text": [
                    "The system shall respond rapidly.",
                    "The device shall be user-friendly.",
                ],
                "ObjectType": ["Technical Req", "Technical Req"],
            }
        )

        path = tmp_path / "doublons.xlsx"
        frame.to_excel(path, index=False)

        result = load_requirements(path)

        # La version précédente supprimait ces lignes en silence.
        assert len(result["requirements"]) == 2
        assert result["diagnostics"]["duplicate_ids"] == 2
        assert any(
            "identifiant" in warning
            for warning in result["diagnostics"]["warnings"]
        )

    def test_colonne_sans_nom_reconnu(self, tmp_path) -> None:
        frame = pd.DataFrame(
            {
                "colonne_a": ["X-1", "X-2"],
                "colonne_b": [
                    "The system shall respond rapidly under all "
                    "operating conditions defined by the customer.",
                    "The supplier shall deliver the documentation "
                    "before the acceptance test takes place.",
                ],
            }
        )

        path = tmp_path / "inconnu.xlsx"
        frame.to_excel(path, index=False)

        result = load_requirements(path)

        # Repli sur la colonne la plus verbeuse, avec
        # avertissement.
        assert result["column_mapping"]["text"] == "colonne_b"
        assert (
            result["diagnostics"]["text_detection_method"]
            == "longest_text_column"
        )

    def test_aucune_colonne_de_texte(self, tmp_path) -> None:
        frame = pd.DataFrame({"a": [1, 2], "b": [3, 4]})

        path = tmp_path / "vide.xlsx"
        frame.to_excel(path, index=False)

        with pytest.raises(ValueError, match="--text-column"):
            load_requirements(path)

    def test_fichier_inexistant(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_requirements("fichier_absent.xlsx")

    def test_extension_refusee(self, tmp_path) -> None:
        path = tmp_path / "document.pdf"
        path.write_text("contenu", encoding="utf-8")

        with pytest.raises(ValueError, match="Extension"):
            load_requirements(path)
