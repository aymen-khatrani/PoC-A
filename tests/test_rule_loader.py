# ============================================================
# Tests du chargement du catalogue
# ============================================================

import pytest

from src import config
from src.rule_loader import (
    expand_catalog_paths,
    load_rule_catalog,
    load_rules,
)

CATALOG = "rules/rules_en.csv"


class TestChargementCatalogue:
    """Le catalogue livré doit se charger entièrement."""

    def test_toutes_les_regles_sont_chargees(self) -> None:
        result = load_rules(CATALOG)
        diagnostics = result["diagnostics"]

        # Le catalogue était illisible lorsque les champs
        # étaient alignés par des espaces avant les guillemets.
        assert diagnostics["error_count"] == 0
        assert diagnostics["valid_rule_count"] == (
            diagnostics["csv_row_count"]
        )
        assert diagnostics["enabled_rule_count"] > 50

    def test_les_patterns_sont_compiles(self) -> None:
        for rule in load_rules(CATALOG)["rules"]:
            assert rule.compiled_pattern is not None

    def test_alignement_par_espaces_tolere(self, tmp_path) -> None:
        contenu = (
            "rule_id , category , pattern , severity , "
            "explanation , clarification_question , "
            "rewrite_template , enabled\n"
            'TEST-001 , AMBIGUITY , \\bfast\\b , HIGH , '
            '"Too vague, and not measurable." , '
            '"Which limit, and under which conditions?" , '
            "The system shall [TO BE DEFINED]. , true\n"
        )

        path = tmp_path / "aligne.csv"
        path.write_text(contenu, encoding="utf-8")

        result = load_rules(path)

        assert len(result["rules"]) == 1
        assert result["rules"][0].rule_id == "TEST-001"
        assert (
            result["rules"][0].explanation
            == "Too vague, and not measurable."
        )

    def test_gravite_invalide_rejetee(self, tmp_path) -> None:
        contenu = (
            "rule_id,category,pattern,severity,explanation,"
            "clarification_question,rewrite_template,enabled\n"
            "T-1,AMBIGUITY,\\bfast\\b,URGENT,e,q,r,true\n"
        )

        path = tmp_path / "gravite.csv"
        path.write_text(contenu, encoding="utf-8")

        with pytest.raises(ValueError, match="gravité invalide"):
            load_rules(path)

    def test_regex_invalide_rejetee(self, tmp_path) -> None:
        contenu = (
            "rule_id,category,pattern,severity,explanation,"
            "clarification_question,rewrite_template,enabled\n"
            "T-1,AMBIGUITY,[unclosed,HIGH,e,q,r,true\n"
        )

        path = tmp_path / "regex.csv"
        path.write_text(contenu, encoding="utf-8")

        with pytest.raises(ValueError, match="régulière invalide"):
            load_rules(path)


class TestAxeSmart:
    """Chaque règle porte l'axe SMART qu'elle met en défaut."""

    def test_toutes_les_regles_portent_un_axe(self) -> None:
        for rule in load_rules(CATALOG)["rules"]:
            assert rule.smart_dimension in config.SMART_ALLOWED_AXES

    def test_axe_declare_dans_le_catalogue(self) -> None:
        par_identifiant = {
            rule.rule_id: rule
            for rule in load_rules(CATALOG)["rules"]
        }

        # « as soon as possible » est un défaut de délai, pas de
        # mesurabilité : le catalogue le déclare explicitement.
        assert (
            par_identifiant["VER-001"].smart_dimension
            == config.SMART_TIME_BOUND
        )

    def test_axe_deduit_de_la_categorie(self, tmp_path) -> None:
        contenu = (
            "rule_id,category,pattern,severity,explanation,"
            "clarification_question,rewrite_template,enabled\n"
            "T-1,WEAK_OBLIGATION,\\bshould\\b,MEDIUM,e,q,r,true\n"
        )

        path = tmp_path / "sans_axe.csv"
        path.write_text(contenu, encoding="utf-8")

        rule = load_rules(path)["rules"][0]

        assert rule.smart_dimension == config.SMART_ACHIEVABLE

    def test_categorie_inconnue_rattachee_a_l_axe_par_defaut(
        self,
        tmp_path,
    ) -> None:
        contenu = (
            "rule_id,category,pattern,severity,explanation,"
            "clarification_question,rewrite_template,enabled\n"
            "T-1,NOUVELLE_CATEGORIE,\\bfast\\b,HIGH,e,q,r,true\n"
        )

        path = tmp_path / "categorie_inconnue.csv"
        path.write_text(contenu, encoding="utf-8")

        rule = load_rules(path)["rules"][0]

        assert rule.smart_dimension == config.SMART_DEFAULT_DIMENSION

    def test_axe_invalide_rejete(self, tmp_path) -> None:
        contenu = (
            "rule_id,category,pattern,severity,explanation,"
            "clarification_question,rewrite_template,enabled,"
            "smart_dimension\n"
            "T-1,AMBIGUITY,\\bfast\\b,HIGH,e,q,r,true,URGENT\n"
        )

        path = tmp_path / "axe.csv"
        path.write_text(contenu, encoding="utf-8")

        with pytest.raises(ValueError, match="axe SMART invalide"):
            load_rules(path)

    def test_axes_comptes_dans_les_diagnostics(self) -> None:
        diagnostics = load_rule_catalog("rules")["diagnostics"]

        assert diagnostics["smart_axes"]
        assert sum(diagnostics["smart_axes"].values()) == (
            diagnostics["enabled_rule_count"]
        )


class TestCatalogueMultiFichiers:
    """Le catalogue peut être réparti sur plusieurs fichiers."""

    def test_chargement_par_dossier(self) -> None:
        result = load_rule_catalog("rules")

        assert result["diagnostics"]["enabled_rule_count"] > 50
        assert result["rule_origin"]

    def test_doublon_entre_fichiers_detecte(self, tmp_path) -> None:
        ligne = (
            "T-1,AMBIGUITY,\\bfast\\b,HIGH,e,q,r,true\n"
        )
        entete = (
            "rule_id,category,pattern,severity,explanation,"
            "clarification_question,rewrite_template,enabled\n"
        )

        (tmp_path / "a.csv").write_text(entete + ligne, encoding="utf-8")
        (tmp_path / "b.csv").write_text(entete + ligne, encoding="utf-8")

        with pytest.raises(ValueError, match="est définie dans"):
            load_rule_catalog(tmp_path)

    def test_fichier_fourni_deux_fois_sans_erreur(self) -> None:
        chemins = expand_catalog_paths([CATALOG, CATALOG])

        assert len(chemins) == 1
