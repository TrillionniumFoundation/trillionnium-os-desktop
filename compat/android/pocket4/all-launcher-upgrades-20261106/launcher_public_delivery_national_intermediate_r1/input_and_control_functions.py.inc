def full_stat(st):
    return {key: getattr(st, key) for key in
            ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
             'st_size', 'st_mtime_ns', 'st_ctime_ns')}


def directory_identity(st):
    return {key: getattr(st, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid')}


class FixedPriorHTML:
    """Hold the sole pinned ordinary-owner input; no arbitrary-path argument."""
    def __init__(self, end, accounting):
        self.end, self.accounting = end, accounting
        self.owned, self.dirs = [], []
        self.fd = self.before = self.parent_fd = self.name = None
        try:
            parts = Path(INPUT['path']).parts
            need(parts[0] == '/' and len(parts) > 2 and all(x not in ('.', '..') for x in parts[1:]),
                 'FIXED_ABSOLUTE_INPUT_PATH')
            fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
            self.owned.append(fd)
            accounting['acquired'] += 1
            self.dirs.append({'fd': fd, 'parent': None, 'name': '/', 'before': full_stat(os.fstat(fd))})
            for part in parts[1:-1]:
                parent = fd
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)
                self.owned.append(fd)
                accounting['acquired'] += 1
                self.dirs.append({'fd': fd, 'parent': parent, 'name': part, 'before': full_stat(os.fstat(fd))})
            self.parent_fd, self.name = fd, parts[-1]
            parent_st = os.fstat(fd)
            need(parent_st.st_uid == INPUT['uid'] and parent_st.st_gid == INPUT['gid']
                 and stat.S_IMODE(parent_st.st_mode) == INPUT['parent_mode'], 'EXACT_PRIVATE_INPUT_PARENT')
            self.fd = os.open(self.name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=fd)
            self.owned.append(self.fd)
            accounting['acquired'] += 1
            st = os.fstat(self.fd)
            need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == INPUT['uid']
                 and st.st_gid == INPUT['gid'] and stat.S_IMODE(st.st_mode) == INPUT['mode']
                 and st.st_size == INPUT['bytes'], 'EXACT_PRIOR_HTML_REGULAR_OWNER_SIZE_MODE')
            self.before = full_stat(st)
            self.raw = self.recheck()
        except BaseException:
            self.close()
            raise

    def path_recheck(self):
        for row in self.dirs:
            st = os.fstat(row['fd'])
            need(stat.S_ISDIR(st.st_mode), 'HELD_INPUT_DIRECTORY_REQUIRED')
            saved = {k: row['before'][k] for k in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid')}
            need(directory_identity(st) == saved, 'HELD_INPUT_DIRECTORY_IDENTITY_CHANGED')
            named = (os.stat('/', follow_symlinks=False) if row['parent'] is None else
                     os.stat(row['name'], dir_fd=row['parent'], follow_symlinks=False))
            need(directory_identity(named) == saved, 'NAMED_INPUT_DIRECTORY_IDENTITY_CHANGED')
        need(full_stat(os.fstat(self.fd)) == self.before, 'HELD_PRIOR_HTML_STAT_CHANGED')
        need(full_stat(os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False)) == self.before,
             'NAMED_PRIOR_HTML_STAT_CHANGED')

    def recheck(self):
        need(time.monotonic() < self.end, 'PRIOR_HTML_READ_DEADLINE')
        self.path_recheck()
        chunks, offset, digest = [], 0, hashlib.sha256()
        while offset < INPUT['bytes']:
            need(time.monotonic() < self.end, 'PRIOR_HTML_READ_DEADLINE')
            part = os.pread(self.fd, min(65536, INPUT['bytes'] - offset), offset)
            need(bool(part), 'PRIOR_HTML_SHORT_READ')
            chunks.append(part)
            digest.update(part)
            offset += len(part)
        need(os.pread(self.fd, 1, offset) == b'' and digest.hexdigest() == INPUT['sha256'],
             'PRIOR_HTML_COMPLETE_BYTE_PIN_REQUIRED')
        self.path_recheck()
        return b''.join(chunks)

    def public_binding(self):
        return {'path': INPUT['path'], 'bytes': INPUT['bytes'], 'sha256': INPUT['sha256'],
                'file': self.before, 'held_directory_count': len(self.dirs),
                'directories': [{'name': x['name'], 'before_full_stat': x['before']} for x in self.dirs],
                'directory_stability_fields': ['st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid'],
                'file_stability_fields': list(self.before), 'read_only': True}

    def close(self):
        while self.owned:
            try:
                os.close(self.owned.pop())
                self.accounting['closed'] += 1
            except OSError as error:
                self.accounting['errors'].append({'errno': error.errno, 'operation': 'close_owned_input_fd'})


def public_response_headers(rows):
    """Do not persist or replay anonymous response cookie values."""
    result = []
    for name, value in rows:
        if name.casefold() in ('set-cookie', 'set-cookie2'):
            raw = value.encode('utf-8', 'strict')
            value = '[redacted value: bytes=' + str(len(raw)) + '; sha256=' + hashlib.sha256(raw).hexdigest() + ']'
        result.append((name, value))
    return result


def derive_exact_intermediate(raw):
    parser, title = parse_html(raw)
    selected = set()
    for row in parser.rows:
        if ' '.join(row['text'].split()).casefold() != 'free xapk download for android' or not row['href']:
            continue
        absolute = urllib.parse.urljoin(SOURCE_PAGE_URL, row['href'])
        normal_https_url(absolute)
        selected.add(absolute)
    need(selected == {INTERMEDIATE_URL}, 'ONE_ACTUAL_PINNED_LITERAL_INTERMEDIATE_REQUIRED')
    text = raw.decode('utf-8', 'strict')
    need(all(token in text for token in
             ('com.ehi.national.mobile', '6.16.0.9403',
              'a901bc4949fe241750cd7ea3fb5df690d00b21e217b2212be813bbd51e5a36bb')),
         'PRIOR_ACTUAL_METADATA_LITERALS_CHANGED')
    return {'source_title': title, 'literal_url': next(iter(selected)),
            'url_rederived_from_exact_prior_HTML': True, 'URL_inferred_or_synthesized': False}


def observe_intermediate_controls(raw):
    parser, title = parse_html(raw)
    rows = []
    for anchor in parser.rows:
        label = ' '.join(anchor['text'].split())
        if not anchor['href']:
            continue
        absolute = urllib.parse.urljoin(INTERMEDIATE_URL, anchor['href'])
        item = urllib.parse.urlsplit(absolute)
        if not (any(x in label.casefold() for x in ('download', 'xapk', 'apk'))
                or label.casefold() in ('here', 'click here')
                or item.path.casefold().endswith(('.apk', '.xapk'))):
            continue
        if item.scheme != 'https' or item.fragment:
            continue
        normal_https_url(absolute)
        need(len(rows) < 64 and len(label) <= 512, 'BOUNDED_INTERMEDIATE_CONTROLS')
        rows.append({'literal_label': label, 'literal_url': absolute, 'followed': False,
                     'referenced_file_identity': 'UNKNOWN_NOT_FETCHED'})
    return {'title': title, 'unfollowed_literal_controls': rows,
            'automatic_script_execution': False, 'binary_URL_qualified': False,
            'APK_or_XAPK_downloaded': False, 'store_installer_used': False,
            'unknown_or_empty_control_requires_original_HTML_review': True}
