# ============================================================
# Configuration centrale du contrôleur qualité
# ============================================================
#
# Ce module regroupe tous les réglages qui dépendaient
# auparavant d'un export DOORS particulier. Aucun nom de
# colonne, aucun type d'objet et aucun identifiant client
# n'est codé en dur ailleurs dans le projet.
#
# ============================================================

from __future__ import annotations

from dataclasses import dataclass, field


# ============================================================
# Noms de colonnes canoniques utilisés en interne
# ============================================================

# Le projet travaille toujours avec ces trois noms internes,
# quelle que soit la façon dont le client a nommé ses colonnes.

CANONICAL_ID = "Requirement_ID"
CANONICAL_TEXT = "Requirement_Text"
CANONICAL_TYPE = "Requirement_Type"

CANONICAL_HEADING = "Requirement_Heading"
SOURCE_ROW = "Source_Excel_Row"
SOURCE_SHEET = "Source_Sheet"


# ============================================================
# Détection des colonnes d'entrée
# ============================================================
#
# Chaque rôle est décrit par une liste d'alias. La détection
# est insensible à la casse, aux accents, à la ponctuation et
# aux espaces multiples. Les alias sont classés du plus
# spécifique au plus générique : le premier trouvé gagne.
#
# Pour ajouter un format client, il suffit d'ajouter un alias
# dans la liste correspondante.

ID_COLUMN_ALIASES = [
    "requirement id",
    "req id",
    "object id",
    "object identifier",
    "doors id",
    "absolute number",
    "article id",
    "clause id",
    "exigence id",
    "identifiant exigence",
    "identifiant",
    "identifier",
    "reference",
    "ref",
    "key",
    "id",
    "no",
    "num",
    "numero",
]

TEXT_COLUMN_ALIASES = [
    "object heading and object text",
    "requirement text",
    "requirement statement",
    "requirement description",
    "requirement",
    "object text",
    "specification text",
    "statement",
    "description",
    "libelle exigence",
    "texte exigence",
    "exigence",
    "libelle",
    "wording",
    "content",
    "text",
    "texte",
    "body",
]

HEADING_COLUMN_ALIASES = [
    "object heading",
    "requirement heading",
    "heading",
    "title",
    "titre",
    "name",
    "subject",
    "objet",
]

TYPE_COLUMN_ALIASES = [
    "objecttype",
    "object type",
    "requirement type",
    "req type",
    "requirement category",
    "requirement kind",
    "type exigence",
    "nature exigence",
    "classification",
    "category",
    "categorie",
    "nature",
    "kind",
    "type",
]


# ============================================================
# Classification des types d'objet
# ============================================================
#
# Le PoC initial n'acceptait que "Technical Req" et
# "Non-Technical Req" et jetait tout le reste. Un autre client
# écrira "Functional requirement", "SYS-REQ", "Exigence
# fonctionnelle" ou ne fournira aucune colonne de type.
#
# La logique est donc inversée : tout objet est analysable,
# SAUF si son type ressemble à un élément de structure
# documentaire. Cette liste décrit ce qui n'est pas une
# exigence.

NON_REQUIREMENT_TYPE_KEYWORDS = [
    "heading",
    "header",
    "title",
    "titre",
    "chapter",
    "chapitre",
    "section",
    "paragraph",
    "subtitle",
    "information",
    "info",
    "note",
    "remark",
    "remarque",
    "comment",
    "commentaire",
    "figure",
    "image",
    "picture",
    "photo",
    "table",
    "tableau",
    "caption",
    "legend",
    "legende",
    "toc",
    "table of contents",
    "sommaire",
    "glossary",
    "glossaire",
    "definition",
    "abbreviation",
    "acronym",
    "scope",
    "introduction",
    "preamble",
    "preambule",
    "reference document",
    "appendix",
    "annexe",
    "cover",
    "page de garde",
    "deleted",
    "obsolete",
    "void",
    "spare",
]

# Mots indiquant au contraire une exigence, utilisés pour
# lever un doute lorsqu'un type contient les deux signaux
# (exemple : "Requirement heading" doit rester une exigence
# si le texte porte une obligation).

REQUIREMENT_TYPE_KEYWORDS = [
    "requirement",
    "req",
    "exigence",
    "shall",
    "spec",
    "constraint",
    "contrainte",
    "need",
    "besoin",
]


# ============================================================
# Heuristique de détection des titres sans colonne de type
# ============================================================

# Un texte plus court que ce seuil et sans verbe d'obligation
# est considéré comme un intitulé plutôt qu'une exigence.
HEADING_MAX_WORD_COUNT = 8

# Motif d'une numérotation de chapitre en début de texte,
# par exemple "3.", "4.2.1" ou "A.1".
HEADING_NUMBERING_PATTERN = r"^\s*(?:[A-Z]|\d+)(?:\.\d+)*\.?\s"

# Verbes et formulations qui signalent une obligation.
OBLIGATION_KEYWORDS = [
    "shall",
    "must",
    "will",
    "should",
    "may",
    "is required to",
    "are required to",
    "has to",
    "have to",
    "doit",
    "devra",
    "doivent",
]


# ============================================================
# Détection de la ligne d'en-tête
# ============================================================

# Nombre de lignes scannées en haut de feuille pour trouver
# l'en-tête réel. Beaucoup d'exports placent un titre, un
# logo ou des métadonnées au-dessus du tableau.
HEADER_SEARCH_DEPTH = 20

# Nombre de lignes lues pour estimer le contenu des colonnes
# lors du choix de la feuille.
SHEET_PROBE_ROW_COUNT = 60


# ============================================================
# Contrôle de langue du catalogue
# ============================================================
#
# Le catalogue de règles est en anglais. Analyser un export
# rédigé dans une autre langue ne produirait aucune alerte
# pertinente : il faut le signaler sans bloquer l'exécution.

ENGLISH_STOPWORDS = {
    "the", "shall", "and", "of", "to", "be", "a", "in", "for",
    "is", "that", "with", "as", "on", "by", "or", "this", "it",
    "all", "any", "from", "at", "which", "are", "not", "if",
    "must", "should", "when", "where", "each", "its", "their",
    "has", "have", "been", "will", "may", "than", "then", "such",
}

# Mots fonctionnels d'autres langues européennes probables dans
# un contexte industriel. Ils servent à distinguer deux cas très
# différents, que la version précédente confondait :
#
#   - un texte rédigé dans une autre langue, pour lequel le
#     catalogue anglais est inopérant ;
#   - un texte anglais télégraphique ou tabulaire, qui contient
#     peu de mots fonctionnels quelle que soit la langue.
#
# Le premier cas justifie un avertissement de langue, le second
# non.
OTHER_LANGUAGE_STOPWORDS = {
    # français
    "le", "la", "les", "des", "du", "une", "doit", "doivent",
    "dans", "pour", "est", "sont", "avec", "sur", "par", "que",
    "qui", "au", "aux", "ce", "cette", "etre", "ou",
    # allemand
    "der", "die", "das", "und", "muss", "mussen", "soll",
    "sollen", "mit", "fur", "von", "den", "dem", "ist", "sind",
    "werden", "nicht", "eine", "einen",
    # espagnol et italien
    "el", "los", "las", "una", "debe", "deben", "con", "para",
    "por", "del", "que", "il", "lo", "gli", "deve", "devono",
    "della", "delle", "nel", "sono",
}

# Sous ce ratio de mots fonctionnels anglais, la langue est
# considérée comme douteuse et les deux cas ci-dessus sont
# départagés.
MINIMUM_ENGLISH_STOPWORD_RATIO = 0.04

# Au-dessus de ce ratio de mots fonctionnels d'une autre langue,
# le texte est signalé comme non anglais.
OTHER_LANGUAGE_STOPWORD_RATIO = 0.04

# En dessous de ce nombre de mots, aucun verdict de langue n'est
# émis : l'échantillon est trop court pour conclure.
MINIMUM_WORDS_FOR_LANGUAGE_GUESS = 40


# ============================================================
# Gravités et statuts
# ============================================================

SEVERITY_RANK = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}

ALLOWED_SEVERITIES = set(SEVERITY_RANK)

# Poids utilisés pour le score qualité de 0 à 100.
SEVERITY_WEIGHT = {
    "LOW": 2,
    "MEDIUM": 5,
    "HIGH": 12,
    "CRITICAL": 25,
}

STATUS_PRE_ANALYSIS_OK = "PRE_ANALYSIS_OK"
STATUS_REVIEW_RECOMMENDED = "REVIEW_RECOMMENDED"
STATUS_REVIEW_REQUIRED = "REVIEW_REQUIRED"
STATUS_CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
STATUS_NOT_ANALYSED = "NOT_ANALYSED"

# Gravité maximale qui déclenche chaque statut.
SEVERITY_TO_STATUS = {
    "CRITICAL": STATUS_CLARIFICATION_REQUIRED,
    "HIGH": STATUS_CLARIFICATION_REQUIRED,
    "MEDIUM": STATUS_REVIEW_REQUIRED,
    "LOW": STATUS_REVIEW_RECOMMENDED,
}

# Catégories pour lesquelles un risque projet peut être
# pertinent, car elles touchent la vérifiabilité ou
# l'acceptation.
RISK_RELEVANT_CATEGORIES = {
    "NOT_VERIFIABLE",
    "INCOMPLETE",
    "UNDEFINED_CONDITION",
    "UNDEFINED_REFERENCE",
    "MISSING_UNIT_OR_LIMIT",
    "MISSING_TOLERANCE",
    "MISSING_VERIFICATION_CRITERIA",
}

# Un brouillon de risque est proposé si la gravité maximale
# atteint ce niveau, ou si plusieurs catégories sensibles sont
# touchées en même temps. Le PoC initial en proposait un pour
# presque chaque alerte, ce qui noyait l'information.
RISK_MINIMUM_SEVERITY = "HIGH"
RISK_MINIMUM_RISK_CATEGORY_COUNT = 2


# ============================================================
# Réglages d'exécution
# ============================================================

@dataclass(frozen=True)
class LoaderSettings:
    """Réglages de lecture d'un classeur client."""

    sheet_name: str | None = None
    id_column: str | None = None
    text_column: str | None = None
    type_column: str | None = None
    heading_column: str | None = None
    header_row: int | None = None
    combine_heading_and_text: bool = True
    include_types: tuple[str, ...] = ()
    exclude_types: tuple[str, ...] = ()
    detect_headings_without_type: bool = True
    minimum_text_length: int = 3


@dataclass(frozen=True)
class EngineSettings:
    """Réglages du moteur de règles."""

    severity_to_status: dict[str, str] = field(
        default_factory=lambda: dict(SEVERITY_TO_STATUS)
    )
    risk_minimum_severity: str = RISK_MINIMUM_SEVERITY
    risk_minimum_category_count: int = (
        RISK_MINIMUM_RISK_CATEGORY_COUNT
    )
    max_evidence_per_rule: int = 5
