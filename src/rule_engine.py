# ============================================================
# Moteur de règles déterministe
# ============================================================
#
# Le moteur détecte et prouve. Il ne décide pas.
#
# Il reçoit un tableau déjà normalisé par le chargeur et
# applique le catalogue de règles. Il ne connaît ni le nom des
# colonnes du client, ni son vocabulaire de types : ce travail
# est fait en amont.
#
# ============================================================

from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any

import pandas as pd

from src import config
from src.config import (
    CANONICAL_ID,
    CANONICAL_TEXT,
    CANONICAL_TYPE,
    SOURCE_ROW,
    SOURCE_SHEET,
    EngineSettings,
)
from src.rule_loader import Rule
from src.smart_evaluator import evaluate_requirement
from src.text_utils import (
    clean_value,
    join_unique,
    normalize_key,
    unique_preserve_order,
)


def smart_column_name(dimension: str) -> str:
    """
    Nomme la colonne de rapport d'un axe SMART.

    Le nom vient de la configuration, et n'est codé en dur
    nulle part : déclarer un axe suffit à le voir apparaître
    dans le rapport.
    """

    return config.SMART_DIMENSION_COLUMNS[dimension]


SMART_DIMENSION_COLUMNS = [
    smart_column_name(dimension)
    for dimension in config.SMART_DIMENSIONS
]


FINDING_COLUMNS = [
    "Requirement_ID",
    "Source",
    "Rule_ID",
    "Category",
    "SMART_Dimension",
    "Severity",
    "Evidence",
    "Start_Position",
    "End_Position",
    "Occurrence_Index",
    "Explanation",
    "Clarification_Question",
    "Rewrite_Template",
    "Source_Excel_Row",
]

SUMMARY_COLUMNS = [
    CANONICAL_ID,
    CANONICAL_TEXT,
    CANONICAL_TYPE,
    SOURCE_ROW,
    SOURCE_SHEET,
    "Quality_Status",
    "Quality_Score",
    "SMART_Score",
    "SMART_Profile",
    "SMART_Compliant_Axes",
    *SMART_DIMENSION_COLUMNS,
    "SMART_Failed_Axes",
    "SMART_Axes_To_Check",
    "Singularity_Status",
    "Obligation_Count",
    "Estimated_Requirement_Count",
    "Singularity_Reason",
    "Singularity_Evidence",
    "Duplicate_Status",
    "Duplicate_With",
    "Recommended_Action",
    "Issue_Count",
    "Occurrence_Count",
    "Highest_Severity",
    "Issue_Categories",
    "Triggered_Rules",
    "Evidence",
    "Annotated_Text",
    "Explanations",
    "Clarification_Questions",
    "Proposed_Rewrites",
    "Risk_To_Assess",
    "Risk_Draft",
    "Analysis_Time_ms",
]


# ============================================================
# Modèle d'une anomalie
# ============================================================

@dataclass(frozen=True)
class Finding:
    """Une occurrence de règle détectée dans une exigence."""

    requirement_id: str
    rule_id: str
    category: str
    smart_dimension: str
    severity: str
    evidence: str
    start_position: int
    end_position: int
    occurrence_index: int
    explanation: str
    clarification_question: str
    rewrite_template: str
    source_excel_row: int | None

    # Origine du constat : une règle du catalogue, ou le modèle
    # lors de la revue contextuelle.
    source: str = config.FINDING_SOURCE_RULE

    def to_row(self) -> dict[str, Any]:
        """Convertit l'anomalie en ligne de rapport."""

        values = asdict(self)

        return {
            "Requirement_ID": values["requirement_id"],
            "Source": values["source"],
            "Rule_ID": values["rule_id"],
            "Category": values["category"],
            "SMART_Dimension": values["smart_dimension"],
            "Severity": values["severity"],
            "Evidence": values["evidence"],
            "Start_Position": values["start_position"],
            "End_Position": values["end_position"],
            "Occurrence_Index": values["occurrence_index"],
            "Explanation": values["explanation"],
            "Clarification_Question": values[
                "clarification_question"
            ],
            "Rewrite_Template": values["rewrite_template"],
            "Source_Excel_Row": values["source_excel_row"],
        }


# ============================================================
# Utilitaires
# ============================================================

def severity_rank(severity: str) -> int:
    """Retourne le rang numérique d'une gravité."""

    return config.SEVERITY_RANK.get(str(severity).upper(), 0)


def get_highest_severity(findings: list[Finding]) -> str:
    """Retourne la gravité la plus élevée, ou NONE."""

    if not findings:
        return "NONE"

    return max(
        (finding.severity for finding in findings),
        key=severity_rank,
    )


def distinct_rule_ids(findings: list[Finding]) -> list[str]:
    """Liste les règles déclenchées, sans répétition."""

    return unique_preserve_order(
        [finding.rule_id for finding in findings]
    )


# ============================================================
# Texte annoté
# ============================================================

# Marqueurs encadrant un passage détecté. Ils ne font pas
# partie du texte client : ils sont ajoutés pour la revue.
EVIDENCE_OPENING_MARK = "《"
EVIDENCE_CLOSING_MARK = "》"


def build_annotated_text(
    text: str,
    findings: list[Finding],
) -> str:
    """
    Recopie l'exigence en encadrant les passages détectés.

    C'est la seule « reformulation » que le moteur puisse
    produire honnêtement : le texte du client, intact, avec le
    défaut montré là où il se trouve. Aucun mot n'est ajouté,
    retiré ni déplacé.

    Les chevauchements sont écartés : un passage déjà encadré
    n'est pas annoté une seconde fois.
    """

    if not text or not findings:
        return ""

    spans: list[tuple[int, int]] = []

    for finding in sorted(
        findings,
        key=lambda item: (item.start_position, -item.end_position),
    ):
        start = int(finding.start_position)
        end = int(finding.end_position)

        if start < 0 or end > len(text) or start >= end:
            continue

        if spans and start < spans[-1][1]:
            continue

        spans.append((start, end))

    if not spans:
        return ""

    pieces: list[str] = []
    cursor = 0

    for start, end in spans:
        pieces.append(text[cursor:start])
        pieces.append(EVIDENCE_OPENING_MARK)
        pieces.append(text[start:end])
        pieces.append(EVIDENCE_CLOSING_MARK)
        cursor = end

    pieces.append(text[cursor:])

    return "".join(pieces)


# ============================================================
# Score, statut et risque
# ============================================================

def compute_quality_score(findings: list[Finding]) -> int:
    """
    Calcule un score de 0 à 100.

    Le score est pénalisé une seule fois par règle déclenchée.
    Une exigence qui répète dix fois le même mot vague n'est
    pas dix fois plus mauvaise qu'une exigence qui le dit une
    fois : seule la nature du défaut compte.
    """

    if not findings:
        return 100

    severity_by_rule: dict[str, str] = {}

    for finding in findings:
        current = severity_by_rule.get(finding.rule_id)

        if current is None or severity_rank(
            finding.severity
        ) > severity_rank(current):
            severity_by_rule[finding.rule_id] = finding.severity

    penalty = sum(
        config.SEVERITY_WEIGHT.get(severity, 0)
        for severity in severity_by_rule.values()
    )

    return max(0, 100 - penalty)


def determine_quality_status(
    findings: list[Finding],
    settings: EngineSettings,
) -> str:
    """Déduit le statut qualité de la gravité la plus élevée."""

    if not findings:
        return config.STATUS_PRE_ANALYSIS_OK

    highest = get_highest_severity(findings)

    return settings.severity_to_status.get(
        highest,
        config.STATUS_REVIEW_REQUIRED,
    )


def raise_to_review_required(quality_status: str) -> str:
    """
    Relève un statut favorable au niveau « revue nécessaire ».

    Un statut déjà plus sévère n'est jamais abaissé : une
    exigence qui demande une clarification client ne redevient
    pas une simple revue interne.
    """

    if quality_status in (
        config.STATUS_PRE_ANALYSIS_OK,
        config.STATUS_REVIEW_RECOMMENDED,
    ):
        return config.STATUS_REVIEW_REQUIRED

    return quality_status


def escalate_status_for_singularity(
    quality_status: str,
    singularity_status: str,
) -> str:
    """
    Relève le statut d'une exigence qui en contient plusieurs.

    Un énoncé à scinder ne peut pas être déclaré bon en
    pré-analyse, même quand aucune règle de rédaction ne se
    déclenche : tant que les exigences ne sont pas séparées,
    leur vérification ne peut pas être tracée une par une.
    """

    if singularity_status != config.SINGULARITY_TO_SPLIT:
        return quality_status

    return raise_to_review_required(quality_status)


def should_assess_risk(
    findings: list[Finding],
    settings: EngineSettings,
    singularity_status: str = "",
) -> bool:
    """
    Indique si un brouillon de risque mérite d'être proposé.

    Trois conditions suffisent, mais aucune n'est automatique :
    une gravité élevée, plusieurs catégories sensibles touchées
    en même temps, ou un énoncé qui porte plusieurs exigences.
    Proposer un risque pour chaque alerte reviendrait à n'en
    signaler aucun.

    Le troisième cas n'a pas besoin de constat de règle : un
    énoncé à scinder empêche de tracer la vérification de
    chaque obligation, ce qui est un risque d'acceptation même
    quand la rédaction est par ailleurs irréprochable.
    """

    if singularity_status == config.SINGULARITY_TO_SPLIT:
        return True

    if not findings:
        return False

    highest_rank = severity_rank(get_highest_severity(findings))

    if highest_rank >= severity_rank(
        settings.risk_minimum_severity
    ):
        return True

    touched_risk_categories = {
        finding.category
        for finding in findings
        if finding.category in config.RISK_RELEVANT_CATEGORIES
    }

    return (
        len(touched_risk_categories)
        >= settings.risk_minimum_category_count
    )


def build_risk_draft(
    requirement_id: str,
    findings: list[Finding],
    assessment: dict[str, Any] | None = None,
) -> str:
    """
    Construit un brouillon de risque factuel, prêt à discuter.

    Le brouillon est écrit en anglais, comme les exigences : il
    est destiné à être partagé avec le client après validation
    humaine.

    Aucune valeur, aucun seuil, aucun délai et aucune
    conséquence chiffrée n'est inventé. Le texte ne reprend que
    les axes SMART en défaut, les catégories détectées, les
    preuves relevées et le verdict de singularité. Il nomme
    enfin l'action attendue, pour qu'un lecteur sache quoi en
    faire.
    """

    assessment = assessment or {}
    singularity = assessment.get("singularity", {})
    to_split = (
        singularity.get("status") == config.SINGULARITY_TO_SPLIT
    )

    if not findings and not to_split:
        return ""

    lines = [f"Title: Requirement quality risk on {requirement_id}"]

    failed_axes = ", ".join(
        config.SMART_DIMENSION_NAMES_EN[dimension]
        for dimension in (
            list(assessment.get("not_met", ()))
            + list(assessment.get("to_check", ()))
        )
    )

    cause = []

    if failed_axes:
        cause.append(
            "The requirement does not satisfy the following "
            f"quality criteria: {failed_axes}."
        )

    if findings:
        cause.append(
            "Detected categories: "
            + join_unique(
                [finding.category for finding in findings],
                separator=", ",
            )
            + ". Detected wording: "
            + join_unique(
                [finding.evidence for finding in findings],
                separator=", ",
            )
            + "."
        )

    if to_split:
        cause.append(
            "The statement also carries more than one "
            "obligation, so the verification of each obligation "
            "cannot be traced separately."
        )

    lines.append("Cause: " + " ".join(cause))

    lines.append(
        "Risk event: The customer and the project team may "
        "interpret, implement or verify the requirement "
        "differently."
    )
    lines.append(
        "Potential consequence: Rework, acceptance dispute, cost "
        "increase or schedule delay."
    )
    lines.append(
        "Proposed mitigation: Submit the clarification questions "
        "attached to this requirement to the customer, then "
        "reword"
        + (" and split" if to_split else "")
        + " the requirement once the answers are confirmed."
    )
    lines.append("Status: DRAFT - HUMAN VALIDATION REQUIRED")

    return "\n".join(lines)


# ============================================================
# Analyse d'une exigence
# ============================================================

def analyse_text(
    requirement_id: str,
    text: str,
    rules: list[Rule],
    source_excel_row: int | None,
) -> list[Finding]:
    """Applique toutes les règles actives à un texte."""

    findings: list[Finding] = []

    for rule in rules:
        if not rule.enabled:
            continue

        for occurrence_index, match in enumerate(
            rule.find_matches(text),
            start=1,
        ):
            findings.append(
                Finding(
                    requirement_id=requirement_id,
                    rule_id=rule.rule_id,
                    category=rule.category,
                    smart_dimension=rule.smart_dimension,
                    severity=rule.severity,
                    evidence=match["evidence"],
                    start_position=match["start_position"],
                    end_position=match["end_position"],
                    occurrence_index=occurrence_index,
                    explanation=rule.explanation,
                    clarification_question=(
                        rule.clarification_question
                    ),
                    rewrite_template=rule.rewrite_template,
                    source_excel_row=source_excel_row,
                )
            )

    return findings


def read_source_row(value: Any) -> int | None:
    """Lit un numéro de ligne Excel, ou None s'il est illisible."""

    try:
        return (
            int(value)
            if value is not None and not pd.isna(value)
            else None
        )
    except (TypeError, ValueError):
        return None


def summarise_requirement(
    requirement_id: str,
    text: str,
    object_type: str,
    source_excel_row: int | None,
    source_sheet: str,
    findings: list[Finding],
    settings: EngineSettings,
    elapsed_milliseconds: float = 0.0,
) -> dict[str, Any]:
    """
    Construit la ligne de résumé d'une exigence.

    La fonction ne détecte rien : elle met en forme un jeu de
    constats déjà établi. C'est ce qui permet de la réutiliser
    après la revue du modèle, lorsque des constats ont été
    écartés et d'autres ajoutés, sans dupliquer la construction
    des colonnes.
    """

    quality_status = (
        config.STATUS_NOT_ANALYSED
        if not text
        else determine_quality_status(findings, settings)
    )

    # Lecture SMART et singularité : les mêmes constats, lus
    # par axe plutôt que par règle.
    assessment = evaluate_requirement(
        text=text,
        findings=findings,
        settings=settings.singularity,
    )
    singularity = assessment["singularity"]

    quality_status = escalate_status_for_singularity(
        quality_status=quality_status,
        singularity_status=singularity["status"],
    )

    risk_to_assess = should_assess_risk(
        findings=findings,
        settings=settings,
        singularity_status=singularity["status"],
    )

    return {
        CANONICAL_ID: requirement_id,
        CANONICAL_TEXT: text,
        CANONICAL_TYPE: object_type,
        SOURCE_ROW: source_excel_row,
        SOURCE_SHEET: source_sheet,
        "Quality_Status": quality_status,
        "Quality_Score": compute_quality_score(findings),
        "SMART_Score": assessment["score"],
        "SMART_Profile": assessment["profile"],
        "SMART_Compliant_Axes": (
            f"{assessment['compliant_count']}"
            f"/{len(config.SMART_DIMENSIONS)}"
        ),
        **{
            smart_column_name(dimension): assessment[
                "dimensions"
            ][dimension]["verdict"]
            for dimension in config.SMART_DIMENSIONS
        },
        "SMART_Failed_Axes": ", ".join(
            config.SMART_DIMENSION_LABELS[dimension]
            for dimension in assessment["not_met"]
        ),
        "SMART_Axes_To_Check": ", ".join(
            config.SMART_DIMENSION_LABELS[dimension]
            for dimension in assessment["to_check"]
        ),
        "Singularity_Status": singularity["status"],
        "Obligation_Count": singularity["obligation_count"],
        "Estimated_Requirement_Count": singularity[
            "estimated_count"
        ],
        "Singularity_Reason": " | ".join(singularity["reasons"]),
        "Singularity_Evidence": " | ".join(
            singularity["evidence"]
        ),
        # Renseignées par la passe sur le lot entier : une
        # exigence seule ne peut pas savoir qu'elle est répétée.
        "Duplicate_Status": config.DUPLICATE_NONE,
        "Duplicate_With": "",
        "Recommended_Action": assessment["action"],
        # Nombre de règles distinctes, et non d'occurrences :
        # c'est la mesure qui reflète le nombre de défauts.
        "Issue_Count": len(distinct_rule_ids(findings)),
        "Occurrence_Count": len(findings),
        "Highest_Severity": get_highest_severity(findings),
        "Issue_Categories": join_unique(
            [finding.category for finding in findings]
        ),
        "Triggered_Rules": join_unique(
            [finding.rule_id for finding in findings]
        ),
        "Evidence": join_unique(
            [finding.evidence for finding in findings]
        ),
        "Annotated_Text": build_annotated_text(text, findings),
        "Explanations": join_unique(
            [finding.explanation for finding in findings]
        ),
        "Clarification_Questions": join_unique(
            [finding.clarification_question for finding in findings]
        ),
        "Proposed_Rewrites": join_unique(
            [finding.rewrite_template for finding in findings]
        ),
        "Risk_To_Assess": "YES" if risk_to_assess else "NO",
        "Risk_Draft": (
            build_risk_draft(
                requirement_id=requirement_id,
                findings=findings,
                assessment=assessment,
            )
            if risk_to_assess
            else ""
        ),
        "Analysis_Time_ms": round(elapsed_milliseconds, 3),
    }


def analyse_row(
    row: pd.Series,
    rules: list[Rule],
    settings: EngineSettings,
) -> tuple[dict[str, Any], list[Finding]]:
    """Analyse une ligne et retourne son résumé et ses anomalies."""

    started_at = perf_counter()

    requirement_id = clean_value(row.get(CANONICAL_ID))
    text = clean_value(row.get(CANONICAL_TEXT))
    object_type = clean_value(row.get(CANONICAL_TYPE))

    source_excel_row = read_source_row(row.get(SOURCE_ROW))

    findings: list[Finding] = (
        analyse_text(
            requirement_id=requirement_id,
            text=text,
            rules=rules,
            source_excel_row=source_excel_row,
        )
        if text
        else []
    )

    summary = summarise_requirement(
        requirement_id=requirement_id,
        text=text,
        object_type=object_type,
        source_excel_row=source_excel_row,
        source_sheet=clean_value(row.get(SOURCE_SHEET)),
        findings=findings,
        settings=settings,
        elapsed_milliseconds=(perf_counter() - started_at) * 1000,
    )

    return summary, findings


# ============================================================
# Relecture des constats depuis le rapport
# ============================================================

def rebuild_findings(
    findings_frame: pd.DataFrame,
    requirement_id: str,
) -> list[Finding]:
    """
    Reconstruit les constats d'une exigence depuis le tableau.

    La revue du modèle travaille sur le rapport déjà produit :
    elle a besoin des constats sous forme d'objets pour les
    réévaluer, sans relancer le moteur de règles.
    """

    if findings_frame.empty:
        return []

    selected = findings_frame[
        findings_frame["Requirement_ID"].astype(str)
        == str(requirement_id)
    ]

    findings: list[Finding] = []

    for _, row in selected.iterrows():
        findings.append(
            Finding(
                requirement_id=clean_value(
                    row.get("Requirement_ID")
                ),
                rule_id=clean_value(row.get("Rule_ID")),
                category=clean_value(row.get("Category")),
                smart_dimension=clean_value(
                    row.get("SMART_Dimension")
                ),
                severity=clean_value(row.get("Severity")),
                evidence=clean_value(row.get("Evidence")),
                start_position=int(
                    row.get("Start_Position") or 0
                ),
                end_position=int(row.get("End_Position") or 0),
                occurrence_index=int(
                    row.get("Occurrence_Index") or 1
                ),
                explanation=clean_value(row.get("Explanation")),
                clarification_question=clean_value(
                    row.get("Clarification_Question")
                ),
                rewrite_template=clean_value(
                    row.get("Rewrite_Template")
                ),
                source_excel_row=read_source_row(
                    row.get(SOURCE_ROW)
                ),
                source=clean_value(row.get("Source"))
                or config.FINDING_SOURCE_RULE,
            )
        )

    return findings


# ============================================================
# Doublons de texte dans le lot
# ============================================================

def build_duplicate_signatures(
    requirement_text: str,
) -> tuple[str, str]:
    """
    Produit les deux signatures d'une exigence.

    La première est le texte normalisé : même ponctuation, même
    casse, mêmes espaces. Elle repère les copier-coller.

    La seconde est l'ensemble trié de ses mots. Elle repère les
    exigences réécrites dans un autre ordre, ou dont seule la
    ponctuation diffère. Sous un nombre minimal de mots, elle
    est abandonnée : deux exigences courtes partagent
    légitimement leur vocabulaire.
    """

    normalized = normalize_key(requirement_text)

    if not normalized:
        return "", ""

    words = sorted(set(normalized.split()))

    if len(words) < config.DUPLICATE_MINIMUM_SIGNATURE_WORDS:
        return normalized, ""

    return normalized, " ".join(words)


def detect_duplicate_text(
    summary_frame: pd.DataFrame,
) -> pd.DataFrame:
    """
    Marque les exigences qui répètent le texte d'une autre.

    Le chargeur signale déjà les identifiants dupliqués. Ici
    c'est le cas inverse : deux identifiants distincts qui
    portent la même exigence. Les deux seront vérifiés, tracés
    et facturés, alors qu'une seule est nécessaire.

    Aucune exigence n'est désignée comme l'originale : les
    membres d'un groupe se citent mutuellement, et le choix de
    celle à conserver revient à l'ingénieur.
    """

    if summary_frame.empty:
        return summary_frame

    frame = summary_frame.copy()

    identical: dict[str, list[str]] = {}
    similar: dict[str, list[str]] = {}

    signatures: list[tuple[str, str]] = []

    for _, row in frame.iterrows():
        requirement_id = clean_value(row.get(CANONICAL_ID))
        exact, approximate = build_duplicate_signatures(
            clean_value(row.get(CANONICAL_TEXT))
        )

        signatures.append((exact, approximate))

        if exact:
            identical.setdefault(exact, []).append(requirement_id)

        if approximate:
            similar.setdefault(approximate, []).append(
                requirement_id
            )

    statuses: list[str] = []
    partners: list[str] = []

    for position, (exact, approximate) in enumerate(signatures):
        requirement_id = clean_value(
            frame.iloc[position].get(CANONICAL_ID)
        )

        group = [
            other
            for other in identical.get(exact, [])
            if other != requirement_id
        ]
        status = config.DUPLICATE_IDENTICAL if group else ""

        if not group:
            group = [
                other
                for other in similar.get(approximate, [])
                if other != requirement_id
            ]
            status = config.DUPLICATE_SIMILAR if group else ""

        statuses.append(status or config.DUPLICATE_NONE)
        partners.append(join_unique(group, separator=", "))

    frame["Duplicate_Status"] = statuses
    frame["Duplicate_With"] = partners

    # Un doublon se traite avant toute correction de rédaction :
    # corriger deux fois le même texte est du travail perdu.
    duplicated = frame["Duplicate_Status"] != config.DUPLICATE_NONE

    frame.loc[duplicated, "Recommended_Action"] = (
        "Doublon de "
        + frame.loc[duplicated, "Duplicate_With"]
        + " : ne conserver qu'une seule exigence avant toute "
        "correction."
    )

    # Le statut suit l'action. Laisser « prête en pré-analyse »
    # une exigence dont l'action demande d'en supprimer une
    # mettrait deux lectures contradictoires sur la même ligne.
    frame.loc[duplicated, "Quality_Status"] = frame.loc[
        duplicated,
        "Quality_Status",
    ].map(raise_to_review_required)

    return frame


# ============================================================
# Analyse d'un tableau complet
# ============================================================

def validate_input_columns(requirements: pd.DataFrame) -> None:
    """Vérifie que le tableau a bien été normalisé en amont."""

    missing = [
        column
        for column in (CANONICAL_ID, CANONICAL_TEXT)
        if column not in requirements.columns
    ]

    if missing:
        raise ValueError(
            "Le tableau d'entrée n'est pas normalisé. Colonnes "
            "absentes : "
            + ", ".join(missing)
            + "\nUtilise src.excel_loader.load_requirements pour "
            "produire ce tableau."
        )


def analyse_requirements(
    requirements: pd.DataFrame,
    rules: list[Rule],
    settings: EngineSettings | None = None,
) -> dict[str, Any]:
    """
    Analyse un tableau d'exigences normalisé.

    Retour :
        {
            "summary":     une ligne par exigence,
            "findings":    une ligne par occurrence de règle,
            "diagnostics": statistiques d'exécution,
        }
    """

    settings = settings or EngineSettings()
    validate_input_columns(requirements)

    if not rules:
        raise ValueError(
            "Aucune règle active : le catalogue est vide ou "
            "toutes les règles sont désactivées."
        )

    started_at = perf_counter()

    summaries: list[dict[str, Any]] = []
    all_findings: list[Finding] = []

    for _, row in requirements.iterrows():
        summary, row_findings = analyse_row(
            row=row,
            rules=rules,
            settings=settings,
        )

        summaries.append(summary)
        all_findings.extend(row_findings)

    summary_frame = pd.DataFrame(
        summaries,
        columns=SUMMARY_COLUMNS,
    )

    if settings.detect_duplicate_text:
        summary_frame = detect_duplicate_text(summary_frame)

    findings_frame = pd.DataFrame(
        [finding.to_row() for finding in all_findings],
        columns=FINDING_COLUMNS,
    )

    total_seconds = perf_counter() - started_at
    analysed_count = len(summary_frame)

    def value_counts(frame: pd.DataFrame, column: str) -> dict:
        if frame.empty:
            return {}

        return frame[column].value_counts().to_dict()

    diagnostics = {
        "analysed_requirement_count": analysed_count,
        "rule_count": len(rules),
        "distinct_issue_count": int(
            summary_frame["Issue_Count"].sum()
        )
        if analysed_count
        else 0,
        "occurrence_count": int(len(findings_frame)),
        "requirements_with_issues": int(
            (summary_frame["Issue_Count"] > 0).sum()
        )
        if analysed_count
        else 0,
        "requirements_without_issues": int(
            (summary_frame["Issue_Count"] == 0).sum()
        )
        if analysed_count
        else 0,
        "flag_rate": round(
            float((summary_frame["Issue_Count"] > 0).mean()),
            4,
        )
        if analysed_count
        else 0.0,
        "average_quality_score": round(
            float(summary_frame["Quality_Score"].mean()),
            2,
        )
        if analysed_count
        else 100.0,
        "average_smart_score": round(
            float(summary_frame["SMART_Score"].mean()),
            2,
        )
        if analysed_count
        else 100.0,
        "fully_smart_count": int(
            (
                summary_frame["SMART_Score"]
                == config.SMART_MAXIMUM_SCORE
            ).sum()
        )
        if analysed_count
        else 0,
        "duplicate_text_count": int(
            (
                summary_frame["Duplicate_Status"]
                != config.DUPLICATE_NONE
            ).sum()
        )
        if analysed_count
        else 0,
        "requirements_to_split": int(
            (
                summary_frame["Singularity_Status"]
                == config.SINGULARITY_TO_SPLIT
            ).sum()
        )
        if analysed_count
        else 0,
        "risk_to_assess_count": int(
            (summary_frame["Risk_To_Assess"] == "YES").sum()
        )
        if analysed_count
        else 0,
        "total_time_seconds": round(total_seconds, 3),
        "average_time_ms": round(
            (total_seconds * 1000) / analysed_count,
            3,
        )
        if analysed_count
        else 0.0,
        "status_counts": value_counts(summary_frame, "Quality_Status"),
        "singularity_counts": value_counts(
            summary_frame,
            "Singularity_Status",
        ),
        "duplicate_counts": value_counts(
            summary_frame[
                summary_frame["Duplicate_Status"]
                != config.DUPLICATE_NONE
            ],
            "Duplicate_Status",
        )
        if analysed_count
        else {},
        # Nombre d'exigences en défaut sur chaque axe, pour
        # savoir où le lot pèche d'abord.
        "smart_axis_not_met_counts": {
            config.SMART_DIMENSION_LABELS[dimension]: int(
                (
                    summary_frame[smart_column_name(dimension)]
                    == config.SMART_VERDICT_NOT_MET
                ).sum()
            )
            for dimension in config.SMART_DIMENSIONS
        }
        if analysed_count
        else {},
        "smart_axis_to_check_counts": {
            config.SMART_DIMENSION_LABELS[dimension]: int(
                (
                    summary_frame[smart_column_name(dimension)]
                    == config.SMART_VERDICT_TO_CHECK
                ).sum()
            )
            for dimension in config.SMART_DIMENSIONS
        }
        if analysed_count
        else {},
        "severity_counts": value_counts(findings_frame, "Severity"),
        "category_counts": value_counts(findings_frame, "Category"),
        "rule_counts": value_counts(findings_frame, "Rule_ID"),
    }

    return {
        "summary": summary_frame,
        "findings": findings_frame,
        "diagnostics": diagnostics,
    }


# ============================================================
# Préparation des constats pour le LLM
# ============================================================

def build_llm_findings(
    requirement_id: str,
    findings_frame: pd.DataFrame,
    max_evidence_per_rule: int = 5,
) -> list[dict[str, Any]]:
    """
    Regroupe les occurrences par règle avant l'appel au LLM.

    C'est un point important de fiabilité. Le prompt demande au
    modèle d'évaluer chaque constat une seule fois par
    identifiant de règle. Si le même identifiant est envoyé
    plusieurs fois, parce qu'un mot vague revient dans une
    exigence longue, le modèle renvoie des évaluations en
    doublon et le contrôle de cohérence rejette toute la
    réponse. Une règle correspond donc à un constat unique,
    accompagné de toutes ses preuves.
    """

    if findings_frame.empty:
        return []

    selected = findings_frame[
        findings_frame["Requirement_ID"].astype(str)
        == str(requirement_id)
    ]

    if selected.empty:
        return []

    grouped: dict[str, dict[str, Any]] = {}

    for _, row in selected.iterrows():
        rule_id = clean_value(row.get("Rule_ID"))

        if not rule_id:
            continue

        if rule_id not in grouped:
            grouped[rule_id] = {
                "rule_id": rule_id,
                "category": clean_value(row.get("Category")),
                # L'axe SMART mis en défaut est transmis au
                # modèle : il situe le constat sans l'obliger à
                # deviner la grille de lecture.
                "smart_dimension": clean_value(
                    row.get("SMART_Dimension")
                ),
                "severity": clean_value(row.get("Severity")),
                "evidence": [],
                "occurrence_count": 0,
                "explanation": clean_value(row.get("Explanation")),
            }

        entry = grouped[rule_id]
        entry["occurrence_count"] += 1

        evidence = clean_value(row.get("Evidence"))

        if (
            evidence
            and evidence not in entry["evidence"]
            and len(entry["evidence"]) < max_evidence_per_rule
        ):
            entry["evidence"].append(evidence)

    return list(grouped.values())
