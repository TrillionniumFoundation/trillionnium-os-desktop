
return function parseLossless(raw){
 let at=0;
 const ws=()=>{while(at<raw.length&&/[\t\r\n ]/.test(raw[at]))at++;};
 function string(){const start=at++;while(at<raw.length){const c=raw[at++];if(c==="\\"){at++;continue;}if(c==='"')return JSON.parse(raw.slice(start,at));}throw Error("unclosed JSON string");}
 function value(){ws();const c=raw[at];
  if(c==='"')return string();
  if(c==="{"){at++;ws();const out=Object.create(null),seen=new Set();if(raw[at]==="}"){at++;return out;}while(true){ws();if(raw[at]!=='"')throw Error("JSON key");const k=string();if(seen.has(k))throw Error("duplicate key");seen.add(k);ws();if(raw[at++]!==":")throw Error("JSON colon");out[k]=value();ws();const e=raw[at++];if(e==="}")return out;if(e!==",")throw Error("JSON object separator");}}
  if(c==="["){at++;ws();const out=[];if(raw[at]==="]"){at++;return out;}while(true){out.push(value());ws();const e=raw[at++];if(e==="]")return out;if(e!==",")throw Error("JSON array separator");}}
  for(const [token,x]of[["true",true],["false",false],["null",null]])if(raw.slice(at,at+token.length)===token){at+=token.length;return x;}
  const m=/-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(raw.slice(at));if(!m||m.index!==0)throw Error("JSON token");at+=m[0].length;const n=Number(m[0]);if(!Number.isFinite(n))throw Error("nonfinite JSON");return !/[.eE]/.test(m[0])&&!Number.isSafeInteger(n)?{exact_number:m[0]}:n;
 }
 const parsed=value();ws();if(at!==raw.length)throw Error("JSON trailing");return parsed;
};