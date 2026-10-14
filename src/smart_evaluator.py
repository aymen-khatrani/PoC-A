# ============================================================
# Évaluation SMART et singularité d'une exigence
# ============================================================
#
# Ce module traduit les constats du moteur de règles en une
# lecture d'ingénierie système :
#
#     - les cinq axes SMART, qui qualifient la rédaction ;
#     - la singularité, qui dit si l'énoncé porte une seule
#       exigence ou plusieurs.
#
# Il ne détecte rien de nouveau sur le fond : chaque verdict
# s'appuie sur des constats déjà prouvés, ou sur un comptage
# structurel du texte. Rien n'est réécrit, rien n'est inventé.
#
# Le module ne connaît ni pandas ni le format du rapport. Il
# reçoit des constats et retourne un verdict, ce qui le rend
# testable seul.
#
# ============================================================

from __future__ import annotations

import re
from typing import Any, Iterable, Sequence

from src import config


# Les constats sont manipulés par attributs plutôt que par un
# type importé : le moteur de règles dépend de ce module, et
# l'inverse créerait un import circulaire. Un constat doit
# exposer rule_id, severity, smart_dimension, evidence et
# clarification_question.


# ============================================================
# Motifs compilés une seule fois
# ============================================================

def build_obligation_pattern() -> re.Pattern[str]:
    """
    Compile le motif des verbes d'obligation comptés.

    Les formulations les plus longues sont placées en premier,
    pour que « is required to » ne soit pas compté comme deux
    correspondances.
    """

    keywords = sorted(
        config.SINGULARITY_OBLIGATION_KEYWORDS,
        key=len,
        reverse=True,
    )

    alternatives = "|".join(
        re.escape(keyword).replace(r"\ ", r"\s+")
        for keyword in keywords
    )

    return re.compile(
        rf"\b(?:{alternatives})\b",
        flags=re.IGNORECASE,
    )


OBLIGATION_PATTERN = build_obligation_pattern()

LIST_MARKER_PATTERN = re.compile(
    config.SINGULARITY_LIST_MARKER_PATTERN,
    flags=re.IGNORECASE | re.MULTILINE,
)

ADDITIVE_PATTERN = re.compile(
    config.SINGULARITY_ADDITIVE_PATTERN,
    flags=re.IGNORECASE,
)

CITATION_PATTERN = re.compile(
    config.SINGULARITY_CITATION_PATTERN,
    flags=re.IGNORECASE,
)

# Fin d'une proposition : c'est jusque-là que porte une
# citation ouverte par « which states that ».
CLAUSE_END_PATTERN = re.compile(r"[.;!?\n]")


# ============================================================
# Utilitaires
# ============================================================

def severity_rank(severity: Any) -> int:
    """Retourne le rang numérique d'une gravité."""

    return config.SEVERITY_RANK.get(str(severity).upper(), 0)


def highest_severity(severities: Iterable[Any]) -> str:
    """Retourne la gravité la plus élevée, ou NONE."""

    ranked = sorted(severities, key=severity_rank, reverse=True)

    for severity in ranked:
        if severity_rank(severity):
            return str(severity).upper()

    return "NONE"


def unique_values(values: Iterable[Any]) -> list[str]:
    """Déduplique en conservant l'ordre d'apparition."""

    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        text = "" if value is None else str(value).strip()

        if text and text not in seen:
            seen.add(text)
            result.append(text)

    return result


def finding_dimension(finding: Any) -> str:
    """
    Retourne l'axe porté par un constat.

    Un constat produit par un catalogue plus ancien, sans axe,
    reste exploitable : sa catégorie décide, puis l'axe par
    défaut.
    """

    declared = str(
        getattr(finding, "smart_dimension", "") or ""
    ).upper()

    if declared in config.SMART_ALLOWED_AXES:
        return declared

    category = str(getattr(finding, "category", "") or "").upper()

    return config.CATEGORY_TO_SMART_DIMENSION.get(
        category,
        config.SMART_DEFAULT_DIMENSION,
    )


# ============================================================
# Singularité de l'exigence
# ============================================================

def citation_spans(text: str) -> list[tuple[int, int]]:
    """
    Localise les passages qui citent une obligation externe.

    Une citation court du marqueur jusqu'à la fin de sa
    proposition. Tout verbe d'obligation qui s'y trouve rappelle
    une exigence définie ailleurs, et ne doit donc pas être
    compté comme une exigence de plus.
    """

    spans: list[tuple[int, int]] = []

    for match in CITATION_PATTERN.finditer(text):
        end_match = CLAUSE_END_PATTERN.search(text, match.end())
        end = end_match.start() if end_match else len(text)

        spans.append((match.start(), end))

    return spans


def count_obligations(text: str) -> list[str]:
    """
    Retourne les verbes d'obligation qui créent une exigence.

    Les verbes situés dans une citation sont ignorés : ils
    renvoient à une obligation déjà exprimée ailleurs.
    """

    if not text:
        return []

    cleaned = str(text)
    spans = citation_spans(cleaned)

    def is_quoted(position: int) -> bool:
        return any(
            start <= position < end
            for start, end in spans
        )

    return [
        match.group(0)
        for match in OBLIGATION_PATTERN.finditer(cleaned)
        if not is_quoted(match.start())
    ]


def count_list_markers(text: str) -> int:
    """Compte les puces et numérotations en début de ligne."""

    if not text:
        return 0

    return len(LIST_MARKER_PATTERN.findall(str(text)))


def evaluate_singularity(
    text: str,
    findings: Sequence[Any] = (),
    settings: config.SingularitySettings | None = None,
) -> dict[str, Any]:
    """
    Vérifie qu'un énoncé ne porte qu'une seule exigence.

    Le principe est simple : une exigence, une obligation, une
    vérification. Dès qu'un énoncé contient deux obligations,
    l'une peut être satisfaite et l'autre non, sans qu'aucun
    statut ne puisse le dire. L'exigence doit alors être
    scindée.

    Trois signaux sont examinés, du plus probant au plus
    prudent :

        1. plusieurs verbes d'obligation ;
        2. une énumération à puces ou numérotée ;
        3. un connecteur additif, un chapelet de
           points-virgules, ou un constat de non-atomicité du
           catalogue.

    Les deux premiers concluent à « à scinder ». Le troisième
    demande seulement une vérification humaine : le découpage
    n'est jamais décidé à la place de l'ingénieur.

    Deux garde-fous évitent de relever à tort le statut d'une
    exigence correcte : une obligation citée depuis un autre
    document n'est pas comptée, et des verbes d'obligation
    différents dans un même énoncé ramènent le verdict à « à
    vérifier ».

    Retour :
        {
            "status":                   verdict,
            "obligation_count":         nombre d'obligations,
            "estimated_count":          exigences estimées,
            "evidence":                 preuves relevées,
            "reasons":                  motifs du verdict,
        }
    """

    settings = settings or config.SingularitySettings()
    cleaned = "" if text is None else str(text).strip()

    if not cleaned:
        return {
            "status": config.SINGULARITY_NOT_ASSESSED,
            "obligation_count": 0,
            "estimated_count": 0,
            "evidence": [],
            "reasons": [],
        }

    obligations = count_obligations(cleaned)
    obligation_count = len(obligations)
    list_marker_count = count_list_markers(cleaned)
    semicolon_count = cleaned.count(";")
    additive_matches = ADDITIVE_PATTERN.findall(cleaned)

    atomicity_findings = [
        finding
        for finding in findings
        if finding_dimension(finding) == config.SINGULARITY_AXIS
    ]

    evidence: list[str] = []
    reasons: list[str] = []
    status = config.SINGULARITY_UNIQUE
    estimated_count = 1

    if obligation_count > settings.maximum_obligations:
        distinct_modals = {
            obligation.strip().lower()
            for obligation in obligations
        }

        # Verbes identiques : deux obligations rédigées
        # ensemble. Verbes différents : plus souvent un style
        # mêlé ou une citation, donc prudence.
        mixed_modals = (
            settings.require_same_modal
            and len(distinct_modals) > 1
        )

        status = (
            config.SINGULARITY_TO_CHECK
            if mixed_modals
            else config.SINGULARITY_TO_SPLIT
        )
        estimated_count = obligation_count

        reasons.append(
            f"{obligation_count} verbes d'obligation dans un "
            "seul énoncé"
            + (
                ", mais de formes différentes : vérifier qu'il "
                "ne s'agit pas d'un rappel d'obligation"
                if mixed_modals
                else ""
            )
        )
        evidence.extend(obligations)

    if list_marker_count >= settings.minimum_list_markers:
        status = config.SINGULARITY_TO_SPLIT
        estimated_count = max(estimated_count, list_marker_count)

        reasons.append(
            f"énumération de {list_marker_count} éléments "
            "rassemblés dans une seule ligne"
        )

    if status != config.SINGULARITY_TO_SPLIT:
        if additive_matches:
            status = config.SINGULARITY_TO_CHECK

            reasons.append(
                "connecteur additif : une obligation peut en "
                "cacher une seconde"
            )
            evidence.extend(additive_matches)

        elif semicolon_count >= settings.minimum_semicolons:
            status = config.SINGULARITY_TO_CHECK

            reasons.append(
                f"{semicolon_count} points-virgules : l'énoncé "
                "ressemble à une liste"
            )

        elif atomicity_findings:
            status = config.SINGULARITY_TO_CHECK

            reasons.append(
                "constat de non-atomicité : "
                + ", ".join(
                    unique_values(
                        finding.rule_id
                        for finding in atomicity_findings
                    )
                )
            )
            evidence.extend(
                finding.evidence
                for finding in atomicity_findings
            )

    return {
        "status": status,
        "obligation_count": obligation_count,
        "estimated_count": estimated_count,
        "evidence": unique_values(evidence),
        "reasons": reasons,
    }


# ============================================================
# Axes SMART
# ============================================================

def evaluate_dimensions(
    findings: Sequence[Any],
    text_is_analysable: bool = True,
) -> dict[str, dict[str, Any]]:
    """
    Évalue les cinq axes SMART à partir des constats.

    Un axe sans constat est déclaré conforme. C'est une
    conformité de pré-analyse, pas un satisfecit : elle signifie
    que le catalogue déterministe n'a rien trouvé à reprocher à
    l'exigence sur cet axe. L'avis d'ingénierie reste requis, et
    la page de synthèse le dit.

    L'axe de singularité est traité à part par
    evaluate_singularity : il n'entre pas dans le score SMART.
    """

    grouped: dict[str, list[Any]] = {
        dimension: []
        for dimension in config.SMART_DIMENSIONS
    }

    for finding in findings:
        dimension = finding_dimension(finding)

        if dimension in grouped:
            grouped[dimension].append(finding)

    assessment: dict[str, dict[str, Any]] = {}

    for dimension, dimension_findings in grouped.items():
        if not text_is_analysable:
            verdict = config.SMART_VERDICT_NOT_ASSESSED
            severity = "NONE"

        elif not dimension_findings:
            verdict = config.SMART_VERDICT_OK
            severity = "NONE"

        else:
            severity = highest_severity(
                finding.severity
                for finding in dimension_findings
            )
            verdict = config.SEVERITY_TO_SMART_VERDICT.get(
                severity,
                config.SMART_VERDICT_TO_CHECK,
            )

        assessment[dimension] = {
            "verdict": verdict,
            "highest_severity": severity,
            "rule_ids": unique_values(
                finding.rule_id
                for finding in dimension_findings
            ),
            "evidence": unique_values(
                finding.evidence
                for finding in dimension_findings
            ),
            "questions": unique_values(
                finding.clarification_question
                for finding in dimension_findings
            ),
            "rewrites": unique_values(
                getattr(finding, "rewrite_template", "")
                for finding in dimension_findings
            ),
        }

    return assessment


def compute_smart_score(
    dimensions: dict[str, dict[str, Any]],
) -> int:
    """
    Calcule un score SMART de 0 à 100.

    Les cinq axes pèsent le même poids : vingt points chacun.
    Un axe non conforme perd tout, un axe à vérifier perd la
    moitié. Le score ne remplace pas la lecture des axes, il
    sert à trier le lot par priorité.
    """

    return sum(
        config.SMART_VERDICT_POINTS.get(
            dimensions[dimension]["verdict"],
            0,
        )
        for dimension in config.SMART_DIMENSIONS
    )


def dimensions_with_verdict(
    dimensions: dict[str, dict[str, Any]],
    verdict: str,
) -> list[str]:
    """Liste les axes portant un verdict donné, dans l'ordre."""

    return [
        dimension
        for dimension in config.SMART_DIMENSIONS
        if dimensions[dimension]["verdict"] == verdict
    ]


def format_smart_profile(
    dimensions: dict[str, dict[str, Any]],
) -> str:
    """
    Résume les cinq axes en une chaîne compacte.

    Exemple : « S:OK M:KO A:OK R:OK T:? ». Une seule colonne
    suffit alors à lire le profil d'une exigence.
    """

    return " ".join(
        "{letter}:{symbol}".format(
            letter=config.SMART_DIMENSION_LETTERS[dimension],
            symbol=config.SMART_VERDICT_SYMBOLS.get(
                dimensions[dimension]["verdict"],
                "-",
            ),
        )
        for dimension in config.SMART_DIMENSIONS
    )


# ============================================================
# Action recommandée
# ============================================================

def build_recommended_action(
    dimensions: dict[str, dict[str, Any]],
    singularity: dict[str, Any],
    text_is_analysable: bool = True,
) -> str:
    """
    Formule l'action attendue, en une ligne.

    L'ordre des priorités est celui du travail réel : on scinde
    d'abord, car le découpage change les exigences à corriger ;
    on corrige ensuite les axes non conformes ; on vérifie
    enfin les axes douteux.
    """

    if not text_is_analysable:
        return "Compléter le texte de l'exigence : il est vide."

    if singularity["status"] == config.SINGULARITY_TO_SPLIT:
        return (
            "Scinder en "
            f"{singularity['estimated_count']} exigences "
            "unitaires avant toute correction de rédaction."
        )

    not_met = dimensions_with_verdict(
        dimensions,
        config.SMART_VERDICT_NOT_MET,
    )

    if not_met:
        return "Corriger : " + ", ".join(
            config.SMART_DIMENSION_ACTIONS[dimension]
            for dimension in not_met
        ) + "."

    to_check = dimensions_with_verdict(
        dimensions,
        config.SMART_VERDICT_TO_CHECK,
    )

    if to_check:
        return "Vérifier : " + ", ".join(
            config.SMART_DIMENSION_ACTIONS[dimension]
            for dimension in to_check
        ) + "."

    if singularity["status"] == config.SINGULARITY_TO_CHECK:
        return (
            "Vérifier que l'énoncé ne porte qu'une seule "
            "exigence."
        )

    return "Aucune action : revue d'ingénierie seule."


# ============================================================
# Évaluation complète d'une exigence
# ============================================================

def evaluate_requirement(
    text: str,
    findings: Sequence[Any] = (),
    settings: config.SingularitySettings | None = None,
) -> dict[str, Any]:
    """
    Évalue une exigence sur les axes SMART et la singularité.

    Retour :
        {
            "dimensions":    verdict détaillé par axe,
            "score":         score SMART de 0 à 100,
            "profile":       résumé compact des cinq axes,
            "compliant_count": axes conformes,
            "not_met":       axes non conformes,
            "to_check":      axes à vérifier,
            "singularity":   verdict de singularité,
            "action":        action recommandée,
        }
    """

    text_is_analysable = bool(
        text is not None and str(text).strip()
    )

    dimensions = evaluate_dimensions(
        findings=findings,
        text_is_analysable=text_is_analysable,
    )

    singularity = evaluate_singularity(
        text=text,
        findings=findings,
        settings=settings,
    )

    return {
        "dimensions": dimensions,
        "score": compute_smart_score(dimensions),
        "profile": format_smart_profile(dimensions),
        "compliant_count": len(
            dimensions_with_verdict(
                dimensions,
                config.SMART_VERDICT_OK,
            )
        ),
        "not_met": dimensions_with_verdict(
            dimensions,
            config.SMART_VERDICT_NOT_MET,
        ),
        "to_check": dimensions_with_verdict(
            dimensions,
            config.SMART_VERDICT_TO_CHECK,
        ),
        "singularity": singularity,
        "action": build_recommended_action(
            dimensions=dimensions,
            singularity=singularity,
            text_is_analysable=text_is_analysable,
        ),
    }
