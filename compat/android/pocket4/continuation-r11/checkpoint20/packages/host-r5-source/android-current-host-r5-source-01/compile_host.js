/* Pure source compiler. No filesystem/network/process/device/ref API.
 * Only compileActual exports source bundles; it requires complete actual raw
 * baseline and qualification receipts plus externally verified original pins.
 */
function createCurrentHostForkCompiler(h) {
  "use strict";
  const need=(v,c)=>{if(!v)throw Error(c);};
  const digest=s=>{need(typeof s==="string","EXACT_UTF8_STRING_REQUIRED");return h.sha(s);};
  const size=s=>h.utf8(s).length;
  const shaPattern=/^[0-9a-f]{64}$/;
  const oldEpoch="48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f";
  const schema="pocket4-main-current-baseline-v1";
  const expectedBaselineSource="9bc710444bff9d90cb3375fd5acb155e0438e2a71a65348b23d4483cf81d00f9";
  const oldHostManifest="52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1";
  const oldCoordinator="e2769eeeae2d620456a67959dfaff3b07545f2352cd9a60692450451004c39fd";
  const specs={
    bili:{old:8,next:9,target:"tv.danmaku.bili",manifest:"8e3454bcc9ebe1ff55dcaf62706ce1176cfa1d0f0ede7099cbbfa46f4ad53f1e"},
    ihg:{old:1,next:2,target:"com.ihg.apps.android",manifest:"ab971f5b361f1d97b8036c954a6b88734b7faedbeed6349b873ead85fa79d5f3"},
    amazon:{old:2,next:3,target:"com.amazon.mShop.android.shopping",manifest:"32be752c72fc4cfe7f50a73bba54cd6444e9ed3990b4f0cd809cb7023b540b98"},
    bestbuy:{old:2,next:3,target:"com.bestbuy.android",manifest:"f7f13e75bf38518581581a2851714a3bb67a169dddeec1d444de2150398f01f9"}
  };
  const exactPin=(raw,pin)=>{
    need(pin&&Number.isSafeInteger(pin.bytes)&&pin.bytes>0&&shaPattern.test(pin.sha256),"EXTERNAL_RAW_PIN_REQUIRED");
    need(size(raw)===pin.bytes&&digest(raw)===pin.sha256,"EXTERNAL_RAW_PIN_MISMATCH");
    return JSON.parse(raw);
  };
  const pin=raw=>({bytes:size(raw),sha256:digest(raw)});
  const fdClosed=row=>row&&Number.isSafeInteger(row.acquired)&&row.acquired>0&&
    row.acquired===row.close_attempts&&row.acquired===row.closed&&row.remaining===0&&
    Array.isArray(row.errors)&&row.errors.length===0;
  function actualBinding(input) {
    need(input&&Object.keys(input).sort().join(",")==="current_guard_raw,qualification_raw,result_pin,result_raw","EXACT_ACTUAL_INPUT_SET");
    const r=exactPin(input.result_raw,input.result_pin);
    need(r.schema==="pocket4-main-current-baseline-result-v1"&&r.ok===true&&r.identity_qualified===true&&
      r.error===null&&Array.isArray(r.secondary_errors)&&r.secondary_errors.length===0&&
      r.final_fixed_identity_equal===true&&r.historical_inputs_and_boot_unchanged===true,
      "ACTUAL_COMPLETE_BASELINE_RESULT_REQUIRED");
    need(r.source_manifest_sha256===expectedBaselineSource&&r.source_basis.runtime_R4_manifest_sha256===oldHostManifest,
      "EXACT_REVIEWED_BASELINE_SOURCE_REQUIRED");
    need(r.namespace_entry===false&&r.deployment_performed===false&&r.automatic_retry===false&&
      r.old_epoch_reauthorized===false&&r.framework_exit_cause_resolved===false&&r.whole_app_production_ready===false&&
      ["Android_commands","UI_actions","App_launches","helper_installs"].every(k=>r[k]===0),
      "BASELINE_SCOPE_OR_PRODUCTION_BOUNDARY_CHANGED");
    need(fdClosed(r.observation_fds)&&fdClosed(r.publication_fds),"ACTUAL_BASELINE_FDS_NOT_CLOSED");
    need(r.controls&&r.controls.all_passed===true&&r.controls.count===32&&r.controls.cases.length===32&&
      r.controls.cases.every(c=>c.passed===true)&&new Set(r.controls.cases.map(c=>c.name)).size===32&&
      r.controls.compiled_sources.length===7&&r.controls.guard_template_values_are_syntax_only===true,
      "ACTUAL_BASELINE_CONTROLS_REQUIRED");
    need(r.double_sample_count===3&&Number.isSafeInteger(r.explicit_observation_span_ns)&&
      r.explicit_observation_span_ns>=10000000000&&r.explicit_observation_span_ns<=90000000000,
      "ACTUAL_BOUNDED_IDENTITY_OBSERVATION_REQUIRED");
    need(shaPattern.test(r.new_epoch_sha256)&&r.new_epoch_sha256!==oldEpoch,"NEW_ACTUAL_EPOCH_REQUIRED");
    const q=exactPin(input.qualification_raw,r.qualification);
    need(q.schema==="pocket4-main-current-baseline-qualification-v1"&&q.identity_qualified===true&&
      q.epoch_sha256===r.new_epoch_sha256&&q.source_manifest_sha256===expectedBaselineSource&&
      q.historical_deployment_revalidated===true&&q.new_deployment_performed===false&&q.old_epoch_reauthorized===false&&
      q.three_double_samples_equal===true&&q.final_seven_role_identity_equal===true&&
      q.all_owned_service_children_joined===true&&q.framework_exit_cause_resolved===false&&
      q.production_ready===false&&q.UI_or_install_runtime_admitted===false&&
      JSON.stringify(q.baseline)===JSON.stringify(r.baseline)&&fdClosed(q.observation_fds),
      "ACTUAL_QUALIFICATION_PARENT_BINDING_REQUIRED");
    need(r.baseline.path==="/home/alex/work/pocket4-main-current-baseline-01/baseline.private.json"&&
      r.qualification.path==="/home/alex/work/pocket4-main-current-baseline-01/qualification.json"&&
      r.generated_current_guard.path==="/home/alex/work/pocket4-main-current-baseline-01/current_baseline_guard.py"&&
      shaPattern.test(r.baseline.sha256),"FIXED_CURRENT_BASELINE_OUTPUT_PATHS_REQUIRED");
    need(size(input.current_guard_raw)===r.generated_current_guard.bytes&&
      digest(input.current_guard_raw)===r.generated_current_guard.sha256,"ACTUAL_GENERATED_GUARD_PIN_REQUIRED");
    const g=input.current_guard_raw;
    for(const s of [
      'BASELINE_SHA="'+r.baseline.sha256+'"','QUALIFICATION_SHA="'+r.qualification.sha256+'"',
      'MAIN_EPOCH="'+r.new_epoch_sha256+'"','SOURCE_MANIFEST_SHA="'+expectedBaselineSource+'"',
      'BASELINE_BYTES='+r.baseline.bytes,'QUALIFICATION_BYTES='+r.qualification.bytes])
      need(g.split(s).length===2,"ACTUAL_GUARD_LITERAL_MISMATCH");
    need(!g.includes("@@"),"UNBOUND_CURRENT_GUARD_TEMPLATE");
    const uids=r.selected_package_uids;
    const packages=[...Object.values(specs).map(x=>x.target),"local.pocket4.actions.v2"];
    need(uids&&Object.keys(uids).sort().join(",")===packages.sort().join(",")&&
      Object.values(uids).every(v=>Number.isSafeInteger(v)&&v>=10000&&v<100000)&&
      new Set(Object.values(uids)).size===5,"ACTUAL_SELECTED_UID_SET_REQUIRED");
    return {epoch:r.new_epoch_sha256,baseline:r.baseline,qualification:r.qualification,
      guard:r.generated_current_guard,result:input.result_pin,guard_raw:g,uids,
      unresolved_framework_exit_cause:true,helper_installed_uid:null,APK_sha256:null,signer_sha256:null};
  }
  function checkOld(raw,files,wantedManifest) {
    need(digest(raw)===wantedManifest,"FROZEN_PARENT_MANIFEST_CHANGED");
    const m=JSON.parse(raw);
    need(m.files&&typeof files==="object"&&!Array.isArray(files),"FROZEN_PARENT_SOURCE_SET");
    for(const[name,text]of Object.entries(files)){
      need(m.files[name]&&size(text)===m.files[name].bytes&&digest(text)===m.files[name].sha256,
        "FROZEN_PARENT_SOURCE_CHANGED:"+name);
    }
    return m;
  }
  function editor(original,name) {
    let text=original;const edits=[];
    return {get text(){return text;},edits,
      one(a,b){need(a!==b&&text.split(a).length===2,"EXACT_SINGLE_PATCH_SITE:"+name);text=text.replace(a,b);edits.push({old:a,next:b,count:1});},
      all(a,b){if(a===b)return;const n=text.split(a).length-1;if(!n)return;text=text.split(a).join(b);edits.push({old:a,next:b,count:n});},
      inverse(){let r=text;for(const e of [...edits].reverse()){need(r.split(e.next).length-1===e.count,"PATCH_INVERSE_SITE_COLLISION:"+name);r=r.split(e.next).join(e.old);}need(r===original,"PATCH_INVERSE_NOT_EXACT:"+name);return true;}}
  }

const NEW_SCOPE="def verify_scope(scope, activation, contract):\n    require(scope.get(\"schema\") == \"pocket4-current-recorder-scope-v1\" and\n            scope.get(\"current_baseline_schema\") == BASELINE_SCHEMA and\n            scope.get(\"package\") == PACKAGE and scope.get(\"component\") == COMPONENT and\n            type(scope.get(\"uid\")) is int and scope[\"uid\"] == UID and\n            type(scope.get(\"user\")) is int and scope[\"user\"] == 0 and\n            scope.get(\"automatic_retry\") is False,\n            \"CURRENT_BILIBILI_SCOPE_REQUIRED\")\n    require(activation.get(\"schema\") == BASELINE_SCHEMA and\n            activation.get(\"kind\") == \"current-framework-generation\" and\n            \"main_deployed\" not in activation and activation.get(\"deployment_performed\") is False and\n            scope.get(\"epoch_sha256\") == MAIN_EPOCH and\n            activation[\"framework_epoch\"][\"sha256\"] == MAIN_EPOCH and\n            scope.get(\"current_baseline_sha256\") == BASELINE_SHA and\n            scope.get(\"current_baseline_qualification_sha256\") == BASELINE_QUALIFICATION_SHA and\n            scope.get(\"historical_activation_sha256\") == HISTORICAL_ACTIVATION_SHA and\n            scope.get(\"historical_verified_sha256\") == HISTORICAL_VERIFIED_SHA and\n            \"activation_sha256\" not in scope and \"verified_sha256\" not in scope,\n            \"CURRENT_BASELINE_AND_SEPARATE_HISTORY_REQUIRED\")\n    history = activation.get(\"historical_deployment\", {})\n    require(history.get(\"activation_sha256\") == HISTORICAL_ACTIVATION_SHA and\n            history.get(\"verification_sha256\") == HISTORICAL_VERIFIED_SHA and\n            activation.get(\"framework_exit_cause_resolved\") is False and\n            activation.get(\"whole_app_production_ready\") is False,\n            \"HISTORICAL_LINEAGE_OR_PRODUCTION_BOUNDARY_CHANGED\")\n    require(scope.get(\"adapter_manifest_sha256\") == contract.sha256 and\n            scope.get(\"recorder_sha256\") == contract.files[\"recorder.py\"][\"sha256\"],\n            \"RECORDER_ADAPTER_BINDING_CHANGED\")\n";
const NEW_INIT="    def __init__(self, args):\n        self.source, self.contract = source_contract(args.adapter_manifest_sha256)\n        self.current_guard = self.contract.load('current_baseline_guard.py', 'p4_current_baseline_guard')\n        require(self.current_guard.BASELINE_SHA == self.source.BASELINE_SHA and\n                self.current_guard.QUALIFICATION_SHA == self.source.BASELINE_QUALIFICATION_SHA and\n                self.current_guard.MAIN_EPOCH == self.source.MAIN_EPOCH,\n                'CURRENT_GUARD_LITERAL_BINDING_CHANGED')\n        self.current_guard.current_guard()\n        self.binding = None\n        self.transport = None\n        self._android_mutation = False\n        self._private_backend_transport = False\n        self.root = args.flow_dir\n        if args.operation == 'init':\n            self.root.mkdir(mode=0o700)\n        info = self.root.lstat()\n        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o077,\n                'FLOW_DIRECTORY_MUST_BE_PRIVATE_AND_ROOT_OWNED')\n        self.lock = lock_file(self.root / 'flow.lock')\n        self.epoch = load_module(args.epoch_module, EPOCH_SHA, 'p4_flow_epoch')\n        self.app = load_module(APP, APP_SHA, 'p4_flow_android_app')\n        self.tasks = task_functions(args.task_source)\n        self.step = None\n        self.action_attempted = False\n        self.command_index = 0\n        if args.operation == 'init':\n            require(args.current_baseline == self.current_guard.BASELINE_PATH and\n                    args.baseline_sha256 == self.source.BASELINE_SHA,\n                    'EXPLICIT_CURRENT_BASELINE_INPUT_REQUIRED')\n            raw = self.current_guard.raw_file(args.current_baseline, 4*1024*1024,\n                    self.source.BASELINE_SHA, self.current_guard.BASELINE_BYTES)\n            qualification_raw = self.current_guard.raw_file(self.current_guard.QUALIFICATION_PATH, 65536,\n                    self.source.BASELINE_QUALIFICATION_SHA, self.current_guard.QUALIFICATION_BYTES)\n            self.activation = json.loads(raw)  # Compatibility attribute; only the new typed baseline is accepted.\n            require(self.activation == self.current_guard.current_baseline(),\n                    'CURRENT_BASELINE_DIFFERS_FROM_QUALIFIED_ORIGINAL')\n            bound = self.activation['framework_epoch']\n            require(self.activation.get('schema') == self.source.BASELINE_SCHEMA and\n                    'main_deployed' not in self.activation and self.activation.get('deployment_performed') is False,\n                    'CURRENT_BASELINE_IS_NOT_A_DEPLOYMENT_RECEIPT')\n            require(self.activation['engine_sha256'] == ENGINE_SHA and\n                    self.activation['presenter_sha256'] == PRESENTER_SHA, 'WRONG_BASELINE_ARTIFACTS')\n            require(re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\\.[A-Za-z0-9_]+)+', args.package), 'INVALID_PACKAGE')\n            require(re.fullmatch(re.escape(args.package) + r'/[A-Za-z0-9_.$]+', args.component), 'INVALID_COMPONENT')\n            self.scope = {'schema':'pocket4-current-recorder-scope-v1',\n                          'current_baseline_schema':self.source.BASELINE_SCHEMA,\n                          'package': args.package, 'component': args.component,\n                          'uid': self.activation['packages'][args.package], 'user': 0,\n                          'current_baseline_sha256': digest(raw),\n                          'current_baseline_qualification_sha256': digest(qualification_raw),\n                          'historical_activation_sha256':self.source.HISTORICAL_ACTIVATION_SHA,\n                          'historical_verified_sha256':self.source.HISTORICAL_VERIFIED_SHA,\n                          'epoch_sha256': bound['sha256'], 'created_utc': now(),\n                          'adapter_manifest_sha256': self.contract.sha256,\n                          'recorder_sha256': digest(read_regular(__file__)), 'automatic_retry': False}\n            self.guard()\n            write_new(self.root / 'baseline.json', raw)\n            write_new(self.root / 'baseline-qualification.json', qualification_raw)\n            write_new(self.root / 'scope.json', self.scope)\n            (self.root / 'steps').mkdir(mode=0o700)\n            (self.root / 'reconciliations').mkdir(mode=0o700)\n        else:\n            self.scope = json.loads(read_regular(self.root / 'scope.json'))\n            raw = self.current_guard.raw_file(self.root / 'baseline.json', 4*1024*1024,\n                    self.source.BASELINE_SHA, self.current_guard.BASELINE_BYTES)\n            self.current_guard.raw_file(self.root / 'baseline-qualification.json', 65536,\n                    self.source.BASELINE_QUALIFICATION_SHA, self.current_guard.QUALIFICATION_BYTES)\n            require(self.scope.get('current_baseline_sha256') == self.source.BASELINE_SHA and\n                    self.scope.get('current_baseline_qualification_sha256') == self.source.BASELINE_QUALIFICATION_SHA,\n                    'SAVED_CURRENT_BASELINE_CHANGED')\n            require(digest(read_regular(__file__)) == self.scope['recorder_sha256'], 'RECORDER_CHANGED_MID_FLOW')\n            self.activation = json.loads(raw)\n        self.source.verify_scope(self.scope, self.activation, self.contract)\n\n";
const OLD_INIT="    def __init__(self, args):\n        self.source, self.contract = source_contract(args.adapter_manifest_sha256)\n        self.binding = None\n        self.transport = None\n        self._android_mutation = False\n        self._private_backend_transport = False\n        self.root = args.flow_dir\n        if args.operation == 'init':\n            self.root.mkdir(mode=0o700)\n        info = self.root.lstat()\n        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o077,\n                'FLOW_DIRECTORY_MUST_BE_PRIVATE_AND_ROOT_OWNED')\n        self.lock = lock_file(self.root / 'flow.lock')\n        self.epoch = load_module(args.epoch_module, EPOCH_SHA, 'p4_flow_epoch')\n        self.app = load_module(APP, APP_SHA, 'p4_flow_android_app')\n        self.tasks = task_functions(args.task_source)\n        self.step = None\n        self.action_attempted = False\n        self.command_index = 0\n        if args.operation == 'init':\n            raw = read_regular(args.activation_after)\n            require(digest(raw) == args.activation_sha256, 'ACTIVATION_RECEIPT_PIN')\n            match = re.fullmatch(r'activation-after-([A-Za-z0-9_-]+)\\.json', args.activation_after.name)\n            require(match is not None, 'NOT_AN_EXPLICIT_ACTIVATION_AFTER_RECEIPT')\n            verified_path = args.activation_after.with_name('activation-verified-' + match[1] + '.json')\n            verified_raw = read_regular(verified_path)\n            verified = json.loads(verified_raw)\n            self.activation = json.loads(raw)\n            bound = self.activation['framework_epoch']\n            require(self.activation['main_deployed'] is True and verified['main_deployed'] is True and\n                    verified['framework_epoch_sha256'] == bound['sha256'], 'ACTIVATION_NOT_VERIFIED')\n            require(self.activation['engine_sha256'] == ENGINE_SHA and\n                    self.activation['presenter_sha256'] == PRESENTER_SHA, 'WRONG_ACTIVATION_ARTIFACTS')\n            require(re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\\.[A-Za-z0-9_]+)+', args.package), 'INVALID_PACKAGE')\n            require(re.fullmatch(re.escape(args.package) + r'/[A-Za-z0-9_.$]+', args.component), 'INVALID_COMPONENT')\n            self.scope = {'package': args.package, 'component': args.component,\n                          'uid': self.activation['packages'][args.package], 'user': 0,\n                          'activation_sha256': digest(raw), 'verified_sha256': digest(verified_raw),\n                          'epoch_sha256': bound['sha256'], 'created_utc': now(),\n                          'adapter_manifest_sha256': self.contract.sha256,\n                          'recorder_sha256': digest(read_regular(__file__)), 'automatic_retry': False}\n            self.guard()\n            write_new(self.root / 'activation.json', raw)\n            write_new(self.root / 'activation-verified.json', verified_raw)\n            write_new(self.root / 'scope.json', self.scope)\n            (self.root / 'steps').mkdir(mode=0o700)\n            (self.root / 'reconciliations').mkdir(mode=0o700)\n        else:\n            self.scope = json.loads(read_regular(self.root / 'scope.json'))\n            raw = read_regular(self.root / 'activation.json')\n            require(digest(raw) == self.scope['activation_sha256'] and\n                    digest(read_regular(self.root / 'activation-verified.json')) == self.scope['verified_sha256'],\n                    'SAVED_ACTIVATION_CHANGED')\n            require(digest(read_regular(__file__)) == self.scope['recorder_sha256'], 'RECORDER_CHANGED_MID_FLOW')\n            self.activation = json.loads(raw)\n        self.source.verify_scope(self.scope, self.activation, self.contract)\n\n";
const COORDINATOR_COPIES={"require":"def require(ok, message):\n    if not ok:\n        raise RuntimeError(message)\n","digest":"def digest(data):\n    return hashlib.sha256(data).hexdigest()\n","read":"def read(path, maximum=1024 * 1024, expected=None):\n    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)\n    try:\n        first = os.fstat(fd)\n        require(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and first.st_size <= maximum,\n                'bounded single-link regular file required: ' + str(path))\n        data = bytearray()\n        while len(data) <= maximum:\n            block = os.read(fd, min(65536, maximum + 1 - len(data)))\n            if not block:\n                break\n            data.extend(block)\n        last = os.fstat(fd)\n        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')\n        require(all(getattr(first, k) == getattr(last, k) for k in fields) and len(data) == first.st_size,\n                'input changed or exceeded bound')\n        if expected is not None:\n            require(digest(data) == expected, 'input hash changed: ' + str(path))\n        return bytes(data)\n    finally:\n        os.close(fd)\n","write_new":"def write_new(path, value, mode=0o600):\n    data = value if isinstance(value, bytes) else (json.dumps(value, sort_keys=True, indent=2) + '\\n').encode()\n    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, mode)\n    try:\n        with os.fdopen(fd, 'wb', closefd=False) as stream:\n            stream.write(data)\n            stream.flush()\n            os.fsync(fd)\n    finally:\n        os.close(fd)\n    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)\n    try:\n        os.fsync(directory)\n    finally:\n        os.close(directory)\n    return {'path': str(path), 'bytes': len(data), 'sha256': digest(data)}\n","module":"def module(raw, filename, name):\n    value = types.ModuleType(name)\n    value.__file__ = str(filename)\n    exec(compile(raw, str(filename), 'exec'), value.__dict__)\n    return value\n","run_cli":"def run_cli(name, argv, timeout, evidence, guard):\n    guard()\n    write_new(evidence / (name + '.intent.json'), {'argv': argv, 'timeout_seconds': timeout,\n        'separate_process': True, 'automatic_retry': False})\n    observed = {'name': name, 'argv': argv, 'spawned': False, 'joined': False, 'timed_out': False,\n                'returncode': None, 'secondary_errors': [], 'Main_before': True}\n    process = pidfd = None\n    primary = None\n    streams = []\n    try:\n        for suffix in ('.stdout', '.stderr'):\n            streams.append(open(evidence / (name + suffix), 'xb'))\n        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=streams[0], stderr=streams[1],\n                                   env=ENV, close_fds=True)\n        observed.update(spawned=True, owned_child_pid=process.pid)\n        pidfd = os.pidfd_open(process.pid, 0)\n        try:\n            observed['returncode'] = process.wait(timeout=timeout)\n            observed['joined'] = True\n        except BaseException as error:\n            observed['timed_out'] = isinstance(error, subprocess.TimeoutExpired)\n            raise\n    except BaseException as error:\n        primary = error\n        observed['primary_error'] = {'type': type(error).__name__, 'message': str(error)}\n    finally:\n        if process is not None and not observed['joined']:\n            try:\n                if process.poll() is None:\n                    if pidfd is not None:\n                        signal.pidfd_send_signal(pidfd, signal.SIGKILL)\n                    else:\n                        # Exact Popen child, no intervening wait/reaper; no ambient PID selection.\n                        process.kill()\n                observed['returncode'] = process.wait(timeout=6)\n                observed['joined'] = True\n            except BaseException as error:\n                observed['secondary_errors'].append({'stage': 'owned-child-retirement', 'error': repr(error)})\n        if pidfd is not None:\n            try:\n                os.close(pidfd)\n            except BaseException as error:\n                observed['secondary_errors'].append({'stage': 'owned-pidfd-close', 'error': repr(error)})\n        for stream in streams:\n            try:\n                stream.flush()\n                os.fsync(stream.fileno())\n            except BaseException as error:\n                observed['secondary_errors'].append({'stage': 'output-sync', 'error': repr(error)})\n            try:\n                stream.close()\n            except BaseException as error:\n                observed['secondary_errors'].append({'stage': 'output-close', 'error': repr(error)})\n        try:\n            observed['Main_after'] = guard()\n        except BaseException as error:\n            observed['secondary_errors'].append({'stage': 'Main-after', 'error': repr(error)})\n        for suffix in ('.stdout', '.stderr'):\n            try:\n                data = read(evidence / (name + suffix))\n                observed[suffix[1:]] = {'bytes': len(data), 'sha256': digest(data)}\n            except BaseException as error:\n                observed['secondary_errors'].append({'stage': 'output-read', 'error': repr(error)})\n        try:\n            write_new(evidence / (name + '.result.json'), observed)\n        except BaseException as error:\n            observed['secondary_errors'].append({'stage': 'phase-result-write', 'error': repr(error)})\n            if primary is None:\n                primary = error\n            else:\n                primary.add_note('phase result write: ' + repr(error))\n    if primary is not None:\n        raise primary\n    require(observed['joined'] and observed['returncode'] == 0 and not observed['secondary_errors'],\n            name + ' did not complete exactly once with a preserved Main fence')\n    return json.loads(read(evidence / (name + '.stdout')))\n"};
const HOST_CONTROLS="\"\"\"Pure current-host source controls. No process, filesystem, namespace or Android actions.\"\"\"\nimport ast,copy,hashlib,json,types\ndef require(value,code):\n    if not value:raise RuntimeError(code)\ndef functions(raw,classname=None):\n    tree=ast.parse(raw)\n    if classname is None:body=tree.body\n    else:\n        rows=[x for x in tree.body if isinstance(x,ast.ClassDef) and x.name==classname]\n        require(len(rows)==1,\"EXACT_CLASS_REQUIRED\")\n        body=rows[0].body\n    return {x.name:ast.dump(x,include_attributes=False) for x in body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))}\ndef run_controls(files,parents,manifest_raw):\n    require(type(files) is dict and type(parents) is dict,\"CONTROL_SOURCE_MAPS_REQUIRED\")\n    m=json.loads(manifest_raw)\n    require(m[\"schema\"]==2 and m[\"artifact\"]==\"pocket4-bilibili-current-recorder-held-r5\" and\n            set(m[\"files\"])==set(files),\"EXACT_NEW_HOST_SOURCE_CLOSURE_REQUIRED\")\n    compiled=[]\n    for name,raw in sorted(files.items()):\n        require(len(raw.encode())==m[\"files\"][name][\"bytes\"] and\n                hashlib.sha256(raw.encode()).hexdigest()==m[\"files\"][name][\"sha256\"],\"CONTROL_SOURCE_PIN_CHANGED\")\n        if name.endswith(\".py\"):\n            compile(raw,name,\"exec\");compiled.append(name)\n    rows=[]\n    def passed(name):rows.append({\"name\":name,\"passed\":True})\n    passed(\"complete_new_source_closure_compiles\")\n    source=types.ModuleType(\"controlled_current_source_contract\");source.__file__=\"/current-source/source_contract.py\"\n    parsed=ast.parse(files[\"source_contract.py\"])\n    constants={\"PACKAGE\",\"COMPONENT\",\"UID\",\"BASELINE_SCHEMA\",\"MAIN_EPOCH\",\"BASELINE_SHA\",\n               \"BASELINE_QUALIFICATION_SHA\",\"HISTORICAL_ACTIVATION_SHA\",\"HISTORICAL_VERIFIED_SHA\"}\n    selected=[x for x in parsed.body if\n              (isinstance(x,ast.FunctionDef) and x.name in {\"require\",\"verify_scope\"}) or\n              (isinstance(x,ast.Assign) and len(x.targets)==1 and isinstance(x.targets[0],ast.Name) and\n               x.targets[0].id in constants)]\n    require(len(selected)==len(constants)+2,\"EXACT_PRODUCTION_PURE_SCOPE_SELECTION_REQUIRED\")\n    exec(compile(ast.Module(body=selected,type_ignores=[]),source.__file__,\"exec\"),source.__dict__)\n    contract=types.SimpleNamespace(sha256=hashlib.sha256(manifest_raw.encode()).hexdigest(),files=m[\"files\"])\n    scope={\"schema\":\"pocket4-current-recorder-scope-v1\",\"current_baseline_schema\":source.BASELINE_SCHEMA,\n           \"package\":source.PACKAGE,\"component\":source.COMPONENT,\"uid\":source.UID,\"user\":0,\n           \"automatic_retry\":False,\"epoch_sha256\":source.MAIN_EPOCH,\n           \"current_baseline_sha256\":source.BASELINE_SHA,\n           \"current_baseline_qualification_sha256\":source.BASELINE_QUALIFICATION_SHA,\n           \"historical_activation_sha256\":source.HISTORICAL_ACTIVATION_SHA,\n           \"historical_verified_sha256\":source.HISTORICAL_VERIFIED_SHA,\n           \"adapter_manifest_sha256\":contract.sha256,\"recorder_sha256\":m[\"files\"][\"recorder.py\"][\"sha256\"]}\n    baseline={\"schema\":source.BASELINE_SCHEMA,\"kind\":\"current-framework-generation\",\"deployment_performed\":False,\n              \"framework_epoch\":{\"sha256\":source.MAIN_EPOCH},\n              \"historical_deployment\":{\"activation_sha256\":source.HISTORICAL_ACTIVATION_SHA,\n                  \"verification_sha256\":source.HISTORICAL_VERIFIED_SHA},\n              \"framework_exit_cause_resolved\":False,\"whole_app_production_ready\":False}\n    source.verify_scope(copy.deepcopy(scope),copy.deepcopy(baseline),contract)\n    passed(\"typed_current_scope_positive\")\n    def negative(name,change):\n        s=copy.deepcopy(scope);b=copy.deepcopy(baseline);change(s,b)\n        try:source.verify_scope(s,b,contract)\n        except RuntimeError:pass\n        else:raise RuntimeError(\"CURRENT_SCOPE_NEGATIVE_ACCEPTED:\"+name)\n        passed(name)\n    negative(\"old_epoch\",lambda s,b:s.update(epoch_sha256=\"48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f\"))\n    negative(\"missing_baseline\",lambda s,b:s.pop(\"current_baseline_sha256\"))\n    negative(\"wrong_qualification\",lambda s,b:s.update(current_baseline_qualification_sha256=\"0\"*64))\n    negative(\"old_scope_schema\",lambda s,b:s.pop(\"schema\"))\n    negative(\"historical_as_current\",lambda s,b:s.update(activation_sha256=source.HISTORICAL_ACTIVATION_SHA))\n    negative(\"forged_deployment_flag\",lambda s,b:b.update(main_deployed=True))\n    negative(\"new_deployment_claim\",lambda s,b:b.update(deployment_performed=True))\n    negative(\"foreign_target\",lambda s,b:s.update(package=\"example.unrelated\"))\n    negative(\"wrong_uid\",lambda s,b:s.update(uid=source.UID+1))\n    negative(\"bool_uid\",lambda s,b:s.update(uid=True))\n    negative(\"bool_user\",lambda s,b:s.update(user=False))\n    negative(\"wrong_component\",lambda s,b:s.update(component=source.PACKAGE+\"/Other\"))\n    negative(\"source_pin_changed\",lambda s,b:s.update(adapter_manifest_sha256=\"0\"*64))\n    negative(\"history_pin_changed\",lambda s,b:b[\"historical_deployment\"].update(activation_sha256=\"0\"*64))\n    negative(\"production_claim\",lambda s,b:b.update(whole_app_production_ready=True))\n    negative(\"cause_resolved_claim\",lambda s,b:b.update(framework_exit_cause_resolved=True))\n    negative(\"automatic_retry\",lambda s,b:s.update(automatic_retry=True))\n    old=functions(parents[\"recorder.py\"],\"Flow\");new=functions(files[\"recorder.py\"],\"Flow\")\n    keep=set(old)-{\"__init__\",\"guard\"}\n    require(set(old)==set(new) and all(old[x]==new[x] for x in keep),\"FROZEN_FLOW_ACTION_OR_CLEANUP_BODY_CHANGED\")\n    passed(\"all_flow_action_command_lock_cleanup_bodies_unchanged\")\n    def body(raw,classname,name):\n        t=ast.parse(raw);c=next(x for x in t.body if isinstance(x,ast.ClassDef) and x.name==classname)\n        return next(x for x in c.body if isinstance(x,ast.FunctionDef) and x.name==name)\n    og=body(parents[\"recorder.py\"],\"Flow\",\"guard\");ng=body(files[\"recorder.py\"],\"Flow\",\"guard\")\n    extra=[x for x in ng.body if isinstance(x,ast.Expr) and isinstance(x.value,ast.Call) and\n           isinstance(x.value.func,ast.Attribute) and x.value.func.attr==\"current_guard\"]\n    require(len(extra)==1 and ast.unparse(extra[0].value)==\"self.current_guard.current_guard(self.activation, action_attempted=attempted)\",\n            \"EXACT_ADDITIONAL_CURRENT_MAIN_GUARD_REQUIRED\")\n    ng.body=[x for x in ng.body if x not in extra]\n    require(ast.dump(og,include_attributes=False)==ast.dump(ng,include_attributes=False),\"ORIGINAL_FLOW_GUARD_WEAKENED\")\n    passed(\"original_flow_guard_all_checks_retained_plus_current_guard\")\n    current_init=body(files[\"recorder.py\"],\"Flow\",\"__init__\")\n    calls=[ast.unparse(x) for x in ast.walk(current_init) if isinstance(x,ast.Call)]\n    require(\"self.current_guard.current_guard()\" in calls and not any(\"activation_after\" in x for x in calls),\n            \"CURRENT_INIT_OR_OLD_DEPLOYMENT_REJECTION_MISSING\")\n    passed(\"current_init_prewrite_guard_and_no_old_activation_argument\")\n    old_entry=functions(parents[\"existing_ui_entry.py\"]);new_entry=functions(files[\"existing_ui_entry.py\"])\n    require(set(old_entry)==set(new_entry) and all(old_entry[k]==new_entry[k] for k in old_entry if k!=\"load_context\"),\n            \"EXISTING_UI_CHILD_DISPATCH_CHANGED\")\n    passed(\"existing_ui_dispatch_bodies_unchanged\")\n    context=ast.unparse(ast.parse(files[\"existing_ui_entry.py\"]))\n    require(\"view.current_guard = current_guard\" in context and \"baseline-qualification.json\" in context and\n            \"activation-verified.json\" not in context,\"CHILD_CURRENT_BASELINE_BINDING_MISSING\")\n    passed(\"child_guard_instance_and_new_saved_inputs_bound\")\n    old_source=functions(parents[\"source_contract.py\"]);new_source=functions(files[\"source_contract.py\"])\n    require(all(old_source[k]==new_source[k] for k in old_source if k!=\"verify_scope\"),\n            \"ORIGINAL_SHARED_HELPER_OR_BOUNDED_READ_CHANGED\")\n    passed(\"shared_native_helper_and_bounded_source_reads_unchanged\")\n    for name in (\"references/original_recorder.py\",\"references/android_app.py\",\"references/android_backend.py\",\n                 \"references/framework_epoch.py\",\"references/task_scope_baseline.py\",\"references/held_runtime_r5.py\",\n                 \"references/bound_android_transport_r3.py\"):\n        require(files[name]==parents[name],\"FROZEN_REFERENCE_CHANGED\")\n    passed(\"all_seven_original_references_byte_exact\")\n    require(len(rows)==26 and len({r[\"name\"] for r in rows})==26,\"EXACT_CURRENT_HOST_CONTROL_COUNT\")\n    return {\"schema\":\"pocket4-current-host-source-controls-v1\",\"all_passed\":True,\"count\":len(rows),\"cases\":rows,\n            \"compiled_sources\":compiled,\"fixture_is_not_baseline_observation\":True,\n            \"Android_commands\":0,\"UI_actions\":0,\"children\":0,\"filesystem_operations\":0}\n";

  function hostFork(parent,b) {
    need(parent&&Object.keys(parent).sort().join(",")==="coordinator_raw,files,manifest_raw","EXACT_HOST_PARENT_SET");
    const old=parent.files;
    const m=checkOld(parent.manifest_raw,old,oldHostManifest);
    need(digest(parent.coordinator_raw)===oldCoordinator,"EXACT_OLD_COORDINATOR_REQUIRED");
    const required=["recorder.py","source_contract.py","main_binding.py","bound_android_transport.py","existing_ui_entry.py",
      "references/original_recorder.py","references/android_app.py","references/android_backend.py","references/framework_epoch.py",
      "references/task_scope_baseline.py","references/held_runtime_r5.py","references/bound_android_transport_r3.py"];
    need(Object.keys(old).sort().join("|")===required.sort().join("|"),"EXACT_TWELVE_HOST_RUNTIME_PARENTS");
    const files={},proof={};
    const oldAct="7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615";
    const oldVerified="2d6f2ef7953b98109044f823da56694111bd9f8ff14fff5e746afb7bd42b0387";
    for(const[name,original]of Object.entries(old)) {
      const e=editor(original,name);
      if(name==="source_contract.py"){
        e.one('ARTIFACT = "pocket4-bilibili-existing-recorder-held-r1"','ARTIFACT = "pocket4-bilibili-current-recorder-held-r5"');
        e.one('MAIN_EPOCH = "'+oldEpoch+'"\nACTIVATION_SHA = "'+oldAct+'"\nVERIFIED_SHA = "'+oldVerified+'"',
          'MAIN_EPOCH = "'+b.epoch+'"\nBASELINE_SCHEMA = "'+schema+'"\nBASELINE_SHA = "'+b.baseline.sha256+
          '"\nBASELINE_QUALIFICATION_SHA = "'+b.qualification.sha256+'"\nCURRENT_GUARD_SHA = "'+b.guard.sha256+
          '"\nHISTORICAL_ACTIVATION_SHA = "'+oldAct+'"\nHISTORICAL_VERIFIED_SHA = "'+oldVerified+'"');
        if(b.uids["tv.danmaku.bili"]!==10117)e.one("UID = 10117","UID = "+b.uids["tv.danmaku.bili"]);
        e.one('"existing_ui_entry.py", "bound_android_transport.py"}',
          '"existing_ui_entry.py", "bound_android_transport.py",\n                    "current_baseline_guard.py", "current_coordinator.py"}');
        e.one('require(manifest.get("schema") == 1 and manifest.get("artifact") == ARTIFACT,',
          'require(manifest.get("schema") == 2 and manifest.get("artifact") == ARTIFACT,');
        const closure='        self.files = manifest["files"]';
        e.one(closure,
          '        binding = manifest.get("current_baseline", {})\n'+
          '        require(binding == {"schema": BASELINE_SCHEMA, "epoch_sha256": MAIN_EPOCH,\n'+
          '                "baseline_sha256": BASELINE_SHA, "qualification_sha256": BASELINE_QUALIFICATION_SHA,\n'+
          '                "guard_sha256": CURRENT_GUARD_SHA,\n'+
          '                "historical_activation_sha256": HISTORICAL_ACTIVATION_SHA,\n'+
          '                "historical_verified_sha256": HISTORICAL_VERIFIED_SHA},\n'+
          '                "ACTUAL_CURRENT_HOST_MANIFEST_BINDING_REQUIRED")\n'+closure);
        e.one('PRODUCTION_FILES | set(REFERENCE_PINS) <= set(self.files),',
          'PRODUCTION_FILES | set(REFERENCE_PINS) == set(self.files),');
        e.one('        self.verify()\n','        require(self.files["current_baseline_guard.py"]["sha256"] == CURRENT_GUARD_SHA,\n'+
          '                "CURRENT_GUARD_SOURCE_PIN_CHANGED")\n        self.verify()\n');
        const oldScope=original.slice(original.indexOf("def verify_scope("));
        e.one(oldScope,NEW_SCOPE);
      }
      if(name==="recorder.py"){
        e.one('"""One explicit Pocket4 business-flow step, bound to a verified activation.',
          '"""One explicit Pocket4 business-flow step, bound to a typed current baseline.');
        e.one(OLD_INIT,NEW_INIT);
        e.one("        self.source.verify_scope(self.scope, self.activation, self.contract)\n        self.epoch.require_unchanged",
          "        self.source.verify_scope(self.scope, self.activation, self.contract)\n"+
          "        self.current_guard.current_guard(self.activation, action_attempted=attempted)\n        self.epoch.require_unchanged");
        e.one("    parser.add_argument('--activation-after', type=Path)\n    parser.add_argument('--activation-sha256')",
          "    parser.add_argument('--current-baseline', type=Path)\n    parser.add_argument('--baseline-sha256')");
        e.one("default=Path('/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py')",
          "default=Path(__file__).resolve().parent / 'references/framework_epoch.py'");
      }
      if(name==="bound_android_transport.py"){
        e.one('FRAMEWORK_EPOCH_SHA256 = "'+oldEpoch+'"','FRAMEWORK_EPOCH_SHA256 = "'+b.epoch+'"');
        if(b.uids["tv.danmaku.bili"]!==10117)e.one("EXPECTED_UID = 10117","EXPECTED_UID = "+b.uids["tv.danmaku.bili"]);
      }
      if(name==="main_binding.py"){
        if(b.uids["local.pocket4.actions.v2"]!==10125)e.one('"local.pocket4.actions.v2": 10125','"local.pocket4.actions.v2": '+b.uids["local.pocket4.actions.v2"]);
        e.one('self.record = {"schema": 1, "scope": "fixed Main Bilibili only",',
          'self.record = {"schema": 2, "scope": "fixed current-baseline Main Bilibili only",\n'+
          '                "current_baseline_schema": source.BASELINE_SCHEMA,\n'+
          '                "current_baseline_sha256": source.BASELINE_SHA,\n'+
          '                "current_baseline_qualification_sha256": source.BASELINE_QUALIFICATION_SHA,');
      }
      if(name==="existing_ui_entry.py"){
        const begin="    activation_raw = source.bounded_file(root / 'activation.json')";
        const end="    source.verify_scope(scope, activation, contract)";
        const at=e.text.indexOf(begin),stop=e.text.indexOf(end,at);
        need(at>=0&&stop>at,"EXACT_EXISTING_CHILD_CONTEXT_BLOCK");
        e.one(e.text.slice(at,stop),
          "    current_guard = contract.load('current_baseline_guard.py', 'p4_child_current_baseline_guard')\n"+
          "    require(current_guard.BASELINE_SHA == source.BASELINE_SHA and\n"+
          "            current_guard.QUALIFICATION_SHA == source.BASELINE_QUALIFICATION_SHA and\n"+
          "            current_guard.MAIN_EPOCH == source.MAIN_EPOCH, 'CURRENT_CHILD_GUARD_BINDING_CHANGED')\n"+
          "    activation_raw = current_guard.raw_file(root / 'baseline.json', 4*1024*1024,\n"+
          "            source.BASELINE_SHA, current_guard.BASELINE_BYTES)\n"+
          "    scope = json.loads(source.bounded_file(root / 'scope.json'))\n"+
          "    current_guard.raw_file(root / 'baseline-qualification.json', 65536,\n"+
          "            source.BASELINE_QUALIFICATION_SHA, current_guard.QUALIFICATION_BYTES)\n"+
          "    require(scope.get('current_baseline_sha256') == source.BASELINE_SHA and\n"+
          "            scope.get('current_baseline_qualification_sha256') == source.BASELINE_QUALIFICATION_SHA,\n"+
          "            'SAVED_CURRENT_BASELINE_CHANGED')\n"+
          "    activation = json.loads(activation_raw)\n");
        e.one("    view.source, view.contract = source, contract\n",
          "    view.source, view.contract = source, contract\n    view.current_guard = current_guard\n");
      }
      e.inverse();files[name]=e.text;proof[name]={parent:pin(original),generated:pin(e.text),inverse_byte_exact:true,
        edits:e.edits.map(x=>({old:x.old,next:x.next,count:x.count}))};
    }
    files["current_baseline_guard.py"]=b.guard_raw;
    const common=["require","digest","read","write_new","module","run_cli"].map(n=>{
      need(parent.coordinator_raw.includes(COORDINATOR_COPIES[n]),"COORDINATOR_ORIGINAL_FUNCTION_NOT_EXACT:"+n);
      return COORDINATOR_COPIES[n];
    }).join("\n");
    files["current_coordinator.py"]=
      '"""Typed current-baseline coordinator utilities. Importing performs no operations.\n'+
      'Fresh app workflows must use these new names and new recorder init options.\n'+
      'Historical activation receipts are lineage only; runtime admission is separate.\n"""\n'+
      "import hashlib,json,os,signal,stat,subprocess,time,types\nfrom pathlib import Path\n"+
      "HERE=Path(__file__).resolve().parent\nBASELINE=Path("+JSON.stringify(b.baseline.path)+")\n"+
      "BASELINE_SHA="+JSON.stringify(b.baseline.sha256)+"\nQUALIFICATION=Path("+JSON.stringify(b.qualification.path)+")\n"+
      "QUALIFICATION_SHA="+JSON.stringify(b.qualification.sha256)+"\nEPOCH="+JSON.stringify(b.epoch)+"\n"+
      "EPOCH_SOURCE=HERE/'references/framework_epoch.py'\nEPOCH_SOURCE_SHA='f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288'\n"+
      "GUARD_SOURCE=HERE/'current_baseline_guard.py'\nGUARD_SOURCE_SHA="+JSON.stringify(b.guard.sha256)+"\n"+
      "ENV={'PATH':'/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8'}\n\n"+
      common+"\n"+
      "def guard_module():\n"+
      "    guard=module(read(GUARD_SOURCE,expected=GUARD_SOURCE_SHA),GUARD_SOURCE,'current_coordinator_guard')\n"+
      "    require(guard.BASELINE_SHA==BASELINE_SHA and guard.QUALIFICATION_SHA==QUALIFICATION_SHA and\n"+
      "            guard.MAIN_EPOCH==EPOCH,'CURRENT_COORDINATOR_GUARD_BINDING_CHANGED')\n"+
      "    return guard\n"+
      "def current_baseline():\n"+
      "    return guard_module().current_baseline()\n"+
      "def main_guard(baseline=None,epoch=None):\n"+
      "    return guard_module().current_guard(baseline,action_attempted=False)\n";
    const binding={schema,epoch_sha256:b.epoch,baseline_sha256:b.baseline.sha256,qualification_sha256:b.qualification.sha256,
      guard_sha256:b.guard.sha256,historical_activation_sha256:oldAct,historical_verified_sha256:oldVerified};
    const manifest={schema:2,artifact:"pocket4-bilibili-current-recorder-held-r5",revision:5,
      parent_R4_manifest_sha256:oldHostManifest,current_baseline:binding,
      actual_baseline_result:b.result,current_baseline_private:b.baseline,current_qualification:b.qualification,
      source_fork_is_not_deployment:true,old_flows_reauthorized:false,whole_app_production_ready:false,
      files:Object.fromEntries(Object.entries(files).sort().map(([n,s])=>[n,pin(s)]))};
    const raw=JSON.stringify(manifest,null,2)+"\n";
    need(Object.keys(files).length===14&&size(raw)<=131072,"EXACT_CURRENT_HOST_SOURCE_CLOSURE");
    return {files,manifest_raw:raw,manifest_sha256:digest(raw),binding,proof,
      controls_source:HOST_CONTROLS,controls_expected:26,current_runtime_admitted:false,
      other_apps_context_rebinding_still_required:true,framework_exit_cause_resolved:false};
  }
  function compileHostActual(actual,parent){
    const b=actualBinding(actual);
    return hostFork(parent,b);
  }
  return {compileHostActual};
}
