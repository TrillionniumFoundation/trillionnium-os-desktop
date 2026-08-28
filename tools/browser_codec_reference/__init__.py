"""Executable standard-library reference for Browser API canonical wire v1."""
from .canonical import CodecError, PROTOCOL, canonical, decode_unique
from .request import decode_request, encode_request, validate_request
from .response import decode_response, encode_response, validate_response
from .evidence import build_result, fixtures, self_test

__all__ = [
    "CodecError", "PROTOCOL", "canonical", "decode_unique", "decode_request",
    "encode_request", "validate_request", "decode_response", "encode_response",
    "validate_response", "build_result", "fixtures", "self_test",
]
