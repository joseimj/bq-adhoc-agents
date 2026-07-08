# dq-rules-repo — gobierno de reglas de calidad (rules-as-code)

Cada tabla tiene su archivo `rules/{project}/{dataset}/{table}.yaml`. Los
agentes de bq-adhoc-agents PROPONEN cambios abriendo PR/MR; los data stewards
APRUEBAN con merge (protege `main` con CODEOWNERS por dominio); el CI APLICA
con la service account de gobierno (única identidad con
`roles/dataplex.dataScanEditor`), idealmente vía Workload Identity Federation.

- PR/MR -> `python apply.py validate` (esquema y rangos; falla el pipeline si
  la propuesta es inválida)
- merge a main -> `python apply.py apply` (crea/actualiza el DataScan de
  Dataplex y dispara la primera corrida)

Los tres pipelines (GitHub Actions, GitLab CI, Bitbucket Pipelines) invocan el
mismo `apply.py`: el proveedor Git es configuración, no arquitectura. Nota:
el adaptador de Bitbucket cubre Bitbucket Cloud; Data Center requiere adaptar
rutas de API.
