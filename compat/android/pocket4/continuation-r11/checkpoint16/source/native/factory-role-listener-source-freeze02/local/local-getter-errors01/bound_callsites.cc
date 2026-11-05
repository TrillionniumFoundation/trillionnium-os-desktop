#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>
#include <sys/eventfd.h>
#include <sys/syscall.h>
#include <stdexcept>
#include <string>
namespace fixture {
constexpr uint64_t kSessionRequestNanos=2000000000ULL;
constexpr short kDead=POLLERR|POLLHUP|POLLNVAL|POLLRDHUP;
struct GrantHandle{unsigned slot=0;uint64_t serial=1;};
struct DispatchResult{};
int Error(int error){errno=error;return -1;}
uint64_t Now(){timespec t{};if(clock_gettime(CLOCK_MONOTONIC,&t)<0)return 0;return uint64_t(t.tv_sec)*1000000000ULL+uint64_t(t.tv_nsec);}
int TimeRemaining(uint64_t deadline,uint64_t* previous){const uint64_t n=Now();if(!n||n<*previous)return Error(EIO);*previous=n;return n<deadline?0:Error(ETIMEDOUT);}
// Explicit authority and getter seams. poll uses real owned kernel descriptors.
struct OwnerLease {
 int control,pidfd,fail_control,fail_pidfd;
 mutable unsigned control_calls=0,pidfd_calls=0,verifies=0;
 int Verify()const{++verifies;errno=0;return 0;}
 int control_fd()const{++control_calls;if(fail_control)return Error(fail_control);errno=EUCLEAN;return control;}
 int owner_pidfd()const{++pidfd_calls;if(fail_pidfd)return Error(fail_pidfd);errno=EUCLEAN;return pidfd;}
};
struct Registry {
 int connection;unsigned closes=0;
 int Sweep(){return 0;}int IsActive(GrantHandle){return 0;}
 int Connection(GrantHandle){return connection;}
 void Close(GrantHandle){++closes;errno=EBUSY;}
};
int CloseError(Registry& registry,GrantHandle handle,int error){registry.Close(handle);return Error(error>0&&error<=4095?error:EIO);}
void Need(bool value,const char* reason){if(!value)throw std::runtime_error(reason);}
}
namespace preimage_session {
using namespace fixture;
int Wait(Registry& registry, GrantHandle handle, const OwnerLease& owner, int connection,
         short events, uint64_t deadline, uint64_t* previous, bool require_active) {
  for (;;) {
    if (TimeRemaining(deadline, previous) < 0 || owner.Verify() < 0 || registry.Sweep() < 0) return -1;
    if (require_active && registry.IsActive(handle) < 0) return -1;
    const uint64_t remaining = deadline - *previous;
    int timeout = static_cast<int>((remaining + 999999) / 1000000);
    if (timeout > 100) timeout = 100;
    pollfd items[3] = {
        {connection, static_cast<short>(events | POLLRDHUP), 0},
        {owner.control_fd(), static_cast<short>(POLLIN | POLLRDHUP), 0},
        {owner.owner_pidfd(), POLLIN, 0}};
    const int count = poll(items, 3, timeout);
    if (count < 0) { if (errno == EINTR) continue; return -1; }
    if (items[1].revents || items[2].revents) return Error(ECANCELED);
    if (items[0].revents & kDead) return Error(EPIPE);
    if (items[0].revents & events) {
      if (TimeRemaining(deadline, previous) < 0 || owner.Verify() < 0 || registry.Sweep() < 0) return -1;
      return require_active ? registry.IsActive(handle) : 0;
    }
  }
}
int DispatchOne(Registry& registry, GrantHandle handle, const OwnerLease& owner, DispatchResult* result) {
  if (!result) return Error(EINVAL);
  const uint64_t start = Now();
  if (!start || start > UINT64_MAX - kSessionRequestNanos) return CloseError(registry, handle, EIO);
  const uint64_t deadline = start + kSessionRequestNanos; uint64_t previous = start;
  if (registry.IsActive(handle) < 0 || owner.Verify() < 0) return CloseError(registry, handle, errno);
  const int connection = registry.Connection(handle);
  if (connection < 0) return CloseError(registry, handle, errno);
  if (connection == owner.control_fd() || connection == owner.owner_pidfd()) return CloseError(registry, handle, EINVAL);
  (void)deadline; (void)previous; return 777;
}
}
namespace preimage_admission {
using namespace fixture;
int Check(Registry& registry, const OwnerLease& owner, uint64_t deadline, uint64_t* previous,
          const GrantHandle* handle, bool active, int role_connection) {
  const uint64_t now = Now();
  if (!now || now < *previous) return Error(EIO);
  *previous = now;
  if (now >= deadline) return Error(ETIMEDOUT);
  if (owner.Verify() < 0 || registry.Sweep() < 0) return -1;
  if (handle) {
    if (active && registry.IsActive(*handle) < 0) return -1;
    const int current = registry.Connection(*handle);
    if (current < 0) return -1;
    if (current != role_connection) return Error(ESTALE);
  }
  return 0;
}
int Wait(Registry& registry, const OwnerLease& owner, int connection, short events,
         uint64_t deadline, uint64_t* previous, const GrantHandle* handle = nullptr,
         bool active = false, int role_connection = -1) {
  for (;;) {
    if (Check(registry, owner, deadline, previous, handle, active, role_connection) < 0) return -1;
    const int control = owner.control_fd(), pidfd = owner.owner_pidfd();
    if (control < 0 || pidfd < 0) return -1;
    int timeout = static_cast<int>((deadline - *previous + 999999) / 1000000);
    if (timeout > 100) timeout = 100;
    pollfd items[3] = {{connection, static_cast<short>(events | POLLRDHUP), 0},
                      {control, static_cast<short>(POLLIN | POLLRDHUP), 0}, {pidfd, POLLIN, 0}};
    const int count = poll(items, 3, timeout);
    if (count < 0) { if (errno == EINTR) continue; return -1; }
    if (items[1].revents || items[2].revents) return Error(ECANCELED);
    if (items[0].revents & kDead) return Error(EPIPE);
    if (items[0].revents & events) return Check(registry, owner, deadline, previous, handle, active, role_connection);
  }
}
}
namespace candidate_session {
using namespace fixture;
int Wait(Registry& registry, GrantHandle handle, const OwnerLease& owner, int connection,
         short events, uint64_t deadline, uint64_t* previous, bool require_active) {
  for (;;) {
    if (TimeRemaining(deadline, previous) < 0 || owner.Verify() < 0 || registry.Sweep() < 0) return -1;
    if (require_active && registry.IsActive(handle) < 0) return -1;
    const uint64_t remaining = deadline - *previous;
    int timeout = static_cast<int>((remaining + 999999) / 1000000);
    if (timeout > 100) timeout = 100;
    const int control = owner.control_fd();
    if (control < 0) return -1;
    const int pidfd = owner.owner_pidfd();
    if (pidfd < 0) return -1;
    pollfd items[3] = {
        {connection, static_cast<short>(events | POLLRDHUP), 0},
        {control, static_cast<short>(POLLIN | POLLRDHUP), 0},
        {pidfd, POLLIN, 0}};
    const int count = poll(items, 3, timeout);
    if (count < 0) { if (errno == EINTR) continue; return -1; }
    if (items[1].revents || items[2].revents) return Error(ECANCELED);
    if (items[0].revents & kDead) return Error(EPIPE);
    if (items[0].revents & events) {
      if (TimeRemaining(deadline, previous) < 0 || owner.Verify() < 0 || registry.Sweep() < 0) return -1;
      return require_active ? registry.IsActive(handle) : 0;
    }
  }
}
int DispatchOne(Registry& registry, GrantHandle handle, const OwnerLease& owner, DispatchResult* result) {
  if (!result) return Error(EINVAL);
  const uint64_t start = Now();
  if (!start || start > UINT64_MAX - kSessionRequestNanos) return CloseError(registry, handle, EIO);
  const uint64_t deadline = start + kSessionRequestNanos; uint64_t previous = start;
  if (registry.IsActive(handle) < 0 || owner.Verify() < 0) return CloseError(registry, handle, errno);
  const int connection = registry.Connection(handle);
  if (connection < 0) return CloseError(registry, handle, errno);
  const int control = owner.control_fd();
  if (control < 0) return CloseError(registry, handle, errno);
  const int pidfd = owner.owner_pidfd();
  if (pidfd < 0) return CloseError(registry, handle, errno);
  if (connection == control || connection == pidfd) return CloseError(registry, handle, EINVAL);
  (void)deadline; (void)previous; return 777;
}
}
namespace candidate_admission {
using namespace fixture;
int Check(Registry& registry, const OwnerLease& owner, uint64_t deadline, uint64_t* previous,
          const GrantHandle* handle, bool active, int role_connection) {
  const uint64_t now = Now();
  if (!now || now < *previous) return Error(EIO);
  *previous = now;
  if (now >= deadline) return Error(ETIMEDOUT);
  if (owner.Verify() < 0 || registry.Sweep() < 0) return -1;
  if (handle) {
    if (active && registry.IsActive(*handle) < 0) return -1;
    const int current = registry.Connection(*handle);
    if (current < 0) return -1;
    if (current != role_connection) return Error(ESTALE);
  }
  return 0;
}
int Wait(Registry& registry, const OwnerLease& owner, int connection, short events,
         uint64_t deadline, uint64_t* previous, const GrantHandle* handle = nullptr,
         bool active = false, int role_connection = -1) {
  for (;;) {
    if (Check(registry, owner, deadline, previous, handle, active, role_connection) < 0) return -1;
    const int control = owner.control_fd();
    if (control < 0) return -1;
    const int pidfd = owner.owner_pidfd();
    if (pidfd < 0) return -1;
    int timeout = static_cast<int>((deadline - *previous + 999999) / 1000000);
    if (timeout > 100) timeout = 100;
    pollfd items[3] = {{connection, static_cast<short>(events | POLLRDHUP), 0},
                      {control, static_cast<short>(POLLIN | POLLRDHUP), 0}, {pidfd, POLLIN, 0}};
    const int count = poll(items, 3, timeout);
    if (count < 0) { if (errno == EINTR) continue; return -1; }
    if (items[1].revents || items[2].revents) return Error(ECANCELED);
    if (items[0].revents & kDead) return Error(EPIPE);
    if (items[0].revents & events) return Check(registry, owner, deadline, previous, handle, active, role_connection);
  }
}
}

int main(){
 using namespace fixture;
 int pipes[2];Need(pipe2(pipes,O_NONBLOCK|O_CLOEXEC)==0,"own readiness pipe");
 const int control=eventfd(0,EFD_CLOEXEC|EFD_NONBLOCK),pidfd=static_cast<int>(syscall(SYS_pidfd_open,getpid(),0));
 Need(control>=0&&pidfd>=0,"own quiet event and live PIDFD");
 Need(write(pipes[1],"x",1)==1,"real readiness");
 unsigned comparisons=0,original_defects=0;
 for(int site=0;site<3;++site)for(int fail=0;fail<3;++fail){
  int observed_rc[2]{},observed_error[2]{};unsigned calls[2][3]{};
  for(int arm=0;arm<2;++arm){
   Registry registry{pipes[0]};OwnerLease owner{control,pidfd,fail==1?EMFILE:0,fail==2?EINTR:0};
   GrantHandle handle{};DispatchResult output{};uint64_t previous=Now(),deadline=previous+kSessionRequestNanos;
   errno=0;int rc;
   if(site==0)rc=arm?candidate_session::Wait(registry,handle,owner,pipes[0],POLLIN,deadline,&previous,true):preimage_session::Wait(registry,handle,owner,pipes[0],POLLIN,deadline,&previous,true);
   else if(site==1)rc=arm?candidate_session::DispatchOne(registry,handle,owner,&output):preimage_session::DispatchOne(registry,handle,owner,&output);
   else rc=arm?candidate_admission::Wait(registry,owner,pipes[0],POLLIN,deadline,&previous):preimage_admission::Wait(registry,owner,pipes[0],POLLIN,deadline,&previous);
   observed_rc[arm]=rc;observed_error[arm]=errno;calls[arm][0]=owner.control_calls;calls[arm][1]=owner.pidfd_calls;calls[arm][2]=registry.closes;
   if(!fail){Need(rc==(site==1?777:0),"positive reaches original next point");Need(owner.control_calls==1&&owner.pidfd_calls==1&&!registry.closes,"positive exact getter count");}
   else if(arm){
    Need(rc==-1&&errno==(fail==1?EMFILE:EINTR),"candidate retains first getter error");
    Need(owner.control_calls==1&&owner.pidfd_calls==(fail==1?0U:1U),"candidate never evaluates later getter after failure");
    Need(registry.closes==(site==1?1U:0U),"candidate Dispatch closes before receive");
   }else{
    Need(owner.control_calls==1&&owner.pidfd_calls==1&&!registry.closes,"original consumes both getters and does not close");
    if(site<2){Need(rc==(site==1?777:0),"original failure swallowed before continuation");++original_defects;}
    else if(fail==1){Need(rc==-1&&errno==EUCLEAN,"original first error overwritten by later successful getter");++original_defects;}
    else Need(rc==-1&&errno==EINTR,"unchanged original second getter rejection");
   }
  }
  printf("{\"site\":%d,\"fault\":%d,\"original_rc\":%d,\"original_errno\":%d,\"candidate_rc\":%d,\"candidate_errno\":%d,\"original_getters_and_close\":[%u,%u,%u],\"candidate_getters_and_close\":[%u,%u,%u]}\n",site,fail,observed_rc[0],observed_error[0],observed_rc[1],observed_error[1],calls[0][0],calls[0][1],calls[0][2],calls[1][0],calls[1][1],calls[1][2]);
  ++comparisons;
 }
 Need(comparisons==9&&original_defects==5,"exact five original error-path defects observed");
 Need(close(pipes[0])==0&&close(pipes[1])==0&&close(control)==0&&close(pidfd)==0,"close exact owned controls");
 printf("{\"state\":\"PASS_BOUND_CALLSITE_ERROR_CONTROLS\",\"comparisons\":9,\"original_defects\":5,\"authority_and_getters\":\"explicit_seam\",\"poll\":\"actual_owned_kernel_descriptors\",\"production_authorization_executed\":false}\n");
}
