"""Mandatory original live-Root sources shared by selection and verification.

This is source identity policy, never an authority or runtime qualification.
"""
ROOT_ADMIN_SOURCE_FILES = frozenset({
    "CALLERS.toml",
    "scripts/verify_hepta_callers.py",
    "qa/b4-no-bypass/test_root_admin_source_closure.py",
    "codex-rs/hepta-agentd/ROOT_ADMIN.md",
    "codex-rs/hepta-agentd/src/authority_host_admin.rs",
    "codex-rs/hepta-agentd/src/authority_host_admin_protocol.rs",
    "codex-rs/hepta-agentd/src/authority_host_admin_service.rs",
    "codex-rs/hepta-agentd/src/authority_host_admin_effect.rs",
    "codex-rs/hepta-agentd/src/authority_host_admin_deadline.rs",
    "codex-rs/hepta-agentd/src/authority_host_admin_tests.rs",
    "codex-rs/hepta-agentd/src/authority_host_admin_deadline_tests.rs",
    "codex-rs/hepta-agentd/src/authority_host_service.rs",
    "codex-rs/hepta-agentd/src/authority_host_session.rs",
    "codex-rs/hepta-agentd/src/authority_host_session_material.rs",
    "codex-rs/hepta-agentd/src/deployment_issuer.rs",
    "codex-rs/hepta-agentd/src/deployment_notes.rs",
    "codex-rs/hepta-agentd/src/deployment_notes_observation.rs",
    "codex-rs/hepta-agentd/src/deployment_notes_observation_tests.rs",
    "codex-rs/hepta-agentd/src/deployment_notes_revoke.rs",
    "codex-rs/hepta-agentd/src/deployment_notes_revoke_observation.rs",
    "codex-rs/hepta-agentd/src/deployment_signed_grant.rs",
    "codex-rs/hepta-agentd/src/deployment_signed_grant_tests.rs",
    "codex-rs/hepta-agentd/src/root_authority_session.rs",
    "codex-rs/hepta-agentd/src/root_authority_session_tests.rs",
    "codex-rs/hepta-agentd/src/root_authority_resource_tests.rs",
    "codex-rs/hepta-agentd/src/config.rs",
    "codex-rs/hepta-agentd/src/config_root_handoff.rs",
    "codex-rs/hepta-agentd/src/config_root_handoff_tests.rs",
    "codex-rs/hepta-agentd/src/owner_writer_custody.rs",
    "codex-rs/hepta-agentd/src/production_writer_host.rs",
    "codex-rs/hepta-agentd/src/production_protected_host.rs",
    "codex-rs/hepta-agentd/src/production_owner_custody_tests.rs",
    "codex-rs/hepta-contracts/src/final_use.rs",
    "codex-rs/hepta-contracts/src/authority_lease.rs",
    "codex-rs/hepta-contracts/src/authority_lease_revoke.rs",
    "codex-rs/hepta-contracts/src/authority_lease_revoke_tests.rs",
})


def require_root_admin_sources(records):
    names = [record["path"] for record in records]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate original source identity")
    missing = sorted(ROOT_ADMIN_SOURCE_FILES - set(names))
    if missing:
        raise ValueError("Source contract omits original live Root administration inputs: " + ", ".join(missing))
