function(aText,bText,path){
 if(aText===bText)return "";
 if((aText&&!aText.endsWith("\n"))||(bText&&!bText.endsWith("\n")))throw new Error("final newline required");
 const a=aText?aText.slice(0,-1).split("\n"):[],b=bText?bText.slice(0,-1).split("\n"):[];
 const xvec=new Map([[1,0]]),trace=[];let done=false;
 for(let d=0;d<=a.length+b.length&&!done;d++){trace.push(new Map(xvec));for(let k=-d;k<=d;k+=2){
  let x=(k===-d||(k!==d&&(xvec.get(k-1)??-1)<(xvec.get(k+1)??-1)))?(xvec.get(k+1)??0):(xvec.get(k-1)??0)+1,y=x-k;
  while(x<a.length&&y<b.length&&a[x]===b[y]){x++;y++;}xvec.set(k,x);if(x>=a.length&&y>=b.length){done=true;break;}
 }}
 let x=a.length,y=b.length;const rev=[];
 for(let d=trace.length-1;d>=0;d--){const p=trace[d],k=x-y,pk=(k===-d||(k!==d&&(p.get(k-1)??-1)<(p.get(k+1)??-1)))?k+1:k-1,px=p.get(pk)??0,py=px-pk;while(x>px&&y>py){rev.push([" ",a[--x]]);--y;}if(d===0)break;if(x===px)rev.push(["+",b[--y]]);else rev.push(["-",a[--x]]);}
 const ops=rev.reverse(),old=[0],neu=[0];for(const[op]of ops){old.push(old.at(-1)+(op!=="+"?1:0));neu.push(neu.at(-1)+(op!=="-"?1:0));}
 if(ops.filter(o=>o[0]!=="+").map(o=>o[1]).join("\n")+(a.length?"\n":"")!==aText||ops.filter(o=>o[0]!=="-").map(o=>o[1]).join("\n")+(b.length?"\n":"")!==bText)throw new Error("diff complete reconstruction");
 const ranges=[];for(let i=0;i<ops.length;i++)if(ops[i][0]!==" "){const s=Math.max(0,i-3),e=Math.min(ops.length,i+4);if(ranges.length&&s<=ranges.at(-1)[1])ranges.at(-1)[1]=e;else ranges.push([s,e]);}
 let out="--- "+(aText?"a/"+path:"/dev/null")+"\n+++ "+(bText?"b/"+path:"/dev/null")+"\n";
 for(const[s,e]of ranges){const oc=old[e]-old[s],nc=neu[e]-neu[s];out+="@@ -"+(oc?old[s]+1:old[s])+","+oc+" +"+(nc?neu[s]+1:neu[s])+","+nc+" @@\n";for(let i=s;i<e;i++)out+=ops[i][0]+ops[i][1]+"\n";}return out;
}
