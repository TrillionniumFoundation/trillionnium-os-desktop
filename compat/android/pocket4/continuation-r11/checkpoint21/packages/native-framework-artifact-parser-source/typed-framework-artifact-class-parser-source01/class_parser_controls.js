function frameworkClassParserControls(parse, sha256) {
  const u1=n=>[n&255],u2=n=>[(n>>>8)&255,n&255],u4=n=>[(n>>>24)&255,(n>>>16)&255,(n>>>8)&255,n&255];
  const utf=s=>[1,...u2(s.length),...Array.from(s,c=>c.charCodeAt(0))];
  function fixture(options={}) {
    const entries=[
      utf("fixture/TypedIngress"),[7,...u2(1)],utf("java/lang/Object"),[7,...u2(3)],
      utf("nativeProbe"),utf("()V"),utf("Code"),utf("run"),
      [12,...u2(5),...u2(6)],[10,...u2(2),...u2(9)]
    ];
    if(options.bad_tag)entries[0][0]=2;
    const code=options.code||[0xb8,0,10,0xb1];
    const body=[...u2(0),...u2(0),...u4(options.code_length??code.length),...code,...u2(0),...u2(0)];
    if(options.code_trailing)body.push(0);
    const attr=[...u2(7),...u4(body.length),...body];
    const nativeAttrs=options.native_has_code?[...u2(1),...attr]:u2(0);
    const native=[...u2(0x109),...u2(5),...u2(6),...nativeAttrs];
    let runAttrs=options.no_code?u2(0):[...u2(options.duplicate_code?2:1),...attr,...(options.duplicate_code?attr:[])];
    const run=[...u2(0x9),...u2(8),...u2(6),...runAttrs];
    const out=[...u4(options.magic??0xcafebabe),...u2(0),...u2(options.major??65),
      ...u2(11),...entries.flat(),...u2(0x21),...u2(2),...u2(4),...u2(0),...u2(0),
      ...u2(options.duplicate_member?3:2),...native,...run,...(options.duplicate_member?run:[]),...u2(0)];
    if(options.trailing)out.push(0);
    return new Uint8Array(out);
  }
  const checks=[];
  function yes(name,fn){fn();checks.push({name,passed:true});}
  function no(name,bytes,expected){yes(name,()=>{
    let actual=null;try{parse(bytes,sha256);}catch(e){actual=e.message;}
    if(actual!==expected)throw Error(name+": "+actual+" != "+expected);
  });}
  yes("complete_Code_and_native_declaration",()=>{
    const x=parse(fixture(),sha256);
    if(x.class_name!=="fixture/TypedIngress"||x.methods.length!==2||
       x.methods[0].code!==null||x.methods[1].code.bytes!==4||
       x.methods[1].code.references.length!==1||
       x.methods[1].code.references[0].owner!=="fixture/TypedIngress"||
       x.methods[1].code.references[0].name!=="nativeProbe"||
       x.methods[1].code.references[0].descriptor!=="()V")throw Error("VALID_PARSE");
  });
  no("header_style_missing_Code_rejected",fixture({no_code:true}),"METHOD_CODE_COUNT");
  no("native_Code_rejected",fixture({native_has_code:true}),"METHOD_CODE_COUNT");
  no("duplicate_Code_rejected",fixture({duplicate_code:true}),"METHOD_CODE_COUNT");
  no("duplicate_method_rejected",fixture({duplicate_member:true}),"DUPLICATE_MEMBER");
  no("trailing_class_bytes_rejected",fixture({trailing:true}),"CLASS_TRAILING_BYTES");
  no("truncated_class_rejected",fixture().subarray(0,fixture().length-1),"TRUNCATED_CLASS_STRUCTURE");
  no("invalid_magic_rejected",fixture({magic:0xfeedbeef}),"CLASS_MAGIC");
  no("unqualified_future_class_version_rejected",fixture({major:66}),"CLASS_VERSION_OUTSIDE_PINNED_JDK21_RANGE");
  no("unknown_pool_tag_rejected",fixture({bad_tag:true}),"UNKNOWN_CONSTANT_POOL_TAG");
  no("empty_Code_rejected",fixture({code:[]}),"CODE_LENGTH_BOUND");
  no("truncated_Code_operand_rejected",fixture({code:[0xb8,0]}),"TRUNCATED_CLASS_STRUCTURE");
  no("invalid_invocation_pool_reference_rejected",fixture({code:[0xb8,0,7,0xb1]}),"CONSTANT_POOL_REFERENCE");
  no("Code_trailing_bytes_rejected",fixture({code_trailing:true}),"CODE_ATTRIBUTE_TRAILING_BYTES");
  no("reserved_bytecode_rejected",fixture({code:[0xca]}),"RESERVED_BYTECODE");
  no("branch_to_operand_rejected",fixture({code:[0xa7,0,1,0xb1]}),"BRANCH_TARGET_NOT_INSTRUCTION");
  yes("valid_branch_to_instruction",()=>{parse(fixture({code:[0xa7,0,3,0xb1]}),sha256);});
  no("wide_invalid_nested_rejected",fixture({code:[0xc4,0x00,0,1,0xb1]}),"WIDE_OPCODE");
  yes("valid_wide_and_iinc",()=>{parse(fixture({code:[0xc4,0x15,0,1,0xc4,0x84,0,1,0,1,0x57,0xb1]}),sha256);});
  const table=[0xaa,0,0,0,...u4(20),...u4(0),...u4(0),...u4(20),0xb1];
  yes("tableswitch_alignment_and_targets",()=>{parse(fixture({code:table}),sha256);});
  no("tableswitch_nonzero_padding_rejected",fixture({code:table.map((v,i)=>i===2?1:v)}),"NONZERO_SWITCH_PADDING");
  no("tableswitch_invalid_target_rejected",fixture({code:table.map((v,i)=>i===19?19:v)}),"BRANCH_TARGET_NOT_INSTRUCTION");
  const lookup=[0xab,0,0,0,...u4(28),...u4(2),...u4(2),...u4(28),...u4(1),...u4(28),0xb1];
  no("lookupswitch_unsorted_keys_rejected",fixture({code:lookup}),"LOOKUPSWITCH_ORDER");
  return {schema:1,kind:"framework-class-parser-synthetic-controls",count:checks.length,
          controls:checks,all_passed:true,actual_artifacts_read:false,
          JVM_verifier_or_Android_execution:false,runtime_authorization_enabled:false};
}