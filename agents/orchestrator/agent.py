"""Orquestador router: Looker-first, BQ ad-hoc como complemento.

Complementa a bi-selfservice-agents (github.com/joseimj/bi-selfservice-agents):
si el dato está modelado en Looker, la respuesta correcta es la métrica
gobernada por LookML — se delega vía A2A al orquestador hermano. Si el dato
NO está onboardeado en Looker, entra la cuadrilla BQ ad-hoc de este repo.

Looker es "core preferido", no regla: la delegación es condicional a la
cobertura reportada por el catálogo y a que el usuario tenga superficie
Looker (algunos usuarios pueden operar solo sobre BQ, e.g. Looker Original
sin API self-service habilitada).
"""

import os

from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH, RemoteA2aAgent

from ..common.model_factory import get_model


def _remote(name: str, env_url: str, description: str) -> RemoteA2aAgent:
    return RemoteA2aAgent(
        name=name,
        description=description,
        agent_card=f"{os.environ[env_url].rstrip('/')}{AGENT_CARD_WELL_KNOWN_PATH}",
    )


catalog = _remote(
    "catalog_agent",
    "CATALOG_AGENT_URL",
    "Descubre activos en Dataplex Universal Catalog, resuelve esquemas "
    "exactos y policy tags, y determina cobertura Looker.",
)
sql = _remote(
    "sql_agent",
    "SQL_AGENT_URL",
    "Genera y ejecuta SQL de solo lectura en BigQuery con la identidad del "
    "usuario final; valida con dry-run.",
)
viz = _remote(
    "viz_agent",
    "VIZ_AGENT_URL",
    "Renderiza gráficas PNG (artifacts) a partir de resultados ya autorizados.",
)

sub_agents = [catalog, sql, viz]

# Delegación opcional al sistema hermano (dashboards gobernados en Looker).
if os.environ.get("LOOKER_ORCHESTRATOR_URL"):
    sub_agents.append(
        _remote(
            "looker_selfservice",
            "LOOKER_ORCHESTRATOR_URL",
            "Sistema bi-selfservice-agents: métricas gobernadas y creación de "
            "dashboards nativos en Looker (LookML).",
        )
    )

root_agent = Agent(
    name="bq_adhoc_orchestrator",
    model=get_model("orchestrator"),
    description=(
        "Responde preguntas de negocio sobre datos de BigQuery no onboardeados "
        "en Looker, respetando el control de acceso del usuario final."
    ),
    instruction="""
Eres el orquestador de analítica ad-hoc. Flujo por petición:

1. DESCUBRIR. Delega al catalog_agent la resolución de los activos
   relevantes (tablas exactas, columnas, policy tags, cobertura Looker).

2. RUTEAR (Looker-first, no Looker-only):
   - Si el activo está modelado en Looker Y existe el agente
     looker_selfservice: propón al usuario la ruta gobernada (métricas
     consistentes, dashboard persistente) y delega ahí si acepta.
   - Si NO está en Looker, la cobertura es unknown, el usuario no tiene
     Looker, o prefiere una respuesta ad-hoc: continúa con la ruta BQ.

3. ESPECIFICAR. Construye una QuerySpec breve (tablas exactas, columnas,
   filtros, agregación, periodo) y confírmala con el usuario si la
   pregunta es ambigua. Nunca pases al sql_agent nombres no resueltos
   por el catalog_agent.

4. EJECUTAR. Delega al sql_agent. Los resultados llegan ya filtrados por
   BigQuery según los permisos del usuario (IAM, RLS, policy tags).

5. RESPONDER. Sintetiza la respuesta de negocio en lenguaje claro, incluye
   el SQL usado, y si los datos son graficables ofrece/delega la gráfica
   al viz_agent.

6. CALIDAD (opcional). Si el usuario quiere definir reglas de calidad,
   delega al catalog_agent: perfilará la tabla, propondrá reglas y, con la
   confirmación del usuario, someterá un PR al repo de gobierno. Deja claro
   que las reglas se activan cuando un data steward apruebe el PR (merge),
   no antes; comparte la URL del PR.

Reglas de acceso (no negociables):
- Jamás intentes reformular una query para evitar un permiso denegado.
- Jamás uses datos de una sesión/usuario para responder a otro.
- Si el usuario pregunta por qué no ve ciertos datos: explica que el
  acceso lo gobierna BigQuery/Dataplex y sugiere contactar al data owner.
""",
    sub_agents=sub_agents,
)
