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
from typing import Any

import pandas as pd

from src import config


# Largeur maximale d'une colonne, en caractères.
MAXIMUM_COLUMN_WIDTH = 60
MINIMUM_COLUMN_WIDTH = 12

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

        if series.dtype == object:
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

        width = min(
            max(longest + 2, MINIMUM_COLUMN_WIDTH),
            MAXIMUM_COLUMN_WIDTH,
        )

        worksheet.column_dimensions[
            get_column_letter(position)
        ].width = width


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
) -> Path:
    """
    Écrit un classeur à partir d'un dictionnaire de feuilles.

    Les noms de feuilles sont tronqués à 31 caractères, limite
    d'Excel. Une feuille vide est conservée avec son en-tête
    pour que le lecteur sache qu'elle a bien été produite.
    """

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

    except PermissionError as error:
        raise PermissionError(
            "Impossible d'écrire le rapport : le fichier est "
            "probablement ouvert dans Excel.\n"
            f"Ferme {path.name} puis relance l'analyse."
        ) from error

    return path
