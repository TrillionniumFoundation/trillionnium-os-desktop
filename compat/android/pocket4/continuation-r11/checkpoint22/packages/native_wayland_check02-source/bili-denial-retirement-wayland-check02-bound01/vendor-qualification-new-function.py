def qualified_vendor_inputs(registry, original_lock, cache, report):
    require(all(type(row.get('bytes')) is int and row['bytes'] > 0 and
                re.fullmatch(r'[0-9a-f]{64}',row.get('sha256','')) is not None
                for row in VENDOR_BINDING.values()),
            'future vendor preparation pins are not actually bound')
    raw_inputs, staged_inputs = {}, {}
    for name, limit in [('vendor-prep-result.json',4*1024*1024),
                        ('prepared-vendor-manifest.json',32*1024*1024),
                        ('prepared-vendor-config.toml',4096)]:
        raw,row = held(HERE/name,limit)
        expected = VENDOR_BINDING[name]
        require(row['bytes'] == expected['bytes'] and row['sha256'] == expected['sha256'],
                'staged actual vendor input differs: '+name)
        raw_inputs[name],staged_inputs[name] = raw,row
    prior = json.loads(raw_inputs['vendor-prep-result.json'])
    manifest = json.loads(raw_inputs['prepared-vendor-manifest.json'])
    require(prior['state'] == 'PASS' and prior['collection_complete'] is True and
            prior['offline_vendor_prepared_qualified'] is True and
            prior['fixed_registry_packages'] == 193 and len(prior['packages']) == 193 and
            prior['shared_cache_writes'] == 0 and prior['workspace_or_lock_modified'] is False and
            prior['production_sources_modified'] is False and prior['Main_actions'] == 0 and
            prior['Cargo_executed'] is False and prior['crate_code_executed'] is False and
            prior['commands_executed'] == 0 and prior['metadata_or_compile_qualified'] is False and
            prior['production_ready'] is False and not prior['secondary_errors'] and
            not prior['observed_signals'] and prior['shared_cache_presence_unchanged'] is True and
            prior['own_children_before']['observed_empty'] is True and
            prior['own_children_after']['observed_empty'] is True and
            prior['owned_resource_gate']['pass'] is True and prior['owned_resource_fd_closed'] is True and
            not prior['explicit_owned_descriptor_journal']['remaining'] and
            not prior['explicit_owned_descriptor_journal']['close_errors'] and
            all(prior[name] == [] for name in ['authorities_changes','original_cached_archives_changes',
                  'original_45_sources_changes','private_archives_changes','vendor_sources_changes']),
            'actual preparation lacks a complete success and unchanged-input/cleanup/resource gate')
    require(all(item['complete'] is True and item['http_requests'] == 1 and
                item['automatic_retries'] == 0 and item['redirects_followed'] == 0 and
                item['response_closed'] is True and item['connection_closed'] is True
                for item in prior['downloads']), 'preparation retained an incomplete download')
    current_registry = {(row['name'],row['version']):row for row in registry['packages']}
    prior_rechecked = {(row['name'],row['version']):row for row in prior['original_45_requalification']}
    require(len(current_registry) == len(registry['packages']) == 45 and
            len(prior_rechecked) == len(prior['original_45_requalification']) == 45 and
            set(prior_rechecked) == set(current_registry) and
            all(prior_rechecked[key]['every_archive_file_matches_held_extracted_source'] is True and
                prior_rechecked[key]['archive']['sha256'] ==
                    current_registry[key]['expected_lock_checksum'] ==
                    current_registry[key]['comparison']['archive']['sha256']
                for key in current_registry),
            'prepared vendor lost the original45 archive/source authority')
    fixed_vendor, fixed_archives = PREP_OUT/'vendor', PREP_OUT/'archives'
    require(manifest['schema'] == 1 and
            manifest['source'] == 'exact-crates-io-original-workspace-lock' and
            manifest['original_lock'] == {'bytes':51836,'sha256':
                'c1dfa6f13f789cf40435d0d72973d029d0e264b27bd833eabb5a727492127f62'} and
            manifest['vendor_root'] == str(fixed_vendor) and manifest['archive_root'] == str(fixed_archives) and
            manifest['registry_packages'] == 193 and manifest['metadata_or_compilation_executed'] is False,
            'actual prepared vendor uses a different root, phase or original lock')
    config = ('[source.crates-io]\nreplace-with = "pocket4-locked-vendor"\n\n'
              '[source.pocket4-locked-vendor]\ndirectory = '+json.dumps(str(fixed_vendor))+
              '\n\n[net]\noffline = true\n').encode()
    require(raw_inputs['prepared-vendor-config.toml'] == config and
            prior['source_config'] == manifest['source_config'],
            'explicit vendor source replacement differs')
    original_outputs = {}
    for input_name, field, path in [
        ('prepared-vendor-manifest.json','vendor_manifest',PREP_OUT/'vendor-manifest.json'),
        ('prepared-vendor-config.toml','source_config',PREP_OUT/'vendor-config.toml')]:
        before = prior[field]
        real_directory(path.parent)
        require(before['path'] == str(path) and before['bytes'] == VENDOR_BINDING[input_name]['bytes'] and
                before['sha256'] == VENDOR_BINDING[input_name]['sha256'] and
                hash_held(path,32*1024*1024) == before,
                'original prepared vendor metadata changed')
        original_outputs[str(path)] = before
    locked = {(row['name'],row['version']):row for row in original_lock['package'] if 'source' in row}
    records = manifest['packages']
    prepared = {(row['name'],row['version']):row for row in records}
    require(len(locked) == len(records) == len(prepared) == 193 and set(prepared) == set(locked),
            'prepared vendor does not contain exactly all locked registry packages')
    total_files,total_bytes,total_archives = 0,0,0
    for key in sorted(prepared):
        require(time.monotonic() < DEADLINE, 'complete vendor input qualification deadline exhausted')
        row,lock = prepared[key],locked[key]
        name,version = key
        require(re.fullmatch(r'[A-Za-z0-9_-]+',name) is not None and
                re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9_.+-]+)?',version) is not None and
                lock['source'] == 'registry+https://github.com/rust-lang/crates.io-index' and
                re.fullmatch(r'[0-9a-f]{64}',lock.get('checksum','')) is not None and
                row['package_checksum'] == lock['checksum'],
                'prepared package differs from original exact source/checksum')
        directory,archive = fixed_vendor/(name+'-'+version),fixed_archives/(name+'-'+version+'.crate')
        real_directory(directory)
        directory_st = directory.lstat()
        require(stat.S_ISDIR(directory_st.st_mode) and directory_st.st_uid == 1000 and
                directory_st.st_gid == 1000 and stat.S_IMODE(directory_st.st_mode) == 0o700 and
                row['directory'] == str(directory) and row['archive']['path'] == str(archive),
                'prepared package left its exact private root')
        archive_pin = hash_held(archive,32*1024*1024)
        require(archive_pin == row['archive'] and archive_pin['sha256'] == lock['checksum'],
                'prepared complete archive changed')
        inventory = regular_tree(directory,4096,64*1024*1024)
        require(inventory == row['files'] and '.cargo-checksum.json' in inventory and 'Cargo.toml' in inventory and
                len(inventory) == row['source_files']+1 and
                inventory['.cargo-checksum.json'] == row['checksum_metadata'] and
                all(value['path'] == str(directory/path) and
                    stat.S_IMODE(value['identity'][2]) in (0o444,0o555)
                    for path,value in inventory.items()),
                'complete archive-derived vendor file map changed')
        checksum_raw,checksum_pin = held(directory/'.cargo-checksum.json',1024*1024)
        expected_checksum = {'package':lock['checksum'],
            'files':{path:value['sha256'] for path,value in sorted(inventory.items())
                     if path != '.cargo-checksum.json'}}
        require(json.loads(checksum_raw) == expected_checksum and
                checksum_pin == row['checksum_metadata'],
                'Cargo source checksum metadata differs from every prepared original archive file')
        package_raw,package_pin = held(directory/'Cargo.toml',1024*1024)
        package = tomllib.loads(package_raw.decode('utf-8'))['package']
        require(package['name'] == name and package['version'] == version and
                package_pin == inventory['Cargo.toml'], 'prepared package manifest name/version differs')
        total_files += len(inventory)
        total_bytes += sum(value['bytes'] for value in inventory.values())
        total_archives += archive_pin['bytes']
        require(total_files <= 193*4096 and total_bytes <= 1024*1024*1024 and
                total_archives <= 512*1024*1024,
                'complete prepared registry exceeds original finite bounds')
        files = {str(archive):archive_pin,**{value['path']:value for value in inventory.values()}}
        cache[key] = {'checksum':lock['checksum'],'rows':inventory,'archive':archive_pin,'files':files,
                      'directory':str(directory),'source_inventory':prior['vendor_manifest']}
    require(total_files == prior['vendor_file_count'] and total_bytes == prior['vendor_source_bytes'] and
            total_archives == prior['archive_bytes'],
            'prepared full mapping totals differ')
    report['actual_vendor_preparation'] = {
        'result':staged_inputs['vendor-prep-result.json'],'original_manifest':prior['vendor_manifest'],
        'original_config':prior['source_config'],'registry_packages':193,
        'source_files':total_files,'source_bytes':total_bytes,'archive_bytes':total_archives,
        'all_current_archive_and_file_maps_equal_actual_preparation':True,
        'original45_authority_preserved':True,
        'source_copy_qualifies_no_Cargo_or_runtime_result':True}
    report['offline_vendor_input_gate_qualified'] = True
    collected = {value['path']:value for value in staged_inputs.values()}
    collected.update(original_outputs)
    for entry in cache.values():
        collected.update(entry['files'])
    return prepared,collected

