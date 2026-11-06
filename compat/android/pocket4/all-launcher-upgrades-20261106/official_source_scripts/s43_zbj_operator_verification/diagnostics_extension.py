"""Pure legacy aapt extension for three actual S42 forms and their contexts.

Official Command.cpp output branches are recorded in primary/source-rules.json.
Unknown, malformed, misplaced, duplicate and diagnostic rows remain failures.
"""
import re


def feature_group_diagnostics(original, kind, raw, stderr):
    result = original(kind, raw, stderr)
    accepted = []
    if kind == 'badging':
        lines = raw.decode('utf-8', 'strict').splitlines()
        group_line = None
        group_has_feature = False
        group_gl_seen = False
        main_seen = False
        install_seen = False
        width_seen = False
        for number, line in enumerate(lines, 1):
            install = re.fullmatch(r"install-location:'(auto|internalOnly|preferExternal)'", line)
            width = re.fullmatch(r"requires-smallest-width:'([1-9][0-9]{0,9})'", line)
            previous = lines[number - 2] if number > 1 else None
            if install and not install_seen and previous is not None and previous.startswith('package: '):
                accepted.append({'line_number': number, 'raw_line': line, 'tag': 'install-location',
                                 'value': install[1], 'package_row': number - 1})
                install_seen = True
            elif width and not width_seen and int(width[1]) <= 2147483647 and previous in (
                    "supports-any-density: 'true'", "supports-any-density: 'false'"):
                accepted.append({'line_number': number, 'raw_line': line, 'tag': 'requires-smallest-width',
                                 'value_dp': int(width[1]), 'density_row': number - 1})
                width_seen = True
            if re.fullmatch(r"feature-group: label='[^'\r\n]*'", line):
                group_line = number
                group_has_feature = False
                group_gl_seen = False
                continue
            gl = re.fullmatch(r"  uses-gl-es: '0x([1-9a-f][0-9a-f]{0,7})'", line)
            if group_line is not None and gl and not group_has_feature and not group_gl_seen and int(gl[1], 16) <= 2147483647:
                accepted.append({'line_number': number, 'raw_line': line, 'feature_group_line': group_line,
                                 'tag': 'uses-gl-es', 'value_hex': '0x' + gl[1]})
                group_gl_seen = True
                continue
            feature = re.fullmatch(
                r"  (uses-feature|uses-feature-not-required): name='([A-Za-z_][A-Za-z0-9_.]*)'", line)
            implied = re.fullmatch(
                r"  uses-implied-feature: name='([A-Za-z_][A-Za-z0-9_.]*)' reason='([^'\r\n]+)'", line)
            if group_line is not None and (feature or implied):
                row = {'line_number': number, 'raw_line': line, 'feature_group_line': group_line}
                if feature:
                    row.update(tag=feature[1], name=feature[2])
                else:
                    row.update(tag='uses-implied-feature', name=implied[1], reason=implied[2])
                accepted.append(row)
                group_has_feature = True
                continue
            if line == 'main' and group_line is not None and group_has_feature and not main_seen:
                accepted.append({'line_number': number, 'raw_line': line,
                    'tag': 'legacy_bare_main_marker', 'feature_group_line': group_line,
                    'launchable_component_inferred': False})
                main_seen = True
            # An unrecognized or misplaced row ends the contiguous group.
            # Its original diagnostic/unrecognized record is never discarded.
            group_line = None
            group_has_feature = False
            group_gl_seen = False
        accepted_keys = {(row['line_number'], row['raw_line']) for row in accepted}
        result['unrecognized_badging_lines'] = [row for row in result['unrecognized_badging_lines']
            if (row['line_number'], row['raw_line']) not in accepted_keys]
    result['recognized_feature_group_extension_rows'] = accepted
    result['healthy_output_shape'] = (not result['stderr_nonempty'] and
        not result['stdout_diagnostic_lines'] and not result['unrecognized_badging_lines'])
    result['raw_lines_preserved'] = True
    result['parser_itself_executes_no_commands'] = True
    return result
