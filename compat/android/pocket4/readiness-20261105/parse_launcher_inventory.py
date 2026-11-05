#!/usr/bin/env python3
"""Strictly reconcile saved query-activities --brief output; no device query.

The original conservative inventory remains immutable. Derivation fails on any
unknown/missing/duplicate row and cross-checks the original parsed components.
"""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import re
from update_matrix import need, read_json, sha, inventory_data


def parse_launchers(raw):
    need(len(raw) <= 65536 and raw.endswith(b'\n') and b'\r' not in raw,
         'bounded complete LF-terminated launcher output required')
    lines = raw.decode('utf-8', 'strict').splitlines()
    header = re.fullmatch(r'([1-9]\d*) activities found:', lines[0]) if lines else None
    need(header is not None, 'unknown launcher header')
    count = int(header[1])
    need(count <= 4096 and len(lines) == 1 + 3 * count, 'launcher header/block count differs')
    metadata = re.compile(r'    priority=(-?\d+) preferredOrder=(-?\d+) match=0x([0-9a-fA-F]+) '
                          r'specificIndex=(-?\d+) isDefault=(true|false)')
    component = re.compile(r'    ([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+/'
                           r'(?:\.[A-Za-z_$]|[A-Za-z_$])[A-Za-z0-9_.$]*)')
    components, records = [], []
    for index in range(count):
        head, meta, name = lines[1 + 3 * index:4 + 3 * index]
        need(head == '  Activity #' + str(index) + ':', 'launcher index missing, duplicated or reordered')
        fields, app = metadata.fullmatch(meta), component.fullmatch(name)
        need(fields is not None, 'unknown launcher metadata')
        need(app is not None, 'unknown launcher component')
        priority, preferred, match, specific = int(fields[1]), int(fields[2]), int(fields[3], 16), int(fields[4])
        need(all(-(2**31) <= v < 2**31 for v in (priority, preferred, specific))
             and 0 <= match < 2**32, 'launcher metadata integer out of range')
        components.append(app[1])
        records.append({'index': index, 'priority': priority, 'preferred_order': preferred,
                        'match': match, 'specific_index': specific, 'is_default': fields[5] == 'true'})
    need(len(components) == len(set(components)), 'duplicate launcher component')
    return components, records, [line for index, line in enumerate(lines) if index == 0 or index % 3 != 0]


def derive(original, original_pin, raw, raw_pin, parser_pin):
    need(original.get('all_package_manager_queries_succeeded') is True
         and original.get('read_only') is True, 'original query receipt did not succeed')
    need(original.get('complete_launcher_parsing') is False
         and original.get('complete_package_manager_inventory') is False,
         'retain the original conservative false flags')
    components, records, metadata_lines = parse_launchers(raw)
    need(components == original['launcher_components'], 'raw components differ from original receipt')
    need(metadata_lines == original['unparsed_launcher_rows'], 'original unparsed rows differ from saved raw output')
    need(sorted({x.split('/')[0] for x in components}) == original['launcher_packages'],
         'raw launcher package coverage differs')
    need(original['launcher_component_count'] == len(components), 'original component count differs')
    result = copy.deepcopy(original)
    result.update(schema='pocket4-held-launcher-inventory-derived-v1', complete_launcher_parsing=True,
                  complete_package_manager_inventory=True, complete_package_manager_queries=True,
                  unparsed_launcher_rows=[])
    result['derivation'] = {
        'source_inventory': original_pin, 'source_launcher_stdout': raw_pin, 'parser': parser_pin,
        'original_complete_launcher_parsing': False, 'original_complete_package_manager_inventory': False,
        'original_unparsed_row_count': len(metadata_lines), 'all_raw_rows_consumed': True,
        'header_count_and_contiguous_indices_verified': True, 'metadata_grammar_verified': True,
        'unique_components_verified': True, 'original_components_and_packages_equal': True,
        'is_default_counts': dict(Counter(str(row['is_default']).lower() for row in records)),
        'metadata_records': records, 'device_queries': 0, 'UI_actions': 0,
        'whole_app_readiness_inferred': False}
    inventory_data(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', required=True, type=Path)
    parser.add_argument('--original-sha256', required=True)
    parser.add_argument('--launchers', required=True, type=Path)
    parser.add_argument('--launchers-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    original, pin = read_json(args.original)
    raw = args.launchers.read_bytes()
    need(pin['sha256'] == args.original_sha256 and sha(raw) == args.launchers_sha256, 'input hash differs')
    raw_pin = {'file': args.launchers.name, 'bytes': len(raw), 'sha256': sha(raw)}
    self_raw = Path(__file__).read_bytes()
    self_pin = {'file': Path(__file__).name, 'bytes': len(self_raw), 'sha256': sha(self_raw)}
    result = derive(original, pin, raw, raw_pin, self_pin)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'complete_package_manager_inventory': True,
                      'installed_package_count': result['installed_package_count'],
                      'launcher_package_count': result['launcher_package_count'],
                      'third_party_package_count': len(result['third_party_packages']),
                      'output_sha256': sha(args.output.read_bytes()), 'device_queries': 0}))


if __name__ == '__main__':
    main()
