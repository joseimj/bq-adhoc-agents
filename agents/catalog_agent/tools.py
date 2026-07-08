"""Tools del Catalog Agent sobre Dataplex Universal Catalog.

Rol equivalente al Catalog Agent (LookML) del repo hermano: barrera
anti-alucinación. El SQL Agent solo acepta tablas y columnas con nombre
exacto `project.dataset.table` / `column` previamente resueltos aquí.

La metadata (descripciones, glosario, policy tags, linaje) proviene del
harvest automático que Dataplex hace de BigQuery — y, si la organización
catalogó su instancia de Looker, las entradas de Looker aparecen en el
mismo catálogo, lo que habilita el routing Looker-first del orquestador.
"""

import os

from google.cloud import dataplex_v1

PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT_ID"]
CATALOG_LOCATION = os.environ.get("DATAPLEX_LOCATION", "global")
# Allowlist opcional de datasets visibles para los agentes (defensa en
# profundidad; el techo real siempre es el IAM del usuario final).
DATASET_ALLOWLIST = [
    d.strip() for d in os.environ.get("BQ_DATASET_ALLOWLIST", "").split(",") if d.strip()
]

_client = dataplex_v1.CatalogServiceClient()


def search_catalog(query: str, max_results: int = 10) -> list[dict]:
    """Busca activos de datos por término de negocio en Dataplex Universal Catalog.

    Args:
        query: términos de negocio ("ventas", "churn", "inventario CDMX").
        max_results: máximo de entradas a devolver.

    Returns:
        Entradas con nombre completo, sistema origen (bigquery/looker),
        descripción y aspectos relevantes.
    """
    request = dataplex_v1.SearchEntriesRequest(
        name=f"projects/{PROJECT_ID}/locations/{CATALOG_LOCATION}",
        query=query,
        page_size=max_results,
    )
    results = []
    for r in _client.search_entries(request=request):
        entry = r.dataplex_entry
        fqn = entry.fully_qualified_name  # p. ej. bigquery:proj.ds.tabla | looker:...
        system = fqn.split(":", 1)[0] if ":" in fqn else "unknown"
        if system == "bigquery" and DATASET_ALLOWLIST:
            if not any(f".{ds}." in fqn or fqn.endswith(f".{ds}") for ds in DATASET_ALLOWLIST):
                continue
        results.append(
            {
                "fully_qualified_name": fqn,
                "source_system": system,
                "display_name": entry.entry_source.display_name,
                "description": entry.entry_source.description,
                "entry_type": entry.entry_type,
            }
        )
    return results


def get_entry_details(fully_qualified_name: str) -> dict:
    """Resuelve el detalle de una entrada: esquema, descripciones de columnas,
    aspectos (glosario, calidad, policy tags) y linaje básico.

    El resultado es el contrato que el SQL Agent usa para generar SQL:
    nombres exactos de columnas, tipos, y qué columnas están protegidas
    por policy tags (para anticipar al usuario que podrían venir enmascaradas).
    """
    request = dataplex_v1.LookupEntryRequest(
        name=f"projects/{PROJECT_ID}/locations/{CATALOG_LOCATION}",
        entry=fully_qualified_name,
        view=dataplex_v1.EntryView.ALL,
    )
    entry = _client.lookup_entry(request=request)

    schema_columns = []
    policy_tagged = []
    for aspect_key, aspect in entry.aspects.items():
        data = dict(aspect.data) if aspect.data else {}
        if "schema" in aspect_key and "fields" in data:
            for f in data["fields"]:
                col = {
                    "name": f.get("name"),
                    "type": f.get("dataType") or f.get("type"),
                    "description": f.get("description", ""),
                }
                schema_columns.append(col)
                if f.get("policyTags") or f.get("policy_tags"):
                    policy_tagged.append(f.get("name"))

    return {
        "fully_qualified_name": entry.fully_qualified_name,
        "description": entry.entry_source.description,
        "columns": schema_columns,
        "policy_tagged_columns": policy_tagged,
        "note": (
            "Las columnas con policy tags pueden devolverse enmascaradas o "
            "denegadas según los permisos del usuario; eso lo resuelve BigQuery "
            "en tiempo de ejecución, no este agente."
        ),
    }


def check_looker_coverage(fully_qualified_name: str) -> dict:
    """Determina si el activo está modelado en Looker (routing Looker-first).

    Heurística sobre el catálogo: busca entradas de sistema `looker` cuyo
    linaje/nombre referencie la tabla BQ. Si la organización no catalogó
    Looker en Dataplex, devuelve `unknown` y el orquestador aplica su
    fallback (consultar por A2A al Catalog Agent del repo hermano).
    """
    table_ref = fully_qualified_name.split(":", 1)[-1]
    request = dataplex_v1.SearchEntriesRequest(
        name=f"projects/{PROJECT_ID}/locations/{CATALOG_LOCATION}",
        query=f"system=looker {table_ref.split('.')[-1]}",
        page_size=5,
    )
    looker_entries = [
        r.dataplex_entry.fully_qualified_name
        for r in _client.search_entries(request=request)
        if r.dataplex_entry.fully_qualified_name.startswith("looker:")
    ]
    return {
        "table": table_ref,
        "covered_by_looker": bool(looker_entries),
        "looker_entries": looker_entries,
        "confidence": "catalog_heuristic" if looker_entries else "unknown",
    }
