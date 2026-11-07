def main():
    need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000
         and sys.argv[1:] == ['--observe-pinned-national-intermediate-only'], 'EXACT_ORDINARY_OWNER_ENTRY')
    need(ROOT.parent.resolve(strict=True) == ROOT.parent, 'EXISTING_NORMAL_PARENT_REQUIRED')
    os.umask(0o077)
    before = census()
    ROOT.mkdir(mode=0o700)
    accounting = {'acquired': 0, 'closed': 0, 'errors': []}
    result = {
        'schema': 'pocket4-national-literal-intermediate-observation-v1', 'ok': False,
        'meaning_of_ok': 'one complete ordinary intermediate HTML observation; no binary qualification',
        'package': 'com.ehi.national.mobile', 'started_utc': now(), 'requests': [], 'errors': [],
        'prior_successful_page_job': '1a1b356f0cc-fc05-8238',
        'prior_HTML_reference': INPUT, 'input_owned_descriptors': accounting,
        'maximum_HTTP_GET_requests': 1, 'maximum_HTML_bytes': MAX_BODY,
        'maximum_total_seconds': TOTAL_SECONDS, 'ordinary_uid': os.getuid(),
        'user_agent_policy': 'urllib default unmodified', 'TLS_policy': 'system trust/default verification',
        'cookie_jar_created': False, 'prior_cookie_values_read_or_replayed': False,
        'response_cookie_values_persisted': False, 'response_cookie_values_hashed_and_redacted': True,
        'automatic_redirects': False, 'automatic_retry': False, 'script_execution': False,
        'challenge_solving': False, 'DNS_IP_proxy_TLS_modifications': False,
        'ordinary_resolver_internal_attempts_not_instrumented': True,
        'delivery_link_requests': 0, 'APK_downloads': 0, 'APK_signature_verified': False,
        'APK_candidate_qualified': False, 'store_installer_used': False,
        'subprocesses_started': 0, 'Main_actions': 0, 'Android_commands': 0,
        'UI_actions': 0, 'installs': 0, 'permission_changes': 0,
        'production_ready': False, 'cleanup_eligible': False,
        'before_descriptor_identities': before,
        'output_pin_semantics': 'hash of bytes written; no separate output readback or directory crash-persistence proof',
    }
    held = None
    previous_handler = signal.signal(signal.SIGALRM, deadline_signal)
    try:
        end = time.monotonic() + TOTAL_SECONDS
        signal.setitimer(signal.ITIMER_REAL, TOTAL_SECONDS, 0)
        held = FixedPriorHTML(end, accounting)
        result['prior_HTML_binding'] = held.public_binding()
        result['literal_rederivation'] = derive_exact_intermediate(held.raw)
        raw, row = fetch_html_once(1, result['literal_rederivation']['literal_url'], end, result)
        need(not any(name.casefold() == 'cf-mitigated' and value.casefold() == 'challenge'
                     for name, value in row['headers']), 'PUBLIC_CHALLENGE_STOP_NO_SOLVING_OR_ALTERNATE_IDENTITY')
        row['parsed_observation'] = observe_intermediate_controls(raw)
        need(held.recheck() == held.raw, 'PRIOR_HTML_BYTES_CHANGED_AFTER_REQUEST')
        result['prior_HTML_complete_bytes_stat_path_rechecked_after_request'] = True
        result['ok'] = len(result['requests']) == 1 and row['complete'] is True
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
        result['ok'] = False
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if held is not None:
            try:
                held.path_recheck()
                result['prior_HTML_path_stat_stable_at_final_close'] = True
            except BaseException as error:
                result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512],
                                         'phase': 'input_final_path_stat'})
                result['ok'] = False
            finally:
                held.close()
    result['after_descriptor_identities'] = census()
    result['original_descriptor_identities_restored'] = result['after_descriptor_identities'] == before
    result['ok'] = (result['ok'] and result['original_descriptor_identities_restored']
                    and accounting['acquired'] == accounting['closed'] and not accounting['errors']
                    and not result['errors'])
    result['ended_utc'] = now()
    raw = (json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False) + '\n').encode()
    save('result.json', raw)
    need(census() == before, 'FINAL_PUBLICATION_DESCRIPTOR_SET_CHANGED')
    print(raw.decode(), end='', flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
