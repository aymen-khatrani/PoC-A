# ============================================================
# Génération de classeurs de test hétérogènes
# ============================================================
#
# Ces fichiers simulent la diversité réelle des exports client :
# noms de colonnes différents, en-tête décalé, feuilles
# parasites, absence d'identifiant, absence de type, intitulé
# et corps séparés, export CSV, autre langue.
#
# Exécution :
#     python -m tests.make_fixtures
#
# ============================================================

from __future__ import annotations

from pathlib import Path

import pandas as pd

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"

GOOD_REQUIREMENTS = [
    "The braking system shall stop the train within 250 m from "
    "80 km/h on dry rails, verified by test procedure TP-14.",
    "The supplier shall deliver the maintenance manual in PDF "
    "format before the Factory Acceptance Test.",
    "The cabinet shall weigh 45 kg plus or minus 2 kg, measured "
    "with a calibrated scale.",
    "The door shall open when the train speed is 0 km/h and the "
    "platform side is detected by sensor S12.",
]

BAD_REQUIREMENTS = [
    "The system should respond rapidly and be user-friendly.",
    "The equipment shall be maximally modular and maintained as "
    "quickly as possible.",
    "The interface shall be robust and handle errors "
    "appropriately, if necessary.",
    "The supplier shall provide adequate documentation and "
    "support as required.",
]


def build_rows() -> list[dict[str, str]]:
    """Construit un jeu mixte d'exigences et d'éléments ignorés."""

    rows: list[dict[str, str]] = []

    rows.append(
        {
            "identifier": "1",
            "heading": "SAFETY REQUIREMENTS",
            "text": "",
            "type": "Heading",
            "expected": "NO",
        }
    )

    for position, text in enumerate(GOOD_REQUIREMENTS, start=1):
        rows.append(
            {
                "identifier": f"CUS-{100 + position}",
                "heading": f"Function {position}",
                "text": text,
                "type": "Technical Req",
                "expected": "NO",
            }
        )

    for position, text in enumerate(BAD_REQUIREMENTS, start=1):
        rows.append(
            {
                "identifier": f"CUS-{200 + position}",
                "heading": f"Performance {position}",
                "text": text,
                "type": (
                    "Technical Req"
                    if position % 2
                    else "Non-Technical Req"
                ),
                "expected": "YES",
            }
        )

    rows.append(
        {
            "identifier": "2",
            "heading": "Reference documents",
            "text": "See the applicable standards list.",
            "type": "Information",
            "expected": "NO",
        }
    )

    return rows


def write_doors_like(path: Path, rows: list[dict[str, str]]) -> None:
    """Format proche de l'export DOORS d'origine."""

    frame = pd.DataFrame(
        [
            {
                "ID": row["identifier"],
                "Object Heading and Object Text": (
                    f"{row['heading']}\n{row['text']}".strip()
                ),
                "ObjectType": row["type"],
                "Expected_Flag": row["expected"],
            }
            for row in rows
        ]
    )

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame({"Note": ["Feuille de garde"]}).to_excel(
            writer,
            sheet_name="Cover",
            index=False,
        )
        frame.to_excel(writer, sheet_name="ViewRich", index=False)


def write_renamed_columns(path: Path, rows: list[dict[str, str]]) -> None:
    """Noms de colonnes totalement différents, en-tête décalé."""

    frame = pd.DataFrame(
        [
            {
                "Req. ID": row["identifier"],
                "Requirement Description": row["text"] or row["heading"],
                "Requirement Category": row["type"],
                "Expected_Flag": row["expected"],
            }
            for row in rows
        ]
    )

    # Trois lignes de métadonnées au-dessus de l'en-tête réel.
    preamble = pd.DataFrame(
        [
            ["Customer specification export", None, None, None],
            ["Project PKP - confidential", None, None, None],
            [None, None, None, None],
        ]
    )

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        preamble.to_excel(
            writer,
            sheet_name="Specification",
            index=False,
            header=False,
        )
        frame.to_excel(
            writer,
            sheet_name="Specification",
            index=False,
            startrow=3,
        )


def write_no_id_no_type(path: Path, rows: list[dict[str, str]]) -> None:
    """Ni identifiant, ni type : uniquement du texte."""

    frame = pd.DataFrame(
        [
            {
                "Statement": row["text"] or row["heading"],
                "Expected_Flag": row["expected"],
            }
            for row in rows
        ]
    )

    frame.to_excel(path, sheet_name="Sheet1", index=False)


def write_split_heading(path: Path, rows: list[dict[str, str]]) -> None:
    """Intitulé et corps dans deux colonnes distinctes."""

    frame = pd.DataFrame(
        [
            {
                "Object Identifier": row["identifier"],
                "Object Heading": row["heading"],
                "Object Text": row["text"],
                "Type": row["type"],
                "Expected_Flag": row["expected"],
            }
            for row in rows
        ]
    )

    frame.to_excel(path, sheet_name="Exigences", index=False)


def write_french(path: Path) -> None:
    """Export rédigé en français, pour tester l'avertissement."""

    frame = pd.DataFrame(
        [
            {
                "Identifiant": "FR-001",
                "Libellé exigence": (
                    "Le système doit démarrer rapidement et rester "
                    "convivial pour les opérateurs de maintenance."
                ),
                "Type exigence": "Exigence technique",
            },
            {
                "Identifiant": "FR-002",
                "Libellé exigence": (
                    "Le fournisseur doit livrer la documentation "
                    "complète avant la recette usine."
                ),
                "Type exigence": "Exigence contractuelle",
            },
        ]
    )

    frame.to_excel(path, sheet_name="Feuil1", index=False)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    """Export CSV avec point-virgule."""

    frame = pd.DataFrame(
        [
            {
                "Key": row["identifier"],
                "Requirement": row["text"] or row["heading"],
                "Kind": row["type"],
                "Expected_Flag": row["expected"],
            }
            for row in rows
        ]
    )

    frame.to_csv(path, sep=";", index=False, encoding="utf-8")


def main() -> None:
    """Génère tous les fichiers de test."""

    FIXTURE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    rows = build_rows()

    write_doors_like(
        FIXTURE_DIRECTORY / "format_doors.xlsx",
        rows,
    )
    write_renamed_columns(
        FIXTURE_DIRECTORY / "format_colonnes_renommees.xlsx",
        rows,
    )
    write_no_id_no_type(
        FIXTURE_DIRECTORY / "format_sans_id_ni_type.xlsx",
        rows,
    )
    write_split_heading(
        FIXTURE_DIRECTORY / "format_intitule_separe.xlsx",
        rows,
    )
    write_french(FIXTURE_DIRECTORY / "format_francais.xlsx")
    write_csv(FIXTURE_DIRECTORY / "format_csv.csv", rows)

    for item in sorted(FIXTURE_DIRECTORY.iterdir()):
        print(f"créé : {item.name}")


if __name__ == "__main__":
    main()
