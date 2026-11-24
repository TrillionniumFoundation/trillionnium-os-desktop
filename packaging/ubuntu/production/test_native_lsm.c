#define main maintenance_original_main
#define syscall maintenance_test_syscall
#include "maintenance.c"
#undef main
#undef syscall
#include <assert.h>
#include <stdarg.h>
static unsigned int selected_case, calls;
long maintenance_test_syscall(long number, ...) {
    va_list args;va_start(args,number);
    unsigned int attr=va_arg(args,unsigned int);
    struct maintenance_lsm_context *ctx=va_arg(args,struct maintenance_lsm_context *);
    uint32_t *size=va_arg(args,uint32_t *);
    uint32_t flags=va_arg(args,uint32_t);va_end(args);
    ++calls;
    assert(number==459 && attr==100 && flags==1 && ctx->id==101);
    if(selected_case==1) {errno=EACCES;return -1;}
    ctx->ctx_len=sizeof(CONTEXT);ctx->len=(32+ctx->ctx_len+7)&~7ULL;
    *size=(uint32_t)ctx->len;memcpy(ctx->data,CONTEXT,sizeof(CONTEXT));
    if(selected_case==2) ctx->id=104;
    if(selected_case==3) ctx->flags=1;
    if(selected_case==4) ++*size;
    if(selected_case==5) ++ctx->ctx_len;
    if(selected_case==6) ctx->data[sizeof(CONTEXT)-1]=1;
    if(selected_case==7) ctx->data[3]=0;
    if(selected_case==8) ctx->data[sizeof(CONTEXT)]=1;
    return selected_case==9?0:1;
}
int main(void) {
    for(selected_case=0;selected_case<10;selected_case++) {
        calls=0;errno=0;
        bool got=selinux_context_is();
        assert(got==(selected_case==0));assert(calls==1);
        if(selected_case==1) assert(errno==EACCES);
        else if(selected_case) assert(errno==EPROTO);
    }
    puts("10 native selector ABI cases passed; no runtime qualification");
    return 0;
}
