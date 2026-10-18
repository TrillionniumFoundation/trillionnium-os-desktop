set -euo pipefail
mkdir -p "$RUNNER_TEMP/a10"
python3 -B -m unittest discover -s tests/ui \
  -p 'test_original_hepta_shell.py' -v 2>&1 | tee "$RUNNER_TEMP/a10/original-shell-contracts.log"
