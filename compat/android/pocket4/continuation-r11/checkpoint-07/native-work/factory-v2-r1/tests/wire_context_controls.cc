// SPDX-License-Identifier: Apache-2.0
// Pure wire/context-parser controls. No service, socket, namespace or app is run.
#include "berberis/kernel_api/proc_maps_factory_protocol.h"
#include "factory_context.h"
#include <fcntl.h>
#include <linux/magic.h>
#include <stdio.h>
#include <string.h>
#include <string>
namespace p=berberis::proc_maps_provenance;
namespace f=droidloom::proc_maps_factory;
static unsigned passed,failed;
static void Check(const char* name,bool ok) {
  printf("{\"case\":\"%s\",\"pass\":%s}\n",name,ok?"true":"false");
  if(ok)++passed;else ++failed;
}
static bool SameRequest(const p::CreateRequest& a,const p::CreateRequest& b) {
  return a.payload_size==b.payload_size&&a.caller_tid==b.caller_tid&&
         a.source_flags==b.source_flags&&a.original_fd_flags==b.original_fd_flags;
}
static p::Origin MakeOrigin() {
  p::Origin o{};auto* w=o.words;
  w[p::kFactoryUsernsDevice]=p::kTrustedUserNamespaceDevice;
  w[p::kFactoryUsernsInode]=p::kTrustedUserNamespaceInode;
  w[p::kBackingDevice]=13;w[p::kBackingInode]=19;w[p::kBackingSize]=123;
  w[p::kOriginTgid]=42;w[p::kOriginStartTicks]=5678;
  w[p::kStatDevice]=17;w[p::kStatInode]=456;
  w[p::kStatMode]=S_IFREG|0444;w[p::kStatNlink]=1;w[p::kStatUid]=10164;w[p::kStatGid]=10164;
  w[p::kStatRdev]=0;w[p::kStatSize]=0;w[p::kStatBlockSize]=1024;w[p::kStatBlocks]=0;
  w[p::kStatAtimeSeconds]=13;w[p::kStatAtimeNanoseconds]=987;
  w[p::kStatMtimeSeconds]=static_cast<uint64_t>(INT64_C(-7));w[p::kStatMtimeNanoseconds]=654;
  w[p::kStatCtimeSeconds]=9;w[p::kStatCtimeNanoseconds]=321;
  w[p::kFsType]=PROC_SUPER_MAGIC;w[p::kFsBlockSize]=4096;
  w[p::kFsBlocks]=11;w[p::kFsBlocksFree]=12;w[p::kFsBlocksAvailable]=13;
  w[p::kFsFiles]=14;w[p::kFsFilesFree]=15;
  w[p::kFsId0]=0xfedcba98u;w[p::kFsId1]=0x76543210u;
  w[p::kFsNameLength]=255;w[p::kFsFragmentSize]=4096;w[p::kFsFlags]=0x1000020u;
  w[p::kFsSpare0]=0x8000000000000000ULL;w[p::kFsSpare1]=UINT64_MAX;
  w[p::kFsSpare2]=0x123456789abcdef0ULL;w[p::kFsSpare3]=7;
  memcpy(o.path,"/proc/42/maps",13);o.path_size=13;
  return o;
}
static bool OriginUnchanged(const p::Origin& a,const p::Origin& b) {
  return !memcmp(a.words,b.words,sizeof(a.words))&&!memcmp(a.path,b.path,sizeof(a.path))&&a.path_size==b.path_size;
}
static std::string Status() {
  return "Name:\towned-parser-only\nTgid:\t42\nUid:\t10164\t10164\t10164\t10164\n"
    "Gid:\t10164\t10164\t10164\t10164\nNStgid:\t42\t6\nNSpid:\t42\t6\n"
    "CapInh:\t0000000000000000\nCapPrm:\t0000000000000000\n"
    "CapEff:\t0000000000000000\nCapAmb:\t0000000000000000\n";
}
int main() {
  const p::CreateRequest request{123,42,O_RDONLY|O_NONBLOCK,FD_CLOEXEC};
  unsigned char bytes[p::kRequestBytes];
  p::CreateRequest got{};
  Check("v2_request_round_trip",p::EncodeCreateRequest(request,bytes)&&
        p::DecodeCreateRequest(bytes,sizeof(bytes),&got)&&SameRequest(request,got));
  unsigned char request_oracle[64]{};
  memcpy(request_oracle,"DP4REQ02",8);request_oracle[8]=2;request_oracle[12]=1;
  request_oracle[16]=123;request_oracle[24]=42;request_oracle[29]=8;
  request_oracle[32]=1;request_oracle[36]=1;request_oracle[40]=64;
  Check("fixed_independent_64_byte_V2_request_oracle",!memcmp(bytes,request_oracle,64));
  bool all_lengths=true;
  for(size_t n=0;n<sizeof(bytes);++n)all_lengths=all_lengths&&!p::DecodeCreateRequest(bytes,n,&got);
  unsigned char oversized[p::kRequestBytes+1]{};memcpy(oversized,bytes,sizeof(bytes));
  all_lengths=all_lengths&&!p::DecodeCreateRequest(oversized,sizeof(oversized),&got);
  Check("request_all_short_and_oversized_lengths_rejected",all_lengths);
  bool request_negative=true;
  const unsigned offsets[]={0,7,8,12,36,40,44,63};
  for(unsigned offset:offsets) {
    unsigned char bad[sizeof(bytes)];memcpy(bad,bytes,sizeof(bytes));bad[offset]^=1;
    const p::CreateRequest before{7,8,9,10};got=before;
    request_negative=request_negative&&!p::DecodeCreateRequest(bad,sizeof(bad),&got)&&SameRequest(got,before);
  }
  Check("request_magic_version_operation_raw_encoding_abi_reserved_output_atomicity",request_negative);
  bool invalid_values=true;
  for(unsigned kind=0;kind<7;++kind) {
    p::CreateRequest bad=request;
    switch(kind){case 0:bad.payload_size=0;break;case 1:bad.payload_size=p::kMaxSnapshotBytes+1;break;
      case 2:bad.caller_tid=0;break;case 3:bad.caller_tid=UINT32_MAX;break;
      case 4:bad.source_flags=O_WRONLY;break;case 5:bad.source_flags=O_PATH;break;
      default:bad.original_fd_flags=2;break;}
    unsigned char target[sizeof(bytes)];memset(target,0xa5,sizeof(target));
    unsigned char before[sizeof(target)];memcpy(before,target,sizeof(before));
    invalid_values=invalid_values&&!p::EncodeCreateRequest(bad,target)&&!memcmp(target,before,sizeof(target));
  }
  Check("request_ranges_modes_flags_fail_without_output_mutation",invalid_values);
  const p::Origin origin=MakeOrigin();p::Origin decoded{};
  unsigned char tag[p::kMaxTagBytes];const size_t tag_size=p::EncodeOrigin(origin,tag,sizeof(tag));
  Check("v2_origin_round_trip",tag_size==p::kTagHeaderBytes+origin.path_size&&
        p::DecodeOrigin(tag,tag_size,&decoded)&&OriginUnchanged(origin,decoded));
  const unsigned char header_oracle[24]={'D','P','4','M','A','P','S','2',2,0,0,0,
                                        0x5d,1,0,0,13,0,0,0,1,0,0,0};
  Check("fixed_independent_V2_tag_header_and_first_word",tag_size==349&&
        !memcmp(tag,header_oracle,24)&&tag[24]==5&&tag[25]==0&&tag[31]==0);
  p::KernelStatfs raw{};struct statfs libc{};struct stat st{};
  p::KernelStatfs expected{};
  expected.f_type=PROC_SUPER_MAGIC;expected.f_bsize=4096;expected.f_blocks=11;
  expected.f_bfree=12;expected.f_bavail=13;expected.f_files=14;expected.f_ffree=15;
  expected.f_fsid[0]=0xfedcba98u;expected.f_fsid[1]=0x76543210u;
  expected.f_namelen=255;expected.f_frsize=4096;expected.f_flags=0x1000020u;
  expected.f_spare[0]=0x8000000000000000ULL;expected.f_spare[1]=UINT64_MAX;
  expected.f_spare[2]=0x123456789abcdef0ULL;expected.f_spare[3]=7;
  Check("all_120_kernel_statfs_bytes_including_ST_VALID_and_spares",
        p::DecodeKernelStatfs(decoded,&raw)&&!memcmp(&raw,&expected,sizeof(raw)));
  p::KernelStatfs libc_expected=expected;
#if defined(__BIONIC__)
  libc_expected.f_flags&=~UINT64_C(0x20);
#endif
  Check("host_libc_conversion_clears_only_Bionic_ST_VALID",
        p::DecodeStatfs(decoded,&libc)&&!memcmp(&libc,&libc_expected,sizeof(libc)));
  Check("decoded_stat_fields_and_signed_seconds",
        p::DecodeStat(decoded,&st)&&st.st_dev==17&&st.st_ino==456&&st.st_mode==(S_IFREG|0444)&&
        st.st_nlink==1&&st.st_uid==10164&&st.st_gid==10164&&st.st_rdev==0&&st.st_size==0&&
        st.st_blksize==1024&&st.st_blocks==0&&st.st_atim.tv_sec==13&&st.st_atim.tv_nsec==987&&
        st.st_mtim.tv_sec==-7&&st.st_mtim.tv_nsec==654&&st.st_ctim.tv_sec==9&&st.st_ctim.tv_nsec==321);
  bool tag_negative=true;
  const unsigned tag_offsets[]={0,7,8,12,16,20};
  for(unsigned offset:tag_offsets) {
    unsigned char bad[p::kMaxTagBytes];memcpy(bad,tag,tag_size);bad[offset]^=1;
    p::Origin before=origin;before.words[0]=999;decoded=before;
    tag_negative=tag_negative&&!p::DecodeOrigin(bad,tag_size,&decoded)&&OriginUnchanged(before,decoded);
  }
  unsigned char old[p::kMaxTagBytes];memcpy(old,tag,tag_size);
  old[7]='1';p::PutU32(old+8,1);p::PutU32(old+20,0);
  tag_negative=tag_negative&&!p::DecodeOrigin(old,tag_size,&decoded);
  Check("V1_and_ambiguous_tag_headers_rejected_output_unchanged",tag_negative);
  bool origin_negative=true;
  for(unsigned kind=0;kind<9;++kind) {
    p::Origin bad=origin;
    switch(kind){case 0:bad.path[6]='9';break;case 1:bad.path[3]=0;break;
      case 2:bad.words[p::kBackingSize]=0;break;case 3:bad.words[p::kOriginTgid]=0;break;
      case 4:bad.words[p::kStatMode]=S_IFREG|0644;break;
      case 5:bad.words[p::kStatAtimeNanoseconds]=1000000000;break;
      case 6:bad.words[p::kFsBlockSize]=UINT64_MAX;break;
      case 7:bad.words[p::kFsId0]=UINT64_C(1)<<32;break;
      default:bad.words[p::kBackingSize]=p::kMaxSnapshotBytes+1;break;}
    unsigned char output[p::kMaxTagBytes];memset(output,0xa5,sizeof(output));
    unsigned char before[sizeof(output)];memcpy(before,output,sizeof(output));
    origin_negative=origin_negative&&p::EncodeOrigin(bad,output,sizeof(output))==0&&
                    !memcmp(output,before,sizeof(output));
  }
  Check("origin_path_shape_ranges_signedness_failure_atomicity",origin_negative);
  unsigned char reply[p::kReplyBytes];p::EncodeReply(14,reply);
  bool zeros=true;for(unsigned i=16;i<sizeof(reply);++i)zeros=zeros&&reply[i]==0;
  Check("reply_exact_version_errno_reserved",!memcmp(reply,"DP4REP02",8)&&
        p::GetU32(reply+8)==2&&p::GetU32(reply+12)==14&&zeros);
  f::ProcessStatus status{};const std::string status_text=Status();
  Check("process_status_complete_namespace_and_four_credential_fields",
        f::ParseStatus(status_text.data(),status_text.size(),&status)&&status.tgid==42&&
        status.tgid_depth==2&&status.namespace_tgids[1]==6&&
        f::Unprivileged(status,10164,10164));
  bool status_negative=true;
  for(unsigned kind=0;kind<6;++kind) {
    std::string bad=status_text;
    switch(kind) {
      case 0:bad+="Uid:\t10164 10164 10164 10164\n";break;
      case 1:bad.erase(bad.find("CapAmb:"));break;
      case 2:bad.replace(bad.find("NSpid:\t42\t6"),12,"NSpid:\t42\n");break;
      case 3:bad[0]=0;break;case 4:bad.pop_back();break;
      default:bad.replace(bad.find("Tgid:\t42"),8,"Tgid:\t4294967296");break;
    }
    f::ProcessStatus before=status;before.tgid=999;f::ProcessStatus value=before;
    status_negative=status_negative&&!f::ParseStatus(bad.data(),bad.size(),&value)&&f::SameAuthority(value,before);
  }
  Check("status_duplicates_missing_caps_depth_overflow_no_partial_publish",status_negative);
  f::ProcessStatus privileged=status;privileged.inheritable=8;
  f::ProcessStatus uid_change=status;uid_change.uid[3]=0;
  Check("zero_capabilities_and_all_credential_slots_required",
        !f::Unprivileged(privileged,10164,10164)&&!f::Unprivileged(uid_change,10164,10164)&&
        !f::Unprivileged(status,0,10164)&&!f::SameAuthority(status,uid_change));
  std::string stat_text="42 (odd ) name) R";
  for(unsigned field=4;field<22;++field)stat_text+=" 0";
  stat_text+=" 7654 0\n";uint64_t ticks=0;
  Check("stat_last_comm_parenthesis_field22_startticks",
        f::ParseStartTicks(stat_text.data(),stat_text.size(),42,&ticks)&&ticks==7654);
  bool stat_negative=!f::ParseStartTicks(stat_text.data(),stat_text.size(),43,&ticks);
  std::string negative=stat_text;negative.replace(negative.find("7654"),4,"-1");
  stat_negative=stat_negative&&!f::ParseStartTicks(negative.data(),negative.size(),42,&ticks);
  std::string overflow=stat_text;overflow.replace(overflow.find("7654"),4,"18446744073709551616");
  stat_negative=stat_negative&&!f::ParseStartTicks(overflow.data(),overflow.size(),42,&ticks);
  Check("stat_wrong_pid_negative_or_overflow_ticks_rejected",stat_negative);
  uint64_t value=999;
  Check("numeric_preflight_bounds_no_sign_whitespace_or_wrap",
        f::ParseDecimal("1023",4,1023,&value)&&value==1023&&
        !f::ParseDecimal("+1",2,1023,&value)&&!f::ParseDecimal(" 1",2,1023,&value)&&
        !f::ParseDecimal("1024",4,1023,&value)&&!f::ParseDecimal("9",1,0,&value)&&
        !f::ParseDecimal("",0,1023,&value));
  printf("{\"passed\":%u,\"failed\":%u,\"service_run\":false,\"Android_run\":false,\"production_ready\":false}\n",passed,failed);
  return failed?1:0;
}
