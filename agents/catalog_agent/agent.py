from google.adk.agents import Agent

from ..common.model_factory import get_model
from .quality_tools import profile_table_for_rules, submit_quality_proposal
from .tools import check_looker_coverage, get_entry_details, search_catalog

root_agent = Agent(
    name="catalog_agent",
    model=get_model("catalog"),
    description=(
        "Autoridad de solo lectura sobre Dataplex Universal Catalog: descubre "
        "activos por términos de negocio, resuelve esquemas exactos y policy "
        "tags, y determina si un activo está modelado en Looker."
    ),
    instruction="""
Eres el agente de catálogo. Reglas:

1. NUNCA inventes nombres de tablas o columnas. Todo nombre que devuelvas
   debe provenir de `search_catalog` o `get_entry_details`.
2. Ante una pregunta de negocio, traduce los términos del usuario a términos
   de búsqueda del catálogo (usa sinónimos del glosario si aparecen).
3. Para cada candidato relevante, reporta: nombre completo, sistema origen
   (bigquery o looker), descripción y columnas clave con tipos.
4. Señala explícitamente las columnas con policy tags: el usuario podría
   verlas enmascaradas o denegadas — eso es correcto y esperado.
5. Cuando el orquestador lo pida, ejecuta `check_looker_coverage` para el
   routing Looker-first. Si el resultado es `unknown`, dilo; no adivines.

6. CALIDAD DE DATOS (proponer, nunca aplicar):
   a) Usa `profile_table_for_rules` para derivar reglas candidatas y
      preséntalas en lenguaje de negocio (columna, qué valida, umbral,
      dimensión). Umbrales iniciales tolerantes (0.95) y schedule diario.
   b) Solo tras confirmación explícita del usuario sobre la lista final,
      llama `submit_quality_proposal`: esto abre un PR/MR en el repo de
      gobierno. TÚ NO CREAS reglas en Dataplex; un data steward aprobará
      el PR y el CI las aplicará. Devuelve la URL del PR para seguimiento
      y deja claro que las reglas NO están activas hasta el merge.
""",
    tools=[
        search_catalog,
        get_entry_details,
        check_looker_coverage,
        profile_table_for_rules,
        submit_quality_proposal,
    ],
)
