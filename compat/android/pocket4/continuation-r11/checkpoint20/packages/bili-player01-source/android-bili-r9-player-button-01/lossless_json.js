function losslessJsonNodes(text){
 let i=0;
 const need=(v,c)=>{if(!v)throw Error(c)},space=()=>{while(/\s/.test(text[i]||"")&&i<text.length)i++};
 function parse(){
  space();const start=i,c=text[i];let node;
  if(c==="{"){i++;const fields={};space();if(text[i]!=="}")while(true){space();const key=parse();need(key.type==="string","JSON_KEY");need(!Object.hasOwn(fields,key.value),"JSON_DUPLICATE_KEY");space();need(text[i++]===":","JSON_COLON");fields[key.value]=parse();space();if(text[i]!==",")break;i++;}need(text[i++]==="}","JSON_OBJECT_END");node={type:"object",fields};}
  else if(c==="["){i++;const items=[];space();if(text[i]!=="]")while(true){items.push(parse());space();if(text[i]!==",")break;i++;}need(text[i++]==="]","JSON_ARRAY_END");node={type:"array",items};}
  else if(c==='"'){i++;let escaped=false;while(i<text.length){const q=text[i++];if(!escaped&&q==='"')break;if(!escaped&&q==="\\")escaped=true;else escaped=false;}const raw=text.slice(start,i);node={type:"string",value:JSON.parse(raw)};}
  else{const m=text.slice(i).match(/^(?:true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)/);need(m,"JSON_SCALAR");i+=m[0].length;node={type:["true","false"].includes(m[0])?"boolean":m[0]==="null"?"null":"number"};}
  node.raw=text.slice(start,i);return node;
 }
 const result=parse();space();need(i===text.length,"JSON_TRAILING");return result;
}
function nodeField(root,path){let value=root;for(const part of path){if(!value||value.type!=="object"||!Object.hasOwn(value.fields,part))throw Error("MISSING_LOSSLESS_FIELD "+path.join("."));value=value.fields[part];}return value;}
function losslessCanonical(node){
 if(node.type==="object")return "{"+Object.keys(node.fields).sort().map(k=>JSON.stringify(k)+":"+losslessCanonical(node.fields[k])).join(",")+"}";
 if(node.type==="array")return "["+node.items.map(losslessCanonical).join(",")+"]";
 return node.type==="string"?JSON.stringify(node.value):node.raw;
}
function losslessPython(node){
 if(node.type==="object")return "{"+Object.keys(node.fields).map(k=>JSON.stringify(k)+":"+losslessPython(node.fields[k])).join(",")+"}";
 if(node.type==="array")return "["+node.items.map(losslessPython).join(",")+"]";
 if(node.type==="string")return JSON.stringify(node.value);
 if(node.type==="boolean")return node.raw==="true"?"True":"False";
 if(node.type==="null")return "None";
 return node.raw;
}
