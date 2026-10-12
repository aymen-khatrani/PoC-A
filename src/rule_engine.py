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
from src.text_utils import clean_value


FINDING_COLUMNS = [
    "Requirement_ID",
    "Rule_ID",
    "Category",
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
    "Issue_Count",
    "Occurrence_Count",
    "Highest_Severity",
    "Issue_Categories",
    "Triggered_Rules",
    "Evidence",
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
    severity: str
    evidence: str
    start_position: int
    end_position: int
    occurrence_index: int
    explanation: str
    clarification_question: str
    rewrite_template: str
    source_excel_row: int | None

    def to_row(self) -> dict[str, Any]:
        """Convertit l'anomalie en ligne de rapport."""

        values = asdict(self)

        return {
            "Requirement_ID": values["requirement_id"],
            "Rule_ID": values["rule_id"],
            "Category": values["category"],
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


def should_assess_risk(
    findings: list[Finding],
    settings: EngineSettings,
) -> bool:
    """
    Indique si un brouillon de risque mérite d'être proposé.

    Deux conditions suffisent, mais aucune n'est automatique :
    une gravité élevée, ou plusieurs catégories sensibles
    touchées en même temps. Proposer un risque pour chaque
    alerte reviendrait à n'en signaler aucun.
    """

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
) -> str:
    """
    Construit un brouillon de risque factuel.

    Aucune valeur, aucun seuil et aucune conséquence chiffrée
    n'est inventé : le texte ne reprend que les catégories
    détectées et les preuves relevées.
    """

    if not findings:
        return ""

    categories = join_unique(
        [finding.category for finding in findings],
        separator=", ",
    )

    evidence = join_unique(
        [finding.evidence for finding in findings],
        separator=", ",
    )

    return (
        f"Title: Requirement quality risk on {requirement_id}\n"
        "Cause: The requirement shows potential quality issues "
        f"in the following categories: {categories}. "
        f"Detected evidence: {evidence}.\n"
        "Risk event: The customer and the project team may "
        "interpret or verify the requirement differently.\n"
        "Potential consequence: Rework, acceptance dispute, cost "
        "increase or schedule delay.\n"
        "Status: DRAFT - HUMAN VALIDATION REQUIRED"
    )


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

    source_excel_row = row.get(SOURCE_ROW)

    try:
        source_excel_row = (
            int(source_excel_row)
            if source_excel_row is not None
            and not pd.isna(source_excel_row)
            else None
        )
    except (TypeError, ValueError):
        source_excel_row = None

    if not text:
        findings: list[Finding] = []
        quality_status = config.STATUS_NOT_ANALYSED
    else:
        findings = analyse_text(
            requirement_id=requirement_id,
            text=text,
            rules=rules,
            source_excel_row=source_excel_row,
        )
        quality_status = determine_quality_status(
            findings,
            settings,
        )

    risk_to_assess = should_assess_risk(findings, settings)

    summary = {
        CANONICAL_ID: requirement_id,
        CANONICAL_TEXT: text,
        CANONICAL_TYPE: object_type,
        SOURCE_ROW: source_excel_row,
        SOURCE_SHEET: clean_value(row.get(SOURCE_SHEET)),
        "Quality_Status": quality_status,
        "Quality_Score": compute_quality_score(findings),
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
            build_risk_draft(requirement_id, findings)
            if risk_to_assess
            else ""
        ),
        "Analysis_Time_ms": round(
            (perf_counter() - started_at) * 1000,
            3,
        ),
    }

    return summary, findings


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
