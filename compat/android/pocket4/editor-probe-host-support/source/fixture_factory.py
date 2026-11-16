"""Compose extracted original classes with only the new owned session."""
import types

def construct(session, result, emit):
    m = session.components
    trial = m['fixture_trial.py'].make_trial(session, session.tx, session.evidence_root / 'ui')
    loop = m['fixture_continuation.py'].make_loop(emit)
    name = 'fixture_editor.py' if session.kind == 'editor_ui03' else 'fixture_probe.py'
    adapter = m[name].make_case(session, trial, loop, result)
    diagnostics = m['fixture_diagnostics.py'].make_diagnostics(session, session.tx, session.evidence_root / 'diagnostics')
    session.trial = trial; session.case = adapter.flow
    session.helper.foreground = trial.owned_foreground
    return types.SimpleNamespace(flow=adapter.flow, identity=adapter.identity, diagnostics=diagnostics)
