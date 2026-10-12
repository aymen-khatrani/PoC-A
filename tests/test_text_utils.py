# ============================================================
# Tests des normalisations et heuristiques
# ============================================================

from src import config
from src.text_utils import (
    classify_object_type,
    clean_value,
    collapse_whitespace,
    english_stopword_ratio,
    guess_language_profile,
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


class TestProfilDeLangue:
    """
    Distinction entre autre langue et anglais abrégé.

    Un ratio faible de mots fonctionnels anglais ne suffit pas à
    conclure qu'un texte n'est pas en anglais : des exigences
    techniques du type « Cabinet IP65. Weight 45 kg. » n'en
    contiennent aucun.
    """

    def test_anglais_redige(self) -> None:
        textes = [
            "The braking system shall stop the train within "
            "250 m from 80 km/h on dry rails."
        ] * 4

        assert guess_language_profile(textes)["verdict"] == "english"

    def test_anglais_telegraphique(self) -> None:
        textes = [
            "Cabinet IP65. Weight 45 kg +/- 2 kg.",
            "Supply 110 VDC nom., range 77-137 VDC per EN 50155.",
            "MTBF >= 100000 h. MTTR <= 30 min.",
            "Temp -25/+45 C. Vibration EN 61373 Cat 1 Cl B.",
        ] * 3

        assert (
            guess_language_profile(textes)["verdict"]
            == "telegraphic"
        )

    def test_anglais_avec_acronymes(self) -> None:
        textes = [
            "TCMS shall transmit CAN data to the HMI via MVB at "
            "1 Mbit/s as defined in the interface document."
        ] * 4

        assert guess_language_profile(textes)["verdict"] == "english"

    def test_francais(self) -> None:
        textes = [
            "Le système doit démarrer rapidement et rester "
            "convivial pour les opérateurs de maintenance."
        ] * 4

        assert (
            guess_language_profile(textes)["verdict"]
            == "other_language"
        )

    def test_allemand(self) -> None:
        textes = [
            "Das System muss innerhalb von 250 m zum Stehen "
            "kommen und mit der Schnittstelle arbeiten."
        ] * 4

        assert (
            guess_language_profile(textes)["verdict"]
            == "other_language"
        )

    def test_echantillon_trop_court(self) -> None:
        assert (
            guess_language_profile(["Short text."])["verdict"]
            == "undetermined"
        )
