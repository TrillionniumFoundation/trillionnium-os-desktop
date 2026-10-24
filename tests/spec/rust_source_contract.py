"""Small lexical helpers for source guards, not a Rust parser or runtime proof.

Keep comments and formatting out of comparisons without discarding string
literals, token boundaries, feature expressions or operation order. Native
kernel and guest tests remain the authority for compiled behavior.
"""
import re


_RAW_STRING = re.compile(r'(?:br|r)(#{0,255})"')
_TOKEN = re.compile(
    r"'(?:[A-Za-z_][A-Za-z0-9_]*)\b(?!')"
    r'|[A-Za-z_][A-Za-z0-9_]*|[0-9][A-Za-z0-9_]*'
    r'|::|=>|->|\.\.=|\.\.|<<=?|>>=?|&&|\|\||==|!=|<=|>='
    r'|[+*/%&|^!-]=|[^\s]'
)


def rust_tokens(source):
    """Tokenize the guards' Rust subset, including nested comments/literals."""
    result = []
    at = 0
    while at < len(source):
        if source[at].isspace():
            at += 1
            continue
        if source.startswith('//', at):
            end = source.find('\n', at)
            at = len(source) if end == -1 else end + 1
            continue
        if source.startswith('/*', at):
            at += 2
            depth = 1
            while depth and at < len(source):
                if source.startswith('/*', at):
                    depth += 1
                    at += 2
                elif source.startswith('*/', at):
                    depth -= 1
                    at += 2
                else:
                    at += 1
            if depth:
                raise AssertionError('unterminated Rust block comment')
            continue
        raw = _RAW_STRING.match(source, at)
        if raw:
            suffix = '"' + raw[1]
            end = source.find(suffix, raw.end())
            if end == -1:
                raise AssertionError('unterminated Rust raw string')
            end += len(suffix)
        elif source[at] == '"':
            end = at + 1
            while end < len(source) and source[end] != '"':
                end += 2 if source[end] == '\\' else 1
            if end >= len(source):
                raise AssertionError('unterminated Rust string')
            end += 1
        else:
            char = re.match(r"'(?:\\.|[^'\\\n])'", source[at:])
            end = at + len(char[0]) if char else _TOKEN.match(source, at).end()
        result.append(source[at:end])
        at = end
    return tuple(result)


def positions(tokens, fragment):
    needle = rust_tokens(fragment)
    return [at for at in range(len(tokens) - len(needle) + 1)
            if tokens[at:at + len(needle)] == needle]


def require_sequence(tokens, fragment, label):
    if not positions(tokens, fragment):
        raise AssertionError(f'{label}: missing Rust token sequence: {fragment}')


def replace_once(tokens, fragment, replacement):
    """Create a negative control without depending on source line wrapping."""
    starts = positions(tokens, fragment)
    if not starts:
        raise AssertionError(f'missing mutation target: {fragment}')
    start = starts[0]
    return tokens[:start] + rust_tokens(replacement) + tokens[start + len(rust_tokens(fragment)):]


def block_after(tokens, fragment):
    starts = positions(tokens, fragment)
    if len(starts) != 1:
        raise AssertionError(f'expected one Rust block for {fragment}, got {len(starts)}')
    start = starts[0] + len(rust_tokens(fragment))
    while start < len(tokens) and tokens[start] != '{':
        start += 1
    depth = 1
    for end in range(start + 1, len(tokens)):
        depth += (tokens[end] == '{') - (tokens[end] == '}')
        if depth == 0:
            return tokens[start + 1:end]
    raise AssertionError(f'unterminated Rust block for {fragment}')
