/* Owned diagnostic: actual mapped files and actual signal dispositions.
 * No publisher packages, JNI environment calls, or changes outside this process.
 * Bionic sigaction uses its public LP64 layout, not the kernel syscall layout. */
typedef unsigned long U;
typedef long S;
typedef long long J;
typedef unsigned int U32;
_Static_assert(sizeof(U)==8 && sizeof(S)==8 && sizeof(J)==8,"LP64 JNI");
#define EXPORT __attribute__((visibility("default")))
#define NOINLINE __attribute__((noinline))
#define LOAD(P) __c11_atomic_load((P),2)
#define STORE(P,V) __c11_atomic_store((P),(V),3)
_Static_assert(__atomic_always_lock_free(8,0),"signal-safe lock-free fields");
#if defined(__aarch64__)
typedef void (*Handler)(int,void*,void*);
typedef struct { int flags; U32 pad; Handler action; U mask; void (*restorer)(void); } PublicAction;
_Static_assert(sizeof(PublicAction)==32 && __builtin_offsetof(PublicAction,action)==8 && __builtin_offsetof(PublicAction,mask)==16,"pinned Bionic sigaction ABI");
extern int sigaction(int,const PublicAction*,PublicAction*);
#define NR_OPENAT 56
#define NR_CLOSE 57
#define NR_READ 63
#define NR_MMAP 222
#define NR_MPROTECT 226
#define NR_MUNMAP 215
#define NR_MEMFD 279
#define NR_FTRUNCATE 46
#define NR_GETPID 172
#define NR_GETUID 174
#define NR_GETTID 178
#define NR_TGKILL 131
#define NR_SIGMASK 135
#define NR_SIGPENDING 136
static inline S raw6(S nr,S a,S b,S c,S d,S e,S f) {
 register S x0 __asm__("x0")=a,x1 __asm__("x1")=b,x2 __asm__("x2")=c,x3 __asm__("x3")=d,x4 __asm__("x4")=e,x5 __asm__("x5")=f,x8 __asm__("x8")=nr;
 __asm__ volatile("svc #0":"+r"(x0):"r"(x1),"r"(x2),"r"(x3),"r"(x4),"r"(x5),"r"(x8):"memory","cc");return x0;
}
static U action_pointer(const PublicAction* a){return (U)a->action;}
static void prepare_action(PublicAction* a,Handler h){a->flags=4;a->pad=0;a->action=h;a->mask=0;a->restorer=0;}
#elif defined(HOST_CONTROL) && defined(__x86_64__)
#include <signal.h>
typedef struct sigaction PublicAction;
#define NR_OPENAT 257
#define NR_CLOSE 3
#define NR_READ 0
#define NR_MMAP 9
#define NR_MPROTECT 10
#define NR_MUNMAP 11
#define NR_MEMFD 319
#define NR_FTRUNCATE 77
#define NR_GETPID 39
#define NR_GETUID 102
#define NR_GETTID 186
#define NR_TGKILL 234
#define NR_SIGMASK 14
#define NR_SIGPENDING 127
static inline S raw6(S nr,S a,S b,S c,S d,S e,S f) {
 register S r10 __asm__("r10")=d,r8 __asm__("r8")=e,r9 __asm__("r9")=f;S result;
 __asm__ volatile("syscall":"=a"(result):"a"(nr),"D"(a),"S"(b),"d"(c),"r"(r10),"r"(r8),"r"(r9):"rcx","r11","memory","cc");return result;
}
static U action_pointer(const PublicAction* a){return (U)a->sa_sigaction;}
static void prepare_action(PublicAction* a,void (*h)(int,void*,void*)){a->sa_flags=SA_SIGINFO;a->sa_sigaction=(void (*)(int,siginfo_t*,void*))h;sigemptyset(&a->sa_mask);}
#else
#error unsupported diagnostic target
#endif
NOINLINE static S raw_getpid(void){return raw6(NR_GETPID,0,0,0,0,0,0);}
NOINLINE static S raw_getuid(void){return raw6(NR_GETUID,0,0,0,0,0,0);}
NOINLINE static S raw_gettid(void){return raw6(NR_GETTID,0,0,0,0,0,0);}
NOINLINE static S raw_mmap(S size,S prot,S flags,S fd,S offset){return raw6(NR_MMAP,0,size,prot,flags,fd,offset);}
NOINLINE static S raw_mprotect(S ptr,S size,S prot){return raw6(NR_MPROTECT,ptr,size,prot,0,0,0);}
NOINLINE static S raw_munmap(S ptr,S size){return raw6(NR_MUNMAP,ptr,size,0,0,0,0);}
NOINLINE static S raw_memfd(void){return raw6(NR_MEMFD,(S)"p4-owned-offset-v8",1,0,0,0,0);}
NOINLINE static S raw_ftruncate(S fd,S size){return raw6(NR_FTRUNCATE,fd,size,0,0,0,0);}
NOINLINE static S raw_open_maps(void){return raw6(NR_OPENAT,-100,(S)"/proc/self/maps",0,0,0,0);}
NOINLINE static S raw_read(S fd,void* p,S n){return raw6(NR_READ,fd,(S)p,n,0,0,0);}
NOINLINE static S raw_close(S fd){return raw6(NR_CLOSE,fd,0,0,0,0,0);}
NOINLINE static S raw_tgkill(S pid,S tid){return raw6(NR_TGKILL,pid,tid,14,0,0,0);}
NOINLINE static S raw_sigmask(const U* in,U* out){return raw6(NR_SIGMASK,2,(S)in,(S)out,8,0,0);}
NOINLINE static S raw_sigpending(U* out){return raw6(NR_SIGPENDING,(S)out,8,0,0,0,0);}
enum { FIELD_COUNT=40 };
static volatile S fields[FIELD_COUNT];
static _Atomic U handler_count,handler_signo,info_signo,info_errno,info_code,info_pid,info_uid;
static void reset(S c) {
 for(S i=0;i<FIELD_COUNT;i++)fields[i]=-999;
 fields[0]=1;fields[1]=c;fields[2]=raw_getpid();fields[3]=raw_getuid();fields[4]=0;
}
static int number(const char** ptr,U radix,U* out) {
 const char* p=*ptr;U v=0,n=0;
 for(;;p++){unsigned char c=(unsigned char)*p;U d;
  if(c>='0'&&c<='9')d=c-'0';else if(c>='a'&&c<='f')d=c-'a'+10;else if(c>='A'&&c<='F')d=c-'A'+10;else break;
  if(d>=radix || v>(~(U)0-d)/radix)return 0;v=v*radix+d;n++;
 }
 if(!n)return 0;*ptr=p;*out=v;return 1;
}
static void spaces(const char** p){while(**p==' '||**p=='\t')(*p)++;}
static S consume(const char* line,U begin,U end,S* count) {
 const char* p=line;U a,b,o,maj,min,ino;
 if(!number(&p,16,&a)||*p++!='-'||!number(&p,16,&b))return 0;
 if(b<=begin || a>=end)return 0;
 spaces(&p);U perm=0;
 if(p[0]=='r')perm|=1;else if(p[0]!='-')return 4;
 if(p[1]=='w')perm|=2;else if(p[1]!='-')return 4;
 if(p[2]=='x')perm|=4;else if(p[2]!='-')return 4;
 if(p[3]=='p')perm|=8;else if(p[3]!='s')return 4;
 p+=4;spaces(&p);
 if(!number(&p,16,&o))return 4;spaces(&p);
 if(!number(&p,16,&maj)||*p++!=':'||!number(&p,16,&min))return 4;spaces(&p);
 if(!number(&p,10,&ino))return 4;
 if(*count>=3)return 8;
 S at=18+7*(*count);fields[at]=(S)a;fields[at+1]=(S)b;fields[at+2]=(S)o;fields[at+3]=(S)perm;fields[at+4]=(S)maj;fields[at+5]=(S)min;fields[at+6]=(S)ino;(*count)++;
 return 0;
}
static S run_maps(S c) {
 reset(c);fields[5]=0;
 if(c<0||c>3){fields[4]=1;return 1;}
 const S page=4096;S size=(c==3?5:3)*page,fd=-1,base=-1,opened=-1,status=0;
 U offset=c==1?((U)1<<32)+8192:8192;
 if(c==3)offset=0;
 fields[7]=size;fields[8]=(S)offset;
 if(c!=3){fd=raw_memfd();fields[10]=fd;if(fd<0||raw_ftruncate(fd,(S)offset+size)!=0){status=1;goto done;}}
 base=raw_mmap(size,c==3?0:1,c==3?0x22:2,fd,(S)offset);fields[11]=base;
 if(base<0&&base>=-4095){base=-1;status=1;goto done;}
 fields[6]=base;
 S begin=base+(c==3?page:0);fields[12]=0;
 if(c==3){fields[12]=raw_mprotect(begin,3*page,1);if(fields[12]){status=1;goto done;}}
 if(c!=2){fields[12]=raw_mprotect(begin+page,page,5);if(fields[12]){status=1;goto done;}}
 opened=raw_open_maps();fields[13]=opened;if(opened<0){status=2;goto done;}
 char chunk[4096],line[1024];S used=0,overflow=0,count=0,total=0,rc=0,finished=0;
 for(S round=0;round<4096;round++){
  rc=raw_read(opened,chunk,sizeof(chunk));fields[15]=rc;
  if(rc<0){status|=2;break;}if(rc==0){finished=1;break;}total+=rc;
  for(S k=0;k<rc;k++){
   if(chunk[k]=='\n'){if(!overflow){line[used]=0;status|=consume(line,(U)begin,(U)begin+3*page,&count);}used=0;overflow=0;}
   else if(used<1023)line[used++]=chunk[k];else overflow=1;
  }
 }
 fields[14]=total;fields[9]=count;if(!finished||used)status|=2;
 if(count!=(c==2?1:3))status|=8;
 for(S i=0;i<count&&i<3;i++){
  S at=18+7*i;U expected_start=(U)begin+(c==2?0:(U)i*page),expected_end=(U)begin+(c==2?3:(U)i+1)*page;
  if((U)fields[at]!=expected_start || (U)fields[at+1]!=expected_end)status|=16;
  if((U)fields[at+2]!=(c==3?0:offset+(c==2?0:(U)i*page)))status|=32;
  if(fields[at+3]!=(c!=2&&i==1?13:9))status|=64;
  if(c==3){if(fields[at+4]!=0||fields[at+5]!=0||fields[at+6]!=0)status|=128;}
  else if(fields[at+6]<=0||fields[at+4]!=fields[22]||fields[at+5]!=fields[23]||fields[at+6]!=fields[24])status|=128;
 }
done:
 if(opened>=0){fields[16]=raw_close(opened);if(fields[16])status|=256;}
 if(base!=-1){fields[17]=raw_munmap(base,size);if(fields[17])status|=256;}
 if(fd>=0 && raw_close(fd))status|=256;
 fields[4]=status;return status;
}
static U little(const volatile unsigned char* p,unsigned n){U v=0;for(unsigned i=0;i<n;i++)v|=(U)p[i]<<(8*i);return v;}
static void receive(int signo,void* record,void* context) {
 (void)context;
 STORE(&handler_signo,(U)(S)signo);
 if(record){const volatile unsigned char* p=record;STORE(&info_signo,(U)(S)(int)(U32)little(p,4));STORE(&info_errno,(U)(S)(int)(U32)little(p+4,4));STORE(&info_code,(U)(S)(int)(U32)little(p+8,4));STORE(&info_pid,little(p+16,4));STORE(&info_uid,little(p+20,4));}
 __c11_atomic_fetch_add(&handler_count,1,4);
}
static void settle(U target){for(U i=0;i<1000 && LOAD(&handler_count)<target;i++)(void)raw_getpid();}
static S run_signals(void) {
 reset(4);fields[5]=1;PublicAction old={0},action={0},after={0};U oldmask=0,mask=0,pending=0,current=0;S status=0;
 fields[6]=sigaction(14,(const PublicAction*)0,&old);fields[7]=(S)action_pointer(&old);
 fields[8]=raw_sigmask((const U*)0,&oldmask);fields[9]=(S)oldmask;
 if(fields[6]||fields[8]){fields[4]=1;return 1;}
 STORE(&handler_count,0);STORE(&handler_signo,0);STORE(&info_signo,0);STORE(&info_errno,0);STORE(&info_code,0);STORE(&info_pid,0);STORE(&info_uid,0);
 prepare_action(&action,receive);fields[10]=sigaction(14,&action,(PublicAction*)0);
 if(fields[10]){fields[4]=2;return 2;}
 mask=oldmask&~((U)1<<13);fields[11]=raw_sigmask(&mask,(U*)0);
 fields[12]=raw_tgkill(fields[2],raw_gettid());settle(1);fields[13]=(S)LOAD(&handler_count);
 mask|=(U)1<<13;fields[14]=raw_sigmask(&mask,(U*)0);fields[15]=raw_tgkill(fields[2],raw_gettid());
 fields[16]=raw_sigpending(&pending);fields[17]=(S)pending;fields[18]=(S)LOAD(&handler_count);
 mask&=~((U)1<<13);fields[19]=raw_sigmask(&mask,(U*)0);settle(2);fields[20]=(S)LOAD(&handler_count);
 fields[21]=(S)LOAD(&handler_signo);fields[22]=(S)LOAD(&info_signo);fields[23]=(S)LOAD(&info_errno);fields[24]=(S)LOAD(&info_code);fields[25]=(S)LOAD(&info_pid);fields[26]=(S)LOAD(&info_uid);
 fields[27]=sigaction(14,&old,(PublicAction*)0);fields[28]=raw_sigmask(&oldmask,(U*)0);
 fields[29]=sigaction(14,(const PublicAction*)0,&after);fields[30]=(S)action_pointer(&after);fields[31]=raw_sigmask((const U*)0,&current);fields[32]=(S)current;
 for(S i=10;i<=31;i++)if((i==10||i==11||i==12||i==14||i==15||i==16||i==19||i==27||i==28||i==29||i==31)&&fields[i])status|=4;
 if(fields[13]!=1||fields[18]!=1||fields[20]!=2||(pending&((U)1<<13))==0)status|=8;
 if(fields[21]!=14||fields[22]!=14||fields[23]!=0||fields[24]!=-6||fields[25]!=fields[2]||fields[26]!=fields[3])status|=16;
 if(fields[30]!=fields[7]||current!=oldmask)status|=32;
 fields[4]=status;return status;
}
static S query_alarm(void){PublicAction current={0};return sigaction(14,(const PublicAction*)0,&current)==0?(S)action_pointer(&current):-999;}
static S run_alarm(void){reset(5);fields[5]=2;fields[6]=query_alarm();fields[7]=raw_tgkill(fields[2],raw_gettid());fields[4]=fields[7]?1:0;return fields[4];}
EXPORT J Java_local_pocket4_nativeoraclev8_MainActivity_runCase(void* env,void* cls,int c){(void)env;(void)cls;return c<4?run_maps(c):(c==4?run_signals():(c==5?run_alarm():-999));}
EXPORT J Java_local_pocket4_nativeoraclev8_MainActivity_readField(void* env,void* cls,int i){(void)env;(void)cls;return i>=0&&i<FIELD_COUNT?fields[i]:-999;}
EXPORT J Java_local_pocket4_nativeoraclev8_MainActivity_queryAlarm(void* env,void* cls){(void)env;(void)cls;return query_alarm();}
#ifdef HOST_CONTROL
#include <stdio.h>
#include <unistd.h>
#include <sys/wait.h>
int main(void) {
 for(S c=0;c<5;c++){S status=c<4?run_maps(c):run_signals();printf("{\"case\":%ld,\"status\":%ld,\"fields\":[",c,status);for(S i=0;i<FIELD_COUNT;i++)printf("%s%ld",i?",":"",fields[i]);printf("]}\n");if(status)return 1;}
 fflush(stdout);pid_t child=fork();if(child<0)return 2;
 if(child==0){if(query_alarm()!=0)_exit(87);(void)run_alarm();_exit(88);}
 int status=0;if(waitpid(child,&status,0)!=child)return 3;
 printf("{\"default_child_signaled\":%d,\"default_child_signal\":%d}\n",WIFSIGNALED(status),WIFSIGNALED(status)?WTERMSIG(status):0);
 return WIFSIGNALED(status)&&WTERMSIG(status)==14?0:4;
}
#endif
