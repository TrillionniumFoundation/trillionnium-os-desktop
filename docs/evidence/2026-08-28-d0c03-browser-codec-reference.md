# D0C-03 Browser codec executable reference evidence

> **SUPERSEDED_HISTORICAL:** This reference snapshot predates the Rust product
> codec host validation. The executable corpus remains useful historical
> evidence; current status is recorded in
> `docs/architecture/CANONICAL_BROWSER_CODEC.md` and the generated result.

**Date:** 2026-08-28  
**Scope:** canonical JSON, Browser API shape, session binding and effect classification  
**Product listener:** not created  
**Browser dispatch:** not performed  
**External effect:** not authorized  
**Rust product codec:** not implemented

## Why this checkpoint exists

The earlier D0C-03 branch had drifted from the active D5 contract: it used a
`timeout_ms` request envelope, omitted the current typed navigation model and
classified navigation as read-only. That implementation was not carried
forward. The v2 checkpoint is regenerated from the current
`browser-api.v1.schema.json` and adds a stricter canonical wire layer.

## Executed environment

```text
Python 3.13.5
Linux 6.18.35 x86_64 GNU/Linux
```

## Commands executed

```text
python3 tools/browser_codec_reference.py \
  --self-test \
  --contract contracts/browser-codec.v1.json \
  --write-result docs/evidence/generated/d0c03-browser-codec-reference-result.json \
  --write-golden-dir contracts/golden
python3 -m py_compile \
  tools/browser_codec_reference.py \
  tools/browser_codec_reference/*.py
```

## Observed result

All 26 reference checks passed. The corpus includes:

- canonical round trip and noncanonical whitespace rejection;
- recursive duplicate-member rejection;
- unknown top-level and operation-member rejection;
- unbound/bound session and generation rules;
- boolean-to-integer coercion rejection;
- unpublished semantic snapshot rejection;
- external HTTP, URL userinfo and private-LAN fixture rejection;
- navigation/click potential-effect and scroll-local classification;
- UTF-8 byte bounds, message-size-before-parse and nesting bounds;
- floating-point rejection;
- strict success/error response shapes;
- normative error retry binding;
- paired response session identity.

Stable content hashes:

```text
browser-codec contract:
  b6f4b8318925775f8e2fe053b714a5563f7610286e8da471a91bf21d9d827c37
request wire schema:
  e22d5e7c0dfab8064b621cf53b856fc3537543d50f89b71947eac3a059b01b62
response wire schema:
  d24560192330acb9028d95bf9a2dcc839c74250fa36d5674dc81499be40b7f4d
reference result:
  b7885a813933fe73ee710332274060649e81dee636e7580f556f0b24cb88e818
```

Golden canonical SHA-256 values:

```text
health request:        2315fbbe2e6ff4aff43ab9ccd7a9dbed5dd0f0b531dc11270157a1a81386ac46
session create:        3d5e3db8d918030df3f1fb840462d56a6fde96a99013e61ba1bb55f2d502c4fb
external navigation:   51d86fbbd56906e3127bd134fd101404cda78eaf55f36fe5d7a3dddd1fe18e59
click request:         527d781b55dca3c9b274f27f5a021ae50ad4500cfd065167b3909fd994b717af
success response:      1a003c1e7b381d17cb3109361b32087aa6b50e398bcaa0b26201ee8f5def85e4
policy error response: c17a6e750d6d09c832bbf24e91bd36559145331cfd7126fde51a4c405c0c0337
```

## Claim ceiling

This checkpoint proves that the executable standard-library reference and its
golden vectors agree with the checked-in codec contract on the recorded host.
It does not prove a Rust product codec, an AgentPort bridge, a live listener,
a BrowserActor, a Servo WebView, navigation, rendering, native input or any
external side effect. Merge readiness remains false until the Rust 1.93
implementation and exact-head checks are completed.
