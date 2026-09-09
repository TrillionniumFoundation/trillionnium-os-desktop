# Event-loop completion boundary

Status: **S06 callback fixture candidate; no native engine event loop**

## Purpose

The callback completion model separates enqueue acceptance from terminal engine
completion. `EngineCompletion` is single-use and non-cloneable. Queueing is not
execution and is never durable success.

## State and wakeups

The model permits one queued request, one active call and one completion. The
owner does not block waiting for a callback. Request enqueue, abandonment,
endpoint drop, callback result and callback drop wake the state machine.
Cancellation, deadline and request-custody checks use the original monotonic
request boundary and cannot be reset by a callback.

## Terminal classification

A dropped callback is a browser crash, not success. Retirement invalidates the
pending operation and performs cleanup at most once. Before a final reply the
actor rechecks request-scoped identity; uncertainty after a possible effect is
reported as indeterminate and is never automatically replayed.

## Product boundary

The product crate does not export the callback backend trait or accept a generic
runtime. The S06 product actor owns only the deterministic local fixture runtime.
A native Servo event loop requires a later concrete reviewed adapter, exact-pin
behavior evidence and installed-image qualification.

## Evidence and claim ceiling

Required source and document paths are recorded in
`contracts/event-loop-completion.v1.json` and mechanically checked. This source
model proves no process IPC, native event-loop latency, product listener,
external-effect authority, installed image, hardware, signing or release.
