from pathlib import Path
import copy, hashlib, importlib.util, itertools, json, os, stat, tempfile, time, unittest

ROOT = Path(__file__).resolve().parent

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

core = module('apex_transition', ROOT/'apex_test_transition.py')
book = module('source_bookends', ROOT/'base-support/vendor_source_bookends_text_auto_9907.py')
partial = module('apex_partial', ROOT/'apex_test_partial.py')

def manifest(name):
    directory = ROOT.parent/'p4_vendor_apex_source_fix'
    path = directory/('base' if name == 'lint' else 'candidate')/'android/manifest'/(
        'production-full-lint-source-lock.json' if name == 'lint'
        else 'production-full-apex-tests-source-lock.json')
    raw = path.read_bytes()
    lock = json.loads(raw)
    return {
        'schema_version':1, 'source_lock_sha256':hashlib.sha256(raw).hexdigest(),
        'plan':{
            'schema_version':1, 'superproject_commit':lock['superproject']['commit'],
            'projects':[{
                'path':p['path'], 'url':lock['remote_base']+p['name'],
                'commit':p['commit'], 'purpose':p['purpose'], 'sparse_paths':p.get('sparse_paths',[]),
            } for p in lock['projects']],
            'links':lock['links'], 'unrestricted_repo_sync':False,
        },
    }

OLD, NEW = manifest('lint'), manifest('apex')

def absent(key):
    oid, _, _ = core.CANDIDATES[key]
    return {'project':key[0], 'path':key[1], 'git_mode':'100644',
            'git_blob':oid, 'present':False, 'sparse_skip':True, 'f9':None}

def present(key):
    oid, size, sha = core.CANDIDATES[key]
    return {'project':key[0], 'path':key[1], 'git_mode':'100644', 'git_blob':oid,
            'present':True, 'bytes':size, 'sha256':sha, 'mode':0o644,
            'f9':[1,2,stat.S_IFREG|0o644,1000,1000,1,size,100,100]}

class TransitionTests(unittest.TestCase):
    def test_exact_profile_and_each_provider_delta(self):
        a, b = core.validate_profiles(book, OLD, NEW)
        self.assertEqual(a, OLD)
        self.assertEqual(b, NEW)
        for provider in core.PROVIDERS:
            bad = copy.deepcopy(NEW)
            p = next(x for x in bad['plan']['projects'] if x['path'] == provider)
            p['sparse_paths'][-1] += '/Android.bp'
            with self.assertRaises(RuntimeError):
                core.validate_profiles(book, OLD, bad)

    def test_profile_metadata_and_scope_rejections(self):
        for mutation in range(8):
            bad = copy.deepcopy(NEW)
            if mutation == 0: bad['source_lock_sha256'] = '0'*64
            elif mutation == 1: bad['plan']['projects'][0]['commit'] = '0'*40
            elif mutation == 2: bad['plan']['projects'].reverse()
            elif mutation == 3: bad['plan']['links'].pop()
            elif mutation == 4: bad['plan']['unrestricted_repo_sync'] = True
            elif mutation == 5: bad['plan']['projects'][0]['sparse_paths'].append('outside')
            elif mutation == 6: bad['schema_version'] = True
            else: bad['plan']['projects'][0]['purpose'] = 'changed'
            with self.assertRaises(RuntimeError, msg=str(mutation)):
                core.validate_profiles(book, OLD, bad)

    def test_all_sixteen_partial_masks_and_exact_complete_path(self):
        keys = sorted(core.CANDIDATES)
        before = [absent(k) for k in keys]
        for mask in range(16):
            after = [present(k) if mask & (1 << n) else absent(k) for n,k in enumerate(keys)]
            result = core.compare_rows(before, after, allow_partial=True, expected_count=4)
            self.assertEqual(result['provider_materialized'], mask.bit_count())
            self.assertFalse(result['source_recovery_complete'])
            self.assertFalse(result['Vendor_build_credit'])
            if mask == 15:
                complete = core.compare_rows(before, after, allow_partial=False, expected_count=4)
                self.assertEqual(complete['provider_raw_bytes_materialized'], 2186)
                self.assertFalse(complete['partial_recovery_admission_only'])
            else:
                with self.assertRaises(RuntimeError):
                    core.compare_rows(before, after, allow_partial=False, expected_count=4)

    def test_fixed_raw_candidate_bytes_mode_identity_and_types(self):
        for key in core.CANDIDATES:
            for mutation in range(11):
                row = present(key)
                if mutation == 0: row['git_blob'] = '0'*40
                elif mutation == 1: row['sha256'] = '0'*64
                elif mutation == 2: row['bytes'] = True
                elif mutation == 3: row['bytes'] += 1
                elif mutation == 4: row['mode'] = 0o755
                elif mutation == 5: row['f9'][2] = stat.S_IFREG|0o755
                elif mutation == 6: row['f9'][3] = 0
                elif mutation == 7: row['f9'][5] = 2
                elif mutation == 8: row['f9'][0] = True
                elif mutation == 9: row['project'] = 'foreign'
                else: row['extra'] = 'unreviewed'
                with self.assertRaises(RuntimeError, msg=str((key,mutation))):
                    core._candidate(row, key, True)
            row = absent(key); row['sparse_skip'] = False
            with self.assertRaises(RuntimeError):
                core._candidate(row, key, True)

    def test_initial_candidate_presence_and_unrelated_changes_rejected(self):
        keys = sorted(core.CANDIDATES)
        before, after = [absent(k) for k in keys], [present(k) for k in keys]
        for bad in [before[:-1], before+[before[0]], list(reversed(before))]:
            with self.assertRaises(RuntimeError):
                core.compare_rows(bad, after, allow_partial=False, expected_count=4)
        bad = copy.deepcopy(before); bad[0] = present(keys[0])
        with self.assertRaises(RuntimeError):
            core.compare_rows(bad, after, allow_partial=False, expected_count=4)
        other = {'project':'unrelated', 'path':'file', 'present':False,
                 'sparse_skip':True, 'git_mode':'100644','git_blob':'2'*40,'f9':None}
        changed = dict(other); changed['git_blob'] = '3'*40
        with self.assertRaises(RuntimeError):
            core.compare_rows(before+[other],after+[changed],allow_partial=False,expected_count=5)
        for partial_flag, count in [(1,4),(False,True),(False,3)]:
            with self.assertRaises(RuntimeError):
                core.compare_rows(before,after,allow_partial=partial_flag,expected_count=count)

    def test_both_streams_close_on_early_failure(self):
        closed = []
        def stream(label, row):
            try: yield row
            finally: closed.append(label)
        key = next(iter(core.CANDIDATES))
        bad = present(key); bad['sha256'] = '0'*64
        with self.assertRaises(RuntimeError):
            core.compare_rows(stream('before',absent(key)),stream('after',bad),
                              allow_partial=False,expected_count=4)
        self.assertEqual(sorted(closed),['after','before'])

    def test_recovery_dispatch_and_single_resume_matrix(self):
        for new_state, intent, vendor, resumed in itertools.product([False,True],repeat=4):
            actual = NEW if new_state else OLD
            accepted = (intent and new_state) or (not new_state and not vendor and not resumed)
            if vendor and not intent: accepted = False
            if resumed and not intent: accepted = False
            if accepted:
                value = core.recovery_branch(book,actual,OLD,NEW,intent,vendor,resumed)
                self.assertIsInstance(value,str)
            else:
                with self.assertRaises(RuntimeError):
                    core.recovery_branch(book,actual,OLD,NEW,intent,vendor,resumed)
        for flags in [(1,False,False),(False,0,False),(False,False,1)]:
            with self.assertRaises(RuntimeError):
                core.recovery_branch(book,OLD,OLD,NEW,*flags)

    def test_both_projects_have_independent_partial_cone_states(self):
        names = sorted(core.PROVIDERS)
        for choices in itertools.product(['old','new'],repeat=2):
            states = dict(zip(names,choices))
            obj = core.VerifiedPartialInventory(
                book,{'actual_provider_cone_profiles':states},OLD,NEW,time.monotonic()+10,lambda:None)
            for p in obj.projects:
                if p['path'] in states:
                    expected = NEW if states[p['path']] == 'new' else OLD
                    self.assertEqual(p,next(x for x in expected['plan']['projects'] if x['path']==p['path']))
        for states in [{}, {names[0]:'old',names[1]:'unknown'},
                       {names[0]:'old',names[1]:'new','foreign':'old'}]:
            with self.assertRaises(RuntimeError):
                core.VerifiedPartialInventory(
                    book,{'actual_provider_cone_profiles':states},OLD,NEW,time.monotonic()+10,lambda:None)

    def test_unchanged_inventory_reader_hashes_real_fixture_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'inventory.ndjson'
            project = copy.deepcopy(OLD['plan']['projects'][0])
            row = {'project':project['path'],'path':'fixture','present':False,'sparse_skip':True,
                   'git_mode':'100644','git_blob':'a'*40,'f9':None}
            raw = {k:v for k,v in row.items() if k not in ('project','f9')}
            path.write_bytes(book.encoded(row))
            stable = {'project':project,'tree':'b'*40,'tracked_entries':1,'materialized_entries':0,
                      'materialized_bytes':0,'sparse_absent_entries':1,
                      'body_sha256':hashlib.sha256(book.encoded(raw)).hexdigest()}
            summary = {'schema':'pocket4-original-materialized-source-content-bookend-v1',
                       'all_actual_Git_blob_reads_verified':True,'source_mutations':False,
                       'project_count':1,'projects':[stable],
                       'inventory':partial.fingerprint(path),
                       'content_sha256':hashlib.sha256(book.encoded(stable)).hexdigest(),
                       'materialized_entries':0,'materialized_bytes':0,'sparse_absent_entries':1}
            reader = core.VerifiedInventory(book,summary,[project],time.monotonic()+10,lambda:None)
            self.assertEqual(list(reader),[row]);self.assertTrue(reader.completed)
            path.write_bytes(path.read_bytes().replace(b'fixture',b'changed'))
            reader = core.VerifiedInventory(book,summary,[project],time.monotonic()+10,lambda:None)
            with self.assertRaises(RuntimeError):
                list(reader)
            self.assertFalse(reader.completed)

if __name__ == '__main__':
    unittest.main(verbosity=2)
