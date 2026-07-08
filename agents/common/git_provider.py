"""Adaptadores de proveedor Git para someter propuestas de reglas de calidad.

Interfaz única: crear rama -> commit de archivo -> abrir PR/MR. El proveedor
es configuración por repo de gobierno, no arquitectura: dominios distintos
pueden vivir en plataformas distintas con el mismo flujo.

Config (env):
  GIT_PROVIDER        github | gitlab | bitbucket
  GIT_REPO            github: owner/repo · gitlab: id o grupo%2Frepo ·
                      bitbucket: workspace/repo_slug
  GIT_BASE_BRANCH     default: main
  GIT_TOKEN           token con permiso de contenido+PR (inyectado desde
                      Secret Manager como variable de entorno; nunca en código)
  GIT_API_BASE        opcional, para instancias self-hosted
                      (GitLab self-managed, GitHub Enterprise, Bitbucket DC*)

* Bitbucket Data Center usa la API 1.0 con rutas distintas a Bitbucket Cloud;
  este adaptador implementa Cloud (api.bitbucket.org/2.0). Para DC, añade un
  cuarto adaptador con la misma interfaz.
"""

import base64
import os
from urllib.parse import quote

import httpx

PROVIDER = os.environ.get("GIT_PROVIDER", "github")
REPO = os.environ.get("GIT_REPO", "")
BASE_BRANCH = os.environ.get("GIT_BASE_BRANCH", "main")
TOKEN = os.environ.get("GIT_TOKEN", "")


class GitProvider:
    """Contrato mínimo que necesitan los agentes."""

    def submit_proposal(
        self, branch: str, path: str, content: str, title: str, body: str
    ) -> dict:
        """Crea rama desde base, commitea `content` en `path`, abre PR/MR.

        Returns: {url, id, provider} de la propuesta para dar seguimiento.
        """
        raise NotImplementedError


class GitHubProvider(GitProvider):
    def __init__(self):
        self.base = os.environ.get("GIT_API_BASE", "https://api.github.com")
        self.h = {
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
        }

    def submit_proposal(self, branch, path, content, title, body):
        with httpx.Client(headers=self.h, timeout=30) as c:
            sha = c.get(
                f"{self.base}/repos/{REPO}/git/ref/heads/{BASE_BRANCH}"
            ).json()["object"]["sha"]
            c.post(
                f"{self.base}/repos/{REPO}/git/refs",
                json={"ref": f"refs/heads/{branch}", "sha": sha},
            )
            c.put(
                f"{self.base}/repos/{REPO}/contents/{path}",
                json={
                    "message": title,
                    "branch": branch,
                    "content": base64.b64encode(content.encode()).decode(),
                },
            ).raise_for_status()
            pr = c.post(
                f"{self.base}/repos/{REPO}/pulls",
                json={
                    "title": title,
                    "body": body,
                    "head": branch,
                    "base": BASE_BRANCH,
                },
            ).json()
        return {"provider": "github", "id": pr.get("number"), "url": pr.get("html_url")}


class GitLabProvider(GitProvider):
    def __init__(self):
        self.base = os.environ.get("GIT_API_BASE", "https://gitlab.com/api/v4")
        self.h = {"PRIVATE-TOKEN": TOKEN}
        self.proj = quote(REPO, safe="")

    def submit_proposal(self, branch, path, content, title, body):
        with httpx.Client(headers=self.h, timeout=30) as c:
            c.post(
                f"{self.base}/projects/{self.proj}/repository/branches",
                params={"branch": branch, "ref": BASE_BRANCH},
            )
            c.post(
                f"{self.base}/projects/{self.proj}/repository/files/{quote(path, safe='')}",
                json={
                    "branch": branch,
                    "content": content,
                    "commit_message": title,
                },
            ).raise_for_status()
            mr = c.post(
                f"{self.base}/projects/{self.proj}/merge_requests",
                json={
                    "source_branch": branch,
                    "target_branch": BASE_BRANCH,
                    "title": title,
                    "description": body,
                },
            ).json()
        return {"provider": "gitlab", "id": mr.get("iid"), "url": mr.get("web_url")}


class BitbucketProvider(GitProvider):
    """Bitbucket Cloud (api.bitbucket.org/2.0)."""

    def __init__(self):
        self.base = os.environ.get("GIT_API_BASE", "https://api.bitbucket.org/2.0")
        self.h = {"Authorization": f"Bearer {TOKEN}"}

    def submit_proposal(self, branch, path, content, title, body):
        with httpx.Client(headers=self.h, timeout=30) as c:
            main = c.get(
                f"{self.base}/repositories/{REPO}/refs/branches/{BASE_BRANCH}"
            ).json()
            c.post(
                f"{self.base}/repositories/{REPO}/refs/branches",
                json={"name": branch, "target": {"hash": main["target"]["hash"]}},
            )
            # POST /src crea un commit con el archivo sobre la rama indicada
            c.post(
                f"{self.base}/repositories/{REPO}/src",
                data={"branch": branch, "message": title, path: content},
            ).raise_for_status()
            pr = c.post(
                f"{self.base}/repositories/{REPO}/pullrequests",
                json={
                    "title": title,
                    "description": body,
                    "source": {"branch": {"name": branch}},
                    "destination": {"branch": {"name": BASE_BRANCH}},
                },
            ).json()
        return {
            "provider": "bitbucket",
            "id": pr.get("id"),
            "url": pr.get("links", {}).get("html", {}).get("href"),
        }


_PROVIDERS = {
    "github": GitHubProvider,
    "gitlab": GitLabProvider,
    "bitbucket": BitbucketProvider,
}


def get_provider() -> GitProvider:
    try:
        return _PROVIDERS[PROVIDER]()
    except KeyError:
        raise ValueError(
            f"GIT_PROVIDER '{PROVIDER}' no soportado; usa github|gitlab|bitbucket"
        )
