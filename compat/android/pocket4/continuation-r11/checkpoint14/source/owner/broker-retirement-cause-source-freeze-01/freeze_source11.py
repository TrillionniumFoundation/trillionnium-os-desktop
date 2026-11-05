#!/usr/bin/env python3
"""Freeze one diagnostic-only overlay on the actual producer10 broker source."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE=Path('/workspace/scratch/94990735b266/lmkd-recovery-20261105-01')
ROOT=BASE/'broker-retirement-cause-source-freeze-01'
REL=Path('runtime/droidloom-pressure-relay/src/lifecycle_bootstrap.rs')
OLD=BASE/'broker-holding-bootstrap-source-freeze-01/candidate'/REL
ACTUAL=Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence/producer10-broker-compile01/result.json')

HELPER=r'''// Diagnostics only: borrow both original causes before the joined receipt is
// consumed by PressureAudit. UTF-8 hex keeps one parseable line without losing
// newlines or non-ASCII bytes. A stderr failure must not replace either cause,
// change the retirement outcome, or acquire any lifecycle authority.
fn report_retirement_cause(output: &mut impl Write, status: &BootstrapStatus,
    relay_reason: Option<&str>, lifecycle_error: Option<&Error>) {
    if relay_reason.is_none() && lifecycle_error.is_none() { return; }
    let hex = |bytes: &[u8]| -> String {
        const DIGITS: &[u8; 16] = b"0123456789abcdef";
        let mut text = String::with_capacity(bytes.len() * 2);
        for &byte in bytes {
            text.push(DIGITS[(byte >> 4) as usize] as char);
            text.push(DIGITS[(byte & 15) as usize] as char);
        }
        text
    };
    let optional_hex = |text: Option<&str>| -> String {
        match text {
            Some(value) => format!("\"{}\"", hex(value.as_bytes())),
            None => "null".to_owned(),
        }
    };
    let lifecycle_message = lifecycle_error.map(|error| error.to_string());
    let _ = writeln!(output,
        "droidloom-psi-owner: retirement-cause-v1 {{\"schema\":1,\"nonce\":\"{}\",\"authority_generation\":\"{}\",\"cgroup_device\":{},\"cgroup_inode\":{},\"granted\":{},\"faulted\":{},\"relay_reason_utf8_hex\":{},\"lifecycle_error_utf8_hex\":{}}}",
        hex(&status.nonce), hex(&status.generation), status.cgroup.device, status.cgroup.inode,
        status.granted, status.faulted, optional_hex(relay_reason), optional_hex(lifecycle_message.as_deref()));
}

'''

TESTS=r'''    #[test]
    fn retirement_cause_diagnostic_preserves_specific_and_lifecycle_reasons() {
        let (_, mut status) = empty_audit_and_status(); status.faulted = true;
        let before = status.clone();
        let reason = "specific rejection".to_owned();
        let outcome: Result<()> = Err(Error::Reject("outer"));
        let mut output = Vec::new();
        report_retirement_cause(&mut output, &status, Some(&reason), outcome.as_ref().err());
        let expected = format!(
            "droidloom-psi-owner: retirement-cause-v1 {{\"schema\":1,\"nonce\":\"{}\",\"authority_generation\":\"{}\",\"cgroup_device\":3,\"cgroup_inode\":4,\"granted\":false,\"faulted\":true,\"relay_reason_utf8_hex\":\"73706563696669632072656a656374696f6e\",\"lifecycle_error_utf8_hex\":\"72656a65637465643a206f75746572\"}}\n",
            "07".repeat(32), "06".repeat(32));
        assert_eq!(String::from_utf8(output).unwrap(), expected);
        assert_eq!(status, before); assert_eq!(reason, "specific rejection");
        assert!(matches!(outcome, Err(Error::Reject("outer"))));
    }
    #[test]
    fn retirement_cause_diagnostic_healthy_is_silent() {
        struct NoWrite;
        impl Write for NoWrite {
            fn write(&mut self, _: &[u8]) -> io::Result<usize> { panic!("healthy diagnostic wrote"); }
            fn flush(&mut self) -> io::Result<()> { panic!("healthy diagnostic flushed"); }
        }
        let (_, status) = empty_audit_and_status();
        report_retirement_cause(&mut NoWrite, &status, None, None);
    }
    #[test]
    fn retirement_cause_diagnostic_encodes_raw_utf8_once() {
        let (_, mut status) = empty_audit_and_status(); status.faulted = true;
        let reason = "line\n原因\t\"";
        let mut output = Vec::new();
        report_retirement_cause(&mut output, &status, Some(reason), None);
        let text = String::from_utf8(output).unwrap();
        assert_eq!(text.bytes().filter(|byte| *byte == b'\n').count(), 1);
        assert!(text.contains("\"relay_reason_utf8_hex\":\"6c696e650ae58e9fe59ba00922\""));
        assert!(text.contains("\"lifecycle_error_utf8_hex\":null"));
        assert!(!text.contains(reason));
    }
    #[test]
    fn retirement_cause_diagnostic_broken_owned_socket_preserves_outcome() {
        let (mut writer, peer) = std::os::unix::net::UnixStream::pair().unwrap();
        drop(peer);
        assert_eq!(writer.write(b"probe").unwrap_err().kind(), io::ErrorKind::BrokenPipe);
        let (_, mut status) = empty_audit_and_status(); status.faulted = true;
        let before = status.clone();
        let reason = "original admission reason".to_owned();
        let outcome: Result<()> = Err(Error::Reject("original lifecycle result"));
        report_retirement_cause(&mut writer, &status, Some(&reason), outcome.as_ref().err());
        assert_eq!(status, before); assert_eq!(reason, "original admission reason");
        assert!(matches!(outcome, Err(Error::Reject("original lifecycle result"))));
    }
'''


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pretty(value):
    return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()


def main():
    actual_raw=ACTUAL.read_bytes()
    assert len(actual_raw)==39853 and sha(actual_raw)=='879cbe2c95a98de1f2d8d820348059eb1656d1b82c59b272bc4c901b91013460'
    actual=json.loads(actual_raw);assert actual['success'] is True
    old=OLD.read_bytes();expected=actual['inputs_before'][str(REL)]
    assert expected==actual['inputs_after'][str(REL)]=={'bytes':len(old),'sha256':sha(old)}
    text=old.decode()
    anchor='/// Production executable entry.'
    assert text.count(anchor)==1;text=text.replace(anchor,HELPER+anchor,1)
    line='                status.faulted = outcome.is_err() || receipt.reason().is_some();\n'
    assert text.count(line)==1
    addition='                report_retirement_cause(&mut io::stderr().lock(), &status, receipt.reason(), outcome.as_ref().err());\n'
    text=text.replace(line,line+addition,1)
    test_anchor='    #[test]\n    fn producer05_three_second_retirement_is_rejected_before_transport()'
    assert text.count(test_anchor)==1;text=text.replace(test_anchor,TESTS+test_anchor,1)
    reconstructed=text.replace(HELPER,'',1).replace(addition,'',1).replace(TESTS,'',1)
    assert reconstructed.encode()==old
    assert text.count('#[test]')==old.decode().count('#[test]')+4
    diff=''.join(difflib.unified_diff(old.decode().splitlines(True),text.splitlines(True),
                                   fromfile='a/'+str(REL),tofile='b/'+str(REL))).encode()
    validation={'schema':1,'kind':'producer11_diagnostic_only_source_binding','actual_parent_compile':{'path':str(ACTUAL),'bytes':len(actual_raw),'sha256':sha(actual_raw)},
                'preimage':{'path':str(REL),'bytes':len(old),'sha256':sha(old)},
                'candidate':{'path':str(REL),'bytes':len(text.encode()),'sha256':sha(text.encode())},
                'all_original_bytes_reconstructed_by_removing_only_helper_call_and_tests':True,
                'new_Rust_tests':4,'expected_relay_library_tests':30,'unchanged_supervisor_library_tests':122,
                'unchanged_ordinary_IPC_controls':7,'Rust_compiler_available_locally':False,
                'Rust_tests_executed':False,'Android_or_Main_actions':0,'wire_or_authority_or_timeout_changes':False,
                'original_runtime_cause_now_known':False,'existing_Owner10_failure_preserved':True}
    readme='''# Producer11 joined-retirement cause diagnostic: source only\n\nOwner10 actually completed HELLO, broker READY, detached socket PROJECT,\nCOMMIT and DONE, then retired faulted before any enrollment grant. Its\noriginal 15-file collection confirms that stderr contains only the generic\nrelay-retired error. The inner RetirementReceipt.reason existed, but the\nbootstrap caller converted it to the faulted flag and consumed the receipt.\nNo claim is made that blkio/cpuset messages or SIGHUP caused this failure.\n\nThis one-file overlay borrows the original relay reason and original lifecycle\noutcome immediately before receipt consumption. It emits one diagnostic line\nwith schema, exact nonce/authority-generation/cgroup identity and status flags.\nBoth causes are independently encoded as UTF-8 hex; neither overwrites the\nother and the decoder can recover embedded newlines/non-ASCII bytes exactly.\nNo new authority, retry, thread, descriptor, timeout, PSI threshold, IPC field\nor production entry is added. Healthy retirement with no cause emits nothing.\nAn output error is ignored and cannot replace the original error/receipt.\n\nFour Rust tests exercise exact dual-cause retention, no healthy output, exact\nUTF-8/framing and a real owned UnixStream whose peer has closed. They have NOT\nbeen compiled or run locally: this environment has no Rust compiler. Matching\ncompile and ordinary execution must establish their results. Expected totals\nare 30 relay and unchanged 122 supervisor library tests, plus unchanged 7 IPC\ncontrols. A subsequent fresh owned runtime is still needed for the real cause.\nThis candidate is not deployed; Owner10 and every old frozen file remain intact.\n'''
    files={'preimage/'+str(REL):old,'candidate/'+str(REL):text.encode(),
           'source.diff':diff,'validation.json':pretty(validation),'README.md':readme.encode(),
           'freeze_source11.py':Path(__file__).read_bytes()}
    ROOT.mkdir(exist_ok=False)
    rows=[]
    for name,raw in files.items():
        raw.decode();path=ROOT/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(raw)
        rows.append({'path':name,'bytes':len(raw),'sha256':sha(raw)})
    manifest=pretty({'schema':1,'source_only':True,'files':rows,'runtime_qualified':False})
    (ROOT/'manifest.json').write_bytes(manifest)
    print(json.dumps({'root':str(ROOT),'manifest_sha256':sha(manifest),'diff_bytes':len(diff),'diff_sha256':sha(diff),**validation},indent=2))


if __name__=='__main__':
    main()
