// Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
// Real bounded packet/SCM_RIGHTS transport controls. No PSI, cgroup, Android,
// memory pressure, process registration or kill is performed by this test.
#include "enrollment.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <fstream>
#include <poll.h>
#include <string>
#include <sys/socket.h>
#include <thread>
#include <unistd.h>
#include <vector>

using namespace droidloom::lmkd::relay;
static unsigned passed = 0;
static void Need(bool value, const char* label) {
    if (!value) { std::fprintf(stderr, "SETUP %s errno=%d\n", label, errno); std::exit(3); }
}
static void Check(bool value, const char* label) {
    if (!value) { std::fprintf(stderr, "FAIL %s errno=%d\n", label, errno); std::exit(2); }
    ++passed; std::printf("PASS %s\n", label);
}
static size_t Fds() {
    DIR* directory = opendir("/proc/self/fd"); Need(directory != nullptr, "fd inventory");
    size_t result = 0;
    while (dirent* entry = readdir(directory)) if (entry->d_name[0] != '.') ++result;
    closedir(directory); return result;
}
static EnrollmentRequest Request() {
    EnrollmentRequest request; request.nonce.fill(0x31);
    request.cgroup_device = 13; request.cgroup_inode = 17;
    request.budget = BindBudget(64 * 1024 * 1024, 24 * 1024 * 1024, 0, false, false);
    request.count = 2;
    request.configs[0] = {Level::Medium, 1000000, 70000};
    request.configs[1] = {Level::Critical, 1000000, 70000};
    return request;
}
template <size_t N> static std::string Hex(const std::array<uint8_t, N>& bytes) {
    static const char* digits = "0123456789abcdef"; std::string result;
    for (uint8_t byte : bytes) { result += digits[byte >> 4]; result += digits[byte & 15]; }
    return result;
}
static std::string Golden(const char* directory, const char* file) {
    std::ifstream stream(std::string(directory) + "/" + file); Need(bool(stream), "golden fixture");
    std::string value; stream >> value; return value;
}
static void CodecControls(const char* directory) {
    EnrollmentRequest request = Request(); EnrollmentGrant grant{request, {}}; grant.generation.fill(0x51);
    RequestWire wire = EncodeRequest(request); GrantWire response = EncodeGrant(grant);
    Check(Hex(wire) == Golden(directory, "request.hex"), "request agrees with independent cross-language byte vector");
    Check(Hex(response) == Golden(directory, "grant.hex"), "grant agrees with independent cross-language byte vector");
    EnrollmentRequest decoded; EnrollmentGrant reply;
    Check(DecodeRequest(wire, &decoded) && decoded == request, "request fields preserve exact scope and thresholds");
    Check(DecodeGrant(response, &reply) && reply.request == request && reply.generation == grant.generation, "grant binds nonce generation scope and exact monitor configurations");
    for (size_t offset : {size_t(0), size_t(8), size_t(100), size_t(124)}) {
        RequestWire bad = wire; bad[offset] ^= 1; Check(!DecodeRequest(bad, &decoded), "invalid magic/version/reserved request rejected");
    }
    EnrollmentRequest one = request; one.count = 1; RequestWire bad = EncodeRequest(one); bad[120] = 2;
    Check(!DecodeRequest(bad, &decoded), "unused monitor slot must be canonical zero");
    EnrollmentRequest duplicate = request; duplicate.configs[1] = duplicate.configs[0];
    Check(!ValidRequest(duplicate), "duplicate monitor level rejected");
    request.nonce.fill(0); Check(!ValidRequest(request), "zero request nonce rejected");
    response[48] = 0; std::fill(response.begin() + 48, response.begin() + 80, 0);
    Check(!DecodeGrant(response, &reply), "zero lease generation rejected");
    Bytes32 first{}, second{};
    Check(FreshRequestNonce(&first) && FreshRequestNonce(&second) && first != second,
          "fresh nonce comes from kernel randomness without deterministic fallback");
}

enum class Variant { Good, Nonce, Scope, Config, Count, NoRights, Pipe, ExtraRights,
                     Oversized, Truncated, ZeroGeneration, OldThenNew, ExtraControl,
                     Expired, Closed, WrongServer, Repeated, RepeatedUnclaimed };
static void Send(int socket, const GrantWire& wire, const std::vector<int>& fds, size_t payload_size) {
    std::array<uint8_t, kGrantSize + 1> body{}; std::copy(wire.begin(), wire.end(), body.begin());
    iovec payload{body.data(), payload_size};
    alignas(cmsghdr) unsigned char control[CMSG_SPACE(8 * sizeof(int))]{};
    msghdr message{}; message.msg_iov = &payload; message.msg_iovlen = 1;
    if (!fds.empty()) {
        message.msg_control = control; message.msg_controllen = CMSG_SPACE(fds.size() * sizeof(int));
        cmsghdr* c = CMSG_FIRSTHDR(&message); c->cmsg_level = SOL_SOCKET; c->cmsg_type = SCM_RIGHTS;
        c->cmsg_len = CMSG_LEN(fds.size() * sizeof(int)); std::memcpy(CMSG_DATA(c), fds.data(), fds.size() * sizeof(int));
    }
    ssize_t sent = sendmsg(socket, &message, MSG_NOSIGNAL);
    Need(sent == static_cast<ssize_t>(payload_size) || (sent < 0 && (errno == EPIPE || errno == ECONNRESET)), "owned grant send");
}
static void Transport(Variant variant, const char* label) {
    size_t before = Fds();
    int control[2]; Need(socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC | SOCK_NONBLOCK, 0, control) == 0, "owned control");
    Credentials credentials; Need(ReadCredentials(control[1], &credentials), "control credentials");
    std::atomic<bool> release{false}, peer_closed{false}, request_matched{false}, response_done{false};
    std::thread server([&]() {
        pollfd incoming{control[0], POLLIN | POLLRDHUP, 0};
        int ready = poll(&incoming, 1, 1000);
        if (ready <= 0 || incoming.revents & (POLLHUP | POLLRDHUP)) {
            close(control[0]); peer_closed = true; return;
        }
        RequestWire wire{}; ssize_t count = recv(control[0], wire.data(), wire.size(), MSG_DONTWAIT | MSG_TRUNC);
        EnrollmentRequest request;
        if (count != ssize_t(wire.size()) || !DecodeRequest(wire, &request)) { close(control[0]); peer_closed = true; return; }
        request_matched = request == Request();
        EnrollmentGrant grant{request, {}}; grant.generation.fill(0x51);
        std::vector<int> recipients, senders;
        size_t number = variant == Variant::ExtraRights ? 6 : 2;
        for (size_t i = 0; i < number; ++i) {
            int pair[2];
            if (variant == Variant::Pipe) {
                Need(pipe2(pair, O_CLOEXEC | O_NONBLOCK) == 0, "owned wrong-shape pipe");
                senders.push_back(pair[1]); recipients.push_back(pair[0]);
            } else {
                Need(socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC | SOCK_NONBLOCK, 0, pair) == 0, "owned recipient");
                Need(shutdown(pair[0], SHUT_RD) == 0 && shutdown(pair[1], SHUT_WR) == 0, "one-way recipient");
                senders.push_back(pair[0]); recipients.push_back(pair[1]);
            }
        }
        switch (variant) {
            case Variant::Nonce: grant.request.nonce[0] ^= 1; break;
            case Variant::Scope: ++grant.request.cgroup_inode; break;
            case Variant::Config: ++grant.request.configs[1].stall_us; break;
            case Variant::Count: grant.request.count = 1; break;
            case Variant::ZeroGeneration: grant.generation.fill(0); break;
            default: break;
        }
        if (variant == Variant::Expired) std::this_thread::sleep_for(std::chrono::milliseconds(40));
        if (variant != Variant::Closed) {
            GrantWire grant_wire = EncodeGrant(grant);
            if (variant == Variant::OldThenNew) {
                grant_wire[16] ^= 1; Send(control[0], grant_wire, recipients, kGrantSize);
                grant_wire = EncodeGrant(grant); Send(control[0], grant_wire, recipients, kGrantSize);
            } else {
                Send(control[0], grant_wire, variant == Variant::NoRights ? std::vector<int>{} : recipients,
                     variant == Variant::Oversized ? kGrantSize + 1 : variant == Variant::Truncated ? kGrantSize - 1 : kGrantSize);
            }
        }
        for (int fd : recipients) close(fd);
        if (variant == Variant::ExtraControl) {
            char extra = 'x'; ssize_t rc = send(control[0], &extra, 1, MSG_NOSIGNAL);
            Need(rc == 1 || errno == EPIPE || errno == ECONNRESET, "extra control negative");
        }
        response_done = true;
        if (variant == Variant::Closed) { close(control[0]); peer_closed = true; }
        while (!release.load()) std::this_thread::yield();
        for (int fd : senders) close(fd);
        if (variant != Variant::Closed) close(control[0]);
        peer_closed = true;
    });
    {
        EnrollmentClient client; GrantRecipients grant;
        if (variant == Variant::WrongServer) ++credentials.uid;
        bool ok = client.Exchange(control[1], credentials, Request(), variant == Variant::Expired ? 10U : 1000U, &grant);
        bool expected = variant == Variant::Good || variant == Variant::Repeated || variant == Variant::RepeatedUnclaimed;
        // Extra control is permitted to race the final receive boundary; it
        // must still invalidate Healthy before any subsequent decision.
        if (variant == Variant::ExtraControl) {
            while (!response_done.load()) std::this_thread::yield();
            Check(!peer_closed.load() && !client.Healthy(), label);
            release = true; server.join();
        } else if (expected) {
            Check(ok && grant.complete() && request_matched.load(), label);
            if (variant == Variant::RepeatedUnclaimed) {
                Check(!client.Exchange(-1, credentials, Request(), 1000, &grant) && !grant.complete() &&
                      grant.Take(0) == -1 && grant.Take(1) == -1,
                      "rejected replay clears previously successful unclaimed recipient output");
                release = true; server.join();
                Check(!client.Healthy(), "replayed client cannot keep a live enrollment authority");
            } else {
            Scope scope{grant.grant().generation, grant.grant().request.cgroup_device,
                        grant.grant().request.cgroup_inode, grant.grant().request.budget};
            Monitor first, second;
            Need(first.Adopt(grant.Take(0), scope, Request().configs[0], credentials), "first real granted monitor");
            Need(second.Adopt(grant.Take(1), scope, Request().configs[1], credentials), "second real granted monitor");
            Check(first.Consume(scope).status == Status::Empty && second.Consume(scope).status == Status::Empty,
                  "granted quiet sockets cannot synthesize pressure");
            if (variant == Variant::Repeated) Check(!client.Exchange(-1, credentials, Request(), 1000, &grant), "grant attempt cannot be replayed on existing client");
            release = true; server.join();
            Check(peer_closed.load() && !client.Healthy() && first.Consume(scope).status == Status::Revoked &&
                  second.Consume(scope).status == Status::Revoked, "server retirement invalidates control and all granted channels");
            }
        } else {
            release = true; server.join();
            Check(!ok && !grant.complete() && !client.Healthy(), label);
        }
    }
    Check(Fds() == before, "success/rejection releases every SCM_RIGHTS duplicate and control pidfd");
}
int main(int argc, char** argv) {
    Need(argc == 2, "usage test-enrollment golden-directory");
    CodecControls(argv[1]);
    for (const auto& item : std::vector<std::pair<Variant, const char*>>{
        {Variant::Good, "real SCM_RIGHTS grant carries two exact one-way packet recipients"},
        {Variant::Nonce, "stale nonce grant rejected"}, {Variant::Scope, "different cgroup inode rejected"},
        {Variant::Config, "changed exact stall threshold rejected"}, {Variant::Count, "changed monitor count rejected"},
        {Variant::NoRights, "grant without SCM_RIGHTS rejected"}, {Variant::Pipe, "pipe cannot replace packet recipient"},
        {Variant::ExtraRights, "truncated excess rights are rejected without leaks"},
        {Variant::Oversized, "oversized grant rejected"}, {Variant::Truncated, "short grant rejected"},
        {Variant::ZeroGeneration, "zero lease generation rejected"},
        {Variant::OldThenNew, "bad first grant is not retried using a queued newer grant"},
        {Variant::ExtraControl, "unsolicited post-grant control data invalidates the client"},
        {Variant::Expired, "late grant cannot extend the bounded handshake"},
        {Variant::Closed, "closed grant channel is rejected"},
        {Variant::WrongServer, "expected lifecycle server UID is not learned from response"},
        {Variant::Repeated, "initial grant succeeds before replay refusal"},
        {Variant::RepeatedUnclaimed, "unclaimed grant exists before explicit replay rejection"}}) Transport(item.first, item.second);
    std::printf("RESULT %u assertions passed; host transport only; no Android or PSI\n", passed);
    return 0;
}
