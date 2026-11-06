"use strict";
/* Pure byte parser only. It reads no files, runs no commands, and authorizes no runtime.
 * The caller supplies exact class bytes extracted from a separately qualified
 * implementation JAR and supplies the SHA-256 implementation.
 */
function parseFrameworkClass(input, sha256) {
  if (!(input instanceof Uint8Array) || input.length < 10 || input.length > 2 * 1024 * 1024)
    throw Error("CLASS_BYTES_BOUND");
  if (typeof sha256 !== "function") throw Error("SHA256_REQUIRED");
  function reader(bytes) {
    let at = 0;
    const take = n => {
      if (!Number.isSafeInteger(n) || n < 0 || at + n > bytes.length) throw Error("TRUNCATED_CLASS_STRUCTURE");
      const result = bytes.subarray(at, at + n); at += n; return result;
    };
    return {
      take, u1() { return take(1)[0]; },
      u2() { const b = take(2); return b[0] * 256 + b[1]; },
      u4() { const b = take(4); return b[0] * 16777216 + b[1] * 65536 + b[2] * 256 + b[3]; },
      get at() { return at; }, get left() { return bytes.length - at; }
    };
  }
  const r = reader(input);
  if (r.u4() !== 0xcafebabe) throw Error("CLASS_MAGIC");
  const minor = r.u2(), major = r.u2();
  if (major < 45 || major > 65) throw Error("CLASS_VERSION_OUTSIDE_PINNED_JDK21_RANGE");
  const count = r.u2();
  if (count < 2) throw Error("EMPTY_CONSTANT_POOL");
  const pool = new Array(count).fill(null);
  for (let i = 1; i < count; i++) {
    const tag = r.u1();
    if (tag === 1) {
      const b = r.take(r.u2());
      // Structural UTF8 constants may contain modified UTF-8. Only public ASCII
      // class/member/descriptor constants are decoded and returned.
      let value = "";
      for (const x of b) { if (x < 0x20 || x > 0x7e) { value = null; break; } value += String.fromCharCode(x); }
      pool[i] = {tag, value};
    } else if (tag === 3 || tag === 4) {
      pool[i] = {tag}; r.take(4);
    } else if (tag === 5 || tag === 6) {
      if (i + 1 >= count) throw Error("WIDE_CONSTANT_AT_POOL_END");
      pool[i] = {tag}; r.take(8); i++;
    } else if ([7,8,16,19,20].includes(tag)) {
      pool[i] = {tag, a:r.u2()};
    } else if ([9,10,11,12,17,18].includes(tag)) {
      pool[i] = {tag, a:r.u2(), b:r.u2()};
    } else if (tag === 15) {
      pool[i] = {tag, a:r.u1(), b:r.u2()};
    } else throw Error("UNKNOWN_CONSTANT_POOL_TAG");
  }
  function cp(i, tags) {
    if (!Number.isInteger(i) || i <= 0 || i >= count || !pool[i] || !tags.includes(pool[i].tag))
      throw Error("CONSTANT_POOL_REFERENCE");
    return pool[i];
  }
  const utf = i => cp(i,[1]).value;
  const className = i => utf(cp(i,[7]).a);
  function memberRef(i) {
    const x = cp(i,[9,10,11]), nt = cp(x.b,[12]);
    return {kind:x.tag === 9 ? "field" : "method", owner:className(x.a),
            name:utf(nt.a), descriptor:utf(nt.b)};
  }
  function scanCode(code) {
    const q = reader(code), references = [];
    const widths = new Array(202).fill(0);
    for (const op of [0x10,0x12,0x15,0x16,0x17,0x18,0x19,0x36,0x37,0x38,0x39,0x3a,0xa9,0xbc]) widths[op]=1;
    for (const op of [0x11,0x13,0x14,0x84,0x99,0x9a,0x9b,0x9c,0x9d,0x9e,0x9f,0xa0,0xa1,0xa2,0xa3,0xa4,0xa5,0xa6,0xa7,0xa8,
                      0xb2,0xb3,0xb4,0xb5,0xb6,0xb7,0xb8,0xbb,0xbd,0xc0,0xc1,0xc6,0xc7]) widths[op]=2;
    widths[0xb9]=4; widths[0xba]=4; widths[0xc5]=3; widths[0xc8]=4; widths[0xc9]=4;
    const signed = x => x > 0x7fffffff ? x - 0x100000000 : x;
    const branchTargets = [], boundaries = new Set();
    while(q.left) {
      const offset=q.at, op=q.u1(); boundaries.add(offset);
      if(op>=0xca) throw Error("RESERVED_BYTECODE");
      if(op===0xaa || op===0xab) {
        while(q.at%4) if(q.u1()!==0) throw Error("NONZERO_SWITCH_PADDING");
        branchTargets.push(offset + signed(q.u4()));
        if(op===0xaa) {
          const low=signed(q.u4()), high=signed(q.u4()), n=high-low+1;
          if(n<=0 || n>16384 || n*4>q.left) throw Error("TABLESWITCH_BOUND");
          for(let j=0;j<n;j++) branchTargets.push(offset+signed(q.u4()));
        } else {
          const n=signed(q.u4());
          if(n<0 || n>8192 || n*8>q.left) throw Error("LOOKUPSWITCH_BOUND");
          let prior=null;
          for(let j=0;j<n;j++) {
            const key=signed(q.u4());
            if(prior!==null && key<=prior) throw Error("LOOKUPSWITCH_ORDER");
            prior=key; branchTargets.push(offset+signed(q.u4()));
          }
        }
      } else if(op===0xc4) {
        const nested=q.u1();
        if(nested===0x84) q.take(4);
        else if([0x15,0x16,0x17,0x18,0x19,0x36,0x37,0x38,0x39,0x3a,0xa9].includes(nested)) q.take(2);
        else throw Error("WIDE_OPCODE");
      } else {
        const operands=q.take(widths[op]);
        if((op>=0x99&&op<=0xa8)||op===0xc6||op===0xc7) {
          let d=operands[0]*256+operands[1]; if(d>=32768)d-=65536;branchTargets.push(offset+d);
        }
        if(op===0xc8||op===0xc9) branchTargets.push(offset+signed(operands[0]*16777216+operands[1]*65536+operands[2]*256+operands[3]));
        if(op>=0xb2&&op<=0xb9) {
          const index=operands[0]*256+operands[1];
          if(op===0xb9) {
            cp(index,[11]);
            if(operands[2]===0||operands[3]!==0) throw Error("INVOKEINTERFACE_OPERANDS");
          } else if(op<=0xb5) cp(index,[9]);
          else if(op===0xb6) cp(index,[10]);
          else cp(index,[10,11]);
          references.push({offset,opcode:op,...memberRef(index)});
        }
        if(op===0xba) {
          cp(operands[0]*256+operands[1],[18]);
          if(operands[2]!==0||operands[3]!==0) throw Error("INVOKEDYNAMIC_OPERANDS");
        }
      }
    }
    for(const target of branchTargets) if(!boundaries.has(target)) throw Error("BRANCH_TARGET_NOT_INSTRUCTION");
    return {references,boundaries};
  }
  let attributesSeen=0;
  function attributes(q, allowCode) {
    const n=q.u2(), output=[];
    if(n>4096 || (attributesSeen+=n)>16384) throw Error("ATTRIBUTE_COUNT_BOUND");
    for(let i=0;i<n;i++) {
      const name=utf(q.u2()), body=q.take(q.u4());
      if(name!=="Code") continue;
      if(!allowCode) throw Error("CODE_ON_NON_METHOD");
      const c=reader(body), max_stack=c.u2(),max_locals=c.u2(),length=c.u4();
      if(length<1||length>65535) throw Error("CODE_LENGTH_BOUND");
      const code=c.take(length), decoded=scanCode(code), exceptions=c.u2();
      if(exceptions>4096) throw Error("EXCEPTION_TABLE_BOUND");
      for(let j=0;j<exceptions;j++) {
        const start=c.u2(),end=c.u2(),handler=c.u2(),type=c.u2();
        if(start>=end||end>length||!decoded.boundaries.has(start)||
           (end!==length&&!decoded.boundaries.has(end))||!decoded.boundaries.has(handler))
          throw Error("EXCEPTION_RANGE");
        if(type)cp(type,[7]);
      }
      attributes(c,false);
      if(c.left)throw Error("CODE_ATTRIBUTE_TRAILING_BYTES");
      output.push({bytes:length,sha256:sha256(code),max_stack,max_locals,references:decoded.references});
    }
    return output;
  }
  const access=r.u2(), this_class=className(r.u2()), superclassIndex=r.u2();
  const super_class=superclassIndex?className(superclassIndex):null;
  if(!this_class)throw Error("PUBLIC_CLASS_NAME_REQUIRED");
  const interfaces=r.u2(); if(interfaces>2048)throw Error("INTERFACE_COUNT_BOUND");
  for(let i=0;i<interfaces;i++)className(r.u2());
  function members(methods) {
    const n=r.u2();if(n>4096)throw Error("MEMBER_COUNT_BOUND");
    const out=[],seen=new Set();
    for(let i=0;i<n;i++) {
      const flags=r.u2(),name=utf(r.u2()),descriptor=utf(r.u2()),codes=attributes(r,methods);
      if(name!==null&&descriptor!==null){
        const key=name+"\0"+descriptor;
        if(seen.has(key))throw Error("DUPLICATE_MEMBER");
        seen.add(key);
      }
      if(methods){
        const noCode=!!(flags&(0x0100|0x0400));
        if(codes.length!==(noCode?0:1))throw Error("METHOD_CODE_COUNT");
      }
      out.push({access:flags,name,descriptor,...(methods?{code:codes[0]||null}:{})});
    }
    return out;
  }
  const fields=members(false),methods=members(true);
  attributes(r,false);
  if(r.left)throw Error("CLASS_TRAILING_BYTES");
  return {bytes:input.length,sha256:sha256(input),minor,major,access,
          class_name:this_class,super_class,fields,methods,
          runtime_authorization_enabled:false};
}
