// Bounded zlib/DEFLATE decoder for exact-hash receipt transport.
// No dictionary, concatenated stream, trailing payload, or unbounded output is accepted.
function inflatePinnedZlib(input, expectedBytes) {
  const need=(ok,message)=>{if(!ok)throw new Error("zlib receipt: "+message);};
  need(input instanceof Uint8Array && input.length>=8 && input.length<=1048576,"input bound");
  need(Number.isSafeInteger(expectedBytes)&&expectedBytes>=0&&expectedBytes<=67108864,"output bound");
  const cmf=input[0],flg=input[1];
  need((cmf&15)===8&&(cmf>>>4)<=7&&((cmf<<8)|flg)%31===0&&!(flg&32),"header/dictionary");
  const dataEnd=input.length-4,window=1<<(8+(cmf>>>4));
  let bit=16,at=0;
  const out=new Uint8Array(expectedBytes);
  function bits(n) {
    need(n>=0&&n<=16&&bit+n<=dataEnd*8,"truncated deflate bits");
    let value=0;for(let i=0;i<n;i++,bit++)value|=((input[bit>>>3]>>>(bit&7))&1)<<i;
    return value;
  }
  function tree(lengths) {
    const count=new Uint16Array(16),maps=Array.from({length:16},()=>new Map());
    let maximum=0,nonzero=0;
    for(const n of lengths){need(Number.isInteger(n)&&n>=0&&n<=15,"code length");if(n){count[n]++;maximum=Math.max(maximum,n);nonzero++;}}
    let left=1;for(let n=1;n<=15;n++){left=left*2-count[n];need(left>=0,"oversubscribed tree");}
    const next=new Uint32Array(16);let code=0;
    for(let n=1;n<=15;n++){code=(code+count[n-1])*2;next[n]=code;}
    for(let symbol=0;symbol<lengths.length;symbol++){const n=lengths[symbol];if(n)maps[n].set(next[n]++,symbol);}
    return {maps,maximum,nonzero};
  }
  function symbol(t) {
    need(t.nonzero>0,"empty Huffman tree");let code=0;
    for(let n=1;n<=t.maximum;n++){code=code*2+bits(1);const value=t.maps[n].get(code);if(value!==undefined)return value;}
    throw new Error("zlib receipt: invalid Huffman symbol");
  }
  const lengthBase=[3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258];
  const lengthExtra=[0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0];
  const distanceBase=[1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577];
  const distanceExtra=[0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13];
  const fixedLiteral=tree(Array.from({length:288},(_,i)=>i<144?8:i<256?9:i<280?7:8));
  const fixedDistance=tree(Array(32).fill(5));
  let final=0,blocks=0;
  do {
    need(++blocks<=1048576,"block bound");
    final=bits(1);const kind=bits(2);
    if(kind===0) {
      bit=Math.ceil(bit/8)*8;
      const n=bits(16),inverse=bits(16);need((n^65535)===inverse&&at+n<=out.length,"stored block size");
      for(let i=0;i<n;i++)out[at++]=bits(8);
      continue;
    }
    need(kind===1||kind===2,"reserved block");
    let literal=fixedLiteral,distance=fixedDistance;
    if(kind===2) {
      const nl=bits(5)+257,nd=bits(5)+1,nc=bits(4)+4;
      need(nl<=286&&nd<=32,"dynamic alphabet bound");
      const order=[16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15],cl=Array(19).fill(0);
      for(let i=0;i<nc;i++)cl[order[i]]=bits(3);
      const ct=tree(cl),lengths=[];
      while(lengths.length<nl+nd) {
        const value=symbol(ct);
        if(value<=15){lengths.push(value);continue;}
        let count,valueToRepeat;
        if(value===16){need(lengths.length>0,"repeat without predecessor");count=bits(2)+3;valueToRepeat=lengths[lengths.length-1];}
        else if(value===17){count=bits(3)+3;valueToRepeat=0;}
        else{need(value===18,"code-length opcode");count=bits(7)+11;valueToRepeat=0;}
        need(lengths.length+count<=nl+nd,"repeat exceeds alphabet");
        for(let i=0;i<count;i++)lengths.push(valueToRepeat);
      }
      need(lengths[256]>0,"missing end marker");
      literal=tree(lengths.slice(0,nl));distance=tree(lengths.slice(nl));
    }
    while(true) {
      const value=symbol(literal);
      if(value<256){need(at<out.length,"literal exceeds exact output");out[at++]=value;continue;}
      if(value===256)break;
      need(value>=257&&value<=285,"reserved length symbol");
      const index=value-257,n=lengthBase[index]+bits(lengthExtra[index]),d=symbol(distance);
      need(d<30,"reserved distance symbol");
      const back=distanceBase[d]+bits(distanceExtra[d]);
      need(back<=at&&back<=window&&at+n<=out.length,"invalid backreference/output");
      for(let i=0;i<n;i++){out[at]=out[at-back];at++;}
    }
  }while(!final);
  need(at===expectedBytes&&Math.ceil(bit/8)===dataEnd,"exact output/end boundary");
  let a=1,b=0;for(let i=0;i<out.length;i++){a+=out[i];if(a>=65521)a-=65521;b+=a;if(b>=65521)b-=65521;}
  const wanted=(input[dataEnd]*16777216+input[dataEnd+1]*65536+input[dataEnd+2]*256+input[dataEnd+3])>>>0;
  need(((b*65536+a)>>>0)===wanted,"Adler32 mismatch");
  return out;
}
return inflatePinnedZlib;
