// Pure V8 derivation only; this function performs no device operation.
function deriveResidual02(baselineSource, baselineRequestRaw, original01Stdout, U) {
  const pin = s => ({bytes:U.utf8(s).length, sha256:U.sha256(U.utf8(s))});
  if (pin(baselineSource).sha256 !== "35dedd754a3dc3bd865aba5b718633e20f7dff1da0657d760b3b0a782e231238" ||
      pin(original01Stdout).bytes !== 4749 ||
      pin(original01Stdout).sha256 !== "642be65fb1edc94b866c1f0bc578ae1d8801100f6d25ced64de4505c52fba6e8") throw Error("exact baseline/original01");
  const replacements = [["KIND='pocket4-original-ndk-install01-residual-read01'","KIND='pocket4-original-ndk-install01-residual-read02'\nPRIOR_RESIDUAL_RESULT={'job_id':'1a1b2a4e11f-fc05-7f1d','bytes':4749,\n    'sha256':'642be65fb1edc94b866c1f0bc578ae1d8801100f6d25ced64de4505c52fba6e8'}"],["            'old_install_status':'UNKNOWN','installed_UID_qualified':None,","            'old_install_status':'UNKNOWN','installed_UID_qualified':None,\n            'prior_residual_observation':dict(PRIOR_RESIDUAL_RESULT),"]];
  let source = baselineSource;
  for (const [a,b] of replacements) {
    if (source.split(a).length !== 2) throw Error("single replacement");
    source = source.replace(a,b);
  }
  let inverse = source;
  for (const [a,b] of replacements.toReversed()) inverse = inverse.replace(b,a);
  if (inverse !== baselineSource) throw Error("exact inverse");
  const q = JSON.parse(baselineRequestRaw);
  if (q.stdin !== baselineSource) throw Error("baseline request source");
  q.stdin = source;
  q.idempotency_key = "p4-ndk-install01-residual-read02-" + pin(source).sha256.slice(0,16);
  return {source, request:JSON.stringify(q,null,2)+"\n"};
}
