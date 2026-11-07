"""Export immutable owned evidence after one completed phase; no unit action."""
from pathlib import Path, PurePosixPath
import datetime, hashlib, io, json, os, re, stat, sys, tarfile, traceback

P = Path
PROFILES = {'pressure':('p4-lmkd-relay-pressure-r11-04','06'), 'stale':('p4-lmkd-relay-stale-r11-03','07')}
SOURCE = 'bc996fe6c763b0270de97d85c0f7ace71fd3804ca432c49d79f05ec21edec9e5'
BUILD = '153c08dd7744149e0a1ff67f035d6a42cb218800521baca229f4950715076d46'

def need(value, message):
    if not value: raise RuntimeError(message)

def digest(raw): return hashlib.sha256(raw).hexdigest()

def read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_size <= 1048576, 'owned export file type/size bound')
        raw = stream.read(1048577); after = os.fstat(stream.fileno())
        need((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)
             and len(raw) == before.st_size, 'owned evidence changed while exporting')
        need(not raw.startswith(b'\x7fELF') and not raw.startswith(b'PK\x03\x04'), 'binary/package export forbidden')
        return raw

def put(path, raw, owner):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    os.chown(path, owner.st_uid, owner.st_gid)

def main():
    need(os.geteuid() == 0 and len(sys.argv) == 3 and sys.argv[1] in PROFILES, 'root export requires phase and expected coordinator result SHA')
    phase, pin = sys.argv[1:]; need(re.fullmatch('[0-9a-f]{64}', pin) is not None, 'external receipt pin required')
    stem, suffix = PROFILES[phase]
    root = P('/home/alex/work')/('pocket4-lmkd-pressure-r11-coordinator-'+suffix)
    state = P('/run')/stem; base = P('/home/alex/work/pocket4-lmkd-host-pressure-r11-source-10')
    result_path = root/('02-'+phase+'-once')/'result.json'; result_raw = read(result_path)
    need(digest(result_raw) == pin, 'actual coordinator result pin differs')
    result = json.loads(result_raw)
    need(result['phase'] == phase and result['unit'] == stem+'.service' and result['source_manifest_sha256'] == SOURCE
         and result['matching_build_receipt_sha256'] == BUILD, 'owned result source/phase/unit mismatch')
    payload = {}
    for directory in ['01-prepare','02-'+phase+'-once']:
        for path in sorted((root/directory).iterdir()):
            need(path.is_file() and not path.is_symlink(), 'unexpected coordinator export entry')
            payload['coordinator/'+directory+'/'+path.name] = read(path)
    for path in sorted((state/'evidence').iterdir()):
        need(path.is_file() and not path.is_symlink(), 'unexpected owned evidence entry')
        payload['evidence/'+path.name] = read(path)
    for name in ('unit.stdout','unit.stderr'):
        if (state/name).exists(): payload['unit/'+name] = read(state/name)
    for source, name, expected in [(base/'source-manifest.json','source/source-manifest.json',SOURCE),
                                   (base/'build-result.json','source/matching-build-result.json',BUILD)]:
        raw = read(source); need(digest(raw) == expected, 'source/build export pin changed'); payload[name] = raw
    need(payload['coordinator/02-'+phase+'-once/result.json'] == result_raw, 'result changed during export')
    for name, entry in result.get('retained_files',{}).items():
        raw = payload['evidence/'+name]
        need(len(raw) == entry['bytes'] and digest(raw) == entry['sha256'], 'retained evidence differs from completed coordinator receipt: '+name)
    need(sum(len(raw) for raw in payload.values()) < 8*1048576, 'owned export total bound')
    index = {name:{'bytes':len(raw),'sha256':digest(raw)} for name,raw in sorted(payload.items())}
    manifest = {'schema':1,'phase':phase,'exported_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'coordinator_result_sha256':pin,'source_manifest_sha256':SOURCE,'matching_build_receipt_sha256':BUILD,
                'files':index,'read_only_runtime_export':True,'unit_actions_performed':False,'installed_files_changed':False}
    manifest_raw = (json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode(); payload['export-manifest.json'] = manifest_raw
    out = P('/home/alex/work')/('pocket4-lmkd-pressure-r11-export-'+suffix)
    owner = P('/home/alex').stat(); need(owner.st_uid > 0, 'export destination owner must be the configured nonroot account')
    os.umask(0o077); out.mkdir(mode=0o700); os.chown(out,owner.st_uid,owner.st_gid)
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as archive:
        for name,raw in sorted(payload.items()):
            need(not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts, 'canonical archive member')
            member = tarfile.TarInfo(name); member.size=len(raw); member.mode=0o600; member.mtime=0
            archive.addfile(member,io.BytesIO(raw))
    archive_raw = stream.getvalue(); put(out/'owned-evidence.tar.gz',archive_raw,owner)
    put(out/'coordinator-result.json',result_raw,owner); put(out/'export-manifest.json',manifest_raw,owner)
    summary = {'ok':True,'phase':phase,'archive':str(out/'owned-evidence.tar.gz'),'archive_bytes':len(archive_raw),
               'archive_sha256':digest(archive_raw),'manifest_sha256':digest(manifest_raw),'payload_files':len(index),
               'coordinator_result':str(out/'coordinator-result.json'),'coordinator_result_sha256':pin,
               'phase_ok':result.get('ok'),'exact_owned_cleanup_verified':result.get('exact_owned_cleanup_verified'),
               'stale_relief_critical_qualified':result.get('stale_relief_critical_qualified'),
               'stale_critical_qualified':result.get('stale_critical_qualified'),
               'stale_test_scope':result.get('stale_test_scope'),'native_stale_drop_observed':result.get('native_stale_drop_observed'),
               'above_high_stale_zero_kill_verified':result.get('above_high_stale_zero_kill_verified')}
    put(out/'export-result.json',(json.dumps(summary,indent=2)+'\n').encode(),owner)
    print(json.dumps(summary),flush=True)

if __name__ == '__main__':
    try: main()
    except Exception as error:
        print(json.dumps({'ok':False,'error':type(error).__name__+': '+str(error),'traceback':traceback.format_exc()}),flush=True)
        raise SystemExit(1)
