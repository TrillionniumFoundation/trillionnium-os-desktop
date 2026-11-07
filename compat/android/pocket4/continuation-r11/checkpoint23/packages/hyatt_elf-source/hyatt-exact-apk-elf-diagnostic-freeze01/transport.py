import hashlib,sys
raw=sys.stdin.buffer.read(61153)
if len(raw)!=61152 or hashlib.sha256(raw).hexdigest()!="2dbdd5e7ba69060d329ae7630144724a4cd4395263e0b913fd3af7b6a053a425":
    raise RuntimeError('EXACT_FIXED_DIAGNOSTIC_SOURCE_REQUIRED')
scope={'__name__':'__main__','__file__':"<pocket4-hyatt-exact-apk-native-member-elf-diagnostic-01>"}
exec(compile(raw,"<pocket4-hyatt-exact-apk-native-member-elf-diagnostic-01>",'exec'),scope)
