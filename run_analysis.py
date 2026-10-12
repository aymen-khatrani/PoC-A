# ============================================================
# Exécution complète du contrôleur qualité des exigences
# ============================================================

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

import pandas as pd

from src.rule_loader import load_rules
from src.rule_engine import (
    analyse_requirements,
    display_analysis_diagnostics,
    display_analysis_sample,
)


# ============================================================
# Configuration
# ============================================================

DEFAULT_RULES_PATH = Path("rules/rules_en.csv")
DEFAULT_OUTPUT_DIRECTORY = Path("data/output")


# ============================================================
# Chargement du module Excel
# ============================================================

def get_excel_loader() -> Callable[[str], dict[str, Any]]:
    """
    Recherche la fonction de chargement Excel existante.

    Le projet peut contenir l'une des fonctions suivantes :
    - src.excel_loader.load_requirements ;
    - src.excel_loader.load_required_columns ;
    - load_excel.load_required_columns.
    """

    try:
        from src.excel_loader import load_requirements

        return load_requirements
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from src.excel_loader import load_required_columns

        return load_required_columns
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from load_excel import load_required_columns

        return load_required_columns
    except (ImportError, ModuleNotFoundError) as error:
        raise ImportError(
            "Impossible de trouver la fonction de chargement Excel. "
            "Le projet doit contenir l'une des fonctions suivantes : "
            "src.excel_loader.load_requirements, "
            "src.excel_loader.load_required_columns ou "
            "load_excel.load_required_columns."
        ) from error


# ============================================================
# Arguments de la ligne de commande
# ============================================================

def parse_arguments() -> argparse.Namespace:
    """Lit les arguments fournis dans PowerShell."""

    parser = argparse.ArgumentParser(
        description=(
            "Analyse un export Excel DOORS avec le catalogue "
            "de règles de qualité."
        )
    )

    parser.add_argument(
        "--input",
        "-i",
        dest="input_path",
        help="Chemin du fichier Excel DOORS à analyser.",
    )

    parser.add_argument(
        "--rules",
        "-r",
        dest="rules_path",
        default=str(DEFAULT_RULES_PATH),
        help=(
            "Chemin du catalogue CSV. "
            "Valeur par défaut : rules/rules_en.csv"
        ),
    )

    parser.add_argument(
        "--output",
        "-o",
        dest="output_path",
        help=(
            "Chemin du rapport Excel à créer. Si non fourni, "
            "le rapport est créé dans data/output."
        ),
    )

    parser.add_argument(
        "--sample-size",
        type=int,
        default=10,
        help="Nombre d'exigences signalées à afficher. Défaut : 10.",
    )

    parser.add_argument(
        "--include-non-requirements",
        action="store_true",
        help=(
            "Inclut également Heading, Information et les autres "
            "types dans le résumé avec le statut NON_ANALYSABLE."
        ),
    )

    parser.add_argument(
        "--non-strict-rules",
        action="store_true",
        help=(
            "Ignore les règles CSV invalides au lieu d'arrêter "
            "l'exécution."
        ),
    )

    return parser.parse_args()


# ============================================================
# Gestion des chemins
# ============================================================

def clean_path(value: str) -> Path:
    """Nettoie et résout un chemin saisi par l'utilisateur."""

    cleaned_value = value.strip().strip('"').strip("'")
    return Path(cleaned_value).expanduser().resolve()


def ask_for_input_path() -> Path:
    """Demande le chemin Excel si aucun argument n'a été fourni."""

    value = input("\nChemin du fichier Excel : ").strip()

    if not value:
        raise ValueError("Aucun chemin de fichier Excel n'a été fourni.")

    return clean_path(value)


def build_default_output_path(input_path: Path) -> Path:
    """Construit automatiquement le nom du rapport de sortie."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_name = f"{input_path.stem}_quality_analysis_{timestamp}.xlsx"

    return (DEFAULT_OUTPUT_DIRECTORY / output_name).resolve()


def validate_input_path(input_path: Path) -> None:
    """Vérifie que le fichier Excel d'entrée est exploitable."""

    if not input_path.exists():
        raise FileNotFoundError(
            f"Le fichier Excel est introuvable :\n{input_path}"
        )

    if not input_path.is_file():
        raise ValueError(
            f"Le chemin ne correspond pas à un fichier :\n{input_path}"
        )

    if input_path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError(
            "Le fichier d'entrée doit être au format .xlsx ou .xlsm."
        )


def validate_output_path(output_path: Path) -> None:
    """Vérifie le format du rapport de sortie."""

    if output_path.suffix.lower() != ".xlsx":
        raise ValueError(
            "Le rapport de sortie doit avoir l'extension .xlsx."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)


# ============================================================
# Préparation des données de diagnostic
# ============================================================

def dictionary_to_dataframe(
    data: dict[str, Any],
    section_name: str,
) -> pd.DataFrame:
    """Transforme un dictionnaire, y compris imbriqué, en tableau."""

    rows: list[dict[str, Any]] = []

    for key, value in data.items():
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                rows.append(
                    {
                        "Section": section_name,
                        "Metric": f"{key}.{nested_key}",
                        "Value": nested_value,
                    }
                )
        else:
            rows.append(
                {
                    "Section": section_name,
                    "Metric": key,
                    "Value": value,
                }
            )

    return pd.DataFrame(rows, columns=["Section", "Metric", "Value"])


def prepare_rules_dataframe(rules: list[Any]) -> pd.DataFrame:
    """Convertit les règles chargées en tableau exportable."""

    rows = []

    for rule in rules:
        if hasattr(rule, "to_dict"):
            rows.append(rule.to_dict())
        else:
            rows.append(
                {
                    "rule_id": getattr(rule, "rule_id", ""),
                    "category": getattr(rule, "category", ""),
                    "pattern": getattr(rule, "pattern", ""),
                    "severity": getattr(rule, "severity", ""),
                    "explanation": getattr(rule, "explanation", ""),
                    "clarification_question": getattr(
                        rule,
                        "clarification_question",
                        "",
                    ),
                    "rewrite_template": getattr(
                        rule,
                        "rewrite_template",
                        "",
                    ),
                    "enabled": getattr(rule, "enabled", False),
                }
            )

    return pd.DataFrame(rows)


# ============================================================
# Mise en forme du rapport Excel
# ============================================================

def format_worksheet(worksheet) -> None:
    """Applique une mise en forme simple et lisible à une feuille."""

    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    header_fill = PatternFill(
        fill_type="solid",
        fgColor="1F4E78",
    )
    header_font = Font(
        color="FFFFFF",
        bold=True,
    )

    worksheet.freeze_panes = "A2"
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

    for column_index, column_cells in enumerate(
        worksheet.iter_cols(),
        start=1,
    ):
        max_length = 0

        for cell in column_cells[:100]:
            value = "" if cell.value is None else str(cell.value)
            max_line_length = max(
                (len(line) for line in value.splitlines()),
                default=0,
            )
            max_length = max(max_length, max_line_length)

        width = min(max(max_length + 2, 12), 60)
        column_letter = get_column_letter(column_index)
        worksheet.column_dimensions[column_letter].width = width


def apply_status_formatting(worksheet) -> None:
    """Colore les cellules de statut du résumé."""

    from openpyxl.styles import PatternFill

    headers = {
        cell.value: cell.column
        for cell in worksheet[1]
    }

    status_column = headers.get("Quality_Status")

    if status_column is None:
        return

    fills = {
        "PRE_ANALYSIS_OK": PatternFill(
            fill_type="solid",
            fgColor="C6E0B4",
        ),
        "REVIEW_REQUIRED": PatternFill(
            fill_type="solid",
            fgColor="FCE4D6",
        ),
        "CLARIFICATION_REQUIRED": PatternFill(
            fill_type="solid",
            fgColor="F4B084",
        ),
        "NON_ANALYSABLE": PatternFill(
            fill_type="solid",
            fgColor="F4CCCC",
        ),
    }

    for row_index in range(2, worksheet.max_row + 1):
        cell = worksheet.cell(row=row_index, column=status_column)
        fill = fills.get(str(cell.value))

        if fill is not None:
            cell.fill = fill


# ============================================================
# Export du rapport
# ============================================================

def export_analysis_report(
    output_path: Path,
    analysis_result: dict[str, Any],
    excel_result: dict[str, Any],
    rules_result: dict[str, Any],
    input_path: Path,
    rules_path: Path,
    execution_time_seconds: float,
) -> None:
    """Crée le rapport Excel consolidé."""

    summary_dataframe = analysis_result["summary"].copy()
    findings_dataframe = analysis_result["findings"].copy()

    excel_diagnostics = dictionary_to_dataframe(
        excel_result.get("diagnostics", {}),
        "Excel import",
    )

    rule_diagnostics = dictionary_to_dataframe(
        rules_result.get("diagnostics", {}),
        "Rule loading",
    )

    analysis_diagnostics = dictionary_to_dataframe(
        analysis_result.get("diagnostics", {}),
        "Requirement analysis",
    )

    run_information = pd.DataFrame(
        [
            {"Parameter": "Input file", "Value": str(input_path)},
            {"Parameter": "Rules file", "Value": str(rules_path)},
            {"Parameter": "Output file", "Value": str(output_path)},
            {
                "Parameter": "Execution date",
                "Value": datetime.now().isoformat(timespec="seconds"),
            },
            {
                "Parameter": "Total execution time seconds",
                "Value": round(execution_time_seconds, 3),
            },
        ]
    )

    diagnostics_dataframe = pd.concat(
        [
            excel_diagnostics,
            rule_diagnostics,
            analysis_diagnostics,
        ],
        ignore_index=True,
    )

    rules_dataframe = prepare_rules_dataframe(
        rules_result.get("all_valid_rules", rules_result["rules"])
    )

    invalid_requirements = excel_result.get(
        "invalid_requirements",
        pd.DataFrame(),
    )

    ignored_objects = excel_result.get(
        "ignored_objects",
        pd.DataFrame(),
    )

    try:
        with pd.ExcelWriter(
            output_path,
            engine="openpyxl",
        ) as writer:
            summary_dataframe.to_excel(
                writer,
                sheet_name="Analysis_Results",
                index=False,
            )

            findings_dataframe.to_excel(
                writer,
                sheet_name="Findings",
                index=False,
            )

            diagnostics_dataframe.to_excel(
                writer,
                sheet_name="Diagnostics",
                index=False,
            )

            run_information.to_excel(
                writer,
                sheet_name="Run_Information",
                index=False,
            )

            rules_dataframe.to_excel(
                writer,
                sheet_name="Rules_Used",
                index=False,
            )

            if isinstance(invalid_requirements, pd.DataFrame):
                invalid_requirements.to_excel(
                    writer,
                    sheet_name="Invalid_Requirements",
                    index=False,
                )

            if isinstance(ignored_objects, pd.DataFrame):
                ignored_objects.to_excel(
                    writer,
                    sheet_name="Ignored_Objects",
                    index=False,
                )

            for worksheet in writer.book.worksheets:
                format_worksheet(worksheet)

            apply_status_formatting(
                writer.book["Analysis_Results"]
            )

    except PermissionError as error:
        raise PermissionError(
            "Impossible d'écrire le rapport. Ferme le fichier dans "
            "Excel puis relance l'analyse."
        ) from error


# ============================================================
# Exécution principale
# ============================================================

def run_analysis(
    input_path: Path,
    rules_path: Path,
    output_path: Path,
    sample_size: int = 10,
    include_non_requirements: bool = False,
    strict_rules: bool = True,
) -> dict[str, Any]:
    """Exécute la chaîne complète d'analyse."""

    validate_input_path(input_path)
    validate_output_path(output_path)

    if not rules_path.exists():
        raise FileNotFoundError(
            f"Le catalogue de règles est introuvable :\n{rules_path}"
        )

    started_at = perf_counter()

    print("\n" + "=" * 65)
    print("1. CHARGEMENT DU FICHIER EXCEL")
    print("=" * 65)

    excel_loader = get_excel_loader()
    excel_result = excel_loader(str(input_path))

    requirements = excel_result.get("requirements")

    if not isinstance(requirements, pd.DataFrame):
        raise ValueError(
            "Le chargeur Excel n'a pas retourné le DataFrame "
            "result['requirements']."
        )

    print(f"Exigences prêtes : {len(requirements)}")

    print("\n" + "=" * 65)
    print("2. CHARGEMENT DU CATALOGUE DE RÈGLES")
    print("=" * 65)

    rules_result = load_rules(
        rules_path=rules_path,
        include_disabled=False,
        strict=strict_rules,
    )

    rules = rules_result["rules"]
    print(f"Règles actives : {len(rules)}")

    if not rules:
        raise ValueError("Aucune règle active n'a été chargée.")

    print("\n" + "=" * 65)
    print("3. ANALYSE DES EXIGENCES")
    print("=" * 65)

    analysis_result = analyse_requirements(
        requirements=requirements,
        rules=rules,
        include_non_requirements=include_non_requirements,
    )

    display_analysis_diagnostics(analysis_result)
    display_analysis_sample(
        analysis_result,
        limit=max(sample_size, 0),
    )

    execution_time_seconds = perf_counter() - started_at

    print("\n" + "=" * 65)
    print("4. CRÉATION DU RAPPORT EXCEL")
    print("=" * 65)

    export_analysis_report(
        output_path=output_path,
        analysis_result=analysis_result,
        excel_result=excel_result,
        rules_result=rules_result,
        input_path=input_path,
        rules_path=rules_path,
        execution_time_seconds=execution_time_seconds,
    )

    print(f"Rapport créé : {output_path}")
    print(
        "Temps total : "
        f"{round(perf_counter() - started_at, 3)} seconde(s)"
    )

    return {
        "excel": excel_result,
        "rules": rules_result,
        "analysis": analysis_result,
        "output_path": output_path,
    }


def main() -> None:
    """Point d'entrée du script."""

    print("=" * 65)
    print("CONTRÔLEUR DE QUALITÉ DES EXIGENCES")
    print("=" * 65)

    arguments = parse_arguments()

    try:
        input_path = (
            clean_path(arguments.input_path)
            if arguments.input_path
            else ask_for_input_path()
        )

        rules_path = clean_path(arguments.rules_path)

        output_path = (
            clean_path(arguments.output_path)
            if arguments.output_path
            else build_default_output_path(input_path)
        )

        run_analysis(
            input_path=input_path,
            rules_path=rules_path,
            output_path=output_path,
            sample_size=arguments.sample_size,
            include_non_requirements=(
                arguments.include_non_requirements
            ),
            strict_rules=not arguments.non_strict_rules,
        )

        print("\n" + "=" * 65)
        print("ANALYSE TERMINÉE AVEC SUCCÈS")
        print("=" * 65)

    except KeyboardInterrupt:
        print("\nAnalyse interrompue par l'utilisateur.")
        raise SystemExit(1)

    except (
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

    except Exception as error:
        print("\n" + "=" * 65)
        print("ERREUR INATTENDUE")
        print("=" * 65)
        print(f"Type : {type(error).__name__}")
        print(f"Message : {error}")
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
