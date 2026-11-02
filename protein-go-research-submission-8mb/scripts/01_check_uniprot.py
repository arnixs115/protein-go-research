"""Validate at most 10 human reviewed UniProtKB entries; never paginate."""
import csv
import hashlib
import io
import json
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://rest.uniprot.org"
QUERY = "organism_id:9606 AND reviewed:true"
LIMIT = 10
FIELDS = ["accession", "protein_name", "gene_primary", "xref_geneid", "length",
          "go_p", "go_f", "go_c", "go_id", "organism_id", "reviewed"]
GO_ID = re.compile(r"GO:\d{7}")


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def duplicates(values):
    return {key: n for key, n in Counter(values).items() if n > 1}


def validate(payload, tsv, field_definitions):
    entries = payload["results"]
    if not 1 <= len(entries) <= LIMIT:
        raise ValueError(f"Unexpected JSON entry count: {len(entries)}")
    reader = csv.DictReader(io.StringIO(tsv), delimiter="\t")
    columns = reader.fieldnames or []
    rows = list(reader)
    # Use actual response headers in requested order: display-label case can differ.
    if len(columns) != len(FIELDS) or len(set(columns)) != len(columns):
        raise ValueError(f"Unexpected TSV columns: {columns}")
    if [c.casefold() for c in columns] != [field_definitions[f]["label"].casefold() for f in FIELDS]:
        raise ValueError("TSV header order/labels differ from official field definitions")
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError("Malformed TSV row width")
    records = [dict(zip(FIELDS, [row[c] for c in columns])) for row in rows]
    accessions = [entry["primaryAccession"] for entry in entries]
    if duplicates(accessions) or {r["accession"] for r in records} != set(accessions) or len(records) != len(entries):
        raise ValueError("TSV/JSON accession mismatch or duplicate primary accession")
    by_accession = {r["accession"]: r for r in records}
    issues = []
    summaries = []
    evidence_codes, eco_codes = Counter(), Counter()
    gene_to_entries = defaultdict(set)
    for entry in entries:
        acc = entry["primaryAccession"]
        row = by_accession[acc]
        refs = entry.get("uniProtKBCrossReferences", [])
        gos = [ref for ref in refs if ref.get("database") == "GO"]
        gene_ids = [ref["id"] for ref in refs if ref.get("database") == "GeneID"]
        for gene_id in gene_ids:
            gene_to_entries[gene_id].add(acc)
        names = [g["geneName"]["value"] for g in entry.get("genes", []) if "geneName" in g]
        length = entry.get("sequence", {}).get("length")
        item_issues = []
        if not isinstance(length, int) or isinstance(length, bool) or length <= 0:
            item_issues.append("invalid JSON sequence.length")
        if entry.get("organism", {}).get("taxonId") != 9606 or entry.get("entryType") != "UniProtKB reviewed (Swiss-Prot)":
            item_issues.append("selection criteria mismatch")
        if not row["length"].isdigit() or int(row["length"]) != length:
            item_issues.append("TSV/JSON length mismatch")
        if not row["organism_id"].isdigit() or int(row["organism_id"]) != 9606 or row["reviewed"] != "reviewed":
            item_issues.append("TSV selection criteria mismatch")
        if not row["protein_name"].strip():
            item_issues.append("missing protein name")
        missing_values = [f for f in FIELDS if not row[f].strip()]
        categories = {"BP": [], "MF": [], "CC": []}
        missing_go_evidence = []
        go_ids = []
        for ref in gos:
            gid = ref.get("id")
            go_ids.append(gid)
            if not isinstance(gid, str) or not GO_ID.fullmatch(gid):
                item_issues.append(f"invalid GO ID: {gid}")
            props = {p["key"]: p["value"] for p in ref.get("properties", [])}
            category = {"P": "BP", "F": "MF", "C": "CC"}.get(props.get("GoTerm", "").split(":", 1)[0])
            if category:
                categories[category].append(gid)
            else:
                item_issues.append(f"unknown GO category: {gid}")
            evidence = props.get("GoEvidenceType")
            if evidence:
                evidence_codes[evidence] += 1
            else:
                missing_go_evidence.append(gid)
            for ev in ref.get("evidences", []):
                if "evidenceCode" in ev:
                    eco_codes[ev["evidenceCode"]] += 1
        tsv_go = {}
        for field in ("go_id", "go_p", "go_f", "go_c"):
            tokens = [x.strip() for x in row[field].split(";") if x.strip()]
            ids = GO_ID.findall(row[field])
            if field == "go_id":
                valid = all(GO_ID.fullmatch(t) for t in tokens)
            else:
                valid = all(re.fullmatch(r".+ \[GO:\d{7}\]", t) for t in tokens)
            if not valid:
                item_issues.append(f"unexpected GO cell format: {field}")
            tsv_go[field] = {"tokens": len(tokens), "ids": ids, "duplicates": duplicates(ids)}
        if set(tsv_go["go_id"]["ids"]) != set(go_ids):
            item_issues.append("TSV/JSON GO set mismatch")
        for cat, field in (("BP", "go_p"), ("MF", "go_f"), ("CC", "go_c")):
            if set(categories[cat]) != set(tsv_go[field]["ids"]):
                item_issues.append(f"TSV/JSON {cat} set mismatch")
        tsv_gene_ids = [v.strip() for v in row["xref_geneid"].split(";") if v.strip()]
        if set(tsv_gene_ids) != set(gene_ids):
            item_issues.append("TSV/JSON GeneID mismatch")
        if any(not value.isdigit() for value in gene_ids):
            item_issues.append("non-numeric GeneID")
        summary = {"accession": acc, "protein_names_tsv": row["protein_name"],
                   "primary_gene_names": names, "gene_ids": gene_ids, "length_aa": length,
                   "go_unique_count": len(set(go_ids)),
                   "go_unique_by_category": {k: len(set(v)) for k, v in categories.items()},
                   "json_go_duplicate_ids": duplicates(go_ids), "tsv_go": tsv_go,
                   "missing_tsv_values": missing_values, "go_without_GoEvidenceType": missing_go_evidence,
                   "issues": item_issues}
        summaries.append(summary)
        issues.extend(f"{acc}: {issue}" for issue in item_issues)
    first_go = next((ref for e in entries for ref in e.get("uniProtKBCrossReferences", []) if ref.get("database") == "GO"), None)
    return {"passed": not issues, "issues": issues, "entry_count": len(entries),
            "tsv_columns": columns, "field_to_column": dict(zip(FIELDS, columns)),
            "official_field_labels": {f: field_definitions[f]["label"] for f in FIELDS},
            "tsv_cell_python_types": {c: sorted({type(r[c]).__name__ for r in rows}) for c in columns},
            "json_top_level_types": {k: type(v).__name__ for k, v in payload.items()},
            "json_entry_observed_types": {k: sorted({type(e[k]).__name__ for e in entries if k in e}) for k in set().union(*(e.keys() for e in entries))},
            "json_length_types": sorted({type(e.get("sequence", {}).get("length")).__name__ for e in entries}),
            "sample_tsv_GO_cells": {f: records[0][f] for f in ("go_id", "go_p", "go_f", "go_c")},
            "sample_json_GO_reference": first_go, "GoEvidenceType_counts": dict(evidence_codes),
            "GO_ECO_code_counts": dict(eco_codes),
            "shared_gene_ids_in_sample": {g: sorted(a) for g, a in gene_to_entries.items() if len(a) > 1},
            "entries": summaries}


def main():
    run = ROOT / "data" / "raw" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    metadata = {"started_at_utc": datetime.now(timezone.utc).isoformat(),
                "query": QUERY, "max_entries": LIMIT, "include_isoforms": False,
                "pagination_followed": False, "fields": FIELDS, "requests": [],
                "python_version": sys.version, "requests_version": requests.__version__, "status": "running"}
    session = requests.Session()
    session.headers["User-Agent"] = "protein-go-research/0.1 (10-entry API structure validation)"

    def fetch(name, url, params=None):
        record = {"name": name, "requested_at_utc": datetime.now(timezone.utc).isoformat()}
        metadata["requests"].append(record)
        prepared = session.prepare_request(requests.Request("GET", url, params=params))
        record["url"] = prepared.url
        print(f"\nURL: {prepared.url}", flush=True)
        try:
            response = session.send(prepared, timeout=(10, 60))
            record.update({"url": response.url, "http_status": response.status_code,
                           "headers": dict(response.headers), "received_at_utc": datetime.now(timezone.utc).isoformat(),
                           "sha256": hashlib.sha256(response.content).hexdigest(), "raw_file": name})
            (run / name).write_bytes(response.content)
            print(f"HTTP: {response.status_code}; Content-Type: {response.headers.get('Content-Type')}", flush=True)
            for header in ("X-Total-Results", "X-UniProt-Release", "X-UniProt-Release-Date"):
                print(f"{header}: {response.headers.get(header)}", flush=True)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            record["error"] = str(exc)
            raise

    try:
        config = fetch("result-fields.json", BASE + "/configure/uniprotkb/result-fields").json()
        definitions = {f["name"]: f for group in config for f in group["fields"]}
        absent = sorted(set(FIELDS) - definitions.keys())
        if absent:
            raise ValueError(f"Fields absent from official configuration: {absent}")
        spec = fetch("uniprotkb-openapi.json", BASE + "/uniprotkb/api/docs").json()
        schemas = spec["components"]["schemas"]
        for schema, keys in {"SearchResult": ["results"],
                             "UniProtKBEntry": ["primaryAccession", "sequence", "genes", "uniProtKBCrossReferences"],
                             "UniProtKBCrossReference": ["database", "id", "properties", "evidences"],
                             "Property": ["key", "value"], "Evidence": ["evidenceCode", "source", "id"]}.items():
            if not set(keys) <= schemas[schema]["properties"].keys():
                raise ValueError(f"Official schema changed: {schema}")
        params = {"query": QUERY, "format": "json", "size": LIMIT, "includeIsoform": "false"}
        payload = fetch("sample.json", BASE + "/uniprotkb/search", params).json()
        entries = payload["results"]
        if not 1 <= len(entries) <= LIMIT:
            raise ValueError("JSON entry count outside 1..10")
        ids = [entry["primaryAccession"] for entry in entries]
        if any(not re.fullmatch(r"[A-Z0-9]+", acc) for acc in ids):
            raise ValueError("Unexpected primary accession; refuse to construct query")
        # Restrict second format to the same accession set: never collect more entries.
        subset = QUERY + " AND (" + " OR ".join("accession:" + acc for acc in ids) + ")"
        tsv = fetch("sample.tsv", BASE + "/uniprotkb/search", {
            "query": subset, "format": "tsv", "size": LIMIT,
            "includeIsoform": "false", "fields": ",".join(FIELDS)}).text
        report = validate(payload, tsv, definitions)
        releases = {r["headers"].get("X-UniProt-Release", r["headers"].get("x-uniprot-release"))
                    for r in metadata["requests"] if r["name"] in ("sample.json", "sample.tsv")}
        if len(releases) > 1:
            report["issues"].append("Release differs between JSON and TSV")
            report["passed"] = False
        write_json(run / "validation.json", report)
        print("\n" + json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        metadata["status"] = "success" if report["passed"] else "validation_failed"
        return 0 if report["passed"] else 2
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        metadata.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        print(f"ERROR: {metadata['error']}", file=sys.stderr, flush=True)
        return 1
    finally:
        metadata["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(run / "metadata.json", metadata)
        session.close()
        print(f"\nSaved: {run}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
