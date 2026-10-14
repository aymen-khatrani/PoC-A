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

## 0. L'outil remplit-il son objectif ?

> Analyser un export de requis client, détecter les exigences
> ambiguës, non vérifiables ou à formulation risquée, proposer des
> reformulations soumises à validation humaine, et ouvrir un risque
> à partager et clarifier avec le client.

Évaluation honnête, point par point :

| Partie de l'objectif | Verdict | Fondement |
|---|---|---|
| Analyser un export client | **Oui** | 8 formats hétérogènes testés, colonnes, feuille et en-tête détectés, 0,11 ms par exigence |
| Détecter ambiguïté, non-vérifiabilité, formulations à risque | **Oui** | 83 règles, 5 axes SMART, singularité, doublons de texte. 100 % de précision et de rappel sur les classeurs de test — mais ces classeurs ont été construits pour l'outil |
| Proposer des reformulations soumises à validation | **Oui, avec une nuance à connaître** | Voir ci-dessous |
| Ouvrir un risque à partager avec le client | **Oui** | Page `5. Risques`, brouillon factuel, colonnes de décision à remplir |

**La nuance sur les reformulations.** Sans `--llm`, l'outil ne
réécrit pas les exigences, et c'est volontaire. Ce que la règle
fournit est un **patron** : sur `The HMI shall display the alarm
rapidly`, elle propose `The system shall perform [ACTION TO BE
DEFINED] within [RESPONSE TIME TO BE CONFIRMED]` — l'acteur et
l'action du client ont disparu. Réécrire vraiment une exigence
demande de connaître l'information manquante, et l'inventer serait
la faute la plus grave que cet outil puisse commettre.

L'outil fait donc les trois choses honnêtes possibles : il montre
le défaut **dans le texte du client, intact** (texte annoté), il
formule la **question** à poser, et il propose la **forme**
attendue. La seule véritable reformulation vient du LLM, et elle
est présentée comme un brouillon.

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

### Vérifier l'installation

```bash
./.venv/bin/python -m pytest -q      # doit afficher 204 passed
```

Si les classeurs de test manquent, ils se régénèrent :

```bash
./.venv/bin/python -m tests.make_fixtures
```

### Porter le projet sur une autre machine

Python 3.10 ou plus récent ; le projet est développé sous 3.14.
Aucun service, aucune base de données, aucun accès réseau n'est
requis en mode règles.

| Point d'attention | À savoir |
|---|---|
| Répertoire de lancement | `--rules` vaut `rules/` par défaut, chemin relatif. Lancez depuis la racine du projet, ou passez un chemin absolu |
| Dossier de sortie | `data/output/` est créé automatiquement |
| Fichier Excel ouvert | L'écriture échoue avec un message explicite : fermez le classeur et relancez |
| Version de pandas | Bornée à `<4.0` dans `requirements.txt`. Pandas 3 est couvert et testé |
| Ollama distant | `--host http://adresse:11434` ; le modèle doit être installé sur la machine qui héberge Ollama |

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

Les exigences à scinder passent en premier, puis les autres par
gravité et par score qualité croissant : les plus douteuses
d'abord quand le budget de temps est limité. `--llm-limit -1`
envoie tout, `--llm-include-clean` envoie aussi les exigences sans
alerte en revue contextuelle complète.

Un énoncé à scinder est soumis au modèle **même sans constat de
règle**. Il en était exclu auparavant, faute de constat lexical,
alors que c'est précisément un défaut de structure que le modèle
sait décrire et qu'une expression régulière ne voit qu'en partie.

Prévoyez le temps : 26 à 53 s par exigence, en séquentiel. La
limite par défaut de 20 exigences représente donc environ dix à
quinze minutes. Les exigences non soumises portent `NOT_RUN`.

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

## 7. Le rôle du LLM

### Deux tâches, pas une

Le modèle n'est pas un filtre posé après les règles. Il a deux
tâches, et la seconde est celle qui justifie sa présence.

**1. Arbitrer les constats des règles.** Pour chaque `rule_id`
fourni, il décide si le défaut décrit est réellement présent dans
ce contexte. Une règle est un signal, pas un verdict.

**2. Signaler un défaut qu'aucune règle ne décrit.** C'est le
champ `additional_findings`. Une règle lexicale ne verra jamais
qu'une exigence demande de réduire un phénomène sans dire de
combien, ni qu'une méthode de vérification ne peut pas exister.
Le modèle, lui, le voit.

```text
The system shall reduce the vibration level during operation.

Règles seules   : PRE_ANALYSIS_OK · SMART 100 · S:OK M:OK A:OK R:OK T:OK
                  (aucun mot suspect : aucune règle ne se déclenche)

Après le modèle : CLARIFICATION_REQUIRED · SMART 80 · M:KO
                  LLM-001 [MEASURABLE, HIGH] « reduce the vibration level »
                  « The system shall 《reduce the vibration level》 during operation. »
```

### Le garde-fou : la preuve littérale

Un constat du modèle obéit aux mêmes exigences qu'un constat de
règle : **il doit citer un passage présent mot pour mot dans
l'exigence**. La vérification est faite en Python, pas demandée au
modèle.

| Constat renvoyé | Sort |
|---|---|
| preuve retrouvée dans le texte | retenu, identifiant `LLM-001` |
| `"reduce noise by 50%"` sur un texte qui ne le contient pas | **écarté**, motif tracé |
| critère qualité inconnu | **écarté**, motif tracé |
| gravité `CRITICAL` | **écarté** : elle engage le projet et doit venir d'une règle validée par le métier |
| au-delà de trois constats | **écarté** : au-delà, le modèle ne décrit plus, il commente |

Les motifs d'écartement figurent dans `LLM_Discarded_Findings`.
C'est ce contrôle qui permet de confier au modèle un rôle de
détection sans lui confier le droit d'inventer.

### Le verdict tient compte de la revue

Sans cela, l'avis du modèle restait décoratif : les règles
décidaient du statut, du score et des axes, et le modèle
commentait à côté. Une exigence dont tous les constats étaient
jugés infondés gardait un verdict sévère.

Après `apply_model_review`, le verdict affiché est le meilleur
disponible : constats de règles rejetés par le modèle retirés,
constats du modèle ajoutés, puis statut, score, axes, action,
texte annoté et risque **recalculés**.

| Colonne | Contenu |
|---|---|
| `Quality_Status`, `SMART_Score`, `SMART_Profile` | Le verdict après revue |
| `Rule_Quality_Status`, `Rule_SMART_Score`, `Rule_SMART_Profile` | Le verdict des règles seules, conservé pour l'audit |
| `Source` dans `Rule_Findings` | `RULE` ou `MODEL` : l'origine de chaque constat |

Les exigences non soumises au modèle conservent leur verdict de
règles, et leurs colonnes d'audit le répètent à l'identique : une
absence d'avis ne doit jamais ressembler à un avis.

L'action recommandée suit le même principe. Une fausse alerte
remplace la consigne de correction ; un avis réservé la préfixe
sans l'effacer ; une absence d'avis ne change rien.

### Fiabilité technique

Cinq mécanismes, dans l'ordre où ils agissent :

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

**5. Schéma transmis une seule fois.** Il était à la fois imposé
via `format` et recopié dans le prompt : près d'un cinquième du
prompt pour rien, soit 1 456 caractères par appel, sur une fenêtre
de contexte précieuse pour un modèle local. Il n'est désormais
rappelé dans le prompt qu'en mode de repli, quand la grammaire de
sortie n'est pas imposée.

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

---

## 15. Journal des évolutions

### Refonte SMART, singularité et sortie hiérarchisée

**Objectif de la passe.** Évaluer chaque exigence sur les cinq axes
SMART, faire respecter le principe de singularité — un énoncé, une
exigence — et rendre la première page du rapport lisible sans
formation préalable.

#### Ce qui a été ajouté

**Grille SMART portée par le catalogue.** Une colonne facultative
`smart_dimension` déclare l'axe qu'une règle met en défaut ; vide,
l'axe est déduit de la catégorie. Ajouter une règle ne demande donc
aucune modification de code. Répartition obtenue : 37 règles
`SPECIFIC`, 16 `MEASURABLE`, 10 `TIME_BOUND`, 9 `ACHIEVABLE`,
9 `RELEVANT`, 2 `SINGULARITY`.

**Contrôle de singularité.** Détection structurelle, avec deux
garde-fous qui ont chacun corrigé un comportement mesuré :

```text
"...clause 7.2, which states that the equipment must be painted."
   avant : TO_SPLIT n=2 + statut relevé à tort
   après : UNIQUE              (obligation citée, pas une exigence de plus)

"The system shall log X and the HMI shall display Y."
   après : TO_SPLIT n=2        (inchangé : deux obligations réelles)

"The system shall log X and the operator must confirm."
   après : TO_CHECK            (modaux mêlés : prudence)
```

**Rapport en cinq pages de lecture.** La synthèse s'ouvre sur
deux colonnes, sans filtre ni quadrillage, et annonce ce qui a été
écarté avant d'annoncer ce qui a été analysé. Les pages
`4. Questions client` et `5. Risques` sont les livrables : elles
se terminent par des colonnes de décision vides, trace de la
validation humaine.

**Texte annoté.** La seule « reformulation » que le moteur puisse
produire honnêtement : le texte du client, intact, avec les
passages détectés encadrés.

```text
《The interface shall be》 《robust》 and handle errors 《appropriately》, 《if necessary》.
```

**Doublons de texte dans le lot.** Deux identifiants distincts qui
portent la même exigence : `IDENTICAL` après normalisation,
`SIMILAR` par signature de mots. Le statut est relevé à
`REVIEW_REQUIRED`, car corriger deux fois le même texte est du
travail perdu.

**Le LLM promu d'arbitre à détecteur.** Voir la section 7. Le
modèle peut ajouter des constats, à condition de citer un passage
présent mot pour mot dans l'exigence ; son avis recalcule le
statut, le score, les axes, l'action et le risque, et le verdict
des règles seules est conservé pour l'audit.

#### Deux bugs trouvés en route

**Troncature Excel inopérante.** `prepare_frame_for_excel` testait
`series.dtype == object`. Sous pandas 3, une colonne de texte porte
le dtype `str` : la condition ne se déclenchait plus, la troncature
explicite à 32 000 caractères ne s'exécutait pas, et openpyxl
coupait silencieusement à 32 767 **sans la mention** « texte
tronqué ». Le lecteur ne pouvait pas savoir que le texte était
coupé. Le test porte désormais sur les valeurs, et non sur le
dtype.

**Aperçu console aveugle.** Il filtrait sur `Issue_Count > 0` et
passait donc à côté des exigences à scinder et des doublons, qui ne
déclenchent aucune règle lexicale. Sur le classeur de test dédié,
l'aperçu affichait 1 cas au lieu de 4. Le filtre porte maintenant
sur le statut.

#### Fichiers touchés

| Fichier | Nature |
|---|---|
| `src/smart_evaluator.py` | **créé** — axes SMART et singularité, sans dépendance à pandas ni à Excel |
| `src/config.py` | axes, verdicts, libellés français et anglais, seuils de singularité, doublons, avis et constats du modèle |
| `src/reporting.py` | cinq pages de tête, mise en forme de synthèse, palettes dérivées |
| `src/rule_engine.py` | axe par constat, origine `Source`, texte annoté, risque enrichi, doublons de lot, `summarise_requirement` et `rebuild_findings` extraits |
| `src/llm_analyzer.py` | constats ajoutés par le modèle, `apply_model_review`, action réconciliée, prompt allégé |
| `src/rule_loader.py` | colonne `smart_dimension`, validation, axes dans les diagnostics |
| `src/text_utils.py` | `join_unique` et `unique_preserve_order` déplacés ici, pour que `reporting` n'importe pas le moteur |
| `rules/rules_en.csv` | colonne `smart_dimension`, 11 règles à axe explicite |
| `run_analysis.py` | nouvelles feuilles, console en libellés lisibles, aperçu corrigé |
| `evaluate.py` | imports morts retirés |
| `tests/` | `test_reporting.py` et `test_smart_evaluator.py` créés, fixture `format_singularite.xlsx` ajoutée, `test_pipeline.py` et `test_rule_loader.py` étendus |

**Volume** : environ 1 490 lignes de code et 1 420 lignes de tests.
Tests : 129 → **204**. `pyflakes` ne signale plus rien.
Performance inchangée : 0,11 ms par exigence sur 2 000 exigences.

#### Ce qui reste ouvert

Deux leviers de performance sur le LLM, non entamés :

1. **Parallélisme.** `analyze_batch` boucle en séquentiel, un appel
   bloquant par exigence. Ollama sert plusieurs requêtes en
   parallèle : un pool de quatre workers diviserait le temps mural
   par trois à quatre, et ferait passer `--llm-limit` de 20 à 100
   sans changer la patience de l'utilisateur.
2. **Cache disque.** Relancer la même analyse réinterroge le
   modèle sur chaque exigence. Une clé
   `sha256(modèle + options + prompt)` rendrait la seconde passe
   immédiate, et les doublons de texte gratuits.

Sur le fond, trois manques connus et documentés en section 12 :
l'axe `RELEVANT` reste structurellement optimiste, les doublons
sémantiques ne sont pas détectés, et aucune analyse de cohérence
entre exigences n'existe. `evaluate.py` ne mesure toujours que le
binaire signalé / non signalé, pas la justesse des axes.

---

# PoC-A
