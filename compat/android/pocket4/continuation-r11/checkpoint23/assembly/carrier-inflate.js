function inflateZlibFixed(input,expectedBytes) {
 function need(x,m){if(!x)throw Error("zlib: "+m)}
 need(input instanceof Uint8Array && input.length>=6,"input");
 need(Number.isSafeInteger(expectedBytes)&&expectedBytes>=0&&expectedBytes<=33554432,"output bound");
 const cmf=input[0],flg=input[1];need((cmf&15)===8&&(cmf>>>4)<=7&&((cmf<<8)|flg)%31===0&&!(flg&32),"header");
 const end=input.length-4,out=new Uint8Array(expectedBytes);let pos=2,bits=0,buffer=0,used=0;
 function read(n){need(n>=0&&n<=16,"bit width");while(bits<n){need(pos<end,"truncated bits");buffer|=input[pos++]<<bits;bits+=8}const x=buffer&((1<<n)-1);buffer>>>=n;bits-=n;return x}
 function tree(lengths){const counts=new Int32Array(16),next=new Int32Array(16),table=Array.from({length:16},()=>new Map());let max=0;
  for(const n of lengths){need(Number.isInteger(n)&&n>=0&&n<=15,"code length");if(n){counts[n]++;max=Math.max(max,n)}}
  need(max>0,"empty Huffman alphabet");let left=1,code=0;for(let n=1;n<=15;n++){left=(left<<1)-counts[n];need(left>=0,"oversubscribed Huffman tree");code=(code+counts[n-1])<<1;next[n]=code}
  lengths.forEach((n,sym)=>{if(!n)return;let c=next[n]++,rev=0;for(let i=0;i<n;i++){rev=(rev<<1)|(c&1);c>>>=1}need(!table[n].has(rev),"duplicate code");table[n].set(rev,sym)});return {table,max};}
 function symbol(t){let c=0;for(let n=1;n<=t.max;n++){c|=read(1)<<(n-1);const x=t.table[n].get(c);if(x!==undefined)return x}throw Error("zlib: invalid Huffman code")}
 const lb=[3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258],
 le=[0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0],
 db=[1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577],
 de=[0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13];
 let final=false,blocks=0;while(!final){need(++blocks<=100000,"block bound");final=read(1)===1;const type=read(2);need(type!==3,"reserved block");if(type===0){buffer=0;bits=0;need(pos+4<=end,"stored header");const len=input[pos]|input[pos+1]<<8,nlen=input[pos+2]|input[pos+3]<<8;pos+=4;need((len^nlen)===65535&&pos+len<=end&&used+len<=out.length,"stored block bound");out.set(input.subarray(pos,pos+len),used);pos+=len;used+=len;continue}
 let lit,dist;if(type===1){lit=tree(Array.from({length:288},(_,i)=>i<144?8:i<256?9:i<280?7:8));dist=tree(Array(32).fill(5));}
 else{const nl=read(5)+257,nd=read(5)+1,nc=read(4)+4,order=[16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15],cl=Array(19).fill(0);need(nl<=286&&nd<=32,"alphabet counts");for(let i=0;i<nc;i++)cl[order[i]]=read(3);const ct=tree(cl),lens=[];
 while(lens.length<nl+nd){const s=symbol(ct);if(s<16){lens.push(s);continue}let repeat,value=0;if(s===16){need(lens.length>0,"repeat before first code");repeat=read(2)+3;value=lens[lens.length-1]}else if(s===17)repeat=read(3)+3;else{need(s===18,"code-length symbol");repeat=read(7)+11}need(lens.length+repeat<=nl+nd,"repeat overflow");while(repeat--)lens.push(value)}
 need(lens[256]>0,"end-of-block missing");lit=tree(lens.slice(0,nl));const dl=lens.slice(nl);dist=dl.some(Boolean)?tree(dl):null;}
 while(true){const s=symbol(lit);if(s<256){need(used<out.length,"literal output overflow");out[used++]=s;continue}if(s===256)break;need(s>=257&&s<=285&&dist!==null,"length symbol");const idx=s-257,len=lb[idx]+read(le[idx]),ds=symbol(dist);need(ds<30,"distance symbol");const distance=db[ds]+read(de[ds]);need(distance>0&&distance<=used&&used+len<=out.length,"copy bound");for(let i=0;i<len;i++){out[used]=out[used-distance];used++}}
 }
 need(pos===end&&bits<8&&used===expectedBytes,"trailing bytes or output length");let a=1,b=0;for(let offset=0;offset<used;){const stop=Math.min(offset+5552,used);while(offset<stop){a+=out[offset++];b+=a}a%=65521;b%=65521}
 const wanted=((input[end]<<24)|(input[end+1]<<16)|(input[end+2]<<8)|input[end+3])>>>0;need((((b<<16)|a)>>>0)===wanted,"Adler32");return out;
}