#!/usr/bin/env python3
"""Focused regressions for attached curl header spellings.

The broader governance corpus already exercises these paths.  This small test
keeps the parsing invariant visible: an attached non-``=`` long option cannot
consume the following URL as a supposedly harmless header value.
"""
from __future__ import annotations

import unittest

from tools.validate_governance_integrity import _contains_mutation


class AttachedCurlHeaderRegressionTests(unittest.TestCase):
    def test_dynamic_attached_long_header_fails_closed(self) -> None:
        self.assertTrue(
            _contains_mutation(
                "curl --header${HEADER} https://example.test/resource"
            )
        )

    def test_file_attached_long_header_fails_closed(self) -> None:
        self.assertTrue(
            _contains_mutation(
                "curl --header@headers.txt https://example.test/resource"
            )
        )

    def test_literal_separate_read_only_header_remains_allowed(self) -> None:
        self.assertFalse(
            _contains_mutation(
                'curl --header "Accept: application/json" '
                "https://example.test/resource"
            )
        )

    def test_literal_method_override_is_mutating(self) -> None:
        self.assertTrue(
            _contains_mutation(
                "curl --header=X-HTTP-Method-Override:DELETE "
                "https://example.test/resource"
            )
        )


if __name__ == "__main__":
    unittest.main()
