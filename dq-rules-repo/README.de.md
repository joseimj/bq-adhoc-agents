# dq-rules-repo — Governance von Datenqualitätsregeln (Rules-as-Code)

🌐 [Español](README.md) · [English](README.en.md) · [Français](README.fr.md) · **Deutsch** · [Português](README.pt.md)

Jede Tabelle hat ihre Datei `rules/{project}/{dataset}/{table}.yaml`. Die bq-adhoc-agents SCHLAGEN Änderungen VOR, indem sie PRs/MRs öffnen; Data Stewards GENEHMIGEN per Merge (schütze `main` mit CODEOWNERS pro Domäne); das CI WENDET AN mit dem Governance-Service-Account (die einzige Identität mit `roles/dataplex.dataScanEditor`), idealerweise via Workload Identity Federation.

- PR/MR → `python apply.py validate` + `governance_report.py` (Live-Dataplex-Bericht, von `post_comment.py` als Kommentar veröffentlicht, plus Benachrichtigung an den Steward-Chat via `CHAT_WEBHOOK_URL`)
- Merge nach main → `python apply.py apply` (erstellt/aktualisiert den Dataplex-DataScan und startet den ersten Lauf)

Alle drei Pipelines (GitHub Actions, GitLab CI, Bitbucket Pipelines) rufen dasselbe `apply.py` auf: Der Git-Provider ist Konfiguration, nicht Architektur. Hinweis: Auf Bitbucket nutzt der `apply`-Schritt das auf `main` beschränkte Deployment Environment `production`; der agentenseitige Adapter deckt Bitbucket Cloud ab (Data Center erfordert angepasste API-Pfade).

## Autor

**Jose Maldonado** ([@joseimj](https://github.com/joseimj))
