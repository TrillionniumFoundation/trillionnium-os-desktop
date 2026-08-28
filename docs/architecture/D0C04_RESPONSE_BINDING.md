# D0C-04 response binding

The handler cannot author protocol, request ID, session ID, session generation,
transport sequence or connection nonce. The connected AgentPort copies these
fields from the validated request and authenticated connection, canonicalizes
the response, records its SHA-256, and only then attempts the same-sequence
transport commit before the effective deadline.
