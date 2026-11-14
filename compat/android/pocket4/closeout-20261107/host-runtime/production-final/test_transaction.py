"""Host-only regression for the existing multi-file transaction core."""
import importlib.util, pathlib, tempfile, json, os
HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("cohort",HERE/"deploy_cohort.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
results=[]
def fixture(root):
    rows=[]
    for i in range(11):
        target=root/f"target-{i}";old=b"baseline-"+str(i).encode();new=b"candidate-"+str(i).encode()
        target.write_bytes(old)
        if os.geteuid()==0 and i in (2,3): os.chown(target,1000,1000)
        if i < 10: os.setxattr(target,"user.pocket4-fixture",b"preserved")
        target.chmod(0o444 if i==10 else 0o755)
        base=m.snapshot(target)
        before=root/f"rollback-{i}";after=root/f"candidate-{i}"
        before.write_bytes(old);after.write_bytes(new)
        rows.append({"name":str(i),"host_path":str(target),"baseline":base,
                     "candidate":{"path":str(after),"sha256":m.digest(new),"bytes":len(new)},
                     "rollback":{"path":str(before),"sha256":m.digest(old),"bytes":len(old)}})
    return rows
def hashes(rows,variant):
    return all(m.snapshot(t["host_path"])["sha256"]==t[variant]["sha256"] for t in rows)
def note(*_):pass
for case in ("success","rollback","rename_fail_first","rename_fail_middle","rename_fail_last",
             "rename_then_fail","unknown_before","unknown_during","payload_changed","guard_refuses"):
    with tempfile.TemporaryDirectory(prefix="p4-cohort-tests-") as tmp:
        root=pathlib.Path(tmp);rows=fixture(root);count=0;guards=0
        def guard():
            global guards
            guards+=1
            if case=="guard_refuses":raise RuntimeError("fixture not stopped")
        def replace(source,dest):
            global count
            count+=1
            index={"rename_fail_first":1,"rename_fail_middle":6,"rename_fail_last":11}.get(case)
            if count==index:raise OSError("injected rename failure")
            os.replace(source,dest)
            if case=="rename_then_fail" and count==6:raise OSError("injected post-rename failure")
            if case=="unknown_during" and count==1:
                p=pathlib.Path(rows[8]["host_path"]);p.write_bytes(b"third-party bytes")
                os.utime(p,ns=(rows[8]["baseline"]["atime_ns"],rows[8]["baseline"]["mtime_ns"]))
                raise OSError("third party change and stop")
        if case=="unknown_before":
            pathlib.Path(rows[5]["host_path"]).write_bytes(b"unknown")
        if case=="payload_changed":
            pathlib.Path(rows[4]["candidate"]["path"]).write_bytes(b"unexpected payload")
        raised=None
        try:r=m.transact(rows,"candidate",guard,note,replace=replace)
        except RuntimeError as e:raised=str(e);r=None
        if case in ("unknown_before","guard_refuses"):
            assert raised is not None and r is None
            assert count==0
        elif case in ("success","rollback"):
            assert r["success"] and hashes(rows,"candidate")
            assert all(m.same_attributes(m.snapshot(t["host_path"]),t["baseline"]) for t in rows)
            assert all(m.snapshot(t["host_path"])["inode"]!=t["baseline"]["inode"] for t in rows)
            if case=="rollback":
                r=m.transact(rows,"rollback",lambda:None,note)
                assert r["success"] and hashes(rows,"rollback")
        elif case=="unknown_during":
            assert not r["success"] and not r["rollback_completed"]
            assert "UNKNOWN_BYTES" in r["rollback_error"]
        else:
            assert not r["success"] and hashes(rows,"rollback")
            if case.startswith("rename"):assert r["rollback_completed"]
        assert not list(root.glob(".pocket4-closeout-cohort-*"))
        results.append({"case":case,"passed":True,"targets":11})
report={"schema":"pocket4-cohort-core-regressions-v1","state":"PASS","tests":results,"Main_actions":0}
(HERE/"transaction-tests.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps(report))

