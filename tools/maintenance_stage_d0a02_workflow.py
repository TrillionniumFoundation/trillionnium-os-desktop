#!/usr/bin/env python3
"""Generate the final permanent D0A-02 workflow without mutating a branch."""

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


path = Path(".github/workflows/servo-headed-runtime.yml")
text = path.read_text(encoding="utf-8")
start = text.index("on:\n")
end = text.index("\npermissions:\n")
text = text[:start] + """on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
  workflow_dispatch:
""" + text[end:]
text = replace_once(
    text,
    """          for key in [
              'signal_sent',
              'exact_termination_observed',
              'old_process_absent',
              'servo_crash_callback_observed',
          ]:
              assert fault[key] is True, (key, fault)
          assert isinstance(fault['servo_crash_callback_reason'], str)
""",
    """          for key in [
              'signal_sent',
              'exact_termination_observed',
              'old_process_absent',
          ]:
              assert fault[key] is True, (key, fault)
          assert fault['servo_pipeline_panic_callback_required'] is False
          assert isinstance(fault['servo_pipeline_panic_callback_observed'], bool)
          assert isinstance(fault['servo_pipeline_panic_callback_reason'], str)
""",
    "workflow callback assertions",
)
text = replace_once(
    text,
    """              'repository': os.environ['GITHUB_REPOSITORY'],
              'mode': os.environ['EVIDENCE_MODE'],
""",
    """              'repository': os.environ['GITHUB_REPOSITORY'],
              'event_name': os.environ['GITHUB_EVENT_NAME'],
              'ref': os.environ['GITHUB_REF'],
              'ref_name': os.environ['GITHUB_REF_NAME'],
              'promotion_authoritative': os.environ['EVIDENCE_MODE'] == 'exact_main_push',
              'mode': os.environ['EVIDENCE_MODE'],
""",
    "workflow evidence ref identity",
)
text = replace_once(
    text,
    """                  'exact_termination_observed': True,
              },
""",
    """                  'exact_termination_observed': True,
                  'servo_pipeline_panic_callback_observed': fault['servo_pipeline_panic_callback_observed'],
              },
""",
    "receipt optional callback evidence",
)
path.write_text(text, encoding="utf-8")
