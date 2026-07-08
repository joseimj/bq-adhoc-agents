# dq-rules-repo — gobierno de reglas de calidad (rules-as-code)

🌐 **Español** · [English](README.en.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Português](README.pt.md)

Cada tabla tiene su archivo `rules/{project}/{dataset}/{table}.yaml`. Los agentes de bq-adhoc-agents PROPONEN cambios abriendo PR/MR; los data stewards APRUEBAN con merge (protege `main` con CODEOWNERS por dominio); el CI APLICA con la service account de gobierno (única identidad con `roles/dataplex.dataScanEditor`), idealmente vía Workload Identity Federation.

- PR/MR → `python apply.py validate` + `governance_report.py` (reporte vivo de Dataplex publicado como comentario por `post_comment.py`, y notificación al chat de stewards vía `CHAT_WEBHOOK_URL`)
- merge a main → `python apply.py apply` (crea/actualiza el DataScan de Dataplex y dispara la primera corrida)

Los tres pipelines (GitHub Actions, GitLab CI, Bitbucket Pipelines) invocan el mismo `apply.py`: el proveedor Git es configuración, no arquitectura. Nota: en Bitbucket, el paso `apply` usa el deployment environment `production` restringido a `main`; el adaptador del agente cubre Bitbucket Cloud (Data Center requiere adaptar rutas de API).

## Autor

**Jose Maldonado** ([@joseimj](https://github.com/joseimj))
