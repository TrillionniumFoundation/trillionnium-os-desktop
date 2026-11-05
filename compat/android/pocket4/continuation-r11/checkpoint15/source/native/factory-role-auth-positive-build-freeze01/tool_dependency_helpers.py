def pin_tool(path):
    original=Path(path);resolved=original.resolve(strict=True)
    require(any(resolved.is_relative_to(root) for root in [Path('/usr/bin'),Path('/usr/lib'),Path('/usr/libexec/gcc')]),
            'tool/library outside fixed system roots: '+str(resolved))
    row=hash_held(resolved,128*1024*1024)
    row.update({'requested_path':str(original),'resolved_path':str(resolved)})
    require(original.resolve(strict=True)==resolved,'tool resolution changed')
    return row

def dependency_files(raw):
    text=raw.decode().replace(chr(92)+chr(10),' ')
    require(text.startswith('CONTROL:') and text.count('CONTROL:')==1,'unexpected compiler dependency format')
    words=shlex.split(text[len('CONTROL:'):]);require(0<len(words)<=1024,'compiler dependency bound exceeded')
    rows={}
    for name in words:
        requested=Path(os.path.abspath(str(SOURCE/name))) if not Path(name).is_absolute() else Path(name)
        resolved=requested.resolve(strict=True)
        require(any(resolved.is_relative_to(p) for p in [SOURCE,Path('/usr/include'),Path('/usr/lib/gcc')]),
                'compiler header escaped staged source/system include roots: '+str(resolved))
        row=hash_held(resolved,16*1024*1024)
        row.update({'requested_path':str(requested),'resolved_path':str(resolved)})
        rows[str(requested)]=row
    return rows
