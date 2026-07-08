# dq-rules-repo — governança de regras de qualidade (rules-as-code)

🌐 [Español](README.md) · [English](README.en.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · **Português**

Cada tabela tem seu arquivo `rules/{project}/{dataset}/{table}.yaml`. Os agentes do bq-adhoc-agents PROPÕEM mudanças abrindo PRs/MRs; os data stewards APROVAM com merge (proteja a `main` com CODEOWNERS por domínio); o CI APLICA com a service account de governança (única identidade com `roles/dataplex.dataScanEditor`), idealmente via Workload Identity Federation.

- PR/MR → `python apply.py validate` + `governance_report.py` (relatório vivo do Dataplex publicado como comentário pelo `post_comment.py`, além de notificação ao chat dos stewards via `CHAT_WEBHOOK_URL`)
- merge na main → `python apply.py apply` (cria/atualiza o DataScan do Dataplex e dispara a primeira execução)

Os três pipelines (GitHub Actions, GitLab CI, Bitbucket Pipelines) invocam o mesmo `apply.py`: o provedor Git é configuração, não arquitetura. Nota: no Bitbucket, o passo `apply` usa o deployment environment `production` restrito à `main`; o adaptador do lado do agente cobre o Bitbucket Cloud (Data Center exige adaptar os caminhos de API).

## Autor

**Jose Maldonado** ([@joseimj](https://github.com/joseimj))
