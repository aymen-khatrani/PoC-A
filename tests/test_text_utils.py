# ============================================================
# Tests des normalisations et heuristiques
# ============================================================

from src import config
from src.text_utils import (
    classify_object_type,
    clean_value,
    collapse_whitespace,
    english_stopword_ratio,
    has_obligation_keyword,
    looks_like_heading,
    match_alias,
    normalize_key,
)


class TestNormalisation:
    """Nettoyage des valeurs issues d'Excel."""

    def test_espace_insecable_et_retour_chariot(self) -> None:
        assert clean_value(" texte\r\n") == "texte"

    def test_valeur_absente(self) -> None:
        assert clean_value(None) == ""

    def test_espaces_multiples(self) -> None:
        assert collapse_whitespace(" a \n  b ") == "a b"

    def test_cle_normalisee_ignore_ponctuation_et_accents(
        self,
    ) -> None:
        assert normalize_key(" Réf. Exigence ") == "ref exigence"


class TestDetectionColonnes:
    """Reconnaissance des rôles de colonnes."""

    def test_format_doors(self) -> None:
        colonnes = ["ID", "Object Heading and Object Text", "ObjectType"]

        assert (
            match_alias(colonnes, config.TEXT_COLUMN_ALIASES)
            == "Object Heading and Object Text"
        )

    def test_noms_client_differents(self) -> None:
        colonnes = ["Req. ID", "Requirement Description", "Category"]

        assert (
            match_alias(colonnes, config.ID_COLUMN_ALIASES)
            == "Req. ID"
        )
        assert (
            match_alias(colonnes, config.TEXT_COLUMN_ALIASES)
            == "Requirement Description"
        )

    def test_colonnes_francaises(self) -> None:
        colonnes = ["Identifiant", "Libellé exigence", "Type exigence"]

        assert (
            match_alias(colonnes, config.TEXT_COLUMN_ALIASES)
            == "Libellé exigence"
        )

    def test_aucune_correspondance(self) -> None:
        assert match_alias(["foo", "bar"], config.TEXT_COLUMN_ALIASES) is None


class TestClassificationType:
    """Un type inconnu doit rester analysable."""

    def test_type_exigence_reconnu(self) -> None:
        assert classify_object_type("Technical Req") == "REQUIREMENT"
        assert classify_object_type("SYS-REQ") == "REQUIREMENT"
        assert (
            classify_object_type("Exigence fonctionnelle")
            == "REQUIREMENT"
        )

    def test_structure_documentaire(self) -> None:
        for valeur in ("Heading", "Information", "Figure", "Annexe"):
            assert classify_object_type(valeur) == "NON_REQUIREMENT"

    def test_type_absent_ou_inconnu(self) -> None:
        assert classify_object_type("") == "UNKNOWN"
        assert classify_object_type("Niveau 3") == "UNKNOWN"


class TestHeuristiqueIntitule:
    """Un texte portant une obligation n'est jamais un intitulé."""

    def test_numerotation_de_chapitre(self) -> None:
        assert looks_like_heading("3.2.1 Scope") is True

    def test_titre_en_majuscules(self) -> None:
        assert looks_like_heading("SAFETY REQUIREMENTS") is True

    def test_obligation_protege_le_texte(self) -> None:
        assert looks_like_heading("The system shall stop.") is False
        assert looks_like_heading("1. The door shall close.") is False

    def test_texte_long_sans_obligation_reste_analysable(self) -> None:
        texte = (
            "The supplier provides documentation and support "
            "for the complete system during operation."
        )

        assert looks_like_heading(texte) is False

    def test_mot_cle_obligation(self) -> None:
        assert has_obligation_keyword("it must be closed") is True
        assert has_obligation_keyword("a nice shallow curve") is False


class TestLangue:
    """Détection grossière de l'anglais."""

    def test_anglais(self) -> None:
        ratio = english_stopword_ratio(
            ["The system shall be available for all the users."]
        )

        assert ratio > config.MINIMUM_ENGLISH_STOPWORD_RATIO

    def test_francais(self) -> None:
        ratio = english_stopword_ratio(
            ["Le système doit démarrer rapidement."]
        )

        assert ratio < config.MINIMUM_ENGLISH_STOPWORD_RATIO

    def test_texte_vide(self) -> None:
        assert english_stopword_ratio([]) == 0.0
