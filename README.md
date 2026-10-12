# Controleur de qualite des exigences

## PoC 1 - Analyse hybride par regles et LLM local

Ce projet est un prototype local de controle qualite d'exigences client exportees depuis IBM DOORS au format Excel.

L'outil analyse des exigences redigees en anglais afin de detecter des formulations potentiellement :

- ambigues ;
- incompletes ;
- non verifiables ;
- faiblement obligatoires ;
- non atomiques ;
- dependantes de conditions ou references non definies ;
- insuffisamment quantifiees ;
- susceptibles de necessiter une clarification avec le client.

Le prototype combine trois niveaux de traitement :

1. un moteur de regles deterministe et explicable ;
2. un LLM local execute avec Ollama pour l'analyse contextuelle ;
3. une validation humaine obligatoire avant toute reformulation ou ouverture de risque.

> Le prototype est une aide a la revue. Il ne remplace pas l'expertise metier, ne modifie pas automatiquement les exigences du client et ne doit pas creer ou communiquer un risque sans validation humaine.

---

## 1. Objectif du projet

L'objectif du PoC est de verifier si une solution locale peut accelerer la premiere revue d'un export d'exigences client tout en conservant :

- le texte original sans modification ;
- l'identifiant DOORS de chaque objet ;
- une preuve textuelle pour chaque alerte ;
- une explication de la detection ;
- une question de clarification proposee ;
- une reformulation en brouillon ;
- une proposition de risque soumise a validation humaine ;
- une trace des performances et erreurs techniques.

Le PoC doit repondre a la question suivante :

> Une combinaison de regles explicites et d'un LLM local permet-elle d'identifier utilement des exigences de mauvaise qualite avant leur analyse detaillee par les equipes projet ?

---

## 2. Perimetre du PoC 1

### Inclus

- lecture d'un export Excel DOORS ;
- recherche automatique des colonnes utiles ;
- filtrage des objets selon leur type ;
- analyse des exigences techniques et non techniques ;
- application d'un catalogue de regles en anglais ;
- creation d'un resultat detaille par anomalie ;
- creation d'un resume par exigence ;
- analyse contextuelle facultative avec un LLM Ollama ;
- generation de questions de clarification ;
- generation de reformulations avec des placeholders ;
- preparation d'un brouillon de risque ;
- export des resultats dans un nouveau fichier Excel ;
- mesure des temps, tokens et erreurs ;
- test sur dix exigences selectionnees par le manager.

### Hors perimetre actuel

- modification automatique de DOORS ;
- validation contractuelle automatique ;
- envoi automatique de questions au client ;
- ouverture automatique d'un risque officiel ;
- authentification d'entreprise ;
- gestion multi-utilisateur ;
- deploiement sur une VM ou un serveur ;
- interface Streamlit finalisee ;
- API FastAPI integree au pipeline ;
- RAG et base vectorielle ;
- traitement LLM systematique de toutes les exigences.

---

## 3. Architecture fonctionnelle

```text
Export Excel DOORS
        |
        v
Chargement des colonnes A, B et C
        |
        v
Filtrage par ObjectType
        |
        +--> Technical Req
        +--> Non-Technical Req
        |
        v
Moteur de regles Python
        |
        +--> anomalies lexicales
        +--> anomalies structurelles
        +--> preuves et gravites
        |
        v
Selection des exigences a approfondir
        |
        v
LLM local Ollama / qwen2.5:3b
        |
        +--> confirmation ou rejet des alertes
        +--> revue contextuelle
        +--> informations manquantes
        +--> questions de clarification
        +--> reformulations en brouillon
        +--> proposition de risque
        |
        v
Validation humaine
        |
        v
Rapport Excel enrichi
```

Principe de responsabilite :

```text
Moteur de regles = detecter et prouver
LLM              = contextualiser et suggerer
Humain           = decider et valider
```

---

## 4. Format d'entree

Le prototype cherche automatiquement une feuille contenant les trois colonnes suivantes :

| Colonne | Nom | Utilisation |
|---|---|---|
| A | `ID` | Identifiant unique de l'objet DOORS |
| B | `Object Heading and Object Text` | Texte anglais a analyser |
| C | `ObjectType` | Type de l'objet |

Types analyses :

```text
Technical Req
Non-Technical Req
```

Types ignores par le moteur principal :

```text
Heading
Information
Type absent
```

L'export de reference utilise la feuille `ViewRich`.

Le texte original est conserve. Les traitements de normalisation servent uniquement a la recherche et ne remplacent pas le contenu importe.

---

## 5. Structure du projet

```text
Controleur de qualite PoC 1/
|
|-- README.md
|-- requirements.txt
|-- load_excel.py
|-- run_analysis.py
|-- test_manager_requirements.py
|
|-- rules/
|   |-- rules_en.csv
|
|-- src/
|   |-- __init__.py
|   |-- excel_loader.py          # selon l'organisation retenue
|   |-- rule_loader.py
|   |-- rule_engine.py
|   |-- llm_analyzer.py
|
|-- data/
|   |-- input/
|   |   |-- 10_examples_CONCEPT DESIGN.CUS.xlsx
|   |
|   |-- output/
|
|-- tests/
|-- logs/
|
|-- .venv/
```

Selon la version du projet, le chargeur Excel peut se trouver :

```text
load_excel.py
```

ou :

```text
src/excel_loader.py
```

Les scripts fournis recherchent les deux organisations.

---

## 6. Prerequis

### Systeme

- Windows avec PowerShell ;
- Python 3.14 actuellement utilise dans le PoC ;
- Ollama installe localement ;
- Microsoft Excel recommande pour consulter les rapports.

### Modele local

Modele de generation actuellement utilise :

```text
qwen2.5:3b
```

Modele d'embedding installe mais non utilise dans le PoC 1 :

```text
bge-m3:latest
```

Le modele d'embedding sera utile uniquement lors d'une future evolution RAG.

---

## 7. Installation

### 7.1 Creer l'environnement virtuel

```powershell
& "C:\Program Files\Python314\python.exe" -m venv .venv
```

Si PowerShell interdit l'activation, il n'est pas necessaire de modifier durablement la politique d'execution. Utiliser directement le Python de l'environnement :

```powershell
.\.venv\Scripts\python.exe --version
```

### 7.2 Installer les dependances

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

```powershell
.\.venv\Scripts\python.exe -m pip install pandas openpyxl pytest streamlit ollama
```

Exemple de `requirements.txt` :

```text
pandas
openpyxl
pytest
streamlit
ollama
```

Installation depuis le fichier :

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 7.3 Installer le modele Ollama

```powershell
ollama pull qwen2.5:3b
```

Verifier les modeles :

```powershell
ollama list
```

Tester l'API Ollama :

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:11434/api/tags" `
  -Method Get
```

---

## 8. Composants developpes

### 8.1 Chargeur Excel

Le chargeur :

- parcourt les feuilles du classeur ;
- cherche les trois colonnes requises ;
- charge uniquement les informations utiles ;
- conserve la ligne Excel source ;
- controle les ID absents ou dupliques ;
- controle les textes et types absents ;
- separe les exigences analysables des objets ignores ;
- produit un diagnostic d'import.

Resultats disponibles :

```python
result["all_objects"]
result["requirements"]
result["invalid_requirements"]
result["ignored_objects"]
result["diagnostics"]
```

### 8.2 Catalogue de regles

Le fichier `rules/rules_en.csv` contient le catalogue de controle qualite.

Colonnes :

```text
rule_id
category
pattern
severity
explanation
clarification_question
rewrite_template
enabled
```

Categories principales :

```text
AMBIGUITY
NOT_VERIFIABLE
INCOMPLETE
UNDEFINED_CONDITION
UNDEFINED_REFERENCE
UNDEFINED_QUANTITY
WEAK_OBLIGATION
POTENTIALLY_NON_ATOMIC
MISSING_ACTOR
MISSING_UNIT_OR_LIMIT
MISSING_TOLERANCE
MISSING_VERIFICATION_CRITERIA
```

Gravites :

```text
LOW
MEDIUM
HIGH
CRITICAL
```

Une regle est un signal de revue et non une decision automatique de non-conformite.

### 8.3 Chargeur de regles

`src/rule_loader.py` :

- lit le CSV en UTF-8 ;
- verifie les colonnes obligatoires ;
- controle les identifiants dupliques ;
- controle les niveaux de gravite ;
- compile les expressions regulieres ;
- gere les regles actives et desactivees ;
- fournit des fonctions de recherche par ID, categorie et gravite.

Test :

```powershell
.\.venv\Scripts\python.exe -m src.rule_loader
```

### 8.4 Moteur de regles

`src/rule_engine.py` :

- applique les regles aux exigences ;
- enregistre chaque occurrence ;
- conserve la preuve textuelle et sa position ;
- determine la gravite maximale ;
- calcule un statut qualite ;
- consolide les explications et questions ;
- propose un brouillon de risque ;
- mesure le temps par exigence.

Statuts :

```text
PRE_ANALYSIS_OK
REVIEW_REQUIRED
CLARIFICATION_REQUIRED
NON_ANALYSABLE
```

Sorties :

```python
analysis_result["summary"]
analysis_result["findings"]
analysis_result["diagnostics"]
```

### 8.5 Analyseur LLM

`src/llm_analyzer.py` communique avec Ollama.

Responsabilites actuelles :

- verifier qu'Ollama est accessible ;
- verifier que `qwen2.5:3b` est installe ;
- recevoir une exigence et les alertes du moteur ;
- demander au modele d'evaluer chaque alerte ;
- produire une sortie JSON ;
- confirmer ou rejeter les findings ;
- identifier les informations manquantes ;
- proposer des questions de clarification ;
- proposer une reformulation ;
- proposer un brouillon de risque ;
- collecter les tokens et temps d'execution ;
- retourner une erreur exploitable sans casser tout le lot.

Decisions :

```text
CONFIRMED
PARTIALLY_CONFIRMED
FALSE_POSITIVE
NEEDS_EXPERT_REVIEW
ERROR
```

Le calcul de la decision globale a ete deplace vers Python a partir de valeurs `issue_present` produites par le LLM. Cette approche evite certaines incoherences dans lesquelles un finding etait rejete avec une justification confirmant pourtant le probleme.

### 8.6 Pipeline complet

`run_analysis.py` :

- charge le fichier Excel ;
- charge le catalogue ;
- execute le moteur ;
- affiche les diagnostics ;
- genere un rapport Excel.

L'integration automatique generale du LLM dans ce script reste a finaliser et stabiliser.

### 8.7 Test manager

`test_manager_requirements.py` utilise dix exigences identifiees comme problematiques par le manager :

```text
PKP-ANNEX1.CUS-72
PKP-ANNEX1.CUS-198
PKP-ANNEX1.CUS-3475
PKP-ANNEX1.CUS-235
PKP-ANNEX1.CUS-237
PKP-ANNEX1.CUS-3482
PKP-ANNEX1.CUS-3489
PKP-ANNEX1.CUS-314
PKP-ANNEX1.CUS-562
PKP-ANNEX1.CUS-609
```

Ce jeu permet de mesurer le rappel sur des cas positifs. Il ne suffit pas pour mesurer la precision, puisqu'il ne contient pas encore de cas consideres comme correctement rediges.

---

## 9. Commandes d'utilisation

### 9.1 Verifier la syntaxe

```powershell
.\.venv\Scripts\python.exe -m py_compile .\src\rule_loader.py
.\.venv\Scripts\python.exe -m py_compile .\src\rule_engine.py
.\.venv\Scripts\python.exe -m py_compile .\src\llm_analyzer.py
.\.venv\Scripts\python.exe -m py_compile .\run_analysis.py
.\.venv\Scripts\python.exe -m py_compile .\test_manager_requirements.py
```

Aucun affichage signifie que la syntaxe est valide.

### 9.2 Tester le chargeur Excel

```powershell
.\.venv\Scripts\python.exe .\load_excel.py `
  ".\data\input\10_examples_CONCEPT DESIGN.CUS.xlsx"
```

### 9.3 Tester le catalogue

```powershell
.\.venv\Scripts\python.exe -m src.rule_loader
```

### 9.4 Tester le moteur

```powershell
.\.venv\Scripts\python.exe -m src.rule_engine
```

### 9.5 Tester le LLM seul

```powershell
.\.venv\Scripts\python.exe -m src.llm_analyzer
```

### 9.6 Analyser l'export complet avec les regles

```powershell
.\.venv\Scripts\python.exe .\run_analysis.py `
  --input ".\data\input\00 - PKP-A1_CONCEPT DESIGN.CUS (2026-09-29 18 26 32).xlsx" `
  --rules ".\rules\rules_en.csv" `
  --output ".\data\output\PKP_quality_analysis.xlsx" `
  --sample-size 20
```

### 9.7 Tester les dix cas sans LLM

```powershell
.\.venv\Scripts\python.exe .\test_manager_requirements.py `
  --input ".\data\input\10_examples_CONCEPT DESIGN.CUS.xlsx" `
  --rules ".\rules\rules_en.csv" `
  --output ".\data\output\manager_test_rules_only.xlsx" `
  --skip-llm
```

### 9.8 Tester les dix cas avec Qwen

```powershell
.\.venv\Scripts\python.exe .\test_manager_requirements.py `
  --input ".\data\input\10_examples_CONCEPT DESIGN.CUS.xlsx" `
  --rules ".\rules\rules_en.csv" `
  --output ".\data\output\manager_test_qwen.xlsx" `
  --model "qwen2.5:3b"
```

---

## 10. Rapport Excel

Le rapport de test contient notamment :

### `Manager_Test_Results`

Une ligne par exigence avec :

- texte original ;
- statut des regles ;
- nombre d'anomalies ;
- categories ;
- preuves ;
- decision LLM ;
- findings confirmes et rejetes ;
- informations manquantes ;
- questions ;
- reformulation ;
- risque ;
- temps et tokens ;
- erreur technique eventuelle.

### `Rule_Findings`

Une ligne par anomalie deterministe.

### `Run_Information`

Synthese de l'execution :

- fichiers utilises ;
- modele ;
- cas trouves ;
- rappel des regles ;
- couverture technique LLM ;
- temps total ;
- date.

---

## 11. Resultats obtenus

Premier test complet sur les dix exigences manager :

```text
Exigences trouvees       : 10/10
Detectees par les regles : 8/10
Rappel moteur de regles  : 80 %
Signalees par le LLM     : 6/10
Temps total              : 449,33 secondes
```

Interpretation correcte du resultat LLM :

```text
6 appels avec reponse exploitable
4 erreurs techniques ou JSON incomplets
0 rejet metier confirme dans les reponses exploitables
```

Les quatre erreurs ne doivent pas etre automatiquement comptees comme des faux negatifs metier. Les statistiques futures doivent distinguer :

```text
Rule_Engine_Recall
LLM_Technical_Success_Rate
LLM_Confirmation_Rate_On_Success
End_To_End_Recall
```

Performance observee sur le cas de test simple :

```text
Modele              : qwen2.5:3b
Vitesse              : environ 11 a 16 tokens/s
Temps par exigence   : environ 26 a 53 secondes selon le prompt
```

Le lot de dix exigences a pris environ 7 minutes et 29 secondes.

---

## 12. Limites connues

### 12.1 Jeu de reference uniquement positif

Les dix exigences du manager sont toutes considerees problematiques. Le jeu mesure le rappel, mais pas la precision ni les faux positifs.

### 12.2 Couverture des regles

Certaines anomalies sont semantiques et difficiles a detecter avec un mot-cle. Exemple : une exigence demandant de reduire un phenomene sans definir le niveau de reduction ni les conditions de verification.

### 12.3 Regles manquantes identifiees

Deux formulations ont ete identifiees comme non couvertes dans le catalogue initial :

```text
maximally modular
as quickly as possible
```

Elles doivent etre ajoutees au catalogue, apres validation metier.

### 12.4 Prompt trop influence par un exemple

Une version du prompt utilisait l'exemple `respond rapidly`. Le modele reutilisait parfois a tort des notions de temps de reponse ou de trigger pour des exigences sans rapport. Le prompt doit rester general et independant du domaine.

### 12.5 JSON incomplet

Sur les exigences longues, le modele peut produire :

```text
Unterminated string
token repeat limit reached
```

Causes probables :

- limite de sortie trop basse ;
- reponse trop longue ;
- repetition du modele ;
- exigence tres longue avec plusieurs findings.

### 12.6 Temps de traitement

Le LLM est trop lent pour analyser systematiquement environ 1 000 exigences sur la machine actuelle.

Estimation lineaire observee :

```text
100 exigences  : environ 1 h 15
1 000 exigences: environ 12 h 30
```

L'architecture cible doit donc utiliser les regles pour filtrer les cas prioritaires avant le LLM.

### 12.7 Absence de validation humaine dans une interface

Les decisions humaines ne sont pas encore gerees dans une interface dediee. Elles doivent etre ajoutees avant tout usage operationnel.

---

## 13. Regles de securite fonctionnelle

Le LLM ne doit jamais :

- modifier le texte original ;
- inventer une valeur ou un seuil ;
- inventer une norme ou une version ;
- inventer un acteur ;
- transformer une preference en engagement contractuel ;
- valider automatiquement une reformulation ;
- ouvrir automatiquement un risque ;
- communiquer automatiquement avec le client.

Les valeurs inconnues doivent utiliser des placeholders descriptifs :

```text
[MAXIMUM RESPONSE TIME TO BE CONFIRMED]
[COMPONENTS TO BE DEFINED]
[APPLICABLE CONDITIONS TO BE CONFIRMED]
[ACCEPTANCE CRITERION TO BE DEFINED]
```

Eviter :

```text
[VALUE TO BE CONFIRMED]
```

lorsqu'un placeholder plus precis est possible.

---

## 14. Ce qui reste a faire

### Priorite 1 - Stabiliser la version actuelle

- conserver une sauvegarde des versions fonctionnelles ;
- supprimer les caracteres HTML parasites comme `-&gt;` ;
- compiler tous les scripts avant execution ;
- ajouter les deux formulations manquantes au CSV ;
- relancer le test des regles uniquement ;
- confirmer le passage potentiel de 8/10 a 9/10.

### Priorite 2 - Generaliser le prompt LLM

- retirer les exemples specifiques au temps de reponse ;
- utiliser une grille generique : acteur, obligation, action, objet, scope, conditions, quantification, tolerance, verification, atomicite et references ;
- demander une revue contextuelle complete apres la validation des findings ;
- eviter d'ajouter des criteres non pertinents ;
- conserver le niveau d'abstraction initial.

### Priorite 3 - Fiabiliser le JSON

- augmenter `num_predict` de maniere controlee ;
- ajouter `repeat_penalty` ;
- limiter le nombre et la longueur des champs ;
- ajouter une seule reprise automatique ;
- ne jamais boucler indefiniment ;
- conserver la reponse brute pour diagnostic.

Parametres candidats :

```python
num_ctx = 4096
num_predict = 700
temperature = 0.1
repeat_penalty = 1.1
seed = 42
keep_alive = "30m"
```

En reprise :

```python
temperature = 0.0
num_predict = 850
repeat_penalty = 1.15
```

### Priorite 4 - Corriger les statistiques

Ajouter :

```text
nombre d'appels LLM
nombre de succes techniques
nombre d'erreurs techniques
nombre de decisions CONFIRMED
nombre de decisions PARTIALLY_CONFIRMED
nombre de FALSE_POSITIVE
taux de succes technique
taux de confirmation sur succes
rappel de bout en bout
```

### Priorite 5 - Ajouter des cas negatifs

Demander au manager au moins dix exigences considerees correctement redigees.

Jeu cible :

```text
10 cas problematiques
10 cas corrects
```

Puis calculer :

```text
precision
rappel
F1-score
faux positifs
faux negatifs
```

### Priorite 6 - Elargir le jeu de validation

Ajouter des exigences issues de plusieurs domaines :

- logiciel ;
- cybersécurite ;
- performance ;
- maintenance ;
- documentation ;
- mecanique ;
- securite ;
- contractuel.

### Priorite 7 - Ajouter l'interface Streamlit

Fonctions attendues :

- depot d'un fichier ;
- apercu ;
- diagnostic ;
- lancement des regles ;
- selection des exigences pour analyse LLM ;
- progression ;
- filtres ;
- comparaison regles/LLM ;
- acceptation, modification ou rejet ;
- telechargement du rapport.

### Priorite 8 - Deploiement partage

Apres validation du PoC :

```text
Interface Web
    |
FastAPI
    |
Moteur de regles + Ollama
    |
PostgreSQL
    |
Validation humaine
```

Pour 20 utilisateurs, une VM interne peut suffire. Pour une cible de 120 personnes, un serveur LLM dedie, une file d'attente, une authentification et une supervision seront necessaires.

### Priorite 9 - RAG, plus tard

Le RAG n'est pas necessaire pour les regles lexicales. Il sera utile pour fournir :

- glossaire client ;
- regles redactionnelles ;
- standards applicables ;
- exemples approuves ;
- criteres de verification ;
- contexte projet.

Le modele `bge-m3` pourra alors servir a produire les embeddings.

---

## 15. Strategie de validation recommandee

Pour chaque exigence, enregistrer :

```text
Expected_Flag
Expected_Categories
Rule_Engine_Flag
Triggered_Rules
LLM_Technical_Status
LLM_Decision
LLM_Additional_Issues
Useful_Questions
Faithful_Rewrite
Invented_Value
Risk_Relevant
Human_Decision
Human_Comment
```

Criteres eliminatoires pour un modele :

- valeurs inventees ;
- changement du sens contractuel ;
- JSON souvent invalide ;
- non-respect des placeholders ;
- reformulations hors contexte ;
- risque presente comme valide ;
- confirmation systematique de toutes les alertes.

---

## 16. Depannage

### `ModuleNotFoundError: No module named 'ollama'`

```powershell
.\.venv\Scripts\python.exe -m pip install ollama
```

### Scripts PowerShell bloques

L'activation du venv n'est pas obligatoire :

```powershell
.\.venv\Scripts\python.exe script.py
```

### `FileNotFoundError`

Verifier :

```powershell
Get-ChildItem ".\data\input" -File
```

Utiliser le chemin exact du fichier.

### Caracteres HTML dans Python

Incorrect :

```text
-&gt;
&lt;
&gt;
<br>
```

Correct :

```text
->
<
>
```

Rechercher :

```powershell
Select-String `
  -Path ".\src\*.py" `
  -Pattern "&gt;|&lt;|<br>|<em>|</em>"
```

### `return outside function` ou `unexpected unindent`

Verifier l'indentation :

```text
classe   : 0 espace
methode  : 4 espaces
contenu  : 8 espaces
```

### Rapport Excel impossible a ecrire

Fermer le fichier dans Excel puis relancer.

### Ollama ne repond pas

```powershell
ollama list
```

Puis :

```powershell
ollama serve
```

Ne pas demarrer un second serveur si le port 11434 est deja utilise.

---

## 17. Etat actuel du PoC

| Composant | Etat |
|---|---|
| Chargement Excel | Fonctionnel |
| Detection des colonnes | Fonctionnelle |
| Filtrage `ObjectType` | Fonctionnel |
| Catalogue de regles | Fonctionnel, a enrichir |
| Chargeur de regles | Fonctionnel |
| Moteur deterministe | Fonctionnel |
| Export Excel | Fonctionnel |
| Connexion Ollama | Fonctionnelle |
| Qwen2.5:3b | Fonctionnel |
| Sortie JSON | Fonctionnelle mais encore instable sur certains cas longs |
| Test manager | Fonctionnel |
| Statistiques LLM | A corriger et separer |
| Prompt general multi-domaine | A finaliser |
| Reprise automatique | A implementer proprement |
| Interface Streamlit | A faire |
| FastAPI partagee | Test technique realise, integration a faire |
| Base de donnees | A faire apres validation du PoC |
| RAG | Hors PoC 1, evolution future |
| Deploiement serveur | A faire apres validation metier |

---

## 18. Prochaine sequence de travail

Ordre recommande :

```text
1. Geler une copie de la version fonctionnelle
2. Verifier la syntaxe de tous les fichiers
3. Ajouter les deux regles manquantes
4. Relancer les regles seules
5. Generaliser le prompt sans exemple specifique
6. Limiter la longueur des sorties
7. Ajouter une reprise unique
8. Corriger les statistiques LLM
9. Relancer les dix cas manager
10. Faire valider les resultats par le manager
11. Ajouter dix cas negatifs
12. Calculer precision, rappel et F1
13. Creer l'interface Streamlit
14. Integrer le LLM au pipeline general
15. Preparer le deploiement sur une VM interne
```

---

## 19. Conclusion

Le PoC a demontre la faisabilite technique de la chaine suivante :

```text
Excel DOORS
-> filtrage
-> regles explicites
-> analyse LLM locale
-> rapport Excel
```

Les resultats initiaux montrent :

- un moteur de regles rapide et deja utile ;
- un rappel initial de 80 % sur dix cas positifs ;
- une capacite du LLM a contextualiser les alertes ;
- une necessite de fiabiliser les sorties JSON ;
- une necessite de generaliser le prompt ;
- un besoin de validation humaine et de cas negatifs avant conclusion.

La priorite n'est pas encore le deploiement a grande echelle. La priorite est de stabiliser le comportement, mesurer les faux positifs et faire valider les resultats par les responsables metier.
