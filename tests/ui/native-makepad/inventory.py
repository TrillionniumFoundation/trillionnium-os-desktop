#!/usr/bin/env python3
"""Read installed native UI prerequisites without connecting to any user bus."""
import importlib.util
import json
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET


def executable(*paths):
    return next((str(Path(path)) for path in paths if Path(path).is_file()), None)


def inventory():
    commands = {name: shutil.which(name) for name in (
        "Xvfb", "xauth", "xdotool", "xdpyinfo", "xprop", "setxkbmap",
        "dbus-daemon", "gdbus", "ibus-daemon", "ibus", "glib-compile-schemas",
        "orca", "speech-dispatcher",
    )}
    helpers = {
        "a11y_bus": executable("/usr/libexec/at-spi-bus-launcher", "/usr/lib/at-spi2-core/at-spi-bus-launcher"),
        "ibus_panel": executable("/usr/libexec/ibus-ui-gtk3", "/usr/lib/ibus/ibus-ui-gtk3"),
        "ibus_memconf": executable("/usr/libexec/ibus-memconf", "/usr/lib/ibus/ibus-memconf"),
    }
    # Direct GI Atspi bindings are part of the required installed namespace;
    # the optional pyatspi compatibility wrapper is not a prerequisite.
    modules = {"gi": importlib.util.find_spec("gi") is not None}
    namespaces = {}
    if modules["gi"]:
        import gi
        for name, version in (("Gtk", "3.0"), ("Atspi", "2.0")):
            try:
                gi.require_version(name, version)
                namespaces[name] = version
            except Exception as error:
                namespaces[name] = {"error": str(error)}
    components = []
    for path in sorted(Path("/usr/share/ibus/component").glob("*.xml")):
        try:
            root = ET.parse(path).getroot()
            engine_list = root.find("engines")
            components.append({"file": str(path), "name": root.findtext("name"),
                               "exec": root.findtext("exec"),
                               "engines": [node.text for node in root.findall(".//engine/name")],
                               "dynamic_engines_exec": None if engine_list is None else engine_list.get("exec")})
        except Exception as error:
            components.append({"file": str(path), "error": str(error)})
    packages = None
    if shutil.which("dpkg-query"):
        result = subprocess.run(["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\n",
                                 "xvfb", "ibus", "ibus-libpinyin", "python3-gi",
                                 "at-spi2-core", "orca"], capture_output=True, text=True, timeout=8)
        packages = {"stdout": result.stdout, "stderr": result.stderr, "exit_code": result.returncode}
    return {"schema": "trill.native-ui-inventory.v1", "python": sys.version,
            "platform": platform.platform(), "commands": commands, "helpers": helpers,
            "python_modules": modules, "gi_namespaces": namespaces,
            "ibus_components": components, "packages": packages,
            "connected_to_user_bus": False, "installed_or_changed_packages": False}


if __name__ == "__main__":
    print(json.dumps(inventory(), ensure_ascii=False, indent=2))
