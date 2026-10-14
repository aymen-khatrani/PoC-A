# ============================================================
# Production des rapports Excel
# ============================================================
#
# Un seul module écrit les rapports, pour que le pipeline et le
# script d'évaluation produisent des fichiers cohérents.
#
# La mise en forme s'adapte à n'importe quelles colonnes : rien
# n'est codé en dur, hormis la coloration des statuts connus.
#
# ============================================================

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from src import config
from src.config import (
    CANONICAL_ID,
    CANONICAL_TEXT,
    SOURCE_ROW,
)
from src.smart_evaluator import highest_severity
from src.text_utils import clean_value, join_unique


# Largeur maximale d'une colonne, en caractères.
MAXIMUM_COLUMN_WIDTH = 60
MINIMUM_COLUMN_WIDTH = 12

# Une colonne dont tout le contenu tient en deux caractères,
# comme un verdict d'axe, n'a pas besoin de la largeur
# minimale : elle resterait vide et éloignerait les colonnes
# voisines les unes des autres.
NARROW_CONTENT_LENGTH = 2
NARROW_COLUMN_WIDTH = 6

# Nombre de lignes examinées pour calculer la largeur.
WIDTH_SAMPLE_ROWS = 150

# Excel refuse une cellule de plus de 32 767 caractères.
EXCEL_MAXIMUM_CELL_LENGTH = 32000

STATUS_COLORS = {
    config.STATUS_PRE_ANALYSIS_OK: "C6E0B4",
    config.STATUS_REVIEW_RECOMMENDED: "FFF2CC",
    config.STATUS_REVIEW_REQUIRED: "FCE4D6",
    config.STATUS_CLARIFICATION_REQUIRED: "F4B084",
    config.STATUS_NOT_ANALYSED: "D9D9D9",
}

DECISION_COLORS = {
    "CONFIRMED": "F4B084",
    "PARTIALLY_CONFIRMED": "FCE4D6",
    "FALSE_POSITIVE": "C6E0B4",
    "NEEDS_EXPERT_REVIEW": "FFF2CC",
    "ERROR": "F4CCCC",
    "NOT_RUN": "D9D9D9",
}


# ============================================================
# Pages de tête du rapport
# ============================================================
#
# Le rapport s'ouvre sur deux pages faites pour être lues, et
# non dépouillées :
#
#     1. Synthèse  : le bilan du lot, en une page, sans jargon.
#     2. Exigences : une ligne par exigence, triée par
#                    priorité, avec l'action attendue.
#
# Tout le détail — constats, preuves, positions, diagnostics,
# règles — reste disponible dans les pages suivantes. Rien
# n'est supprimé : l'information est hiérarchisée.
#
# ============================================================

OVERVIEW_SHEET_NAME = "1. Synthese"
REQUIREMENTS_SHEET_NAME = "2. Exigences"
SMART_DETAIL_SHEET_NAME = "3. Detail SMART"
QUESTIONS_SHEET_NAME = "4. Questions client"
RISKS_SHEET_NAME = "5. Risques"

OVERVIEW_COLUMNS = ["Indicateur", "Valeur"]

# Une ligne dont la valeur est vide est un titre de section.
# C'est la seule convention de mise en forme de la synthèse.
OVERVIEW_SECTION_FILL = "1F4E78"

REQUIREMENTS_COLUMNS = [
    "Exigence",
    "Texte de l'exigence",
    "Verdict",
    "Score SMART",
    "S",
    "M",
    "A",
    "R",
    "T",
    "Unicité",
    "Action prioritaire",
    "Ligne source",
]

SMART_DETAIL_COLUMNS = [
    "Exigence",
    "Axe",
    "Verdict",
    "Gravité",
    "Règles déclenchées",
    "Preuves relevées",
    "Question à poser",
    "Reformulation proposée",
]

QUESTIONS_COLUMNS = [
    "Exigence",
    "Texte du client (passages en cause encadrés)",
    "Questions à poser",
    "Patron de reformulation",
    "Reformulation du modèle",
    "Avis du modèle",
    "Décision de l'ingénieur",
    "Question retenue ou reformulée",
    "Validé par",
]

RISKS_COLUMNS = [
    "Exigence",
    "Verdict",
    "Axes en défaut",
    "Unicité",
    "Brouillon de risque",
    "Risque du modèle",
    "Décision de l'ingénieur",
    "Ouvert dans l'outil de risques",
    "Validé par",
]


# Couleurs des verdicts affichés en clair.
STATUS_LABEL_COLORS = {
    config.STATUS_LABELS[status]: color
    for status, color in STATUS_COLORS.items()
    if status in config.STATUS_LABELS
}

SINGULARITY_LABEL_COLORS = {
    config.SINGULARITY_LABELS[config.SINGULARITY_UNIQUE]: "C6E0B4",
    config.SINGULARITY_LABELS[config.SINGULARITY_TO_CHECK]: "FFF2CC",
    config.SINGULARITY_LABELS[config.SINGULARITY_TO_SPLIT]: "F4B084",
    config.SINGULARITY_LABELS[
        config.SINGULARITY_NOT_ASSESSED
    ]: "D9D9D9",
}

DUPLICATE_STATUS_COLORS = {
    config.DUPLICATE_IDENTICAL: "F4B084",
    config.DUPLICATE_SIMILAR: "FFF2CC",
}

SMART_VERDICT_COLORS = {
    config.SMART_VERDICT_OK: "C6E0B4",
    config.SMART_VERDICT_TO_CHECK: "FFF2CC",
    config.SMART_VERDICT_NOT_MET: "F4B084",
    config.SMART_VERDICT_NOT_ASSESSED: "D9D9D9",
}

SINGULARITY_STATUS_COLORS = {
    config.SINGULARITY_UNIQUE: "C6E0B4",
    config.SINGULARITY_TO_CHECK: "FFF2CC",
    config.SINGULARITY_TO_SPLIT: "F4B084",
    config.SINGULARITY_NOT_ASSESSED: "D9D9D9",
}

# Couleur du symbole affiché en page 2, déduite du verdict
# qu'il représente : une seule table de couleurs fait foi.
SMART_SYMBOL_COLORS = {
    config.SMART_VERDICT_SYMBOLS[verdict]: color
    for verdict, color in SMART_VERDICT_COLORS.items()
}

SMART_VERDICT_LABEL_COLORS = {
    config.SMART_VERDICT_LABELS[config.SMART_VERDICT_OK]: "C6E0B4",
    config.SMART_VERDICT_LABELS[
        config.SMART_VERDICT_TO_CHECK
    ]: "FFF2CC",
    config.SMART_VERDICT_LABELS[
        config.SMART_VERDICT_NOT_MET
    ]: "F4B084",
    config.SMART_VERDICT_LABELS[
        config.SMART_VERDICT_NOT_ASSESSED
    ]: "D9D9D9",
}


LLM_DECISION_LABEL_COLORS = {
    config.LLM_DECISION_LABELS[decision]: color
    for decision, color in DECISION_COLORS.items()
    if decision in config.LLM_DECISION_LABELS
}


# La colonne « Verdict » porte un statut d'exigence en page 2,
# et un verdict d'axe ou d'unicité en page 3.
VERDICT_COLORS = {
    **STATUS_LABEL_COLORS,
    **SMART_VERDICT_LABEL_COLORS,
    **SINGULARITY_LABEL_COLORS,
}


# ============================================================
# Outils communs
# ============================================================

def status_label(status: Any) -> str:
    """Traduit un statut technique en libellé lisible."""

    key = clean_value(status)

    return config.STATUS_LABELS.get(key, key)


def singularity_label(status: Any) -> str:
    """Traduit un verdict de singularité en libellé lisible."""

    key = clean_value(status)

    return config.SINGULARITY_LABELS.get(key, key)


def smart_verdict_label(verdict: Any) -> str:
    """Traduit un verdict d'axe en libellé lisible."""

    key = clean_value(verdict)

    return config.SMART_VERDICT_LABELS.get(key, key)


def pluralize(count: int, singular: str, plural: str) -> str:
    """Accorde un libellé avec son effectif."""

    return f"{count} {singular if count <= 1 else plural}"


def display_severity(severities: Any) -> str:
    """
    Retourne la gravité la plus élevée, à afficher.

    L'absence de gravité laisse la cellule vide : « NONE »
    serait lu comme un niveau.
    """

    severity = highest_severity(severities)

    return "" if severity == "NONE" else severity


def llm_decision_label(decision: Any) -> str:
    """Traduit un avis du modèle en libellé lisible."""

    key = clean_value(decision)

    if not key:
        return ""

    return config.LLM_DECISION_LABELS.get(key, key)


def format_share(count: int, total: int) -> str:
    """Formate un effectif et sa part du lot."""

    if not total:
        return str(count)

    return f"{count} ({count / total:.0%})"


def sort_by_priority(summary_frame: pd.DataFrame) -> pd.DataFrame:
    """
    Trie les exigences dans l'ordre de traitement.

    Ce qui bloque la livraison remonte en haut : d'abord le
    statut, puis le score SMART le plus faible. La page
    technique Analysis_Results conserve, elle, l'ordre du
    fichier d'origine.
    """

    if summary_frame.empty:
        return summary_frame

    ordered = summary_frame.copy()

    ordered["_priority"] = (
        ordered["Quality_Status"]
        .map(config.STATUS_PRIORITY)
        .fillna(len(config.STATUS_PRIORITY) + 1)
    )

    ordered = ordered.sort_values(
        ["_priority", "SMART_Score", CANONICAL_ID],
        kind="stable",
    )

    return ordered.drop(columns=["_priority"])


# ============================================================
# Page 1 : la synthèse
# ============================================================

def overview_section(title: str) -> dict[str, Any]:
    """Crée une ligne de titre de section."""

    return {"Indicateur": title, "Valeur": ""}


def overview_row(label: str, value: Any) -> dict[str, Any]:
    """Crée une ligne d'indicateur."""

    return {"Indicateur": label, "Valeur": value}


def build_import_rows(
    import_diagnostics: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Résume ce qui a été lu, et surtout ce qui a été écarté.

    Un relecteur commence par là : un rapport qui annonce huit
    exigences sans dire que le fichier en contenait dix ne
    permet pas de savoir si l'analyse a porté sur le bon
    périmètre. Les anomalies ne sont affichées que lorsqu'elles
    existent, pour ne pas allonger la page inutilement.
    """

    if not import_diagnostics:
        return []

    rows = [
        overview_row(
            "Lignes lues dans la feuille",
            import_diagnostics.get("total_rows", ""),
        ),
        overview_row(
            "Lignes écartées",
            f"{import_diagnostics.get('excluded_rows', 0)} "
            "(motif par ligne dans la page Excluded_Rows)",
        ),
    ]

    anomalies = [
        (
            "Identifiants générés",
            import_diagnostics.get("generated_ids", 0),
            "exigences sans identifiant d'origine",
        ),
        (
            "Identifiants dupliqués",
            import_diagnostics.get("duplicate_ids", 0),
            "lignes partagent un même identifiant",
        ),
    ]

    for label, count, comment in anomalies:
        if count:
            rows.append(overview_row(label, f"{count} {comment}"))

    verdict = clean_value(import_diagnostics.get("language_verdict"))

    if verdict and verdict != "english":
        rows.append(
            overview_row(
                "Langue détectée",
                f"{verdict} — le catalogue est en anglais, les "
                "règles y auront peu de prise",
            )
        )

    for warning in import_diagnostics.get("warnings", []) or []:
        rows.append(overview_row("Avertissement", warning))

    return rows


def build_llm_rows(
    llm_diagnostics: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Résume ce que le modèle a revu, et ce qu'il n'a pas vu.

    Le nombre d'exigences non soumises est affiché autant que
    les verdicts : une absence d'avis ne doit jamais être lue
    comme un avis favorable.
    """

    if not llm_diagnostics or not llm_diagnostics.get("llm_enabled"):
        return []

    rows = [
        overview_section("CE QUE LE MODÈLE A REVU"),
        overview_row(
            "Exigences soumises au modèle",
            llm_diagnostics.get("selected_count", 0),
        ),
    ]

    decisions = llm_diagnostics.get("decision_counts", {}) or {}

    for decision, count in decisions.items():
        rows.append(
            overview_row(
                config.LLM_DECISION_LABELS.get(decision, decision),
                count,
            )
        )

    apports = [
        (
            "Défauts trouvés par le modèle seul",
            llm_diagnostics.get("added_finding_count"),
        ),
        (
            "Fausses alertes écartées par le modèle",
            llm_diagnostics.get("dropped_finding_count"),
        ),
        (
            "Verdicts allégés après revue",
            llm_diagnostics.get("status_improved_count"),
        ),
        (
            "Verdicts aggravés après revue",
            llm_diagnostics.get("status_worsened_count"),
        ),
    ]

    for label, count in apports:
        if count:
            rows.append(overview_row(label, count))

    rows.append(
        overview_row(
            "Exigences non soumises",
            "Leur absence d'avis n'est pas un avis favorable.",
        )
    )

    return rows


def build_overview_frame(
    summary_frame: pd.DataFrame,
    diagnostics: dict[str, Any],
    context_rows: list[tuple[str, Any]] | None = None,
    import_diagnostics: dict[str, Any] | None = None,
    llm_diagnostics: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Construit la page de synthèse.

    La page répond à cinq questions, dans cet ordre : sur quoi
    a-t-on travaillé, ce qui a été écarté, que vaut le lot, où
    le lot pèche, et où aller ensuite. Elle ne contient aucun
    identifiant d'exigence et aucune preuve : c'est le rôle des
    pages suivantes.
    """

    total = int(diagnostics.get("analysed_requirement_count", 0))
    status_counts = diagnostics.get("status_counts", {}) or {}
    not_met_counts = (
        diagnostics.get("smart_axis_not_met_counts", {}) or {}
    )
    to_check_counts = (
        diagnostics.get("smart_axis_to_check_counts", {}) or {}
    )

    rows: list[dict[str, Any]] = [
        overview_section("CE QUI A ÉTÉ ANALYSÉ"),
        overview_row("Exigences analysées", total),
    ]

    for label, value in context_rows or []:
        rows.append(overview_row(label, value))

    import_rows = build_import_rows(import_diagnostics or {})

    if import_rows:
        rows.append(overview_row("", ""))
        rows.append(overview_section("CE QUI A ÉTÉ ÉCARTÉ"))
        rows.extend(import_rows)

    rows.extend(
        [
            overview_row("", ""),
            overview_section("CE QUE VAUT LE LOT"),
            overview_row(
                "Score SMART moyen",
                f"{diagnostics.get('average_smart_score', 0)}"
                f"/{config.SMART_MAXIMUM_SCORE}",
            ),
            overview_row(
                "Exigences conformes sur les cinq axes",
                format_share(
                    int(diagnostics.get("fully_smart_count", 0)),
                    total,
                ),
            ),
            overview_row(
                "Exigences portant au moins un défaut",
                format_share(
                    int(
                        diagnostics.get(
                            "requirements_with_issues",
                            0,
                        )
                    ),
                    total,
                ),
            ),
            overview_row(
                "Exigences à scinder",
                format_share(
                    int(diagnostics.get("requirements_to_split", 0)),
                    total,
                ),
            ),
            overview_row(
                "Exigences au texte répété",
                format_share(
                    int(diagnostics.get("duplicate_text_count", 0)),
                    total,
                ),
            ),
            overview_row(
                "Risques à ouvrir avec le client",
                format_share(
                    int(diagnostics.get("risk_to_assess_count", 0)),
                    total,
                ),
            ),
        ]
    )

    rows.append(overview_row("", ""))
    rows.append(overview_section("CE QUE DEMANDE CHAQUE EXIGENCE"))

    for status, priority in sorted(
        config.STATUS_PRIORITY.items(),
        key=lambda item: item[1],
    ):
        count = int(status_counts.get(status, 0))

        if not count:
            continue

        rows.append(
            overview_row(
                config.STATUS_LABELS.get(status, status),
                format_share(count, total),
            )
        )

    rows.append(overview_row("", ""))
    rows.append(overview_section("OÙ LE LOT PÈCHE : LES CINQ AXES"))

    for dimension in config.SMART_DIMENSIONS:
        label = config.SMART_DIMENSION_LABELS[dimension]
        not_met = int(not_met_counts.get(label, 0))
        to_check = int(to_check_counts.get(label, 0))

        rows.append(
            overview_row(
                f"{config.SMART_DIMENSION_LETTERS[dimension]} - "
                f"{label}",
                ", ".join(
                    [
                        pluralize(
                            not_met,
                            "non conforme",
                            "non conformes",
                        ),
                        f"{to_check} à vérifier",
                        pluralize(
                            max(total - not_met - to_check, 0),
                            "conforme",
                            "conformes",
                        ),
                    ]
                ),
            )
        )

    llm_rows = build_llm_rows(llm_diagnostics or {})

    if llm_rows:
        rows.append(overview_row("", ""))
        rows.extend(llm_rows)

    rows.append(overview_row("", ""))
    rows.append(overview_section("COMMENT LIRE CE RAPPORT"))

    rows.extend(
        [
            overview_row(
                f"Page « {REQUIREMENTS_SHEET_NAME} »",
                "Une ligne par exigence, triée par priorité, "
                "avec l'action attendue.",
            ),
            overview_row(
                f"Page « {SMART_DETAIL_SHEET_NAME} »",
                "Pour chaque exigence, l'axe en défaut, la "
                "preuve et la question à poser.",
            ),
            overview_row(
                f"Page « {QUESTIONS_SHEET_NAME} »",
                "Les questions à envoyer au client, une ligne "
                "par exigence, avec une colonne de validation "
                "à remplir avant envoi.",
            ),
            overview_row(
                f"Page « {RISKS_SHEET_NAME} »",
                "Les brouillons de risque à ouvrir et à "
                "partager, à valider avant toute communication.",
            ),
            overview_row(
                "Pages suivantes",
                "Constats règle par règle, lignes écartées, "
                "diagnostics et catalogue utilisé.",
            ),
            overview_row("", ""),
            overview_section("LA GRILLE D'ÉVALUATION"),
        ]
    )

    # La grille est affichée avec la question posée sur chaque
    # axe : le rapport doit pouvoir être lu sans son auteur.
    for dimension in config.SMART_DIMENSIONS:
        rows.append(
            overview_row(
                f"{config.SMART_DIMENSION_LETTERS[dimension]} - "
                f"{config.SMART_DIMENSION_LABELS[dimension]}",
                config.SMART_DIMENSION_QUESTIONS[dimension],
            )
        )

    rows.extend(
        [
            overview_row(
                config.SMART_DIMENSION_LABELS[
                    config.SINGULARITY_AXIS
                ],
                config.SMART_DIMENSION_QUESTIONS[
                    config.SINGULARITY_AXIS
                ]
                + " « À scinder » signale un énoncé qui porte "
                "plusieurs obligations.",
            ),
            overview_row("", ""),
            overview_row(
                "Symboles des axes",
                " | ".join(
                    f"{config.SMART_VERDICT_SYMBOLS[verdict]} = "
                    f"{config.SMART_VERDICT_LABELS[verdict]}"
                    for verdict in (
                        config.SMART_VERDICT_OK,
                        config.SMART_VERDICT_TO_CHECK,
                        config.SMART_VERDICT_NOT_MET,
                        config.SMART_VERDICT_NOT_ASSESSED,
                    )
                ),
            ),
            overview_row(
                "Portée du verdict",
                "Analyse automatique de la rédaction. Elle ne "
                "juge pas la pertinence technique, ne décide "
                "aucune non-conformité et ne remplace pas la "
                "revue d'ingénierie.",
            ),
            overview_row(
                "Reformulations et risques",
                "Tout ce que l'outil propose est un brouillon. "
                "Rien ne part au client sans validation humaine.",
            ),
        ]
    )

    return pd.DataFrame(rows, columns=OVERVIEW_COLUMNS)


# ============================================================
# Page 2 : une ligne par exigence
# ============================================================

def llm_was_consulted(summary_frame: pd.DataFrame) -> bool:
    """Indique si au moins une exigence a reçu un avis."""

    if "LLM_Decision" not in summary_frame.columns:
        return False

    decisions = (
        summary_frame["LLM_Decision"].map(clean_value).str.upper()
    )

    return bool((~decisions.isin({"", "NOT_RUN"})).any())


def build_requirements_frame(
    summary_frame: pd.DataFrame,
) -> pd.DataFrame:
    """
    Construit la page essentielle, une ligne par exigence.

    Douze colonnes seulement : l'identifiant, le texte, le
    verdict, le profil SMART, l'unicité, l'action attendue et la
    ligne d'origine. Tout le reste est reporté dans les pages
    de détail.

    Une treizième colonne apparaît lorsque le modèle a été
    consulté : sans elle, la page pourrait réclamer une
    correction que le modèle a déjà jugée non fondée.
    """

    if summary_frame.empty:
        return pd.DataFrame(columns=REQUIREMENTS_COLUMNS)

    with_llm = llm_was_consulted(summary_frame)

    columns = list(REQUIREMENTS_COLUMNS)

    if with_llm:
        columns.insert(
            columns.index("Action prioritaire"),
            "Avis du modèle",
        )

    ordered = sort_by_priority(summary_frame)

    rows: list[dict[str, Any]] = []

    for _, row in ordered.iterrows():
        entry = {
            "Exigence": clean_value(row.get(CANONICAL_ID)),
            "Texte de l'exigence": clean_value(
                row.get(CANONICAL_TEXT)
            ),
            "Verdict": status_label(row.get("Quality_Status")),
            "Score SMART": row.get("SMART_Score"),
            "Unicité": singularity_label(
                row.get("Singularity_Status")
            ),
            "Action prioritaire": clean_value(
                row.get("Recommended_Action")
            ),
            "Ligne source": row.get(SOURCE_ROW),
        }

        if with_llm:
            entry["Avis du modèle"] = llm_decision_label(
                row.get("LLM_Decision")
            )

        for dimension in config.SMART_DIMENSIONS:
            entry[
                config.SMART_DIMENSION_LETTERS[dimension]
            ] = config.SMART_VERDICT_SYMBOLS.get(
                clean_value(
                    row.get(
                        config.SMART_DIMENSION_COLUMNS[dimension]
                    )
                ),
                "-",
            )

        rows.append(entry)

    return pd.DataFrame(rows, columns=columns)


# ============================================================
# Page 3 : le détail par axe
# ============================================================

def build_smart_detail_frame(
    summary_frame: pd.DataFrame,
    findings_frame: pd.DataFrame,
) -> pd.DataFrame:
    """
    Détaille, pour chaque exigence, les axes en défaut.

    Une ligne par couple exigence / axe. Les axes conformes ne
    sont pas répétés : la page ne contient que du travail à
    faire. Le défaut d'unicité y figure comme un axe à part
    entière, avec la question à poser.
    """

    if summary_frame.empty:
        return pd.DataFrame(columns=SMART_DETAIL_COLUMNS)

    findings_by_axis: dict[tuple[str, str], pd.DataFrame] = {}

    if not findings_frame.empty:
        grouped = findings_frame.groupby(
            ["Requirement_ID", "SMART_Dimension"],
            dropna=False,
        )

        findings_by_axis = {
            (str(requirement_id), str(dimension)): group
            for (requirement_id, dimension), group in grouped
        }

    rows: list[dict[str, Any]] = []

    for _, row in sort_by_priority(summary_frame).iterrows():
        requirement_id = clean_value(row.get(CANONICAL_ID))

        for dimension in config.SMART_DIMENSIONS:
            verdict = clean_value(
                row.get(config.SMART_DIMENSION_COLUMNS[dimension])
            )

            if verdict == config.SMART_VERDICT_OK:
                continue

            group = findings_by_axis.get(
                (requirement_id, dimension)
            )

            rows.append(
                {
                    "Exigence": requirement_id,
                    "Axe": config.SMART_DIMENSION_LABELS[
                        dimension
                    ],
                    "Verdict": smart_verdict_label(verdict),
                    "Gravité": (
                        display_severity(group["Severity"])
                        if group is not None and not group.empty
                        else ""
                    ),
                    "Règles déclenchées": join_unique(
                        list(group["Rule_ID"])
                        if group is not None
                        else [],
                        separator=", ",
                    ),
                    "Preuves relevées": join_unique(
                        list(group["Evidence"])
                        if group is not None
                        else [],
                        separator=", ",
                    ),
                    "Question à poser": join_unique(
                        list(group["Clarification_Question"])
                        if group is not None
                        else []
                    ),
                    "Reformulation proposée": join_unique(
                        list(group["Rewrite_Template"])
                        if group is not None
                        else []
                    ),
                }
            )

        singularity_status = clean_value(
            row.get("Singularity_Status")
        )

        if singularity_status in (
            config.SINGULARITY_TO_SPLIT,
            config.SINGULARITY_TO_CHECK,
        ):
            estimated = row.get("Estimated_Requirement_Count")

            rows.append(
                {
                    "Exigence": requirement_id,
                    "Axe": config.SMART_DIMENSION_LABELS[
                        config.SINGULARITY_AXIS
                    ],
                    "Verdict": singularity_label(
                        singularity_status
                    ),
                    "Gravité": "",
                    "Règles déclenchées": "",
                    "Preuves relevées": clean_value(
                        row.get("Singularity_Evidence")
                    )
                    or clean_value(
                        row.get("Singularity_Reason")
                    ),
                    "Question à poser": (
                        "L'énoncé semble contenir "
                        f"{estimated} exigences : quelles "
                        "exigences unitaires doivent en être "
                        "tirées, et laquelle porte quelle "
                        "vérification ?"
                        if singularity_status
                        == config.SINGULARITY_TO_SPLIT
                        else (
                            "Cet énoncé porte-t-il une seule "
                            "obligation, ou plusieurs rédigées "
                            "d'un seul tenant ?"
                        )
                    ),
                    "Reformulation proposée": (
                        "Une exigence par obligation, chacune "
                        "avec son identifiant et son critère de "
                        "vérification."
                        if singularity_status
                        == config.SINGULARITY_TO_SPLIT
                        else ""
                    ),
                }
            )

    return pd.DataFrame(rows, columns=SMART_DETAIL_COLUMNS)


# ============================================================
# Page 4 : les questions à poser au client
# ============================================================

def build_questions_frame(
    summary_frame: pd.DataFrame,
) -> pd.DataFrame:
    """
    Construit la liste des questions à envoyer au client.

    C'est la page que l'on sort d'un rapport pour la joindre à
    un courrier. Elle ne contient donc que des exigences qui
    appellent réellement une clarification, et elle montre le
    texte du client annoté plutôt qu'une réécriture : le
    passage en cause est encadré à l'endroit exact où il se
    trouve, sans qu'un mot soit ajouté, retiré ou déplacé.

    Les trois dernières colonnes sont vides à dessein. Elles
    sont là pour être remplies à la main : c'est la trace de la
    validation humaine, sans laquelle rien ne doit partir.
    """

    if summary_frame.empty:
        return pd.DataFrame(columns=QUESTIONS_COLUMNS)

    rows: list[dict[str, Any]] = []

    for _, row in sort_by_priority(summary_frame).iterrows():
        questions = clean_value(row.get("Clarification_Questions"))

        if not questions:
            continue

        annotated = clean_value(row.get("Annotated_Text"))

        rows.append(
            {
                "Exigence": clean_value(row.get(CANONICAL_ID)),
                "Texte du client (passages en cause encadrés)": (
                    annotated or clean_value(row.get(CANONICAL_TEXT))
                ),
                "Questions à poser": questions,
                "Patron de reformulation": clean_value(
                    row.get("Proposed_Rewrites")
                ),
                "Reformulation du modèle": clean_value(
                    row.get("LLM_Proposed_Rewrite")
                ),
                "Avis du modèle": llm_decision_label(
                    row.get("LLM_Decision")
                ),
                "Décision de l'ingénieur": "",
                "Question retenue ou reformulée": "",
                "Validé par": "",
            }
        )

    return pd.DataFrame(rows, columns=QUESTIONS_COLUMNS)


# ============================================================
# Page 5 : les risques à ouvrir
# ============================================================

def build_llm_risk_summary(row: Any) -> str:
    """
    Rassemble en un texte le risque proposé par le modèle.

    Le modèle renvoie son risque en quatre champs distincts.
    Les laisser séparés obligerait le lecteur à recoller les
    morceaux ; les concaténer sans étiquette rendrait le texte
    illisible. Un champ vide est simplement omis.
    """

    if clean_value(row.get("LLM_Risk_Recommended")).upper() not in (
        "YES",
        "TRUE",
        "OUI",
    ):
        return ""

    parts = [
        ("Title", clean_value(row.get("LLM_Risk_Title"))),
        ("Cause", clean_value(row.get("LLM_Risk_Cause"))),
        ("Risk event", clean_value(row.get("LLM_Risk_Event"))),
        (
            "Potential consequence",
            clean_value(row.get("LLM_Risk_Consequences")),
        ),
    ]

    lines = [
        f"{label}: {value}"
        for label, value in parts
        if value
    ]

    if not lines:
        return ""

    lines.append("Status: DRAFT - HUMAN VALIDATION REQUIRED")

    return "\n".join(lines)


def build_risks_frame(
    summary_frame: pd.DataFrame,
) -> pd.DataFrame:
    """
    Construit la liste des risques à ouvrir et à partager.

    Un risque n'est proposé que lorsque le défaut peut
    réellement peser sur l'interprétation, la vérification ou
    l'acceptation. Le brouillon est factuel : il ne cite que
    les axes en défaut, les passages relevés et le verdict de
    singularité, sans inventer de seuil, de coût ni de délai.

    Comme la page des questions, elle se termine par des
    colonnes vides : un risque se décide, il ne se déduit pas.
    """

    if summary_frame.empty:
        return pd.DataFrame(columns=RISKS_COLUMNS)

    rows: list[dict[str, Any]] = []

    selected = summary_frame[
        summary_frame["Risk_To_Assess"].astype(str) == "YES"
    ]

    for _, row in sort_by_priority(selected).iterrows():
        rows.append(
            {
                "Exigence": clean_value(row.get(CANONICAL_ID)),
                "Verdict": status_label(row.get("Quality_Status")),
                "Axes en défaut": clean_value(
                    row.get("SMART_Failed_Axes")
                )
                or clean_value(row.get("SMART_Axes_To_Check")),
                "Unicité": singularity_label(
                    row.get("Singularity_Status")
                ),
                "Brouillon de risque": clean_value(
                    row.get("Risk_Draft")
                ),
                "Risque du modèle": build_llm_risk_summary(row),
                "Décision de l'ingénieur": "",
                "Ouvert dans l'outil de risques": "",
                "Validé par": "",
            }
        )

    return pd.DataFrame(rows, columns=RISKS_COLUMNS)



# ============================================================
# Conversion des diagnostics en tableau
# ============================================================

def diagnostics_to_frame(
    diagnostics: dict[str, Any],
    section: str,
) -> pd.DataFrame:
    """
    Transforme un dictionnaire de diagnostics en tableau.

    Les dictionnaires imbriqués et les listes sont aplatis,
    afin qu'aucune information ne disparaisse du rapport.
    """

    rows: list[dict[str, Any]] = []

    for key, value in diagnostics.items():
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                rows.append(
                    {
                        "Section": section,
                        "Metric": f"{key}.{nested_key}",
                        "Value": nested_value,
                    }
                )
        elif isinstance(value, (list, tuple)):
            if not value:
                rows.append(
                    {
                        "Section": section,
                        "Metric": key,
                        "Value": "",
                    }
                )

            for position, item in enumerate(value, start=1):
                rows.append(
                    {
                        "Section": section,
                        "Metric": f"{key}.{position}",
                        "Value": item,
                    }
                )
        else:
            rows.append(
                {
                    "Section": section,
                    "Metric": key,
                    "Value": value,
                }
            )

    return pd.DataFrame(
        rows,
        columns=["Section", "Metric", "Value"],
    )


def rules_to_frame(rules: list[Any]) -> pd.DataFrame:
    """Convertit les règles utilisées en tableau traçable."""

    rows = [
        rule.to_dict()
        if hasattr(rule, "to_dict")
        else {"rule_id": str(rule)}
        for rule in rules
    ]

    return pd.DataFrame(rows)


# ============================================================
# Préparation des données pour Excel
# ============================================================

def prepare_frame_for_excel(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Rend un tableau écrivable par openpyxl.

    Les valeurs trop longues sont tronquées avec une mention
    explicite, car Excel rejetterait silencieusement la
    cellule. Les types non scalaires sont convertis en texte.
    """

    prepared = frame.copy()

    for column in prepared.columns:
        series = prepared[column]

        if series.map(
            lambda value: isinstance(value, (list, dict, tuple, set))
        ).any():
            series = series.map(
                lambda value: str(value)
                if isinstance(value, (list, dict, tuple, set))
                else value
            )

        # Le test porte sur les valeurs, et non sur le dtype de
        # la colonne. Pandas 3 donne le dtype « str » aux
        # colonnes de texte : la condition « dtype == object »
        # ne s'y déclenchait plus, et Excel tronquait à sa
        # limite sans le dire au lecteur.
        if series.map(lambda value: isinstance(value, str)).any():
            series = series.map(
                lambda value: (
                    value[:EXCEL_MAXIMUM_CELL_LENGTH]
                    + " [...texte tronqué pour Excel]"
                )
                if isinstance(value, str)
                and len(value) > EXCEL_MAXIMUM_CELL_LENGTH
                else value
            )

        prepared[column] = series

    return prepared


# ============================================================
# Mise en forme
# ============================================================

def format_worksheet(worksheet) -> None:
    """Applique une mise en forme lisible à une feuille."""

    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    if worksheet.max_row < 1:
        return

    header_fill = PatternFill(fill_type="solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)

    worksheet.freeze_panes = "A2"

    if worksheet.max_row > 1:
        worksheet.auto_filter.ref = worksheet.dimensions

    for cell in worksheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

    for row in worksheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True,
            )

    for position, column_cells in enumerate(
        worksheet.iter_cols(),
        start=1,
    ):
        longest = 0

        for cell in column_cells[:WIDTH_SAMPLE_ROWS]:
            value = "" if cell.value is None else str(cell.value)

            longest = max(
                longest,
                max(
                    (len(line) for line in value.splitlines()),
                    default=0,
                ),
            )

        if longest <= NARROW_CONTENT_LENGTH:
            width = NARROW_COLUMN_WIDTH
        else:
            width = min(
                max(longest + 2, MINIMUM_COLUMN_WIDTH),
                MAXIMUM_COLUMN_WIDTH,
            )

        worksheet.column_dimensions[
            get_column_letter(position)
        ].width = width


def format_overview_worksheet(
    worksheet,
    title: str = "CONTRÔLEUR DE QUALITÉ DES EXIGENCES",
) -> None:
    """
    Met en forme la page de synthèse.

    La synthèse n'est pas un tableau de données : ni filtre, ni
    volet figé, ni quadrillage. La première ligne porte le
    titre du rapport à la place des en-têtes de colonnes, et
    les lignes sans valeur deviennent des titres de section.
    """

    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    if worksheet.max_row < 1:
        return

    worksheet.sheet_view.showGridLines = False

    worksheet.column_dimensions[get_column_letter(1)].width = 42
    worksheet.column_dimensions[get_column_letter(2)].width = 78

    # Ligne 1 : le titre, à la place de « Indicateur / Valeur ».
    title_cell = worksheet.cell(row=1, column=1)
    title_cell.value = title
    worksheet.cell(row=1, column=2).value = None

    for column in (1, 2):
        cell = worksheet.cell(row=1, column=column)
        cell.fill = PatternFill(
            fill_type="solid",
            fgColor=OVERVIEW_SECTION_FILL,
        )
        cell.font = Font(color="FFFFFF", bold=True, size=14)
        cell.alignment = Alignment(vertical="center")

    worksheet.row_dimensions[1].height = 26

    for row_index in range(2, worksheet.max_row + 1):
        label_cell = worksheet.cell(row=row_index, column=1)
        value_cell = worksheet.cell(row=row_index, column=2)

        label = (
            "" if label_cell.value is None else str(label_cell.value)
        )
        value = (
            "" if value_cell.value is None else str(value_cell.value)
        )

        label_cell.alignment = Alignment(vertical="top")
        value_cell.alignment = Alignment(
            vertical="top",
            wrap_text=True,
        )

        if label and not value:
            for column in (1, 2):
                cell = worksheet.cell(row=row_index, column=column)
                cell.fill = PatternFill(
                    fill_type="solid",
                    fgColor=OVERVIEW_SECTION_FILL,
                )
                cell.font = Font(color="FFFFFF", bold=True)

            continue

        label_cell.font = Font(bold=True)


def apply_value_colors(
    worksheet,
    column_name: str,
    colors: dict[str, str],
) -> None:
    """Colore les cellules d'une colonne selon leur valeur."""

    from openpyxl.styles import PatternFill

    headers = {
        str(cell.value): cell.column
        for cell in worksheet[1]
        if cell.value is not None
    }

    column_index = headers.get(column_name)

    if column_index is None:
        return

    fills = {
        value: PatternFill(fill_type="solid", fgColor=color)
        for value, color in colors.items()
    }

    for row_index in range(2, worksheet.max_row + 1):
        cell = worksheet.cell(row=row_index, column=column_index)
        fill = fills.get(str(cell.value))

        if fill is not None:
            cell.fill = fill


# ============================================================
# Écriture du rapport
# ============================================================

def write_report(
    output_path: str | Path,
    sheets: dict[str, pd.DataFrame],
    overview_sheets: Iterable[str] = (),
) -> Path:
    """
    Écrit un classeur à partir d'un dictionnaire de feuilles.

    L'ordre du dictionnaire est celui des onglets : la feuille
    de synthèse est donc celle qui s'ouvre.

    Les noms de feuilles sont tronqués à 31 caractères, limite
    d'Excel. Une feuille vide est conservée avec son en-tête
    pour que le lecteur sache qu'elle a bien été produite.

    Les feuilles nommées dans overview_sheets reçoivent la mise
    en forme de synthèse au lieu de la mise en forme tableau.
    """

    overview_titles = {
        str(name)[:31]
        for name in overview_sheets
    }

    path = Path(output_path).expanduser().resolve()

    if path.suffix.lower() != ".xlsx":
        raise ValueError(
            "Le rapport de sortie doit porter l'extension .xlsx."
        )

    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for sheet_name, frame in sheets.items():
                if frame is None:
                    continue

                prepare_frame_for_excel(frame).to_excel(
                    writer,
                    sheet_name=sheet_name[:31],
                    index=False,
                )

            for worksheet in writer.book.worksheets:
                if worksheet.title in overview_titles:
                    format_overview_worksheet(worksheet)
                    continue

                format_worksheet(worksheet)
                apply_value_colors(
                    worksheet,
                    "Quality_Status",
                    STATUS_COLORS,
                )
                apply_value_colors(
                    worksheet,
                    "LLM_Decision",
                    DECISION_COLORS,
                )
                apply_value_colors(
                    worksheet,
                    "Import_Status",
                    {"READY": "C6E0B4"},
                )

                # Lecture SMART : verdicts en clair sur les
                # pages de tête, valeurs techniques sur les
                # pages de détail.
                apply_value_colors(
                    worksheet,
                    "Verdict",
                    VERDICT_COLORS,
                )
                apply_value_colors(
                    worksheet,
                    "Unicité",
                    SINGULARITY_LABEL_COLORS,
                )
                apply_value_colors(
                    worksheet,
                    "Singularity_Status",
                    SINGULARITY_STATUS_COLORS,
                )
                apply_value_colors(
                    worksheet,
                    "Duplicate_Status",
                    DUPLICATE_STATUS_COLORS,
                )
                apply_value_colors(
                    worksheet,
                    "Avis du modèle",
                    LLM_DECISION_LABEL_COLORS,
                )

                for dimension in config.SMART_DIMENSIONS:
                    apply_value_colors(
                        worksheet,
                        config.SMART_DIMENSION_COLUMNS[dimension],
                        SMART_VERDICT_COLORS,
                    )
                    apply_value_colors(
                        worksheet,
                        config.SMART_DIMENSION_LETTERS[dimension],
                        SMART_SYMBOL_COLORS,
                    )

    except PermissionError as error:
        raise PermissionError(
            "Impossible d'écrire le rapport : le fichier est "
            "probablement ouvert dans Excel.\n"
            f"Ferme {path.name} puis relance l'analyse."
        ) from error

    return path
