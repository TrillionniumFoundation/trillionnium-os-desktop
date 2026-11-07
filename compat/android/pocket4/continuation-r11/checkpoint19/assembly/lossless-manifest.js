function rootMembers(raw) {
 let i=0;const ws=()=>{while(/\s/.test(raw[i]||"")&&i<raw.length)i++;};
 const endString=()=>{if(raw[i]!=='"')throw Error("JSON string expected");i++;while(i<raw.length){const c=raw[i++];if(c==='\\'){i++;continue;}if(c==='"')return;}throw Error("unclosed string");};
 const endValue=()=>{
  if(raw[i]==='"'){endString();return;}
  if(raw[i]==='{'||raw[i]==='['){const stack=[raw[i++]];while(i<raw.length&&stack.length){const c=raw[i];if(c==='"'){endString();continue;}i++;if(c==='{'||c==='[')stack.push(c);else if(c==='}'||c===']'){const o=stack.pop();if((o==='{'&&c!=='}')||(o==='['&&c!==']'))throw Error("JSON bracket mismatch");}}if(stack.length)throw Error("unclosed JSON");return;}
  const start=i;while(i<raw.length&&!/[\s,}\]]/.test(raw[i]))i++;if(start===i)throw Error("empty value");
 };
 ws();if(raw[i++]!=='{')throw Error("object expected");const members=new Map();ws();
 while(raw[i]!=='}'){const ks=i;endString();const key=JSON.parse(raw.slice(ks,i));if(members.has(key))throw Error("duplicate key");ws();if(raw[i++]!==':')throw Error("colon");ws();const start=i;endValue();const end=i;members.set(key,{start,end,raw:raw.slice(start,end)});ws();if(raw[i]===','){i++;ws();continue;}if(raw[i]!=='}')throw Error("comma/close");}
 const close=i++;ws();if(i!==raw.length)throw Error("JSON trailing");
 return {members,close};
}
function updateRootPreservingHistoricalBytes(original, rawUpdates) {
 const parsed=rootMembers(original), edits=[],added=[];
 for(const [key,newRaw] of Object.entries(rawUpdates)){JSON.parse(newRaw);const m=parsed.members.get(key);if(m)edits.push({start:m.start,end:m.end,replacement:newRaw});else added.push(JSON.stringify(key)+": "+newRaw);}
 if(added.length){const at=[...parsed.members.values()].at(-1)?.end??parsed.close;edits.push({start:at,end:at,replacement:(parsed.members.size?",\n  ":"\n  ")+added.join(",\n  ")});}
 let result=original;for(const e of edits.sort((a,b)=>b.start-a.start))result=result.slice(0,e.start)+e.replacement+result.slice(e.end);
 const checked=rootMembers(result);
 for(const[key,m]of parsed.members){if(!(key in rawUpdates)&&checked.members.get(key).raw!==m.raw)throw Error("historical root field changed: "+key);}
 return result;
}
