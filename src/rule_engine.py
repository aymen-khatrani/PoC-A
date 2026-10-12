# ============================================================
# Moteur d'analyse des exigences
# ============================================================

from __future__ import annotations

from dataclasses import dataclass, asdict
from time import perf_counter
from typing import Any

import pandas as pd

try:
    from src.rule_loader import Rule
except ModuleNotFoundError:
    from rule_loader import Rule


# ============================================================
# Configuration
# ============================================================

ID_COLUMN = "ID"
TEXT_COLUMN = "Object Heading and Object Text"
TYPE_COLUMN = "ObjectType"

ANALYSABLE_OBJECT_TYPES = {
    "Technical Req",
    "Non-Technical Req",
}

SEVERITY_RANK = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}

STATUS_RANK = {
    "PRE_ANALYSIS_OK": 1,
    "REVIEW_REQUIRED": 2,
    "CLARIFICATION_REQUIRED": 3,
    "NON_ANALYSABLE": 4,
}

FINDING_COLUMNS = [
    "requirement_id",
    "original_text",
    "object_type",
    "source_excel_row",
    "rule_id",
    "category",
    "severity",
    "evidence",
    "start_position",
    "end_position",
    "explanation",
    "clarification_question",
    "rewrite_template",
]

SUMMARY_COLUMNS = [
    "ID",
    "Object Heading and Object Text",
    "ObjectType",
    "Source_Excel_Row",
    "Quality_Status",
    "Issue_Count",
    "Issue_Categories",
    "Triggered_Rules",
    "Evidence",
    "Highest_Severity",
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
    """Représente une anomalie détectée sur une exigence."""

    requirement_id: str
    original_text: str
    object_type: str
    source_excel_row: int | None
    rule_id: str
    category: str
    severity: str
    evidence: str
    start_position: int
    end_position: int
    explanation: str
    clarification_question: str
    rewrite_template: str

    def to_dict(self) -> dict[str, Any]:
        """Convertit l'anomalie en dictionnaire exportable."""

        return asdict(self)


# ============================================================
# Fonctions utilitaires
# ============================================================

def normalize_value(value: Any) -> str:
    """Convertit une valeur en texte nettoyé."""

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip()


def unique_preserve_order(values: list[str]) -> list[str]:
    """Supprime les doublons en conservant l'ordre initial."""

    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        cleaned_value = normalize_value(value)

        if cleaned_value and cleaned_value not in seen:
            seen.add(cleaned_value)
            result.append(cleaned_value)

    return result


def join_unique(values: list[str], separator: str = " | ") -> str:
    """Assemble des valeurs uniques dans une seule chaîne."""

    return separator.join(unique_preserve_order(values))


def get_highest_severity(findings: list[Finding]) -> str:
    """Retourne la gravité la plus élevée parmi les anomalies."""

    if not findings:
        return "NONE"

    return max(
        (finding.severity for finding in findings),
        key=lambda severity: SEVERITY_RANK.get(severity, 0),
    )


def determine_quality_status(findings: list[Finding]) -> str:
    """Calcule le statut qualité à partir des anomalies détectées."""

    if not findings:
        return "PRE_ANALYSIS_OK"

    highest_severity = get_highest_severity(findings)

    if highest_severity in {"HIGH", "CRITICAL"}:
        return "CLARIFICATION_REQUIRED"

    return "REVIEW_REQUIRED"


def should_assess_risk(findings: list[Finding]) -> bool:
    """Indique si un risque doit être évalué par un humain."""

    risk_categories = {
        "NOT_VERIFIABLE",
        "INCOMPLETE",
        "UNDEFINED_CONDITION",
        "UNDEFINED_REFERENCE",
        "MISSING_UNIT_OR_LIMIT",
        "MISSING_TOLERANCE",
        "MISSING_VERIFICATION_CRITERIA",
    }

    return any(
        finding.severity in {"HIGH", "CRITICAL"}
        or finding.category in risk_categories
        for finding in findings
    )


def build_risk_draft(
    requirement_id: str,
    findings: list[Finding],
) -> str:
    """Construit un brouillon de risque sans inventer de valeur."""

    if not findings or not should_assess_risk(findings):
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
        f"Title: Requirement quality risk for {requirement_id}\n"
        f"Cause: The requirement contains potential quality issues "
        f"in the following categories: {categories}. "
        f"Detected evidence: {evidence}.\n"
        "Risk event: The customer and the project team may interpret "
        "or verify the requirement differently.\n"
        "Potential consequence: Rework, acceptance dispute, cost "
        "increase, or schedule delay.\n"
        "Status: DRAFT - HUMAN VALIDATION REQUIRED"
    )


def validate_requirement_columns(dataframe: pd.DataFrame) -> None:
    """Vérifie la présence des trois colonnes nécessaires."""

    required_columns = {
        ID_COLUMN,
        TEXT_COLUMN,
        TYPE_COLUMN,
    }

    missing_columns = sorted(
        required_columns.difference(dataframe.columns)
    )

    if missing_columns:
        raise ValueError(
            "Colonnes obligatoires absentes du DataFrame : "
            + ", ".join(missing_columns)
        )


# ============================================================
# Analyse d'une exigence
# ============================================================

def analyse_text_with_rules(
    requirement_id: str,
    original_text: str,
    object_type: str,
    source_excel_row: int | None,
    rules: list[Rule],
) -> list[Finding]:
    """Applique toutes les règles actives au texte d'une exigence."""

    findings: list[Finding] = []

    for rule in rules:
        if not rule.enabled:
            continue

        matches = rule.find_matches(original_text)

        for match in matches:
            findings.append(
                Finding(
                    requirement_id=requirement_id,
                    original_text=original_text,
                    object_type=object_type,
                    source_excel_row=source_excel_row,
                    rule_id=rule.rule_id,
                    category=rule.category,
                    severity=rule.severity,
                    evidence=match["evidence"],
                    start_position=match["start_position"],
                    end_position=match["end_position"],
                    explanation=rule.explanation,
                    clarification_question=rule.clarification_question,
                    rewrite_template=rule.rewrite_template,
                )
            )

    return findings


def analyse_requirement_row(
    row: pd.Series,
    rules: list[Rule],
) -> tuple[dict[str, Any], list[Finding]]:
    """Analyse une ligne et retourne son résumé et ses anomalies."""

    started_at = perf_counter()

    requirement_id = normalize_value(row.get(ID_COLUMN))
    original_text = normalize_value(row.get(TEXT_COLUMN))
    object_type = normalize_value(row.get(TYPE_COLUMN))

    source_excel_row_value = row.get("Source_Excel_Row")
    source_excel_row: int | None = None

    if source_excel_row_value is not None:
        try:
            if not pd.isna(source_excel_row_value):
                source_excel_row = int(source_excel_row_value)
        except (TypeError, ValueError):
            source_excel_row = None

    non_analysable_reasons: list[str] = []

    if not requirement_id:
        non_analysable_reasons.append("Missing ID")

    if not original_text:
        non_analysable_reasons.append("Missing requirement text")

    if not object_type:
        non_analysable_reasons.append("Missing ObjectType")

    findings: list[Finding] = []

    if non_analysable_reasons:
        quality_status = "NON_ANALYSABLE"
    elif object_type not in ANALYSABLE_OBJECT_TYPES:
        quality_status = "NON_ANALYSABLE"
        non_analysable_reasons.append(
            f"Unsupported ObjectType: {object_type}"
        )
    else:
        findings = analyse_text_with_rules(
            requirement_id=requirement_id,
            original_text=original_text,
            object_type=object_type,
            source_excel_row=source_excel_row,
            rules=rules,
        )
        quality_status = determine_quality_status(findings)

    highest_severity = get_highest_severity(findings)
    risk_to_assess = should_assess_risk(findings)

    if non_analysable_reasons:
        explanations = " | ".join(non_analysable_reasons)
    else:
        explanations = join_unique(
            [finding.explanation for finding in findings]
        )

    elapsed_ms = round((perf_counter() - started_at) * 1000, 3)

    summary = {
        "ID": requirement_id,
        "Object Heading and Object Text": original_text,
        "ObjectType": object_type,
        "Source_Excel_Row": source_excel_row,
        "Quality_Status": quality_status,
        "Issue_Count": len(findings),
        "Issue_Categories": join_unique(
            [finding.category for finding in findings]
        ),
        "Triggered_Rules": join_unique(
            [finding.rule_id for finding in findings]
        ),
        "Evidence": join_unique(
            [finding.evidence for finding in findings]
        ),
        "Highest_Severity": highest_severity,
        "Explanations": explanations,
        "Clarification_Questions": join_unique(
            [finding.clarification_question for finding in findings]
        ),
        "Proposed_Rewrites": join_unique(
            [finding.rewrite_template for finding in findings]
        ),
        "Risk_To_Assess": "YES" if risk_to_assess else "NO",
        "Risk_Draft": build_risk_draft(
            requirement_id=requirement_id,
            findings=findings,
        ),
        "Analysis_Time_ms": elapsed_ms,
    }

    return summary, findings


# ============================================================
# Analyse d'un DataFrame complet
# ============================================================

def analyse_requirements(
    requirements: pd.DataFrame,
    rules: list[Rule],
    include_non_requirements: bool = False,
) -> dict[str, Any]:
    """
    Analyse un DataFrame contenant les colonnes ID, texte et type.

    Par défaut, seuls Technical Req et Non-Technical Req sont inclus.
    """

    validate_requirement_columns(requirements)

    started_at = perf_counter()
    working_dataframe = requirements.copy()

    if not include_non_requirements:
        normalized_types = (
            working_dataframe[TYPE_COLUMN]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        working_dataframe = working_dataframe[
            normalized_types.isin(ANALYSABLE_OBJECT_TYPES)
        ].copy()

    summaries: list[dict[str, Any]] = []
    all_findings: list[Finding] = []

    for _, row in working_dataframe.iterrows():
        summary, row_findings = analyse_requirement_row(
            row=row,
            rules=rules,
        )

        summaries.append(summary)
        all_findings.extend(row_findings)

    summary_dataframe = pd.DataFrame(
        summaries,
        columns=SUMMARY_COLUMNS,
    )

    findings_dataframe = pd.DataFrame(
        [finding.to_dict() for finding in all_findings],
        columns=FINDING_COLUMNS,
    )

    total_time_seconds = perf_counter() - started_at

    status_counts = (
        summary_dataframe["Quality_Status"]
        .value_counts()
        .to_dict()
        if not summary_dataframe.empty
        else {}
    )

    severity_counts = (
        findings_dataframe["severity"]
        .value_counts()
        .to_dict()
        if not findings_dataframe.empty
        else {}
    )

    category_counts = (
        findings_dataframe["category"]
        .value_counts()
        .to_dict()
        if not findings_dataframe.empty
        else {}
    )

    rule_counts = (
        findings_dataframe["rule_id"]
        .value_counts()
        .to_dict()
        if not findings_dataframe.empty
        else {}
    )

    diagnostics = {
        "input_row_count": int(len(requirements)),
        "analysed_row_count": int(len(summary_dataframe)),
        "finding_count": int(len(findings_dataframe)),
        "rule_count": int(len(rules)),
        "requirements_with_findings": int(
            (summary_dataframe["Issue_Count"] > 0).sum()
        ) if not summary_dataframe.empty else 0,
        "requirements_without_findings": int(
            (summary_dataframe["Issue_Count"] == 0).sum()
        ) if not summary_dataframe.empty else 0,
        "risk_assessment_count": int(
            (summary_dataframe["Risk_To_Assess"] == "YES").sum()
        ) if not summary_dataframe.empty else 0,
        "total_time_seconds": round(total_time_seconds, 3),
        "average_time_ms_per_requirement": round(
            (total_time_seconds * 1000) / len(summary_dataframe),
            3,
        ) if len(summary_dataframe) > 0 else 0.0,
        "status_counts": status_counts,
        "severity_counts": severity_counts,
        "category_counts": category_counts,
        "rule_counts": rule_counts,
    }

    return {
        "summary": summary_dataframe,
        "findings": findings_dataframe,
        "diagnostics": diagnostics,
    }


# ============================================================
# Affichage des résultats
# ============================================================

def display_analysis_diagnostics(result: dict[str, Any]) -> None:
    """Affiche le diagnostic général de l'analyse."""

    diagnostics = result["diagnostics"]

    print("\n" + "=" * 65)
    print("DIAGNOSTIC DE L'ANALYSE")
    print("=" * 65)

    print(f"Lignes reçues                  : {diagnostics['input_row_count']}")
    print(f"Exigences analysées            : {diagnostics['analysed_row_count']}")
    print(f"Règles chargées                : {diagnostics['rule_count']}")
    print(f"Anomalies détectées            : {diagnostics['finding_count']}")
    print(
        "Exigences avec anomalie       : "
        f"{diagnostics['requirements_with_findings']}"
    )
    print(
        "Exigences sans anomalie       : "
        f"{diagnostics['requirements_without_findings']}"
    )
    print(
        "Risques à évaluer             : "
        f"{diagnostics['risk_assessment_count']}"
    )
    print(
        "Temps total                   : "
        f"{diagnostics['total_time_seconds']} s"
    )
    print(
        "Temps moyen par exigence      : "
        f"{diagnostics['average_time_ms_per_requirement']} ms"
    )

    print("\nRépartition par statut :")
    for status, count in diagnostics["status_counts"].items():
        print(f"  - {status}: {count}")

    print("\nRépartition par gravité :")
    for severity, count in diagnostics["severity_counts"].items():
        print(f"  - {severity}: {count}")

    print("\nPrincipales catégories :")
    sorted_categories = sorted(
        diagnostics["category_counts"].items(),
        key=lambda item: item[1],
        reverse=True,
    )

    for category, count in sorted_categories[:10]:
        print(f"  - {category}: {count}")


def display_analysis_sample(
    result: dict[str, Any],
    limit: int = 10,
) -> None:
    """Affiche un aperçu des exigences signalées."""

    summary = result["summary"]

    print("\n" + "=" * 65)
    print(f"APERÇU DES {limit} PREMIÈRES EXIGENCES SIGNALÉES")
    print("=" * 65)

    if summary.empty:
        print("Aucune exigence analysée.")
        return

    flagged = summary[summary["Issue_Count"] > 0]

    if flagged.empty:
        print("Aucune anomalie détectée.")
        return

    columns = [
        "ID",
        "ObjectType",
        "Quality_Status",
        "Issue_Count",
        "Triggered_Rules",
        "Evidence",
    ]

    print(
        flagged[columns]
        .head(limit)
        .to_string(index=False, max_colwidth=70)
    )


# ============================================================
# Test autonome
# ============================================================

def main() -> None:
    """Test simple du moteur avec quelques exigences."""

    try:
        from src.rule_loader import load_rules
    except ModuleNotFoundError:
        from rule_loader import load_rules

    test_requirements = pd.DataFrame(
        [
            {
                "ID": "TEST-001",
                "Object Heading and Object Text": (
                    "The system should respond rapidly."
                ),
                "ObjectType": "Technical Req",
                "Source_Excel_Row": 2,
            },
            {
                "ID": "TEST-002",
                "Object Heading and Object Text": (
                    "The system shall respond within 2 seconds."
                ),
                "ObjectType": "Technical Req",
                "Source_Excel_Row": 3,
            },
            {
                "ID": "TEST-003",
                "Object Heading and Object Text": (
                    "The interface shall be intuitive and user-friendly."
                ),
                "ObjectType": "Non-Technical Req",
                "Source_Excel_Row": 4,
            },
        ]
    )

    rules_result = load_rules("rules/rules_en.csv")

    analysis_result = analyse_requirements(
        requirements=test_requirements,
        rules=rules_result["rules"],
    )

    display_analysis_diagnostics(analysis_result)
    display_analysis_sample(analysis_result)


if __name__ == "__main__":
    main()
