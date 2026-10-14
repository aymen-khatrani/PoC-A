# ============================================================
# Imports
# ============================================================

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Pattern

import pandas as pd

from src import config


# ============================================================
# Configuration
# ============================================================

REQUIRED_RULE_COLUMNS = [
    "rule_id",
    "category",
    "pattern",
    "severity",
    "explanation",
    "clarification_question",
    "rewrite_template",
    "enabled",
]

# Colonnes facultatives. Leur absence ne bloque pas le
# chargement : la valeur est alors déduite de la catégorie de la
# règle.
OPTIONAL_RULE_COLUMNS = [
    "smart_dimension",
]

ALLOWED_SEVERITIES = set(config.ALLOWED_SEVERITIES)

ALLOWED_SMART_AXES = set(config.SMART_ALLOWED_AXES)

TRUE_VALUES = {
    "true",
    "1",
    "yes",
    "y",
    "oui",
    "o",
    "enabled",
}

FALSE_VALUES = {
    "false",
    "0",
    "no",
    "n",
    "non",
    "disabled",
}

DEFAULT_RULES_PATH = Path("rules/rules_en.csv")


# ============================================================
# Modèle d'une règle
# ============================================================

@dataclass(frozen=True)
class Rule:
    """
    Représente une règle de contrôle qualité chargée depuis
    le fichier CSV.

    L'objet est immutable grâce à frozen=True.
    """

    rule_id: str
    category: str
    pattern: str
    severity: str
    explanation: str
    clarification_question: str
    rewrite_template: str
    enabled: bool
    compiled_pattern: Pattern[str]

    # Axe SMART, ou axe de singularité, mis en défaut par la
    # règle. Résolu au chargement : la colonne du catalogue
    # prime, sinon la catégorie décide.
    smart_dimension: str = config.SMART_DEFAULT_DIMENSION

    def matches(self, text: str) -> bool:
        """
        Indique si la règle détecte au moins une correspondance
        dans le texte fourni.
        """

        if not self.enabled:
            return False

        if text is None:
            return False

        return self.compiled_pattern.search(str(text)) is not None

    def find_matches(self, text: str) -> list[dict]:
        """
        Retourne toutes les correspondances trouvées dans le texte.

        Pour chaque correspondance, la fonction retourne :
        - le passage détecté ;
        - sa position de début ;
        - sa position de fin.
        """

        if not self.enabled:
            return []

        if text is None:
            return []

        text = str(text)
        matches = []

        for match in self.compiled_pattern.finditer(text):
            matches.append(
                {
                    "evidence": match.group(0),
                    "start_position": match.start(),
                    "end_position": match.end(),
                }
            )

        return matches

    def to_dict(self) -> dict:
        """
        Convertit la règle en dictionnaire.

        Le pattern compilé n'est pas inclus, car il ne peut pas
        être directement exporté en JSON ou dans Excel.
        """

        return {
            "rule_id": self.rule_id,
            "category": self.category,
            "pattern": self.pattern,
            "severity": self.severity,
            "explanation": self.explanation,
            "clarification_question": (
                self.clarification_question
            ),
            "rewrite_template": self.rewrite_template,
            "enabled": self.enabled,
            "smart_dimension": self.smart_dimension,
        }


# ============================================================
# Fonctions de normalisation
# ============================================================

def normalize_column_name(value) -> str:
    """
    Normalise le nom d'une colonne.

    Exemple :
        " Rule ID " devient "rule_id"
    """

    if value is None:
        return ""

    normalized = str(value).strip().lower()
    normalized = re.sub(r"\s+", "_", normalized)

    return normalized


def normalize_text(value) -> str:
    """
    Convertit une valeur en texte et retire les espaces inutiles.

    Les valeurs absentes deviennent une chaîne vide.
    """

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip()


def parse_boolean(value, row_number: int) -> bool:
    """
    Convertit différentes représentations textuelles en booléen.

    Valeurs acceptées comme vraies :
        true, 1, yes, y, oui, o, enabled

    Valeurs acceptées comme fausses :
        false, 0, no, n, non, disabled
    """

    normalized_value = normalize_text(value).lower()

    if normalized_value in TRUE_VALUES:
        return True

    if normalized_value in FALSE_VALUES:
        return False

    raise ValueError(
        f"Ligne CSV {row_number} : valeur booléenne invalide "
        f"pour la colonne 'enabled' : {value!r}. "
        f"Valeurs admises : true ou false."
    )


# ============================================================
# Validation de la structure du fichier CSV
# ============================================================

def validate_csv_columns(dataframe: pd.DataFrame) -> None:
    """
    Vérifie que toutes les colonnes obligatoires sont présentes.
    """

    missing_columns = [
        column
        for column in REQUIRED_RULE_COLUMNS
        if column not in dataframe.columns
    ]

    if missing_columns:
        raise ValueError(
            "Le fichier de règles ne contient pas toutes les "
            "colonnes obligatoires.\n"
            "Colonnes absentes : "
            + ", ".join(missing_columns)
        )


def validate_required_value(
    value,
    column_name: str,
    row_number: int,
) -> str:
    """
    Vérifie qu'une valeur obligatoire est renseignée et retourne
    sa version nettoyée.
    """

    normalized_value = normalize_text(value)

    if not normalized_value:
        raise ValueError(
            f"Ligne CSV {row_number} : la colonne "
            f"'{column_name}' est vide."
        )

    return normalized_value


def compile_rule_pattern(
    pattern: str,
    rule_id: str,
    row_number: int,
) -> Pattern[str]:
    """
    Compile une expression régulière en ignorant la casse.

    Une erreur explicite est levée si le pattern est invalide.
    """

    try:
        return re.compile(
            pattern,
            flags=re.IGNORECASE | re.MULTILINE,
        )

    except re.error as error:
        raise ValueError(
            f"Ligne CSV {row_number}, règle '{rule_id}' : "
            f"expression régulière invalide.\n"
            f"Pattern : {pattern}\n"
            f"Erreur : {error}"
        ) from error


def resolve_smart_dimension(
    declared_value,
    category: str,
    rule_id: str,
    row_number: int,
) -> str:
    """
    Détermine l'axe SMART mis en défaut par une règle.

    La colonne smart_dimension du catalogue prime. Quand elle
    est vide ou absente, l'axe est déduit de la catégorie de la
    règle. Une catégorie inconnue est rattachée à l'axe par
    défaut, pour qu'une règle nouvelle soit toujours comptée
    quelque part plutôt que perdue.
    """

    declared = normalize_text(declared_value).upper().replace(
        "-",
        "_",
    )

    if declared:
        if declared not in ALLOWED_SMART_AXES:
            raise ValueError(
                f"Ligne CSV {row_number}, règle '{rule_id}' : "
                f"axe SMART invalide '{declared}'. "
                f"Valeurs admises : "
                f"{', '.join(sorted(ALLOWED_SMART_AXES))}."
            )

        return declared

    return config.CATEGORY_TO_SMART_DIMENSION.get(
        category,
        config.SMART_DEFAULT_DIMENSION,
    )


# ============================================================
# Création d'une règle depuis une ligne CSV
# ============================================================

def build_rule_from_row(
    row: pd.Series,
    row_number: int,
) -> Rule:
    """
    Crée une instance Rule à partir d'une ligne du fichier CSV.
    """

    rule_id = validate_required_value(
        row["rule_id"],
        "rule_id",
        row_number,
    )

    category = validate_required_value(
        row["category"],
        "category",
        row_number,
    ).upper()

    pattern = validate_required_value(
        row["pattern"],
        "pattern",
        row_number,
    )

    severity = validate_required_value(
        row["severity"],
        "severity",
        row_number,
    ).upper()

    explanation = validate_required_value(
        row["explanation"],
        "explanation",
        row_number,
    )

    clarification_question = validate_required_value(
        row["clarification_question"],
        "clarification_question",
        row_number,
    )

    rewrite_template = validate_required_value(
        row["rewrite_template"],
        "rewrite_template",
        row_number,
    )

    enabled = parse_boolean(
        row["enabled"],
        row_number,
    )

    if severity not in ALLOWED_SEVERITIES:
        raise ValueError(
            f"Ligne CSV {row_number}, règle '{rule_id}' : "
            f"gravité invalide '{severity}'. "
            f"Valeurs admises : "
            f"{', '.join(sorted(ALLOWED_SEVERITIES))}."
        )

    compiled_pattern = compile_rule_pattern(
        pattern=pattern,
        rule_id=rule_id,
        row_number=row_number,
    )

    smart_dimension = resolve_smart_dimension(
        declared_value=row.get("smart_dimension", ""),
        category=category,
        rule_id=rule_id,
        row_number=row_number,
    )

    return Rule(
        rule_id=rule_id,
        category=category,
        pattern=pattern,
        severity=severity,
        explanation=explanation,
        clarification_question=clarification_question,
        rewrite_template=rewrite_template,
        enabled=enabled,
        compiled_pattern=compiled_pattern,
        smart_dimension=smart_dimension,
    )


# ============================================================
# Chargement principal
# ============================================================

def load_rules(
    rules_path: str | Path = DEFAULT_RULES_PATH,
    include_disabled: bool = False,
    strict: bool = True,
) -> dict:
    """
    Charge et valide le catalogue de règles.

    Paramètres :
        rules_path:
            Chemin du fichier CSV.

        include_disabled:
            Si False, seules les règles actives sont retournées
            dans la clé "rules".

        strict:
            Si True, une règle invalide bloque le chargement.

            Si False, les règles invalides sont ignorées et leurs
            erreurs sont placées dans "errors".

    Retour :
        {
            "rules": liste des règles utilisables,
            "all_valid_rules": toutes les règles valides,
            "disabled_rules": règles valides désactivées,
            "errors": erreurs rencontrées,
            "diagnostics": statistiques de chargement
        }
    """

    path = Path(rules_path).expanduser().resolve()

    if not path.exists():
        raise FileNotFoundError(
            f"Le fichier de règles est introuvable :\n{path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Le chemin ne correspond pas à un fichier :\n{path}"
        )

    if path.suffix.lower() != ".csv":
        raise ValueError(
            "Le catalogue de règles doit être un fichier CSV."
        )

    try:
        dataframe = pd.read_csv(
            path,
            dtype=object,
            encoding="utf-8-sig",
            keep_default_na=False,
            # Les catalogues sont souvent alignés à la main avec
            # des espaces après les virgules. Sans cette option,
            # un champ aligné perd ses guillemets et le fichier
            # devient illisible.
            skipinitialspace=True,
        )

    except UnicodeDecodeError as error:
        raise ValueError(
            "Le fichier CSV ne semble pas être encodé en UTF-8. "
            "Enregistre rules_en.csv au format UTF-8."
        ) from error

    except pd.errors.EmptyDataError as error:
        raise ValueError(
            "Le fichier de règles est vide."
        ) from error

    except pd.errors.ParserError as error:
        raise ValueError(
            "Le fichier CSV ne peut pas être lu. "
            "Vérifie les virgules, les guillemets et les retours "
            "à la ligne dans le fichier."
        ) from error

    except Exception as error:
        raise ValueError(
            f"Impossible de lire le fichier de règles : {error}"
        ) from error

    # Normalisation des noms de colonnes.
    dataframe.columns = [
        normalize_column_name(column)
        for column in dataframe.columns
    ]

    validate_csv_columns(dataframe)

    # Conservation des colonnes prévues, et des colonnes
    # facultatives réellement présentes dans le fichier.
    retained_columns = REQUIRED_RULE_COLUMNS + [
        column
        for column in OPTIONAL_RULE_COLUMNS
        if column in dataframe.columns
    ]

    dataframe = dataframe[retained_columns].copy()

    all_valid_rules: list[Rule] = []
    errors: list[str] = []

    # La ligne 1 du CSV contient les en-têtes.
    # La première règle est donc située à la ligne 2.
    for dataframe_index, row in dataframe.iterrows():
        csv_row_number = int(dataframe_index) + 2

        try:
            rule = build_rule_from_row(
                row=row,
                row_number=csv_row_number,
            )

            all_valid_rules.append(rule)

        except ValueError as error:
            if strict:
                raise

            errors.append(str(error))

    # Vérification des identifiants dupliqués.
    rule_ids = [rule.rule_id for rule in all_valid_rules]

    duplicate_rule_ids = sorted(
        rule_id
        for rule_id, count in Counter(rule_ids).items()
        if count > 1
    )

    if duplicate_rule_ids:
        duplicate_message = (
            "Identifiants de règles dupliqués : "
            + ", ".join(duplicate_rule_ids)
        )

        if strict:
            raise ValueError(duplicate_message)

        errors.append(duplicate_message)

        # En mode non strict, seule la première occurrence
        # de chaque identifiant est conservée.
        unique_rules = []
        seen_rule_ids = set()

        for rule in all_valid_rules:
            if rule.rule_id in seen_rule_ids:
                continue

            seen_rule_ids.add(rule.rule_id)
            unique_rules.append(rule)

        all_valid_rules = unique_rules

    enabled_rules = [
        rule
        for rule in all_valid_rules
        if rule.enabled
    ]

    disabled_rules = [
        rule
        for rule in all_valid_rules
        if not rule.enabled
    ]

    if include_disabled:
        selected_rules = all_valid_rules
    else:
        selected_rules = enabled_rules

    categories = {}

    for rule in enabled_rules:
        categories[rule.category] = (
            categories.get(rule.category, 0) + 1
        )

    severities = {}

    for rule in enabled_rules:
        severities[rule.severity] = (
            severities.get(rule.severity, 0) + 1
        )

    smart_axes = {}

    for rule in enabled_rules:
        smart_axes[rule.smart_dimension] = (
            smart_axes.get(rule.smart_dimension, 0) + 1
        )

    diagnostics = {
        "file_name": path.name,
        "file_path": str(path),
        "csv_row_count": int(len(dataframe)),
        "valid_rule_count": len(all_valid_rules),
        "enabled_rule_count": len(enabled_rules),
        "disabled_rule_count": len(disabled_rules),
        "returned_rule_count": len(selected_rules),
        "error_count": len(errors),
        "categories": dict(
            sorted(categories.items())
        ),
        "severities": dict(
            sorted(severities.items())
        ),
        "smart_axes": dict(
            sorted(smart_axes.items())
        ),
    }

    return {
        "rules": selected_rules,
        "all_valid_rules": all_valid_rules,
        "disabled_rules": disabled_rules,
        "errors": errors,
        "diagnostics": diagnostics,
    }


# ============================================================
# Chargement d'un catalogue réparti sur plusieurs fichiers
# ============================================================

def expand_catalog_paths(
    paths: list[str | Path] | str | Path,
) -> list[Path]:
    """
    Développe une liste de chemins en liste de fichiers CSV.

    Un dossier est développé en tous les fichiers .csv qu'il
    contient, triés par nom. Cela permet de distribuer le
    catalogue par domaine, par exemple un fichier commun et un
    fichier propre à un client.
    """

    if isinstance(paths, (str, Path)):
        paths = [paths]

    expanded: list[Path] = []

    for item in paths:
        path = Path(item).expanduser().resolve()

        if path.is_dir():
            csv_files = sorted(path.glob("*.csv"))

            if not csv_files:
                raise FileNotFoundError(
                    f"Aucun fichier .csv dans le dossier :\n{path}"
                )

            expanded.extend(csv_files)
            continue

        expanded.append(path)

    # Un même fichier fourni deux fois ne doit pas provoquer
    # une erreur de doublons.
    unique_paths: list[Path] = []

    for path in expanded:
        if path not in unique_paths:
            unique_paths.append(path)

    return unique_paths


def load_rule_catalog(
    paths: list[str | Path] | str | Path = DEFAULT_RULES_PATH,
    include_disabled: bool = False,
    strict: bool = True,
) -> dict:
    """
    Charge un catalogue réparti sur un ou plusieurs fichiers.

    Le retour a la même forme que load_rules, avec en plus la
    liste des fichiers utilisés et l'origine de chaque règle.
    """

    catalog_paths = expand_catalog_paths(paths)

    merged_rules: list[Rule] = []
    all_valid_rules: list[Rule] = []
    disabled_rules: list[Rule] = []
    errors: list[str] = []
    rule_origin: dict[str, str] = {}

    for path in catalog_paths:
        result = load_rules(
            rules_path=path,
            include_disabled=include_disabled,
            strict=strict,
        )

        for rule in result["all_valid_rules"]:
            previous_file = rule_origin.get(rule.rule_id)

            if previous_file is not None:
                message = (
                    f"La règle {rule.rule_id!r} est définie dans "
                    f"{previous_file} et dans {path.name}."
                )

                if strict:
                    raise ValueError(message)

                errors.append(message)
                continue

            rule_origin[rule.rule_id] = path.name
            all_valid_rules.append(rule)

            if rule.enabled:
                merged_rules.append(rule)
            else:
                disabled_rules.append(rule)

                if include_disabled:
                    merged_rules.append(rule)

        errors.extend(result["errors"])

    categories: dict[str, int] = {}
    severities: dict[str, int] = {}
    smart_axes: dict[str, int] = {}

    for rule in all_valid_rules:
        if not rule.enabled:
            continue

        categories[rule.category] = (
            categories.get(rule.category, 0) + 1
        )
        severities[rule.severity] = (
            severities.get(rule.severity, 0) + 1
        )
        smart_axes[rule.smart_dimension] = (
            smart_axes.get(rule.smart_dimension, 0) + 1
        )

    diagnostics = {
        "file_name": ", ".join(path.name for path in catalog_paths),
        "file_path": ", ".join(str(path) for path in catalog_paths),
        "file_count": len(catalog_paths),
        "csv_row_count": len(all_valid_rules),
        "valid_rule_count": len(all_valid_rules),
        "enabled_rule_count": len(
            [rule for rule in all_valid_rules if rule.enabled]
        ),
        "disabled_rule_count": len(disabled_rules),
        "returned_rule_count": len(merged_rules),
        "error_count": len(errors),
        "categories": dict(sorted(categories.items())),
        "severities": dict(sorted(severities.items())),
        "smart_axes": dict(sorted(smart_axes.items())),
    }

    return {
        "rules": merged_rules,
        "all_valid_rules": all_valid_rules,
        "disabled_rules": disabled_rules,
        "errors": errors,
        "diagnostics": diagnostics,
        "catalog_paths": catalog_paths,
        "rule_origin": rule_origin,
    }


# ============================================================
# Fonctions de recherche de règles
# ============================================================

def get_rule_by_id(
    rules: list[Rule],
    rule_id: str,
) -> Rule | None:
    """
    Recherche une règle par son identifiant.
    """

    normalized_rule_id = normalize_text(rule_id).upper()

    for rule in rules:
        if rule.rule_id.upper() == normalized_rule_id:
            return rule

    return None


def get_rules_by_category(
    rules: list[Rule],
    category: str,
) -> list[Rule]:
    """
    Retourne les règles correspondant à une catégorie donnée.
    """

    normalized_category = normalize_text(category).upper()

    return [
        rule
        for rule in rules
        if rule.category.upper() == normalized_category
    ]

def get_rules_by_severity(
    rules: list[Rule],
    severity: str,
) -> list[Rule]:
    """
    Retourne les règles correspondant à un niveau de gravité.
    """

    normalized_severity = normalize_text(severity).upper()

    if normalized_severity not in ALLOWED_SEVERITIES:
        raise ValueError(
            f"Gravité inconnue : {severity}. "
            f"Valeurs admises : "
            f"{', '.join(sorted(ALLOWED_SEVERITIES))}."
        )

    return [
        rule
        for rule in rules
        if rule.severity == normalized_severity
    ]


# ============================================================
# Affichage des diagnostics
# ============================================================

def display_rule_diagnostics(result: dict) -> None:
    """
    Affiche un résumé du chargement des règles.
    """

    diagnostics = result["diagnostics"]

    print("\n" + "=" * 65)
    print("DIAGNOSTIC DU CATALOGUE DE RÈGLES")
    print("=" * 65)

    print(
        f"Fichier                : "
        f"{diagnostics['file_name']}"
    )

    print(
        f"Lignes dans le CSV     : "
        f"{diagnostics['csv_row_count']}"
    )

    print(
        f"Règles valides         : "
        f"{diagnostics['valid_rule_count']}"
    )

    print(
        f"Règles actives         : "
        f"{diagnostics['enabled_rule_count']}"
    )

    print(
        f"Règles désactivées     : "
        f"{diagnostics['disabled_rule_count']}"
    )

    print(
        f"Règles retournées      : "
        f"{diagnostics['returned_rule_count']}"
    )

    print(
        f"Erreurs                : "
        f"{diagnostics['error_count']}"
    )

    print("\nRépartition par catégorie :")

    if not diagnostics["categories"]:
        print("  Aucune catégorie.")

    for category, count in diagnostics[
        "categories"
    ].items():
        print(f"  - {category}: {count}")

    print("\nRépartition par gravité :")

    if not diagnostics["severities"]:
        print("  Aucun niveau de gravité.")

    for severity, count in diagnostics[
        "severities"
    ].items():
        print(f"  - {severity}: {count}")

    if result["errors"]:
        print("\nErreurs rencontrées :")

        for error in result["errors"]:
            print(f"  - {error}")


def display_rule_sample(
    rules: list[Rule],
    limit: int = 10,
) -> None:
    """
    Affiche un aperçu des premières règles chargées.
    """

    print("\n" + "=" * 65)
    print(f"APERÇU DES {limit} PREMIÈRES RÈGLES")
    print("=" * 65)

    if not rules:
        print("Aucune règle chargée.")
        return

    for rule in rules[:limit]:
        print(
            f"\n{rule.rule_id}"
            f" | {rule.category}"
            f" | {rule.severity}"
        )

        print(f"Pattern     : {rule.pattern}")
        print(f"Explication : {rule.explanation}")


# ============================================================
# Test autonome du chargeur
# ============================================================

def main() -> None:
    """
    Permet de tester directement le fichier rule_loader.py.

    Commande :
        python -m src.rule_loader

    Ou :
        python src/rule_loader.py
    """

    print("=" * 65)
    print("CHARGEMENT DU CATALOGUE DE RÈGLES")
    print("=" * 65)

    try:
        result = load_rules(
            rules_path=DEFAULT_RULES_PATH,
            include_disabled=False,
            strict=True,
        )

        display_rule_diagnostics(result)

        display_rule_sample(
            rules=result["rules"],
            limit=10,
        )

        print("\n" + "=" * 65)
        print("CATALOGUE CHARGÉ AVEC SUCCÈS")
        print("=" * 65)

    except (
        FileNotFoundError,
        ValueError,
        PermissionError,
    ) as error:
        print("\n" + "=" * 65)
        print("ERREUR DE CHARGEMENT")
        print("=" * 65)
        print(error)

        raise SystemExit(1) from error


if __name__ == "__main__":
    main()