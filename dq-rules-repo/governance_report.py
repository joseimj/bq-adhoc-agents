#!/usr/bin/env python3
"""Reporte de gobierno para el PR: metadata VIVA de Dataplex/BigQuery.

Se ejecuta en el paso `validate` del CI (con una SA de solo lectura) y emite
Markdown a stdout / report.md, que post_comment.py publica como comentario
del PR. Objetivo: que el steward apruebe con contexto fresco del catálogo,
no solo con el YAML.

Contenido por propuesta:
  - Descripción y tipo del entry en Dataplex Universal Catalog
  - Verificación columna-a-columna: ¿las columnas de las reglas existen HOY
    en el esquema? (drift entre propuesta y realidad = bloqueo)
  - Policy tags sobre columnas referenciadas (señal de sensibilidad)
  - Score de calidad vigente si ya existe un DataScan sobre la tabla
  - Tamaño y filas de la tabla (proxy del costo del scan programado)

Uso: python governance_report.py <archivos yaml...>  > report.md
"""

import os
import re
import sys

import yaml
from google.cloud import bigquery, dataplex_v1

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT_ID", "")
CATALOG_LOCATION = os.environ.get("DATAPLEX_LOCATION", "global")


def entry_metadata(table: str) -> dict:
    client = dataplex_v1.CatalogServiceClient()
    fqn = f"bigquery:{table}"
    try:
        entry = client.lookup_entry(
            request=dataplex_v1.LookupEntryRequest(
                name=f"projects/{PROJECT_ID}/locations/{CATALOG_LOCATION}",
                entry=fqn,
                view=dataplex_v1.EntryView.ALL,
            )
        )
    except Exception as e:
        return {"error": f"entry no encontrado en el catálogo: {e}"}

    columns, tagged = {}, []
    for key, aspect in entry.aspects.items():
        data = dict(aspect.data) if aspect.data else {}
        if "schema" in key and "fields" in data:
            for f in data["fields"]:
                columns[f.get("name")] = f.get("dataType") or f.get("type")
                if f.get("policyTags") or f.get("policy_tags"):
                    tagged.append(f.get("name"))
    return {
        "description": entry.entry_source.description or "(sin descripción)",
        "columns": columns,
        "policy_tagged": tagged,
    }


def table_stats(table: str) -> dict:
    try:
        t = bigquery.Client(project=PROJECT_ID).get_table(table)
        return {
            "rows": t.num_rows,
            "gib": round((t.num_bytes or 0) / 1024**3, 2),
        }
    except Exception as e:
        return {"error": str(e)}


def current_quality(table: str, location: str) -> dict:
    client = dataplex_v1.DataScanServiceClient()
    _, d, t = table.split(".")
    scan_id = f"dq-{re.sub(r'[^a-z0-9]', '-', (d + '-' + t).lower())}"[:63]
    try:
        scan = client.get_data_scan(
            request=dataplex_v1.GetDataScanRequest(
                name=f"projects/{PROJECT_ID}/locations/{location}/dataScans/{scan_id}",
                view=dataplex_v1.GetDataScanRequest.DataScanView.FULL,
            )
        )
        if scan.data_quality_result:
            r = scan.data_quality_result
            return {"exists": True, "passed": r.passed, "score": getattr(r, "score", None)}
        return {"exists": True, "passed": None}
    except Exception:
        return {"exists": False}


def render(path: str) -> tuple[str, bool]:
    spec = yaml.safe_load(open(path))
    table = spec["table"]
    meta = entry_metadata(table)
    stats = table_stats(table)
    dq = current_quality(table, spec.get("location", "us-central1"))

    lines = [f"### Reporte de gobierno · `{table}`", ""]
    blocking = False

    if "error" in meta:
        lines.append(f"> :warning: {meta['error']}")
        return "\n".join(lines), True

    lines.append(f"**Catálogo:** {meta['description']}")
    if meta["policy_tagged"]:
        lines.append(
            f"**Columnas con policy tags:** `{'`, `'.join(meta['policy_tagged'])}` "
            "— datos sensibles; validar que las reglas no expongan valores."
        )
    if "error" not in stats:
        lines.append(f"**Volumen:** {stats['rows']:,} filas · {stats['gib']} GiB")
    if dq.get("exists"):
        lines.append(
            f"**Scan existente:** sí (este PR lo ACTUALIZA) · último resultado: "
            f"passed={dq.get('passed')} score={dq.get('score')}"
        )
    else:
        lines.append("**Scan existente:** no (este PR lo CREA)")

    lines += ["", "| Regla | Columna | ¿Existe hoy? | Tipo actual | Policy tag |", "|---|---|---|---|---|"]
    for r in spec.get("rules", []):
        col = r.get("column", "—")
        if col == "—" or r["type"] == "sql_assertion":
            lines.append(f"| {r['type']} | — | n/a | n/a | n/a |")
            continue
        exists = col in meta["columns"]
        blocking = blocking or not exists
        lines.append(
            f"| {r['type']} | `{col}` | {'✅' if exists else '❌ NO EXISTE'} | "
            f"{meta['columns'].get(col, '—')} | "
            f"{'🔒' if col in meta['policy_tagged'] else '—'} |"
        )

    if blocking:
        lines += ["", "> :no_entry: **Bloqueante:** hay columnas que no existen en el esquema actual."]
    return "\n".join(lines), blocking


def main():
    files = sys.argv[1:]
    parts, any_blocking = [], False
    for f in files:
        if not f.strip():
            continue
        md, blocking = render(f)
        parts.append(md)
        any_blocking = any_blocking or blocking
    report = "\n\n---\n\n".join(parts) or "Sin archivos de reglas en este cambio."
    print(report)
    with open("report.md", "w") as out:
        out.write(report)
    sys.exit(1 if any_blocking else 0)


if __name__ == "__main__":
    main()
