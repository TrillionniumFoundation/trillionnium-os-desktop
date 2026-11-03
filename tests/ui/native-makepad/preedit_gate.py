"""Additional exact-source and XIM negotiation gates for the preedit product.

These checks supplement the existing real IBus and AT-SPI workflow. A log line
alone cannot qualify preedit, committed text, positioning, or Root authority.
"""
import hashlib
import json
from pathlib import Path
import re


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def verify_resources(resources, build, *, packaged_binary=False, atomic_editable_text=False):
    source_path = resources / "NATIVE-SDK-SOURCE.json"
    source = json.loads(source_path.read_bytes()) if source_path.is_file() else None
    selected = (build or {}).get("profile", {}).get("sdk_profile") == "preedit-callbacks"
    bundled = source is not None and source.get("sdk_profile") == "preedit-callbacks"
    if not selected and not bundled:
        return None
    require(selected and bundled, "Preedit qualification requires the matching explicit product build receipt and SDK bundle")
    require(packaged_binary and atomic_editable_text,
            "Preedit product acceptance requires --atomic-editable-text and --packaged-binary")
    require(build.get("sdk_source_profile") == source, "Resource SDK source differs from the exact build")
    require(build["profile"].get("required_runtime_gate")
            == "same-packaged-ELF-real-IBus-AT-SPI-callback-XID-and-owned-cleanup",
            "Unknown preedit runtime acceptance contract")
    expected = build.get("resources", {})
    require(len(expected) == 61, "The exact preedit resource/notice inventory is required")
    actual = set()
    for path in resources.rglob("*"):
        require(not path.is_symlink(), "Preedit resource evidence must not contain symlinks")
        if path.is_file():
            relative = path.relative_to(resources).as_posix()
            require(relative in expected and digest(path) == expected[relative],
                    "Preedit resource differs from the compiled product: " + relative)
            actual.add(relative)
    require(actual == set(expected), "Preedit resource inventory differs from the compiled product")
    return {"name": "preedit-callbacks", "patched_tree": source["patched_tree"],
            "source_profile_sha256": digest(source_path)}


def verify_negotiation(stderr, xid):
    lines = re.findall(r"^makepad-x11-ime profile=preedit-callbacks-v1 "
                       r"style=(callback|position|nothing|unavailable) window=(\d+)$",
                       Path(stderr).read_text(errors="replace"), re.MULTILINE)
    styles = [style for style, window in lines if int(window) == int(str(xid), 0)]
    require(styles and all(style == "callback" for style in styles),
            "Actual preedit editor did not exclusively negotiate callback XIM")
    return {"xid": int(str(xid), 0), "styles": styles,
            "sdk_stderr_sha256": digest(stderr), "real_ibus_checks_required": True}
