from pathlib import Path
import ast, hashlib, json

root = Path(__file__).resolve().parent
base = (root/'base-support/partial_diagnostic.py').read_text()
assert hashlib.sha256(base.encode()).hexdigest() == '493b054a63750757bf3b92d8b9e2734f2c83054a4689de75a59a05268582b5be'
s = base

def replace(old, new, count=1):
    global s
    assert s.count(old) == count, (old[:120], s.count(old), count)
    s = s.replace(old, new)

replace('Read-only partial lint-transition observations under the caller\'s custody.',
        'Read-only partial APEX-provider observations under the caller\'s custody.')
replace('Only the six independently fixed original lint blobs',
        'Only the four independently fixed original APEX provider blobs')
replace("SCHEMA = 'p4-r20-incomplete-lint-recovery-diagnostic-v1'",
        "SCHEMA = 'p4-r22-incomplete-apex-provider-recovery-diagnostic-v1'")
replace('def _lint_attributes(bookends, core, checkout, deadline, guard, commands, captures, directory):\n    names = sorted(core.LINT)',
        "def _provider_attributes(bookends, core, project, checkout, deadline, guard, commands, captures, directory):\n    names = sorted(path for provider, path in core.CANDIDATES if provider == project)\n    need(len(names) == 2, 'both files of this original provider')")
replace("'check-attr', '--source=' + core.COMMIT]", "'check-attr', '--source=' + core.PROVIDERS[project]['commit']]")
replace('complete six-candidate attribute triples', 'complete provider attribute triples')
replace('exact original lint attribute order', 'exact original provider attribute order')
replace('new lint members require unchanged raw checkout bytes and no content transformations',
        'new provider members require unchanged raw checkout bytes and no content transformations')
replace('committed and effective lint attributes differ', 'committed and effective provider attributes differ')
start = s.index('def candidate_checkout_rules(')
end = s.index('\ndef _candidate_checkout_rules(', start)
s = s[:start] + '''def candidate_checkout_rules(bookends, core, source, directory, deadline, guard, config_admission):
    _production_admission(config_admission)
    source, directory = Path(source), Path(directory)
    need(source.resolve() == source and source.is_dir(), 'original source root')
    need(directory.is_absolute() and directory.parent.resolve() == directory.parent
         and source != directory and source not in directory.parents,
         'provider rule observations must be outside source')
    directory.mkdir(mode=0o700)
    result = {}
    for number, project in enumerate(sorted(core.PROVIDERS)):
        result[project] = _candidate_checkout_rules(
            bookends, core, project, source / project, directory / ('provider-%02d' % number),
            deadline, guard, config_admission)
    need(set(result) == set(core.PROVIDERS), 'both original provider rule observations')
    return {'schema': 'p4-r22-four-original-apex-provider-checkout-rules-v1',
            'providers': result, 'candidate_count': 4,
            'all_five_attributes_unspecified': True, 'committed_effective_equal': True,
            'custom_filters_executed': False, 'source_mutations': False,
            'source_recovery_complete': False, 'runtime_qualified': False, 'production_ready': False}

''' + s[end:]
replace('def _candidate_checkout_rules(bookends, core, checkout, directory, deadline, guard, config_admission):',
        'def _candidate_checkout_rules(bookends, core, project, checkout, directory, deadline, guard, config_admission):')
replace('Same six-attribute parser for the initial reconcile and a single resume.',
        'Same exact attribute parser for the initial reconcile and a single resume.')
replace("need(head == core.COMMIT and origin == core.ORIGIN, 'six rules belong to original HealthFitness')",
        "need(head == core.PROVIDERS[project]['commit'] and origin == core.PROVIDERS[project]['url'],\n             'rules belong to this exact original APEX provider')")
replace('        for name in core.LINT:\n',
        "        for provider, name in core.CANDIDATES:\n            if provider != project:\n                continue\n")
replace("need(not os.path.lexists(checkout / '.git/info/attributes'), 'no local attribute override for lint')",
        "need(not os.path.lexists(checkout / '.git/info/attributes'), 'no local attribute override for providers')", 2)
replace('observations = _lint_attributes(bookends, core, checkout, deadline, guard, commands, captures, directory)',
        'observations = _provider_attributes(bookends, core, project, checkout, deadline, guard, commands, captures, directory)')
replace('original six-rule metadata remains unchanged', 'original provider-rule metadata remains unchanged')
replace("'schema': 'p4-r20-six-original-lint-checkout-rules-v1'",
        "'schema': 'p4-r22-original-apex-project-checkout-rules-v1'")
replace("'HEAD': head, 'origin': origin, 'candidate_count': 6,",
        "'HEAD': head, 'origin': origin, 'project': project, 'candidate_count': 2,")
replace("'schema': 'p4-r20-six-original-lint-checkout-rules-failure-v1'",
        "'schema': 'p4-r22-original-apex-project-checkout-rules-failure-v1'")
replace('observed_ns = time.time_ns(); health_profile = None; health_attributes = None',
        'observed_ns = time.time_ns(); provider_profiles = {}; provider_attributes = {}')
replace("                is_health = old['path'] == core.HEALTH\n                need((new == {**old, 'sparse_paths': old['sparse_paths'] + ['lint']}) if is_health else old == new,\n                     'only the original complete lint directory may expand')",
        "                provider = core.PROVIDERS.get(old['path'])\n                is_provider = provider is not None\n                need((new == {**old, 'sparse_paths': old['sparse_paths'] + [provider['cone']]})\n                     if is_provider else old == new,\n                     'only both complete original provider directories may expand')")
replace("                        if is_health:\n                            health_profile = 'old'",
        "                        if is_provider:\n                            provider_profiles[old['path']] = 'old'")
replace("need(is_health and set(cones) == set(bookends.canonical_sparse_cones(new['sparse_paths'])),\n                             'actual sparse cones match neither fixed Health scope')\n                        selected = new; health_profile = 'new'",
        "need(is_provider and set(cones) == set(bookends.canonical_sparse_cones(new['sparse_paths'])),\n                             'actual sparse cones match neither fixed provider scope')\n                        selected = new; provider_profiles[old['path']] = 'new'")
replace('                if is_health:\n',
        '                if is_provider:\n')
replace('                    health_attributes = _lint_attributes(bookends, core, checkout, deadline, guard,\n                                                         commands, captures, directory)',
        "                    provider_attributes[old['path']] = _provider_attributes(\n                        bookends, core, old['path'], checkout, deadline, guard, commands, captures, directory)")
replace('                    # Only these six entries use the old cone requirement when',
        '                    # Only these four entries use the old cone requirement when')
replace('                    candidate = is_health and relative in core.LINT',
        "                    candidate_key = (old['path'], relative)\n                    candidate = candidate_key in core.CANDIDATES")
replace('                        core._candidate(observed, core.LINT[relative], True)',
        '                        core._candidate(observed, candidate_key, True)')
replace("        need(health_profile in ('old', 'new') and health_attributes is not None,\n             'one actual HealthFitness partial scope and six attributes')",
        "        need(set(provider_profiles) == set(provider_attributes) == set(core.PROVIDERS)\n             and all(state in ('old', 'new') for state in provider_profiles.values()),\n             'both actual original provider scopes and all four attribute observations')")
replace("'actual_health_cone_profile': health_profile, 'lint_checkout_attributes': health_attributes,",
        "'actual_provider_cone_profiles': provider_profiles, 'provider_checkout_attributes': provider_attributes,")
ast.parse(s)
before = {n.name: ast.get_source_segment(base, n) for n in ast.parse(base).body if isinstance(n, ast.FunctionDef)}
after = {n.name: ast.get_source_segment(s, n) for n in ast.parse(s).body if isinstance(n, ast.FunctionDef)}
unchanged = ['need', 'f9', 'fingerprint', 'write_bytes', '_no_git_locks', '_metadata', '_scope',
             '_production_admission', '_capture_query', '_configuration', '_all_tracked_filters', 'partial_snapshot']
for name in unchanged:
    assert before[name] == after[name], name
out = root/'apex_test_partial.py'
with out.open('x') as f:
    f.write(s)
(root/'PARTIAL-SOURCE-PROOF.json').write_text(json.dumps({
    'schema':'p4-r22-apex-provider-partial-source-proof-v1',
    'parent_bytes':len(base.encode()), 'parent_sha256':hashlib.sha256(base.encode()).hexdigest(),
    'successor_bytes':len(s.encode()), 'successor_sha256':hashlib.sha256(s.encode()).hexdigest(),
    'unchanged_function_bodies':unchanged, 'source_operations_executed':False,
    'runtime_qualified':False, 'production_ready':False,
}, indent=2)+'\n')
print(len(s.encode()), hashlib.sha256(s.encode()).hexdigest(), 'unchanged', len(unchanged))
