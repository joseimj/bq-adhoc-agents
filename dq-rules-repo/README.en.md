# dq-rules-repo — data quality rules governance (rules-as-code)

🌐 [Español](README.md) · **English** · [Français](README.fr.md) · [Deutsch](README.de.md) · [Português](README.pt.md)

Each table has its own file `rules/{project}/{dataset}/{table}.yaml`. The bq-adhoc-agents PROPOSE changes by opening PRs/MRs; data stewards APPROVE via merge (protect `main` with per-domain CODEOWNERS); the CI APPLIES with the governance service account (the only identity holding `roles/dataplex.dataScanEditor`), ideally via Workload Identity Federation.

- PR/MR → `python apply.py validate` + `governance_report.py` (live Dataplex report posted as a comment by `post_comment.py`, plus a notification to the stewards' chat via `CHAT_WEBHOOK_URL`)
- merge to main → `python apply.py apply` (creates/updates the Dataplex DataScan and triggers the first run)

All three pipelines (GitHub Actions, GitLab CI, Bitbucket Pipelines) invoke the same `apply.py`: the Git provider is configuration, not architecture. Note: on Bitbucket, the `apply` step uses the `production` deployment environment restricted to `main`; the agent-side adapter covers Bitbucket Cloud (Data Center requires adapting the API paths).

## Author

**Jose Maldonado** ([@joseimj](https://github.com/joseimj))
