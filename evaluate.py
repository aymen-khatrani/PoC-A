# ============================================================
# Évaluation mesurée du contrôleur
# ============================================================
#
# Ce script remplace le test figé sur dix identifiants d'un
# projet précis. Il mesure la performance sur n'importe quel
# jeu de référence, à condition de savoir ce qui est attendu.
#
# Deux façons de déclarer l'attendu :
#
#   --expected-column Expected_Flag
#       une colonne du fichier indique YES ou NO pour chaque
#       exigence. C'est la méthode recommandée, car elle
#       contient aussi des cas corrects et permet donc de
#       mesurer la précision.
#
#   --ids CUS-72 CUS-198 ...   ou   --ids-file identifiants.txt
#       les identifiants cités sont considérés comme des cas
#       problématiques, tous les autres comme corrects.
#
# Indicateurs produits, volontairement séparés :
#
#   Rule_Engine            précision, rappel, F1 des règles
#   LLM_Technical          taux de réponses exploitables
#   LLM_Business           avis du modèle sur ces réponses
#   End_To_End             règles et LLM combinés
#
# Une erreur technique du modèle n'est jamais comptée comme
# une détection : c'était le principal biais de la version
# précédente.
#
# ============================================================

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd

from src import config
from src.config import (
    CANONICAL_ID,
    CANONICAL_TEXT,
    EngineSettings,
    LoaderSettings,
)
from src.excel_loader import load_requirements
from src.reporting import diagnostics_to_frame, write_report
from src.rule_engine import analyse_requirements
from src.rule_loader import load_rule_catalog
from src.text_utils import clean_value, normalize_key


DEFAULT_OUTPUT_DIRECTORY = Path("data/output")

POSITIVE_VALUES = {
    "yes", "y", "oui", "o", "true", "1", "ko", "nok", "bad",
    "problematique", "problematic", "flag", "flagged", "defect",
}

NEGATIVE_VALUES = {
    "no", "n", "non", "false", "0", "ok", "good", "correct",
    "clean", "acceptable",
}

# Décisions du LLM qui valent détection d'un défaut. Une erreur
# technique et une demande d'expertise humaine n'en font pas
# partie : ce ne sont pas des avis.
LLM_POSITIVE_DECISIONS = {
    "CONFIRMED",
    "PARTIALLY_CONFIRMED",
}


# ============================================================
# Ligne de commande
# ============================================================

def build_argument_parser() -> argparse.ArgumentParser:
    """Décrit les options d'évaluation."""

    parser = argparse.ArgumentParser(
        description=(
            "Mesure la précision, le rappel et le F1 du "
            "contrôleur sur un jeu de référence."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemples :\n"
            "  python evaluate.py -i reference.xlsx "
            "--expected-column Expected_Flag\n"
            "  python evaluate.py -i export.xlsx --ids-file "
            "cas_manager.txt --llm\n"
        ),
    )

    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Fichier de référence à évaluer.",
    )
    parser.add_argument(
        "--rules",
        "-r",
        nargs="+",
        default=["rules"],
        help="Fichiers ou dossiers de règles.",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Rapport Excel d'évaluation.",
    )

    expectation = parser.add_argument_group("attendu")

    expectation.add_argument(
        "--expected-column",
        help=(
            "Colonne du fichier indiquant si l'exigence est "
            "problématique (YES/NO, OK/KO, 1/0)."
        ),
    )
    expectation.add_argument(
        "--ids",
        nargs="+",
        default=[],
        metavar="ID",
        help="Identifiants considérés comme problématiques.",
    )
    expectation.add_argument(
        "--ids-file",
        help=(
            "Fichier texte contenant un identifiant "
            "problématique par ligne."
        ),
    )

    columns = parser.add_argument_group("colonnes")

    columns.add_argument("--sheet")
    columns.add_argument("--id-column")
    columns.add_argument("--text-column")
    columns.add_argument("--type-column")
    columns.add_argument("--heading-column")

    llm = parser.add_argument_group("analyse LLM")

    llm.add_argument(
        "--llm",
        action="store_true",
        help="Évalue aussi le LLM local.",
    )
    llm.add_argument("--model", default="qwen2.5:3b")
    llm.add_argument("--host", default="http://localhost:11434")
    llm.add_argument(
        "--llm-limit",
        type=int,
        default=-1,
        help=(
            "Nombre maximal d'exigences envoyées au modèle. "
            "Défaut : toutes."
        ),
    )

    return parser


def clean_path(value: str) -> Path:
    """Nettoie un chemin saisi dans un terminal."""

    return (
        Path(value.strip().strip('"').strip("'"))
        .expanduser()
        .resolve()
    )


# ============================================================
# Lecture de l'attendu
# ============================================================

def parse_expected_value(value: Any) -> bool | None:
    """
    Interprète une valeur d'attendu.

    Retourne None lorsque la valeur est vide ou illisible :
    l'exigence est alors exclue du calcul plutôt que comptée
    arbitrairement.
    """

    key = normalize_key(value).replace(" ", "")

    if not key:
        return None

    if key in POSITIVE_VALUES:
        return True

    if key in NEGATIVE_VALUES:
        return False

    return None


def read_ids_file(path: Path) -> list[str]:
    """Lit une liste d'identifiants, un par ligne."""

    if not path.exists():
        raise FileNotFoundError(
            f"Fichier d'identifiants introuvable :\n{path}"
        )

    identifiers: list[str] = []

    for line in path.read_text(encoding="utf-8-sig").splitlines():
        cleaned = line.strip()

        # Les lignes vides et les commentaires sont ignorés.
        if cleaned and not cleaned.startswith("#"):
            identifiers.append(cleaned)

    return identifiers


def attach_expectations(
    summary: pd.DataFrame,
    all_objects: pd.DataFrame,
    arguments: argparse.Namespace,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Ajoute la colonne Expected_Flag au résumé.

    Retourne le résumé enrichi et la liste des identifiants
    attendus mais absents du fichier.
    """

    warnings: list[str] = []
    result = summary.copy()

    expected_ids = list(arguments.ids)

    if arguments.ids_file:
        expected_ids.extend(
            read_ids_file(clean_path(arguments.ids_file))
        )

    if arguments.expected_column:
        column = arguments.expected_column
        matching = [
            name
            for name in all_objects.columns
            if normalize_key(name) == normalize_key(column)
        ]

        if not matching:
            raise ValueError(
                f"La colonne d'attendu {column!r} est absente du "
                "fichier.\nColonnes disponibles : "
                + ", ".join(str(name) for name in all_objects.columns)
            )

        expectation_by_id = {
            clean_value(row[CANONICAL_ID]): parse_expected_value(
                row[matching[0]]
            )
            for _, row in all_objects.iterrows()
        }

        result["Expected_Flag"] = result[CANONICAL_ID].map(
            lambda value: expectation_by_id.get(
                clean_value(value)
            )
        )

        unreadable = int(result["Expected_Flag"].isna().sum())

        if unreadable:
            warnings.append(
                f"{unreadable} exigence(s) sans attendu lisible "
                "dans la colonne "
                f"{column!r} : exclues du calcul."
            )

    elif expected_ids:
        normalized_expected = {
            normalize_key(value) for value in expected_ids
        }

        result["Expected_Flag"] = result[CANONICAL_ID].map(
            lambda value: normalize_key(value)
            in normalized_expected
        )

        present = {
            normalize_key(value)
            for value in all_objects[CANONICAL_ID]
        }

        missing = [
            value
            for value in expected_ids
            if normalize_key(value) not in present
        ]

        if missing:
            warnings.append(
                f"{len(missing)} identifiant(s) attendu(s) sont "
                "absents du fichier : "
                + ", ".join(missing[:10])
                + (" ..." if len(missing) > 10 else "")
            )

        analysed = set(result[CANONICAL_ID].map(normalize_key))

        not_analysed = [
            value
            for value in expected_ids
            if normalize_key(value) in present
            and normalize_key(value) not in analysed
        ]

        if not_analysed:
            warnings.append(
                f"{len(not_analysed)} identifiant(s) attendu(s) "
                "ont été écartés à l'import (type ignoré ou "
                "texte vide) : "
                + ", ".join(not_analysed[:10])
            )

        if not any(result["Expected_Flag"]):
            warnings.append(
                "Aucun identifiant attendu ne figure parmi les "
                "exigences analysées : le rappel sera nul par "
                "construction."
            )

    else:
        raise ValueError(
            "Aucun attendu fourni.\nUtilise --expected-column, "
            "--ids ou --ids-file.\nSans attendu, aucune "
            "précision ni aucun rappel ne peut être calculé."
        )

    return result, warnings


# ============================================================
# Calcul des indicateurs
# ============================================================

def compute_metrics(
    expected: pd.Series,
    predicted: pd.Series,
    label: str,
) -> dict[str, Any]:
    """
    Calcule la matrice de confusion et les indicateurs.

    Les exigences sans attendu lisible sont ignorées.
    """

    mask = expected.notna()
    expected_values = expected[mask].astype(bool)
    predicted_values = predicted[mask].astype(bool)

    true_positive = int(
        (expected_values & predicted_values).sum()
    )
    false_positive = int(
        (~expected_values & predicted_values).sum()
    )
    false_negative = int(
        (expected_values & ~predicted_values).sum()
    )
    true_negative = int(
        (~expected_values & ~predicted_values).sum()
    )

    evaluated = (
        true_positive
        + false_positive
        + false_negative
        + true_negative
    )

    precision = (
        true_positive / (true_positive + false_positive)
        if (true_positive + false_positive)
        else 0.0
    )

    recall = (
        true_positive / (true_positive + false_negative)
        if (true_positive + false_negative)
        else 0.0
    )

    f1_score = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )

    accuracy = (
        (true_positive + true_negative) / evaluated
        if evaluated
        else 0.0
    )

    has_negative_cases = (~expected_values).any()

    return {
        "label": label,
        "evaluated_count": evaluated,
        "positive_reference_count": int(expected_values.sum()),
        "negative_reference_count": int((~expected_values).sum()),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1_score, 4),
        "accuracy": round(accuracy, 4),
        "precision_is_measurable": bool(has_negative_cases),
    }


def metrics_to_frame(
    metrics_list: list[dict[str, Any]],
) -> pd.DataFrame:
    """Met les indicateurs en tableau comparatif."""

    return pd.DataFrame(metrics_list)


def print_metrics(metrics: dict[str, Any]) -> None:
    """Affiche un bloc d'indicateurs lisible."""

    print(f"\n--- {metrics['label']} ---")
    print(
        f"Cas évalués           : {metrics['evaluated_count']} "
        f"({metrics['positive_reference_count']} problématiques, "
        f"{metrics['negative_reference_count']} corrects)"
    )
    print(
        f"Vrais positifs        : {metrics['true_positive']}   "
        f"Faux négatifs : {metrics['false_negative']}"
    )
    print(
        f"Faux positifs         : {metrics['false_positive']}   "
        f"Vrais négatifs : {metrics['true_negative']}"
    )
    print(f"Rappel                : {metrics['recall']:.1%}")

    if metrics["precision_is_measurable"]:
        print(f"Précision             : {metrics['precision']:.1%}")
        print(f"F1-score              : {metrics['f1_score']:.1%}")
        print(f"Exactitude            : {metrics['accuracy']:.1%}")
    else:
        print(
            "Précision             : non mesurable, le jeu de "
            "référence ne contient aucun cas correct"
        )


# ============================================================
# Évaluation
# ============================================================

def run_evaluation(arguments: argparse.Namespace) -> dict[str, Any]:
    """Exécute l'évaluation complète et écrit le rapport."""

    started_at = perf_counter()
    input_path = clean_path(arguments.input)

    output_path = (
        clean_path(arguments.output)
        if arguments.output
        else (
            DEFAULT_OUTPUT_DIRECTORY
            / (
                f"{input_path.stem}_evaluation_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            )
        ).resolve()
    )

    print("=" * 65)
    print("ÉVALUATION DU CONTRÔLEUR DE QUALITÉ")
    print("=" * 65)

    excel_result = load_requirements(
        file_path=input_path,
        settings=LoaderSettings(
            sheet_name=arguments.sheet,
            id_column=arguments.id_column,
            text_column=arguments.text_column,
            type_column=arguments.type_column,
            heading_column=arguments.heading_column,
        ),
    )

    requirements = excel_result["requirements"]

    if requirements.empty:
        raise ValueError(
            "Aucune exigence analysable : vérifie les options de "
            "colonnes et de filtrage."
        )

    rules_result = load_rule_catalog(paths=list(arguments.rules))
    rules = rules_result["rules"]

    analysis_result = analyse_requirements(
        requirements=requirements,
        rules=rules,
        settings=EngineSettings(),
    )

    summary = analysis_result["summary"]
    findings = analysis_result["findings"]

    summary, expectation_warnings = attach_expectations(
        summary=summary,
        all_objects=excel_result["all_objects"],
        arguments=arguments,
    )

    summary["Rule_Engine_Flag"] = summary["Issue_Count"] > 0

    print(f"\nFichier               : {input_path.name}")
    print(f"Exigences analysées   : {len(summary)}")
    print(f"Règles actives        : {len(rules)}")

    for warning in excel_result["diagnostics"]["warnings"]:
        print(f"  ! {warning}")

    for warning in expectation_warnings:
        print(f"  ! {warning}")

    metrics_list = [
        compute_metrics(
            expected=summary["Expected_Flag"],
            predicted=summary["Rule_Engine_Flag"],
            label="Rule_Engine",
        )
    ]

    llm_diagnostics: dict[str, Any] = {"llm_enabled": arguments.llm}

    # ------------------------------------------------------
    # Évaluation du LLM
    # ------------------------------------------------------

    if arguments.llm:
        from src.llm_analyzer import (
            LLMSettings,
            analyze_batch,
            display_llm_diagnostics,
            merge_llm_results,
        )

        candidates = summary

        if arguments.llm_limit is not None and arguments.llm_limit >= 0:
            candidates = summary.head(arguments.llm_limit)

        print(f"\nExigences envoyées au LLM : {len(candidates)}")

        llm_result = analyze_batch(
            candidates=candidates,
            findings_frame=findings,
            settings=LLMSettings(
                model=arguments.model,
                host=arguments.host,
            ),
        )

        display_llm_diagnostics(llm_result)

        summary = merge_llm_results(
            summary_frame=summary,
            llm_frame=llm_result["dataframe"],
        )

        llm_diagnostics.update(llm_result["diagnostics"])

        summary["LLM_Flag"] = summary["LLM_Decision"].isin(
            LLM_POSITIVE_DECISIONS
        )

        # Le LLM n'est évalué que sur les appels techniquement
        # réussis : sinon on mesurerait la fiabilité du service,
        # pas la qualité de l'avis.
        technically_analysed = summary["LLM_Analyzed"] == "YES"

        metrics_list.append(
            compute_metrics(
                expected=summary["Expected_Flag"].where(
                    technically_analysed
                ),
                predicted=summary["LLM_Flag"],
                label="LLM_Business_On_Success",
            )
        )

        summary["End_To_End_Flag"] = (
            summary["Rule_Engine_Flag"] | summary["LLM_Flag"]
        )

        metrics_list.append(
            compute_metrics(
                expected=summary["Expected_Flag"],
                predicted=summary["End_To_End_Flag"],
                label="End_To_End",
            )
        )

    for metrics in metrics_list:
        print_metrics(metrics)

    if arguments.llm:
        print(
            "\nFiabilité technique du modèle : "
            f"{llm_diagnostics.get('technical_success_count', 0)}"
            f"/{llm_diagnostics.get('call_count', 0)} appels "
            "exploitables "
            f"({llm_diagnostics.get('technical_success_rate', 0):.0%})"
        )
        print(
            "Les erreurs techniques ne sont comptées ni comme "
            "détections ni comme rejets."
        )

    # ------------------------------------------------------
    # Rapport
    # ------------------------------------------------------

    elapsed = perf_counter() - started_at

    run_information = pd.DataFrame(
        [
            {"Parameter": "Fichier", "Value": str(input_path)},
            {
                "Parameter": "Méthode d'attendu",
                "Value": (
                    f"colonne {arguments.expected_column}"
                    if arguments.expected_column
                    else "liste d'identifiants"
                ),
            },
            {"Parameter": "Règles actives", "Value": len(rules)},
            {
                "Parameter": "LLM évalué",
                "Value": "oui" if arguments.llm else "non",
            },
            {
                "Parameter": "Modèle",
                "Value": (
                    arguments.model if arguments.llm else "non utilisé"
                ),
            },
            {
                "Parameter": "Date",
                "Value": datetime.now().isoformat(timespec="seconds"),
            },
            {
                "Parameter": "Durée (s)",
                "Value": round(elapsed, 2),
            },
        ]
    )

    warnings_frame = pd.DataFrame(
        [
            {"Source": "Import", "Warning": warning}
            for warning in excel_result["diagnostics"]["warnings"]
        ]
        + [
            {"Source": "Attendu", "Warning": warning}
            for warning in expectation_warnings
        ],
        columns=["Source", "Warning"],
    )

    write_report(
        output_path=output_path,
        sheets={
            "Evaluation_Detail": summary,
            "Metrics": metrics_to_frame(metrics_list),
            "Rule_Findings": findings,
            "Warnings": warnings_frame,
            "Excluded_Rows": excel_result["excluded"],
            "Run_Information": run_information,
            "Diagnostics": pd.concat(
                [
                    diagnostics_to_frame(
                        analysis_result["diagnostics"],
                        "Moteur de regles",
                    ),
                    diagnostics_to_frame(llm_diagnostics, "LLM"),
                ],
                ignore_index=True,
            ),
        },
    )

    print(f"\nRapport               : {output_path}")
    print(f"Durée                 : {elapsed:.2f} s")

    return {
        "summary": summary,
        "metrics": metrics_list,
        "output_path": output_path,
    }


def main() -> None:
    """Point d'entrée du script d'évaluation."""

    arguments = build_argument_parser().parse_args()

    try:
        run_evaluation(arguments)

    except KeyboardInterrupt:
        print("\nÉvaluation interrompue.")
        raise SystemExit(130)

    except (
        ConnectionError,
        FileNotFoundError,
        ImportError,
        PermissionError,
        ValueError,
    ) as error:
        print("\n" + "=" * 65)
        print("ERREUR")
        print("=" * 65)
        print(error)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
