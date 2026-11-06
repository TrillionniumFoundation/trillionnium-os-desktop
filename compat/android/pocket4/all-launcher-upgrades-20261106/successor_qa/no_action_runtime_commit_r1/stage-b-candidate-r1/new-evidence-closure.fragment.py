def collect_relative_hashes(base, context, flow, deadline):
    hashes = {}
    for path, (raw, metadata) in context['originals'].items():
        if not path.startswith(FLOW + '/'):
            continue
        relative = path[len(FLOW) + 1:]
        need(relative and not relative.startswith('reconciliations/') and '\\' not in relative and
             all(part not in ('', '.', '..') for part in relative.split('/')),
             'ONLY_ORIGINAL_FLOW_RELATIVE_EVIDENCE_NO_EXTERNAL_PATH_DISGUISE')
        hashes[relative] = sha(raw)
    root_names = {'scope.json', 'launch-scope.json', 'qa-' + CASE_STEP + '.case.json',
                  'baseline.json', 'baseline-qualification.json'}
    expected = root_names | {'steps/' + CASE_STEP + '/' + name
                            for name in context['historical_hashes']['case']}
    expected |= {'steps/' + STAGE_A_STEP + '/' + name for name in context['stage_A_file_set']}
    need(len(context['historical_hashes']['case']) == 90 and len(context['stage_A_file_set']) == 57 and
         set(hashes) == expected and len(expected) == 152,
         'EXACT_90_FAILED_57_COMPLETED_RUNTIME_AND_FIVE_FLOW_INPUTS')
    initial = sorted(os.listdir(flow.step))
    current = {'intent.json', 'held-main-binding.json'}
    current |= {'command-%03d%s' % (index, suffix) for index in range(1, 7)
                for suffix in ('.intent.json', '.result.json', '.stdout', '.stderr')}
    current |= {'transport-%03d.%s.json' % (index, suffix) for index in range(1, 9)
                for suffix in ('intent', 'command-result', 'verified-result')}
    current |= {'producer-source.py', 'producer-request.json', 'no-action-history.json',
                'history-reader.stdout.original.json', 'history-reader.terminal.original.json',
                'stage-a-controller.stdout.original.jsonl', 'stage-a-controller.terminal.original.json',
                'stage-a-owned-joint.original.json', 'owned-qa-no-action-proof.json'}
    need(set(initial) == current and len(current) == 59 and 'result.json' not in initial,
         'EXACT_NEW_59_PREPUBLICATION_FILES_NO_FUTURE_RESULT_OR_INVENTED_OBSERVER')
    for name in initial:
        need(time.monotonic() < deadline, 'BOUNDED_NEW_PROOF_FILE_SET')
        raw, _ = base.read(flow.step / name)
        relative = 'steps/' + STEP + '/' + name
        need(relative not in hashes, 'NEW_PROOF_MUST_NOT_REPLACE_ORIGINAL_EVIDENCE')
        hashes[relative] = sha(raw)
    need(sorted(os.listdir(flow.step)) == initial and len(hashes) == 211,
         'ALL_211_REQUIRED_ORIGINAL_AND_NEW_EVIDENCE_MEMBERS')
    return dict(sorted(hashes.items()))


def published_member_set(hashes):
    need(type(hashes) is dict and len(hashes) == 211, 'EXACT_211_PUBLISHED_EVIDENCE_MEMBERS')
    fixed = {'scope.json', 'launch-scope.json', 'qa-' + CASE_STEP + '.case.json',
             'baseline.json', 'baseline-qualification.json'}
    counts = {'steps/' + CASE_STEP + '/': 90, 'steps/' + STAGE_A_STEP + '/': 57,
              'steps/' + STEP + '/': 59}
    need({name for name in hashes if not name.startswith('steps/')} == fixed and
         all(sum(name.startswith(prefix) for name in hashes) == count for prefix, count in counts.items()) and
         all(name in fixed or any(name.startswith(prefix) for prefix in counts) for name in hashes),
         'PUBLISHED_CLOSURE_HAS_ONLY_THIS_CASE_ACTUAL_STAGE_A_AND_NEW_COMMIT')
