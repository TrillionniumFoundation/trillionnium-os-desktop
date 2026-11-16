"""Compare normal serialized source plans without inventing omitted sparse cones.

The normal Rust PlannedProject uses serde(default, skip_serializing_if =
"Vec::is_empty") for sparse_paths. Omission therefore means the empty vector
(a complete project); null, scalars, duplicate paths, and narrowing are errors.
"""
from pathlib import PurePosixPath


def require(value, message):
    if not value:
        raise ValueError(message)


def sparse_paths(project):
    require(type(project) is dict, 'project must be a mapping')
    paths = project.get('sparse_paths', [])
    require(type(paths) is list, 'sparse_paths must be an array when present')
    for path in paths:
        require(type(path) is str and path and '\\' not in path and '\0' not in path,
                'sparse path must be a nonempty POSIX string')
        parts = path.split('/')
        require(not PurePosixPath(path).is_absolute() and all(part not in ('', '.', '..') for part in parts),
                'sparse path must stay inside its project')
    require(len(set(paths)) == len(paths), 'duplicate sparse path')
    return paths


def index_projects(rows):
    require(type(rows) is list, 'project list required')
    result = {}
    for row in rows:
        require(type(row) is dict and type(row.get('path')) is str and row['path'], 'project path required')
        require(row['path'] not in result, 'duplicate project path')
        sparse_paths(row)
        result[row['path']] = row
    return result


def validate_plan_expansion(previous_rows, current_rows, closure):
    previous = index_projects(previous_rows)
    current = index_projects(current_rows)
    expected = index_projects(closure['projects'])
    additions = index_projects(closure['added_projects'])
    require(type(closure['previous_project_count']) is int
            and type(closure['project_count']) is int
            and len(previous) == closure['previous_project_count']
            and len(current) == closure['project_count'], 'project count differs')
    require(set(current) == set(expected) and set(previous).issubset(current)
            and set(current) - set(previous) == set(additions), 'project membership changed')
    require(type(closure['added_cones']) is dict and set(closure['added_cones']).issubset(previous),
            'added cones must name existing projects')
    for name, row in current.items():
        wanted = expected[name]
        require(set(row).issubset({'path', 'url', 'commit', 'purpose', 'sparse_paths'}),
                'unknown normal project field')
        require(row['url'] == 'https://android.googlesource.com/' + wanted['name']
                and row['commit'] == wanted['commit'] and row['purpose'] == wanted['purpose']
                and sparse_paths(row) == sparse_paths(wanted), 'reviewed original project differs')
        if name in previous:
            old = previous[name]
            require({k:v for k,v in row.items() if k != 'sparse_paths'} ==
                    {k:v for k,v in old.items() if k != 'sparse_paths'}, 'existing project identity changed')
            old_paths = sparse_paths(old)
            new_paths = sparse_paths(row)
            added_paths = sparse_paths({'sparse_paths': closure['added_cones'].get(name, [])})
            require((bool(old_paths) or not new_paths)
                    and set(old_paths).issubset(new_paths)
                    and set(new_paths) - set(old_paths) == set(added_paths),
                    'unreviewed source cone change or complete project narrowed')
        else:
            require(wanted == additions[name], 'added project differs from its reviewed identity')
    return {'previous_project_count': len(previous), 'project_count': len(current),
            'added_project_paths': sorted(additions),
            'omitted_empty_sparse_paths': sum('sparse_paths' not in x for x in current_rows),
            'exact_expansion': True}
