#!/usr/bin/env python3
"""D0A-01 exact-pin qualifier with semantic official-example validation.

The compile work remains in qualify_servo_exact_pin.py. This entry point
replaces only its brittle variable-name-sensitive source sentinel with checks
for the same public embedder flow at Servo's immutable pin.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import qualify_servo_exact_pin as qualifier


def require(text: str, pattern: str, label: str) -> None:
    if re.search(pattern, text, flags=re.MULTILINE | re.DOTALL) is None:
        raise RuntimeError(f"required Servo official-example flow missing: {label}")


def validate_source_surface(
    servo_root: Path,
    requirements: dict[str, Any],
) -> dict[str, list[str]]:
    webview = (servo_root / "components/servo/webview.rs").read_text(encoding="utf-8")
    delegate = (servo_root / "components/servo/webview_delegate.rs").read_text(
        encoding="utf-8"
    )
    lib = (servo_root / "components/servo/lib.rs").read_text(encoding="utf-8")
    minimal = (servo_root / "components/servo/examples/winit_minimal.rs").read_text(
        encoding="utf-8"
    )

    explicit_exports = {
        "Servo",
        "ServoBuilder",
        "ServoDelegate",
        "WebView",
        "WebViewBuilder",
        "WebViewDelegate",
        "RenderingContext",
        "WindowRenderingContext",
        "CompositionEvent",
        "ClipboardDelegate",
        "CreateNewWebViewRequest",
        "NavigationRequest",
        "InputMethodControl",
        "EmbedderControl",
        "WebResourceLoad",
    }
    wildcard_exports = {"EventLoopWaker", "InputEvent"}
    required_exports = set(requirements["required_public_exports"])
    if required_exports != explicit_exports | wildcard_exports:
        raise RuntimeError("Servo public export requirement classification is stale")
    for export in sorted(explicit_exports):
        if export not in lib:
            raise RuntimeError(f"Servo public export source does not mention {export}")
    require(
        lib,
        r"pub\s+use\s+embedder_traits::\{\s*submit_resource_reader\s*,\s*\*\s*\}\s*;",
        "embedder_traits wildcard public re-export",
    )

    for method in requirements["required_webview_methods"]:
        qualifier.require_regex(
            webview,
            rf"\bpub\s+fn\s+{re.escape(method)}\b",
            f"WebView::{method}",
        )

    for callback in requirements["required_delegate_callbacks"]:
        qualifier.require_regex(
            delegate,
            rf"\bfn\s+{re.escape(callback)}\b",
            f"WebViewDelegate::{callback}",
        )

    official_flow = {
        "ServoBuilder::default": r"ServoBuilder::default\s*\(\s*\)",
        "EventLoopWaker": r"\.event_loop_waker\s*\(\s*Box::new\s*\(",
        "WebViewBuilder::new": r"WebViewBuilder::new\s*\(\s*&[^,]+,",
        "Servo::spin_event_loop": r"\.spin_event_loop\s*\(\s*\)",
        "WebView::notify_input_event": r"\.notify_input_event\s*\(",
        "WebView::paint": r"\.paint\s*\(\s*\)",
        "RenderingContext::present": r"\.present\s*\(\s*\)",
    }
    for label, pattern in official_flow.items():
        require(minimal, pattern, label)

    return {
        "public_exports": sorted(required_exports),
        "webview_methods": list(requirements["required_webview_methods"]),
        "delegate_callbacks": list(requirements["required_delegate_callbacks"]),
        "official_minimal_flow": list(official_flow),
    }


def main() -> int:
    qualifier.validate_source_surface = validate_source_surface
    return qualifier.main()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - one fail-closed CLI path
        print(f"Servo qualification failed: {error}", file=sys.stderr)
        raise
