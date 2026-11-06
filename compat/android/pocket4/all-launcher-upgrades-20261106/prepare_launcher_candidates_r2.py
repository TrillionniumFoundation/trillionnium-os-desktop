#!/usr/bin/env python3
"""Stage original official Android APK candidates. Never installs or runs an App."""
import concurrent.futures, datetime, hashlib, json, os, pathlib, shutil, time
import urllib.error, urllib.parse, urllib.request

ROOT = pathlib.Path("/home/alex/work/pocket4-launcher-official-candidates-20261106-r2")
CANDIDATES = [
    {"package":"com.tencent.mm","channel_version":"8.0.80",
     "landing":"https://weixin.qq.com/",
     "url":"https://dldir1v6.qq.com/weixin/android/weixin8080android3220_0x28005032_arm64.apk"},
    {"package":"com.rytong.airchina","channel_version":"7.53.0",
     "landing":"https://m.airchina.com.cn/apps/",
     "url":"https://m.airchina.com.cn/apps/ipa/AirChina.apk"},
    {"package":"com.jingdong.app.mall","channel_version":"16.1.50",
     "landing":"https://wqs.jd.com/downloadApp/download.html",
     "url":"https://apk.360buyimg.com/jdmobile/M%E5%BC%95%E6%B5%81H5%E4%B8%8B%E8%BD%BD%E9%A1%B5%E5%AE%98%E6%96%B9%E5%8C%85_1587867215427.apk"},
    {"package":"com.sankuai.meituan.takeoutnew","channel_version":"8.85.1",
     "landing":"https://waimai.meituan.com/download?channel=1013",
     "url":"https://api.mobile.meituan.com/appupdate/download/simple/waimai?channel=1013&scheme=null",
     "source_note":"HTTPS form of observed public redirect; only verified package/signer will establish identity; no install over re-signed current package"}
]
LIMIT = 768 * 1024 * 1024

class HTTPSOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise RuntimeError("HTTPS_REDIRECT_REQUIRED")
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def fetch(candidate):
    row = dict(candidate, started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
               automatic_retry=False, app_installed=False, app_executed=False)
    part = ROOT / (candidate["package"] + ".part")
    final = ROOT / (candidate["package"] + ".apk")
    hasher = hashlib.sha256()
    count = 0
    deadline = time.monotonic() + 480
    try:
        opener = urllib.request.build_opener(HTTPSOnly)
        request = urllib.request.Request(candidate["url"], headers={
            "User-Agent":"Mozilla/5.0 (Linux; Android 17) AppleWebKit/537.36"})
        with opener.open(request, timeout=20) as response, part.open("xb") as out:
            row.update(final_url=response.url, http_status=response.status,
                       content_type=response.headers.get("Content-Type"),
                       declared_length=response.headers.get("Content-Length"))
            if response.status != 200:
                raise RuntimeError("HTTP_STATUS_NOT_OK")
            if row["declared_length"] and int(row["declared_length"]) > LIMIT:
                raise RuntimeError("DOWNLOAD_SIZE_LIMIT")
            first = True
            while True:
                if time.monotonic() > deadline:
                    raise RuntimeError("DOWNLOAD_DEADLINE")
                block = response.read(1024 * 1024)
                if not block:
                    break
                if first and not block.startswith(b"PK\x03\x04"):
                    raise RuntimeError("RESPONSE_IS_NOT_ZIP_APK")
                first = False
                count += len(block)
                if count > LIMIT:
                    raise RuntimeError("DOWNLOAD_SIZE_LIMIT")
                out.write(block)
                hasher.update(block)
            if count < 1024:
                raise RuntimeError("EMPTY_OR_SHORT_APK")
            if row["declared_length"] and count != int(row["declared_length"]):
                raise RuntimeError("INCOMPLETE_DOWNLOAD")
            out.flush()
            os.fsync(out.fileno())
        if final.exists():
            raise RuntimeError("FINAL_PATH_ALREADY_EXISTS")
        os.rename(part, final)
        row.update(status="STAGED_PENDING_SIGNATURE_AND_IDENTITY_VERIFICATION",
                   bytes=count, sha256=hasher.hexdigest(), local_path=str(final),
                   claimed_latest_usable=False)
    except Exception as exc:
        row.update(status="DOWNLOAD_FAILED", error_type=type(exc).__name__,
                   error=str(exc)[:400], partial_bytes=count,
                   partial_sha256=hasher.hexdigest(), partial_preserved=part.exists())
    row["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    print(json.dumps(row, ensure_ascii=False), flush=True)
    return row

def main():
    if shutil.disk_usage(ROOT.parent).free < 4 * 1024**3:
        raise RuntimeError("INSUFFICIENT_STAGING_SPACE")
    os.mkdir(ROOT, 0o700)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(fetch, CANDIDATES))
    report = {"schema":"pocket4-all-launcher-official-candidates-v2",
              "download_only":True, "UI_actions":0, "installs":0,
              "automatic_retries":0, "candidates":rows}
    target = ROOT / "download-results.json"
    with target.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"report":str(target),"downloaded":sum(x["status"].startswith("STAGED_") for x in rows),
                      "failed":sum(x["status"]=="DOWNLOAD_FAILED" for x in rows)}), flush=True)

if __name__ == "__main__":
    main()
