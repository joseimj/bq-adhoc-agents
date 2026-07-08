#!/usr/bin/env python3
"""Publica report.md como comentario del PR y notifica al chat de stewards.

Multi-plataforma vía variables que cada CI ya provee:
  GitHub Actions:  GITHUB_REPOSITORY, PR_NUMBER (del workflow), GITHUB_TOKEN
  GitLab CI:       CI_PROJECT_ID, CI_MERGE_REQUEST_IID, GITLAB_TOKEN
  Bitbucket:       BITBUCKET_WORKSPACE, BITBUCKET_REPO_SLUG,
                   BITBUCKET_PR_ID, BB_TOKEN

Notificación uniforme: si CHAT_WEBHOOK_URL está definida (webhook entrante de
Google Chat o Slack), se envía un resumen con la liga del PR — mismo
mecanismo en las tres plataformas, sin apps por-plataforma.
"""

import os
import sys

import httpx


def read_report() -> str:
    try:
        return open("report.md").read()
    except FileNotFoundError:
        return "Sin reporte generado."


def comment_pr(body: str) -> str:
    if os.environ.get("GITHUB_REPOSITORY") and os.environ.get("PR_NUMBER"):
        repo, pr = os.environ["GITHUB_REPOSITORY"], os.environ["PR_NUMBER"]
        httpx.post(
            f"https://api.github.com/repos/{repo}/issues/{pr}/comments",
            headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"},
            json={"body": body},
            timeout=30,
        ).raise_for_status()
        return f"https://github.com/{repo}/pull/{pr}"

    if os.environ.get("CI_MERGE_REQUEST_IID"):
        base = os.environ.get("CI_API_V4_URL", "https://gitlab.com/api/v4")
        proj, mr = os.environ["CI_PROJECT_ID"], os.environ["CI_MERGE_REQUEST_IID"]
        httpx.post(
            f"{base}/projects/{proj}/merge_requests/{mr}/notes",
            headers={"PRIVATE-TOKEN": os.environ["GITLAB_TOKEN"]},
            json={"body": body},
            timeout=30,
        ).raise_for_status()
        return os.environ.get("CI_MERGE_REQUEST_PROJECT_URL", "") + f"/-/merge_requests/{mr}"

    if os.environ.get("BITBUCKET_PR_ID"):
        ws = os.environ["BITBUCKET_WORKSPACE"]
        slug = os.environ["BITBUCKET_REPO_SLUG"]
        pr = os.environ["BITBUCKET_PR_ID"]
        httpx.post(
            f"https://api.bitbucket.org/2.0/repositories/{ws}/{slug}/pullrequests/{pr}/comments",
            headers={"Authorization": f"Bearer {os.environ['BB_TOKEN']}"},
            json={"content": {"raw": body}},
            timeout=30,
        ).raise_for_status()
        return f"https://bitbucket.org/{ws}/{slug}/pull-requests/{pr}"

    print("Sin contexto de PR detectado; solo notificación de chat.", file=sys.stderr)
    return ""


def notify_chat(pr_url: str, report: str):
    url = os.environ.get("CHAT_WEBHOOK_URL")
    if not url:
        return
    summary = report.split("\n")[0].replace("###", "").strip()
    text = (
        f"🧪 *Propuesta de reglas de calidad pendiente de aprobación*\n"
        f"{summary}\n{pr_url or '(ver PR en la plataforma)'}"
    )
    httpx.post(url, json={"text": text}, timeout=15)


if __name__ == "__main__":
    report = read_report()
    pr_url = comment_pr(report)
    notify_chat(pr_url, report)
    print("comentario y notificación enviados")
