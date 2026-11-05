// SPDX-License-Identifier: Apache-2.0
#include "factory_context.h"
#include <limits.h>
#include <string.h>
namespace droidloom::proc_maps_factory {
bool ParseDecimal(const char* text,size_t size,uint64_t maximum,uint64_t* result) {
  if(size==0)return false;
  uint64_t value=0;
  for(size_t i=0;i<size;++i) {
    if(text[i]<'0'||text[i]>'9')return false;
    const unsigned digit=static_cast<unsigned>(text[i]-'0');
    if(digit>maximum||value>(maximum-digit)/10)return false;
    value=value*10+digit;
  }
  *result=value;return true;
}
namespace {
bool Space(char c){return c==' '||c=='\t';}
bool Numbers(const char* p,size_t n,uint32_t* out,size_t capacity,size_t* count) {
  size_t at=0,used=0;
  while(at<n) {
    while(at<n&&Space(p[at]))++at;
    if(at==n)break;
    const size_t begin=at;
    while(at<n&&!Space(p[at]))++at;
    uint64_t value;
    if(used==capacity||!ParseDecimal(p+begin,at-begin,UINT32_MAX,&value))return false;
    out[used++]=static_cast<uint32_t>(value);
  }
  *count=used;return true;
}
bool Hex(const char* p,size_t n,uint64_t* result) {
  while(n&&Space(*p)){++p;--n;}
  while(n&&Space(p[n-1]))--n;
  if(!n||n>16)return false;
  uint64_t value=0;
  for(size_t i=0;i<n;++i) {
    unsigned digit;
    if(p[i]>='0'&&p[i]<='9')digit=static_cast<unsigned>(p[i]-'0');
    else if(p[i]>='a'&&p[i]<='f')digit=static_cast<unsigned>(p[i]-'a'+10);
    else if(p[i]>='A'&&p[i]<='F')digit=static_cast<unsigned>(p[i]-'A'+10);
    else return false;
    value=value*16+digit;
  }
  *result=value;return true;
}
}
bool ParseStatus(const char* text,size_t size,ProcessStatus* result) {
  if(!size||size>16384||text[size-1]!='\n'||memchr(text,0,size))return false;
  ProcessStatus value{};unsigned seen=0;size_t offset=0;
  while(offset<size) {
    size_t end=offset;while(end<size&&text[end]!='\n')++end;
    const char* line=text+offset;size_t length=end-offset;offset=end+1;
    const char* colon=static_cast<const char*>(memchr(line,':',length));
    if(!colon)continue;
    const size_t key=static_cast<size_t>(colon-line);
    const char* data=colon+1;const size_t n=length-key-1;
    unsigned bit=0;size_t count=0;bool ok=true;
#define FIELD(name) (key==sizeof(name)-1&&!memcmp(line,name,sizeof(name)-1))
    if(FIELD("Uid")){bit=1u<<0;ok=Numbers(data,n,value.uid,4,&count)&&count==4;}
    else if(FIELD("Gid")){bit=1u<<1;ok=Numbers(data,n,value.gid,4,&count)&&count==4;}
    else if(FIELD("CapInh")){bit=1u<<2;ok=Hex(data,n,&value.inheritable);}
    else if(FIELD("CapPrm")){bit=1u<<3;ok=Hex(data,n,&value.permitted);}
    else if(FIELD("CapEff")){bit=1u<<4;ok=Hex(data,n,&value.effective);}
    else if(FIELD("CapAmb")){bit=1u<<5;ok=Hex(data,n,&value.ambient);}
    else if(FIELD("Tgid")){bit=1u<<6;ok=Numbers(data,n,&value.tgid,1,&count)&&count==1;}
    else if(FIELD("NStgid")){bit=1u<<7;ok=Numbers(data,n,value.namespace_tgids,kMaxNamespaceDepth,&value.tgid_depth);}
    else if(FIELD("NSpid")){bit=1u<<8;ok=Numbers(data,n,value.namespace_pids,kMaxNamespaceDepth,&value.pid_depth);}
#undef FIELD
    if(!ok||(bit&&(seen&bit)))return false;
    seen|=bit;
  }
  if(seen!=0x1ffu||!value.tgid||value.tgid>INT_MAX||!value.tgid_depth||
     value.tgid_depth!=value.pid_depth)return false;
  for(size_t i=0;i<value.tgid_depth;++i)
    if(!value.namespace_tgids[i]||value.namespace_tgids[i]>INT_MAX||
       !value.namespace_pids[i]||value.namespace_pids[i]>INT_MAX)return false;
  if(value.tgid!=value.namespace_tgids[0])return false;
  *result=value;return true;
}
bool ParseStartTicks(const char* text,size_t size,uint32_t expected_pid,uint64_t* result) {
  if(!size||size>16384||memchr(text,0,size))return false;
  size_t first=0;while(first<size&&text[first]!=' ')++first;
  uint64_t pid;
  if(!ParseDecimal(text,first,INT_MAX,&pid)||pid!=expected_pid||
     first+2>=size||text[first+1]!='(')return false;
  size_t close=size;
  for(size_t i=first+2;i<size;++i)if(text[i]==')')close=i;
  if(close==size||close+3>=size||text[close+1]!=' ')return false;
  size_t offset=close+2;
  for(unsigned field=3;field<=22;++field) {
    while(offset<size&&text[offset]==' ')++offset;
    const size_t start=offset;
    while(offset<size&&text[offset]!=' '&&text[offset]!='\n')++offset;
    if(start==offset)return false;
    if(field==3) {
      if(offset-start!=1||strchr("RSDZTtXxKWPI",text[start])==nullptr)return false;
    } else if(field==22) {
      uint64_t value;
      if(!ParseDecimal(text+start,offset-start,UINT64_MAX,&value)||value==0)return false;
      *result=value;return true;
    }
  }
  return false;
}
bool SameAuthority(const ProcessStatus& a,const ProcessStatus& b) {
  if(memcmp(a.uid,b.uid,sizeof(a.uid))||memcmp(a.gid,b.gid,sizeof(a.gid))||
     a.inheritable!=b.inheritable||a.permitted!=b.permitted||
     a.effective!=b.effective||a.ambient!=b.ambient||a.tgid!=b.tgid||
     a.tgid_depth!=b.tgid_depth||a.pid_depth!=b.pid_depth)return false;
  return !memcmp(a.namespace_tgids,b.namespace_tgids,a.tgid_depth*sizeof(uint32_t))&&
         !memcmp(a.namespace_pids,b.namespace_pids,a.pid_depth*sizeof(uint32_t));
}
bool Unprivileged(const ProcessStatus& status,uint32_t uid,uint32_t gid) {
  if(uid==0||status.inheritable||status.permitted||status.effective||status.ambient)return false;
  for(unsigned i=0;i<4;++i)if(status.uid[i]!=uid||status.gid[i]!=gid)return false;
  return true;
}
}  // namespace droidloom::proc_maps_factory
