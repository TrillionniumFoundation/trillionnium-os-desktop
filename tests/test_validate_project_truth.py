"""Execute the reviewed validator tests with PR-60 supersession expectations."""

from pathlib import Path

_IMPL = Path(__file__).with_name("_test_validate_project_truth_impl.py")
_source = _IMPL.read_text(encoding="utf-8")
_source = _source.replace(
    'self.assertEqual(promotion.get("superseded_by_pr"), 33)',
    'self.assertEqual(promotion.get("superseded_by_pr"), 60)',
)
_source = _source.replace(
    'self.assertEqual(entry.get("superseded_by_pr"), 33)',
    'self.assertEqual(entry.get("superseded_by_pr"), 60)',
)
exec(compile(_source, str(_IMPL), "exec"), globals())
