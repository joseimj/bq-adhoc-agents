"""SQL Agent: NL2SQL sobre BigQuery con credenciales del usuario final.

Análogo al par Catalog→Builder del repo hermano, pero para consulta:
- Solo acepta tablas/columnas resueltas antes por el Catalog Agent.
- Valida todo SQL con dry-run antes de ejecutar (esquema real + costo).
- Ejecuta SIEMPRE como el usuario final (ver common/euc.py): BigQuery
  aplica IAM, row-level security y enmascaramiento por policy tags.
- WriteMode.BLOCKED: incapaz de mutar datos por construcción.
"""

from google.adk.agents import Agent

from ..common.euc import build_bigquery_toolset
from ..common.model_factory import get_model
from .tools import dry_run_sql

# Toolset de primera parte de ADK, restringido a lo mínimo necesario.
bigquery_toolset = build_bigquery_toolset(
    tool_filter=[
        "get_dataset_info",
        "get_table_info",
        "execute_sql",
        # Opcional: delega el NL2SQL a Conversational Analytics con EUC.
        # "ask_data_insights",
    ]
)

root_agent = Agent(
    name="sql_agent",
    model=get_model("sql"),
    description=(
        "Genera y ejecuta SQL de solo lectura en BigQuery con la identidad "
        "del usuario final. Valida con dry-run antes de ejecutar."
    ),
    instruction="""
Eres el agente SQL. Contrato estricto:

1. Solo usa tablas y columnas que vengan en la especificación resuelta por
   el catalog_agent (nombres exactos `project.dataset.table`). Si falta una
   columna, devuelve la petición al orquestador; NO la inventes.
2. Genera GoogleSQL estándar, con LIMIT explícito (<= 200 filas) salvo en
   agregaciones.
3. Antes de ejecutar, SIEMPRE valida con `dry_run_sql`. Si el dry-run falla,
   corrige y reintenta (máx. 3 veces). Si excede el techo de bytes, propone
   una versión más acotada (partición, filtro de fecha, agregación).
4. Ejecuta con `execute_sql`. Si BigQuery deniega acceso (403 / access denied
   / row access policy), NO intentes rodearlo: informa que el usuario no
   tiene permisos sobre ese dato y sugiere solicitar acceso al data owner.
   Un permiso denegado es el sistema funcionando, no un error tuyo.
5. Si columnas vienen enmascaradas (policy tags), preséntalas tal cual y
   explica brevemente por qué.
6. Devuelve resultados tabulares compactos + el SQL final para transparencia
   y reproducibilidad.
""",
    tools=[dry_run_sql, bigquery_toolset],
)
