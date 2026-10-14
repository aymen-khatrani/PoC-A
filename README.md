# Contrôleur de qualité des exigences

Analyse la qualité rédactionnelle d'un export d'exigences client
et produit un rapport Excel exploitable en revue.

Chaque exigence est évaluée sur les cinq axes **SMART** et sur le
principe de **singularité** : un énoncé, une exigence.

L'outil combine trois niveaux, dans cet ordre de responsabilité :

```text
Moteur de règles  ->  détecte et prouve
LLM local         ->  contextualise et suggère
Humain            ->  décide et valide
```

> C'est une aide à la revue. L'outil ne modifie jamais le texte du
> client, n'invente aucune valeur, n'ouvre aucun risque et
> n'envoie rien au client sans validation humaine.

---

## 1. Ce que l'outil accepte en entrée

N'importe quel tableau d'exigences, sans configuration préalable :

| Variabilité du fichier client | Traitement |
|---|---|
| Noms de colonnes quelconques | Détectés par alias, en français et en anglais |
| Plusieurs feuilles, feuilles parasites | La feuille dont l'en-tête est le plus reconnaissable est retenue |
| En-tête précédé d'un titre ou d'un logo | Ligne d'en-tête réelle détectée dans les 20 premières lignes |
| Absence de colonne d'identifiant | Identifiants `ROW-<ligne Excel>` générés, avec avertissement |
| Absence de colonne de type | Les intitulés sont repérés par heuristique de texte |
| Intitulé et corps dans deux colonnes | Les deux sont analysés ensemble |
| Vocabulaire de types inconnu | Tout type inconnu est analysé, seule la structure documentaire est écartée |
| Identifiants dupliqués | Conservés, analysés et signalés |
| Export CSV ou texte délimité | Séparateur détecté automatiquement |
| Texte rédigé dans une autre langue | Analysé, avec avertissement explicite |
| Style télégraphique ou tabulaire | Analysé, signalé comme style d'écriture et non comme problème de langue |

Formats de fichier : `.xlsx`, `.xlsm`, `.csv`, `.tsv`, `.txt`.

Chaque détection automatique peut être forcée en ligne de commande.
**Aucune ligne n'est écartée en silence** : toute ligne non analysée
figure dans la feuille `Excluded_Rows` du rapport avec son motif.

---

## 2. Installation

```bash
python -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

Sous Windows PowerShell, sans activer l'environnement :

```powershell
& "C:\Program Files\Python314\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Pour l'analyse LLM, en plus :

```bash
ollama pull qwen2.5:3b
```

Le mode règles seules **ne nécessite pas** Ollama ni le paquet
`ollama` : l'import n'a lieu que si `--llm` est demandé.

---

## 3. Utilisation

### Analyse par règles

```bash
python run_analysis.py -i mon_export.xlsx
```

Le rapport est écrit dans `data/output/` avec un horodatage. Il
s'ouvre sur la page `1. Synthese`, qui tient en un écran ; le
détail suit dans les pages suivantes.

### Forcer une colonne mal détectée

```bash
python run_analysis.py -i export.xlsx \
    --text-column "Requirement Description" \
    --id-column "Req. ID"
```

### Choisir ce qui est analysé

```bash
# uniquement certains types
python run_analysis.py -i export.xlsx --include-types "Technical Req" "SYS-REQ"

# tout sauf certains types
python run_analysis.py -i export.xlsx --exclude-types "Information" "Figure"
```

La comparaison ignore la casse et les accents. Pour éviter qu'un
filtre `Technical Req` attrape aussi `Non-Technical Req`, la
correspondance partielle n'est acceptée qu'en préfixe de mot.

### Ajouter le LLM sur les cas prioritaires

```bash
python run_analysis.py -i export.xlsx --llm --llm-limit 20
```

Les exigences sont classées par gravité puis par score qualité
croissant : les plus douteuses passent en premier. `--llm-limit -1`
envoie tout, `--llm-include-clean` envoie aussi les exigences sans
alerte en revue contextuelle complète.

### Mesurer la performance

```bash
# méthode recommandée : une colonne d'attendu avec des cas corrects
python evaluate.py -i reference.xlsx --expected-column Expected_Flag

# ou une liste d'identifiants problématiques
python evaluate.py -i export.xlsx --ids-file cas_manager.txt
```

### Options complètes

```bash
python run_analysis.py --help
python evaluate.py --help
```

---

## 4. Structure du projet

```text
.
|-- run_analysis.py          pipeline complet : import, règles, LLM, rapport
|-- evaluate.py              mesure précision, rappel, F1 sur un jeu de référence
|
|-- src/
|   |-- config.py            tous les réglages : alias, seuils, gravités
|   |-- text_utils.py        normalisation, détection de rôle, heuristiques
|   |-- excel_loader.py      import génerique d'un fichier client
|   |-- rule_loader.py       chargement et validation du catalogue
|   |-- rule_engine.py       application des règles, score, risque
|   |-- smart_evaluator.py   axes SMART et singularité de l'exigence
|   |-- llm_analyzer.py      analyse contextuelle Ollama
|   |-- reporting.py         écriture et mise en forme des rapports
|
|-- rules/
|   |-- rules_en.csv         catalogue de 83 règles
|
|-- tests/
|   |-- make_fixtures.py     génère 8 classeurs de test hétérogènes
|   |-- conftest.py
|   |-- test_*.py            204 tests
|
|-- data/input/              fichiers à analyser
|-- data/output/             rapports produits
```

Pour ajouter le support d'un nouveau format client, il suffit en
général d'ajouter un alias dans `src/config.py`. Aucun nom de
colonne n'est codé en dur ailleurs.

---

## 5. Catalogue de règles

`rules/rules_en.csv`, 8 colonnes obligatoires et 1 facultative :

```text
rule_id, category, pattern, severity, explanation,
clarification_question, rewrite_template, enabled,
smart_dimension
```

`smart_dimension` déclare l'axe SMART mis en défaut par la règle :
`SPECIFIC`, `MEASURABLE`, `ACHIEVABLE`, `RELEVANT`, `TIME_BOUND`
ou `SINGULARITY`. Laissée vide, ou absente du fichier, elle est
déduite de la catégorie via `CATEGORY_TO_SMART_DIMENSION` dans
`src/config.py`. Une règle nouvelle est donc toujours rattachée à
un axe, sans modifier le code.

Catégories : `AMBIGUITY`, `NOT_VERIFIABLE`, `INCOMPLETE`,
`UNDEFINED_CONDITION`, `UNDEFINED_REFERENCE`, `UNDEFINED_QUANTITY`,
`WEAK_OBLIGATION`, `POTENTIALLY_NON_ATOMIC`, `MISSING_ACTOR`,
`MISSING_UNIT_OR_LIMIT`, `MISSING_TOLERANCE`,
`MISSING_VERIFICATION_CRITERIA`.

Gravités : `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.

Répartition actuelle : 83 règles actives, 34 `HIGH`, 44 `MEDIUM`,
5 `LOW`, aucune `CRITICAL`.

Le catalogue peut être réparti sur plusieurs fichiers, par exemple
un socle commun et un fichier par client :

```bash
python run_analysis.py -i export.xlsx --rules rules/ mon_client/regles.csv
```

Un identifiant défini deux fois est signalé avec le nom des deux
fichiers concernés.

Une règle est un **signal de revue**, jamais une décision de
non-conformité.

---

## 6. Interprétation du rapport

Le rapport est hiérarchisé : les trois premières feuilles sont
faites pour être lues, les suivantes pour être auditées. Rien
n'est supprimé, tout est rangé.

| Feuille | Pour qui | Contenu |
|---|---|---|
| `1. Synthese` | tout le monde | Le bilan du lot en une page : ce qui a été lu, **ce qui a été écarté**, ce que vaut le lot, où il pèche, comment lire la suite |
| `2. Exigences` | l'ingénieur | Une ligne par exigence, triée par priorité : texte, verdict, profil SMART, unicité, action attendue |
| `3. Detail SMART` | l'ingénieur | Une ligne par couple exigence / axe en défaut : preuve, question à poser, patron de reformulation |
| `4. Questions client` | le client, après validation | Les questions à poser, le texte du client avec les passages en cause encadrés, et trois colonnes vides pour tracer la validation humaine |
| `5. Risques` | le responsable exigences | Les brouillons de risque à ouvrir, avec les axes en défaut et les colonnes de décision |

La page de synthèse ne contient aucun identifiant d'exigence,
aucune preuve brute et aucune constante technique : c'est une page
de décision, pas une page de données. Elle annonce aussi le
nombre de lignes lues et écartées, les identifiants générés ou
dupliqués et les avertissements d'import : un rapport qui annonce
huit exigences sans dire que le fichier en contenait dix ne permet
pas de juger du périmètre analysé.

### Ce que l'outil propose, et ce qu'il ne propose pas

C'est la distinction la plus importante du rapport.

| Colonne | Ce que c'est |
|---|---|
| `Texte du client (passages en cause encadrés)` | **Le texte du client, intact**, avec les passages détectés encadrés par `《 》`. Aucun mot ajouté, retiré ou déplacé. |
| `Patron de reformulation` | Un **patron** issu de la règle, pas une réécriture de l'exigence. Il montre la forme attendue, avec des marqueurs à compléter. |
| `Reformulation du modèle` | La seule véritable reformulation, produite par le LLM quand il est activé. Brouillon soumis à validation. |
| `Questions à poser` | Les questions de clarification, directement envoyables au client après validation. |
| `Brouillon de risque` | Un risque factuel : axes en défaut, passages relevés, verdict d'unicité. Aucun seuil, coût ni délai inventé. |

Sans `--llm`, l'outil ne réécrit donc pas les exigences : il montre
précisément où le défaut se trouve, formule la question à poser, et
propose la forme attendue. C'est volontaire : réécrire une exigence
demande de connaître l'information manquante, et l'inventer serait
la faute la plus grave que cet outil puisse commettre.

### Doublons de texte

Le chargeur signale les **identifiants** dupliqués. Le moteur
signale le cas inverse, plus coûteux en revue : deux identifiants
distincts qui portent la même exigence.

| `Duplicate_Status` | Détection |
|---|---|
| `IDENTICAL` | textes identiques après normalisation de la casse, des accents, de la ponctuation et des espaces |
| `SIMILAR` | même ensemble de mots dans un ordre différent, au-delà de six mots significatifs |

Aucune exigence n'est désignée comme l'originale : les membres d'un
groupe se citent mutuellement, et le choix de celle à conserver
revient à l'ingénieur. Le statut d'un doublon est relevé à
`REVIEW_REQUIRED` : corriger deux fois le même texte est du travail
perdu.

### La grille SMART

Les cinq axes pèsent le même poids, vingt points chacun, pour un
score de 0 à 100 :

| Axe | Question posée | Catégories de règles rattachées |
|---|---|---|
| **S** Spécifique | Un acteur, une action, un objet, sans ambiguïté ? | `AMBIGUITY`, `MISSING_ACTOR`, `UNDEFINED_REFERENCE`, `UNDEFINED_CONDITION` |
| **M** Mesurable | Un résultat quantifié et vérifiable par un essai ? | `NOT_VERIFIABLE`, `UNDEFINED_QUANTITY`, `MISSING_UNIT_OR_LIMIT`, `MISSING_TOLERANCE`, `MISSING_VERIFICATION_CRITERIA` |
| **A** Atteignable | Une obligation ferme et techniquement tenable ? | `WEAK_OBLIGATION`, objectifs absolus |
| **R** Pertinente | Une exigence complète, rattachable à un besoin ? | `INCOMPLETE` |
| **T** Temporellement définie | Un délai, une durée ou une fréquence chiffrés ? | règles de délai déclarées `TIME_BOUND` |

Le verdict d'un axe vient de la gravité la plus élevée constatée
sur cet axe : `HIGH` ou `CRITICAL` donnent `NOT_MET` (0 point),
`MEDIUM` ou `LOW` donnent `TO_CHECK` (10 points), l'absence de
constat donne `OK` (20 points).

Un axe `OK` signifie que le catalogue déterministe n'a rien trouvé
à reprocher à l'exigence sur cet axe. Ce n'est pas un satisfecit :
la revue d'ingénierie reste requise, et la synthèse le dit.

### La singularité

Une exigence doit exprimer **une seule obligation**. Deux
obligations dans un même énoncé rendent la vérification partielle
impossible à tracer : l'une peut être satisfaite et l'autre non,
sans qu'aucun statut ne puisse le dire.

| Verdict | Déclenché par |
|---|---|
| `TO_SPLIT` | plusieurs verbes d'obligation **de même forme**, ou une énumération à puces ou numérotée |
| `TO_CHECK` | des verbes d'obligation de formes différentes, un connecteur additif, un chapelet de points-virgules, ou un constat `POTENTIALLY_NON_ATOMIC` |
| `UNIQUE` | aucun de ces signaux |

Deux garde-fous évitent de condamner une exigence correcte :

- **une obligation citée n'est pas une exigence de plus.** Dans
  `The supplier shall comply with clause 7.2, which states that the
  equipment must be painted.`, le `must` rappelle une obligation
  définie ailleurs. Les marqueurs de citation sont listés dans
  `SINGULARITY_CITATION_PATTERN` ;
- **des modaux mêlés appellent la prudence.** `shall` puis `must`
  dans un même énoncé trahissent plus souvent une citation ou un
  style mélangé que deux exigences : le verdict reste `TO_CHECK`.

Les seuils sont regroupés dans `SingularitySettings`
(`src/config.py`) et peuvent être resserrés sans toucher au code.

La singularité n'entre pas dans le score SMART : elle ne qualifie
pas la rédaction, elle dit combien d'exigences l'énoncé contient.
En revanche, une exigence `TO_SPLIT` ne peut pas rester
`PRE_ANALYSIS_OK` : son statut est relevé à `REVIEW_REQUIRED`.

Le découpage n'est jamais fait à la place de l'ingénieur. L'outil
compte, prouve, et demande.

### Feuille `Analysis_Results`

Une ligne par exigence.

| Colonne | Signification |
|---|---|
| `Quality_Status` | `PRE_ANALYSIS_OK`, `REVIEW_RECOMMENDED`, `REVIEW_REQUIRED`, `CLARIFICATION_REQUIRED`, `NOT_ANALYSED` |
| `Quality_Score` | 0 à 100, pénalisé **une seule fois par règle** |
| `SMART_Score` | 0 à 100, vingt points par axe |
| `SMART_Profile` | Les cinq axes en une colonne, par exemple `S:OK M:KO A:OK R:OK T:?` |
| `SMART_Specific` … `SMART_Time_Bound` | Verdict de chaque axe : `OK`, `TO_CHECK`, `NOT_MET`, `NOT_ASSESSED` |
| `Singularity_Status` | `UNIQUE`, `TO_CHECK`, `TO_SPLIT`, `NOT_ASSESSED` |
| `Estimated_Requirement_Count` | Nombre d'exigences que l'énoncé semble contenir |
| `Recommended_Action` | L'action attendue, en une phrase |
| `Issue_Count` | Nombre de règles distinctes déclenchées |
| `Occurrence_Count` | Nombre total de correspondances |
| `Evidence` | Passages exacts qui ont déclenché les règles |
| `Risk_To_Assess` | Un risque projet mérite d'être examiné |
| `LLM_Decision` | `CONFIRMED`, `PARTIALLY_CONFIRMED`, `FALSE_POSITIVE`, `NEEDS_EXPERT_REVIEW`, `ERROR`, `NOT_RUN` |

`Issue_Count` et `Occurrence_Count` sont distincts à dessein : une
exigence qui répète dix fois le même mot vague n'a pas dix défauts,
elle en a un. Le score suit la même logique.

`NOT_RUN` signifie que le modèle n'a pas été consulté. Une absence
d'avis ne doit jamais être lue comme un avis favorable.

### Autres feuilles

| Feuille | Contenu |
|---|---|
| `Rule_Findings` | Une ligne par occurrence, avec preuve, position et axe SMART |
| `Excluded_Rows` | Toute ligne non analysée, avec son motif |
| `Diagnostics` | Import, catalogue, moteur, LLM |
| `Run_Information` | Fichiers, colonnes retenues, modèle, durée |
| `Rules_Used` | Catalogue effectivement appliqué |

---

## 7. Fiabilité de l'analyse LLM

Quatre mécanismes, dans l'ordre où ils agissent :

**1. Constats dédupliqués avant l'appel.** Les occurrences sont
regroupées par `rule_id`, avec leurs preuves en liste. Envoyer deux
fois le même identifiant conduisait le modèle à répondre deux fois,
ce que le contrôle de cohérence rejetait : toute la réponse était
perdue. C'était la cause principale des échecs sur les exigences
longues.

**2. Sortie contrainte par un schéma JSON.** Le schéma est transmis
à Ollama via `format`, avec les identifiants de règles attendus en
énumération. Le modèle ne peut structurellement ni tronquer sa
réponse, ni commenter, ni inventer une règle.

**3. Décision calculée en Python.** La décision globale est déduite
des valeurs `issue_present`, jamais demandée au modèle. Cela évite
qu'un constat soit rejeté avec une justification qui, en réalité,
confirmait le problème.

**4. Une seule reprise.** En cas d'échec, une seconde tentative est
lancée avec `temperature` à 0, `num_predict` augmenté de 30 % et
`repeat_penalty` à 1.15. Jamais plus d'une reprise, jamais de
boucle. La réponse brute est conservée dans le rapport.

### Prompt indépendant du domaine

Le prompt ne contient plus aucun exemple métier. Une version
précédente citait un cas de temps de réponse, et le modèle
réutilisait ensuite des notions de délai ou de déclencheur sur des
exigences sans aucun rapport. Les consignes passent par une grille
abstraite : acteur, obligation, action, objet, portée, conditions,
quantification, unités, tolérances, vérification, atomicité,
références, cohérence.

### Règles de sécurité fonctionnelle

Le modèle ne doit jamais modifier le texte original, inventer une
valeur, un seuil, une norme, une version, un acteur ou une date,
transformer une préférence en engagement contractuel, valider une
reformulation, ouvrir un risque ou communiquer avec le client.

Les valeurs inconnues restent dans des marqueurs descriptifs :

```text
[MAXIMUM RESPONSE TIME TO BE CONFIRMED]
[COMPONENTS TO BE DEFINED]
[ACCEPTANCE CRITERION TO BE DEFINED]
```

et non `[VALUE TO BE CONFIRMED]`, trop vague pour être actionnable.

---

## 8. Mesurer la performance honnêtement

`evaluate.py` produit des indicateurs séparés, parce qu'ils
répondent à des questions différentes :

| Indicateur | Question |
|---|---|
| `Rule_Engine` | Que trouvent les règles seules ? |
| `LLM_Business_On_Success` | Que dit le modèle, sur ses réponses exploitables ? |
| `End_To_End` | Que trouve la chaîne complète ? |
| `technical_success_rate` | Quelle part des appels aboutit techniquement ? |

Deux règles de méthode appliquées dans le code :

- **Une erreur technique n'est pas une détection.** `ERROR` et
  `NEEDS_EXPERT_REVIEW` ne sont jamais comptés comme des défauts
  trouvés. Compter `NEEDS_EXPERT_REVIEW` comme un succès gonflait
  artificiellement le rappel du modèle.
- **Sans cas corrects, la précision n'existe pas.** Un jeu de
  référence uniquement composé de cas problématiques mesure le
  rappel et rien d'autre. Le rapport affiche alors explicitement
  « précision non mesurable » au lieu d'un chiffre trompeur.

Jeu de référence cible : **10 cas problématiques et 10 cas
considérés correctement rédigés**, validés par le métier.

---

## 9. Tests

```bash
./.venv/bin/python -m pytest
```

129 tests, sans aucun appel réseau : le LLM est testé via un client
factice.

Les classeurs de test couvrent sept présentations (DOORS, colonnes
renommées avec en-tête décalé, sans identifiant ni type, intitulé
séparé, CSV à point-virgule, anglais télégraphique, français). Le
pipeline doit produire le même résultat analytique pour les quatre
formats équivalents : c'est le test qui garantit la généricité.

Pour régénérer les fixtures :

```bash
./.venv/bin/python -m tests.make_fixtures
```

---

## 10. Performance observée

### Moteur de règles

2 000 lignes désordonnées, dont des textes très longs, des lignes
vides, des types inconnus et des identifiants dupliqués :

```text
Lecture + analyse + rapport Excel : environ 1,5 s
Analyse seule                     : 0,11 s, soit 0,09 ms par exigence
```

Le moteur peut donc traiter l'intégralité d'un export sans
sélection préalable.

### LLM local

Avec `qwen2.5:3b`, environ 11 à 16 tokens par seconde sur machine
de bureau, soit **26 à 53 secondes par exigence**. Estimation :

```text
100 exigences    : environ 1 h 15
1 000 exigences  : environ 12 h 30
```

Le LLM n'est donc pas utilisable sur un export complet. C'est la
raison d'être de `--llm-limit` et du classement par priorité : les
règles filtrent, le modèle approfondit.

---

## 11. État actuel

| Composant | État |
|---|---|
| Import générique multi-format | Fonctionnel, testé sur 6 formats |
| Détection colonnes, feuille, en-tête | Fonctionnelle, surchargeable |
| Catalogue de règles | Fonctionnel, 83 règles, à enrichir |
| Catalogue multi-fichiers | Fonctionnel |
| Moteur déterministe | Fonctionnel |
| Score et statuts qualité | Fonctionnels, seuils réglables |
| Évaluation SMART par axe | Fonctionnelle, axes déclarés dans le catalogue |
| Contrôle de singularité | Fonctionnel, détection structurelle |
| Rapport hiérarchisé en pages de lecture | Fonctionnel |
| Doublons de texte dans le lot | Fonctionnel, exact et par signature de mots |
| Page de questions client avec validation | Fonctionnelle |
| Page de risques avec validation | Fonctionnelle |
| Avis du modèle réconcilié avec l'action | Fonctionnel |
| Analyse LLM intégrée au pipeline | Fonctionnelle |
| Sortie JSON contrainte par schéma | Fonctionnelle |
| Reprise unique | Fonctionnelle |
| Évaluation précision / rappel / F1 | Fonctionnelle |
| Rapport Excel | Fonctionnel |
| Tests automatisés | 204 tests |
| Jeu de référence avec cas négatifs | **À constituer avec le métier** |
| Interface de validation humaine | Colonnes de validation dans le rapport ; outil dédié à faire |
| Déploiement partagé | À faire après validation métier |
| RAG | Hors périmètre |

---

## 12. Limites connues

**Couverture sémantique.** Les règles sont lexicales. Une exigence
demandant de réduire un phénomène sans définir le niveau de
réduction ni la méthode de vérification ne contient aucun mot
suspect. C'est précisément ce que le mode `FULL_CONTEXT_REVIEW` du
LLM doit couvrir, et ce qui reste à mesurer.

**Précision non mesurée sur données réelles.** Sur les classeurs de
test, 100 % de précision et de rappel. Mais ces fixtures ont été
construites pour l'outil. Le chiffre qui compte viendra d'un jeu de
référence constitué par le métier, avec des cas corrects.

**Catalogue conservateur.** Le catalogue ne produit aucune alerte
sur des formulations pourtant discutables comme « the relevant
clauses » ou « the applicable curve ». Il privilégie la précision
au rappel. C'est un choix défendable en revue client, mais il doit
être assumé.

**Portée de la grille SMART.** Un axe est déclaré conforme quand
aucune règle ne s'est déclenchée sur lui. L'axe **R**, en
particulier, ne peut pas être établi par une analyse lexicale : la
pertinence d'une exigence se juge par rapport à un besoin, à une
exigence parente et à un périmètre contractuel, qui ne figurent pas
dans le texte analysé. L'outil n'y signale donc que
l'incomplétude déclarée, du type `TBD`.

**Portée du contrôle de singularité.** La détection est
structurelle : verbes d'obligation, énumérations, connecteurs
additifs. Deux obligations rédigées sans verbe répété, par exemple
« the system shall log and notify », ne sont vues qu'au titre des
règles `POTENTIALLY_NON_ATOMIC`, et seulement signalées comme « à
vérifier ». Le verdict est un signal de revue : le découpage reste
une décision d'ingénierie.

**Portée de la détection de doublons.** Elle repose sur deux
signatures, le texte normalisé et l'ensemble des mots. Deux
exigences qui disent la même chose avec des mots différents ne
sont pas détectées : il faudrait une comparaison sémantique, donc
le LLM ou un modèle d'embeddings.

**Langue.** Les exigences traitées par ce projet sont en anglais,
ce qui correspond au catalogue. Le contrôle de langue n'est donc
pas une limite ici, mais un garde-fou : il signale un export qui
arriverait dans une autre langue, cas où le catalogue anglais ne
produirait presque aucune alerte.

Ce contrôle distingue deux situations que l'on confondrait
facilement :

- **une autre langue** : les mots fonctionnels sont
  majoritairement non anglais, le catalogue est inopérant ;
- **de l'anglais télégraphique** : un style abrégé ou tabulaire du
  type `Cabinet IP65. Weight 45 kg +/- 2 kg.` ne contient presque
  aucun mot fonctionnel, dans aucune langue. Le texte est bien en
  anglais, mais les règles lexicales y auront peu de prise. Le
  message invite alors à vérifier la colonne retenue, sans jamais
  affirmer que le texte n'est pas en anglais.

Un échantillon de moins de 40 mots ne donne aucun verdict : trop
court pour conclure. Si un catalogue dans une autre langue devenait
nécessaire, ce serait un fichier CSV supplémentaire chargé via
`--rules`.

**Validation humaine dans le classeur.** Les pages
`4. Questions client` et `5. Risques` portent des colonnes de
décision vides, à remplir à la main : c'est la trace de la
validation, et elle suffit à travailler. Mais rien ne la rend
obligatoire, rien ne la relit et rien ne la conserve d'une
analyse à la suivante. Une interface dédiée reste le prérequis
d'un usage opérationnel à l'échelle.

---

## 13. Suite du travail

**Priorité 1 — faire valider les règles par le métier.** Le
catalogue est le cœur de l'outil et n'a pas encore été revu règle
par règle avec un responsable exigences.

**Priorité 2 — constituer le jeu de référence.** Demander 10 cas
problématiques et 10 cas corrects, puis lancer `evaluate.py`. Sans
cela, aucun chiffre de précision n'est défendable.

**Priorité 3 — mesurer le LLM sur ce jeu.** Comparer
`Rule_Engine`, `LLM_Business_On_Success` et `End_To_End`, et
vérifier sur les reformulations : aucune valeur inventée, aucun
changement de sens contractuel, marqueurs respectés.

**Priorité 4 — interface de validation humaine.** Dépôt du
fichier, aperçu, lancement, filtres, acceptation ou rejet par
exigence, export. C'est ce qui transforme le prototype en outil.

**Priorité 5 — enrichir le catalogue** avec les formulations
remontées en revue, et envisager un catalogue par domaine.

**Priorité 6 — déploiement**, après validation métier seulement :
interface web, API, moteur de règles et Ollama, base de données,
traçabilité des décisions humaines.

---

## 14. Dépannage

**`Aucune colonne de texte d'exigence n'a été reconnue`**
Le message liste les colonnes disponibles. Utilise
`--text-column "<nom exact>"`.

**La mauvaise feuille est analysée**
`--sheet "<nom de la feuille>"`.

**La mauvaise ligne d'en-tête est retenue**
`--header-row 4` (numérotation Excel, la première ligne vaut 1).

**Trop de lignes écartées**
Consulte la feuille `Excluded_Rows` du rapport : chaque ligne porte
son motif. Au besoin, `--include-types`, `--exclude-types` ou
`--keep-headings`.

**`Le modèle ... n'est pas installé`**
```bash
ollama pull qwen2.5:3b
ollama list
```

**`Impossible de contacter Ollama`**
```bash
ollama serve
```
Ne pas démarrer un second serveur si le port 11434 est déjà pris.

**`Impossible d'écrire le rapport`**
Le fichier est ouvert dans Excel. Ferme-le puis relance.

**`La règle 'X' est définie dans a.csv et dans b.csv`**
Deux fichiers du catalogue déclarent le même identifiant. Supprime
le doublon, ou utilise `--non-strict-rules` pour ignorer les règles
en conflit.
# PoC-A
