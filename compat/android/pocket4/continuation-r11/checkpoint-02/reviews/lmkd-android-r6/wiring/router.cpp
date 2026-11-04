#include <cstdint>
#include <initializer_list>

#include <sys/epoll.h>
#include <cstdio>
#include <cstdlib>
#define ALOGI(...) ((void)0)
#define ALOGD(...) ((void)0)
struct polling_params {};
struct event_handler_info { int data; void (*handler)(int, uint32_t, polling_params*); };
static bool cell_relay_required = true, active = true;
static unsigned effects = 0, closes = 0, done = 0, checks = 0;
static int last_closed = -1;
static struct { void start() {} void stop() {} } watchdog;
static void cell_relay_event(int, uint32_t events, polling_params*) {
    if (events & (EPOLLHUP | EPOLLRDHUP | EPOLLERR)) active = false;
    else if (active) ++effects;
}
static void cell_relay_control_event(int, uint32_t, polling_params*) { active = false; }
static void kill_done_handler(int, uint32_t, polling_params*) { ++done; }
static void ordinary_handler(int, uint32_t, polling_params*) {}
static void ctrl_data_close(int index) { ++closes; last_closed = index; }
static void call_handler(event_handler_info* info, polling_params* params, uint32_t events) {
    info->handler(info->data, events, params);
}
static bool is_cell_relay_handler(const struct event_handler_info* info) {
    return cell_relay_required && info &&
           (info->handler == cell_relay_event || info->handler == cell_relay_control_event);
}
static void Run(epoll_event* events, int nevents) {
 event_handler_info* handler_info; polling_params poll_params; epoll_event* evt; int i;
        for (i = 0, evt = &events[0]; i < nevents; ++i, evt++) {
            // Relay closure is not a framework data-socket index. Retire it
            // before dispatching any other event from this epoll batch.
            // An extra control record also invalidates the complete lease.
            if (evt->data.ptr) {
                handler_info = (struct event_handler_info*)evt->data.ptr;
                if (is_cell_relay_handler(handler_info) &&
                    (handler_info->handler == cell_relay_control_event ||
                     (evt->events & (EPOLLHUP | EPOLLRDHUP | EPOLLERR)))) {
                    call_handler(handler_info, &poll_params, evt->events);
                    evt->data.ptr = nullptr;
                    continue;
                }
            }
            if ((evt->events & EPOLLHUP) && evt->data.ptr) {
                handler_info = (struct event_handler_info*)evt->data.ptr;
                if (handler_info->handler == kill_done_handler) {
                    call_handler(handler_info, &poll_params, evt->events);
                } else {
                    ALOGI("lmkd data connection dropped");
                    watchdog.start();
                    ctrl_data_close(handler_info->data);
                    watchdog.stop();
                }
            }
        }
        for (i = 0, evt = &events[0]; i < nevents; ++i, evt++) {
            if (evt->events & EPOLLERR) {
                ALOGD("EPOLLERR on event #%d", i);
            }
            if (evt->events & EPOLLHUP) {
                /* This case was handled in the first pass */
                continue;
            }
            if (evt->data.ptr) {
                handler_info = (struct event_handler_info*)evt->data.ptr;
                call_handler(handler_info, &poll_params, evt->events);
            }
        }
}

static void Check(bool value, const char* label) {
    if (!value) { std::fprintf(stderr, "FAIL %s\n", label); std::exit(2); }
    ++checks; std::printf("PASS %s\n", label);
}
int main() {
    event_handler_info medium{1, cell_relay_event}, critical{2, cell_relay_event};
    event_handler_info control{0, cell_relay_control_event}, ordinary{2, ordinary_handler};
    event_handler_info killed{0, kill_done_handler};
    for (uint32_t fault : {uint32_t(EPOLLHUP), uint32_t(EPOLLRDHUP), uint32_t(EPOLLERR)}) {
        active = true; effects = closes = 0;
        epoll_event batch[2]{};
        batch[0].events = EPOLLIN; batch[0].data.ptr = &critical;
        batch[1].events = fault; batch[1].data.ptr = &medium;
        Run(batch, 2);
        Check(!active && !effects && !closes, "relay failure preempts earlier queued event without ctrl_data_close");
    }
    active = true; effects = closes = 0;
    epoll_event control_batch[2]{};
    control_batch[0].events = EPOLLIN; control_batch[0].data.ptr = &critical;
    control_batch[1].events = EPOLLIN; control_batch[1].data.ptr = &control;
    Run(control_batch, 2);
    Check(!active && !effects && !closes, "unexpected control IN retires old batch before pressure dispatch");
    epoll_event original{}; original.events = EPOLLHUP; original.data.ptr = &ordinary;
    Run(&original, 1);
    Check(closes == 1 && last_closed == 2, "ordinary framework connection keeps original close index");
    original.data.ptr = &killed; Run(&original, 1);
    Check(done == 1 && closes == 1, "process-death HUP keeps original completion handler");
    active = true; effects = closes = 0;
    original.events = EPOLLIN; original.data.ptr = &critical; Run(&original, 1);
    Check(effects == 1 && !closes, "healthy pressure dispatch remains reachable");
    std::printf("RESULT %u source router assertions passed; no Android event loop\n", checks);
}
