#!/usr/bin/env python3
"""Read one completed failed case; do not run any Android or Flow entry.

Only the fixed case step, its declared nonce/command/transport filename set,
scope, launch, exact case/request and frozen parser sources may be read.
Full original bytes stay in one new root-private bundle. Stdout has hashes,
phase names and the original parser's content-free failure diagnostics only.
Collection success never qualifies the failed case or authorizes another UI.
"""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

CONFIG = {'sources': {'base': {'path': '/home/alex/work/pocket4-beike-owned-cleanup-20261106-r1/cleanup_owned_task_once.py', 'bytes': 22233, 'sha256': '559ae3641a5f6e017914102af61c5f8e909605cb92be32d1a045ae7c66a935cf'}, 'core': {'path': '/home/alex/work/pocket4-beike-owned-postcondition-20261106-baaf68ac0d617dbe3894f714b18f099b/owned_postcondition_core.py', 'bytes': 28714, 'sha256': '6f780bdd021942617a6817dbc449eeacc60eeda9972d619fdb192ec4ae313e41'}, 'qa': {'path': '/home/alex/work/pocket4-successor-qa-build-source-b34f158f88bbebf112840fd88df25d03/qa_contract.py', 'bytes': 52359, 'sha256': 'bfe1e781e254033ab5c5b7616a928d309998bde4cbc243bd542c3eb4805eda6e'}, 'transport': {'path': '/home/alex/work/pocket4-successor-qa-source-b34f158f88bbebf112840fd88df25d03/recorder/bound_android_transport.py', 'bytes': 15603, 'sha256': '069d003809d95b33e0d727fdec3ca6e8488e214180449cacbad07e66a302652f'}, 'worker': {'bytes': 25377, 'path': '/home/alex/work/pocket4-beike-owned-ui-reusable-20261106-r1/owned_ui_request_once.py', 'sha256': 'c394598e477f1912378c6c3d582850a196e64f77791d0b7f5c4d498ec9b61e38'}, 'adapter': {'path': '/home/alex/work/pocket4-successor-qa-build-source-b34f158f88bbebf112840fd88df25d03/qa_adapter.py', 'bytes': 29378, 'sha256': 'ad54e8583ffb8b4ff186accde10199aee1ab063bd5dbbb5b9586c908ebebb10c'}, 'run_case': {'path': '/home/alex/work/pocket4-successor-qa-build-source-b34f158f88bbebf112840fd88df25d03/run_case.py', 'bytes': 9595, 'sha256': 'cea31bd9afd0ddc147224a441fab277e0b5d55e034008dc49295ff198a046f2b'}}, 'scope': {'path': '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/scope.json', 'bytes': 1002, 'sha256': '08c014646be1d32ef9eacc119f7930b941fc696333bd4cff9d74106f19dba516'}, 'launch': {'path': '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/launch-scope.json', 'bytes': 373, 'sha256': '54a669eb54fa0dcf6df5afcd17848af7511c2122623192051eb6370e42bfbb06'}, 'case': {'bytes': 1435, 'path': '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/qa-close-and-observe-search-01.case.json', 'sha256': '2049bd107278f39cab66fccf14a6d9dda5c66db40723761d8eb64b436ee4ae95'}, 'request': {'bytes': 1808, 'path': '/home/alex/work/pocket4-beike-owned-ui-reusable-20261106-r1/request-5886781c82e9e392d8e1ff33b95b28bb5dba615011a50eb53cc2d1d903c026af.json', 'sha256': '5886781c82e9e392d8e1ff33b95b28bb5dba615011a50eb53cc2d1d903c026af'}, 'actual_stdout_base64': 'eyJhY2NlcHRhbmNlX3JlcXVpcmVzX29yaWdpbmFsX3N0ZG91dF9hbmRfYXV0aG9yaXRhdGl2ZV9kdXJhYmxlX3Rlcm1pbmFsIjp0cnVlLCJhdXRvbWF0aWNfcmV0cnkiOmZhbHNlLCJjaGlsZF9saWZlY3ljbGUiOnsiY2hpbGRfcGlkIjoxNTk2NTczLCJlcnJvcnMiOltdLCJvd25lZF9jaGlsZF9zaWdraWxsX2NvdW50IjowLCJwYXJlbnRfZGVzY3JpcHRvcnNfcmVzdG9yZWQiOnRydWUsInBpZGZkX2FjcXVpcmVkIjp0cnVlLCJwaWRmZF9jbG9zZWQiOnRydWUsInBpZGZkX2V4aXRfb2JzZXJ2ZWQiOnRydWUsInJldHVybmNvZGUiOjEsInRpbWVvdXQiOmZhbHNlfSwiY2hpbGRfc3RkZXJyX2J5dGVzIjowLCJjaGlsZF9zdGRlcnJfb3JpZ2luYWwiOiIiLCJjaGlsZF9zdGRlcnJfc2hhMjU2IjoiZTNiMGM0NDI5OGZjMWMxNDlhZmJmNGM4OTk2ZmI5MjQyN2FlNDFlNDY0OWI5MzRjYTQ5NTk5MWI3ODUyYjg1NSIsImNoaWxkX3N0ZG91dF9ieXRlcyI6NDA0NiwiY2hpbGRfc3Rkb3V0X29yaWdpbmFsIjoie1wiYWxsb3dzX25ld19tdXRhdGlvbl93aXRob3V0X29yaWdpbmFsX0Zsb3dfY2hlY2tzXCI6ZmFsc2UsXCJhdXRvbWF0aWNfcmV0cnlcIjpmYWxzZSxcImNsZWFudXBfb3JfZm9jdXNfYWN0aW9uc1wiOjAsXCJkZWNsYXJlZF9tdXRhdGlvblwiOnRydWUsXCJlcnJvcnNcIjpbe1wicmVhc29uXCI6XCJPUklHSU5BTF9FTlRSWV9GQUlMRURfTk9fUkVUUllcIixcInR5cGVcIjpcIlJ1bnRpbWVFcnJvclwifV0sXCJmbG93XCI6XCIvaG9tZS9hbGV4L3dvcmsvcG9ja2V0NC1zdWNjZXNzb3ItcWEtZmxvdy1iNmRlMmJkNGYwNGJjZDU3MmEwNzRlZjk4NGJhN2RiZVwiLFwiaW5wdXRfYXJ0aWZhY3RcIjp7XCJieXRlc1wiOjE0MzUsXCJwYXRoXCI6XCIvaG9tZS9hbGV4L3dvcmsvcG9ja2V0NC1zdWNjZXNzb3ItcWEtZmxvdy1iNmRlMmJkNGYwNGJjZDU3MmEwNzRlZjk4NGJhN2RiZS9xYS1jbG9zZS1hbmQtb2JzZXJ2ZS1zZWFyY2gtMDEuY2FzZS5qc29uXCIsXCJzaGEyNTZcIjpcIjIwNDliZDEwNzI3OGYzOWNhYjY2ZmNjZjE0YTZkOWRkYTVjNjZkYjQwNzIzNzYxZDhlYjY0YjQzNmVlNGFlOTVcIn0sXCJpbnN0YWxsc1wiOjAsXCJraW5kXCI6XCJjYXNlXCIsXCJuYXRpdmVfbGF1bmNoZXNcIjowLFwib2tcIjpmYWxzZSxcIm9yaWdpbmFsX1VOS05PV05fcmV3cml0dGVuXCI6ZmFsc2UsXCJvcmlnaW5hbF9hcmd2XCI6W1wiL2hvbWUvYWxleC93b3JrL3BvY2tldDQtc3VjY2Vzc29yLXFhLWJ1aWxkLXNvdXJjZS1iMzRmMTU4Zjg4YmJlYmYxMTI4NDBmZDg4ZGYyNWQwMy9ydW5fY2FzZS5weVwiLFwiLS1leGVjdXRlLW9uY2VcIixcIi0taW50ZXJhY3RpdmUtcHJvZHVjdGlvblwiLFwiLS1zb3VyY2UtbWFuaWZlc3Qtc2hhMjU2XCIsXCJkZmI5YjZhNDgzZjEwNjk4NDc0MzMxNTJiOWIyZThiMGYxYjJjZGQ1NzFhMWRiZGUzMDY4ZmM5MzkzYWQ2MmM0XCIsXCItLWJ1aWxkLXJlY2VpcHRcIixcIi9ob21lL2FsZXgvd29yay9wb2NrZXQ0LXN1Y2Nlc3Nvci1xYS1idWlsZC1iMzRmMTU4Zjg4YmJlYmYxMTI4NDBmZDg4ZGYyNWQwMy9idWlsZC1yZXN1bHQuanNvblwiLFwiLS1idWlsZC1yZWNlaXB0LXNoYTI1NlwiLFwiYzBkZDgxMTdjZGI3ZmE4YjU1MWUyYTU5YjQ2NmM5MWQ0OGVlMmYyZDlhOTg5MDhmNjliM2QzZmI4ODA3YmYzZFwiLFwiLS1hcGstc2hhMjU2XCIsXCIwMDZiM2JkZDY0ZmNkOGEwM2E0Y2VhYzBkMDM2YjNiOTk5MDYxNDBmZWFkZWU2MWQxOTg3NTZjYjZjNTVjOGQ5XCIsXCItLXNpZ25lci1jZXJ0aWZpY2F0ZS1zaGEyNTZcIixcImQ0OGQxMDMzNDJiNDI3OTFhZTRlOTI3ZDcwMjU4MDYyZDBkZTExZjlhY2I5ZjMyYjQ0MjZhZmY1ODNmMjdkNmZcIixcIi0tY2FzZVwiLFwiL2hvbWUvYWxleC93b3JrL3BvY2tldDQtc3VjY2Vzc29yLXFhLWZsb3ctYjZkZTJiZDRmMDRiY2Q1NzJhMDc0ZWY5ODRiYTdkYmUvcWEtY2xvc2UtYW5kLW9ic2VydmUtc2VhcmNoLTAxLmNhc2UuanNvblwiLFwiLS1jYXNlLXNoYTI1NlwiLFwiMjA0OWJkMTA3Mjc4ZjM5Y2FiNjZmY2NmMTRhNmQ5ZGRhNWM2NmRiNDA3MjM3NjFkOGViNjRiNDM2ZWU0YWU5NVwiLFwiLS1zdGVwXCIsXCJjbG9zZS1hbmQtb2JzZXJ2ZS1zZWFyY2gtMDFcIixcIi0tcmVjb3JkZXItcm9vdFwiLFwiL2hvbWUvYWxleC93b3JrL3BvY2tldDQtc3VjY2Vzc29yLXFhLXNvdXJjZS1iMzRmMTU4Zjg4YmJlYmYxMTI4NDBmZDg4ZGYyNWQwMy9yZWNvcmRlclwiLFwiLS1mbG93LWRpclwiLFwiL2hvbWUvYWxleC93b3JrL3BvY2tldDQtc3VjY2Vzc29yLXFhLWZsb3ctYjZkZTJiZDRmMDRiY2Q1NzJhMDc0ZWY5ODRiYTdkYmVcIixcIi0taGVscGVyLXVpZFwiLFwiMTAxNTdcIl0sXCJvcmlnaW5hbF9lbnRyeV9pbnZva2VkXCI6dHJ1ZSxcIm9yaWdpbmFsX3JldHVybmNvZGVcIjoyLFwib3JpZ2luYWxfc291cmNlc19tb2RpZmllZFwiOmZhbHNlLFwib3JpZ2luYWxfc3Rkb3V0XCI6XCJ7XFxcImFjdGlvbl9hdHRlbXB0ZWRcXFwiOiB0cnVlLCBcXFwiYXV0b21hdGljX3JldHJ5XFxcIjogZmFsc2UsIFxcXCJidXNpbmVzc19zdWNjZXNzX3ZlcmlmaWVkXFxcIjogZmFsc2UsIFxcXCJjYXNlX3NoYTI1NlxcXCI6IFxcXCIyMDQ5YmQxMDcyNzhmMzljYWI2NmZjY2YxNGE2ZDlkZGE1YzY2ZGI0MDcyMzc2MWQ4ZWI2NGI0MzZlZTRhZTk1XFxcIiwgXFxcImVuZGVkX3V0Y1xcXCI6IFxcXCIyMDI2LTExLTA2VDIwOjAxOjE3LjU2OTcyNyswMDowMFxcXCIsIFxcXCJlcG9jaF9zaGEyNTZcXFwiOiBcXFwiN2Q5Mjc4MTIzOTJkMzBhYjhjY2E0M2RhODdjMDc4NWUyNDY5NWNhNzI0ZGE5M2IzYjQ2NTEyMjUwMmI4MDQ1Y1xcXCIsIFxcXCJlcnJvcnNcXFwiOiBbe1xcXCJjb2RlXFxcIjogXFxcIkVYQUNUX1NVQ0NFU1NGVUxfRklOSVNIX1JFUVVJUkVEXFxcIiwgXFxcInR5cGVcXFwiOiBcXFwiUHJvdG9jb2xFcnJvclxcXCJ9XSwgXFxcIm9rXFxcIjogZmFsc2UsIFxcXCJvcmlnaW5hbF9hY3Rpb25fb3V0Y29tZXNfcmV3cml0dGVuXFxcIjogZmFsc2UsIFxcXCJvdXRjb21lX3Vua25vd25cXFwiOiB0cnVlLCBcXFwicHJvZHVjdGlvbl9yZWFkeVxcXCI6IGZhbHNlLCBcXFwic2NoZW1hXFxcIjogXFxcInBvY2tldDQtb3duZWQtc2NvcGVkLXFhLWNhc2UtcmVzdWx0LXYxXFxcIiwgXFxcInN0ZXBzXFxcIjogW3tcXFwiYWxsb3dzX25leHRfZGVjbGFyZWRfY2FzZV9kZWNpc2lvbl9vbmx5XFxcIjogdHJ1ZSwgXFxcImJ1c2luZXNzX3N1Y2Nlc3NfdmVyaWZpZWRcXFwiOiBmYWxzZSwgXFxcImluZGV4XFxcIjogMCwgXFxcIm1hdGNoZWRcXFwiOiB7XFxcIm5vZGVfcGF0aFxcXCI6IFxcXCIwLzAvMC8wLzAvMC8wLzEvMC8wLzEvMC8wLzEvMS8wLzAvMVxcXCIsIFxcXCJub2RlX3NoYTI1NlxcXCI6IFxcXCI3OTQwNjgyNDRlNGY0MTEyMzA5YjlmMDhlZTU2YTlmMDkyMjVkYzIwY2FkMzI2NzY3MjhkZTQ4NDY2OGY3ZDk3XFxcIiwgXFxcInRyZWVfc2hhMjU2XFxcIjogXFxcIjE5ZWQwMjAxNjE5YzZmOTY5NjY3OGE0NTM4NWUxODc5MTgzMjE0N2VhODA0YTI4ZWM4MjEwZjI1N2I0NjE3NGFcXFwiLCBcXFwid2luZG93X3NoYTI1NlxcXCI6IFxcXCIyZDA5NzNhM2NhNDI1MzVhNzk4OWM3Njc5MjY1ODdlMGJlMzg3YTc5YTZiMTM0NzdhZDg3NWQ0ZDQ4ZTBkNzczXFxcIn0sIFxcXCJvcmlnaW5hbF9hY3Rpb25fb3V0Y29tZVxcXCI6IFxcXCJ1bmtub3duX3JldGFpbmVkXFxcIiwgXFxcInBvc3Rfbm9uY2VcXFwiOiBcXFwiMjhkYWUxYjY5MzUwZDE4Y2JjNjI1MjA3ZmFkZjA5NzZcXFwiLCBcXFwicG9zdF93aXJlX3NoYTI1NlxcXCI6IFxcXCIzZjk2YzQ4MWRkYzhjOTUwNGJhOWE1OWY3ZWY4YjM1ODVlNGEwYTY0NTFhOTFlMmZiNmMxMjcxZmVmNDQ1MjkyXFxcIiwgXFxcInBvc3Rjb25kaXRpb25cXFwiOiB7XFxcImNsYXNzXFxcIjogXFxcImFuZHJvaWQud2lkZ2V0LlRleHRWaWV3XFxcIiwgXFxcImNsaWNrYWJsZVxcXCI6IHRydWUsIFxcXCJlbmFibGVkXFxcIjogdHJ1ZSwgXFxcInJlc291cmNlX2lkXFxcIjogXFxcImNvbS5saWFuamlhLmJlaWtlOmlkL3R2X25hdl9yaWdodF9zZWFyY2hfdGV4dFxcXCIsIFxcXCJ0ZXh0XFxcIjogXFxcIlxcXFx1NjQxY1xcXFx1N2QyMlxcXCJ9fV19XFxuXCIsXCJvcmlnaW5hbF9zdGRvdXRfYnl0ZXNcIjoxMzQwLFwib3JpZ2luYWxfc3Rkb3V0X3NoYTI1NlwiOlwiODY0YTk4M2VlZTkxN2EwZjcxYzFiYzEyYmM3MDM0NDYyYjA0MDc1NWI3ZWUzNjQ2YTE2Zjg0YjRlOWRlYmUzOVwiLFwib3V0Y29tZV91bmtub3duXCI6dHJ1ZSxcInBlcm1pc3Npb25fY2hhbmdlc1wiOjAsXCJwcm9kdWN0aW9uX3JlYWR5XCI6ZmFsc2UsXCJyZWNvbmNpbGlhdGlvbl9wdWJsaXNoZWRcIjpmYWxzZSxcInJlcXVlc3RcIjp7XCJieXRlc1wiOjE4MDgsXCJwYXRoXCI6XCIvaG9tZS9hbGV4L3dvcmsvcG9ja2V0NC1iZWlrZS1vd25lZC11aS1yZXVzYWJsZS0yMDI2MTEwNi1yMS9yZXF1ZXN0LTU4ODY3ODFjODJlOWUzOTJkOGUxZmYzM2I5NWIyOGJiNWRiYTYxNTAxMWE1MGViNTNjYzJkMWQ5MDNjMDI2YWYuanNvblwiLFwic2hhMjU2XCI6XCI1ODg2NzgxYzgyZTllMzkyZDhlMWZmMzNiOTViMjhiYjVkYmE2MTUwMTFhNTBlYjUzY2MyZDFkOTAzYzAyNmFmXCJ9LFwic2NoZW1hXCI6XCJwb2NrZXQ0LWZpeGVkLXJldXNhYmxlLW93bmVkLXVpLWNoaWxkLXYxXCIsXCJzb3VyY2VcIjp7XCJieXRlc1wiOjI1Mzc3LFwicGF0aFwiOlwiL2hvbWUvYWxleC93b3JrL3BvY2tldDQtYmVpa2Utb3duZWQtdWktcmV1c2FibGUtMjAyNjExMDYtcjEvb3duZWRfdWlfcmVxdWVzdF9vbmNlLnB5XCIsXCJzaGEyNTZcIjpcImMzOTQ1OThlNDc3ZjE5MTIzNzhjNmMzZDU4Mjg1MGExOTZlNjRmNzc3OTFkMGI3ZjVjNGQ0OThlYzliNjFlMzhcIn0sXCJzdGVwXCI6XCJjbG9zZS1hbmQtb2JzZXJ2ZS1zZWFyY2gtMDFcIixcInRhc2tcIjo4Nzh9XG4iLCJjaGlsZF9zdGRvdXRfc2hhMjU2IjoiMTA5ZGM5ZDA0NmE1OGMxMjE1NWRiNzYxNWQ4NjExZmRkYjhhNjFmYTA1MzQxYjY2ZmRiODU0MDcyMGM5ZTI0YiIsImNsZWFudXBfb3JfZm9jdXNfYWN0aW9ucyI6MCwiZXJyb3JzIjpbeyJyZWFzb24iOiJOT1JNQUxfT1JJR0lOQUxfQ0hJTERfTElGRVRJTUVfUkVRVUlSRUQiLCJ0eXBlIjoiUnVudGltZUVycm9yIn1dLCJmbG93IjoiL2hvbWUvYWxleC93b3JrL3BvY2tldDQtc3VjY2Vzc29yLXFhLWZsb3ctYjZkZTJiZDRmMDRiY2Q1NzJhMDc0ZWY5ODRiYTdkYmUiLCJpbnN0YWxscyI6MCwibmF0aXZlX2xhdW5jaGVzIjowLCJvayI6ZmFsc2UsIm9sZF9wcm9kdWN0c19kZWxldGVkIjpmYWxzZSwib3JpZ2luYWxfVU5LTk9XTl9yZXdyaXR0ZW4iOmZhbHNlLCJvdXRjb21lX3Vua25vd24iOnRydWUsInBlcm1pc3Npb25fY2hhbmdlcyI6MCwicHJvZHVjdGlvbl9yZWFkeSI6ZmFsc2UsInJlY29uY2lsaWF0aW9uX3B1Ymxpc2hlZCI6ZmFsc2UsInJlcXVlc3QiOnsiYnl0ZXMiOjE4MDgsInBhdGgiOiIvaG9tZS9hbGV4L3dvcmsvcG9ja2V0NC1iZWlrZS1vd25lZC11aS1yZXVzYWJsZS0yMDI2MTEwNi1yMS9yZXF1ZXN0LTU4ODY3ODFjODJlOWUzOTJkOGUxZmYzM2I5NWIyOGJiNWRiYTYxNTAxMWE1MGViNTNjYzJkMWQ5MDNjMDI2YWYuanNvbiIsInNoYTI1NiI6IjU4ODY3ODFjODJlOWUzOTJkOGUxZmYzM2I5NWIyOGJiNWRiYTYxNTAxMWE1MGViNTNjYzJkMWQ5MDNjMDI2YWYifSwic2NoZW1hIjoicG9ja2V0NC1maXhlZC1yZXVzYWJsZS1vd25lZC11aS1yZXN1bHQtdjEiLCJzb3VyY2UiOnsiYnl0ZXMiOjI1Mzc3LCJwYXRoIjoiL2hvbWUvYWxleC93b3JrL3BvY2tldDQtYmVpa2Utb3duZWQtdWktcmV1c2FibGUtMjAyNjExMDYtcjEvb3duZWRfdWlfcmVxdWVzdF9vbmNlLnB5Iiwic2hhMjU2IjoiYzM5NDU5OGU0NzdmMTkxMjM3OGM2YzNkNTgyODUwYTE5NmU2NGY3Nzc5MWQwYjdmNWM0ZDQ5OGVjOWI2MWUzOCJ9LCJ0YXNrIjo4Nzh9Cg==', 'actual_stdout_sha256': '78ab558a72b5cb14ad00d6d74c978a935272d9252cd13e6a66215dbac1a3abe2', 'terminal_base64': 'ewogICJhdF91bml4X21zIjogMTc5Mzk5NTI3NzYyMSwKICAiYXVkaXRfcmVjb3JkZWQiOiB0cnVlLAogICJhdXRvbWF0aWNfcmV0cnkiOiBmYWxzZSwKICAiY2FuY2VsbGVkIjogZmFsc2UsCiAgImV4aXRfY29kZSI6IDEsCiAgImpvYl9pZCI6ICIxYTFiMjcyZWM5ZC1mYzA1LTdlMGQiLAogICJsYXVuY2hfbm9uY2UiOiAiMWE5NGI4YzA4NGUyNWUzMzliMjhlY2QxNzI5MTUzZGQiLAogICJsb2dfYnl0ZXMiOiB7CiAgICAic3RkZXJyIjogewogICAgICAic2VlbiI6IDAsCiAgICAgICJzdG9yZWQiOiAwCiAgICB9LAogICAgInN0ZG91dCI6IHsKICAgICAgInNlZW4iOiA1OTIwLAogICAgICAic3RvcmVkIjogNTkyMAogICAgfQogIH0sCiAgImxvZ19lcnJvcnMiOiB7CiAgICAic3RkZXJyIjogbnVsbCwKICAgICJzdGRvdXQiOiBudWxsCiAgfSwKICAibG9nX3N5bmNlZCI6IHsKICAgICJzdGRlcnIiOiB0cnVlLAogICAgInN0ZG91dCI6IHRydWUKICB9LAogICJsb2dfdHJ1bmNhdGVkIjogewogICAgInN0ZGVyciI6IGZhbHNlLAogICAgInN0ZG91dCI6IGZhbHNlCiAgfSwKICAib3V0cHV0X2NvbXBsZXRlIjogdHJ1ZSwKICAib3V0cHV0X2R1cmFibGUiOiB0cnVlLAogICJzdGF0ZSI6ICJmYWlsZWQiLAogICJ0ZXJtaW5hbF9wdWJsaWNhdGlvbl9jb25maXJtZWQiOiB0cnVlLAogICJ0ZXJtaW5hbF9wdWJsaWNhdGlvbl9wcm90b2NvbCI6IDEsCiAgInRpbWVkX291dCI6IGZhbHNlCn0=', 'terminal_bytes': 728, 'terminal_sha256': '0f6c8209f05831b056fc35bb5c8a94dc5b1fb583d99e724e0c38aab104e5b088', 'child_stdout_sha256': '109dc9d046a58c12155db7615d8611fddb8a61fa05341b66fdb8540720c9e24b', 'original_case_stdout_sha256': '864a983eee917a0f71c1bc12bc7034462b040755b7ee3646a16f84b4e9debe39'}  # Filled once from actual local originals, preserving Python ints.
BASE = {'path': '/home/alex/work/pocket4-beike-owned-cleanup-20261106-r1/cleanup_owned_task_once.py', 'bytes': 22233, 'sha256': '559ae3641a5f6e017914102af61c5f8e909605cb92be32d1a045ae7c66a935cf'}
FLOW = '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe'
STEP = 'close-and-observe-search-01'
OUTPUT = '/home/alex/work/pocket4-beike-case-failure-evidence-20261106-r1'
HELPER = 'org.droidloom.qa.successor.p8f89f253350ba2fa.r1'
HELD_HELPER = '/home/alex/work/pocket4-owned-held-ns-runner-r4-01/held-namespace-entry'
EPOCH = '7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_rdev',
          'st_size', 'st_mtime_ns', 'st_ctime_ns')
MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('ascii')


def load_base():
    """Bootstrap only the already deployed exact root-owned utility module."""
    path = Path(BASE['path']); fds = []
    try:
        parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC); fds.append(parent)
        for name in path.parts[1:-1]:
            parent = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            fds.append(parent)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent); fds.append(fd)
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1 and
             not before.st_mode & 0o022 and before.st_size == BASE['bytes'], 'EXACT_ROOT_UTILITY_FILE')
        raw = bytearray()
        while len(raw) <= before.st_size:
            part = os.read(fd, before.st_size + 1 - len(raw))
            if not part:
                break
            raw.extend(part)
        after, named = os.fstat(fd), os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        keys = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        need(len(raw) == BASE['bytes'] and sha(raw) == BASE['sha256'] and
             all(getattr(before, key) == getattr(after, key) == getattr(named, key) for key in keys), 'UTILITY_SOURCE_CHANGED')
    finally:
        for fd in reversed(fds):
            os.close(fd)
    module = types.ModuleType('unchanged_cleanup_utilities_only'); module.__file__ = str(path)
    exec(compile(bytes(raw), str(path), 'exec'), module.__dict__)
    return module


def census():
    """Close listdir's transient directory FD before inspecting persistent FDs."""
    names = os.listdir('/proc/self/fd')
    rows = {}
    for name in sorted(names, key=int):
        need(name.isdigit(), 'PROC_FD_NAME')
        fd = int(name)
        try:
            first = os.fstat(fd)
        except OSError as error:
            # listdir's own already-closed descriptor is the sole allowed skip.
            need(error.errno == 9 and not os.path.lexists('/proc/self/fd/' + name),
                 'FD_CENSUS_UNSTABLE_OR_REUSED')
            continue
        link = os.readlink('/proc/self/fd/' + name)
        flags = fcntl.fcntl(fd, fcntl.F_GETFD)
        after = os.fstat(fd)
        identity = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_rdev')
        need(all(getattr(first, key) == getattr(after, key) for key in identity) and
             link == os.readlink('/proc/self/fd/' + name) and
             flags == fcntl.fcntl(fd, fcntl.F_GETFD), 'FD_CHANGED_DURING_CENSUS')
        rows[name] = {'link': link, 'flags': flags,
                      **{key: getattr(first, key) for key in identity}}
    return rows


def phases(case):
    rows = []
    need(case['name'] == 'beike-close-and-observe-search-01' and len(case['steps']) == 2,
         'ONLY_THE_ACTUAL_TWO_STEP_CASE')
    for index, item in enumerate(case['steps']):
        for kind, plan in (('operation', item['plan']), ('post_inspection', item['post_inspection'])):
            need(plan['operation'] == ('click' if kind == 'operation' else 'inspect'), 'FIXED_CASE_OPERATIONS')
            for phase in ('before', 'inspect', 'action', 'after'):
                if phase == 'action' and kind == 'post_inspection':
                    continue
                nonce = plan['nonces'][phase]
                need(type(nonce) is str and re.fullmatch('[0-9a-f]{32}', nonce), 'EXACT_NONCE')
                rows.append({'index': index, 'kind': kind, 'phase': phase, 'nonce': nonce,
                             'op': 'state' if phase in ('before', 'after') else
                             'inspect' if phase == 'inspect' else plan['operation']})
    need(len(rows) == len({row['nonce'] for row in rows}) == 14, 'ALL_FOURTEEN_DISTINCT_DECLARED_NONCES')
    return rows


def allowed_name(name, phase_rows):
    fixed = {'intent.json', 'result.json', 'held-main-binding.json'}
    fixed |= {'case-%02d-%s.json' % (i, kind) for i in range(2)
              for kind in ('operation', 'postcondition')}
    fixed |= {row['nonce'] + suffix for row in phase_rows
              for suffix in ('.request.json', '.assessment.json', '.failed-assessment.json')}
    if name in fixed:
        return True
    match = re.fullmatch(r'command-([0-9]{3})\.(intent\.json|result\.json|stdout|stderr)', name)
    if match:
        return 1 <= int(match[1]) <= 38
    match = re.fullmatch(r'transport-([0-9]{3})\.(intent|command-result|verified-result|failure)\.json', name)
    return bool(match and 1 <= int(match[1]) <= 50)


def names_checked(names, phase_rows):
    need(type(names) is list and 3 <= len(names) <= 400 and len(set(names)) == len(names) and
         {'intent.json', 'result.json', 'held-main-binding.json'} <= set(names) and
         all(type(name) is str and allowed_name(name, phase_rows) for name in names),
         'ONLY_FIXED_CASE_STEP_FILENAMES_NO_OTHER_CONTENT')
    return sorted(names)


def open_dir(path, owned):
    """Walk every component without symlinks; the final directory is private."""
    need(path.startswith('/') and str(Path(path)) == path and '..' not in Path(path).parts,
         'EXACT_ABSOLUTE_DIRECTORY')
    current = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC); owned.append(current)
    for name in Path(path).parts[1:]:
        current = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                          dir_fd=current)
        owned.append(current)
    row = os.fstat(current)
    need(stat.S_ISDIR(row.st_mode) and row.st_uid == 0 and not row.st_mode & 0o077,
         'EXACT_ROOT_PRIVATE_DIRECTORY')
    return current


def info(row):
    return {key: getattr(row, key) for key in FIELDS}


def safe_error(error):
    message = str(error)
    return {'type': type(error).__name__,
            'code': message if re.fullmatch('[A-Z0-9_]{1,128}', message) else 'OFFLINE_CHECK_REJECTED'}


def validate_actual(core):
    raw = base64.b64decode(CONFIG['actual_stdout_base64'], validate=True)
    terminal_raw = base64.b64decode(CONFIG['terminal_base64'], validate=True)
    need(len(raw) == 5920 and sha(raw) == CONFIG['actual_stdout_sha256'] and
         len(terminal_raw) == CONFIG['terminal_bytes'] and sha(terminal_raw) == CONFIG['terminal_sha256'],
         'EMBEDDED_ORIGINAL_CONTROLLER_EVIDENCE_BYTES')
    outer, terminal = core.document(raw), core.document(terminal_raw)
    need(terminal['job_id'] == '1a1b272ec9d-fc05-7e0d' and terminal['state'] == 'failed' and
         terminal['exit_code'] == 1 and all(terminal[key] is True for key in
         ('audit_recorded', 'output_complete', 'output_durable', 'terminal_publication_confirmed')) and
         all(terminal[key] is False for key in ('timed_out', 'cancelled', 'automatic_retry')) and
         terminal['log_bytes'] == {'stdout': {'seen': 5920, 'stored': 5920}, 'stderr': {'seen': 0, 'stored': 0}} and
         terminal['log_synced'] == {'stdout': True, 'stderr': True} and
         terminal['log_truncated'] == {'stdout': False, 'stderr': False} and
         terminal['log_errors'] == {'stdout': None, 'stderr': None}, 'ACTUAL_DURABLE_FAILURE_NOT_RECLASSIFIED')
    need(outer['schema'] == 'pocket4-fixed-reusable-owned-ui-result-v1' and
         outer['ok'] is False and outer['outcome_unknown'] is True and outer['flow'] == FLOW and
         outer['task'] == 878 and outer['source'] == CONFIG['sources']['worker'] and
         outer['request'] == CONFIG['request'] and outer['reconciliation_published'] is False and
         outer['original_UNKNOWN_rewritten'] is False, 'ORIGINAL_FAILED_OUTER_AND_UNKNOWN_RETAINED')
    life = outer['child_lifecycle']
    need(life == {'child_pid': 1596573, 'errors': [], 'owned_child_sigkill_count': 0,
          'parent_descriptors_restored': True, 'pidfd_acquired': True, 'pidfd_closed': True,
          'pidfd_exit_observed': True, 'returncode': 1, 'timeout': False} and
         outer['child_stderr_original'] == '' and outer['child_stderr_bytes'] == 0 and
         outer['child_stderr_sha256'] == sha(b''), 'ACTUAL_NORMAL_FAILED_CHILD_RETIRED_NOT_SUCCESSFUL')
    child_raw = outer['child_stdout_original'].encode('utf-8')
    need(len(child_raw) == outer['child_stdout_bytes'] == 4046 and
         sha(child_raw) == outer['child_stdout_sha256'] == CONFIG['child_stdout_sha256'],
         'ORIGINAL_CHILD_BYTES')
    child = core.document(child_raw)
    need(child['ok'] is False and child['original_returncode'] == 2 and child['step'] == STEP and
         child['flow'] == FLOW and child['task'] == 878 and child['kind'] == 'case' and
         child['declared_mutation'] is True and child['original_entry_invoked'] is True and
         child['outcome_unknown'] is True and child['source'] == CONFIG['sources']['worker'] and
         child['request'] == CONFIG['request'], 'FAILED_ORIGINAL_CASE_ENTRY_NOT_RETRIED')
    original_raw = child['original_stdout'].encode('utf-8')
    need(len(original_raw) == child['original_stdout_bytes'] == 1340 and
         sha(original_raw) == child['original_stdout_sha256'] == CONFIG['original_case_stdout_sha256'],
         'ORIGINAL_CASE_STDOUT_BYTES')
    original = core.document(original_raw)
    need(original['schema'] == 'pocket4-owned-scoped-qa-case-result-v1' and original['ok'] is False and
         original['action_attempted'] is True and original['outcome_unknown'] is True and
         original['epoch_sha256'] == EPOCH and original['case_sha256'] == CONFIG['case']['sha256'] and
         original['errors'] == [{'code': 'EXACT_SUCCESSFUL_FINISH_REQUIRED', 'type': 'ProtocolError'}] and
         len(original['steps']) == 1 and original['steps'][0]['index'] == 0,
         'ACTUAL_PARTIAL_CASE_AND_STRICT_FINISH_REJECTION')
    return original, life


def analyze(files, core, qa, transport, phase_rows, case, expected_result):
    """Content-free diagnosis; no result here is a reconciliation proof."""
    read = lambda name: core.document(files[name])
    result, intent, binding = read('result.json'), read('intent.json'), read('held-main-binding.json')
    need(result == expected_result and intent['operation'] == 'owned-qa-case' and
         intent['mutation'] is True and intent['request']['case'] == case and
         intent['request']['case_sha256'] == CONFIG['case']['sha256'] and
         intent['scope'] == core.document(CONFIG['scope_raw']) and intent['automatic_retry'] is False,
         'SAVED_STEP_MATCHES_ACTUAL_FAILED_CASE_AND_SCOPE')
    core.fixed_build(intent['request']['build'])
    core.held_binding_identity(binding)
    need(binding['framework_epoch_sha256'] == EPOCH and binding['package'] == qa.PACKAGE and
         binding['uid'] == qa.UID and binding['runtime_epoch_sha256'] == qa.RUNTIME_EPOCH and
         binding['app_scope_sha256'] == qa.APP_SCOPE_SHA, 'RECORDED_HELD_RUNTIME_APP_BINDING')
    commands, command_by_hash = [], {}
    indices = sorted({int(name[8:11]) for name in files if name.startswith('command-')})
    need(indices == list(range(1, len(indices) + 1)), 'SEQUENTIAL_ORIGINAL_COMMAND_PREFIX')
    requests = {row['nonce']: read(row['nonce'] + '.request.json') for row in phase_rows
                if row['nonce'] + '.request.json' in files}
    known = [(['/system/bin/cmd', 'package', 'list', 'packages', '-U', '--user', '0', HELPER], 8, False, 'helper_uid'),
             (['/system/bin/cmd', 'package', 'path', '--user', '0', HELPER], 8, False, 'helper_apk_path'),
             (['/system/bin/cmd', 'activity', 'stack', 'list'], 20, False, 'task_list')]
    for nonce, request in requests.items():
        qa.validate_request(request)
        known.append((qa.instrumentation_argv(request), 20, request['op'] in ('click', 'set_text'), nonce))
    routes = []
    for index in indices:
        stem = 'command-%03d' % index
        need(all(stem + suffix in files for suffix in ('.intent.json', '.result.json', '.stdout', '.stderr')),
             'COMPLETE_ORIGINAL_COMMAND_FILES')
        ci, cr = read(stem + '.intent.json'), read(stem + '.result.json')
        out, err = files[stem + '.stdout'], files[stem + '.stderr']
        matches = []
        for argv, timeout, mutation, label in known:
            try:
                route = core.command_argv(ci, argv, timeout, HELD_HELPER, binding['classpath']['values'], transport)
            except Exception:
                continue
            matches.append((argv, timeout, mutation, label, route))
        need(len(matches) == 1, 'ONE_ORIGINAL_DECLARED_COMMAND')
        argv, timeout, mutation, label, route = matches[0]
        need(route['parent_pid'] == 1596573 and (not routes or route == routes[0]), 'ACTUAL_ONE_HELD_CHILD_AUTHORITY')
        routes.append(route)
        need(cr['stdout_sha256'] == sha(out) and cr['stderr_sha256'] == sha(err), 'COMPLETE_RAW_STREAM_HASHES')
        normal = (cr.get('returncode') == 0 and cr.get('spawned') is True and
                  cr.get('owned_command_joined') is True and cr.get('timed_out') is False and
                  cr.get('error') is None and cr.get('errors') == [] and not err)
        if normal:
            core.command_success(ci, cr, out, err, mutation, timeout)
        row = {'index': index, 'kind_or_nonce': label, 'mutation': mutation,
               'normal_zero_joined': normal, 'result_sha256': sha(files[stem + '.result.json']),
               'stdout_bytes': len(out), 'stderr_bytes': len(err), 'stdout_sha256': sha(out),
               'stderr_sha256': sha(err), 'recorded_returncode': cr.get('returncode'),
               'recorded_joined': cr.get('owned_command_joined'), 'recorded_timeout': cr.get('timed_out'),
               'recorded_action_attempted': cr.get('action_attempted')}
        commands.append(row)
        need(row['result_sha256'] not in command_by_hash, 'UNIQUE_ACTUAL_COMMAND_RESULT_HASH')
        command_by_hash[row['result_sha256']] = (stem, ci, cr, out, err, row, argv)
    transport_rows = []
    tindices = sorted({int(name[10:13]) for name in files if name.startswith('transport-')})
    need(tindices == list(range(1, len(tindices) + 1)), 'SEQUENTIAL_ORIGINAL_TRANSPORT_PREFIX')
    command_offset = 0
    private_hash = sha(json.dumps(['/system/bin/dumpsys', 'window', 'displays'],
                                 ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    for index in tindices:
        stem = 'transport-%03d' % index
        need(stem + '.intent.json' in files, 'ORIGINAL_TRANSPORT_INTENT_PRESENT')
        ti = read(stem + '.intent.json')
        need(ti['sequence'] == index and ti['epoch_sha256'] == EPOCH and ti['package'] == qa.PACKAGE and
             ti['uid'] == qa.UID and ti['automatic_retry'] is False and ti['numeric_pid_target_used'] is False,
             'ORIGINAL_TRANSPORT_SCOPE')
        private = ti['command_sha256'] == private_hash
        if private:
            need(ti['timeout_seconds'] == 15 and ti['inner_timeout_seconds'] == 10,
                 'ONLY_ORIGINAL_PRIVATE_FOREGROUND_TRANSPORT')
        else:
            need(command_offset < len(commands), 'TRANSPORT_TO_ORIGINAL_COMMAND_COUNT')
            row = commands[command_offset]; command_offset += 1
            data = command_by_hash[row['result_sha256']]
            need(ti['command_sha256'] == sha(json.dumps(data[6], ensure_ascii=False,
                 separators=(',', ':')).encode('utf-8')) and ti['timeout_seconds'] == data[1]['timeout_seconds'],
                 'TRANSPORT_TO_EXACT_RECORDED_COMMAND')
        tc = read(stem + '.command-result.json') if stem + '.command-result.json' in files else None
        tv = read(stem + '.verified-result.json') if stem + '.verified-result.json' in files else None
        tf = read(stem + '.failure.json') if stem + '.failure.json' in files else None
        need(not (tv and tf), 'NO_BOTH_SUCCESS_AND_FAILED_TRANSPORT')
        for observation in (tc, tv, tf):
            if observation is not None:
                need(all(observation.get(key) == value for key, value in ti.items()), 'TRANSPORT_IDENTITY_PRESERVED')
        if tv is not None:
            need(tc == tv and tv['returncode'] == 0 and tv['outcome_unknown'] is False and
                 tv['action_attempted'] is True, 'ORIGINAL_VERIFIED_RETURN_AND_POST_GUARD')
        if tc is not None and not private:
            need(tc.get('stdout_bytes') == data[5]['stdout_bytes'] and tc.get('stderr_bytes') == data[5]['stderr_bytes'] and
                 tc.get('stdout_sha256') == data[5]['stdout_sha256'] and tc.get('stderr_sha256') == data[5]['stderr_sha256'] and
                 tc.get('returncode') == data[2]['returncode'], 'TRANSPORT_COMPLETE_RAW_BINDING')
        transport_rows.append({'sequence': index, 'private_foreground_raw_not_persisted': private,
            'command_result_present': tc is not None, 'verified_result_present': tv is not None,
            'failure_present': tf is not None, 'returncode': None if tc is None else tc.get('returncode'),
            'outcome_unknown': None if tc is None else tc.get('outcome_unknown'),
            'stdout_bytes': None if tc is None else tc.get('stdout_bytes'),
            'stdout_sha256': None if tc is None else tc.get('stdout_sha256')})
    need(command_offset == len(commands), 'ALL_RECORDED_COMMANDS_HAVE_TRANSPORT_INTENTS')
    phase_results, qualified = [], {}
    for phase in phase_rows:
        row = dict(phase); nonce = phase['nonce']
        req_name, ok_name, fail_name = (nonce + suffix for suffix in
                                      ('.request.json', '.assessment.json', '.failed-assessment.json'))
        row.update(request_present=req_name in files, assessment_present=ok_name in files,
                   failed_assessment_present=fail_name in files)
        need(not (row['assessment_present'] and row['failed_assessment_present']), 'NONCE_HAS_ONE_OBSERVED_OUTCOME')
        if row['request_present']:
            request = requests[nonce]
            need(request['nonce'] == nonce and request['op'] == phase['op'], 'DECLARED_NONCE_PHASE_IDENTITY')
        else:
            need(not row['assessment_present'] and not row['failed_assessment_present'], 'NO_ASSESSMENT_WITHOUT_REQUEST')
        if row['assessment_present'] or row['failed_assessment_present']:
            saved = read(ok_name if row['assessment_present'] else fail_name)
            key = 'recorder_command_result_sha256' if row['assessment_present'] else 'command_result_sha256'
            need(saved[key] in command_by_hash, 'ONE_REAL_NONCE_COMMAND_RESULT')
            stem, ci, cr, out, err, cmdrow, argv = command_by_hash[saved[key]]
            need(cmdrow['kind_or_nonce'] == nonce, 'ASSESSMENT_COMMAND_IS_ITS_EXACT_NONCE')
            row['command_index'] = cmdrow['index']
            if row['assessment_present']:
                again = qa.parse_completed(out, err, cr['returncode'], request, 10157)
                again.update(recorder_command_result_sha256=saved[key], held_transport_returned_after_post_guard=True)
                need(again == saved, 'UNCHANGED_SUCCESS_ASSESSMENT_REPARSED_FROM_RAW')
                qualified[nonce] = again
                row.update(reparsed_success=True, wire_sha256=again['wire_sha256'],
                           helper_action_attempted=again['helper']['action_attempted'],
                           helper_outcome_unknown=again['helper']['outcome_unknown'])
            else:
                try:
                    qa.parse_completed(out, err, cr['returncode'], request, 10157)
                except Exception as failure:
                    need(saved['primary_error'] == {'type': type(failure).__name__, 'message': str(failure)},
                         'ORIGINAL_STRICT_FAILURE_REPRODUCED')
                    row['original_primary_error'] = safe_error(failure)
                else:
                    raise RuntimeError('FAILED_ASSESSMENT_CANNOT_RECLASSIFY_AS_SUCCESS')
                need(saved['request_nonce'] == nonce and saved['operation'] == phase['op'] and
                     saved['qualified_success'] is False and saved['stdout_sha256'] == sha(out) and
                     saved['stderr_sha256'] == sha(err), 'ORIGINAL_FAILURE_METADATA_AND_RAW_BINDING')
                try:
                    diagnostic = qa.failure_diagnostic(out, request, 10157)
                except Exception as diagnostic_error:
                    need(saved.get('diagnostic_unavailable') == type(diagnostic_error).__name__,
                         'ORIGINAL_FAILURE_DIAGNOSTIC_AVAILABILITY')
                    row['diagnostic_unavailable'] = type(diagnostic_error).__name__
                else:
                    need(saved.get('helper_rejection') == diagnostic, 'ORIGINAL_HELPER_REJECTION_REPARSED')
                    row['helper_rejection'] = diagnostic
        phase_results.append(row)
    post_name = 'case-00-postcondition.json'
    need(post_name in files and read(post_name) == result['steps'][0], 'ORIGINAL_FIRST_POSTCONDITION_RECEIPT')
    post = read(post_name); post_nonce = case['steps'][0]['post_inspection']['nonces']['inspect']
    need(post_nonce in qualified and post['post_nonce'] == post_nonce and
         post['post_wire_sha256'] == qualified[post_nonce]['wire_sha256'], 'FIRST_POST_INSPECT_ORIGINAL_RAW_BINDING')
    matched = core.match_postcondition(qa, qualified[post_nonce]['helper']['inspection'], case['steps'][0]['postcondition'])
    need(post['matched'] == {key: matched[key] for key in ('node_path', 'node_sha256', 'tree_sha256', 'window_sha256')},
         'FIRST_POSTCONDITION_RECOMPUTED_WITHOUT_EXPORTING_NODE_CONTENT')
    return {'commands': commands, 'transports': transport_rows, 'phases': phase_results,
            'first_declared_postcondition_reparsed': True,
            'later_case_operation_file_present': 'case-01-operation.json' in files,
            'later_postcondition_file_present': 'case-01-postcondition.json' in files,
            'all_recorded_commands_normal_zero_joined': all(row['normal_zero_joined'] for row in commands),
            'all_recorded_transports_verified': all(row['verified_result_present'] for row in transport_rows),
            'failure_remains_unknown': True, 'new_action_authority': False}


def run(source_sha):
    need(os.getuid() == os.geteuid() == 0, 'ROOT_HOST_READER_REQUIRED')
    before = census(); end = time.monotonic() + 120
    base = load_base(); observed = {}; total = 0

    def retain(key, path, pin=None):
        nonlocal total
        need(key not in observed and time.monotonic() < end, 'ONE_FINITE_READ_AND_DEADLINE')
        raw, identity = base.read(path, MAX_FILE)
        need(time.monotonic() < end, 'READ_COMPLETED_INSIDE_TOTAL_DEADLINE')
        total += len(raw); need(total <= MAX_TOTAL, 'TOTAL_ORIGINAL_BYTES_BOUND')
        if pin is not None:
            need(path == pin['path'] and len(raw) == pin['bytes'] and sha(raw) == pin['sha256'], 'EXACT_SOURCE_OR_INPUT_PIN')
        observed[key] = {'path': path, 'body': raw, 'stat': identity}
        return raw

    modules = {}
    for label, pin in CONFIG['sources'].items():
        raw = retain('source/' + label, pin['path'], pin)
        if label in ('core', 'qa', 'transport'):
            value = types.ModuleType('fixed_offline_' + label); value.__file__ = pin['path']
            exec(compile(raw, pin['path'], 'exec'), value.__dict__); modules[label] = value
    core, qa, transport = (modules[key] for key in ('core', 'qa', 'transport'))
    expected_result, life = validate_actual(core)
    for label in ('scope', 'launch', 'case', 'request'):
        pin = CONFIG[label]
        raw = retain('input/' + label, pin['path'], pin)
        if label == 'scope':
            CONFIG['scope_raw'] = raw
            core.fixed_scope(core.document(raw))
        elif label == 'case':
            case = core.document(raw)
        elif label == 'launch':
            launch = core.document(raw)
            need(launch['task'] == 878 and launch['package'] == qa.PACKAGE and launch['epoch_sha256'] == EPOCH and
                 launch['prelaunch_absent'] is True and launch['cleanup_allowed'] is True,
                 'ACTUAL_TASK878_NATIVE_LAUNCH_SCOPE')
    phase_rows = phases(case)
    owned = []; files = {}; names = None
    try:
        folder = FLOW + '/steps/' + STEP
        directory = open_dir(folder, owned)
        original_dir = info(os.fstat(directory))
        names = names_checked(os.listdir(directory), phase_rows)
        for name in names:
            files[name] = retain('step/' + name, folder + '/' + name)
        need(sorted(os.listdir(directory)) == names and info(os.fstat(directory)) == original_dir and
             info(os.stat(folder, follow_symlinks=False)) == original_dir, 'ORIGINAL_STEP_DIRECTORY_UNCHANGED')
        # Recheck every byte and complete stat before publishing the private copy.
        for key, row in observed.items():
            need(time.monotonic() < end, 'FINAL_ORIGINAL_RECHECK_DEADLINE')
            again, identity = base.read(row['path'], MAX_FILE)
            need(again == row['body'] and identity == row['stat'], 'ORIGINAL_BYTES_OR_STAT_CHANGED')
        need(sorted(os.listdir(directory)) == names and info(os.fstat(directory)) == original_dir and
             info(os.stat(folder, follow_symlinks=False)) == original_dir, 'FINAL_STEP_DIRECTORY_UNCHANGED')
    finally:
        for fd in reversed(owned):
            os.close(fd)
    need(census() == before, 'ALL_READ_DESCRIPTORS_CLOSED_EXACTLY')
    # Preserve the exact evidence even if offline semantic diagnosis rejects it.
    bundle = {'schema': 'pocket4-task878-failed-case-private-original-bytes-v1', 'flow': FLOW, 'step': STEP,
        'actual_job': '1a1b272ec9d-fc05-7e0d', 'full_original_bytes': True, 'contains_private_UI_evidence': True,
        'approved_for_Git': False, 'files': {key: {'path': row['path'], 'bytes': len(row['body']),
        'sha256': sha(row['body']), 'stat': row['stat'], 'base64': base64.b64encode(row['body']).decode('ascii')}
        for key, row in sorted(observed.items())}, 'step_file_set': names,
        'original_stdout': {'bytes': 5920, 'sha256': CONFIG['actual_stdout_sha256'],
                            'base64': CONFIG['actual_stdout_base64']},
        'original_terminal': {'bytes': CONFIG['terminal_bytes'], 'sha256': CONFIG['terminal_sha256'],
                              'base64': CONFIG['terminal_base64']}}
    raw_bundle = canonical(bundle) + b'\n'; need(len(raw_bundle) <= 48 * 1024 * 1024, 'PRIVATE_BUNDLE_BYTE_BOUND')
    result = {'schema': 'pocket4-task878-failed-case-host-diagnostic-v1', 'ok': True,
        'collection_completed': True, 'source_sha256': source_sha, 'historical_job': '1a1b272ec9d-fc05-7e0d',
        'original_stdout_sha256': CONFIG['actual_stdout_sha256'], 'original_terminal_sha256': CONFIG['terminal_sha256'],
        'flow': FLOW, 'step': STEP, 'task': 878, 'files': len(observed), 'original_bytes': total,
        'step_file_count': len(names), 'old_UNKNOWN_modified': False, 'original_case_success': False,
        'reconciliation_published': False, 'production_ready': False, 'current_action_authority': False,
        'original_file_bytes_and_stat_unchanged': True, 'Main_commands': 0, 'namespace_entries': 0,
        'Main_locks_or_guards': 0, 'UI_actions': 0, 'signals': 0, 'installs': 0, 'permission_changes': 0,
        'automatic_retry': False, 'originals_modified': False, 'private_UI_content_in_stdout': False,
        'only_new_private_evidence_files_written': True, 'original_child_lifecycle': life,
        'diagnosis_completed': False, 'diagnosis_error': None}
    try:
        result['diagnosis'] = analyze(files, core, qa, transport, phase_rows, case, expected_result)
        result['diagnosis_completed'] = True
    except Exception as error:
        result['diagnosis_error'] = safe_error(error)
    need(time.monotonic() < end and census() == before, 'DIAGNOSIS_FINISHED_WITHOUT_NEW_RESOURCES')
    output_owned = []
    try:
        # Parent is an existing operator-owned work directory, not required root-private.
        current = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC); output_owned.append(current)
        for name in Path(OUTPUT).parent.parts[1:]:
            current = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=current)
            output_owned.append(current)
        parent = current
        os.mkdir(Path(OUTPUT).name, 0o700, dir_fd=parent)
        outdir = os.open(Path(OUTPUT).name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        output_owned.append(outdir)
        metadata = os.fstat(outdir)
        need(metadata.st_uid == 0 and stat.S_IMODE(metadata.st_mode) == 0o700, 'NEW_ROOT_PRIVATE_OUTPUT_ONLY')
        fd = os.open('bundle.private.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=outdir)
        try:
            offset = 0
            while offset < len(raw_bundle):
                need(time.monotonic() < end, 'OWNED_PRIVATE_BUNDLE_WRITE_DEADLINE')
                count = os.write(fd, raw_bundle[offset:offset + 65536]); need(count > 0, 'OWNED_WRITE_PROGRESS'); offset += count
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(outdir); os.fsync(parent)
        # The utility's 2 MiB default is overridden by this exact own output bound.
        checked, identity = base.read(OUTPUT + '/bundle.private.json', len(raw_bundle))
        need(checked == raw_bundle and identity['st_uid'] == 0 and stat.S_IMODE(identity['st_mode']) == 0o600,
             'EXACT_PRIVATE_BUNDLE_READBACK')
        result['private_bundle'] = {'path': OUTPUT + '/bundle.private.json', 'bytes': len(raw_bundle), 'sha256': sha(raw_bundle)}
    finally:
        for fd in reversed(output_owned):
            os.close(fd)
    for row in observed.values():
        need(time.monotonic() < end, 'POST_PUBLICATION_ORIGINAL_RECHECK_DEADLINE')
        again, identity = base.read(row['path'], MAX_FILE)
        need(again == row['body'] and identity == row['stat'], 'ORIGINAL_CHANGED_AFTER_PRIVATE_COPY')
    need(time.monotonic() < end and census() == before, 'FINAL_WHOLE_PROCESS_FD_IDENTITY_AND_DEADLINE')
    result['whole_process_fd_identities_unchanged'] = True
    result['process_fds_before'] = before; result['process_fds_after'] = census()
    raw = canonical(result) + b'\n'; need(len(raw) <= 262144, 'PUBLIC_DIAGNOSTIC_BOUND_NO_TRUNCATION')
    return raw


if __name__ == '__main__':
    try:
        need(len(sys.argv) == 4 and sys.argv[:3] == ['-c', '--collect-once', '--source-sha256'] and
             re.fullmatch('[0-9a-f]{64}', sys.argv[3]), 'EXACT_FIXED_HOST_READER_ENTRY')
        os.umask(0o077)
        raw = run(sys.argv[3])
    except BaseException as error:
        print(canonical({'schema': 'pocket4-task878-failed-case-host-reader-error-v1', 'ok': False,
            'error': safe_error(error), 'Main_commands': 0, 'UI_actions': 0,
            'original_UNKNOWN_modified': False, 'current_action_authority': False,
            'new_private_bundle_may_be_partial': True}).decode('ascii'), flush=True)
        raise SystemExit(1)
    sys.stdout.buffer.write(raw); sys.stdout.buffer.flush()
