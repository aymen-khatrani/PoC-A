# ============================================================
# Chargement générique d'un export d'exigences client
# ============================================================
#
# Objectif : accepter n'importe quel tableau d'exigences, sans
# supposer ni le nom des colonnes, ni la position de l'en-tête,
# ni la feuille, ni le vocabulaire des types d'objet.
#
# Le fichier d'origine n'est jamais modifié et le texte importé
# n'est jamais réécrit. Aucune ligne n'est supprimée en
# silence : chaque ligne reçoit un statut et un motif.
#
# ============================================================

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pandas as pd

from src import config
from src.config import (
    CANONICAL_HEADING,
    CANONICAL_ID,
    CANONICAL_TEXT,
    CANONICAL_TYPE,
    SOURCE_ROW,
    SOURCE_SHEET,
    LoaderSettings,
)
from src.text_utils import (
    classify_object_type,
    clean_value,
    collapse_whitespace,
    guess_language_profile,
    is_blank,
    looks_like_heading,
    match_alias,
    normalize_key,
)


SUPPORTED_EXCEL_SUFFIXES = {".xlsx", ".xlsm"}
SUPPORTED_CSV_SUFFIXES = {".csv", ".txt", ".tsv"}

STATUS_READY = "READY"
STATUS_MISSING_TEXT = "MISSING_TEXT"
STATUS_TEXT_TOO_SHORT = "TEXT_TOO_SHORT"
STATUS_EXCLUDED_TYPE = "EXCLUDED_NON_REQUIREMENT_TYPE"
STATUS_EXCLUDED_HEADING = "EXCLUDED_HEADING_HEURISTIC"
STATUS_EXCLUDED_FILTER = "EXCLUDED_BY_USER_FILTER"


# ============================================================
# Détection de la ligne d'en-tête
# ============================================================

def score_header_row(values: list[Any]) -> tuple[int, dict[str, Any]]:
    """
    Évalue si une ligne brute peut être la ligne d'en-tête.

    Le score récompense la présence des rôles reconnus et le
    nombre de libellés distincts. Une ligne de données obtient
    un score faible car ses cellules ne ressemblent pas à des
    noms de colonnes.
    """

    non_empty = [value for value in values if not is_blank(value)]

    if len(non_empty) < 2:
        return 0, {}

    roles = {
        "text": match_alias(non_empty, config.TEXT_COLUMN_ALIASES),
        "id": match_alias(non_empty, config.ID_COLUMN_ALIASES),
        "type": match_alias(non_empty, config.TYPE_COLUMN_ALIASES),
        "heading": match_alias(
            non_empty,
            config.HEADING_COLUMN_ALIASES,
        ),
    }

    score = 0

    if roles["text"] is not None:
        score += 10

    if roles["id"] is not None:
        score += 4

    if roles["type"] is not None:
        score += 3

    if roles["heading"] is not None:
        score += 3

    # Un en-tête contient des libellés courts et distincts.
    distinct_labels = {
        normalize_key(value)
        for value in non_empty
    }

    score += min(len(distinct_labels), 10)

    average_length = sum(
        len(collapse_whitespace(value)) for value in non_empty
    ) / len(non_empty)

    if average_length > 80:
        score -= 8

    return score, roles


def detect_header_row(raw_frame: pd.DataFrame) -> tuple[int, int, dict]:
    """
    Recherche la ligne d'en-tête dans les premières lignes.

    Beaucoup d'exports placent un titre, un logo ou des
    métadonnées au-dessus du tableau. Retourne l'index de la
    ligne retenue, son score et les rôles reconnus.
    """

    best_index = 0
    best_score = -1
    best_roles: dict[str, Any] = {}

    depth = min(config.HEADER_SEARCH_DEPTH, len(raw_frame))

    for row_index in range(depth):
        values = list(raw_frame.iloc[row_index].values)
        score, roles = score_header_row(values)

        if score > best_score:
            best_index = row_index
            best_score = score
            best_roles = roles

    return best_index, best_score, best_roles


# ============================================================
# Choix de la feuille
# ============================================================

def probe_sheet(
    path: Path,
    sheet_name: str,
) -> dict[str, Any]:
    """Analyse une feuille sans la charger entièrement."""

    try:
        raw_frame = pd.read_excel(
            path,
            sheet_name=sheet_name,
            header=None,
            dtype=object,
            nrows=(
                config.HEADER_SEARCH_DEPTH
                + config.SHEET_PROBE_ROW_COUNT
            ),
            engine="openpyxl",
        )
    except Exception as error:
        return {
            "sheet_name": sheet_name,
            "readable": False,
            "error": str(error),
            "score": -1,
            "header_row": 0,
            "roles": {},
        }

    if raw_frame.empty:
        return {
            "sheet_name": sheet_name,
            "readable": True,
            "error": "",
            "score": -1,
            "header_row": 0,
            "roles": {},
        }

    header_row, header_score, roles = detect_header_row(raw_frame)

    data_row_count = max(len(raw_frame) - header_row - 1, 0)

    score = header_score

    if data_row_count == 0:
        score -= 20

    return {
        "sheet_name": sheet_name,
        "readable": True,
        "error": "",
        "score": score,
        "header_row": header_row,
        "roles": roles,
        "probed_data_rows": data_row_count,
    }


def select_sheet(
    path: Path,
    requested_sheet: str | None,
) -> dict[str, Any]:
    """
    Choisit la feuille la plus plausible du classeur.

    La feuille demandée explicitement est toujours prioritaire.
    Sinon, la feuille dont l'en-tête est le plus reconnaissable
    est retenue.
    """

    try:
        excel_file = pd.ExcelFile(path, engine="openpyxl")
    except Exception as error:
        raise ValueError(
            f"Impossible d'ouvrir le classeur : {error}"
        ) from error

    sheet_names = list(excel_file.sheet_names)

    if not sheet_names:
        raise ValueError("Le classeur ne contient aucune feuille.")

    if requested_sheet is not None:
        matching = [
            name
            for name in sheet_names
            if normalize_key(name) == normalize_key(requested_sheet)
        ]

        if not matching:
            raise ValueError(
                f"La feuille {requested_sheet!r} est absente du "
                "classeur.\nFeuilles disponibles : "
                + ", ".join(sheet_names)
            )

        probe = probe_sheet(path, matching[0])
        probe["considered_sheets"] = sheet_names
        return probe

    probes = [probe_sheet(path, name) for name in sheet_names]
    best = max(probes, key=lambda item: item["score"])

    if best["score"] < 0:
        raise ValueError(
            "Aucune feuille exploitable n'a été trouvée dans le "
            "classeur.\nFeuilles examinées : "
            + ", ".join(sheet_names)
            + "\nUtilise --sheet et --text-column pour forcer la "
            "lecture."
        )

    best["considered_sheets"] = sheet_names
    best["all_probes"] = probes

    return best


# ============================================================
# Lecture brute du fichier
# ============================================================

def read_table(
    path: Path,
    settings: LoaderSettings,
) -> tuple[pd.DataFrame, str, int]:
    """
    Charge le tableau source et retourne le DataFrame, le nom
    de la feuille retenue et l'index de la ligne d'en-tête.

    Les fichiers CSV et texte délimité sont acceptés, car tous
    les clients n'exportent pas en Excel.
    """

    suffix = path.suffix.lower()

    if suffix in SUPPORTED_CSV_SUFFIXES:
        sample = path.read_text(
            encoding="utf-8-sig",
            errors="replace",
        )[:16384]

        try:
            delimiter = csv.Sniffer().sniff(
                sample,
                delimiters=",;\t|",
            ).delimiter
        except csv.Error:
            delimiter = ","

        raw_frame = pd.read_csv(
            path,
            sep=delimiter,
            header=None,
            dtype=object,
            encoding="utf-8-sig",
            keep_default_na=False,
            skipinitialspace=True,
            engine="python",
        )

        header_row = (
            settings.header_row
            if settings.header_row is not None
            else detect_header_row(raw_frame)[0]
        )

        frame = raw_frame.iloc[header_row + 1:].copy()
        frame.columns = [
            clean_value(value)
            for value in raw_frame.iloc[header_row].values
        ]

        return frame.reset_index(drop=True), path.name, header_row

    if suffix not in SUPPORTED_EXCEL_SUFFIXES:
        raise ValueError(
            f"Extension non prise en charge : {suffix!r}.\n"
            "Formats acceptés : "
            + ", ".join(
                sorted(
                    SUPPORTED_EXCEL_SUFFIXES
                    | SUPPORTED_CSV_SUFFIXES
                )
            )
        )

    selection = select_sheet(path, settings.sheet_name)
    sheet_name = selection["sheet_name"]

    header_row = (
        settings.header_row
        if settings.header_row is not None
        else selection["header_row"]
    )

    frame = pd.read_excel(
        path,
        sheet_name=sheet_name,
        header=header_row,
        dtype=object,
        engine="openpyxl",
    )

    # Les colonnes sans libellé sont renommées pour rester
    # traçables sans provoquer de collision.
    frame.columns = [
        clean_value(column)
        if not str(column).startswith("Unnamed:")
        else f"Column_{position + 1}"
        for position, column in enumerate(frame.columns)
    ]

    return frame, sheet_name, header_row


# ============================================================
# Résolution des colonnes
# ============================================================

def resolve_column(
    frame: pd.DataFrame,
    requested: str | None,
    aliases: list[str],
    role: str,
) -> Any | None:
    """
    Détermine la colonne à utiliser pour un rôle donné.

    Une colonne demandée explicitement est recherchée de façon
    tolérante, puis une erreur claire est levée si elle est
    introuvable.
    """

    columns = list(frame.columns)

    if requested is not None:
        for column in columns:
            if normalize_key(column) == normalize_key(requested):
                return column

        raise ValueError(
            f"La colonne {requested!r} demandée pour le rôle "
            f"{role!r} est absente.\nColonnes disponibles : "
            + ", ".join(str(column) for column in columns)
        )

    return match_alias(columns, aliases)


def find_longest_text_column(frame: pd.DataFrame) -> Any | None:
    """
    Choisit la colonne la plus probable pour le texte quand
    aucun alias ne correspond.

    Le texte d'une exigence est nettement plus long que celui
    d'un identifiant ou d'un type.
    """

    best_column = None
    best_length = 0.0

    for column in frame.columns:
        values = [
            collapse_whitespace(value)
            for value in frame[column].head(200)
        ]

        non_empty = [value for value in values if value]

        if not non_empty:
            continue

        average_length = sum(
            len(value) for value in non_empty
        ) / len(non_empty)

        if average_length > best_length:
            best_length = average_length
            best_column = column

    # Un identifiant ou un type reste court : sous ce seuil,
    # aucune colonne ne ressemble à du texte d'exigence.
    if best_length < 25:
        return None

    return best_column


def resolve_all_columns(
    frame: pd.DataFrame,
    settings: LoaderSettings,
) -> dict[str, Any]:
    """Associe chaque rôle interne à une colonne du fichier."""

    text_column = resolve_column(
        frame,
        settings.text_column,
        config.TEXT_COLUMN_ALIASES,
        "texte",
    )

    heading_column = resolve_column(
        frame,
        settings.heading_column,
        config.HEADING_COLUMN_ALIASES,
        "intitulé",
    )

    id_column = resolve_column(
        frame,
        settings.id_column,
        config.ID_COLUMN_ALIASES,
        "identifiant",
    )

    type_column = resolve_column(
        frame,
        settings.type_column,
        config.TYPE_COLUMN_ALIASES,
        "type",
    )

    # Une même colonne ne peut pas remplir deux rôles.
    if heading_column is not None and heading_column == text_column:
        heading_column = None

    if id_column is not None and id_column == text_column:
        id_column = None

    if type_column is not None and type_column in {
        text_column,
        heading_column,
        id_column,
    }:
        type_column = None

    detection_method = "alias"

    if text_column is None:
        # Dernier recours : la colonne la plus verbeuse.
        text_column = find_longest_text_column(frame)
        detection_method = "longest_text_column"

    if text_column is None and heading_column is not None:
        # Certains exports ne contiennent qu'un intitulé.
        text_column = heading_column
        heading_column = None
        detection_method = "heading_column_fallback"

    if text_column is None:
        raise ValueError(
            "Aucune colonne de texte d'exigence n'a été "
            "reconnue.\nColonnes disponibles : "
            + ", ".join(str(column) for column in frame.columns)
            + "\nIndique la colonne à analyser avec "
            "--text-column."
        )

    return {
        "text": text_column,
        "heading": heading_column,
        "id": id_column,
        "type": type_column,
        "detection_method": detection_method,
    }


# ============================================================
# Construction du texte analysé
# ============================================================

def build_analysed_text(
    heading: str,
    text: str,
    combine: bool,
) -> str:
    """
    Assemble le texte soumis aux règles.

    Lorsque l'intitulé et le corps sont dans deux colonnes
    distinctes, les deux sont conservés : une exigence perd son
    sens si l'on jette son intitulé. Aucun mot n'est réécrit.
    """

    heading = clean_value(heading)
    text = clean_value(text)

    if not combine or not heading:
        return text

    if not text:
        return heading

    # Évite de dupliquer un intitulé déjà répété dans le corps.
    if collapse_whitespace(text).lower().startswith(
        collapse_whitespace(heading).lower()
    ):
        return text

    return f"{heading}\n{text}"


# ============================================================
# Application des filtres de type
# ============================================================

def type_matches_filter(
    object_type: str,
    filter_values: tuple[str, ...],
) -> bool:
    """
    Compare un type d'objet à une liste fournie par
    l'utilisateur, sans tenir compte de la casse ni des
    accents.
    """

    key = normalize_key(object_type)

    if not key:
        return False

    for value in filter_values:
        filter_key = normalize_key(value)

        if not filter_key:
            continue

        if key == filter_key:
            return True

        # Une correspondance partielle n'est acceptée qu'en
        # préfixe, sur une frontière de mot. Sans cette
        # restriction, --include-types "Technical Req"
        # sélectionnerait aussi "Non-Technical Req".
        if key.startswith(f"{filter_key} "):
            return True

        if filter_key.startswith(f"{key} "):
            return True

    return False


def decide_import_status(
    analysed_text: str,
    object_type: str,
    type_class: str,
    has_type_column: bool,
    settings: LoaderSettings,
) -> tuple[str, str]:
    """
    Détermine si une ligne est analysable et explique pourquoi.

    Rien n'est écarté sans motif : le rapport final contient
    toutes les lignes avec leur statut.
    """

    if not analysed_text:
        return STATUS_MISSING_TEXT, "Texte d'exigence vide."

    if len(analysed_text) < settings.minimum_text_length:
        return (
            STATUS_TEXT_TOO_SHORT,
            "Texte trop court pour être analysé "
            f"({len(analysed_text)} caractères).",
        )

    if settings.include_types:
        if not type_matches_filter(
            object_type,
            settings.include_types,
        ):
            return (
                STATUS_EXCLUDED_FILTER,
                f"Type {object_type!r} absent de --include-types.",
            )

        return STATUS_READY, ""

    if settings.exclude_types and type_matches_filter(
        object_type,
        settings.exclude_types,
    ):
        return (
            STATUS_EXCLUDED_FILTER,
            f"Type {object_type!r} présent dans --exclude-types.",
        )

    if type_class == "NON_REQUIREMENT":
        return (
            STATUS_EXCLUDED_TYPE,
            f"Type {object_type!r} reconnu comme élément de "
            "structure documentaire.",
        )

    # Sans type exploitable, l'heuristique de titre évite
    # d'analyser les lignes de sommaire.
    if (
        type_class == "UNKNOWN"
        and settings.detect_headings_without_type
        and looks_like_heading(analysed_text)
    ):
        return (
            STATUS_EXCLUDED_HEADING,
            "Texte court sans obligation : identifié comme "
            "intitulé"
            + ("." if has_type_column else " (aucune colonne de type)."),
        )

    return STATUS_READY, ""


# ============================================================
# Chargement principal
# ============================================================

def load_requirements(
    file_path: str | Path,
    settings: LoaderSettings | None = None,
) -> dict[str, Any]:
    """
    Charge un export d'exigences et retourne un résultat
    normalisé.

    Retour :
        {
            "all_objects":   toutes les lignes avec statut,
            "requirements":  lignes analysables,
            "excluded":      lignes écartées avec motif,
            "column_mapping": rôles vers colonnes réelles,
            "diagnostics":   statistiques et avertissements,
        }
    """

    settings = settings or LoaderSettings()
    path = Path(file_path).expanduser().resolve()

    if not path.exists():
        raise FileNotFoundError(
            f"Le fichier est introuvable :\n{path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Le chemin ne correspond pas à un fichier :\n{path}"
        )

    frame, sheet_name, header_row = read_table(path, settings)

    if frame.empty:
        raise ValueError(
            "Le tableau sélectionné ne contient aucune ligne de "
            f"données (feuille {sheet_name!r})."
        )

    mapping = resolve_all_columns(frame, settings)
    has_type_column = mapping["type"] is not None

    records: list[dict[str, Any]] = []

    for position, (_, row) in enumerate(frame.iterrows()):
        heading = (
            clean_value(row.get(mapping["heading"]))
            if mapping["heading"] is not None
            else ""
        )

        text = clean_value(row.get(mapping["text"]))

        analysed_text = build_analysed_text(
            heading=heading,
            text=text,
            combine=settings.combine_heading_and_text,
        )

        object_type = (
            clean_value(row.get(mapping["type"]))
            if has_type_column
            else ""
        )

        type_class = classify_object_type(object_type)

        raw_identifier = (
            clean_value(row.get(mapping["id"]))
            if mapping["id"] is not None
            else ""
        )

        # L'index Excel réel permet de retrouver la ligne même
        # quand le fichier n'a pas d'identifiant.
        excel_row = header_row + 2 + position

        identifier = raw_identifier
        generated = False

        if not identifier:
            identifier = f"ROW-{excel_row}"
            generated = True

        status, reason = decide_import_status(
            analysed_text=analysed_text,
            object_type=object_type,
            type_class=type_class,
            has_type_column=has_type_column,
            settings=settings,
        )

        records.append(
            {
                CANONICAL_ID: identifier,
                CANONICAL_HEADING: heading,
                CANONICAL_TEXT: analysed_text,
                CANONICAL_TYPE: object_type,
                "Type_Class": type_class,
                SOURCE_ROW: excel_row,
                SOURCE_SHEET: sheet_name,
                "Source_ID": raw_identifier,
                "Source_Text": text,
                "ID_Generated": generated,
                "Import_Status": status,
                "Import_Reason": reason,
            }
        )

    all_objects = pd.DataFrame(records)

    # Les colonnes d'origine du client sont conservées telles
    # quelles. Elles ne servent pas à l'analyse mais elles
    # permettent de retrouver le contexte dans le rapport et
    # d'exploiter une éventuelle colonne d'attendu.
    reserved_names = set(all_objects.columns)

    extra_columns = pd.DataFrame(
        {
            str(column): frame[column].reset_index(drop=True)
            for column in frame.columns
            if str(column) not in reserved_names
        }
    )

    if not extra_columns.empty:
        all_objects = pd.concat(
            [all_objects, extra_columns],
            axis=1,
        )

    # Un identifiant dupliqué est signalé mais jamais écarté :
    # l'exigence existe et doit être analysée.
    all_objects["Duplicate_ID"] = (
        ~all_objects["ID_Generated"]
        & all_objects[CANONICAL_ID].duplicated(keep=False)
    )

    requirements = all_objects[
        all_objects["Import_Status"].eq(STATUS_READY)
    ].copy().reset_index(drop=True)

    excluded = all_objects[
        ~all_objects["Import_Status"].eq(STATUS_READY)
    ].copy().reset_index(drop=True)

    # ------------------------------------------------------
    # Diagnostics et avertissements
    # ------------------------------------------------------

    warnings: list[str] = []

    if mapping["id"] is None:
        warnings.append(
            "Aucune colonne d'identifiant reconnue : des "
            "identifiants ROW-<ligne Excel> ont été générés."
        )

    if not has_type_column:
        warnings.append(
            "Aucune colonne de type reconnue : les intitulés "
            "sont détectés par heuristique de texte."
        )

    if mapping["detection_method"] != "alias":
        warnings.append(
            "Colonne de texte déduite du contenu "
            f"({mapping['detection_method']}) et non d'un nom "
            "connu : vérifie la colonne retenue."
        )

    if requirements.empty:
        warnings.append(
            "Aucune exigence analysable après filtrage : "
            "vérifie --include-types et --text-column."
        )

    language = guess_language_profile(
        requirements[CANONICAL_TEXT].head(200).tolist()
        if not requirements.empty
        else []
    )

    if language["verdict"] == "other_language":
        warnings.append(
            "Le texte ne semble pas rédigé en anglais "
            f"({language['other_language_ratio']:.0%} de mots "
            "fonctionnels d'une autre langue). Le catalogue de "
            "règles anglais produira peu d'alertes pertinentes."
        )

    elif language["verdict"] == "telegraphic":
        # Cas fréquent et parfaitement légitime : des exigences
        # anglaises rédigées en style abrégé ou sous forme de
        # valeurs. Ce n'est pas un problème de langue.
        warnings.append(
            "Le texte contient très peu de mots fonctionnels "
            "(style télégraphique ou tabulaire). Les règles "
            "lexicales auront peu de prise : vérifie que la "
            "colonne de texte retenue est la bonne."
        )

    duplicate_count = int(all_objects["Duplicate_ID"].sum())

    if duplicate_count:
        warnings.append(
            f"{duplicate_count} ligne(s) partagent un "
            "identifiant : elles sont analysées et signalées."
        )

    diagnostics = {
        "file_name": path.name,
        "file_path": str(path),
        "sheet_name": sheet_name,
        "header_excel_row": header_row + 1,
        "column_id": str(mapping["id"] or "non détectée"),
        "column_heading": str(mapping["heading"] or "non détectée"),
        "column_text": str(mapping["text"]),
        "column_type": str(mapping["type"] or "non détectée"),
        "text_detection_method": mapping["detection_method"],
        "total_rows": int(len(all_objects)),
        "requirements_ready": int(len(requirements)),
        "excluded_rows": int(len(excluded)),
        "generated_ids": int(all_objects["ID_Generated"].sum()),
        "duplicate_ids": duplicate_count,
        "language_verdict": language["verdict"],
        "english_stopword_ratio": language["english_ratio"],
        "other_language_stopword_ratio": language[
            "other_language_ratio"
        ],
        "status_counts": all_objects["Import_Status"]
        .value_counts()
        .to_dict(),
        "type_counts": all_objects[CANONICAL_TYPE]
        .replace("", "TYPE_ABSENT")
        .value_counts()
        .to_dict(),
        "warnings": warnings,
    }

    return {
        "all_objects": all_objects,
        "requirements": requirements,
        "excluded": excluded,
        "column_mapping": mapping,
        "diagnostics": diagnostics,
    }


# ============================================================
# Affichage
# ============================================================

def display_diagnostics(result: dict[str, Any]) -> None:
    """Affiche un résumé lisible de l'import."""

    diagnostics = result["diagnostics"]

    print("\n" + "=" * 65)
    print("IMPORT DU FICHIER D'EXIGENCES")
    print("=" * 65)

    print(f"Fichier                : {diagnostics['file_name']}")
    print(f"Feuille retenue        : {diagnostics['sheet_name']}")
    print(
        f"Ligne d'en-tête        : "
        f"{diagnostics['header_excel_row']}"
    )

    print("\nColonnes reconnues :")
    print(f"  - identifiant        : {diagnostics['column_id']}")
    print(f"  - intitulé           : {diagnostics['column_heading']}")
    print(f"  - texte              : {diagnostics['column_text']}")
    print(f"  - type               : {diagnostics['column_type']}")

    print("\nVolumétrie :")
    print(f"  - lignes lues        : {diagnostics['total_rows']}")
    print(
        f"  - exigences prêtes   : "
        f"{diagnostics['requirements_ready']}"
    )
    print(f"  - lignes écartées    : {diagnostics['excluded_rows']}")

    print("\nRépartition des statuts d'import :")
    for status, count in diagnostics["status_counts"].items():
        print(f"  - {status}: {count}")

    if diagnostics["warnings"]:
        print("\nAvertissements :")
        for warning in diagnostics["warnings"]:
            print(f"  ! {warning}")
