def absent_pc_directory(requested):
    # A default search entry is not a promise that the directory exists.
    # Bind the nearest existing protected ancestor and prove its first missing
    # child absent through that held directory. No provider or fallback is made.
    path = Path(requested)
    anchor = None
    for candidate in path.parents:
        try:
            candidate.lstat()
        except FileNotFoundError:
            continue
        anchor = candidate
        break
    require(anchor is not None, 'missing pkg-config path has no existing ancestor')
    resolved = anchor.resolve(strict=True)
    require(resolved == Path('/usr') or resolved.is_relative_to(Path('/usr')) or
            resolved == Path('/lib') or resolved.is_relative_to(Path('/lib')),
            'missing pkg-config path ancestor escaped fixed public host roots')
    real_directory(resolved)
    named_ancestors, real_ancestors = [], []
    for parent in (anchor,*anchor.parents):
        st = parent.lstat()
        require(st.st_uid == 0 and
                (stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode)),
                'missing pkg-config path ancestor has wrong type/owner')
        named_ancestors.append({'path':str(parent),'identity':identity(st),
                                'resolved_path':str(parent.resolve(strict=True))})
    for parent in (resolved,*resolved.parents):
        st = parent.lstat()
        require(stat.S_ISDIR(st.st_mode) and st.st_uid == 0 and
                not stat.S_IMODE(st.st_mode)&0o022,
                'missing pkg-config path real ancestor is not protected')
        real_ancestors.append({'path':str(parent),'identity':identity(st)})
    missing_name = path.relative_to(anchor).parts[0]
    fd = -1
    first_error = None
    close_error = None
    result = None
    try:
        fd = os.open(resolved,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
        held_identity = identity(os.fstat(fd))
        require(held_identity == real_ancestors[0]['identity'],
                'missing pkg-config path ancestor changed before open')
        for observation in range(2):
            try:
                os.stat(missing_name,dir_fd=fd,follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise RuntimeError('pkg-config default entry appeared while proving absence: '+requested)
            for row in named_ancestors:
                current = Path(row['path'])
                require(identity(current.lstat()) == row['identity'] and
                        str(current.resolve(strict=True)) == row['resolved_path'],
                        'missing pkg-config path named ancestor changed')
            for row in real_ancestors:
                require(identity(Path(row['path']).lstat()) == row['identity'],
                        'missing pkg-config path real ancestor changed')
            require(identity(os.fstat(fd)) == held_identity and
                    anchor.resolve(strict=True) == resolved,
                    'missing pkg-config path held ancestor changed')
        result = {'requested_path':requested,'state':'ABSENT',
                  'first_absent_path':str(anchor/missing_name),
                  'resolved_anchor':str(resolved),'held_anchor_identity':held_identity,
                  'named_ancestors':named_ancestors,'real_ancestors':real_ancestors,
                  'absence_observations':2,'provider_qualified':False}
    except BaseException as error:
        first_error = error
    finally:
        if fd >= 0:
            value, fd = fd, -1
            try:
                os.close(value)
            except BaseException as error:
                close_error = error
    if first_error is not None:
        if close_error is not None:
            raise RuntimeError('pkg-config absence primary='+repr(first_error)+
                               '; held ancestor close='+repr(close_error)) from first_error
        raise first_error
    if close_error is not None:
        raise RuntimeError('pkg-config absent ancestor close failed: '+repr(close_error)) from close_error
    require(result is not None, 'pkg-config absence observation did not complete')
    result['held_anchor_fd_closed'] = True
    return result


