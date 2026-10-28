import importlib.util,pathlib,json
s=importlib.util.spec_from_file_location('capture','/workspace/desktop-current-audit/support/rootfs/capture.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
p=pathlib.Path(__import__('sys').argv[1]);f=p/'double-slash.json';f.write_text(json.dumps({'files':[{'path':'//etc/probe','sha256':'a'*64,'bytes':1,'mode':'0444'}]}))
m.extract_verified_tar(p/'absent.tar',f,p/'extracted')
