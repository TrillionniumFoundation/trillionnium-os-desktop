"""Negative controls for comments/literals used by the HOS2 source guards."""
import unittest

from rust_source_contract import block_after, positions, rust_tokens


class RustSourceContractLexing(unittest.TestCase):
    def test_comment_decoys_cannot_satisfy_a_guard(self):
        tokens = rust_tokens('''// checked_call();
            /* nested /* checked_call(); */ checked_call(); */
            actual_call();''')
        self.assertEqual(positions(tokens, "checked_call();"), [])
        self.assertEqual(len(positions(tokens, "actual_call();")), 1)

    def test_literals_do_not_add_code_tokens_or_close_a_function(self):
        tokens = rust_tokens('''fn sample() {
            let plain = "} // checked_call();";
            let raw = r#"} /* checked_call(); */"#;
            actual_call();
        }''')
        body = block_after(tokens, "fn sample(")
        self.assertEqual(positions(body, "checked_call();"), [])
        self.assertEqual(len(positions(body, "actual_call();")), 1)

    def test_malformed_comments_or_literals_fail_closed(self):
        for source in ('/* unfinished', '"unfinished', 'r#"unfinished'):
            with self.subTest(source=source):
                with self.assertRaises(AssertionError):
                    rust_tokens(source)

    def test_missing_or_duplicate_function_is_not_accepted(self):
        for source in ('fn other() {}', 'fn sample() {} fn sample() {}', 'fn sample() {'):
            with self.subTest(source=source):
                with self.assertRaises(AssertionError):
                    block_after(rust_tokens(source), "fn sample(")


if __name__ == "__main__":
    unittest.main()
