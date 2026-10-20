#!/usr/bin/env python3
import datetime,hashlib,json,pathlib
root=pathlib.Path(__file__).resolve().parent
out=[]
for p in sorted((root/"blobs").glob("*.capture.json")):
 r=json.loads(p.read_text())
 raw=r["content"].encode("utf-8")
 got=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
 row={k:v for k,v in r.items() if k!="content"}
 row.update(size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),actual_git_blob=got,blob_matches=got==r["expected_git_blob"])
 if not row["blob_matches"]: raise SystemExit(json.dumps(row))
 target=p.with_name(r["id"]+".source")
 target.write_bytes(raw)
 row["saved_source"]=str(target.relative_to(root))
 out.append(row)
(root/"blob-verification.json").write_text(json.dumps({"verified_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"blobs":out},indent=2)+"\n")
print(json.dumps({"count":len(out),"all_git_blob_match":all(x["blob_matches"] for x in out)}))

