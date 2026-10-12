from pathlib import Path
import sys

import pandas as pd


# ============================================================
# Configuration
# ============================================================

REQUIRED_COLUMNS = [
    "ID",
    "Object Heading and Object Text",
    "ObjectType",
]

ANALYSABLE_OBJECT_TYPES = {
    "Technical Req",
    "Non-Technical Req",
}


# ============================================================
# Fonctions utilitaires
# ============================================================

def normalize_column_name(column_name) -> str:
    """
    Normalise un nom de colonne uniquement pour faciliter
    sa recherche.

    Exemple :
        " ObjectType " devient "objecttype"

    Le nom original de la colonne reste conservé dans le DataFrame.
    """

    if column_name is None:
        return ""

    return " ".join(str(column_name).split()).strip().lower()


def build_column_mapping(columns) -> dict:
    """
    Construit un dictionnaire permettant de retrouver les noms
    de colonnes sans tenir compte de la casse ou des espaces
    supplémentaires.

    Exemple :
        {
            "id": "ID",
            "objecttype": "ObjectType"
        }
    """

    mapping = {}

    for column in columns:
        normalized_name = normalize_column_name(column)

        if normalized_name:
            mapping[normalized_name] = column

    return mapping


def find_matching_columns(columns) -> dict:
    """
    Recherche les trois colonnes obligatoires dans une liste
    de colonnes.

    Retourne un dictionnaire :
        nom attendu -> nom réellement trouvé
    """

    available_columns = build_column_mapping(columns)
    matching_columns = {}

    for required_column in REQUIRED_COLUMNS:
        normalized_required = normalize_column_name(required_column)

        if normalized_required in available_columns:
            matching_columns[required_column] = available_columns[
                normalized_required
            ]

    return matching_columns


# ============================================================
# Recherche de la feuille Excel
# ============================================================

def find_sheet_with_required_columns(
    file_path: Path,
) -> tuple[str, dict]:
    """
    Parcourt toutes les feuilles du classeur et retourne la première
    feuille contenant les trois colonnes obligatoires.

    Seule la première ligne de chaque feuille est lue pendant
    cette phase afin de limiter le temps de traitement.
    """

    try:
        excel_file = pd.ExcelFile(
            file_path,
            engine="openpyxl",
        )

    except Exception as error:
        raise ValueError(
            f"Impossible d'ouvrir le fichier Excel : {error}"
        ) from error

    print("\nFeuilles trouvées dans le classeur :")

    for sheet_name in excel_file.sheet_names:
        print(f"  - {sheet_name}")

    for sheet_name in excel_file.sheet_names:
        try:
            header_df = pd.read_excel(
                excel_file,
                sheet_name=sheet_name,
                nrows=0,
                engine="openpyxl",
            )

        except Exception as error:
            print(
                f"\nAttention : impossible de lire la feuille "
                f"'{sheet_name}' : {error}"
            )
            continue

        matching_columns = find_matching_columns(
            header_df.columns
        )

        missing_columns = [
            column
            for column in REQUIRED_COLUMNS
            if column not in matching_columns
        ]

        if not missing_columns:
            return sheet_name, matching_columns

    raise ValueError(
        "Aucune feuille ne contient les trois colonnes obligatoires : "
        + ", ".join(REQUIRED_COLUMNS)
    )


# ============================================================
# Chargement des données
# ============================================================

def load_required_columns(file_path: str) -> dict:
    """
    Cherche automatiquement les trois colonnes dans le fichier
    Excel et les charge dans un DataFrame pandas.

    Retourne un dictionnaire contenant :
        - la feuille sélectionnée ;
        - toutes les lignes chargées ;
        - les exigences analysables ;
        - les autres objets ;
        - les lignes invalides ;
        - les diagnostics.
    """

    path = Path(file_path).expanduser().resolve()

    # --------------------------------------------------------
    # Vérification du fichier
    # --------------------------------------------------------

    if not path.exists():
        raise FileNotFoundError(
            f"Le fichier n'existe pas :\n{path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Le chemin ne correspond pas à un fichier :\n{path}"
        )

    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError(
            "Le fichier doit être au format .xlsx ou .xlsm."
        )

    # --------------------------------------------------------
    # Recherche de la feuille et des colonnes
    # --------------------------------------------------------

    sheet_name, matching_columns = (
        find_sheet_with_required_columns(path)
    )

    print(
        f"\nFeuille contenant les colonnes recherchées : "
        f"{sheet_name}"
    )

    print("\nCorrespondance des colonnes :")

    for expected_name, actual_name in matching_columns.items():
        print(f"  - {expected_name} -> {actual_name}")

    actual_columns = list(matching_columns.values())

    # --------------------------------------------------------
    # Chargement uniquement des colonnes nécessaires
    # --------------------------------------------------------

    try:
        dataframe = pd.read_excel(
            path,
            sheet_name=sheet_name,
            usecols=actual_columns,
            dtype=object,
            engine="openpyxl",
        )

    except Exception as error:
        raise ValueError(
            f"Impossible de charger les données : {error}"
        ) from error

    # --------------------------------------------------------
    # Renommage avec les noms attendus
    # --------------------------------------------------------

    rename_mapping = {
        actual_name: expected_name
        for expected_name, actual_name
        in matching_columns.items()
    }

    dataframe = dataframe.rename(
        columns=rename_mapping
    )

    # Remettre les colonnes dans l'ordre attendu.
    dataframe = dataframe[REQUIRED_COLUMNS].copy()

    # --------------------------------------------------------
    # Traçabilité de la ligne source
    # --------------------------------------------------------

    # La ligne 1 contient les en-têtes.
    # La première ligne de données correspond donc à la ligne 2.
    dataframe["Source_Excel_Row"] = (
        dataframe.index + 2
    )

    # --------------------------------------------------------
    # Conservation des données originales
    # --------------------------------------------------------

    dataframe["Original_ID"] = dataframe["ID"]

    dataframe["Original_Text"] = dataframe[
        "Object Heading and Object Text"
    ]

    dataframe["Original_ObjectType"] = dataframe[
        "ObjectType"
    ]

    # --------------------------------------------------------
    # Création de valeurs normalisées
    # --------------------------------------------------------

    # Ces colonnes servent uniquement aux contrôles.
    # Elles ne remplacent jamais les données originales.

    dataframe["Normalized_ID"] = (
        dataframe["ID"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    dataframe["Normalized_Text"] = (
        dataframe["Object Heading and Object Text"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    dataframe["Normalized_ObjectType"] = (
        dataframe["ObjectType"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # --------------------------------------------------------
    # Contrôles de qualité de l'import
    # --------------------------------------------------------

    dataframe["Missing_ID"] = (
        dataframe["Normalized_ID"].eq("")
    )

    dataframe["Missing_Text"] = (
        dataframe["Normalized_Text"].eq("")
    )

    dataframe["Missing_ObjectType"] = (
        dataframe["Normalized_ObjectType"].eq("")
    )

    dataframe["Duplicate_ID"] = (
        ~dataframe["Missing_ID"]
        & dataframe["Normalized_ID"].duplicated(
            keep=False
        )
    )

    # --------------------------------------------------------
    # Identification des exigences
    # --------------------------------------------------------

    dataframe["Is_Requirement"] = (
        dataframe["Normalized_ObjectType"]
        .isin(ANALYSABLE_OBJECT_TYPES)
    )

    # --------------------------------------------------------
    # Détermination du statut d'import
    # --------------------------------------------------------

    dataframe["Import_Status"] = "READY"

    # Les objets qui ne sont pas des exigences sont ignorés.
    dataframe.loc[
        ~dataframe["Is_Requirement"],
        "Import_Status",
    ] = "IGNORED_OBJECT_TYPE"

    # Contrôles des valeurs manquantes.
    dataframe.loc[
        dataframe["Missing_ID"],
        "Import_Status",
    ] = "MISSING_ID"

    dataframe.loc[
        dataframe["Missing_Text"],
        "Import_Status",
    ] = "MISSING_TEXT"

    dataframe.loc[
        (
            dataframe["Missing_ID"]
            & dataframe["Missing_Text"]
        ),
        "Import_Status",
    ] = "MISSING_ID_AND_TEXT"

    dataframe.loc[
        (
            dataframe["Missing_ObjectType"]
            & ~dataframe["Missing_ID"]
            & ~dataframe["Missing_Text"]
        ),
        "Import_Status",
    ] = "MISSING_OBJECT_TYPE"

    dataframe.loc[
        (
            dataframe["Duplicate_ID"]
            & dataframe["Import_Status"].eq("READY")
        ),
        "Import_Status",
    ] = "DUPLICATE_ID"

    # --------------------------------------------------------
    # Séparation des différents groupes
    # --------------------------------------------------------

    requirements = dataframe[
        dataframe["Is_Requirement"]
        & dataframe["Import_Status"].eq("READY")
    ].copy()

    invalid_requirements = dataframe[
        dataframe["Is_Requirement"]
        & ~dataframe["Import_Status"].eq("READY")
    ].copy()

    ignored_objects = dataframe[
        ~dataframe["Is_Requirement"]
    ].copy()

    # --------------------------------------------------------
    # Diagnostics
    # --------------------------------------------------------

    object_type_counts = (
        dataframe["Normalized_ObjectType"]
        .replace("", "MISSING_TYPE")
        .value_counts(dropna=False)
        .to_dict()
    )

    diagnostics = {
        "file_name": path.name,
        "file_path": str(path),
        "sheet_name": sheet_name,
        "total_rows": int(len(dataframe)),
        "requirements_ready": int(len(requirements)),
        "invalid_requirements": int(
            len(invalid_requirements)
        ),
        "ignored_objects": int(len(ignored_objects)),
        "missing_ids": int(
            dataframe["Missing_ID"].sum()
        ),
        "missing_texts": int(
            dataframe["Missing_Text"].sum()
        ),
        "missing_object_types": int(
            dataframe["Missing_ObjectType"].sum()
        ),
        "duplicate_ids": int(
            dataframe["Duplicate_ID"].sum()
        ),
        "object_type_counts": object_type_counts,
    }

    return {
        "sheet_name": sheet_name,
        "column_mapping": matching_columns,
        "all_objects": dataframe,
        "requirements": requirements,
        "invalid_requirements": invalid_requirements,
        "ignored_objects": ignored_objects,
        "diagnostics": diagnostics,
    }


# ============================================================
# Affichage des résultats
# ============================================================

def display_diagnostics(result: dict) -> None:
    """
    Affiche un résumé lisible du chargement.
    """

    diagnostics = result["diagnostics"]

    print("\n" + "=" * 65)
    print("DIAGNOSTIC DU FICHIER")
    print("=" * 65)

    print(f"Fichier                : {diagnostics['file_name']}")
    print(f"Chemin                 : {diagnostics['file_path']}")
    print(f"Feuille utilisée       : {diagnostics['sheet_name']}")
    print(f"Nombre total de lignes : {diagnostics['total_rows']}")

    print(
        f"Exigences prêtes       : "
        f"{diagnostics['requirements_ready']}"
    )

    print(
        f"Exigences invalides    : "
        f"{diagnostics['invalid_requirements']}"
    )

    print(
        f"Objets ignorés         : "
        f"{diagnostics['ignored_objects']}"
    )

    print("\nContrôles de qualité :")

    print(
        f"  - ID absents         : "
        f"{diagnostics['missing_ids']}"
    )

    print(
        f"  - Textes absents     : "
        f"{diagnostics['missing_texts']}"
    )

    print(
        f"  - Types absents      : "
        f"{diagnostics['missing_object_types']}"
    )

    print(
        f"  - ID dupliqués       : "
        f"{diagnostics['duplicate_ids']}"
    )

    print("\nRépartition par ObjectType :")

    object_type_counts = diagnostics["object_type_counts"]

    if not object_type_counts:
        print("  Aucun type d'objet trouvé.")
    else:
        for object_type, count in object_type_counts.items():
            print(f"  - {object_type}: {count}")


def display_sample(
    result: dict,
    row_count: int = 10,
) -> None:
    """
    Affiche un aperçu des exigences prêtes à être analysées.

    Paramètres :
        result:
            Résultat retourné par load_required_columns().

        row_count:
            Nombre maximal d'exigences à afficher.
    """

    requirements = result["requirements"]

    print("\n" + "=" * 65)
    print(f"APERÇU DES {row_count} PREMIÈRES EXIGENCES")
    print("=" * 65)

    if requirements.empty:
        print("Aucune exigence prête à être analysée.")
        return

    columns_to_display = [
        "ID",
        "Object Heading and Object Text",
        "ObjectType",
        "Source_Excel_Row",
        "Import_Status",
    ]

    # On conserve uniquement les colonnes réellement disponibles.
    existing_columns = [
        column
        for column in columns_to_display
        if column in requirements.columns
    ]

    sample = requirements[
        existing_columns
    ].head(row_count)

    print(
        sample.to_string(
            index=False,
            max_colwidth=80,
        )
    )


def display_invalid_requirements(
    result: dict,
    row_count: int = 20,
) -> None:
    """
    Affiche les exigences qui ne peuvent pas encore être analysées.

    Exemples :
        - ID absent ;
        - texte absent ;
        - identifiant dupliqué.
    """

    invalid_requirements = result["invalid_requirements"]

    print("\n" + "=" * 65)
    print("EXIGENCES INVALIDES")
    print("=" * 65)

    if invalid_requirements.empty:
        print("Aucune exigence invalide détectée.")
        return

    print(
        f"Nombre d'exigences invalides : "
        f"{len(invalid_requirements)}"
    )

    columns_to_display = [
        "ID",
        "Object Heading and Object Text",
        "ObjectType",
        "Source_Excel_Row",
        "Import_Status",
    ]

    existing_columns = [
        column
        for column in columns_to_display
        if column in invalid_requirements.columns
    ]

    print(
        invalid_requirements[existing_columns]
        .head(row_count)
        .to_string(
            index=False,
            max_colwidth=80,
        )
    )

    if len(invalid_requirements) > row_count:
        remaining_rows = (
            len(invalid_requirements) - row_count
        )

        print(
            f"\n... {remaining_rows} autre(s) ligne(s) "
            f"invalide(s) non affichée(s)."
        )


def display_ignored_objects(
    result: dict,
    row_count: int = 10,
) -> None:
    """
    Affiche un aperçu des objets non analysés.

    Ces objets peuvent être des titres, des informations ou des
    lignes sans type. Ils ne sont pas envoyés au moteur d'analyse.
    """

    ignored_objects = result["ignored_objects"]

    print("\n" + "=" * 65)
    print("OBJETS IGNORÉS")
    print("=" * 65)

    if ignored_objects.empty:
        print("Aucun objet ignoré.")
        return

    print(
        f"Nombre d'objets ignorés : "
        f"{len(ignored_objects)}"
    )

    columns_to_display = [
        "ID",
        "Object Heading and Object Text",
        "ObjectType",
        "Source_Excel_Row",
        "Import_Status",
    ]

    existing_columns = [
        column
        for column in columns_to_display
        if column in ignored_objects.columns
    ]

    print(
        ignored_objects[existing_columns]
        .head(row_count)
        .to_string(
            index=False,
            max_colwidth=80,
        )
    )

    if len(ignored_objects) > row_count:
        remaining_rows = (
            len(ignored_objects) - row_count
        )

        print(
            f"\n... {remaining_rows} autre(s) objet(s) "
            f"ignoré(s) non affiché(s)."
        )


def display_loaded_columns(result: dict) -> None:
    """
    Affiche la correspondance entre les colonnes recherchées
    et les colonnes réellement trouvées dans le classeur.
    """

    column_mapping = result["column_mapping"]

    print("\n" + "=" * 65)
    print("COLONNES CHARGÉES")
    print("=" * 65)

    for expected_name, actual_name in column_mapping.items():
        print(
            f"  - Colonne recherchée : {expected_name}\n"
            f"    Colonne trouvée    : {actual_name}"
        )


def display_complete_result(
    result: dict,
    requirement_sample_size: int = 10,
    invalid_sample_size: int = 20,
    ignored_sample_size: int = 10,
) -> None:
    """
    Affiche l'ensemble des informations importantes après
    le chargement du classeur.
    """

    display_loaded_columns(result)

    display_diagnostics(result)

    display_sample(
        result,
        row_count=requirement_sample_size,
    )

    display_invalid_requirements(
        result,
        row_count=invalid_sample_size,
    )

    display_ignored_objects(
        result,
        row_count=ignored_sample_size,
    )


# ============================================================
# Export de contrôle facultatif
# ============================================================

def export_loaded_requirements(
    result: dict,
    output_path: str,
) -> None:
    """
    Exporte les données chargées dans un nouveau classeur Excel.

    Le classeur comporte quatre feuilles :
        - Requirements ;
        - Invalid_Requirements ;
        - Ignored_Objects ;
        - Diagnostics.

    Cet export permet uniquement de contrôler le chargement.
    Il ne modifie jamais le fichier Excel source.
    """

    output_file = Path(output_path).expanduser().resolve()

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    requirements = result["requirements"].copy()
    invalid_requirements = (
        result["invalid_requirements"].copy()
    )
    ignored_objects = result["ignored_objects"].copy()
    diagnostics = result["diagnostics"]

    diagnostics_rows = []

    for key, value in diagnostics.items():
        if key == "object_type_counts":
            continue

        diagnostics_rows.append(
            {
                "Diagnostic": key,
                "Value": str(value),
            }
        )

    for object_type, count in diagnostics[
        "object_type_counts"
    ].items():
        diagnostics_rows.append(
            {
                "Diagnostic": (
                    f"object_type_count::{object_type}"
                ),
                "Value": count,
            }
        )

    diagnostics_dataframe = pd.DataFrame(
        diagnostics_rows
    )

    try:
        with pd.ExcelWriter(
            output_file,
            engine="openpyxl",
        ) as writer:

            requirements.to_excel(
                writer,
                sheet_name="Requirements",
                index=False,
            )

            invalid_requirements.to_excel(
                writer,
                sheet_name="Invalid_Requirements",
                index=False,
            )

            ignored_objects.to_excel(
                writer,
                sheet_name="Ignored_Objects",
                index=False,
            )

            diagnostics_dataframe.to_excel(
                writer,
                sheet_name="Diagnostics",
                index=False,
            )

    except PermissionError as error:
        raise PermissionError(
            "Impossible d'écrire le fichier de sortie. "
            "Vérifie qu'il n'est pas déjà ouvert dans Excel."
        ) from error

    except Exception as error:
        raise ValueError(
            f"Erreur pendant la création du fichier de sortie : "
            f"{error}"
        ) from error

    print("\n" + "=" * 65)
    print("EXPORT DE CONTRÔLE CRÉÉ")
    print("=" * 65)
    print(f"Fichier : {output_file}")


# ============================================================
# Programme principal
# ============================================================

def main() -> None:
    """
    Point d'entrée du programme.

    Le chemin du fichier peut être fourni :
        1. comme argument dans PowerShell ;
        2. manuellement lorsque le programme le demande.
    """

    print("=" * 65)
    print("CHARGEMENT D'UN EXPORT EXCEL DOORS")
    print("=" * 65)

    # Si un argument est présent, il est utilisé comme chemin.
    if len(sys.argv) > 1:
        file_path = sys.argv[1]

    # Sinon, le programme demande le chemin à l'utilisateur.
    else:
        file_path = input(
            "\nChemin du fichier Excel : "
        ).strip()

    # Supprime les guillemets pouvant être ajoutés lors
    # d'un copier-coller du chemin.
    file_path = file_path.strip('"').strip("'")

    if not file_path:
        print("\nErreur : aucun chemin n'a été fourni.")
        sys.exit(1)

    try:
        # Chargement du classeur.
        result = load_required_columns(file_path)

        # Affichage du résultat.
        display_complete_result(
            result,
            requirement_sample_size=10,
            invalid_sample_size=20,
            ignored_sample_size=10,
        )

        print("\n" + "=" * 65)
        print("CHARGEMENT TERMINÉ AVEC SUCCÈS")
        print("=" * 65)

        print(
            "\nLes exigences prêtes sont disponibles dans :"
        )

        print(
            'result["requirements"]'
        )

        print(
            "\nNombre d'exigences prêtes : "
            f"{len(result['requirements'])}"
        )

        # ----------------------------------------------------
        # Export facultatif
        # ----------------------------------------------------

        export_choice = input(
            "\nCréer un fichier Excel de contrôle ? "
            "(o/n) : "
        ).strip().lower()

        if export_choice in {"o", "oui", "y", "yes"}:
            source_path = Path(file_path)

            output_path = (
                source_path.parent
                / f"{source_path.stem}_loaded.xlsx"
            )

            export_loaded_requirements(
                result,
                str(output_path),
            )

        else:
            print(
                "\nAucun fichier de contrôle n'a été créé."
            )

    except FileNotFoundError as error:
        print("\n" + "=" * 65)
        print("FICHIER INTROUVABLE")
        print("=" * 65)
        print(error)
        sys.exit(1)

    except PermissionError as error:
        print("\n" + "=" * 65)
        print("ERREUR D'ACCÈS")
        print("=" * 65)
        print(error)
        sys.exit(1)

    except ValueError as error:
        print("\n" + "=" * 65)
        print("FICHIER NON VALIDE")
        print("=" * 65)
        print(error)
        sys.exit(1)

    except KeyboardInterrupt:
        print(
            "\n\nProgramme interrompu par l'utilisateur."
        )
        sys.exit(1)

    except Exception as error:
        print("\n" + "=" * 65)
        print("ERREUR INATTENDUE")
        print("=" * 65)

        print(
            f"Type : {type(error).__name__}"
        )

        print(
            f"Message : {error}"
        )

        sys.exit(1)


if __name__ == "__main__":
    main()