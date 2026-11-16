"""Original complete AudioService stream preservation parser, no input."""
import re

def require(value, reason):
    if not value:
        raise RuntimeError(reason)

def audio_streams(raw):
    values = {}
    lines = raw.splitlines()
    for index,line in enumerate(lines):
        if not re.match(r'^[ \t]*- STREAM_',line):
            continue
        # Actual AudioService dump: "- STREAM_SYSTEM (aliased to: STREAM_RING):".
        # Each stream block ends with its own blank line, before volume groups.
        match = re.fullmatch(r'[ \t]*- (STREAM_[A-Z0-9_]+)(?: \(aliased to: (STREAM_[A-Z0-9_]+)\))?:',line)
        require(match is not None, 'AUDIO_STREAM_HEADER_UNRECOGNIZED')
        fields = []
        for child in lines[index+1:]:
            if not child.strip():
                break
            require(child.startswith('   '), 'AUDIO_STREAM_BOUNDARY_CHANGED')
            if re.match(r'^\s*(Muted(?: Internally)?|Min|Max|streamVolume|Current):',child):
                fields.append(child.strip())
        require(match[1] not in values, 'AUDIO_STREAM_DUPLICATE')
        values[match[1]] = {'alias':match[2],'fields':fields}
    require({'STREAM_ALARM','STREAM_RING','STREAM_MUSIC','STREAM_NOTIFICATION'} <= set(values),
            'ACTUAL_SOUND_STREAMS_NOT_OBSERVED')
    for item in values.values():
        fields = item['fields']
        require(all(sum(line.startswith(key + ':') for line in fields) == 1
                    for key in ('Muted','Muted Internally','Min','Max','Current'))
            and sum(line.startswith('streamVolume:') for line in fields) <= 1,
                'AUDIO_VOLUME_FIELDS_AMBIGUOUS')
    return values
