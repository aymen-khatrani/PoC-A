# ============================================================
# Fonctions de normalisation et heuristiques de texte
# ============================================================
#
# Ces fonctions servent uniquement à comprendre un fichier
# client. Elles ne modifient jamais le texte importé : les
# valeurs originales sont toujours conservées à côté.
#
# ============================================================

from __future__ import annotations

import re
import unicodedata
from typing import Any

import pandas as pd

from src import config


# ============================================================
# Normalisation de base
# ============================================================

def clean_value(value: Any) -> str:
    """
    Convertit une valeur de cellule en texte exploitable.

    Les valeurs absentes de pandas, les sauts de ligne Windows
    et les espaces insécables sont traités, car les exports
    Excel en contiennent très souvent.
    """

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    text = str(value)

    # Espaces insécables et tabulations vers espace simple.
    text = text.replace(" ", " ").replace("\t", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    return text.strip()


def collapse_whitespace(value: Any) -> str:
    """Réduit toute suite d'espaces ou de sauts de ligne à un espace."""

    return re.sub(r"\s+", " ", clean_value(value)).strip()


def strip_accents(text: str) -> str:
    """Retire les accents pour permettre une comparaison robuste."""

    decomposed = unicodedata.normalize("NFKD", text)

    return "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )


def normalize_key(value: Any) -> str:
    """
    Produit une clé de comparaison pour un nom de colonne.

    Exemple :
        " Object  Heading & Object_Text " devient
        "object heading object text"

    La ponctuation est supprimée afin que "Req. ID", "Req_ID"
    et "req id" soient reconnus comme le même nom.
    """

    text = strip_accents(collapse_whitespace(value)).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)

    return text.strip()


def is_blank(value: Any) -> bool:
    """Indique si une cellule est vide après nettoyage."""

    return clean_value(value) == ""


# ============================================================
# Détection d'un rôle de colonne
# ============================================================

def match_alias(
    column_names: list[Any],
    aliases: list[str],
) -> Any | None:
    """
    Recherche la colonne correspondant le mieux à une liste
    d'alias.

    La recherche se fait en trois passes, de la plus stricte à
    la plus permissive :

    1. égalité exacte sur la clé normalisée ;
    2. la clé de la colonne contient l'alias comme mot ;
    3. l'alias contient la clé de la colonne.

    Les alias sont testés dans l'ordre fourni, donc du plus
    spécifique au plus générique.
    """

    normalized_columns = [
        (column, normalize_key(column))
        for column in column_names
    ]

    for alias in aliases:
        for column, key in normalized_columns:
            if key == alias:
                return column

    for alias in aliases:
        pattern = re.compile(
            rf"(?:^|\s){re.escape(alias)}(?:\s|$)"
        )

        for column, key in normalized_columns:
            if pattern.search(key):
                return column

    # Troisième passe : un libellé abrégé, par exemple "Req",
    # peut être reconnu dans un alias plus long. Le libellé doit
    # être un mot entier et suffisamment distinctif, sinon une
    # colonne nommée "a" correspondrait à n'importe quoi.
    for alias in aliases:
        for column, key in normalized_columns:
            if len(key) < 3:
                continue

            if re.search(rf"(?:^|\s){re.escape(key)}(?:\s|$)", alias):
                return column

    return None


# ============================================================
# Classification d'un type d'objet
# ============================================================

def classify_object_type(object_type: Any) -> str:
    """
    Détermine si un type d'objet désigne une exigence.

    Retourne :
        "REQUIREMENT"     : à analyser ;
        "NON_REQUIREMENT" : élément de structure documentaire ;
        "UNKNOWN"         : type absent ou non reconnaissable.

    La logique est volontairement permissive : un type inconnu
    est traité comme une exigence potentielle plutôt que jeté,
    car chaque client nomme ses types différemment.
    """

    key = normalize_key(object_type)

    if not key:
        return "UNKNOWN"

    has_requirement_signal = any(
        keyword in key
        for keyword in config.REQUIREMENT_TYPE_KEYWORDS
    )

    has_non_requirement_signal = any(
        keyword in key
        for keyword in config.NON_REQUIREMENT_TYPE_KEYWORDS
    )

    # "Requirement heading" garde le signal exigence : c'est le
    # texte qui tranchera via l'heuristique de titre.
    if has_requirement_signal:
        return "REQUIREMENT"

    if has_non_requirement_signal:
        return "NON_REQUIREMENT"

    return "UNKNOWN"


# ============================================================
# Heuristique de détection d'un intitulé
# ============================================================

def has_obligation_keyword(text: str) -> bool:
    """Indique si le texte contient un verbe d'obligation."""

    lowered = f" {collapse_whitespace(text).lower()} "

    for keyword in config.OBLIGATION_KEYWORDS:
        if re.search(
            rf"(?:^|\W){re.escape(keyword)}(?:\W|$)",
            lowered,
        ):
            return True

    return False


def looks_like_heading(text: Any) -> bool:
    """
    Estime si un texte est un intitulé de chapitre plutôt
    qu'une exigence.

    Cette heuristique n'est utilisée que lorsque le fichier
    client ne fournit pas de colonne de type exploitable. Elle
    n'exclut jamais un texte portant une obligation.
    """

    cleaned = collapse_whitespace(text)

    if not cleaned:
        return False

    if has_obligation_keyword(cleaned):
        return False

    word_count = len(cleaned.split())

    # Un texte long sans obligation reste analysable : il peut
    # s'agir d'une exigence mal rédigée, ce qui est exactement
    # ce que l'outil doit détecter.
    if word_count > config.HEADING_MAX_WORD_COUNT:
        return False

    # Numérotation de chapitre en début de ligne.
    if re.match(config.HEADING_NUMBERING_PATTERN, cleaned):
        return True

    # Intitulé court sans ponctuation finale.
    if not cleaned.endswith((".", ";", ":")):
        return True

    # Intitulé entièrement en majuscules.
    letters = [c for c in cleaned if c.isalpha()]

    if letters and all(c.isupper() for c in letters):
        return True

    return False


# ============================================================
# Estimation de la langue
# ============================================================

def english_stopword_ratio(texts: list[str]) -> float:
    """
    Calcule la proportion de mots anglais très courants.

    Ce test grossier suffit à repérer un export rédigé dans
    une autre langue, cas dans lequel le catalogue anglais ne
    produirait aucune alerte utile.
    """

    total_words = 0
    stopword_count = 0

    for text in texts:
        words = re.findall(
            r"[a-zA-Z]+",
            strip_accents(str(text)).lower(),
        )

        total_words += len(words)

        stopword_count += sum(
            1
            for word in words
            if word in config.ENGLISH_STOPWORDS
        )

    if total_words == 0:
        return 0.0

    return stopword_count / total_words
