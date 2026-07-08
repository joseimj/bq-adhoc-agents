# bq-adhoc-agents · infraestructura
# Patrón espejo de bi-selfservice-agents; lo nuevo aquí: separación de
# identidades (agentes sin datos / lector de PRs / gobernanza de DQ) y
# Workload Identity Federation para GitHub, GitLab y Bitbucket.

locals {
  services = ["run.googleapis.com", "bigquery.googleapis.com",
    "dataplex.googleapis.com", "aiplatform.googleapis.com",
    "secretmanager.googleapis.com", "iamcredentials.googleapis.com",
  "sts.googleapis.com", "artifactregistry.googleapis.com"]
  agents = ["catalog", "sql", "viz", "orchestrator"]
}

resource "google_project_service" "apis" {
  for_each = toset(local.services)
  project  = var.project_id
  service  = each.value
}

# ── Identidades ──────────────────────────────────────────────────────────────
# 1) SA de los agentes: SOLO plataforma. Sin roles de datos de BQ: las queries
#    de negocio corren con el token OAuth del usuario final (EUC).
resource "google_service_account" "agents" {
  project      = var.project_id
  account_id   = "bq-adhoc-agents"
  display_name = "bq-adhoc-agents (runtime, sin acceso a datos)"
}
resource "google_project_iam_member" "agents_roles" {
  for_each = toset(["roles/logging.logWriter", "roles/dataplex.catalogViewer",
  "roles/aiplatform.user", "roles/secretmanager.secretAccessor"])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.agents.email}"
}

# 2) SA lectora para el paso `validate` de los PRs (reporte de gobierno):
#    lee catálogo, metadatos de tablas y resultados de scans. NUNCA escribe.
resource "google_service_account" "dq_reader" {
  project      = var.project_id
  account_id   = "dq-rules-reader"
  display_name = "dq-rules-repo · validate (solo lectura)"
}
resource "google_project_iam_member" "reader_roles" {
  for_each = toset(["roles/dataplex.catalogViewer", "roles/dataplex.dataScanViewer",
  "roles/bigquery.metadataViewer"])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.dq_reader.email}"
}

# 3) SA de gobierno: LA ÚNICA identidad con escritura de DataScans.
#    Solo la asumen los jobs de CI tras un merge aprobado por steward.
resource "google_service_account" "dq_governance" {
  project      = var.project_id
  account_id   = "dq-rules-governance"
  display_name = "dq-rules-repo · apply (escritura AutoDQ)"
}
resource "google_project_iam_member" "governance_roles" {
  for_each = toset(["roles/dataplex.dataScanEditor", "roles/bigquery.metadataViewer"])
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.dq_governance.email}"
}

# ── Workload Identity Federation: un pool, tres providers ────────────────────
resource "google_iam_workload_identity_pool" "ci" {
  project                   = var.project_id
  workload_identity_pool_id = "dq-ci-pool"
  display_name              = "CI de dq-rules-repo"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  count                              = var.github_repo != "" ? 1 : 0
  project                            = var.project_id
  workload_identity_pool_id         = google_iam_workload_identity_pool.ci.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub Actions"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    # repo@ref en un solo atributo: permite atar la SA de gobierno a la rama.
    # push a main => refs/heads/main; PR => refs/pull/N/merge (nunca matchea).
    "attribute.repo_ref"   = "assertion.repository + \"@\" + assertion.ref"
  }
  attribute_condition = "attribute.repository == \"${var.github_repo}\""
  oidc { issuer_uri = "https://token.actions.githubusercontent.com" }
}

resource "google_iam_workload_identity_pool_provider" "gitlab" {
  count                              = var.gitlab_project_path != "" ? 1 : 0
  project                            = var.project_id
  workload_identity_pool_id         = google_iam_workload_identity_pool.ci.workload_identity_pool_id
  workload_identity_pool_provider_id = "gitlab"
  display_name                       = "GitLab CI"
  attribute_mapping = {
    "google.subject"          = "assertion.sub"
    "attribute.project_path"  = "assertion.project_path"
    # Pipelines de MR llevan el ref de la rama fuente: no matchean main.
    "attribute.project_ref"   = "assertion.project_path + \"@\" + assertion.ref"
    "attribute.ref_protected" = "assertion.ref_protected"
  }
  attribute_condition = "attribute.project_path == \"${var.gitlab_project_path}\""
  oidc { issuer_uri = var.gitlab_issuer_uri } # https://gitlab.com o self-managed
}

resource "google_iam_workload_identity_pool_provider" "bitbucket" {
  count                              = var.bitbucket_audience != "" ? 1 : 0
  project                            = var.project_id
  workload_identity_pool_id         = google_iam_workload_identity_pool.ci.workload_identity_pool_id
  workload_identity_pool_provider_id = "bitbucket"
  display_name                       = "Bitbucket Pipelines"
  attribute_mapping = {
    "google.subject"            = "assertion.sub"
    "attribute.repository_uuid" = "assertion.repositoryUuid"
    # El token de Bitbucket NO trae rama. El step `apply` usa un deployment
    # environment restringido a main (config en Bitbucket): solo entonces el
    # token incluye deploymentEnvironmentUuid, y sobre ese UUID se ata la SA
    # de gobierno. Steps sin deployment mapean a "none".
    "attribute.deployment_env"  = "has(assertion.deploymentEnvironmentUuid) ? assertion.deploymentEnvironmentUuid : \"none\""
  }
  attribute_condition = "attribute.repository_uuid == \"${var.bitbucket_repo_uuid}\""
  oidc {
    issuer_uri        = var.bitbucket_issuer_uri # de la config OIDC del workspace
    allowed_audiences = [var.bitbucket_audience]
  }
}

# Bindings dirigidos: la LECTORA se puede asumir desde cualquier evento del
# repo de gobierno; la de GOBERNANZA solo desde el evento de merge a la rama
# protegida (GitHub/GitLab por claim de ref; Bitbucket por deployment env).
locals {
  pool = google_iam_workload_identity_pool.ci.name

  reader_principals = merge(
    var.github_repo != "" ? {
      github = "principalSet://iam.googleapis.com/${local.pool}/attribute.repository/${var.github_repo}"
    } : {},
    var.gitlab_project_path != "" ? {
      gitlab = "principalSet://iam.googleapis.com/${local.pool}/attribute.project_path/${var.gitlab_project_path}"
    } : {},
    var.bitbucket_repo_uuid != "" ? {
      bitbucket = "principalSet://iam.googleapis.com/${local.pool}/attribute.repository_uuid/${var.bitbucket_repo_uuid}"
    } : {},
  )

  governance_principals = merge(
    var.github_repo != "" ? {
      github = "principalSet://iam.googleapis.com/${local.pool}/attribute.repo_ref/${var.github_repo}@refs/heads/${var.protected_branch}"
    } : {},
    var.gitlab_project_path != "" ? {
      gitlab = "principalSet://iam.googleapis.com/${local.pool}/attribute.project_ref/${var.gitlab_project_path}@${var.protected_branch}"
    } : {},
    var.bitbucket_deployment_env_uuid != "" ? {
      bitbucket = "principalSet://iam.googleapis.com/${local.pool}/attribute.deployment_env/${var.bitbucket_deployment_env_uuid}"
    } : {},
  )
}

resource "google_service_account_iam_member" "wif_reader" {
  for_each           = local.reader_principals
  service_account_id = google_service_account.dq_reader.name
  role               = "roles/iam.workloadIdentityUser"
  member             = each.value
}
resource "google_service_account_iam_member" "wif_governance" {
  for_each           = local.governance_principals
  service_account_id = google_service_account.dq_governance.name
  role               = "roles/iam.workloadIdentityUser"
  member             = each.value
}

# ── Secretos ─────────────────────────────────────────────────────────────────
# Token del bot para que el Catalog Agent abra PRs (github|gitlab|bitbucket).
resource "google_secret_manager_secret" "git_token" {
  project   = var.project_id
  secret_id = "dq-git-token"
  replication { auto {} }
}

# ── Cloud Run: especialistas + orquestador A2A (ingress interno) ─────────────
resource "google_cloud_run_v2_service" "agent" {
  for_each = toset(local.agents)
  project  = var.project_id
  location = var.region
  name     = "bq-adhoc-${each.value}"
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.agents.email
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_repo}/${each.value}:latest"
      env {
        name  = "GOOGLE_CLOUD_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "EUC_MODE"
        value = var.euc_mode
      }
      env {
        name  = "GIT_PROVIDER"
        value = var.git_provider
      }
      env {
        name  = "GIT_REPO"
        value = var.git_repo
      }
      env {
        name = "GIT_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.git_token.secret_id
            version = "latest"
          }
        }
      }
    }
  }
}

# El orquestador invoca a los especialistas por A2A con IAM.
resource "google_cloud_run_v2_service_iam_member" "invoker" {
  for_each = toset(["catalog", "sql", "viz"])
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.agent[each.value].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.agents.email}"
}

output "wif_providers" {
  value = {
    github    = try(google_iam_workload_identity_pool_provider.github[0].name, null)
    gitlab    = try(google_iam_workload_identity_pool_provider.gitlab[0].name, null)
    bitbucket = try(google_iam_workload_identity_pool_provider.bitbucket[0].name, null)
  }
  description = "Valores de WIF_PROVIDER a configurar en cada CI"
}
output "service_accounts" {
  value = {
    agents     = google_service_account.agents.email
    dq_reader  = google_service_account.dq_reader.email
    governance = google_service_account.dq_governance.email
  }
}
output "agent_urls" {
  value = { for k, v in google_cloud_run_v2_service.agent : k => v.uri }
}
