"""Pure, narrow extension for the exact observed legacy aapt feature-group form.

The original S39 diagnostic function and execution result remain unchanged.
The caller supplies that original function; no Android or host program is run.
"""
import re


def feature_group_diagnostics(original, kind, raw, stderr):
    result = original(kind, raw, stderr)
    accepted = []
    if kind == 'badging':
        lines = raw.decode('utf-8', 'strict').splitlines()
        group_line = None
        group_has_feature = False
        main_seen = False
        for number, line in enumerate(lines, 1):
            if re.fullmatch(r"feature-group: label='[^'\r\n]*'", line):
                group_line = number
                group_has_feature = False
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
            # Whitespace, malformed rows and any other token end this contiguous
            # block. Their original unrecognized/diagnostic entries remain.
            group_line = None
            group_has_feature = False
        accepted_keys = {(row['line_number'], row['raw_line']) for row in accepted}
        result['unrecognized_badging_lines'] = [row for row in result['unrecognized_badging_lines']
            if (row['line_number'], row['raw_line']) not in accepted_keys]
    result['recognized_feature_group_extension_rows'] = accepted
    result['healthy_output_shape'] = (not result['stderr_nonempty'] and
        not result['stdout_diagnostic_lines'] and not result['unrecognized_badging_lines'])
    result['raw_lines_preserved'] = True
    result['new_remote_execution'] = False
    return result
