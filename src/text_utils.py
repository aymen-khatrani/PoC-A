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
    Produit une clé de comparaison insensible à la forme.

    Elle sert à reconnaître un nom de colonne quelle que soit
    son écriture, et à comparer deux textes d'exigence sans se
    laisser tromper par la ponctuation ou la casse.

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
# Assemblage de listes lisibles
# ============================================================

def unique_preserve_order(values: list[Any]) -> list[str]:
    """Supprime les doublons en conservant l'ordre d'apparition."""

    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        cleaned = clean_value(value)

        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)

    return result


def join_unique(values: list[Any], separator: str = " | ") -> str:
    """Assemble des valeurs uniques en une chaîne lisible."""

    return separator.join(unique_preserve_order(values))


# ============================================================
# Estimation de la langue
# ============================================================

def count_words(texts: list[str]) -> list[str]:
    """Extrait les mots alphabétiques d'une liste de textes."""

    words: list[str] = []

    for text in texts:
        words.extend(
            re.findall(
                r"[a-zA-Z]+",
                strip_accents(str(text)).lower(),
            )
        )

    return words


def english_stopword_ratio(texts: list[str]) -> float:
    """Proportion de mots fonctionnels anglais dans les textes."""

    words = count_words(texts)

    if not words:
        return 0.0

    return sum(
        1
        for word in words
        if word in config.ENGLISH_STOPWORDS
    ) / len(words)


def other_language_stopword_ratio(texts: list[str]) -> float:
    """
    Proportion de mots fonctionnels d'une autre langue
    européenne courante.
    """

    words = count_words(texts)

    if not words:
        return 0.0

    return sum(
        1
        for word in words
        if word in config.OTHER_LANGUAGE_STOPWORDS
    ) / len(words)


def guess_language_profile(texts: list[str]) -> dict[str, object]:
    """
    Qualifie le style d'écriture du corpus.

    La version précédente concluait « ce n'est pas de l'anglais »
    dès que les mots fonctionnels anglais étaient rares. Or des
    exigences anglaises télégraphiques ou tabulaires, du type
    « Cabinet IP65. Weight 45 kg +/- 2 kg. », n'en contiennent
    aucun : l'avertissement se déclenchait à tort.

    Les deux situations sont donc départagées :

        "english"        anglais rédigé, cas normal ;
        "other_language" mots fonctionnels majoritairement d'une
                         autre langue, le catalogue anglais est
                         inopérant ;
        "telegraphic"    peu de mots fonctionnels, quelle que
                         soit la langue : les règles lexicales
                         trouveront peu de prise, mais rien
                         n'indique une autre langue ;
        "undetermined"   échantillon trop court pour conclure.
    """

    words = count_words(texts)

    english_ratio = english_stopword_ratio(texts)
    other_ratio = other_language_stopword_ratio(texts)

    if len(words) < config.MINIMUM_WORDS_FOR_LANGUAGE_GUESS:
        verdict = "undetermined"
    elif english_ratio >= config.MINIMUM_ENGLISH_STOPWORD_RATIO:
        verdict = "english"
    elif other_ratio >= config.OTHER_LANGUAGE_STOPWORD_RATIO:
        verdict = "other_language"
    else:
        verdict = "telegraphic"

    return {
        "verdict": verdict,
        "word_count": len(words),
        "english_ratio": round(english_ratio, 4),
        "other_language_ratio": round(other_ratio, 4),
    }
