"""The exact DEX class reader used in the installed Gallery code inspection."""
import hashlib,re,struct,zlib

def need(ok,reason):
    if not ok:raise RuntimeError(reason)

def classes(raw):
    need(len(raw)>=112 and re.fullmatch(rb'dex\n0[34][0-9]\x00',raw[:8]),'DEX_MAGIC')
    def u32(off):
        need(0<=off<=len(raw)-4,'DEX_U32_BOUND');return struct.unpack_from('<I',raw,off)[0]
    need(u32(32)==len(raw) and u32(36)==112 and u32(40)==0x12345678,'DEX_HEADER')
    need(u32(8)==zlib.adler32(raw[12:])&0xffffffff and raw[12:32]==hashlib.sha1(raw[32:]).digest(),'DEX_CHECKSUM')
    sc,so,tc,to,cc,co=(u32(x) for x in (56,60,64,68,96,100))
    need(so+4*sc<=len(raw) and to+4*tc<=len(raw) and co+32*cc<=len(raw),'DEX_TABLE_BOUNDS')
    names=[]
    for off in range(co,co+cc*32,32):
        typ=u32(off);need(typ<tc,'DEX_TYPE_INDEX');idx=u32(to+typ*4);need(idx<sc,'DEX_STRING_INDEX');pos=u32(so+idx*4)
        for _ in range(5):
            need(pos<len(raw),'DEX_ULEB_BOUND');v=raw[pos];pos+=1
            if v<128:break
        else:raise RuntimeError('DEX_ULEB_OVERFLOW')
        end=raw.find(b'\0',pos,min(len(raw),pos+4096));need(end>=pos,'DEX_DESCRIPTOR_TERMINATION')
        name=raw[pos:end].decode('ascii');need(re.fullmatch(r'L[^;\s]+;',name),'DEX_DESCRIPTOR')
        names.append(name)
    need(len(names)==len(set(names)),'DUPLICATE_CLASS');return names
