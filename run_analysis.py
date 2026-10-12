# ============================================================
# Contrôleur de qualité des exigences - pipeline complet
# ============================================================
#
#     fichier client
#         -> import normalisé
#         -> moteur de règles
#         -> analyse LLM optionnelle sur les cas prioritaires
#         -> rapport Excel
#
# Le script accepte n'importe quel export d'exigences : les
# colonnes, la feuille, la ligne d'en-tête et le vocabulaire
# des types sont détectés, et peuvent tous être forcés en
# ligne de commande.
#
# Exemple minimal :
#     python run_analysis.py -i mon_export.xlsx
#
# ============================================================

from __future__ import annotations

import argparse
import sys
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
from src.excel_loader import display_diagnostics, load_requirements
from src.reporting import (
    diagnostics_to_frame,
    rules_to_frame,
    write_report,
)
from src.rule_engine import analyse_requirements
from src.rule_loader import load_rule_catalog


DEFAULT_RULES_PATH = Path("rules")
DEFAULT_OUTPUT_DIRECTORY = Path("data/output")


# ============================================================
# Ligne de commande
# ============================================================

def build_argument_parser() -> argparse.ArgumentParser:
    """Décrit toutes les options du pipeline."""

    parser = argparse.ArgumentParser(
        description=(
            "Analyse la qualité rédactionnelle d'un export "
            "d'exigences client (Excel ou CSV)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemples :\n"
            "  python run_analysis.py -i export.xlsx\n"
            "  python run_analysis.py -i export.xlsx "
            "--text-column \"Requirement Description\"\n"
            "  python run_analysis.py -i export.xlsx --llm "
            "--llm-limit 20\n"
        ),
    )

    source = parser.add_argument_group("fichier source")

    source.add_argument(
        "--input",
        "-i",
        required=True,
        help="Export d'exigences à analyser (.xlsx, .xlsm, .csv).",
    )
    source.add_argument(
        "--sheet",
        help=(
            "Feuille à lire. Par défaut, la feuille dont "
            "l'en-tête est le plus reconnaissable."
        ),
    )
    source.add_argument(
        "--header-row",
        type=int,
        help=(
            "Numéro de la ligne d'en-tête dans Excel "
            "(1 pour la première ligne). Détecté par défaut."
        ),
    )

    columns = parser.add_argument_group(
        "colonnes",
        "À préciser seulement si la détection automatique se "
        "trompe.",
    )

    columns.add_argument("--id-column", help="Colonne identifiant.")
    columns.add_argument(
        "--text-column",
        help="Colonne du texte de l'exigence.",
    )
    columns.add_argument(
        "--heading-column",
        help="Colonne de l'intitulé, si elle est séparée.",
    )
    columns.add_argument(
        "--type-column",
        help="Colonne du type d'objet.",
    )
    columns.add_argument(
        "--no-combine-heading",
        action="store_true",
        help=(
            "N'analyse que le corps du texte, sans y joindre "
            "l'intitulé."
        ),
    )

    filtering = parser.add_argument_group("filtrage des lignes")

    filtering.add_argument(
        "--include-types",
        nargs="+",
        default=[],
        metavar="TYPE",
        help=(
            "N'analyse que ces types d'objet. Comparaison "
            "insensible à la casse et aux accents."
        ),
    )
    filtering.add_argument(
        "--exclude-types",
        nargs="+",
        default=[],
        metavar="TYPE",
        help="Exclut ces types d'objet.",
    )
    filtering.add_argument(
        "--keep-headings",
        action="store_true",
        help=(
            "Analyse aussi les textes courts identifiés comme "
            "intitulés quand aucune colonne de type n'existe."
        ),
    )

    rules = parser.add_argument_group("catalogue de règles")

    rules.add_argument(
        "--rules",
        "-r",
        nargs="+",
        default=[str(DEFAULT_RULES_PATH)],
        help=(
            "Fichiers CSV ou dossiers de règles. "
            "Défaut : le dossier rules/."
        ),
    )
    rules.add_argument(
        "--non-strict-rules",
        action="store_true",
        help=(
            "Ignore les règles invalides au lieu d'arrêter "
            "l'exécution."
        ),
    )

    llm = parser.add_argument_group("analyse LLM locale")

    llm.add_argument(
        "--llm",
        action="store_true",
        help="Active l'analyse contextuelle par LLM local.",
    )
    llm.add_argument(
        "--model",
        default="qwen2.5:3b",
        help="Modèle Ollama. Défaut : qwen2.5:3b.",
    )
    llm.add_argument(
        "--host",
        default="http://localhost:11434",
        help="Adresse du service Ollama.",
    )
    llm.add_argument(
        "--llm-limit",
        type=int,
        default=20,
        help=(
            "Nombre maximal d'exigences envoyées au modèle. "
            "Utiliser -1 pour tout envoyer. Défaut : 20."
        ),
    )
    llm.add_argument(
        "--llm-min-severity",
        default="MEDIUM",
        choices=sorted(config.ALLOWED_SEVERITIES),
        help=(
            "Gravité minimale pour être envoyé au modèle. "
            "Défaut : MEDIUM."
        ),
    )
    llm.add_argument(
        "--llm-include-clean",
        action="store_true",
        help=(
            "Envoie aussi les exigences sans alerte, en revue "
            "contextuelle complète."
        ),
    )

    output = parser.add_argument_group("sortie")

    output.add_argument(
        "--output",
        "-o",
        help=(
            "Rapport Excel à produire. Par défaut dans "
            "data/output avec un horodatage."
        ),
    )
    output.add_argument(
        "--sample",
        type=int,
        default=10,
        help="Nombre d'exigences signalées à afficher. Défaut : 10.",
    )

    return parser


def clean_path(value: str) -> Path:
    """Nettoie un chemin collé depuis un terminal."""

    return (
        Path(value.strip().strip('"').strip("'"))
        .expanduser()
        .resolve()
    )


def build_default_output_path(input_path: Path) -> Path:
    """Construit un nom de rapport horodaté."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    return (
        DEFAULT_OUTPUT_DIRECTORY
        / f"{input_path.stem}_qualite_{timestamp}.xlsx"
    ).resolve()


# ============================================================
# Affichage
# ============================================================

def print_section(title: str) -> None:
    """Affiche un titre de section."""

    print("\n" + "=" * 65)
    print(title)
    print("=" * 65)


def display_engine_diagnostics(diagnostics: dict[str, Any]) -> None:
    """Affiche le bilan du moteur de règles."""

    print(
        f"Exigences analysées        : "
        f"{diagnostics['analysed_requirement_count']}"
    )
    print(f"Règles appliquées          : {diagnostics['rule_count']}")
    print(
        f"Exigences avec alerte      : "
        f"{diagnostics['requirements_with_issues']} "
        f"({diagnostics['flag_rate']:.0%})"
    )
    print(
        f"Défauts distincts          : "
        f"{diagnostics['distinct_issue_count']} "
        f"({diagnostics['occurrence_count']} occurrences)"
    )
    print(
        f"Score qualité moyen        : "
        f"{diagnostics['average_quality_score']}/100"
    )
    print(
        f"Risques à évaluer          : "
        f"{diagnostics['risk_to_assess_count']}"
    )
    print(
        f"Temps total                : "
        f"{diagnostics['total_time_seconds']} s "
        f"({diagnostics['average_time_ms']} ms par exigence)"
    )

    print("\nRépartition des statuts :")
    for status, count in diagnostics["status_counts"].items():
        print(f"  - {status}: {count}")

    if diagnostics["category_counts"]:
        print("\nPrincipales catégories de défauts :")

        ranked = sorted(
            diagnostics["category_counts"].items(),
            key=lambda item: item[1],
            reverse=True,
        )

        for category, count in ranked[:10]:
            print(f"  - {category}: {count}")


def display_sample(summary: pd.DataFrame, limit: int) -> None:
    """Affiche un aperçu des exigences les plus douteuses."""

    if limit <= 0 or summary.empty:
        return

    flagged = summary[summary["Issue_Count"] > 0]

    if flagged.empty:
        print("\nAucune alerte sur ce fichier.")
        return

    print_section(f"APERÇU DES {min(limit, len(flagged))} CAS PRIORITAIRES")

    columns = [
        CANONICAL_ID,
        "Quality_Status",
        "Quality_Score",
        "Issue_Count",
        "Triggered_Rules",
        "Evidence",
    ]

    print(
        flagged.sort_values("Quality_Score")[columns]
        .head(limit)
        .to_string(index=False, max_colwidth=45)
    )


# ============================================================
# Pipeline
# ============================================================

def run_pipeline(arguments: argparse.Namespace) -> dict[str, Any]:
    """Exécute la chaîne complète et écrit le rapport."""

    started_at = perf_counter()

    input_path = clean_path(arguments.input)

    output_path = (
        clean_path(arguments.output)
        if arguments.output
        else build_default_output_path(input_path)
    )

    loader_settings = LoaderSettings(
        sheet_name=arguments.sheet,
        id_column=arguments.id_column,
        text_column=arguments.text_column,
        type_column=arguments.type_column,
        heading_column=arguments.heading_column,
        header_row=(
            arguments.header_row - 1
            if arguments.header_row is not None
            else None
        ),
        combine_heading_and_text=not arguments.no_combine_heading,
        include_types=tuple(arguments.include_types),
        exclude_types=tuple(arguments.exclude_types),
        detect_headings_without_type=not arguments.keep_headings,
    )

    # ------------------------------------------------------
    # 1. Import
    # ------------------------------------------------------

    print_section("1. IMPORT DU FICHIER")

    excel_result = load_requirements(
        file_path=input_path,
        settings=loader_settings,
    )

    display_diagnostics(excel_result)

    requirements = excel_result["requirements"]

    if requirements.empty:
        raise ValueError(
            "Aucune exigence analysable n'a été retenue. "
            "Consulte les avertissements ci-dessus, puis ajuste "
            "--text-column, --type-column ou --include-types."
        )

    # ------------------------------------------------------
    # 2. Catalogue
    # ------------------------------------------------------

    print_section("2. CATALOGUE DE RÈGLES")

    rules_result = load_rule_catalog(
        paths=list(arguments.rules),
        include_disabled=False,
        strict=not arguments.non_strict_rules,
    )

    rules = rules_result["rules"]

    print(
        f"Fichiers chargés           : "
        f"{rules_result['diagnostics']['file_name']}"
    )
    print(f"Règles actives             : {len(rules)}")

    if rules_result["errors"]:
        print(f"Règles ignorées            : {len(rules_result['errors'])}")

        for message in rules_result["errors"][:5]:
            print(f"  ! {message}")

    # ------------------------------------------------------
    # 3. Moteur de règles
    # ------------------------------------------------------

    print_section("3. ANALYSE PAR RÈGLES")

    analysis_result = analyse_requirements(
        requirements=requirements,
        rules=rules,
        settings=EngineSettings(),
    )

    display_engine_diagnostics(analysis_result["diagnostics"])

    summary = analysis_result["summary"]
    findings = analysis_result["findings"]

    # ------------------------------------------------------
    # 4. Analyse LLM optionnelle
    # ------------------------------------------------------

    llm_diagnostics: dict[str, Any] = {
        "llm_enabled": arguments.llm,
    }

    if arguments.llm:
        print_section("4. ANALYSE CONTEXTUELLE LLM")

        # Import tardif : le mode règles seules ne requiert pas
        # le paquet ollama.
        from src.llm_analyzer import (
            LLMSettings,
            analyze_batch,
            display_llm_diagnostics,
            merge_llm_results,
            select_llm_candidates,
        )

        candidates = select_llm_candidates(
            summary_frame=summary,
            limit=(
                None
                if arguments.llm_limit is not None
                and arguments.llm_limit < 0
                else arguments.llm_limit
            ),
            minimum_severity=arguments.llm_min_severity,
            include_clean=arguments.llm_include_clean,
        )

        print(f"Exigences sélectionnées    : {len(candidates)}")

        if candidates.empty:
            print(
                "Aucune exigence ne remplit les critères de "
                "sélection : analyse LLM ignorée."
            )
            llm_diagnostics["selected_count"] = 0
        else:
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
            llm_diagnostics["selected_count"] = len(candidates)

    # ------------------------------------------------------
    # 5. Aperçu et rapport
    # ------------------------------------------------------

    display_sample(summary, arguments.sample)

    print_section("5. RAPPORT EXCEL")

    execution_seconds = perf_counter() - started_at

    run_information = pd.DataFrame(
        [
            {"Parameter": "Fichier analysé", "Value": str(input_path)},
            {
                "Parameter": "Feuille",
                "Value": excel_result["diagnostics"]["sheet_name"],
            },
            {
                "Parameter": "Colonne texte",
                "Value": excel_result["diagnostics"]["column_text"],
            },
            {
                "Parameter": "Catalogue",
                "Value": rules_result["diagnostics"]["file_path"],
            },
            {"Parameter": "Règles actives", "Value": len(rules)},
            {
                "Parameter": "Analyse LLM",
                "Value": "oui" if arguments.llm else "non",
            },
            {
                "Parameter": "Modèle",
                "Value": arguments.model if arguments.llm else "non utilisé",
            },
            {"Parameter": "Rapport", "Value": str(output_path)},
            {
                "Parameter": "Date d'exécution",
                "Value": datetime.now().isoformat(timespec="seconds"),
            },
            {
                "Parameter": "Durée totale (s)",
                "Value": round(execution_seconds, 2),
            },
        ]
    )

    diagnostics_frame = pd.concat(
        [
            diagnostics_to_frame(
                excel_result["diagnostics"],
                "Import",
            ),
            diagnostics_to_frame(
                rules_result["diagnostics"],
                "Catalogue",
            ),
            diagnostics_to_frame(
                analysis_result["diagnostics"],
                "Moteur de regles",
            ),
            diagnostics_to_frame(llm_diagnostics, "LLM"),
        ],
        ignore_index=True,
    )

    write_report(
        output_path=output_path,
        sheets={
            "Analysis_Results": summary,
            "Rule_Findings": findings,
            "Excluded_Rows": excel_result["excluded"],
            "Diagnostics": diagnostics_frame,
            "Run_Information": run_information,
            "Rules_Used": rules_to_frame(
                rules_result["all_valid_rules"]
            ),
        },
    )

    print(f"Rapport écrit              : {output_path}")
    print(f"Durée totale               : {execution_seconds:.2f} s")

    return {
        "import": excel_result,
        "rules": rules_result,
        "analysis": analysis_result,
        "summary": summary,
        "output_path": output_path,
    }


# ============================================================
# Point d'entrée
# ============================================================

def main() -> None:
    """Exécute le pipeline et traduit les erreurs en messages."""

    print("=" * 65)
    print("CONTRÔLEUR DE QUALITÉ DES EXIGENCES")
    print("=" * 65)

    arguments = build_argument_parser().parse_args()

    try:
        run_pipeline(arguments)

        print_section("ANALYSE TERMINÉE")

    except KeyboardInterrupt:
        print("\nAnalyse interrompue par l'utilisateur.")
        raise SystemExit(130)

    except (
        ConnectionError,
        FileNotFoundError,
        ImportError,
        PermissionError,
        ValueError,
    ) as error:
        print_section("ERREUR")
        print(error)
        raise SystemExit(1) from error

    except Exception as error:
        print_section("ERREUR INATTENDUE")
        print(f"Type    : {type(error).__name__}")
        print(f"Message : {error}")
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
