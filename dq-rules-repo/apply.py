#!/usr/bin/env python3
"""Aplicador determinista de reglas de calidad (rules-as-code -> Dataplex AutoDQ).

Único componente con permiso de escritura sobre Dataplex. Lo ejecuta el CI
(GitHub Actions / GitLab CI / Bitbucket Pipelines) con la service account de
gobierno — idealmente vía Workload Identity Federation, sin llaves.

Modos:
  python apply.py validate <archivos...>   # en PR: valida sin escribir
  python apply.py apply    <archivos...>   # en merge a main: crea/actualiza

El "archivo cambiado" lo determina cada CI (git diff) y se pasa como args.
Sin args, procesa todos los YAML bajo rules/.
"""

import glob
import re
import sys

import yaml
from google.cloud import dataplex_v1

VALID_TYPES = {
    "non_null",
    "uniqueness",
    "set",
    "range",
    "regex",
    "row_condition",
    "sql_assertion",
}


def load(path: str) -> dict:
    with open(path) as f:
        spec = yaml.safe_load(f)
    assert spec.get("apiVersion") == "dq.rules/v1", f"{path}: apiVersion inválida"
    assert re.fullmatch(r"[\w-]+\.[\w]+\.[\w$]+", spec["table"]), (
        f"{path}: table debe ser project.dataset.table"
    )
    for i, r in enumerate(spec.get("rules", [])):
        assert r.get("type") in VALID_TYPES, f"{path}: regla[{i}] type inválido"
        assert 0 < float(r.get("threshold", 1.0)) <= 1.0, (
            f"{path}: regla[{i}] threshold fuera de rango"
        )
    return spec


def to_rule(r: dict) -> dataplex_v1.DataQualityRule:
    kw = {
        "column": r.get("column", ""),
        "dimension": r.get("dimension", "VALIDITY"),
        "threshold": float(r.get("threshold", 1.0)),
        "description": r.get("description", ""),
        "name": re.sub(r"[^a-z0-9-]", "-", r.get("name", r["type"]).lower())[:63],
    }
    t = r["type"]
    R = dataplex_v1.DataQualityRule
    if t == "non_null":
        kw["non_null_expectation"] = R.NonNullExpectation()
    elif t == "uniqueness":
        kw["uniqueness_expectation"] = R.UniquenessExpectation()
    elif t == "set":
        kw["set_expectation"] = R.SetExpectation(values=[str(v) for v in r["values"]])
    elif t == "range":
        kw["range_expectation"] = R.RangeExpectation(
            min_value=str(r.get("min", "")), max_value=str(r.get("max", ""))
        )
    elif t == "regex":
        kw["regex_expectation"] = R.RegexExpectation(regex=r["regex"])
    elif t == "row_condition":
        kw["row_condition_expectation"] = R.RowConditionExpectation(
            sql_expression=r["sql_expression"]
        )
    elif t == "sql_assertion":
        kw.pop("column")
        kw["sql_assertion"] = R.SqlAssertion(sql_statement=r["sql_statement"])
    return R(**kw)


def apply_spec(spec: dict) -> str:
    client = dataplex_v1.DataScanServiceClient()
    p, d, t = spec["table"].split(".")
    parent = f"projects/{p}/locations/{spec.get('location', 'us-central1')}"
    scan_id = f"dq-{re.sub(r'[^a-z0-9]', '-', (d + '-' + t).lower())}"[:63]

    cron = spec.get("schedule_cron") or ""
    trigger = (
        dataplex_v1.Trigger(schedule=dataplex_v1.Trigger.Schedule(cron=cron))
        if cron
        else dataplex_v1.Trigger(on_demand=dataplex_v1.Trigger.OnDemand())
    )
    scan = dataplex_v1.DataScan(
        data=dataplex_v1.DataSource(
            resource=f"//bigquery.googleapis.com/projects/{p}/datasets/{d}/tables/{t}"
        ),
        data_quality_spec=dataplex_v1.DataQualitySpec(
            rules=[to_rule(r) for r in spec["rules"]]
        ),
        execution_spec=dataplex_v1.DataScan.ExecutionSpec(trigger=trigger),
        labels={"origin": "dq-rules-repo", "managed_by": "ci"},
        description=(
            f"Rules-as-code. Propuesto por "
            f"{spec.get('metadata', {}).get('proposed_by', 'n/a')}; "
            f"aprobado vía PR."
        ),
    )
    try:
        client.create_data_scan(
            parent=parent, data_scan=scan, data_scan_id=scan_id
        ).result(timeout=300)
        action = "created"
    except Exception as e:
        if "already exists" not in str(e).lower():
            raise
        scan.name = f"{parent}/dataScans/{scan_id}"
        client.update_data_scan(data_scan=scan).result(timeout=300)
        action = "updated"
    client.run_data_scan(name=f"{parent}/dataScans/{scan_id}")
    return f"{action}: {scan_id}"


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "validate"
    files = sys.argv[2:] or glob.glob("rules/**/*.yaml", recursive=True)
    failed = False
    for f in files:
        try:
            spec = load(f)
            if mode == "apply":
                print(f"[apply] {f} -> {apply_spec(spec)}")
            else:
                print(f"[ok] {f}: {len(spec['rules'])} regla(s) válidas")
        except Exception as e:
            failed = True
            print(f"[error] {f}: {e}", file=sys.stderr)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
