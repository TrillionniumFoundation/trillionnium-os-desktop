"""Decode only the observed OAT275 key table in the exact retained ELF bytes."""
import hashlib, re, struct

def need(value, reason):
    if not value: raise RuntimeError(reason)

def context_bytes(raw):
    need(len(raw)==33536 and hashlib.sha256(raw).hexdigest()==
        'f9bd1ff8feda33004e2052369f64fac534efb461b389831b68ced3b5e262fea6',
        'FIXED_INSTALLED_OAT_BYTES_REQUIRED')
    need(raw[:6]==b'\x7fELF\x02\x01','ELF64_LITTLE_ENDIAN_REQUIRED')
    shoff=struct.unpack_from('<Q',raw,40)[0]
    shentsize,shnum,shstr=struct.unpack_from('<HHH',raw,58)
    need(shentsize==64 and 0<shnum<=32 and shstr<shnum
        and shoff+shentsize*shnum<=len(raw),'ELF_SECTION_TABLE_BOUNDS')
    rows=[struct.unpack_from('<IIQQQQIIQQ',raw,shoff+i*shentsize) for i in range(shnum)]
    table=rows[shstr];need(table[4]+table[5]<=len(raw),'SECTION_NAMES_BOUNDS')
    names=raw[table[4]:table[4]+table[5]]
    selected=[]
    for row in rows:
        need(row[0]<len(names) and names.find(b'\0',row[0])>=0,'SECTION_NAME_BOUNDS')
        name=names[row[0]:names.find(b'\0',row[0])]
        if name==b'.rodata':selected.append(row)
    need(len(selected)==1,'UNIQUE_RODATA_REQUIRED')
    start,size=selected[0][4:6]
    need(start+size<=len(raw) and size>=72 and raw[start:start+8]==b'oat\n275\0',
        'OBSERVED_OAT275_RODATA_REQUIRED')
    count=struct.unpack_from('<I',raw,start+68)[0]
    begin,end=start+72,start+72+count
    need(0<count<=16384 and end<=start+size,'OBSERVED_OAT_KEY_VALUE_BOUNDS')
    data=raw[begin:end];need(data.endswith(b'\0'),'NUL_TERMINATED_KEY_TABLE_REQUIRED')
    parts=data[:-1].split(b'\0');need(len(parts)%2==0,'KEY_VALUE_PAIRS_REQUIRED')
    pairs={};empty_pairs=0
    for key,value in zip(parts[::2],parts[1::2]):
        if key==value==b'':empty_pairs+=1;continue
        need(re.fullmatch(rb'[a-z0-9-]+',key) is not None and key not in pairs,
            'DUPLICATE_OR_INVALID_NONEMPTY_KEY')
        pairs[key]=value
    need(len(pairs)==13 and empty_pairs==944,'OBSERVED_KEY_TABLE_SHAPE_CHANGED')
    stored=pairs[b'classpath'].decode('ascii','strict')
    normalized=re.sub(r'\*\d+(?=\])','',stored)
    expected='PCL[]{PCL[/system_ext/framework/androidx.window.extensions.jar]#PCL[/system_ext/framework/androidx.window.sidecar.jar]}'
    need(normalized==expected,'INSTALLED_OAT_CLASSLOADER_HIERARCHY_CHANGED')
    command=pairs[b'dex2oat-cmdline'].decode('ascii','strict').split()
    need(command.count('--class-loader-context='+expected)==1,'STORED_COMMAND_CONTEXT_DIFFERS')
    return {'input_bytes':len(raw),'input_sha256':hashlib.sha256(raw).hexdigest(),
        'section_file_offset':start,'section_bytes':size,'observed_oat_magic_version':'oat\\n275\\0',
        'observed_header_bytes':72,'observed_key_value_size_word_offset':68,
        'key_value_file_offset':begin,'key_value_bytes':count,
        'key_value_table_sha256':hashlib.sha256(data).hexdigest(),
        'nonempty_unique_keys':[k.decode() for k in pairs],'empty_key_and_empty_value_pairs':empty_pairs,
        'stored_classpath':stored,'stored_clc_without_checksums':normalized,
        'stored_cmdline_same_classloader_context':True,'shared_libraries_after_app_in_stored_context':False,
        'running_classloader_heap_capture':False,'candidate_ART_verified':False,
        'scope':'Exact retained OAT275 bytes only. Empty/empty pairs are explicitly counted; no inference about why they exist, OAT runtime acceptance, or previous oatdump rc1.'}
