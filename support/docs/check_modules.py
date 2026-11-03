#!/usr/bin/env python3
"""Check live module documentation coverage, targets and Markdown heading anchors.

This is a static working-tree check. It neither runs module commands nor grants
runtime qualification. The archived immutable kernel inventory stays untouched.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tomllib
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = "docs/modules/catalogue.json"
HANDBOOK_LABELS = (
    "**职责与接口。**", "**状态、所有权与失败边界。**",
    "**开发与回归。**", "**实际覆盖与待验证。**",
)


def prose(text):
    """Ignore fenced examples when resolving real documentation links/headings."""
    lines, fence = [], None
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if match:
            marker = match[1]
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
            continue
        if fence is None:
            lines.append(line)
    return "\n".join(lines)


def heading_anchors(text):
    anchors, used = set(), {}
    for line in prose(text).splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        heading = re.sub(r"<[^>]+>", "", match[1])
        heading = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", heading)
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        count = used.get(slug, 0)
        used[slug] = count + 1
        anchors.add(slug + ("-" + str(count) if count else ""))
    anchors.update(re.findall(r"<(?:a|span)\b[^>]*\bid=[\"']([^\"']+)[\"']", prose(text)))
    return anchors


def markdown_links(text):
    text = prose(text)
    # Repository contracts use ordinary inline and reference destinations.
    # Angle destinations allow spaces; optional quoted titles are excluded.
    pattern = r"\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+[\"'][^\n]*?[\"'])?\s*\)"
    found = [match[1] or match[2] for match in re.finditer(pattern, text)]
    found.extend(match[1] or match[2] for match in re.finditer(
        r"^\s{0,3}\[[^]]+\]:\s*(?:<([^>]+)>|(\S+))", text, re.MULTILINE))
    return found


def local_target(root, origin, reference):
    parsed = urlsplit(reference)
    if parsed.scheme or parsed.netloc:
        return None
    raw = unquote(parsed.path)
    # Documentation uses repository-relative paths in the catalogue, and paths
    # relative to the containing file in actual Markdown.
    target = (root / origin).parent / raw if raw else root / origin
    target = target.resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("target escapes repository: " + reference)
    return target, unquote(parsed.fragment)


def check_reference(root, origin, reference):
    resolved = local_target(root, origin, reference)
    if resolved is None:
        return None
    target, fragment = resolved
    if not target.exists():
        raise ValueError(f"{origin}: missing target {reference}")
    if fragment and target.suffix.lower() == ".md":
        if fragment not in heading_anchors(target.read_text()):
            raise ValueError(f"{origin}: missing heading anchor {reference}")
    return target


def tracked_manifests(root):
    output = subprocess.check_output([
        "git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard",
    ]).decode()
    return sorted({path for path in output.split("\0") if path.endswith("/Cargo.toml")
                   and not path.startswith(("kernel/", "results/"))
                   and "/evidence/" not in path and "/target/" not in path})


def check_contract(root, record, label, require_entry=False):
    errors, documents = [], set()
    sources = record.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append(label + ": missing actual source entry")
    else:
        for source in sources:
            if not isinstance(source, str):
                errors.append(f"{label}: missing source {source!r}")
                continue
            target = (root / source).resolve()
            if not target.is_relative_to(root.resolve()) or not target.is_file():
                errors.append(f"{label}: missing source {source!r}")
    for field in ("owner", "failure_recovery", "current_scope"):
        value = record.get(field)
        if not isinstance(value, str) or len(value.strip()) < 40:
            errors.append(f"{label}: missing substantive {field}")
    references = [record.get("entry", "")] if require_entry else []
    for field in ("technical", "development"):
        values = record.get(field)
        if not isinstance(values, list) or not values:
            errors.append(f"{label}: missing {field} document")
        else:
            references.extend(values)
    for reference in references:
        if not isinstance(reference, str) or not reference:
            errors.append(f"{label}: empty document reference")
            continue
        try:
            # A synthetic root-level Markdown origin interprets catalogue
            # references relative to the repository root.
            target = check_reference(root, "README.md", reference)
            if target is None or target.suffix.lower() != ".md":
                raise ValueError("module contract must be local Markdown: " + reference)
            if len(prose(target.read_text()).strip()) < 250:
                raise ValueError("module contract is too short: " + reference)
            documents.add(target.relative_to(root).as_posix())
        except ValueError as error:
            errors.append(str(error))
    return errors, documents


def check_catalogue(root, catalogue, manifests):
    errors, documents, covered = [], set(), set()
    if catalogue.get("schema_version") != 1:
        errors.append("unsupported module catalogue schema")
    for record in catalogue.get("packages", []):
        manifest = record.get("manifest", "")
        if manifest in covered:
            errors.append("duplicate module manifest: " + manifest)
        covered.add(manifest)
        if not manifest or not (root / manifest).is_file():
            errors.append("missing module manifest: " + manifest)
            continue
        observed = tomllib.loads((root / manifest).read_text())
        name = observed.get("package", {}).get("name")
        if name != record.get("package"):
            errors.append(f"{manifest}: package name differs: {name!r}")
        if name is None and "workspace" not in observed:
            errors.append(manifest + ": not a package or virtual workspace")
        record_errors, record_documents = check_contract(root, record, manifest, require_entry=True)
        errors.extend(record_errors)
        documents.update(record_documents)
    for path in sorted(set(manifests) - covered):
        errors.append("unmapped first-party Cargo manifest: " + path)
    for path in sorted(covered - set(manifests)):
        errors.append("catalogue manifest is outside current discovery: " + path)
    return errors, documents


def check_domains(root, catalogue):
    errors, documents, identities = [], set(), set()
    for record in catalogue.get("domains", []):
        identity = record.get("id", "")
        if not re.fullmatch(r"A\d\d", identity) or identity in identities:
            errors.append("invalid or duplicate development domain: " + identity)
        identities.add(identity)
        record_errors, record_documents = check_contract(root, record, identity)
        errors.extend(record_errors)
        documents.update(record_documents)
    if not identities:
        errors.append("missing cross-module development domains")
    return errors, documents, identities


def check_kernel(root, catalogue):
    errors, documents, members_seen, manifests = [], set(), set(), set()
    workspace_path = catalogue["kernel_workspace"]
    workspace = tomllib.loads((root / workspace_path).read_text())["workspace"]
    members = workspace["members"]
    if len(members) != len(set(members)):
        errors.append("kernel workspace repeats explicit members")
    books = {}
    for path in catalogue["kernel_handbooks"]:
        books[path] = (root / path).read_text()
        documents.add(path)
    for member in members:
        manifest = (root / workspace_path).parent / member / "Cargo.toml"
        manifests.add(manifest.relative_to(root).as_posix())
        package = tomllib.loads(manifest.read_text())["package"]["name"]
        sections = []
        for path, text in books.items():
            for match in re.finditer(r"^## " + re.escape(package) + r"\s*$\n(.*?)(?=^## |\Z)",
                                     text, re.MULTILINE | re.DOTALL):
                sections.append((path, match[1]))
        if len(sections) != 1:
            errors.append(f"{package}: expected exactly one kernel handbook section, got {len(sections)}")
            continue
        path, section = sections[0]
        for label in HANDBOOK_LABELS:
            if label not in section:
                errors.append(f"{path}#{package}: missing contract {label}")
        relative_manifest = manifest.relative_to(root).as_posix()
        targets = []
        for link in markdown_links(section):
            try:
                resolved = local_target(root, path, link)
                if resolved:
                    targets.append(resolved[0].relative_to(root).as_posix())
            except ValueError as error:
                errors.append(str(error))
        if relative_manifest not in targets:
            errors.append(f"{package}: handbook does not link its actual manifest")
        if not any(target.startswith(str(manifest.parent.relative_to(root)) + "/src/")
                   for target in targets):
            errors.append(f"{package}: handbook does not link its source entry")
        members_seen.add(package)
    return errors, documents, members_seen, manifests


def validate(root):
    catalogue = json.loads((root / CATALOGUE).read_text())
    errors, documents = check_catalogue(root, catalogue, tracked_manifests(root))
    domain_errors, domain_documents, domains = check_domains(root, catalogue)
    errors.extend(domain_errors)
    documents.update(domain_documents)
    kernel_errors, kernel_documents, members, kernel_manifests = check_kernel(root, catalogue)
    errors.extend(kernel_errors)
    documents.update(kernel_documents)
    documents.update({"docs/modules/README.md", "docs/modules/kernel-workspace/README.md"})
    links = 0
    for path in sorted(documents):
        for reference in markdown_links((root / path).read_text()):
            try:
                if check_reference(root, path, reference) is not None:
                    links += 1
            except ValueError as error:
                errors.append(str(error))
    inputs = sorted(documents | {CATALOGUE, catalogue["kernel_workspace"]}
                    | kernel_manifests
                    | {record["manifest"] for record in catalogue["packages"]}
                    | {source for record in catalogue["packages"] + catalogue.get("domains", []) for source in record.get("sources", [])
                       if isinstance(source, str) and (root / source).resolve().is_relative_to(root.resolve())
                       and (root / source).is_file()})
    hashes = {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in inputs}
    digest = hashlib.sha256("".join(path + "\0" + hashes[path] + "\n" for path in inputs).encode()).hexdigest()
    return {
        "schema_version": 1, "ok": not errors, "execution_evidence": False,
        "scope": "live documentation contracts and direct local links; external URLs are not fetched",
        "first_party_cargo_entries": len(catalogue["packages"]),
        "development_domains": len(domains),
        "kernel_members": len(members), "documents": len(documents), "local_links": links,
        "input_digest_sha256": digest, "inputs_sha256": hashes, "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="optional JSON output; does not change source or catalogue")
    args = parser.parse_args()
    try:
        report = validate(ROOT)
    except (KeyError, OSError, ValueError, tomllib.TOMLDecodeError) as error:
        parser.exit(1, "module documentation check failed: " + str(error) + "\n")
    report["source_head"] = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).decode().strip()
    report["working_tree_dirty"] = bool(subprocess.check_output([
        "git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=normal"]))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "inputs_sha256"}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
