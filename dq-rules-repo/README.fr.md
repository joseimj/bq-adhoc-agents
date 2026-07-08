# dq-rules-repo — gouvernance des règles de qualité (rules-as-code)

🌐 [Español](README.md) · [English](README.en.md) · **Français** · [Deutsch](README.de.md) · [Português](README.pt.md)

Chaque table possède son fichier `rules/{project}/{dataset}/{table}.yaml`. Les agents de bq-adhoc-agents PROPOSENT des changements en ouvrant des PR/MR ; les data stewards APPROUVENT via merge (protégez `main` avec des CODEOWNERS par domaine) ; le CI APPLIQUE avec le service account de gouvernance (seule identité détenant `roles/dataplex.dataScanEditor`), idéalement via Workload Identity Federation.

- PR/MR → `python apply.py validate` + `governance_report.py` (rapport vivant de Dataplex publié en commentaire par `post_comment.py`, plus une notification au chat des stewards via `CHAT_WEBHOOK_URL`)
- merge vers main → `python apply.py apply` (crée/met à jour le DataScan Dataplex et déclenche la première exécution)

Les trois pipelines (GitHub Actions, GitLab CI, Bitbucket Pipelines) invoquent le même `apply.py` : le fournisseur Git est de la configuration, pas de l'architecture. Note : sur Bitbucket, l'étape `apply` utilise le deployment environment `production` restreint à `main` ; l'adaptateur côté agent couvre Bitbucket Cloud (Data Center exige d'adapter les chemins d'API).

## Auteur

**Jose Maldonado** ([@joseimj](https://github.com/joseimj))
