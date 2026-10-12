# ============================================================
# Analyse contextuelle des exigences avec Ollama
# ============================================================

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Any

import pandas as pd

try:
    import ollama
except ImportError as error:
    raise ImportError(
        "Le package Python 'ollama' n'est pas installé. "
        "Installe-le avec : python -m pip install ollama"
    ) from error


# ============================================================
# Configuration
# ============================================================

DEFAULT_MODEL = "qwen2.5:3b"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"

ALLOWED_DECISIONS = {
    "CONFIRMED",
    "PARTIALLY_CONFIRMED",
    "FALSE_POSITIVE",
    "NEEDS_EXPERT_REVIEW",
    "ERROR",
}

DEFAULT_LLM_CATEGORIES = {
    "AMBIGUITY",
    "NOT_VERIFIABLE",
    "POTENTIALLY_NON_ATOMIC",
    "UNDEFINED_CONDITION",
    "UNDEFINED_REFERENCE",
    "UNDEFINED_QUANTITY",
    "WEAK_OBLIGATION",
    "MISSING_ACTOR",
    "MISSING_UNIT_OR_LIMIT",
    "MISSING_TOLERANCE",
    "MISSING_VERIFICATION_CRITERIA",
}

LLM_RESULT_COLUMNS = [
    "ID",
    "Original_Text",
    "ObjectType",
    "Triggered_Rules",
    "Rule_Evidence",
    "LLM_Analyzed",
    "LLM_Model",
    "LLM_Decision",
    "LLM_Confirmed_Findings",
    "LLM_Rejected_Findings",
    "LLM_Missing_Information",
    "LLM_Clarification_Questions",
    "LLM_Proposed_Rewrite",
    "LLM_Risk_Recommended",
    "LLM_Risk_Title",
    "LLM_Risk_Cause",
    "LLM_Risk_Event",
    "LLM_Risk_Consequences",
    "LLM_Processing_Time_s",
    "LLM_Prompt_Tokens",
    "LLM_Generated_Tokens",
    "LLM_Tokens_Per_Second",
    "LLM_Error",
    "LLM_Raw_Response",
]


# ============================================================
# Modèles de données
# ============================================================

@dataclass(frozen=True)
class LLMSettings:
    """Paramètres utilisés pour les appels Ollama."""

    model: str = DEFAULT_MODEL
    host: str = DEFAULT_OLLAMA_HOST
    temperature: float = 0.1
    num_ctx: int = 4096
    num_predict: int = 400
    seed: int = 42
    keep_alive: str = "30m"


@dataclass
class LLMRiskDraft:
    """Brouillon de risque proposé par le LLM."""

    title: str = ""
    cause: str = ""
    event: str = ""
    consequences: list[str] = field(default_factory=list)


@dataclass
class LLMAnalysis:
    """Résultat structuré de l'analyse LLM."""

    requirement_id: str
    original_text: str
    object_type: str
    triggered_rules: list[str]
    rule_evidence: list[str]
    analyzed: bool
    model: str
    decision: str
    confirmed_findings: list[dict[str, str]] = field(default_factory=list)
    rejected_findings: list[dict[str, str]] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    clarification_questions: list[str] = field(default_factory=list)
    proposed_rewrite: str = ""
    risk_recommended: bool = False
    risk_draft: LLMRiskDraft = field(default_factory=LLMRiskDraft)
    processing_time_seconds: float = 0.0
    prompt_tokens: int = 0
    generated_tokens: int = 0
    tokens_per_second: float = 0.0
    error: str = ""
    raw_response: str = ""

    def to_row(self) -> dict[str, Any]:
        """Convertit le résultat en une ligne compatible avec pandas."""

        return {
            "ID": self.requirement_id,
            "Original_Text": self.original_text,
            "ObjectType": self.object_type,
            "Triggered_Rules": " | ".join(self.triggered_rules),
            "Rule_Evidence": " | ".join(self.rule_evidence),
            "LLM_Analyzed": "YES" if self.analyzed else "NO",
            "LLM_Model": self.model,
            "LLM_Decision": self.decision,
            "LLM_Confirmed_Findings": json.dumps(
                self.confirmed_findings,
                ensure_ascii=False,
            ),
            "LLM_Rejected_Findings": json.dumps(
                self.rejected_findings,
                ensure_ascii=False,
            ),
            "LLM_Missing_Information": " | ".join(
                self.missing_information
            ),
            "LLM_Clarification_Questions": " | ".join(
                self.clarification_questions
            ),
            "LLM_Proposed_Rewrite": self.proposed_rewrite,
            "LLM_Risk_Recommended": (
                "YES" if self.risk_recommended else "NO"
            ),
            "LLM_Risk_Title": self.risk_draft.title,
            "LLM_Risk_Cause": self.risk_draft.cause,
            "LLM_Risk_Event": self.risk_draft.event,
            "LLM_Risk_Consequences": " | ".join(
                self.risk_draft.consequences
            ),
            "LLM_Processing_Time_s": self.processing_time_seconds,
            "LLM_Prompt_Tokens": self.prompt_tokens,
            "LLM_Generated_Tokens": self.generated_tokens,
            "LLM_Tokens_Per_Second": self.tokens_per_second,
            "LLM_Error": self.error,
            "LLM_Raw_Response": self.raw_response,
        }


# ============================================================
# Fonctions utilitaires
# ============================================================

def normalize_text(value: Any) -> str:
    """Convertit une valeur en texte nettoyé."""

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip()


def split_pipe_values(value: Any) -> list[str]:
    """Transforme une chaîne séparée par | en liste sans doublons."""

    text = normalize_text(value)

    if not text:
        return []

    values: list[str] = []
    seen: set[str] = set()

    for item in text.split("|"):
        cleaned_item = item.strip()

        if cleaned_item and cleaned_item not in seen:
            seen.add(cleaned_item)
            values.append(cleaned_item)

    return values


def ensure_string_list(value: Any) -> list[str]:
    """Convertit une valeur JSON en liste de chaînes nettoyées."""

    if value is None:
        return []

    if isinstance(value, str):
        return [value.strip()] if value.strip() else []

    if not isinstance(value, list):
        return [str(value).strip()] if str(value).strip() else []

    result: list[str] = []

    for item in value:
        item_text = normalize_text(item)
        if item_text:
            result.append(item_text)

    return result


def ensure_finding_list(value: Any) -> list[dict[str, str]]:
    """Normalise une liste de constats confirmés ou rejetés."""

    if not isinstance(value, list):
        return []

    result: list[dict[str, str]] = []

    for item in value:
        if isinstance(item, dict):
            result.append(
                {
                    "rule_id": normalize_text(item.get("rule_id")),
                    "evidence": normalize_text(item.get("evidence")),
                    "reason": normalize_text(item.get("reason")),
                }
            )
        else:
            result.append(
                {
                    "rule_id": "",
                    "evidence": "",
                    "reason": normalize_text(item),
                }
            )

    return result


def get_response_value(response: Any, key: str, default: Any = None) -> Any:
    """Lit une métrique sur un objet Ollama ou un dictionnaire."""

    if isinstance(response, dict):
        return response.get(key, default)

    return getattr(response, key, default)


def get_response_content(response: Any) -> str:
    """Extrait le contenu textuel d'une réponse Ollama."""

    if isinstance(response, dict):
        message = response.get("message", {})
        if isinstance(message, dict):
            return normalize_text(message.get("content"))
        return normalize_text(getattr(message, "content", ""))

    message = getattr(response, "message", None)

    if isinstance(message, dict):
        return normalize_text(message.get("content"))

    return normalize_text(getattr(message, "content", ""))


def parse_json_response(raw_response: str) -> dict[str, Any]:
    """Analyse la réponse JSON, avec retrait éventuel d'un bloc Markdown."""

    cleaned_response = raw_response.strip()

    if cleaned_response.startswith("```"):
        lines = cleaned_response.splitlines()

        if lines and lines[0].strip().lower() in {
            "```json",
            "```",
        }:
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        cleaned_response = "\n".join(lines).strip()

    try:
        parsed = json.loads(cleaned_response)
    except json.JSONDecodeError as error:
        raise ValueError(
            "Le LLM n'a pas retourné un JSON valide. "
            f"Erreur : {error}"
        ) from error

    if not isinstance(parsed, dict):
        raise ValueError(
            "La réponse JSON du LLM doit être un objet et non une liste."
        )

    return parsed
# ============================================================

# ============================================================
def ensure_assessment_list(
    value: Any,
) -> list[dict[str, Any]]:
    """
    Normalise les évaluations produites par le LLM.
    """

    if not isinstance(value, list):
        return []

    assessments: list[dict[str, Any]] = []

    for item in value:
        if not isinstance(item, dict):
            continue

        issue_present = item.get("issue_present")

        if isinstance(issue_present, str):
            issue_present = (
                issue_present.strip().lower() == "true"
            )

        if not isinstance(issue_present, bool):
            issue_present = None

        assessments.append(
            {
                "rule_id": normalize_text(
                    item.get("rule_id")
                ),
                "evidence": normalize_text(
                    item.get("evidence")
                ),
                "issue_present": issue_present,
                "reason": normalize_text(
                    item.get("reason")
                ),
            }
        )

    return assessments

# ============================================================

# ============================================================

def calculate_decision(
    assessments: list[dict[str, Any]],
    expected_rule_ids: set[str],
) -> str:
    """
    Calcule la décision globale sans la demander au LLM.
    """

    if not assessments:
        return "NEEDS_EXPERT_REVIEW"

    assessed_rule_ids = {
        assessment["rule_id"]
        for assessment in assessments
        if assessment["rule_id"]
    }

    if assessed_rule_ids != expected_rule_ids:
        return "NEEDS_EXPERT_REVIEW"

    assessment_values = [
        assessment["issue_present"]
        for assessment in assessments
    ]

    if any(
        value is None
        for value in assessment_values
    ):
        return "NEEDS_EXPERT_REVIEW"

    confirmed_count = sum(
        value is True
        for value in assessment_values
    )

    rejected_count = sum(
        value is False
        for value in assessment_values
    )

    if confirmed_count > 0 and rejected_count == 0:
        return "CONFIRMED"

    if confirmed_count > 0 and rejected_count > 0:
        return "PARTIALLY_CONFIRMED"

    if confirmed_count == 0 and rejected_count > 0:
        return "FALSE_POSITIVE"

    return "NEEDS_EXPERT_REVIEW"


# ============================================================
# Client Ollama et contrôles de disponibilité
# ============================================================

class LLMAnalyzer:
    """Client chargé d'analyser les exigences avec Ollama."""

    def __init__(self, settings: LLMSettings | None = None) -> None:
        self.settings = settings or LLMSettings()
        self.client = ollama.Client(host=self.settings.host)

    def health_check(self) -> dict[str, Any]:
        """Vérifie qu'Ollama répond et que le modèle est installé."""

        try:
            response = self.client.list()
        except Exception as error:
            raise ConnectionError(
                f"Impossible de contacter Ollama sur {self.settings.host}. "
                "Vérifie que le service Ollama est démarré. "
                f"Détail : {error}"
            ) from error

        if isinstance(response, dict):
            models = response.get("models", [])
        else:
            models = getattr(response, "models", [])

        installed_models: list[str] = []

        for model in models:
            if isinstance(model, dict):
                model_name = model.get("model") or model.get("name")
            else:
                model_name = (
                    getattr(model, "model", None)
                    or getattr(model, "name", None)
                )

            if model_name:
                installed_models.append(str(model_name))

        model_available = self.settings.model in installed_models

        if not model_available and ":" not in self.settings.model:
            model_available = any(
                model_name.startswith(f"{self.settings.model}:")
                for model_name in installed_models
            )

        return {
            "ollama_accessible": True,
            "model": self.settings.model,
            "model_available": model_available,
            "installed_models": installed_models,
        }

        @staticmethod
    def build_system_prompt() -> str:
        """
        Construit les instructions générales de revue qualité.
        """

        return (
            "You are a domain-independent requirements quality "
            "review assistant. "

            "You review customer requirements from any engineering "
            "domain, including software, hardware, mechanical systems, "
            "operations, maintenance, safety, cybersecurity, services, "
            "documentation, and contractual deliverables. "

            "Evaluate requirement quality, not the technical merit of "
            "the requested solution. "

            "A rule-engine finding is only a review signal. "
            "It may be correct, partially relevant, or a false positive. "

            "For every supplied finding, decide whether the quality "
            "problem described by the rule is present in the specific "
            "requirement context. "

            "Set issue_present to true when the stated quality defect "
            "is genuinely present. "

            "Set issue_present to false only when that quality defect "
            "is absent in the current context. "

            "Assess the requirement using these general dimensions: "
            "obligation clarity, responsible actor, required action, "
            "affected object, scope, applicability conditions, trigger, "
            "quantification, units, tolerances, verification criteria, "
            "atomicity, completeness, references, feasibility, and "
            "internal consistency. "

            "Do not assume that every requirement needs a time limit, "
            "a trigger event, a load condition, or an operating condition. "
            "Identify only information that is relevant and necessary "
            "for the specific requirement. "

            "Do not reuse concepts from unrelated examples. "

            "Do not invent values, thresholds, tolerances, units, "
            "standards, document versions, actors, dates, technical "
            "solutions, commitments, verification methods, or customer "
            "intentions. "

            "Unknown information must remain in descriptive "
            "square-bracket placeholders. "

            "Every placeholder must name the exact missing information. "

            "Preserve the original intent and level of abstraction. "
            "Do not introduce implementation details unless they already "
            "exist in the requirement. "

            "If one statement contains multiple independently verifiable "
            "obligations, propose splitting it into numbered requirement "
            "statements. "

            "A proposed rewrite is a draft requiring human validation. "
            "A proposed risk is also a draft requiring human validation. "

            "Return exactly one valid JSON object, with no Markdown and "
            "no commentary outside the JSON."
        )
    
    @staticmethod
    def build_user_prompt(
        requirement_id: str,
        original_text: str,
        object_type: str,
        findings: list[dict[str, str]],
    ) -> str:
        """
        Construit un prompt structuré pour analyser une exigence.

        Le LLM évalue chaque anomalie indépendamment.
        La décision globale sera ensuite calculée par Python.
        """

        expected_schema = {
            "findings_assessment": [
                {
                    "rule_id": "string",
                    "evidence": "string",
                    "issue_present": True,
                    "reason": "string",
                }
            ],
            "missing_information": [
                "string"
            ],
            "clarification_questions": [
                "string"
            ],
            "proposed_rewrite": (
                "one faithful requirement statement "
                "with descriptive placeholders"
            ),
            "risk_recommended": False,
            "risk_draft": {
                "title": "string",
                "cause": "string",
                "event": "string",
                "consequences": [
                    "string"
                ],
            },
        }

        payload = {
            "requirement_id": requirement_id,
            "object_type": object_type,
            "original_requirement": original_text,
            "rule_engine_findings": findings,
        }

        input_json = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )

        schema_json = json.dumps(
            expected_schema,
            ensure_ascii=False,
            indent=2,
        )

        return (
            "Review the customer requirement and every rule-engine "
            "finding provided below.\n\n"

            "INPUT:\n"
            f"{input_json}\n\n"

            "ASSESSMENT RULES:\n"
            "1. Evaluate every rule-engine finding independently.\n"

            "2. For each finding, set issue_present to true when the "
            "quality problem described by the rule is genuinely present "
            "in the requirement.\n"

            "3. Set issue_present to false only when the quality problem "
            "described by the rule is absent in this specific context.\n"

            "4. The reason must explain why the issue is present or absent. "
            "The reason must be logically consistent with issue_present.\n"

            "5. Example: if the evidence is 'rapidly' and the requirement "
            "does not provide a measurable time limit, issue_present must "
            "be true because the wording is not objectively verifiable.\n"

            "6. Example: if the evidence is 'should' and the statement is "
            "intended to express a mandatory customer requirement, "
            "issue_present must be true because 'should' creates a weak "
            "obligation.\n"

            "7. Assess every supplied rule_id exactly once.\n"

            "8. Do not omit any supplied rule_id.\n"

            "9. Do not create or return rule IDs that were not supplied "
            "in rule_engine_findings.\n\n"

            "MISSING INFORMATION AND CLARIFICATION:\n"
            "10. Identify only information that is genuinely missing from "
            "the original requirement.\n"

            "11. Do not treat information already present in the original "
            "requirement as missing.\n"

            "12. Write precise clarification questions that can be shared "
            "with the customer after human validation.\n"

            "13. Every clarification question must relate directly to a "
            "confirmed issue or missing information.\n"

            "14. Do not generate generic questions that are irrelevant to "
            "this specific requirement.\n\n"

            "REWRITE RULES:\n"
            "15. Propose one faithful rewrite of the requirement.\n"

            "16. Preserve the original purpose and contractual meaning.\n"

            "17. Do not invent values, thresholds, standards, actors, "
            "dates, technical solutions, operating conditions, or customer "
            "commitments.\n"

            "18. Use descriptive square-bracket placeholders for all "
            "unknown information.\n"

            "19. Each placeholder must explicitly describe the missing "
            "information. For example, use "
            "[MAXIMUM RESPONSE TIME TO BE CONFIRMED] rather than "
            "[VALUE TO BE CONFIRMED].\n"

            "20. If a weak obligation such as 'should' is confirmed, do "
            "not retain the same weak wording in the proposed rewrite.\n"

            "21. Use 'shall' only when the mandatory intent is established "
            "by the requirement context.\n"

            "22. If the obligation level cannot be established, use a "
            "descriptive placeholder such as "
            "[OBLIGATION LEVEL TO BE CONFIRMED].\n"

            "23. Write a grammatically complete requirement statement.\n"

            "24. For wording such as 'respond rapidly', use a structure "
            "similar to: 'The system shall respond within "
            "[MAXIMUM RESPONSE TIME TO BE CONFIRMED] after "
            "[TRIGGER EVENT TO BE DEFINED] under "
            "[OPERATING CONDITIONS TO BE DEFINED].'\n\n"

            "RISK RULES:\n"
            "25. Set risk_recommended to true only when the unresolved "
            "issue can reasonably affect interpretation, verification, "
            "acceptance, safety, cost, or schedule.\n"

            "26. Do not recommend a formal risk for every minor wording "
            "issue.\n"

            "27. If risk_recommended is false, return empty strings for "
            "the risk title, cause and event, and return an empty list "
            "for consequences.\n"

            "28. If risk_recommended is true, the risk must remain a draft "
            "requiring human validation.\n"

            "29. The risk cause must describe the unresolved requirement "
            "quality problem.\n"

            "30. The risk event must describe what may happen because of "
            "that unresolved problem.\n"

            "31. The consequences must describe plausible project or "
            "acceptance impacts without exaggeration.\n\n"

            "OUTPUT RULES:\n"
            "32. Return exactly one valid JSON object.\n"

            "33. Do not use Markdown code fences.\n"

            "34. Do not write explanations before or after the JSON.\n"

            "35. Use JSON booleans true and false for issue_present and "
            "risk_recommended.\n"

            "36. Follow this JSON structure exactly:\n"
            f"{schema_json}"
        )
    def analyze_requirement(
        self,
        requirement_id: str,
        original_text: str,
        object_type: str,
        findings: list[dict[str, str]],
    ) -> LLMAnalysis:
        """
        Analyse une exigence avec Ollama.

        Le LLM évalue chaque finding avec issue_present = true ou false.
        La décision globale est ensuite calculée par Python.
        La méthode retourne toujours un objet LLMAnalysis exploitable,
        même si l'appel au modèle échoue.
        """

        requirement_id = normalize_text(requirement_id)
        original_text = normalize_text(original_text)
        object_type = normalize_text(object_type)

        triggered_rules = [
            normalize_text(finding.get("rule_id"))
            for finding in findings
            if normalize_text(finding.get("rule_id"))
        ]

        rule_evidence = [
            normalize_text(finding.get("evidence"))
            for finding in findings
            if normalize_text(finding.get("evidence"))
        ]

        result = LLMAnalysis(
            requirement_id=requirement_id,
            original_text=original_text,
            object_type=object_type,
            triggered_rules=triggered_rules,
            rule_evidence=rule_evidence,
            analyzed=False,
            model=self.settings.model,
            decision="ERROR",
        )

        if not original_text:
            result.error = "Requirement text is empty."
            return result

        if not findings:
            result.decision = "NEEDS_EXPERT_REVIEW"
            result.error = "No rule-engine finding was provided."
            return result

        expected_rule_ids = {
            normalize_text(finding.get("rule_id"))
            for finding in findings
            if normalize_text(finding.get("rule_id"))
        }

        if not expected_rule_ids:
            result.decision = "NEEDS_EXPERT_REVIEW"
            result.error = "No valid rule ID was provided."
            return result

        user_prompt = self.build_user_prompt(
            requirement_id=requirement_id,
            original_text=original_text,
            object_type=object_type,
            findings=findings,
        )

        started_at = perf_counter()

        try:
            response = self.client.chat(
                model=self.settings.model,
                messages=[
                    {
                        "role": "system",
                        "content": self.build_system_prompt(),
                    },
                    {
                        "role": "user",
                        "content": user_prompt,
                    },
                ],
                format="json",
                options={
                    "temperature": self.settings.temperature,
                    "num_ctx": self.settings.num_ctx,
                    "num_predict": self.settings.num_predict,
                    "seed": self.settings.seed,
                },
                keep_alive=self.settings.keep_alive,
            )

            raw_response = get_response_content(response)

            if not raw_response:
                raise ValueError(
                    "Ollama returned an empty response."
                )

            parsed = parse_json_response(raw_response)

            # ------------------------------------------------
            # Lecture des évaluations produites par le LLM
            # ------------------------------------------------

            assessments = ensure_assessment_list(
                parsed.get("findings_assessment")
            )

            if not assessments:
                raise ValueError(
                    "The LLM did not return any finding assessment."
                )

            returned_rule_ids = [
                assessment["rule_id"]
                for assessment in assessments
                if assessment["rule_id"]
            ]

            returned_rule_id_set = set(returned_rule_ids)

            # ------------------------------------------------
            # Contrôle des doublons
            # ------------------------------------------------

            duplicate_rule_ids = {
                rule_id
                for rule_id in returned_rule_ids
                if returned_rule_ids.count(rule_id) > 1
            }

            if duplicate_rule_ids:
                raise ValueError(
                    "Duplicate rule IDs returned by the LLM: "
                    + ", ".join(sorted(duplicate_rule_ids))
                )

            # ------------------------------------------------
            # Contrôle des règles inconnues
            # ------------------------------------------------

            unknown_rule_ids = (
                returned_rule_id_set - expected_rule_ids
            )

            if unknown_rule_ids:
                raise ValueError(
                    "Unknown rule IDs returned by the LLM: "
                    + ", ".join(sorted(unknown_rule_ids))
                )

            # ------------------------------------------------
            # Contrôle des règles non évaluées
            # ------------------------------------------------

            missing_rule_ids = (
                expected_rule_ids - returned_rule_id_set
            )

            if missing_rule_ids:
                raise ValueError(
                    "Rule IDs not assessed by the LLM: "
                    + ", ".join(sorted(missing_rule_ids))
                )

            # ------------------------------------------------
            # Contrôle des valeurs issue_present
            # ------------------------------------------------

            invalid_assessment_ids = [
                assessment["rule_id"]
                for assessment in assessments
                if assessment["issue_present"] is None
            ]

            if invalid_assessment_ids:
                raise ValueError(
                    "Invalid issue_present value for rule IDs: "
                    + ", ".join(sorted(invalid_assessment_ids))
                )

            # ------------------------------------------------
            # Calcul déterministe de la décision globale
            # ------------------------------------------------

            decision = calculate_decision(
                assessments=assessments,
                expected_rule_ids=expected_rule_ids,
            )

            if decision not in ALLOWED_DECISIONS - {"ERROR"}:
                raise ValueError(
                    f"Calculated decision is not allowed: {decision!r}."
                )

            # ------------------------------------------------
            # Construction des findings confirmés et rejetés
            # ------------------------------------------------

            confirmed_findings = [
                {
                    "rule_id": assessment["rule_id"],
                    "evidence": assessment["evidence"],
                    "reason": assessment["reason"],
                }
                for assessment in assessments
                if assessment["issue_present"] is True
            ]

            rejected_findings = [
                {
                    "rule_id": assessment["rule_id"],
                    "evidence": assessment["evidence"],
                    "reason": assessment["reason"],
                }
                for assessment in assessments
                if assessment["issue_present"] is False
            ]

            # ------------------------------------------------
            # Lecture du brouillon de risque
            # ------------------------------------------------

            risk_data = parsed.get("risk_draft", {})

            if risk_data is None:
                risk_data = {}

            if not isinstance(risk_data, dict):
                raise ValueError(
                    "The field risk_draft must be a JSON object or null."
                )

            risk_recommended_value = parsed.get(
                "risk_recommended",
                False,
            )

            if isinstance(risk_recommended_value, bool):
                risk_recommended = risk_recommended_value
            elif isinstance(risk_recommended_value, str):
                normalized_risk_value = (
                    risk_recommended_value.strip().lower()
                )

                if normalized_risk_value == "true":
                    risk_recommended = True
                elif normalized_risk_value == "false":
                    risk_recommended = False
                else:
                    raise ValueError(
                        "The field risk_recommended must be "
                        "true or false."
                    )
            else:
                raise ValueError(
                    "The field risk_recommended must be a boolean."
                )

            risk_draft = LLMRiskDraft(
                title=normalize_text(
                    risk_data.get("title")
                ),
                cause=normalize_text(
                    risk_data.get("cause")
                ),
                event=normalize_text(
                    risk_data.get("event")
                ),
                consequences=ensure_string_list(
                    risk_data.get("consequences")
                ),
            )

            # Si aucun risque n'est recommandé, les champs
            # de risque sont volontairement vidés.
            if not risk_recommended:
                risk_draft = LLMRiskDraft()

            # ------------------------------------------------
            # Lecture des métriques Ollama
            # ------------------------------------------------

            generated_tokens = int(
                get_response_value(
                    response,
                    "eval_count",
                    0,
                )
                or 0
            )

            prompt_tokens = int(
                get_response_value(
                    response,
                    "prompt_eval_count",
                    0,
                )
                or 0
            )

            eval_duration_ns = int(
                get_response_value(
                    response,
                    "eval_duration",
                    0,
                )
                or 0
            )

            tokens_per_second = 0.0

            if eval_duration_ns > 0:
                eval_duration_seconds = (
                    eval_duration_ns / 1_000_000_000
                )

                tokens_per_second = (
                    generated_tokens
                    / eval_duration_seconds
                )

            # ------------------------------------------------
            # Alimentation du résultat final
            # ------------------------------------------------

            result.analyzed = True
            result.decision = decision
            result.confirmed_findings = confirmed_findings
            result.rejected_findings = rejected_findings

            result.missing_information = ensure_string_list(
                parsed.get("missing_information")
            )

            result.clarification_questions = ensure_string_list(
                parsed.get("clarification_questions")
            )

            result.proposed_rewrite = normalize_text(
                parsed.get("proposed_rewrite")
            )

            result.risk_recommended = risk_recommended
            result.risk_draft = risk_draft

            result.prompt_tokens = prompt_tokens
            result.generated_tokens = generated_tokens

            result.tokens_per_second = round(
                tokens_per_second,
                2,
            )

            result.raw_response = raw_response
            result.error = ""

        except Exception as error:
            result.analyzed = False
            result.decision = "ERROR"

            result.error = (
                f"{type(error).__name__}: {error}"
            )

        finally:
            result.processing_time_seconds = round(
                perf_counter() - started_at,
                2,
            )

        return result
# ============================================================
# Sélection des exigences candidates
# ============================================================

def select_llm_candidates(
    summary_dataframe: pd.DataFrame,
    limit: int | None = 10,
    severities: set[str] | None = None,
    categories: set[str] | None = None,
) -> pd.DataFrame:
    """Sélectionne les exigences pertinentes pour l'analyse LLM."""

    required_columns = {
        "ID",
        "Object Heading and Object Text",
        "ObjectType",
        "Issue_Count",
        "Issue_Categories",
        "Highest_Severity",
    }

    missing_columns = sorted(
        required_columns.difference(summary_dataframe.columns)
    )

    if missing_columns:
        raise ValueError(
            "Colonnes absentes pour la sélection LLM : "
            + ", ".join(missing_columns)
        )

    selected_severities = severities or {"HIGH", "CRITICAL"}
    selected_categories = categories or DEFAULT_LLM_CATEGORIES

    candidates = summary_dataframe[
        (summary_dataframe["Issue_Count"] > 0)
        & summary_dataframe["Highest_Severity"].isin(
            selected_severities
        )
    ].copy()

    def has_selected_category(value: Any) -> bool:
        row_categories = set(split_pipe_values(value))
        return bool(row_categories.intersection(selected_categories))

    candidates = candidates[
        candidates["Issue_Categories"].apply(has_selected_category)
    ].copy()

    severity_order = {
        "CRITICAL": 0,
        "HIGH": 1,
        "MEDIUM": 2,
        "LOW": 3,
        "NONE": 4,
    }

    candidates["_severity_order"] = candidates[
        "Highest_Severity"
    ].map(severity_order).fillna(99)

    candidates = candidates.sort_values(
        by=["_severity_order", "Issue_Count"],
        ascending=[True, False],
    ).drop(columns=["_severity_order"])

    if limit is not None and limit >= 0:
        candidates = candidates.head(limit)

    return candidates.reset_index(drop=True)


# ============================================================
# Analyse en lot
# ============================================================

def build_findings_for_requirement(
    requirement_id: str,
    findings_dataframe: pd.DataFrame,
) -> list[dict[str, str]]:
    """Récupère les constats déterministes d'une exigence."""

    if findings_dataframe.empty:
        return []

    required_columns = {
        "requirement_id",
        "rule_id",
        "category",
        "severity",
        "evidence",
        "explanation",
    }

    missing_columns = sorted(
        required_columns.difference(findings_dataframe.columns)
    )

    if missing_columns:
        raise ValueError(
            "Colonnes absentes du tableau Findings : "
            + ", ".join(missing_columns)
        )

    selected = findings_dataframe[
        findings_dataframe["requirement_id"].astype(str)
        == str(requirement_id)
    ]

    result: list[dict[str, str]] = []

    for _, row in selected.iterrows():
        result.append(
            {
                "rule_id": normalize_text(row.get("rule_id")),
                "category": normalize_text(row.get("category")),
                "severity": normalize_text(row.get("severity")),
                "evidence": normalize_text(row.get("evidence")),
                "explanation": normalize_text(row.get("explanation")),
            }
        )

    return result


def analyze_candidates_with_llm(
    candidates: pd.DataFrame,
    findings_dataframe: pd.DataFrame,
    settings: LLMSettings | None = None,
    stop_on_error: bool = False,
    show_progress: bool = True,
) -> dict[str, Any]:
    """Analyse un lot sans interrompre les autres lignes en cas d'erreur."""

    analyzer = LLMAnalyzer(settings=settings)
    health = analyzer.health_check()

    if not health["model_available"]:
        raise ValueError(
            f"Le modèle {analyzer.settings.model!r} n'est pas installé. "
            f"Exécute : ollama pull {analyzer.settings.model}"
        )

    started_at = perf_counter()
    analyses: list[LLMAnalysis] = []
    total = len(candidates)

    for position, (_, row) in enumerate(
        candidates.iterrows(),
        start=1,
    ):
        requirement_id = normalize_text(row.get("ID"))
        original_text = normalize_text(
            row.get("Object Heading and Object Text")
        )
        object_type = normalize_text(row.get("ObjectType"))

        if show_progress:
            print(
                f"LLM {position}/{total} - {requirement_id}"
            )

        findings = build_findings_for_requirement(
            requirement_id=requirement_id,
            findings_dataframe=findings_dataframe,
        )

        analysis = analyzer.analyze_requirement(
            requirement_id=requirement_id,
            original_text=original_text,
            object_type=object_type,
            findings=findings,
        )

        analyses.append(analysis)

        if stop_on_error and analysis.error:
            raise RuntimeError(
                f"Échec de l'analyse LLM pour {requirement_id}: "
                f"{analysis.error}"
            )

    dataframe = pd.DataFrame(
        [analysis.to_row() for analysis in analyses],
        columns=LLM_RESULT_COLUMNS,
    )

    elapsed_seconds = perf_counter() - started_at

    successful_count = sum(
        1 for analysis in analyses if analysis.analyzed
    )
    error_count = len(analyses) - successful_count
    total_generated_tokens = sum(
        analysis.generated_tokens for analysis in analyses
    )

    diagnostics = {
        "model": analyzer.settings.model,
        "host": analyzer.settings.host,
        "candidate_count": total,
        "successful_count": successful_count,
        "error_count": error_count,
        "total_generated_tokens": total_generated_tokens,
        "total_time_seconds": round(elapsed_seconds, 2),
        "average_time_seconds": round(
            elapsed_seconds / total,
            2,
        ) if total else 0.0,
        "decision_counts": (
            dataframe["LLM_Decision"].value_counts().to_dict()
            if not dataframe.empty
            else {}
        ),
    }

    return {
        "dataframe": dataframe,
        "analyses": analyses,
        "diagnostics": diagnostics,
        "health": health,
    }


# ============================================================
# Fusion avec le résumé déterministe
# ============================================================

def merge_llm_results(
    summary_dataframe: pd.DataFrame,
    llm_dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Ajoute les colonnes LLM au résumé sans écraser les règles."""

    if llm_dataframe.empty:
        result = summary_dataframe.copy()

        for column in LLM_RESULT_COLUMNS:
            if column not in {"ID", "Original_Text", "ObjectType"}:
                if column not in result.columns:
                    result[column] = ""

        return result

    llm_to_merge = llm_dataframe.drop(
        columns=["Original_Text", "ObjectType"],
        errors="ignore",
    )

    if llm_to_merge["ID"].duplicated().any():
        duplicate_ids = sorted(
            llm_to_merge.loc[
                llm_to_merge["ID"].duplicated(keep=False),
                "ID",
            ].astype(str).unique()
        )
        raise ValueError(
            "Résultats LLM dupliqués pour les ID : "
            + ", ".join(duplicate_ids)
        )

    return summary_dataframe.merge(
        llm_to_merge,
        on="ID",
        how="left",
        validate="one_to_one",
    )


# ============================================================
# Affichage des diagnostics
# ============================================================

def display_llm_diagnostics(result: dict[str, Any]) -> None:
    """Affiche un résumé lisible de l'analyse LLM."""

    diagnostics = result["diagnostics"]

    print("\n" + "=" * 65)
    print("DIAGNOSTIC DE L'ANALYSE LLM")
    print("=" * 65)
    print(f"Modèle                    : {diagnostics['model']}")
    print(f"Candidats                 : {diagnostics['candidate_count']}")
    print(f"Analyses réussies         : {diagnostics['successful_count']}")
    print(f"Erreurs                   : {diagnostics['error_count']}")
    print(
        "Tokens générés          : "
        f"{diagnostics['total_generated_tokens']}"
    )
    print(
        "Temps total             : "
        f"{diagnostics['total_time_seconds']} s"
    )
    print(
        "Temps moyen             : "
        f"{diagnostics['average_time_seconds']} s"
    )

    print("\nDécisions :")
    for decision, count in diagnostics["decision_counts"].items():
        print(f"  - {decision}: {count}")


# ============================================================
# Test autonome
# ============================================================

def main() -> None:
    """Teste le module avec une exigence et deux alertes."""

    settings = LLMSettings(model=DEFAULT_MODEL)
    analyzer = LLMAnalyzer(settings=settings)

    print(analyzer.health_check())

    findings = [
        {
            "rule_id": "WEAK-001",
            "category": "WEAK_OBLIGATION",
            "severity": "MEDIUM",
            "evidence": "should",
            "explanation": (
                "The word should may express a recommendation rather "
                "than a mandatory requirement."
            ),
        },
        {
            "rule_id": "AMB-001",
            "category": "AMBIGUITY",
            "severity": "HIGH",
            "evidence": "rapidly",
            "explanation": (
                "The expected response time is not measurable."
            ),
        },
    ]

    result = analyzer.analyze_requirement(
        requirement_id="TEST-001",
        original_text="The system should respond rapidly.",
        object_type="Technical Req",
        findings=findings,
    )

    print(json.dumps(asdict(result), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
