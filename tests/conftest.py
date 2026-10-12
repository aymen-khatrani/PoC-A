# ============================================================
# Fixtures partagées par les tests
# ============================================================

from pathlib import Path

import pytest

from src.rule_loader import load_rule_catalog
from tests.make_fixtures import main as generate_fixtures

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def fixture_directory() -> Path:
    """Génère les classeurs de test s'ils sont absents."""

    expected = FIXTURE_DIRECTORY / "format_doors.xlsx"

    if not expected.exists():
        generate_fixtures()

    return FIXTURE_DIRECTORY


@pytest.fixture(scope="session")
def rules() -> list:
    """Catalogue de règles réel, chargé une seule fois."""

    return load_rule_catalog("rules")["rules"]
