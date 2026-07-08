"""End-User Credentials (EUC) para BigQuery.

Principio de diseño: el agente NUNCA decide qué datos puede ver el usuario.
Toda query se ejecuta con la identidad del usuario final, de modo que
BigQuery aplica por sí mismo:

  - IAM sobre datasets/tablas/vistas autorizadas
  - Row-Level Security (row access policies)
  - Column-Level Security / enmascaramiento (policy tags de Dataplex)
  - VPC Service Controls, si aplica

Tres modos, seleccionados por EUC_MODE:

  gemini_enterprise  -> el token OAuth del usuario lo gestiona la plataforma
                        (Gemini Enterprise) y ADK lo resuelve desde el session
                        state vía `external_access_token_key`.
  oauth_interactive  -> frontend propio (A2UI): ADK dispara el flujo OAuth 2.0
                        con client_id/client_secret y guarda el token en sesión.
  adc                -> SOLO desarrollo local (identidad del developer).

Nunca se usa una service account para ejecutar SQL de negocio: la SA de los
agentes solo tiene permisos de plataforma (logging, artifacts, Dataplex read).
"""

import os

from google.adk.tools.bigquery import BigQueryCredentialsConfig, BigQueryToolset
from google.adk.tools.bigquery.config import BigQueryToolConfig, WriteMode

# Clave bajo la que Gemini Enterprise deposita el access token del usuario
# en el session state (configurada al registrar la Authorization en GE).
GE_AUTH_ID = os.environ.get("GE_AUTH_ID", "bq_user_oauth")

EUC_MODE = os.environ.get("EUC_MODE", "gemini_enterprise")


def build_credentials_config() -> BigQueryCredentialsConfig:
    """Config de credenciales según la superficie de consumo."""
    if EUC_MODE == "gemini_enterprise":
        # El token viaja gestionado por la plataforma; ADK lo lee del state.
        return BigQueryCredentialsConfig(external_access_token_key=GE_AUTH_ID)

    if EUC_MODE == "oauth_interactive":
        # Frontend A2UI / adk web: login OAuth del propio usuario.
        return BigQueryCredentialsConfig(
            client_id=os.environ["OAUTH_CLIENT_ID"],
            client_secret=os.environ["OAUTH_CLIENT_SECRET"],
        )

    if EUC_MODE == "adc":
        import google.auth

        credentials, _ = google.auth.default()
        return BigQueryCredentialsConfig(credentials=credentials)

    raise ValueError(f"EUC_MODE desconocido: {EUC_MODE}")


def build_tool_config() -> BigQueryToolConfig:
    """Guardrails no negociables de la ruta ad-hoc.

    - Solo lectura (WriteMode.BLOCKED): este sistema responde preguntas,
      no materializa contenido; la escritura gobernada vive en el repo hermano.
    - Techo de bytes facturados por query (protección de costo y de scans
      accidentales de tablas enormes).
    - Tope de filas devueltas al LLM: los datasets completos jamás entran
      al contexto del modelo.
    - job_labels: toda query queda etiquetada para auditoría en
      INFORMATION_SCHEMA.JOBS / Cloud Audit Logs.
    """
    return BigQueryToolConfig(
        write_mode=WriteMode.BLOCKED,
        maximum_bytes_billed=int(
            os.environ.get("BQ_MAX_BYTES_BILLED", 10 * 1024**3)  # 10 GiB
        ),
        max_query_result_rows=int(os.environ.get("BQ_MAX_RESULT_ROWS", 200)),
        job_labels={
            "origin": "bq-adhoc-agents",
            "surface": EUC_MODE,
        },
    )


def build_bigquery_toolset(tool_filter: list[str] | None = None) -> BigQueryToolset:
    return BigQueryToolset(
        credentials_config=build_credentials_config(),
        bigquery_tool_config=build_tool_config(),
        tool_filter=tool_filter,
    )
