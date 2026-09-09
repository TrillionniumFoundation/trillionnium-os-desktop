# Session incarnation boundary

Status: **S06 source/test candidate; no durable anti-rollback or installed runtime**

## Purpose

Each BrowserActor lazily acquires 32 bytes from an actor-private operating-system
entropy source on the first valid session creation. The entropy is domain-separated
and hashed before it participates in the opaque session and WebView identities.
A zero or failed read is latched: the actor cannot fall back to a predictable
namespace and must be reconstructed.

## Ownership and API separation

Incarnation entropy belongs to `hepta-browser-actor-simulation`, not the Agent
transport. The product Transport API does not export nonce-source injection,
fixed nonces, or session nonce material. Unit-test entropy injection is private
to the unpublished simulation crate and cannot be selected by a product caller,
environment variable, wire field, or configuration file.

## Ordering and failure

Counter exhaustion is checked before entropy or runtime work. Entropy acquisition
does not extend the original request deadline. A namespace is read at most once
per actor and is never automatically resurrected after an entropy failure.
Close/create cycles use checked ordinals inside the same namespace; actor
reconstruction creates a different namespace. Previous session, WebView, frame,
and semantic references therefore fail closed.

## Frame identity

A scoped frame identity hashes length-delimited session, WebView and local frame
keys under a separate domain. It is an opaque lookup identity, not proof that a
frame/node exists and not action authority. A concrete engine must still resolve
the current frame and retained node under current revisions.

## Claim ceiling

This mechanism does not prove absolute global uniqueness, durable rollback
resistance, product activation, Servo integration, installed-image behavior,
hardware identity, signing, publication or release readiness.
