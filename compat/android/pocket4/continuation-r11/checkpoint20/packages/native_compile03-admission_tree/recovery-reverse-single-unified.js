
return function reverseUnified(newText,diff) {
 const lines=newText.split("\n"), ds=diff.split("\n"), out=[];let cursor=0, hunks=0;
 for(let i=0;i<ds.length;){
  const match=/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/.exec(ds[i]);
  if(!match){if(ds[i].startsWith("--- ")||ds[i].startsWith("+++ ")||ds[i]===""){i++;continue;}throw Error("unexpected diff header");}
  const oldStart=Number(match[1]),oldCount=match[2]===undefined?1:Number(match[2]),newStart=Number(match[3]),newCount=match[4]===undefined?1:Number(match[4]);
  const at=newCount===0?newStart:newStart-1; if(at<cursor)throw Error("overlapping hunks");
  out.push(...lines.slice(cursor,at));cursor=at;let oldPart=[],newPart=[];i++;
  while(i<ds.length&&!ds[i].startsWith("@@ ")&&!ds[i].startsWith("--- ")){
   const line=ds[i];if(line===""&&i===ds.length-1){i++;break;}
   if(![" ","+","-"].includes(line[0]))throw Error("unsupported diff content");
   if(line[0]!=="+")oldPart.push(line.slice(1));if(line[0]!=="-")newPart.push(line.slice(1));i++;
  }
  if(oldPart.length!==oldCount||newPart.length!==newCount)throw Error("hunk cardinality");
  if(out.length!==(oldCount===0?oldStart:oldStart-1))throw Error("old hunk position");
  for(let j=0;j<newPart.length;j++)if(lines[cursor+j]!==newPart[j])throw Error("new hunk byte mismatch");
  out.push(...oldPart);cursor+=newPart.length;hunks++;
 }
 out.push(...lines.slice(cursor));if(!hunks)throw Error("no hunks");return {text:out.join("\n"),hunks};
};