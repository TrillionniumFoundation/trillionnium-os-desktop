// Reproduce only; no filesystem, process or network actions.
function reproduceInstall02(utilitySource,binderSource,basePacketRaw,wrapperTemplateRaw,stdoutRaw,terminalRaw){
  const U=Function(utilitySource+"\nreturn {utf8,sha256,gitBlob};")();
  if(U.gitBlob(U.utf8(binderSource))!=="117fa0bb475b375507a00e7f1f63bd19a6cec60e")throw Error("BINDER02_PIN");
  const bind=Function(binderSource+"\nreturn bindOriginalNdkInstall;")();
  return bind(utilitySource,basePacketRaw,wrapperTemplateRaw,{
    stdout_raw:stdoutRaw,stdout_pin:{bytes:9826,sha256:"f0eb6ad4a6f2fb977571e985638b1c2409203522ba3b5b7142b7fc15b893fbe6"},
    terminal_raw:terminalRaw,terminal_pin:{bytes:731,sha256:"6b9db2494c57d654f7766776ac39030b302d3b4370dd848ad51d21ee2f3bc45d"},
    job_id:"1a1b2da0a51-fc05-8004"});
}
