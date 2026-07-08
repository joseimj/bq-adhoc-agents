variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "us-central1"
}
variable "artifact_repo" {
  type    = string
  default = "bq-adhoc-agents"
}
variable "euc_mode" {
  type    = string
  default = "gemini_enterprise"
}

# Repo de gobierno (uno activo; deja vacío lo que no uses)
variable "git_provider" { type = string } # github | gitlab | bitbucket
variable "git_repo" { type = string }     # owner/repo · grupo/proyecto · workspace/slug

variable "github_repo" {
  type    = string
  default = ""
} # owner/repo para WIF
variable "gitlab_project_path" {
  type    = string
  default = ""
}
variable "gitlab_issuer_uri" {
  type    = string
  default = "https://gitlab.com"
}
variable "bitbucket_issuer_uri" {
  type    = string
  default = ""
} # identidad OIDC del workspace
variable "bitbucket_audience" {
  type    = string
  default = ""
}
variable "bitbucket_repo_uuid" {
  type    = string
  default = ""
}

variable "protected_branch" {
  type    = string
  default = "main"
}
variable "bitbucket_deployment_env_uuid" {
  type        = string
  default     = ""
  description = "UUID del deployment environment de Bitbucket restringido a la rama protegida; requerido para que apply pueda asumir la SA de gobierno"
}
