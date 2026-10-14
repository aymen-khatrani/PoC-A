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

# Libellé lisible de chaque statut. La page de synthèse est
# lue par des personnes qui n'ont pas le code sous les yeux :
# elle n'affiche jamais une constante technique.
STATUS_LABELS = {
    STATUS_PRE_ANALYSIS_OK: "Prête en pré-analyse",
    STATUS_REVIEW_RECOMMENDED: "Revue conseillée",
    STATUS_REVIEW_REQUIRED: "Revue nécessaire",
    STATUS_CLARIFICATION_REQUIRED: "Clarification client",
    STATUS_NOT_ANALYSED: "Non analysée",
}

# Ordre de lecture du lot : ce qui bloque la livraison d'abord,
# les exigences vides en dernier.
STATUS_PRIORITY = {
    STATUS_CLARIFICATION_REQUIRED: 1,
    STATUS_REVIEW_REQUIRED: 2,
    STATUS_REVIEW_RECOMMENDED: 3,
    STATUS_PRE_ANALYSIS_OK: 4,
    STATUS_NOT_ANALYSED: 5,
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
# Évaluation SMART
# ============================================================
#
# Chaque exigence est évaluée sur les cinq axes SMART, puis sur
# un sixième axe tenu à part : la singularité, c'est-à-dire le
# fait qu'une exigence n'exprime qu'une seule exigence.
#
# Les axes ne sont pas devinés. Chaque règle du catalogue porte
# l'axe qu'elle met en défaut, soit explicitement par la
# colonne smart_dimension, soit par défaut via sa catégorie.
# Ajouter une règle ne demande donc aucune modification de
# code.
#
# ============================================================

SMART_SPECIFIC = "SPECIFIC"
SMART_MEASURABLE = "MEASURABLE"
SMART_ACHIEVABLE = "ACHIEVABLE"
SMART_RELEVANT = "RELEVANT"
SMART_TIME_BOUND = "TIME_BOUND"

# Axe tenu hors du score SMART : il ne qualifie pas la
# rédaction de l'exigence, il dit s'il y en a plusieurs.
SINGULARITY_AXIS = "SINGULARITY"

# L'ordre de cette liste est celui de toutes les sorties.
SMART_DIMENSIONS = [
    SMART_SPECIFIC,
    SMART_MEASURABLE,
    SMART_ACHIEVABLE,
    SMART_RELEVANT,
    SMART_TIME_BOUND,
]

# Axes acceptés dans la colonne smart_dimension du catalogue.
SMART_ALLOWED_AXES = set(SMART_DIMENSIONS) | {SINGULARITY_AXIS}

SMART_DIMENSION_LETTERS = {
    SMART_SPECIFIC: "S",
    SMART_MEASURABLE: "M",
    SMART_ACHIEVABLE: "A",
    SMART_RELEVANT: "R",
    SMART_TIME_BOUND: "T",
}

SMART_DIMENSION_LABELS = {
    SMART_SPECIFIC: "Spécifique",
    SMART_MEASURABLE: "Mesurable",
    SMART_ACHIEVABLE: "Atteignable",
    SMART_RELEVANT: "Pertinente",
    SMART_TIME_BOUND: "Temporellement définie",
    SINGULARITY_AXIS: "Unicité",
}

# Question posée au lecteur pour chaque axe. Elle sert de
# légende : un rapport doit pouvoir être lu sans son auteur.
SMART_DIMENSION_QUESTIONS = {
    SMART_SPECIFIC: (
        "L'exigence désigne-t-elle sans ambiguïté un acteur, "
        "une action et un objet ?"
    ),
    SMART_MEASURABLE: (
        "Le résultat attendu est-il quantifié et vérifiable "
        "par un essai ou un contrôle ?"
    ),
    SMART_ACHIEVABLE: (
        "L'obligation est-elle ferme et techniquement "
        "atteignable ?"
    ),
    SMART_RELEVANT: (
        "L'exigence est-elle complète et rattachable à un "
        "besoin réel ?"
    ),
    SMART_TIME_BOUND: (
        "Le délai, la durée ou la fréquence attendus sont-ils "
        "chiffrés ?"
    ),
    SINGULARITY_AXIS: (
        "L'énoncé ne contient-il qu'une seule exigence ?"
    ),
}

# Nom de la colonne de rapport de chaque axe. La convention
# est définie ici, et nulle part ailleurs : le moteur et les
# rapports lisent la même table.
SMART_DIMENSION_COLUMNS = {
    dimension: f"SMART_{dimension.title()}"
    for dimension in SMART_DIMENSIONS
}


# Nom anglais de chaque axe. Les pages du rapport sont en
# français, mais un brouillon de risque ou une question peut
# être transmis au client : ces textes restent dans la langue
# des exigences.
SMART_DIMENSION_NAMES_EN = {
    SMART_SPECIFIC: "Specific",
    SMART_MEASURABLE: "Measurable",
    SMART_ACHIEVABLE: "Achievable",
    SMART_RELEVANT: "Relevant",
    SMART_TIME_BOUND: "Time-bound",
}


# Action demandée à l'ingénieur quand l'axe est en défaut.
# C'est cette formulation qui apparaît en page de synthèse :
# elle doit être lisible sans connaître le catalogue.
SMART_DIMENSION_ACTIONS = {
    SMART_SPECIFIC: "préciser l'énoncé",
    SMART_MEASURABLE: "quantifier le critère attendu",
    SMART_ACHIEVABLE: "confirmer le caractère obligatoire",
    SMART_RELEVANT: "compléter l'information manquante",
    SMART_TIME_BOUND: "chiffrer le délai ou la fréquence",
}


# Axe par défaut de chaque catégorie de règle. Une règle dont
# la catégorie est absente de cette table, et qui ne déclare
# pas d'axe, est rattachée à SPECIFIC : un défaut de rédaction
# non classé reste un défaut de précision.
CATEGORY_TO_SMART_DIMENSION = {
    "AMBIGUITY": SMART_SPECIFIC,
    "MISSING_ACTOR": SMART_SPECIFIC,
    "UNDEFINED_REFERENCE": SMART_SPECIFIC,
    "UNDEFINED_CONDITION": SMART_SPECIFIC,
    "NOT_VERIFIABLE": SMART_MEASURABLE,
    "UNDEFINED_QUANTITY": SMART_MEASURABLE,
    "MISSING_UNIT_OR_LIMIT": SMART_MEASURABLE,
    "MISSING_TOLERANCE": SMART_MEASURABLE,
    "MISSING_VERIFICATION_CRITERIA": SMART_MEASURABLE,
    "WEAK_OBLIGATION": SMART_ACHIEVABLE,
    "INCOMPLETE": SMART_RELEVANT,
    "POTENTIALLY_NON_ATOMIC": SINGULARITY_AXIS,
}

SMART_DEFAULT_DIMENSION = SMART_SPECIFIC


# ============================================================
# Verdicts d'un axe
# ============================================================

SMART_VERDICT_OK = "OK"
SMART_VERDICT_TO_CHECK = "TO_CHECK"
SMART_VERDICT_NOT_MET = "NOT_MET"
SMART_VERDICT_NOT_ASSESSED = "NOT_ASSESSED"

# Verdict déduit de la gravité maximale constatée sur l'axe.
SEVERITY_TO_SMART_VERDICT = {
    "CRITICAL": SMART_VERDICT_NOT_MET,
    "HIGH": SMART_VERDICT_NOT_MET,
    "MEDIUM": SMART_VERDICT_TO_CHECK,
    "LOW": SMART_VERDICT_TO_CHECK,
}

# Points conservés par axe, sur les 20 points que vaut chaque
# axe dans le score SMART de 0 à 100.
SMART_VERDICT_POINTS = {
    SMART_VERDICT_OK: 20,
    SMART_VERDICT_TO_CHECK: 10,
    SMART_VERDICT_NOT_MET: 0,
    SMART_VERDICT_NOT_ASSESSED: 0,
}

# Score obtenu par une exigence conforme sur les cinq axes.
SMART_MAXIMUM_SCORE = (
    len(SMART_DIMENSIONS) * SMART_VERDICT_POINTS[SMART_VERDICT_OK]
)

# Symbole court utilisé sur la page de synthèse.
SMART_VERDICT_SYMBOLS = {
    SMART_VERDICT_OK: "OK",
    SMART_VERDICT_TO_CHECK: "?",
    SMART_VERDICT_NOT_MET: "KO",
    SMART_VERDICT_NOT_ASSESSED: "-",
}

SMART_VERDICT_LABELS = {
    SMART_VERDICT_OK: "Conforme",
    SMART_VERDICT_TO_CHECK: "À vérifier",
    SMART_VERDICT_NOT_MET: "Non conforme",
    SMART_VERDICT_NOT_ASSESSED: "Non évalué",
}


# ============================================================
# Singularité d'une exigence
# ============================================================
#
# Une exigence doit exprimer une obligation et une seule. Deux
# obligations dans un même énoncé rendent la vérification
# partielle impossible à tracer : l'une peut être satisfaite et
# l'autre non, sans que le statut de l'exigence puisse le dire.
#
# La détection est structurelle et volontairement prudente.
# Elle ne réécrit jamais l'exigence : elle compte, elle prouve,
# et elle laisse l'ingénieur décider du découpage.

SINGULARITY_UNIQUE = "UNIQUE"
SINGULARITY_TO_CHECK = "TO_CHECK"
SINGULARITY_TO_SPLIT = "TO_SPLIT"
SINGULARITY_NOT_ASSESSED = "NOT_ASSESSED"

SINGULARITY_LABELS = {
    SINGULARITY_UNIQUE: "Exigence unique",
    SINGULARITY_TO_CHECK: "À vérifier",
    SINGULARITY_TO_SPLIT: "À scinder",
    SINGULARITY_NOT_ASSESSED: "Non évalué",
}

# Verbes d'obligation comptés pour estimer le nombre
# d'exigences contenues dans un énoncé. La liste est plus
# courte que OBLIGATION_KEYWORDS : les modaux faibles comme
# may ou should ne créent pas une exigence supplémentaire, ils
# relèvent de l'axe ACHIEVABLE.
SINGULARITY_OBLIGATION_KEYWORDS = [
    "shall",
    "must",
    "is required to",
    "are required to",
    "has to",
    "have to",
    "doit",
    "doivent",
    "devra",
    "devront",
]

# Au-delà de ce nombre de verbes d'obligation, l'énoncé porte
# plus d'une exigence.
SINGULARITY_MAXIMUM_OBLIGATIONS = 1

# Marqueurs d'énumération : puce, tiret ou numérotation en
# début de ligne. Leur présence révèle une liste d'exigences
# rassemblées dans une seule ligne du tableau.
SINGULARITY_LIST_MARKER_PATTERN = (
    r"(?:^|\n)[ \t]*"
    r"(?:[-•–—*·]|\(?[a-z0-9]{1,3}[.)])"
    r"[ \t]+\S"
)

# Nombre de marqueurs à partir duquel la liste est considérée
# comme une énumération d'exigences.
SINGULARITY_MINIMUM_LIST_MARKERS = 2

# Connecteurs additifs : ils ajoutent une obligation sans
# ouvrir une nouvelle phrase.
SINGULARITY_ADDITIVE_PATTERN = (
    r"\b(?:as well as|in addition|additionally|furthermore|"
    r"moreover|and also|ainsi que|de plus|en outre)\b"
)

# Un point-virgule sépare souvent deux propositions
# indépendantes. Pris seul il ne prouve rien, d'où le seuil.
SINGULARITY_MINIMUM_SEMICOLONS = 2

# Marqueurs de citation. Une obligation qui suit l'un d'eux
# n'est pas une exigence de plus : c'est le rappel d'une
# obligation définie ailleurs.
#
#     The supplier shall comply with clause 7.2, which states
#     that the equipment must be painted.
#
# Sans ce garde-fou, l'énoncé ci-dessus était compté comme
# deux exigences, puis son statut relevé à tort.
SINGULARITY_CITATION_PATTERN = (
    r"\b(?:which states that|stating that|states that|"
    r"which requires that|requires that|as stated in|"
    r"as defined in|as specified in|as required by|"
    r"in accordance with|according to|per clause|"
    r"conformément à|selon)\b"
)

# Deux verbes d'obligation différents, par exemple « shall »
# puis « must », trahissent plus souvent une citation ou un
# style mêlé que deux exigences rédigées ensemble. Le verdict
# reste alors « à vérifier » plutôt que « à scinder ».
SINGULARITY_REQUIRE_SAME_MODAL = True


# ============================================================
# Doublons de texte dans le lot
# ============================================================
#
# Le chargeur signale déjà les identifiants dupliqués. Reste
# le cas inverse, plus coûteux en revue : deux identifiants
# différents qui portent la même exigence. Les deux seront
# vérifiés, tracés et facturés deux fois.
#
# La détection est exacte après normalisation, puis
# approchée par signature de mots. Aucune comparaison deux à
# deux : le lot entier reste traité en une passe.

DUPLICATE_NONE = ""
DUPLICATE_IDENTICAL = "IDENTICAL"
DUPLICATE_SIMILAR = "SIMILAR"

DUPLICATE_LABELS = {
    DUPLICATE_NONE: "",
    DUPLICATE_IDENTICAL: "Texte identique",
    DUPLICATE_SIMILAR: "Texte très proche",
}

# En dessous de ce nombre de mots significatifs, la signature
# de mots n'est pas discriminante : deux exigences courtes
# peuvent légitimement partager leur vocabulaire.
DUPLICATE_MINIMUM_SIGNATURE_WORDS = 6


# ============================================================
# Avis du modèle
# ============================================================

LLM_DECISION_LABELS = {
    "CONFIRMED": "Défaut confirmé",
    "PARTIALLY_CONFIRMED": "Partiellement confirmé",
    "FALSE_POSITIVE": "Fausse alerte",
    "NEEDS_EXPERT_REVIEW": "Avis d'expert requis",
    "ERROR": "Erreur du modèle",
    "NOT_RUN": "Non consulté",
}

# Ce que devient l'action recommandée selon l'avis du modèle.
# Une fausse alerte ne doit pas laisser une consigne de
# correction en tête de page, et un avis manquant ne doit
# jamais être lu comme un avis favorable.
LLM_DECISION_ACTION_OVERRIDE = {
    "FALSE_POSITIVE": (
        "Le modèle juge les constats non fondés : confirmer en "
        "revue, puis clore sans correction."
    ),
}

LLM_DECISION_ACTION_PREFIX = {
    "PARTIALLY_CONFIRMED": "Constats partiellement confirmés",
    "NEEDS_EXPERT_REVIEW": "Avis d'expert requis",
    "ERROR": "Modèle en erreur, constats non arbitrés",
}


# ============================================================
# Constats produits par le modèle
# ============================================================
#
# Le modèle ne se contente pas d'arbitrer les constats des
# règles : il peut en ajouter. C'est sa seule façon de couvrir
# ce qu'une expression régulière ne verra jamais, par exemple
# une exigence qui demande de réduire un phénomène sans dire
# de combien ni comment le vérifier.
#
# Un constat ajouté par le modèle obéit aux mêmes exigences de
# preuve qu'un constat de règle : il doit citer un passage
# présent mot pour mot dans l'exigence. Un passage que l'on ne
# retrouve pas dans le texte est écarté et tracé. Le modèle ne
# peut donc pas inventer un défaut sur un texte qu'il aurait
# mal lu.

# Préfixe des identifiants attribués aux constats du modèle.
# Ils ne peuvent entrer en collision avec aucune règle du
# catalogue, dont les identifiants sont validés au chargement.
MODEL_FINDING_PREFIX = "LLM"

# Catégorie portée par un constat du modèle. Elle le distingue
# des catégories du catalogue dans tous les comptages.
MODEL_FINDING_CATEGORY = "MODEL_REVIEW"

# Origine d'un constat, tracée dans le rapport.
FINDING_SOURCE_RULE = "RULE"
FINDING_SOURCE_MODEL = "MODEL"

FINDING_SOURCE_LABELS = {
    FINDING_SOURCE_RULE: "Règle",
    FINDING_SOURCE_MODEL: "Modèle",
}

# Nombre maximal de constats que le modèle peut ajouter sur une
# exigence. Au-delà, il ne décrit plus un défaut : il commente.
MODEL_MAXIMUM_ADDED_FINDINGS = 3

# Gravités que le modèle peut attribuer. CRITICAL lui est
# refusée : une gravité critique engage le projet et doit venir
# d'une règle validée par le métier, pas d'un modèle local.
MODEL_ALLOWED_SEVERITIES = ["LOW", "MEDIUM", "HIGH"]


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
class SingularitySettings:
    """
    Réglages du contrôle de singularité.

    Les seuils sont regroupés ici, et non lus directement dans
    le module, pour qu'un projet puisse les resserrer ou les
    desserrer sans toucher au code.
    """

    maximum_obligations: int = SINGULARITY_MAXIMUM_OBLIGATIONS
    minimum_list_markers: int = SINGULARITY_MINIMUM_LIST_MARKERS
    minimum_semicolons: int = SINGULARITY_MINIMUM_SEMICOLONS
    require_same_modal: bool = SINGULARITY_REQUIRE_SAME_MODAL


@dataclass(frozen=True)
class EngineSettings:
    """Réglages du moteur de règles."""

    severity_to_status: dict[str, str] = field(
        default_factory=lambda: dict(SEVERITY_TO_STATUS)
    )
    singularity: SingularitySettings = field(
        default_factory=SingularitySettings
    )
    detect_duplicate_text: bool = True
    risk_minimum_severity: str = RISK_MINIMUM_SEVERITY
    risk_minimum_category_count: int = (
        RISK_MINIMUM_RISK_CATEGORY_COUNT
    )
    max_evidence_per_rule: int = 5
