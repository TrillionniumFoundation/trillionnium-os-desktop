# Hosted runner re-probe

**Date:** 2026-08-28

This branch commit re-triggers the permanent repository and Rust workflows after the repository visibility changed to public. It is evidence plumbing only and does not change the transport contract, enable a listener, or make a Rust validation claim.

A PASS may be recorded only from workflow jobs that receive a runner and execute non-empty steps against the exact branch head.
