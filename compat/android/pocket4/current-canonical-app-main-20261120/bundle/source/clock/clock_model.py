"""Explicit adapters for the retained pure original model contracts."""
import types


def model_for(session):
    p=session.components['clock_preservation.py']
    def read_sql(current,label,sql):
        session.c.need(current is session,'SAME_FRESH_CLOCK_SQL_SESSION')
        raw=session.sql(label,sql)
        value=session.c.parse(raw) if raw.strip() else []
        session.c.need(type(value) is list,'ORIGINAL_CLOCK_SQL_ROW_ARRAY')
        return value
    def read(current):
        session.c.need(current is session,'SAME_FRESH_TIMER_SESSION')
        return session.protection.timer_read()
    owned=session.components['clock_expiry_flow.py'].owned_timer if session.kind=='expiry06' else p.owned
    return types.SimpleNamespace(DB=p.DB,read_sql=read_sql,read=read,empty=p.empty,owned=owned,UNUSED=p.UNUSED)


def continuation_factory(session):
    def construct(trial,package):
        session.c.need(trial is session.trial and package=='com.android.deskclock','EXACT_CURRENT_CLOCK_CONTINUATION')
        value=session.components['clock_continuation.py'].TypedContinuation(trial,package,trial.backend,lambda value:None)
        trial.continuation=value
        return value
    return construct
