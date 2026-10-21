#!/usr/bin/env python3
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import tempfile

result = {"kind": "host_only_AF_UNIX_probe_no_kernel", "utc": datetime.now(timezone.utc).isoformat(),
          "stage": "socket_creation", "passed": False,
          "initial_probe_attempt_note": "The first inline probe raised PermissionError at socket construction outside its bind-only try block; no JSON was produced. This corrected probe records the actual failed stage."}
stream = None
with tempfile.TemporaryDirectory(prefix="a01-next7-unix-") as temporary:
    try:
        stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        result["stage"] = "bind"
        stream.bind(str(Path(temporary) / "probe.sock"))
        result.update(passed=True, stage="complete")
    except OSError as error:
        result.update(error_type=type(error).__name__, errno=error.errno, error=str(error))
    finally:
        if stream is not None:
            stream.close()
Path(__file__).with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
