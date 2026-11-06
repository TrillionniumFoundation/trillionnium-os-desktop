function applyUnifiedText(input, patch, reverse=false) {
    if(!input.endsWith("\n")) throw Error("input newline required");
    const original=input.slice(0,-1).split("\n");
    const lines=patch.split("\n");
    let cursor=0, result=[], hunks=0;
    for(let i=0;i<lines.length;i++) {
        const match=/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/.exec(lines[i]);
        if(!match) continue;
        hunks++;
        const start=Number(reverse?match[3]:match[1])-1;
        const expectedOld=Number((reverse?match[4]:match[2])??1);
        const expectedNew=Number((reverse?match[2]:match[4])??1);
        if(start<cursor) throw Error("overlapping diff");
        result.push(...original.slice(cursor,start));cursor=start;
        let oldCount=0,newCount=0;
        for(i++;i<lines.length&&!lines[i].startsWith("@@ ");i++){
            if(lines[i]===""&&i===lines.length-1) break;
            const tag0=lines[i][0],text=lines[i].slice(1);
            const tag=reverse?(tag0==="+"?"-":tag0==="-"?"+":tag0):tag0;
            if(tag===" "||tag==="-"){
                if(original[cursor]!==text) throw Error("diff old text mismatch");
                cursor++;oldCount++;
            }
            if(tag===" "||tag==="+"){result.push(text);newCount++;}
            if(![" ","+","-"].includes(tag)) throw Error("unsupported diff row");
        }
        i--;
        if(oldCount!==expectedOld||newCount!==expectedNew) throw Error("diff hunk count");
    }
    if(hunks===0) throw Error("no diff hunks");
    result.push(...original.slice(cursor));
    return result.join("\n")+"\n";
}
