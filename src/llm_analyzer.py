# ============================================================
# Analyse contextuelle avec un LLM local (Ollama)
# ============================================================
#
# Rôle du LLM : contextualiser et suggérer.
# Il ne détecte pas à la place des règles et ne décide pas à la
# place de l'humain.
#
# Trois principes de fiabilité :
#
# 1. la décision globale est calculée en Python à partir des
#    valeurs issue_present, jamais demandée au modèle ;
# 2. la sortie est contrainte par un schéma JSON, ce qui évite
#    la majorité des réponses tronquées ou bavardes ;
# 3. une seule reprise est tentée, avec des paramètres plus
#    stricts, puis l'erreur est retournée sans interrompre
#    le lot.
#
# Le paquet ollama est importé à la demande : le projet reste
# utilisable en mode règles seules sans l'installer.
#
# ============================================================

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Any

import pandas as pd

from src import config
from src.config import (
    CANONICAL_ID,
    CANONICAL_TEXT,
    CANONICAL_TYPE,
)
from src.rule_engine import build_llm_findings
from src.text_utils import clean_value


DEFAULT_MODEL = "qwen2.5:3b"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"

DECISION_CONFIRMED = "CONFIRMED"
DECISION_PARTIALLY_CONFIRMED = "PARTIALLY_CONFIRMED"
DECISION_FALSE_POSITIVE = "FALSE_POSITIVE"
DECISION_NEEDS_EXPERT_REVIEW = "NEEDS_EXPERT_REVIEW"
DECISION_ERROR = "ERROR"

ALLOWED_DECISIONS = {
    DECISION_CONFIRMED,
    DECISION_PARTIALLY_CONFIRMED,
    DECISION_FALSE_POSITIVE,
    DECISION_NEEDS_EXPERT_REVIEW,
    DECISION_ERROR,
}

# Identifiant du constat utilisé lorsque les règles n'ont rien
# trouvé et que l'on demande malgré tout une revue complète.
FULL_REVIEW_RULE_ID = "FULL-REVIEW"

LLM_RESULT_COLUMNS = [
    CANONICAL_ID,
    "Review_Mode",
    "LLM_Analyzed",
    "LLM_Model",
    "LLM_Decision",
    "LLM_Confirmed_Rules",
    "LLM_Rejected_Rules",
    "LLM_Confirmed_Detail",
    "LLM_Rejected_Detail",
    "LLM_Missing_Information",
    "LLM_Clarification_Questions",
    "LLM_Proposed_Rewrite",
    "LLM_Risk_Recommended",
    "LLM_Risk_Title",
    "LLM_Risk_Cause",
    "LLM_Risk_Event",
    "LLM_Risk_Consequences",
    "LLM_Attempts",
    "LLM_Processing_Time_s",
    "LLM_Prompt_Tokens",
    "LLM_Generated_Tokens",
    "LLM_Tokens_Per_Second",
    "LLM_Error",
    "LLM_Raw_Response",
]


# ============================================================
# Réglages
# ============================================================

@dataclass(frozen=True)
class LLMSettings:
    """Paramètres d'appel du modèle local."""

    model: str = DEFAULT_MODEL
    host: str = DEFAULT_OLLAMA_HOST
    temperature: float = 0.1
    num_ctx: int = 8192
    num_predict: int = 900
    repeat_penalty: float = 1.1
    seed: int = 42
    keep_alive: str = "30m"
    use_json_schema: bool = True
    max_attempts: int = 2
    # Au-delà de cette longueur, le texte envoyé au modèle est
    # tronqué pour rester dans la fenêtre de contexte. Le texte
    # original n'est jamais modifié dans le rapport.
    max_text_characters: int = 6000

    def retry_settings(self) -> LLMSettings:
        """Paramètres plus stricts pour la seconde tentative."""

        return LLMSettings(
            model=self.model,
            host=self.host,
            temperature=0.0,
            num_ctx=self.num_ctx,
            num_predict=int(self.num_predict * 1.3),
            repeat_penalty=max(self.repeat_penalty, 1.15),
            seed=self.seed,
            keep_alive=self.keep_alive,
            use_json_schema=self.use_json_schema,
            max_attempts=1,
            max_text_characters=self.max_text_characters,
        )


@dataclass
class LLMRiskDraft:
    """Brouillon de risque proposé par le modèle."""

    title: str = ""
    cause: str = ""
    event: str = ""
    consequences: list[str] = field(default_factory=list)


@dataclass
class LLMAnalysis:
    """Résultat structuré de l'analyse d'une exigence."""

    requirement_id: str
    review_mode: str
    analyzed: bool
    model: str
    decision: str
    confirmed_findings: list[dict[str, str]] = field(
        default_factory=list
    )
    rejected_findings: list[dict[str, str]] = field(
        default_factory=list
    )
    missing_information: list[str] = field(default_factory=list)
    clarification_questions: list[str] = field(
        default_factory=list
    )
    proposed_rewrite: str = ""
    risk_recommended: bool = False
    risk_draft: LLMRiskDraft = field(
        default_factory=LLMRiskDraft
    )
    attempts: int = 0
    processing_time_seconds: float = 0.0
    prompt_tokens: int = 0
    generated_tokens: int = 0
    tokens_per_second: float = 0.0
    error: str = ""
    raw_response: str = ""

    def to_row(self) -> dict[str, Any]:
        """Convertit le résultat en ligne de rapport."""

        return {
            CANONICAL_ID: self.requirement_id,
            "Review_Mode": self.review_mode,
            "LLM_Analyzed": "YES" if self.analyzed else "NO",
            "LLM_Model": self.model,
            "LLM_Decision": self.decision,
            "LLM_Confirmed_Rules": " | ".join(
                item["rule_id"]
                for item in self.confirmed_findings
                if item.get("rule_id")
            ),
            "LLM_Rejected_Rules": " | ".join(
                item["rule_id"]
                for item in self.rejected_findings
                if item.get("rule_id")
            ),
            "LLM_Confirmed_Detail": json.dumps(
                self.confirmed_findings,
                ensure_ascii=False,
            ),
            "LLM_Rejected_Detail": json.dumps(
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
            "LLM_Attempts": self.attempts,
            "LLM_Processing_Time_s": self.processing_time_seconds,
            "LLM_Prompt_Tokens": self.prompt_tokens,
            "LLM_Generated_Tokens": self.generated_tokens,
            "LLM_Tokens_Per_Second": self.tokens_per_second,
            "LLM_Error": self.error,
            "LLM_Raw_Response": self.raw_response,
        }


# ============================================================
# Lecture tolérante des réponses
# ============================================================

def get_response_value(
    response: Any,
    key: str,
    default: Any = None,
) -> Any:
    """Lit une métrique sur un dictionnaire ou un objet ollama."""

    if isinstance(response, dict):
        return response.get(key, default)

    return getattr(response, key, default)


def get_response_content(response: Any) -> str:
    """Extrait le contenu textuel d'une réponse ollama."""

    message = get_response_value(response, "message", None)

    if isinstance(message, dict):
        return clean_value(message.get("content"))

    return clean_value(getattr(message, "content", ""))


def parse_json_response(raw_response: str) -> dict[str, Any]:
    """
    Analyse la réponse JSON du modèle.

    Un bloc Markdown éventuel est retiré, et si du texte entoure
    le JSON, le premier objet complet est isolé. Cela évite de
    perdre une réponse correcte pour un simple préambule.
    """

    text = raw_response.strip()

    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].lstrip("`").strip().lower() in {
            "",
            "json",
        }:
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")

        if start == -1 or end <= start:
            raise ValueError(
                "La réponse ne contient aucun objet JSON "
                "exploitable."
            ) from None

        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as error:
            raise ValueError(
                f"JSON invalide renvoyé par le modèle : {error}"
            ) from error

    if not isinstance(parsed, dict):
        raise ValueError(
            "La réponse JSON doit être un objet, pas une liste."
        )

    return parsed


def ensure_string_list(value: Any) -> list[str]:
    """Normalise une valeur JSON en liste de chaînes."""

    if value is None:
        return []

    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []

    if not isinstance(value, list):
        cleaned = str(value).strip()
        return [cleaned] if cleaned else []

    result: list[str] = []

    for item in value:
        cleaned = clean_value(item)

        if cleaned:
            result.append(cleaned)

    return result


def parse_boolean_field(value: Any, field_name: str) -> bool:
    """Lit un booléen JSON en tolérant les variantes textuelles."""

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"true", "yes", "1"}:
            return True

        if normalized in {"false", "no", "0"}:
            return False

    raise ValueError(
        f"Le champ {field_name} doit être true ou false, "
        f"valeur reçue : {value!r}."
    )


def ensure_assessment_list(value: Any) -> list[dict[str, Any]]:
    """Normalise les évaluations de constats produites par le LLM."""

    if not isinstance(value, list):
        return []

    assessments: list[dict[str, Any]] = []

    for item in value:
        if not isinstance(item, dict):
            continue

        issue_present = item.get("issue_present")

        try:
            issue_present = parse_boolean_field(
                issue_present,
                "issue_present",
            )
        except ValueError:
            issue_present = None

        assessments.append(
            {
                "rule_id": clean_value(item.get("rule_id")),
                "issue_present": issue_present,
                "reason": clean_value(item.get("reason")),
            }
        )

    return assessments


# ============================================================
# Décision calculée en Python
# ============================================================

def calculate_decision(
    assessments: list[dict[str, Any]],
) -> str:
    """
    Déduit la décision globale des valeurs issue_present.

    La décision n'est jamais demandée au modèle : cela évitait
    déjà, dans la version précédente, qu'un constat soit rejeté
    avec une justification qui confirmait pourtant le problème.
    """

    if not assessments:
        return DECISION_NEEDS_EXPERT_REVIEW

    values = [item["issue_present"] for item in assessments]

    if any(value is None for value in values):
        return DECISION_NEEDS_EXPERT_REVIEW

    confirmed = sum(1 for value in values if value is True)
    rejected = sum(1 for value in values if value is False)

    if confirmed and not rejected:
        return DECISION_CONFIRMED

    if confirmed and rejected:
        return DECISION_PARTIALLY_CONFIRMED

    if rejected and not confirmed:
        return DECISION_FALSE_POSITIVE

    return DECISION_NEEDS_EXPERT_REVIEW


# ============================================================
# Schéma de sortie
# ============================================================

def build_response_schema(rule_ids: list[str]) -> dict[str, Any]:
    """
    Construit le schéma JSON imposé au modèle.

    Contraindre la grammaire de sortie est la façon la plus
    sûre d'éviter les réponses tronquées ou commentées :
    le modèle ne peut structurellement pas produire autre
    chose. Les identifiants de règles attendus sont injectés
    comme énumération, ce qui interdit toute règle inventée.
    """

    return {
        "type": "object",
        "properties": {
            "findings_assessment": {
                "type": "array",
                "minItems": len(rule_ids),
                "maxItems": len(rule_ids),
                "items": {
                    "type": "object",
                    "properties": {
                        "rule_id": {
                            "type": "string",
                            "enum": rule_ids,
                        },
                        "issue_present": {"type": "boolean"},
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "rule_id",
                        "issue_present",
                        "reason",
                    ],
                },
            },
            "missing_information": {
                "type": "array",
                "items": {"type": "string"},
            },
            "clarification_questions": {
                "type": "array",
                "items": {"type": "string"},
            },
            "proposed_rewrite": {"type": "string"},
            "risk_recommended": {"type": "boolean"},
            "risk_draft": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "cause": {"type": "string"},
                    "event": {"type": "string"},
                    "consequences": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "title",
                    "cause",
                    "event",
                    "consequences",
                ],
            },
        },
        "required": [
            "findings_assessment",
            "missing_information",
            "clarification_questions",
            "proposed_rewrite",
            "risk_recommended",
            "risk_draft",
        ],
    }


# ============================================================
# Construction des prompts
# ============================================================

def build_system_prompt() -> str:
    """
    Instructions générales, volontairement sans exemple métier.

    La version précédente citait un cas de temps de réponse. Le
    modèle réutilisait alors des notions de délai ou de
    déclencheur sur des exigences qui n'avaient aucun rapport.
    Les consignes restent donc abstraites.
    """

    return (
        "You are a requirements quality review assistant. "
        "You work across all engineering and contractual "
        "domains: software, hardware, mechanical, electrical, "
        "civil works, operations, maintenance, safety, "
        "cybersecurity, services, documentation and commercial "
        "deliverables.\n\n"

        "Review the quality of the wording, never the technical "
        "merit of the solution requested by the customer.\n\n"

        "A rule-engine finding is a review signal, not a "
        "verdict. It may be correct, partially relevant, or a "
        "false positive in the specific context. For each "
        "finding, decide whether the quality defect described "
        "by the rule is genuinely present in this requirement. "
        "Set issue_present to true when it is present, and "
        "false only when it is clearly absent in this "
        "context.\n\n"

        "Assess the requirement against these dimensions, and "
        "only those that are relevant to it: obligation "
        "clarity, responsible actor, required action, affected "
        "object, applicability scope, triggering conditions, "
        "quantification, units, tolerances, verification "
        "criteria, atomicity, completeness, references and "
        "internal consistency.\n\n"

        "Do not assume that every requirement needs a time "
        "limit, a trigger event, a load condition or an "
        "operating condition. Raise only information that is "
        "genuinely missing and genuinely necessary for this "
        "requirement.\n\n"

        "Never invent values, thresholds, tolerances, units, "
        "standards, document references, versions, actors, "
        "dates, technical solutions, verification methods, "
        "commitments or customer intentions. Unknown "
        "information stays inside square-bracket placeholders "
        "that name the exact missing item.\n\n"

        "Preserve the original intent and level of abstraction. "
        "Do not add implementation detail that is not already "
        "in the requirement.\n\n"

        "If a statement carries several independently "
        "verifiable obligations, propose splitting it into "
        "numbered statements.\n\n"

        "A proposed rewrite and a proposed risk are drafts "
        "requiring human validation."
    )


def build_user_prompt(
    requirement_id: str,
    requirement_text: str,
    object_type: str,
    findings: list[dict[str, Any]],
    schema: dict[str, Any],
) -> str:
    """Construit le prompt d'analyse d'une exigence."""

    payload = {
        "requirement_id": requirement_id,
        "requirement_type": object_type or "not provided",
        "original_requirement": requirement_text,
        "rule_engine_findings": findings,
    }

    return (
        "Review the customer requirement below, together with "
        "every rule-engine finding supplied.\n\n"
        "INPUT:\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\n"
        "ASSESSMENT:\n"
        "1. Assess each supplied rule_id exactly once.\n"
        "2. Never return a rule_id that was not supplied.\n"
        "3. The reason must be logically consistent with "
        "issue_present.\n"
        "4. Several evidence strings may be attached to one "
        "rule: judge the defect, not the number of "
        "occurrences.\n\n"
        "MISSING INFORMATION AND QUESTIONS:\n"
        "5. List only information absent from the original "
        "wording.\n"
        "6. Each clarification question must relate to a "
        "confirmed defect or to missing information, and must "
        "be specific enough to send to the customer after "
        "human validation.\n\n"
        "REWRITE:\n"
        "7. Produce one faithful rewrite preserving the "
        "original purpose and contractual meaning.\n"
        "8. Replace every unknown item with a descriptive "
        "square-bracket placeholder naming that item, written in "
        "upper case, for example "
        "[ACCEPTANCE CRITERION TO BE DEFINED]. A placeholder "
        "names the missing information in plain words: it is "
        "never a variable name and never a generic "
        "[VALUE TO BE CONFIRMED].\n"
        "9. Do not introduce a unit of measurement, a scale or a "
        "metric that the original wording does not already use. "
        "The unit itself is missing information and belongs "
        "inside the placeholder.\n"
        "10. Do not keep a weak obligation that you confirmed "
        "as a defect. If the obligation level cannot be "
        "established from the context, use a placeholder for "
        "it.\n"
        "11. Write a grammatically complete statement.\n\n"
        "RISK:\n"
        "12. Recommend a risk only when the unresolved defect "
        "can plausibly affect interpretation, verification, "
        "acceptance, safety, cost or schedule.\n"
        "13. If risk_recommended is false, return empty "
        "strings and an empty list in risk_draft.\n\n"
        "OUTPUT:\n"
        "14. Return exactly one JSON object matching this "
        "schema, with no Markdown and no commentary:\n"
        + json.dumps(schema, ensure_ascii=False)
    )


# ============================================================
# Constat de revue complète
# ============================================================

def build_full_review_finding() -> list[dict[str, Any]]:
    """
    Constat utilisé quand aucune règle ne s'est déclenchée.

    Il n'affirme pas qu'un défaut existe : il demande au modèle
    de trancher. Cela permet de couvrir les défauts sémantiques
    qu'une expression régulière ne peut pas voir.
    """

    return [
        {
            "rule_id": FULL_REVIEW_RULE_ID,
            "category": "FULL_CONTEXT_REVIEW",
            "severity": "MEDIUM",
            "evidence": ["complete requirement statement"],
            "occurrence_count": 1,
            "explanation": (
                "No lexical rule was triggered. Perform a full "
                "contextual quality review and set "
                "issue_present to true only if the requirement "
                "is ambiguous, incomplete, not verifiable, not "
                "atomic, weakly binding, or dependent on "
                "undefined conditions or references."
            ),
        }
    ]


# ============================================================
# Client
# ============================================================

class LLMAnalyzer:
    """Client d'analyse contextuelle basé sur Ollama."""

    def __init__(self, settings: LLMSettings | None = None) -> None:
        self.settings = settings or LLMSettings()
        self._client: Any = None

    # --------------------------------------------------------

    @property
    def client(self) -> Any:
        """Instancie le client ollama au premier besoin."""

        if self._client is not None:
            return self._client

        try:
            import ollama
        except ImportError as error:
            raise ImportError(
                "Le paquet Python 'ollama' n'est pas installé. "
                "Installe-le avec : python -m pip install ollama\n"
                "L'analyse par règles fonctionne sans ce paquet."
            ) from error

        self._client = ollama.Client(host=self.settings.host)

        return self._client

    # --------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        """Vérifie que le service répond et que le modèle existe."""

        try:
            response = self.client.list()
        except Exception as error:
            raise ConnectionError(
                "Impossible de contacter Ollama sur "
                f"{self.settings.host}. Vérifie que le service "
                f"est démarré.\nDétail : {error}"
            ) from error

        models = get_response_value(response, "models", []) or []
        installed: list[str] = []

        for model in models:
            name = get_response_value(
                model,
                "model",
                None,
            ) or get_response_value(model, "name", None)

            if name:
                installed.append(str(name))

        requested = self.settings.model
        available = requested in installed

        # "qwen2.5" doit reconnaître "qwen2.5:3b".
        if not available and ":" not in requested:
            available = any(
                name.startswith(f"{requested}:")
                for name in installed
            )

        return {
            "ollama_accessible": True,
            "host": self.settings.host,
            "model": requested,
            "model_available": available,
            "installed_models": installed,
        }

    # --------------------------------------------------------

    def call_model(
        self,
        requirement_id: str,
        requirement_text: str,
        object_type: str,
        findings: list[dict[str, Any]],
        rule_ids: list[str],
        settings: LLMSettings,
    ) -> tuple[Any, str]:
        """Effectue un appel au modèle et retourne la réponse brute."""

        schema = build_response_schema(rule_ids)

        response_format: Any = (
            schema if settings.use_json_schema else "json"
        )

        response = self.client.chat(
            model=settings.model,
            messages=[
                {
                    "role": "system",
                    "content": build_system_prompt(),
                },
                {
                    "role": "user",
                    "content": build_user_prompt(
                        requirement_id=requirement_id,
                        requirement_text=requirement_text,
                        object_type=object_type,
                        findings=findings,
                        schema=schema,
                    ),
                },
            ],
            format=response_format,
            options={
                "temperature": settings.temperature,
                "num_ctx": settings.num_ctx,
                "num_predict": settings.num_predict,
                "repeat_penalty": settings.repeat_penalty,
                "seed": settings.seed,
            },
            keep_alive=settings.keep_alive,
        )

        raw_response = get_response_content(response)

        if not raw_response:
            raise ValueError("Ollama a renvoyé une réponse vide.")

        return response, raw_response

    # --------------------------------------------------------

    def interpret_response(
        self,
        parsed: dict[str, Any],
        expected_rule_ids: set[str],
    ) -> dict[str, Any]:
        """
        Contrôle et interprète la réponse du modèle.

        Les contrôles sont volontairement stricts : une réponse
        incomplète doit produire NEEDS_EXPERT_REVIEW plutôt
        qu'une conclusion fausse.
        """

        assessments = ensure_assessment_list(
            parsed.get("findings_assessment")
        )

        if not assessments:
            raise ValueError(
                "Aucune évaluation de constat n'a été renvoyée."
            )

        returned_ids = [
            item["rule_id"]
            for item in assessments
            if item["rule_id"]
        ]

        unknown = sorted(set(returned_ids) - expected_rule_ids)

        if unknown:
            raise ValueError(
                "Règles inconnues renvoyées par le modèle : "
                + ", ".join(unknown)
            )

        # Une évaluation en doublon est fusionnée plutôt que
        # rejetée : seule la première est conservée, et la
        # réponse reste exploitable.
        deduplicated: dict[str, dict[str, Any]] = {}

        for item in assessments:
            if item["rule_id"] and item["rule_id"] not in deduplicated:
                deduplicated[item["rule_id"]] = item

        assessments = list(deduplicated.values())

        missing = sorted(expected_rule_ids - set(deduplicated))

        if missing:
            raise ValueError(
                "Règles non évaluées par le modèle : "
                + ", ".join(missing)
            )

        decision = calculate_decision(assessments)

        confirmed = [
            {
                "rule_id": item["rule_id"],
                "reason": item["reason"],
            }
            for item in assessments
            if item["issue_present"] is True
        ]

        rejected = [
            {
                "rule_id": item["rule_id"],
                "reason": item["reason"],
            }
            for item in assessments
            if item["issue_present"] is False
        ]

        risk_recommended = parse_boolean_field(
            parsed.get("risk_recommended", False),
            "risk_recommended",
        )

        risk_data = parsed.get("risk_draft") or {}

        if not isinstance(risk_data, dict):
            raise ValueError(
                "Le champ risk_draft doit être un objet JSON."
            )

        risk_draft = (
            LLMRiskDraft(
                title=clean_value(risk_data.get("title")),
                cause=clean_value(risk_data.get("cause")),
                event=clean_value(risk_data.get("event")),
                consequences=ensure_string_list(
                    risk_data.get("consequences")
                ),
            )
            if risk_recommended
            else LLMRiskDraft()
        )

        return {
            "decision": decision,
            "confirmed": confirmed,
            "rejected": rejected,
            "missing_information": ensure_string_list(
                parsed.get("missing_information")
            ),
            "clarification_questions": ensure_string_list(
                parsed.get("clarification_questions")
            ),
            "proposed_rewrite": clean_value(
                parsed.get("proposed_rewrite")
            ),
            "risk_recommended": risk_recommended,
            "risk_draft": risk_draft,
        }

    # --------------------------------------------------------

    def analyze_requirement(
        self,
        requirement_id: str,
        requirement_text: str,
        object_type: str = "",
        findings: list[dict[str, Any]] | None = None,
        review_mode: str = "",
    ) -> LLMAnalysis:
        """
        Analyse une exigence et retourne toujours un résultat
        exploitable, même en cas d'échec technique.
        """

        requirement_id = clean_value(requirement_id)
        requirement_text = clean_value(requirement_text)
        object_type = clean_value(object_type)
        findings = list(findings or [])

        if not findings:
            findings = build_full_review_finding()
            review_mode = review_mode or "FULL_CONTEXT_REVIEW"
        else:
            review_mode = review_mode or "VALIDATE_RULE_FINDINGS"

        result = LLMAnalysis(
            requirement_id=requirement_id,
            review_mode=review_mode,
            analyzed=False,
            model=self.settings.model,
            decision=DECISION_ERROR,
        )

        if not requirement_text:
            result.error = "Texte d'exigence vide."
            return result

        rule_ids = []

        for finding in findings:
            rule_id = clean_value(finding.get("rule_id"))

            if rule_id and rule_id not in rule_ids:
                rule_ids.append(rule_id)

        if not rule_ids:
            result.decision = DECISION_NEEDS_EXPERT_REVIEW
            result.error = "Aucun identifiant de règle fourni."
            return result

        truncated_text = requirement_text[
            : self.settings.max_text_characters
        ]

        started_at = perf_counter()
        attempt_settings = self.settings
        last_error = ""

        for attempt in range(1, self.settings.max_attempts + 1):
            result.attempts = attempt

            try:
                response, raw_response = self.call_model(
                    requirement_id=requirement_id,
                    requirement_text=truncated_text,
                    object_type=object_type,
                    findings=findings,
                    rule_ids=rule_ids,
                    settings=attempt_settings,
                )

                result.raw_response = raw_response

                interpreted = self.interpret_response(
                    parsed=parse_json_response(raw_response),
                    expected_rule_ids=set(rule_ids),
                )

                generated = int(
                    get_response_value(response, "eval_count", 0) or 0
                )
                prompt_tokens = int(
                    get_response_value(
                        response,
                        "prompt_eval_count",
                        0,
                    )
                    or 0
                )
                eval_duration = int(
                    get_response_value(
                        response,
                        "eval_duration",
                        0,
                    )
                    or 0
                )

                result.analyzed = True
                result.decision = interpreted["decision"]
                result.confirmed_findings = interpreted["confirmed"]
                result.rejected_findings = interpreted["rejected"]
                result.missing_information = interpreted[
                    "missing_information"
                ]
                result.clarification_questions = interpreted[
                    "clarification_questions"
                ]
                result.proposed_rewrite = interpreted[
                    "proposed_rewrite"
                ]
                result.risk_recommended = interpreted[
                    "risk_recommended"
                ]
                result.risk_draft = interpreted["risk_draft"]
                result.prompt_tokens = prompt_tokens
                result.generated_tokens = generated
                result.tokens_per_second = (
                    round(
                        generated / (eval_duration / 1_000_000_000),
                        2,
                    )
                    if eval_duration > 0
                    else 0.0
                )
                result.error = ""
                break

            except Exception as error:
                last_error = f"{type(error).__name__}: {error}"

                # Une seule reprise, avec des paramètres plus
                # stricts. Jamais de boucle infinie.
                if attempt < self.settings.max_attempts:
                    attempt_settings = (
                        attempt_settings.retry_settings()
                    )
                    continue

                result.analyzed = False
                result.decision = DECISION_ERROR
                result.error = last_error

        result.processing_time_seconds = round(
            perf_counter() - started_at,
            2,
        )

        return result


# ============================================================
# Sélection des exigences à envoyer au LLM
# ============================================================

def select_llm_candidates(
    summary_frame: pd.DataFrame,
    limit: int | None = None,
    minimum_severity: str = "MEDIUM",
    include_clean: bool = False,
) -> pd.DataFrame:
    """
    Choisit les exigences à approfondir avec le modèle.

    Le LLM étant beaucoup plus lent que les règles, les
    exigences sont classées par gravité puis par score qualité
    croissant, afin de traiter les cas les plus douteux en
    premier quand le budget de temps est limité.

    include_clean permet d'envoyer aussi les exigences sans
    alerte, en revue contextuelle complète, pour mesurer ce que
    les règles lexicales ne voient pas.
    """

    required = {
        CANONICAL_ID,
        CANONICAL_TEXT,
        "Issue_Count",
        "Highest_Severity",
        "Quality_Score",
    }

    missing = sorted(required.difference(summary_frame.columns))

    if missing:
        raise ValueError(
            "Colonnes absentes pour la sélection LLM : "
            + ", ".join(missing)
        )

    minimum_rank = config.SEVERITY_RANK.get(
        str(minimum_severity).upper(),
        0,
    )

    candidates = summary_frame.copy()

    candidates["_rank"] = candidates["Highest_Severity"].map(
        lambda value: config.SEVERITY_RANK.get(str(value), 0)
    )

    if include_clean:
        keep = candidates["_rank"] >= minimum_rank
        keep |= candidates["Issue_Count"] == 0
    else:
        keep = (candidates["Issue_Count"] > 0) & (
            candidates["_rank"] >= minimum_rank
        )

    candidates = candidates[keep].copy()

    candidates = candidates.sort_values(
        by=["_rank", "Quality_Score", "Issue_Count"],
        ascending=[False, True, False],
    ).drop(columns=["_rank"])

    if limit is not None and limit >= 0:
        candidates = candidates.head(limit)

    return candidates.reset_index(drop=True)


# ============================================================
# Analyse en lot
# ============================================================

def analyze_batch(
    candidates: pd.DataFrame,
    findings_frame: pd.DataFrame,
    settings: LLMSettings | None = None,
    max_evidence_per_rule: int = 5,
    show_progress: bool = True,
) -> dict[str, Any]:
    """
    Analyse un lot d'exigences sans interrompre le traitement
    en cas d'échec sur une ligne.
    """

    analyzer = LLMAnalyzer(settings=settings)
    health = analyzer.health_check()

    if not health["model_available"]:
        raise ValueError(
            f"Le modèle {analyzer.settings.model!r} n'est pas "
            "installé.\nExécute : ollama pull "
            f"{analyzer.settings.model}\nModèles disponibles : "
            + (", ".join(health["installed_models"]) or "aucun")
        )

    started_at = perf_counter()
    analyses: list[LLMAnalysis] = []
    total = len(candidates)

    for position, (_, row) in enumerate(
        candidates.iterrows(),
        start=1,
    ):
        requirement_id = clean_value(row.get(CANONICAL_ID))

        rule_findings = build_llm_findings(
            requirement_id=requirement_id,
            findings_frame=findings_frame,
            max_evidence_per_rule=max_evidence_per_rule,
        )

        review_mode = (
            "VALIDATE_RULE_FINDINGS"
            if rule_findings
            else "FULL_CONTEXT_REVIEW"
        )

        analysis = analyzer.analyze_requirement(
            requirement_id=requirement_id,
            requirement_text=clean_value(row.get(CANONICAL_TEXT)),
            object_type=clean_value(row.get(CANONICAL_TYPE)),
            findings=rule_findings,
            review_mode=review_mode,
        )

        analyses.append(analysis)

        if show_progress:
            elapsed = perf_counter() - started_at
            remaining = (elapsed / position) * (total - position)

            print(
                f"  LLM [{position}/{total}] {requirement_id} "
                f"-> {analysis.decision} "
                f"({analysis.processing_time_seconds}s, "
                f"reste ~{remaining:.0f}s)"
            )

    frame = pd.DataFrame(
        [analysis.to_row() for analysis in analyses],
        columns=LLM_RESULT_COLUMNS,
    )

    elapsed = perf_counter() - started_at

    technical_success = sum(
        1 for analysis in analyses if analysis.analyzed
    )
    technical_errors = len(analyses) - technical_success

    decisions = (
        frame["LLM_Decision"].value_counts().to_dict()
        if not frame.empty
        else {}
    )

    # Les indicateurs techniques et métier sont séparés : un
    # échec d'appel n'est pas un avis du modèle, et ne doit
    # jamais être compté comme une détection.
    diagnostics = {
        "model": analyzer.settings.model,
        "host": analyzer.settings.host,
        "call_count": len(analyses),
        "technical_success_count": technical_success,
        "technical_error_count": technical_errors,
        "technical_success_rate": round(
            technical_success / len(analyses),
            4,
        )
        if analyses
        else 0.0,
        "confirmed_count": decisions.get(DECISION_CONFIRMED, 0),
        "partially_confirmed_count": decisions.get(
            DECISION_PARTIALLY_CONFIRMED,
            0,
        ),
        "false_positive_count": decisions.get(
            DECISION_FALSE_POSITIVE,
            0,
        ),
        "needs_expert_review_count": decisions.get(
            DECISION_NEEDS_EXPERT_REVIEW,
            0,
        ),
        "confirmation_rate_on_success": round(
            (
                decisions.get(DECISION_CONFIRMED, 0)
                + decisions.get(DECISION_PARTIALLY_CONFIRMED, 0)
            )
            / technical_success,
            4,
        )
        if technical_success
        else 0.0,
        "retried_count": sum(
            1 for analysis in analyses if analysis.attempts > 1
        ),
        "total_generated_tokens": sum(
            analysis.generated_tokens for analysis in analyses
        ),
        "total_time_seconds": round(elapsed, 2),
        "average_time_seconds": round(elapsed / len(analyses), 2)
        if analyses
        else 0.0,
        "decision_counts": decisions,
    }

    return {
        "dataframe": frame,
        "analyses": analyses,
        "diagnostics": diagnostics,
        "health": health,
    }


# ============================================================
# Fusion avec le résumé des règles
# ============================================================

def merge_llm_results(
    summary_frame: pd.DataFrame,
    llm_frame: pd.DataFrame,
) -> pd.DataFrame:
    """
    Ajoute les colonnes LLM au résumé sans écraser les règles.

    Les exigences non soumises au modèle conservent des
    colonnes vides et la mention NOT_RUN, afin qu'aucune
    absence d'avis ne puisse être confondue avec un avis
    favorable.
    """

    result = summary_frame.copy()

    if llm_frame.empty:
        for column in LLM_RESULT_COLUMNS:
            if column == CANONICAL_ID:
                continue

            result[column] = ""

        result["LLM_Decision"] = "NOT_RUN"
        result["LLM_Analyzed"] = "NO"

        return result

    deduplicated = llm_frame.drop_duplicates(
        subset=[CANONICAL_ID],
        keep="first",
    )

    merged = result.merge(
        deduplicated,
        on=CANONICAL_ID,
        how="left",
    )

    merged["LLM_Decision"] = merged["LLM_Decision"].fillna(
        "NOT_RUN"
    )
    merged["LLM_Analyzed"] = merged["LLM_Analyzed"].fillna("NO")
    merged["Review_Mode"] = merged["Review_Mode"].fillna("NOT_RUN")

    for column in LLM_RESULT_COLUMNS:
        if column in merged.columns:
            merged[column] = merged[column].fillna("")

    return merged


# ============================================================
# Affichage
# ============================================================

def display_llm_diagnostics(result: dict[str, Any]) -> None:
    """Affiche les indicateurs techniques et métier du lot."""

    diagnostics = result["diagnostics"]

    print("\n" + "=" * 65)
    print("ANALYSE CONTEXTUELLE LLM")
    print("=" * 65)

    print(f"Modèle                      : {diagnostics['model']}")
    print(f"Appels                      : {diagnostics['call_count']}")
    print(
        "Succès techniques           : "
        f"{diagnostics['technical_success_count']} "
        f"({diagnostics['technical_success_rate']:.0%})"
    )
    print(
        "Erreurs techniques          : "
        f"{diagnostics['technical_error_count']}"
    )
    print(
        "Reprises déclenchées        : "
        f"{diagnostics['retried_count']}"
    )

    print("\nDécisions sur appels réussis :")
    print(f"  - CONFIRMED               : {diagnostics['confirmed_count']}")
    print(
        "  - PARTIALLY_CONFIRMED     : "
        f"{diagnostics['partially_confirmed_count']}"
    )
    print(
        "  - FALSE_POSITIVE          : "
        f"{diagnostics['false_positive_count']}"
    )
    print(
        "  - NEEDS_EXPERT_REVIEW     : "
        f"{diagnostics['needs_expert_review_count']}"
    )
    print(
        "Taux de confirmation        : "
        f"{diagnostics['confirmation_rate_on_success']:.0%}"
    )

    print(
        "\nTemps total                 : "
        f"{diagnostics['total_time_seconds']} s"
    )
    print(
        "Temps moyen par exigence    : "
        f"{diagnostics['average_time_seconds']} s"
    )
