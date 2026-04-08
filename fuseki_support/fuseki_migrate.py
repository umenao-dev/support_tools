import argparse
import json
import os
import re
from typing import Dict, List, Optional, Tuple

import requests


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def normalize_dataset_name(name: str) -> str:
    return name.lstrip("/")


def datasets_from_json(data: dict) -> List[dict]:
    items = []
    if isinstance(data, dict):
        items = data.get("datasets") or data.get("dataset") or data.get("Dataset") or []
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def get_admin_datasets(base_url: str, timeout: int) -> List[dict]:
    url = base_url.rstrip("/") + "/$/datasets"
    resp = requests.get(url, headers={"Accept": "application/json"}, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    datasets = datasets_from_json(data)
    if not datasets:
        raise RuntimeError("No datasets found in /$/datasets response.")
    return datasets


def extract_dataset_name(item: dict) -> Optional[str]:
    name = (
        item.get("ds.name")
        or item.get("name")
        or item.get("dsName")
        or item.get("dataset")
        or item.get("dbName")
    )
    if not isinstance(name, str):
        return None
    return normalize_dataset_name(name)


def get_dataset_detail(base_url: str, dataset: str, timeout: int) -> Tuple[str, str]:
    url = base_url.rstrip("/") + "/$/datasets/" + dataset
    accepted = [
        "application/json",
        "text/turtle",
        "application/ld+json",
        "text/plain",
    ]
    for accept in accepted:
        resp = requests.get(url, headers={"Accept": accept}, timeout=timeout)
        if resp.status_code == 200:
            ctype = resp.headers.get("Content-Type", "")
            return ctype, resp.text
    raise RuntimeError(f"Failed to fetch dataset detail: {url}")


def infer_db_type(admin_item: dict, detail_text: str) -> Optional[str]:
    candidate_keys = ["dbType", "db.type", "ds.type", "type", "storage"]
    for key in candidate_keys:
        value = admin_item.get(key)
        if isinstance(value, str):
            low = value.lower()
            if low in {"mem", "tdb2", "tdb"}:
                return low

    low_text = detail_text.lower()
    if "tdb2:" in low_text or "datasettdb2" in low_text:
        return "tdb2"
    if re.search(r"\btdb:", low_text) or "datasettdb" in low_text:
        return "tdb"
    if "datasetmem" in low_text or "jena:textdataset" in low_text:
        return "mem"
    return None


def sparql_query(endpoint: str, query: str, timeout: int) -> dict:
    resp = requests.post(
        endpoint,
        data={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def list_graphs(sparql_endpoint: str, timeout: int) -> Tuple[bool, List[str]]:
    ask_default = "ASK { ?s ?p ?o }"
    ask_data = sparql_query(sparql_endpoint, ask_default, timeout)
    default_has_data = bool(ask_data.get("boolean"))

    query = "SELECT DISTINCT ?g WHERE { GRAPH ?g { ?s ?p ?o } } ORDER BY ?g"
    data = sparql_query(sparql_endpoint, query, timeout)
    graphs = []
    for binding in data.get("results", {}).get("bindings", []):
        g = binding.get("g", {})
        value = g.get("value")
        if isinstance(value, str):
            graphs.append(value)
    return default_has_data, graphs


def write_json(path: str, obj: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def download_graph(data_endpoint: str, graph_uri: Optional[str], out_path: str, timeout: int) -> None:
    params = {"default": ""} if graph_uri is None else {"graph": graph_uri}
    resp = requests.get(
        data_endpoint,
        params=params,
        headers={"Accept": "application/n-triples"},
        timeout=timeout,
        stream=True,
    )
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 256):
            if chunk:
                f.write(chunk)


def upload_graph(data_endpoint: str, graph_uri: Optional[str], file_path: str, timeout: int) -> None:
    params = {"default": ""} if graph_uri is None else {"graph": graph_uri}
    with open(file_path, "rb") as f:
        resp = requests.put(
            data_endpoint,
            params=params,
            data=f,
            headers={"Content-Type": "application/n-triples"},
            timeout=timeout,
        )
    resp.raise_for_status()


def clear_graph(data_endpoint: str, graph_uri: Optional[str], timeout: int) -> None:
    params = {"default": ""} if graph_uri is None else {"graph": graph_uri}
    resp = requests.delete(data_endpoint, params=params, timeout=timeout)
    resp.raise_for_status()


def create_dataset(base_url: str, dataset: str, db_type: Optional[str], timeout: int) -> None:
    url = base_url.rstrip("/") + "/$/datasets"
    payload = {"dbName": dataset}
    if db_type:
        payload["dbType"] = db_type
    resp = requests.post(url, data=payload, timeout=timeout)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Failed to create dataset '{dataset}': {resp.status_code} {resp.text}")


def delete_dataset(base_url: str, dataset: str, timeout: int) -> None:
    url = base_url.rstrip("/") + "/$/datasets/" + dataset
    resp = requests.delete(url, timeout=timeout)
    if resp.status_code not in (200, 202, 204):
        raise RuntimeError(f"Failed to delete dataset '{dataset}': {resp.status_code} {resp.text}")


def resolve_selected_datasets(admin_items: List[dict], selected: List[str]) -> List[Tuple[str, dict]]:
    by_name: Dict[str, dict] = {}
    for item in admin_items:
        name = extract_dataset_name(item)
        if name:
            by_name[name] = item
    if selected:
        resolved = []
        for name in selected:
            n = normalize_dataset_name(name)
            if n not in by_name:
                raise RuntimeError(f"Dataset not found: {n}")
            resolved.append((n, by_name[n]))
        return resolved
    return sorted(by_name.items(), key=lambda x: x[0])


def backup_command(args: argparse.Namespace) -> int:
    ensure_dir(args.out_dir)
    admin_items = get_admin_datasets(args.base_url, args.timeout)
    selected = []
    if args.datasets:
        selected.extend([d.strip() for d in args.datasets.split(",") if d.strip()])
    if args.dataset:
        selected.extend([d for d in args.dataset if d])
    datasets = resolve_selected_datasets(admin_items, selected)

    manifest = {
        "base_url": args.base_url,
        "datasets": [],
    }

    for dataset, admin_item in datasets:
        print(f"Backup dataset: {dataset}")
        ds_dir = os.path.join(args.out_dir, dataset)
        graphs_dir = os.path.join(ds_dir, "graphs")
        named_dir = os.path.join(graphs_dir, "named")
        ensure_dir(named_dir)

        detail_content_type = ""
        detail_text = ""
        try:
            detail_content_type, detail_text = get_dataset_detail(args.base_url, dataset, args.timeout)
        except Exception as exc:
            print(f"  Warn: dataset detail fetch failed: {exc}")

        db_type = infer_db_type(admin_item, detail_text)
        sparql_endpoint = args.base_url.rstrip("/") + "/" + dataset + "/sparql"
        data_endpoint = args.base_url.rstrip("/") + "/" + dataset + "/data"

        default_has_data, named_graphs = list_graphs(sparql_endpoint, args.timeout)
        graph_manifest = {
            "default_graph_file": None,
            "named_graphs": [],
        }

        if default_has_data:
            default_path = os.path.join(graphs_dir, "default.nt")
            print("  Download default graph")
            download_graph(data_endpoint, None, default_path, args.timeout)
            graph_manifest["default_graph_file"] = "graphs/default.nt"

        for idx, graph_uri in enumerate(named_graphs, start=1):
            file_name = f"{idx:06d}.nt"
            rel_path = os.path.join("graphs", "named", file_name).replace("\\", "/")
            abs_path = os.path.join(named_dir, file_name)
            print(f"  Download named graph: {graph_uri}")
            download_graph(data_endpoint, graph_uri, abs_path, args.timeout)
            graph_manifest["named_graphs"].append(
                {
                    "graph_uri": graph_uri,
                    "file": rel_path,
                }
            )

        write_json(os.path.join(ds_dir, "admin_item.json"), admin_item)
        write_json(
            os.path.join(ds_dir, "metadata.json"),
            {
                "dataset": dataset,
                "db_type_inferred": db_type,
                "detail_content_type": detail_content_type,
                "named_graph_count": len(named_graphs),
                "has_default_graph": default_has_data,
            },
        )
        write_json(os.path.join(ds_dir, "graphs_manifest.json"), graph_manifest)
        if detail_text:
            ext = "txt"
            if "json" in detail_content_type.lower():
                ext = "json"
            elif "turtle" in detail_content_type.lower():
                ext = "ttl"
            with open(os.path.join(ds_dir, f"dataset_detail.{ext}"), "w", encoding="utf-8") as f:
                f.write(detail_text)

        manifest["datasets"].append(
            {
                "name": dataset,
                "path": dataset,
                "db_type_inferred": db_type,
            }
        )

    write_json(os.path.join(args.out_dir, "manifest.json"), manifest)
    print(f"Backup completed: {args.out_dir}")
    return 0


def restore_command(args: argparse.Namespace) -> int:
    manifest_path = os.path.join(args.backup_dir, "manifest.json")
    manifest = read_json(manifest_path)
    datasets = manifest.get("datasets", [])
    if not datasets:
        raise RuntimeError(f"No datasets in manifest: {manifest_path}")

    existing_items = get_admin_datasets(args.base_url, args.timeout)
    existing_names = set()
    for item in existing_items:
        name = extract_dataset_name(item)
        if name:
            existing_names.add(name)

    for ds in datasets:
        dataset = normalize_dataset_name(ds["name"])
        ds_dir = os.path.join(args.backup_dir, ds.get("path", dataset))
        metadata = read_json(os.path.join(ds_dir, "metadata.json"))
        graphs_manifest = read_json(os.path.join(ds_dir, "graphs_manifest.json"))
        db_type = metadata.get("db_type_inferred")

        print(f"Restore dataset: {dataset}")
        exists = dataset in existing_names
        if exists and args.if_exists == "error":
            raise RuntimeError(f"Dataset already exists: {dataset}")
        if exists and args.if_exists == "replace":
            print("  Delete existing dataset")
            delete_dataset(args.base_url, dataset, args.timeout)
            existing_names.remove(dataset)
            exists = False
        if (not exists) and args.create_missing:
            print(f"  Create dataset (dbType={db_type or 'auto'})")
            create_dataset(args.base_url, dataset, db_type, args.timeout)
            existing_names.add(dataset)
            exists = True
        if not exists:
            print("  Skip: dataset does not exist and --create-missing is false")
            continue

        data_endpoint = args.base_url.rstrip("/") + "/" + dataset + "/data"
        if args.clear_before_load:
            if graphs_manifest.get("default_graph_file"):
                print("  Clear default graph")
                clear_graph(data_endpoint, None, args.timeout)
            for graph in graphs_manifest.get("named_graphs", []):
                graph_uri = graph["graph_uri"]
                print(f"  Clear named graph: {graph_uri}")
                clear_graph(data_endpoint, graph_uri, args.timeout)

        default_file = graphs_manifest.get("default_graph_file")
        if default_file:
            default_path = os.path.join(ds_dir, default_file)
            print("  Upload default graph")
            upload_graph(data_endpoint, None, default_path, args.timeout)

        for graph in graphs_manifest.get("named_graphs", []):
            graph_uri = graph["graph_uri"]
            file_path = os.path.join(ds_dir, graph["file"])
            print(f"  Upload named graph: {graph_uri}")
            upload_graph(data_endpoint, graph_uri, file_path, args.timeout)

    print("Restore completed.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backup/restore Fuseki datasets with graph data and dataset metadata."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    backup = sub.add_parser("backup", help="Backup datasets from Fuseki")
    backup.add_argument("--base-url", default="http://127.0.0.1:3030", help="Fuseki base URL")
    backup.add_argument("--out-dir", default="backup", help="Backup output directory")
    backup.add_argument("--datasets", help="Comma-separated dataset names")
    backup.add_argument("--dataset", action="append", help="Dataset name (repeatable)")
    backup.add_argument("--timeout", type=int, default=120, help="HTTP timeout (s)")
    backup.set_defaults(func=backup_command)

    restore = sub.add_parser("restore", help="Restore datasets into Fuseki")
    restore.add_argument("--base-url", default="http://127.0.0.1:3030", help="Fuseki base URL")
    restore.add_argument("--backup-dir", required=True, help="Backup directory")
    restore.add_argument("--timeout", type=int, default=120, help="HTTP timeout (s)")
    restore.add_argument(
        "--if-exists",
        choices=["skip", "error", "replace"],
        default="skip",
        help="Behavior when dataset already exists",
    )
    restore.add_argument(
        "--create-missing",
        action="store_true",
        default=True,
        help="Create dataset when missing (default: true)",
    )
    restore.add_argument(
        "--no-create-missing",
        action="store_false",
        dest="create_missing",
        help="Do not create missing datasets",
    )
    restore.add_argument(
        "--clear-before-load",
        action="store_true",
        default=True,
        help="Clear graphs before upload (default: true)",
    )
    restore.add_argument(
        "--no-clear-before-load",
        action="store_false",
        dest="clear_before_load",
        help="Do not clear graphs before upload",
    )
    restore.set_defaults(func=restore_command)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
