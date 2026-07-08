# Checklist de despliegue end-to-end · bq-adhoc-agents

Orden recomendado. Cada fase tiene criterio de salida: no avances sin cumplirlo. Marca `[x]` al completar.

---

## Fase 0 · Decisiones previas (papel, no consola)

- [ ] Proyecto(s) GCP definidos: proyecto de agentes/cómputo y, si aplica, proyectos de datos separados. Anota el `BQ_BILLING_PROJECT`.
- [ ] Región de despliegue (`region`) y location de DataScans (`DATAPLEX_DQ_LOCATION` — regional, no `global`).
- [ ] Superficie principal: Gemini Enterprise (`EUC_MODE=gemini_enterprise`) o frontend propio A2UI (`oauth_interactive`).
- [ ] Plataforma Git del repo de gobierno elegida (github | gitlab | bitbucket) y lista de data stewards por dominio (para CODEOWNERS / default reviewers).
- [ ] ¿Existe `bi-selfservice-agents` desplegado? Si sí, anota la URL de su orquestador para `LOOKER_ORCHESTRATOR_URL`. ¿La instancia de Looker está catalogada en Dataplex? (habilita `check_looker_coverage`).
- [ ] Presupuesto por query acordado (`BQ_MAX_BYTES_BILLED`, default 10 GiB) y tope de filas al LLM (`BQ_MAX_RESULT_ROWS`).

**Criterio de salida:** tabla de decisiones llena; sin TBDs.

---

## Fase 1 · Base GCP (Terraform)

- [ ] `gcloud auth application-default login` con un usuario con permisos de admin del proyecto.
- [ ] `cd terraform && cp terraform.tfvars.example terraform.tfvars` y llenar: `project_id`, `region`, `git_provider`, `git_repo`, y las variables WIF de tu(s) plataforma(s) (`github_repo` / `gitlab_project_path` / `bitbucket_*`), `protected_branch`.
- [ ] `terraform init && terraform apply`.
- [ ] Captura los outputs: `wif_providers` (para los CIs), `service_accounts` (agents / dq_reader / governance) y `agent_urls`.
- [ ] Verifica separación de poderes en IAM:
  ```bash
  gcloud projects get-iam-policy $PROJECT --flatten=bindings --format=json \
    | jq '.[] | select(.bindings.members[]? | contains("bq-adhoc-agents"))'
  ```
  La SA `bq-adhoc-agents` NO debe tener ningún rol `bigquery.dataViewer`/`dataEditor`; solo `dq-rules-governance` tiene `dataplex.dataScanEditor`.

**Criterio de salida:** `terraform apply` limpio + los tres emails de SA con los roles esperados y nada más.

---

## Fase 2 · Identidad del usuario final (EUC)

- [ ] Pantalla de consentimiento OAuth configurada (interno) y client ID creado.
- [ ] **Si Gemini Enterprise:** registrar una *Authorization* con scope `https://www.googleapis.com/auth/bigquery.readonly` (agrega `https://www.googleapis.com/auth/cloud-platform` solo si perfilarás tablas vía Dataplex con identidad del usuario). Anota su id → `GE_AUTH_ID`.
- [ ] **Si A2UI:** guardar `OAUTH_CLIENT_ID`/`OAUTH_CLIENT_SECRET` en Secret Manager y referenciarlos en el servicio del SQL Agent.
- [ ] Prueba de humo del token (antes de involucrar agentes): con un access token de un usuario de prueba, ejecuta un `jobs.query` simple contra una tabla a la que ese usuario sí tiene acceso y una a la que no. Espera: 200 y 403 respectivamente.

**Criterio de salida:** el par 200/403 con token de usuario reproducido a mano.

---

## Fase 3 · Catálogo y datos de prueba

- [ ] Confirmar que Dataplex Universal Catalog ya muestra las tablas de BQ del dominio piloto (harvest automático): búsqueda por nombre en la consola de Dataplex.
- [ ] Elegir 2–3 tablas piloto y asegurarles metadata mínima: descripción de tabla y de columnas clave (sin esto, `search_catalog` por términos de negocio rinde poco).
- [ ] Configurar (o verificar) en las tablas piloto los tres mecanismos que el sistema debe respetar, para poder probarlos en Fase 7:
  - [ ] IAM: un usuario A con acceso, un usuario B sin acceso.
  - [ ] Una row access policy (p. ej. usuario A solo ve `region = 'norte'`).
  - [ ] Una columna con policy tag y masking (p. ej. `customer_email`), con A sin fine-grained reader.
- [ ] Opcional: registrar la instancia de Looker en Dataplex y verificar que aparecen entradas `looker:` (routing Looker-first).
- [ ] `BQ_DATASET_ALLOWLIST` definida si quieres acotar el piloto.

**Criterio de salida:** las tablas piloto aparecen en el catálogo con descripciones, y los tres mecanismos de acceso están montados y verificados a mano.

---

## Fase 4 · Repo de gobierno (dq-rules-repo)

- [ ] Crear el repo en la plataforma elegida y copiar el contenido de `dq-rules-repo/`.
- [ ] `CODEOWNERS` con tus stewards reales por ruta de dominio (Bitbucket: configurar *default reviewers* equivalentes).
- [ ] Protección de la rama `main`: revisión requerida de code owners, prohibido push directo, prohibido merge sin pipeline verde.
- [ ] **Solo Bitbucket:** crear el deployment environment `production` con *branch restriction* a `main`; captura su UUID → `bitbucket_deployment_env_uuid` en tfvars → `terraform apply` de nuevo.
- [ ] Variables/secretos del CI:
  - [ ] `WIF_PROVIDER` (del output de Terraform), `DQ_READER_SA`, `DQ_GOVERNANCE_SA`, `GCP_PROJECT_ID`.
  - [ ] `CHAT_WEBHOOK_URL` (webhook entrante del espacio de stewards en Google Chat/Slack).
  - [ ] GitLab: `GITLAB_TOKEN` (project access token con scope api) · Bitbucket: `BB_TOKEN`. (GitHub usa el `GITHUB_TOKEN` del workflow.)
- [ ] Token del bot proponente: crear el token con permiso de contenido+PR y cargarlo en Secret Manager:
  ```bash
  echo -n "$TOKEN" | gcloud secrets versions add dq-git-token --data-file=-
  ```

**Criterio de salida:** un PR manual de prueba (editando el YAML de ejemplo) dispara el pipeline `validate`, asigna al steward por CODEOWNERS y notifica al chat.

---

## Fase 5 · Smoke test de WIF (positivo y negativo)

- [ ] **Positivo lectora:** en un PR, el paso `validate` obtiene credenciales de `dq-rules-reader` y `governance_report.py` publica el comentario con metadata del catálogo.
- [ ] **Positivo gobernanza:** merge del PR de prueba a `main` → el paso `apply` asume `dq-rules-governance` y crea el DataScan (verifica en la consola de Dataplex).
- [ ] **Negativo (el importante):** en una rama, edita el pipeline para intentar `apply.py apply` desde el evento de PR. El intercambio de token hacia la SA de gobierno debe FALLAR en IAM (GitHub/GitLab: el ref no matchea; Bitbucket: sin `deployment: production` no hay claim). Si no falla, detente y revisa los bindings `wif_governance`.
- [ ] Revertir/limpiar el scan de prueba si aplica.

**Criterio de salida:** los dos positivos y el negativo se comportan exactamente así.

---

## Fase 6 · Build y despliegue de agentes

- [ ] Artifact Registry creado; build de las 4 imágenes (catalog, sql, viz, orchestrator) con el contexto que incluya `common/`.
- [ ] Cloud Run actualizado con las imágenes reales; verificar env vars por servicio: `GOOGLE_CLOUD_PROJECT_ID`, `EUC_MODE`, `GE_AUTH_ID`, `BQ_*`, `DATAPLEX_*`, `GIT_*`, y en el orquestador `CATALOG/SQL/VIZ_AGENT_URL` (+ `LOOKER_ORCHESTRATOR_URL` si aplica) y `PUBLIC_URL`.
- [ ] AgentCards accesibles internamente: `GET {url}/.well-known/agent-card.json` responde para los tres especialistas (desde una identidad con `run.invoker`).
- [ ] Registrar el orquestador en Gemini Enterprise (o conectar el frontend A2UI) y vincular la Authorization de la Fase 2.
- [ ] Humo conversacional: "¿qué tablas hay sobre ventas?" → el Catalog Agent responde con entradas reales del catálogo (nombres exactos, no inventados).

**Criterio de salida:** conversación de descubrimiento funcionando de punta a punta con metadata real.

---

## Fase 7 · Pruebas end-to-end (matriz de aceptación)

Con los usuarios A y B de la Fase 3:

- [ ] **Consulta feliz (A):** pregunta de negocio → SQL mostrado + resultados correctos + los `job_labels` visibles:
  ```sql
  SELECT user_email, query, total_bytes_billed
  FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
  WHERE labels[SAFE_OFFSET(0)].value = 'bq-adhoc-agents'
  ORDER BY creation_time DESC LIMIT 10;
  ```
  El `user_email` del job debe ser el del USUARIO, no la SA.
- [ ] **IAM (B):** misma pregunta con usuario B → 403 explicado con cortesía, sin reintentos evasivos.
- [ ] **RLS:** misma pregunta con A y con otro usuario con política distinta → respuestas distintas y correctas.
- [ ] **Masking:** consulta que incluya la columna con policy tag → valores enmascarados presentados tal cual, con explicación breve.
- [ ] **Presupuesto:** pregunta que fuerce full scan de una tabla grande → el dry-run la detiene y el agente propone acotarla.
- [ ] **Gráfica:** "…en barras" → PNG inline coherente con la tabla.
- [ ] **Routing Looker-first** (si aplica): pregunta sobre un dato modelado en Looker → el orquestador ofrece la ruta gobernada y delega al aceptar.
- [ ] **Ciclo de calidad completo:** "propón reglas de calidad para X" → perfil → propuesta en lenguaje de negocio → confirmación → PR abierto (URL entregada) → comentario con reporte de gobierno (columnas verificadas, policy tags, volumen) → chat notificado → steward aprueba/merge → scan creado y primera corrida → score visible en la ficha de la tabla → el Catalog Agent lo reporta al preguntarle por la tabla.
- [ ] **Negativo de calidad:** propuesta con una columna inexistente → `governance_report.py` la marca ❌ y el pipeline queda rojo.

**Criterio de salida:** matriz completa en verde; cualquier rojo se corrige antes de abrir a más usuarios.

---

## Fase 8 · Operación continua

- [ ] Dashboard/consulta programada sobre `INFORMATION_SCHEMA.JOBS` filtrando `origin=bq-adhoc-agents` (costo, usuarios, tablas más consultadas — insumo para el futuro Onboarding Agent hacia LookML).
- [ ] Si configuraste `DQ_RESULTS_TABLE`: alerta sobre scans con `passed=false`.
- [ ] Recordatorio de PRs de gobierno abiertos >N días (Scheduler → webhook del chat).
- [ ] Rotación calendarizada de `dq-git-token` y de los tokens de CI (`GITLAB_TOKEN`/`BB_TOKEN`).
- [ ] Revisión trimestral: bindings WIF (¿siguen acotados a repo+rama/environment?), roles de las 3 SAs, allowlist de datasets, umbral `BQ_MAX_BYTES_BILLED`.
- [ ] Criterio de graduación de tablas: N preguntas ad-hoc recurrentes sobre la misma tabla → candidata a onboarding en Looker (cerrar el ciclo con bi-selfservice-agents).

---

## Rollbacks rápidos

| Qué falló | Acción |
|---|---|
| Regla de calidad mala en producción | Revert del PR en el repo de gobierno → el CI re-aplica el estado anterior |
| Token de bot comprometido | Revocar en la plataforma Git + nueva versión del secreto `dq-git-token` |
| Query runaway / costo | Bajar `BQ_MAX_BYTES_BILLED` (redeploy del SQL Agent) — el techo aplica de inmediato |
| Agente comprometido | Ningún acceso a datos que revocar (EUC): basta pausar el servicio de Cloud Run |
