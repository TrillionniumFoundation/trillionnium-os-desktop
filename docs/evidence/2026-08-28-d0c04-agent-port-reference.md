# D0C-04 connected AgentPort executable reference evidence

**Date:** 2026-08-28  
**Carrier:** local AF_UNIX socketpair  
**Listener:** not created  
**BrowserActor:** not called  
**Servo:** not called  
**External effect:** not authorized  
**Rust bridge:** not implemented

## Executed path

```text
SO_PEERCRED policy
  -> nonce challenge
  -> sequence/digest-bound request frame
  -> canonical Browser API decoder
  -> exactly one handler invocation
  -> request-bound canonical response
  -> response frame
```

## Commands

```text
python3 tools/agent_port_bridge_reference.py \
  --contract contracts/agent-port-bridge.v1.json \
  --write-result docs/evidence/generated/d0c04-agent-port-bridge-reference-result.json
python3 -m py_compile \
  tools/agent_port_bridge_reference.py \
  tools/agent_port_bridge_reference/*.py \
  tools/agent_transport_reference.py \
  tools/browser_codec_reference.py \
  tools/browser_codec_reference/*.py
```

## Observed result

All 13 checks passed:

- observation request dispatches exactly once;
- request ID and session identity are copied from the request;
- canonical request and response SHA-256 values are bound;
- peer identity and transport sequence reach the dispatch context;
- observation and potential-effect classes reach the handler unchanged;
- external navigation receives a typed default denial;
- the denial response preserves session ID and generation;
- a late handler result is not committed;
- duplicate JSON members fail before handler invocation;
- an invalid handler reply is not committed.

Stable hashes:

```text
bridge contract:
  8dc44d9731f98b6c31c0ba971aeeae5f991762ec4c0bf929a6c1e961eeb2a64c
reference result:
  7611edc684bd2929bdb6e4602bc40c7771d302c658f595178f32f494e6252c34
bridge entrypoint:
  ccd6c5c1a6183762debbd2f31421d653be0abc4e8372ec6e7efcfee7cb85f6e8
bridge core:
  95aea0ff000fc6427dc4b77a7dd505fd999db002df0d4e4a0a9aa9665f9257c3
bridge corpus:
  eea2ca1b77e2afa320ff7c082c2db59fe5ff03cf12ca3b22ded83a7431ae64e6
```

## Claim ceiling

This proves the behavior of the executable Python standard-library reference
on the recorded host. It does not prove the Rust bridge, a service socket,
systemd custody, TaskFlow principal mapping, BrowserActor dispatch, a Servo
WebView or an external side effect. The stacked PR remains draft and
non-merge-ready until the Rust 1.93 implementation passes exact-head gates.
