"""Dry-run de BigQuery con credenciales del usuario final.

El dry-run es la versión "preview_query" de este sistema: valida contra el
esquema REAL (no contra la memoria del modelo), estima bytes escaneados y
detecta errores de sintaxis o de permisos antes de gastar un solo byte.
"""

import os

from google.adk.tools import ToolContext
from google.cloud import bigquery
from google.oauth2.credentials import Credentials

from ..common.euc import EUC_MODE, GE_AUTH_ID

MAX_BYTES = int(os.environ.get("BQ_MAX_BYTES_BILLED", 10 * 1024**3))
BILLING_PROJECT = os.environ.get("BQ_BILLING_PROJECT") or os.environ[
    "GOOGLE_CLOUD_PROJECT_ID"
]


def _user_client(tool_context: ToolContext) -> bigquery.Client:
    """Cliente BQ con la identidad del usuario final (nunca la SA)."""
    if EUC_MODE == "gemini_enterprise":
        token = tool_context.state.get(GE_AUTH_ID)
        if not token:
            raise PermissionError(
                "No hay token OAuth del usuario en la sesión; la superficie "
                "debe completar la autorización antes de consultar datos."
            )
        creds = Credentials(token=token)
        return bigquery.Client(project=BILLING_PROJECT, credentials=creds)
    # oauth_interactive lo resuelve el BigQueryToolset; adc = solo dev.
    return bigquery.Client(project=BILLING_PROJECT)


def dry_run_sql(sql: str, tool_context: ToolContext) -> dict:
    """Valida un SQL sin ejecutarlo: sintaxis, esquema, permisos y costo.

    Args:
        sql: query GoogleSQL de solo lectura a validar.

    Returns:
        valid, bytes estimados, si excede el techo, y esquema de salida;
        o el error exacto de BigQuery para que el agente lo corrija.
    """
    client = _user_client(tool_context)
    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    try:
        job = client.query(sql, job_config=job_config)
    except Exception as e:  # devolver el error crudo: es la señal de corrección
        return {"valid": False, "error": str(e)}

    total = job.total_bytes_processed or 0
    return {
        "valid": True,
        "estimated_bytes_processed": total,
        "estimated_gib": round(total / 1024**3, 3),
        "exceeds_budget": total > MAX_BYTES,
        "budget_gib": round(MAX_BYTES / 1024**3, 1),
        "output_schema": [
            {"name": f.name, "type": f.field_type} for f in (job.schema or [])
        ],
    }
