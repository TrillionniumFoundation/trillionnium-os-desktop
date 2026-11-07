function exactJsonTokens(raw) {
 let i=0;
 const ws=()=>{while(i<raw.length&&/\s/.test(raw[i]))i++;};
 function atom(){ws();const start=i,c=raw[i];
  if(c==="{"){i++;const pairs=[],seen=new Set();ws();if(raw[i]==="}"){i++;return {kind:"object",pairs,start,end:i};}
   while(true){ws();const m=raw.slice(i).match(/^"(?:[^"\\]|\\.)*"/);if(!m)throw Error("JSON object key");i+=m[0].length;const key=JSON.parse(m[0]);if(seen.has(key))throw Error("duplicate JSON key");seen.add(key);ws();if(raw[i++]!==":")throw Error("JSON colon");const value=atom();pairs.push({key,token:m[0],value});ws();const next=raw[i++];if(next==="}")break;if(next!==",")throw Error("JSON comma");}
   return {kind:"object",pairs,start,end:i};}
  if(c==="["){i++;const values=[];ws();if(raw[i]==="]"){i++;return {kind:"array",values,start,end:i};}
   while(true){values.push(atom());ws();const next=raw[i++];if(next==="]")break;if(next!==",")throw Error("JSON array comma");}
   return {kind:"array",values,start,end:i};}
  const m=raw.slice(i).match(/^(?:"(?:[^"\\]|\\.)*"|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|true|false|null)/);
  if(!m)throw Error("JSON primitive");i+=m[0].length;return {kind:"primitive",raw:m[0],start,end:i};
 }
 const root=atom();ws();if(i!==raw.length)throw Error("JSON trailing bytes");
 function pretty(n,depth=0){const pad="  ".repeat(depth),inside="  ".repeat(depth+1);
  if(n.kind==="primitive")return n.raw;
  if(n.kind==="array")return n.values.length?"[\n"+n.values.map(x=>inside+pretty(x,depth+1)).join(",\n")+"\n"+pad+"]":"[]";
  return n.pairs.length?"{\n"+n.pairs.map(x=>inside+x.token+": "+pretty(x.value,depth+1)).join(",\n")+"\n"+pad+"}":"{}";
 }
 function member(n,key){if(n.kind!=="object")throw Error("object member");const m=n.pairs.find(x=>x.key===key);if(!m)throw Error("missing member "+key);return m.value;}
 return {root,pretty,member,rawSlice:n=>raw.slice(n.start,n.end)};
}