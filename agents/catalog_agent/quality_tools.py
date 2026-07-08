"""Tools de calidad del Catalog Agent: PROPONER, nunca aplicar.

El agente perfila la tabla, deriva reglas candidatas y, tras aprobación del
usuario en la conversación, somete la propuesta como pull request al repo de
gobierno (rules-as-code). La creación real del DataScan la hace el aplicador
determinista del CI cuando un data steward hace merge — ningún LLM tiene
permisos de escritura sobre Dataplex.
"""

import datetime
import os
import re

import yaml
from google.adk.tools import ToolContext
from google.cloud import dataplex_v1
from google.oauth2.credentials import Credentials

from ..common.euc import EUC_MODE, GE_AUTH_ID
from ..common.git_provider import get_provider

PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT_ID"]
DQ_LOCATION = os.environ.get("DATAPLEX_DQ_LOCATION", "us-central1")

VALID_RULE_TYPES = {
    "non_null",
    "uniqueness",
    "set",
    "range",
    "regex",
    "row_condition",
    "sql_assertion",
}
VALID_DIMENSIONS = {
    "COMPLETENESS",
    "UNIQUENESS",
    "VALIDITY",
    "ACCURACY",
    "CONSISTENCY",
    "FRESHNESS",
}


def _scan_client(tool_context: ToolContext) -> dataplex_v1.DataScanServiceClient:
    if EUC_MODE == "gemini_enterprise":
        token = tool_context.state.get(GE_AUTH_ID)
        if not token:
            raise PermissionError("Sesión sin token OAuth del usuario.")
        return dataplex_v1.DataScanServiceClient(credentials=Credentials(token=token))
    return dataplex_v1.DataScanServiceClient()


def profile_table_for_rules(table: str, tool_context: ToolContext) -> dict:
    """Ejecuta (o reutiliza) un profile scan on-demand y devuelve estadísticas
    por columna para derivar reglas candidatas: null ratio, distinct ratio,
    min/max, top values. Solo lectura de datos vía Dataplex; nada persiste
    como regla.
    """
    client = _scan_client(tool_context)
    parent = f"projects/{PROJECT_ID}/locations/{DQ_LOCATION}"
    scan_id = f"adhoc-profile-{re.sub(r'[^a-z0-9]', '-', table.lower())}"[:63]
    p, d, t = table.split(".")
    scan = dataplex_v1.DataScan(
        data=dataplex_v1.DataSource(
            resource=f"//bigquery.googleapis.com/projects/{p}/datasets/{d}/tables/{t}"
        ),
        data_profile_spec=dataplex_v1.DataProfileSpec(),
        execution_spec=dataplex_v1.DataScan.ExecutionSpec(
            trigger=dataplex_v1.Trigger(on_demand=dataplex_v1.Trigger.OnDemand())
        ),
        labels={"origin": "bq-adhoc-agents"},
    )
    try:
        client.create_data_scan(
            parent=parent, data_scan=scan, data_scan_id=scan_id
        ).result(timeout=300)
    except Exception as e:
        if "already exists" not in str(e).lower():
            return {"error": str(e)}
    job = client.run_data_scan(name=f"{parent}/dataScans/{scan_id}").job
    return {
        "profile_scan": scan_id,
        "job": job.name,
        "hint": (
            "Al terminar el job, deriva candidatas: null_ratio≈0 -> non_null; "
            "distinct≈rows -> uniqueness; cardinalidad baja -> set; numéricos "
            "estables -> range. Umbral inicial sugerido: 0.95."
        ),
    }


def submit_quality_proposal(
    table: str,
    rules: list[dict],
    schedule_cron: str,
    justification: str,
    tool_context: ToolContext,
) -> dict:
    """Somete una propuesta de reglas como PR/MR al repo de gobierno.

    LLAMAR SOLO tras confirmación del usuario sobre la lista final de reglas.
    No escribe nada en Dataplex: abre una propuesta que un data steward
    revisará y aprobará (merge) en GitHub/GitLab/Bitbucket según configuración.

    Args:
        table: `project.dataset.table` resuelto por el catálogo.
        rules: reglas declarativas [{type, column?, dimension, threshold,
               description, ...params}].
        schedule_cron: cron (p.ej. "0 6 * * *") o "" para on-demand.
        justification: por qué se proponen (contexto de negocio); va al PR.
    """
    errors = _validate_rules(rules)
    if errors:
        return {"submitted": False, "validation_errors": errors}

    user = tool_context.state.get("user_email", "unknown")
    now = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    spec = {
        "apiVersion": "dq.rules/v1",
        "table": table,
        "location": DQ_LOCATION,
        "schedule_cron": schedule_cron,
        "rules": rules,
        "metadata": {
            "proposed_by": user,
            "proposed_via": "bq-adhoc-agents",
            "proposed_at": now,
            "justification": justification,
        },
    }
    p, d, t = table.split(".")
    path = f"rules/{p}/{d}/{t}.yaml"
    branch = f"dq/{d}-{t}-{now}"
    title = f"DQ: {len(rules)} regla(s) para {table}"
    body = (
        f"Propuesta generada vía bq-adhoc-agents a petición de **{user}**.\n\n"
        f"**Justificación:** {justification}\n\n"
        f"El merge de este PR crea/actualiza el DataScan de Dataplex mediante "
        f"el aplicador de CI (la SA de gobierno). Revisar: columnas, umbrales, "
        f"schedule y costo del scan."
    )
    result = get_provider().submit_proposal(
        branch=branch,
        path=path,
        content=yaml.safe_dump(spec, sort_keys=False, allow_unicode=True),
        title=title,
        body=body,
    )
    return {"submitted": True, "proposal": result, "file": path}


def _validate_rules(rules: list[dict]) -> list[str]:
    """Validación previa al PR (el CI vuelve a validar; defensa doble)."""
    errors = []
    for i, r in enumerate(rules):
        if r.get("type") not in VALID_RULE_TYPES:
            errors.append(f"regla[{i}]: type inválido '{r.get('type')}'")
        if r.get("dimension", "VALIDITY") not in VALID_DIMENSIONS:
            errors.append(f"regla[{i}]: dimension inválida '{r.get('dimension')}'")
        thr = r.get("threshold", 1.0)
        if not (0.0 < float(thr) <= 1.0):
            errors.append(f"regla[{i}]: threshold fuera de (0,1]: {thr}")
        if r.get("type") != "sql_assertion" and not r.get("column"):
            errors.append(f"regla[{i}]: falta 'column'")
        if r.get("type") == "set" and not r.get("values"):
            errors.append(f"regla[{i}]: 'set' requiere 'values'")
        if r.get("type") == "row_condition" and not r.get("sql_expression"):
            errors.append(f"regla[{i}]: falta 'sql_expression'")
        if r.get("type") == "sql_assertion" and not r.get("sql_statement"):
            errors.append(f"regla[{i}]: falta 'sql_statement'")
    return errors
