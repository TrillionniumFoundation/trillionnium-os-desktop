"""Bind content pins to a fixed local role without importing origin-host paths."""
from pathlib import Path


def require(value, message):
    if not value:
        raise ValueError(message)


def local_source_pin(root, relative, ref):
    """Bind content-only pins to the explicit local role, never a provenance path."""
    require(type(ref) is dict and set(ref) == {'bytes', 'sha256'},
           'local source pins contain only bytes and sha256')
    require(type(ref['bytes']) is int and ref['bytes'] >= 0
           and type(ref['sha256']) is str and len(ref['sha256']) == 64
           and all(c in '0123456789abcdef' for c in ref['sha256']),
           'strict local source content identity required')
    require(isinstance(root, Path) and root.is_absolute()
           and type(relative) is str and relative and '\\' not in relative
           and '\0' not in relative and not Path(relative).is_absolute()
           and all(part not in ('', '.', '..') for part in relative.split('/')),
           'fixed local source role path required')
    return {'bytes': ref['bytes'], 'sha256': ref['sha256'], 'path': str(root / relative)}


