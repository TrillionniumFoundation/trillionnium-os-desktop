/* SPDX-License-Identifier: Apache-2.0
 * Real IPv4 ancillary controls, confined to this disposable guest's loopback.
 * Original NetLabel v3 generic-netlink ABI; no external interface or network.
 */
#include <arpa/inet.h>
#include <linux/genetlink.h>
#include <linux/netlink.h>
#include <net/if.h>

#define P4_CIPSO_DOI 8764U
#define P4_PACKET_CONTEXT "u:object_r:p4_packet_peer_t:s0"

struct p4_nl_attrs { unsigned char bytes[1024]; size_t length; };
static uint32_t p4_nl_sequence = 876400;

static int p4_nla_add(struct p4_nl_attrs *a, uint16_t type, const void *data, size_t length)
{
    size_t total = NLA_HDRLEN + length, padded = NLA_ALIGN(total);
    if (total > UINT16_MAX || a->length + padded > sizeof(a->bytes)) { errno = EOVERFLOW; return -1; }
    struct nlattr h = {.nla_len = (uint16_t)total, .nla_type = type};
    memcpy(a->bytes + a->length, &h, sizeof(h));
    memcpy(a->bytes + a->length + NLA_HDRLEN, data, length);
    memset(a->bytes + a->length + total, 0, padded - total);
    a->length += padded; return 0;
}

static int p4_genl(uint16_t family, uint8_t command, uint8_t version,
                   const struct p4_nl_attrs *attrs, int want_data,
                   unsigned char *reply, size_t *reply_length)
{
    unsigned char request[2048] = {0}, response[8192];
    struct nlmsghdr *header = (struct nlmsghdr *)request;
    struct genlmsghdr *generic = (struct genlmsghdr *)(request + NLMSG_HDRLEN);
    uint32_t sequence = ++p4_nl_sequence;
    header->nlmsg_len = NLMSG_HDRLEN + GENL_HDRLEN + attrs->length;
    header->nlmsg_type = family;
    header->nlmsg_flags = NLM_F_REQUEST | (want_data ? 0 : NLM_F_ACK);
    header->nlmsg_seq = sequence;
    generic->cmd = command; generic->version = version;
    memcpy(request + NLMSG_HDRLEN + GENL_HDRLEN, attrs->bytes, attrs->length);
    int fd = socket(AF_NETLINK, SOCK_RAW | SOCK_CLOEXEC, NETLINK_GENERIC);
    if (fd < 0) return -1;
    struct sockaddr_nl local = {.nl_family = AF_NETLINK}, kernel = {.nl_family = AF_NETLINK};
    int error = bind(fd, (struct sockaddr *)&local, sizeof(local)) ? errno : 0;
    if (!error && sendto(fd, request, header->nlmsg_len, 0, (struct sockaddr *)&kernel, sizeof(kernel)) != (ssize_t)header->nlmsg_len)
        error = errno ? errno : EIO;
    long long deadline = milliseconds() + 2500;
    int complete = 0;
    while (!error && !complete) {
        int remaining = (int)(deadline - milliseconds());
        if (remaining <= 0) { error = ETIMEDOUT; break; }
        struct pollfd pollfd = {fd, POLLIN, 0};
        int ready = poll(&pollfd, 1, remaining);
        if (ready < 0 && errno == EINTR) continue;
        if (ready <= 0) { error = ready ? errno : ETIMEDOUT; break; }
        struct sockaddr_nl from = {0};
        struct iovec vector = {response, sizeof(response)};
        struct msghdr message = {.msg_name = &from, .msg_namelen = sizeof(from), .msg_iov = &vector, .msg_iovlen = 1};
        ssize_t count = recvmsg(fd, &message, 0);
        if (count < 0) { error = errno; break; }
        if (from.nl_pid || (message.msg_flags & MSG_TRUNC)) { error = EPROTO; break; }
        size_t offset = 0;
        while (offset + NLMSG_HDRLEN <= (size_t)count) {
            struct nlmsghdr h; memcpy(&h, response + offset, sizeof(h));
            if (h.nlmsg_len < NLMSG_HDRLEN || h.nlmsg_len > (size_t)count - offset || h.nlmsg_seq != sequence) { error = EPROTO; break; }
            if (h.nlmsg_type == NLMSG_ERROR) {
                struct nlmsgerr e;
                if (h.nlmsg_len < NLMSG_HDRLEN + sizeof(e)) { error = EPROTO; break; }
                memcpy(&e, response + offset + NLMSG_HDRLEN, sizeof(e));
                if (e.error) error = e.error < 0 ? -e.error : EPROTO;
                else if (!want_data) complete = 1;
            } else if (want_data && h.nlmsg_type == family && h.nlmsg_len >= NLMSG_HDRLEN + GENL_HDRLEN) {
                size_t length = h.nlmsg_len - NLMSG_HDRLEN - GENL_HDRLEN;
                if (!reply || !reply_length || length > *reply_length) { error = EOVERFLOW; break; }
                memcpy(reply, response + offset + NLMSG_HDRLEN + GENL_HDRLEN, length);
                *reply_length = length; complete = 1;
            } else { error = EPROTO; break; }
            offset += NLMSG_ALIGN(h.nlmsg_len);
        }
        if (!error && offset != (size_t)count) error = EPROTO;
    }
    close(fd); if (error) { errno = error; return -1; } return 0;
}

static int p4_nla_read(const unsigned char *data, size_t length, uint16_t type, void *value, size_t size)
{
    size_t offset = 0; int found = 0;
    while (offset + NLA_HDRLEN <= length) {
        struct nlattr h; memcpy(&h, data + offset, sizeof(h));
        if (h.nla_len < NLA_HDRLEN || h.nla_len > length - offset) { errno = EPROTO; return -1; }
        if ((h.nla_type & NLA_TYPE_MASK) == type) {
            if (found++ || (size_t)h.nla_len - NLA_HDRLEN != size) { errno = EPROTO; return -1; }
            memcpy(value, data + offset + NLA_HDRLEN, size);
        }
        offset += NLA_ALIGN(h.nla_len);
    }
    if (offset != length || found != 1) { errno = EPROTO; return -1; }
    return 0;
}

static int p4_genl_family(const char *name, uint16_t *family)
{
    struct p4_nl_attrs attrs = {0}; unsigned char response[4096]; size_t length = sizeof(response);
    if (p4_nla_add(&attrs, CTRL_ATTR_FAMILY_NAME, name, strlen(name) + 1) ||
        p4_genl(GENL_ID_CTRL, CTRL_CMD_GETFAMILY, 2, &attrs, 1, response, &length) ||
        p4_nla_read(response, length, CTRL_ATTR_FAMILY_ID, family, sizeof(*family))) return -1;
    if (*family < NLMSG_MIN_TYPE) { errno = EPROTO; return -1; } return 0;
}

static int p4_cipso_query(uint16_t family)
{
    struct p4_nl_attrs attrs = {0}; uint32_t doi = P4_CIPSO_DOI, map = 0;
    unsigned char response[4096]; size_t length = sizeof(response);
    if (p4_nla_add(&attrs, 1, &doi, sizeof(doi)) ||
        p4_genl(family, 3, 3, &attrs, 1, response, &length) ||
        p4_nla_read(response, length, 2, &map, sizeof(map))) return -1;
    /* Original netlbl_cipsov4_list replies with MTYPE/TAGLST, not DOI. */
    if (map != 2) { errno = EPROTO; return -1; } return 0;
}

static int p4_cipso_change(uint16_t family, int add)
{
    struct p4_nl_attrs attrs = {0}, tags = {0}; uint32_t doi = P4_CIPSO_DOI, map = 2; uint8_t tag = 1;
    if (p4_nla_add(&attrs, 1, &doi, sizeof(doi))) return -1;
    if (add && (p4_nla_add(&attrs, 2, &map, sizeof(map)) || p4_nla_add(&tags, 3, &tag, sizeof(tag)) ||
                p4_nla_add(&attrs, 4 | NLA_F_NESTED, tags.bytes, tags.length))) return -1;
    return p4_genl(family, add ? 1 : 2, 3, &attrs, 0, NULL, NULL);
}

static int p4_domain_change(uint16_t family, int add)
{
    struct p4_nl_attrs attrs = {0}; const char domain[] = "p4_context_a_t";
    uint32_t protocol = 3, doi = P4_CIPSO_DOI; uint16_t address_family = AF_INET;
    if (p4_nla_add(&attrs, 1, domain, sizeof(domain))) return -1;
    if (add) {
        if (p4_nla_add(&attrs, 2, &protocol, sizeof(protocol)) || p4_nla_add(&attrs, 4, &doi, sizeof(doi))) return -1;
    } else if (p4_nla_add(&attrs, 11, &address_family, sizeof(address_family))) return -1;
    return p4_genl(family, add ? 1 : 2, 3, &attrs, 0, NULL, NULL);
}

static int p4_cipso_options(const unsigned char *bytes, size_t length)
{
    int found = 0; size_t offset = 0;
    while (offset < length) {
        if (!bytes[offset]) break;
        if (bytes[offset] == 1) { offset++; continue; }
        if (offset + 2 > length || bytes[offset + 1] < 2 || offset + bytes[offset + 1] > length) return 0;
        size_t size = bytes[offset + 1];
        if (bytes[offset] == 134) {
            uint32_t doi = 0;
            if (found++ || size < 10) return 0;
            memcpy(&doi, bytes + offset + 2, sizeof(doi));
            if (ntohl(doi) != P4_CIPSO_DOI || bytes[offset + 6] != 1 ||
                bytes[offset + 7] < 4 || (size_t)bytes[offset + 7] + 6 != size ||
                bytes[offset + 8] != 0 || bytes[offset + 9] != 0) return 0;
        }
        offset += size;
    }
    return found == 1;
}

static int p4_loopback(int restore, short *original)
{
    int fd = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (fd < 0) return -1;
    struct ifreq request = {0}; memcpy(request.ifr_name, "lo", 3);
    int error = ioctl(fd, SIOCGIFFLAGS, &request) ? errno : 0;
    if (!error && !(request.ifr_flags & IFF_LOOPBACK)) error = EPROTO;
    if (!error && !restore) {
        *original = request.ifr_flags;
        if (request.ifr_flags & IFF_UP) error = EBUSY;
    }
    if (!error) {
        request.ifr_flags = restore ? *original : (*original | IFF_UP);
        if (ioctl(fd, SIOCSIFFLAGS, &request)) error = errno;
    }
    if (!error && ioctl(fd, SIOCGIFFLAGS, &request)) error = errno;
    if (!error && (restore ? request.ifr_flags != *original : !(request.ifr_flags & IFF_UP))) error = EPROTO;
    close(fd); if (error) { errno = error; return -1; } return 0;
}

static struct { int selected, receiver, transport[2]; uint16_t port; ino_t inode; } ip_work;
static const char ip_payload[] = "p4-8764-cipso-loopback-only";

static void p4_udp_sender(struct observation *o, int unused)
{
    (void)unused;
    close(ip_work.receiver); close(ip_work.transport[0]); close(ip_work.transport[1]);
    if (setns(ip_work.selected ? selected_net : initial_net, CLONE_NEWNET) || change_pair('a', 1, 1) || drop_identity()) { o->error = errno; return; }
    o->caps = caps_zero();
    read_text("/proc-selected/self/attr/current", o->text[0], sizeof(o->text[0]));
    read_text("/proc/self/attr/apparmor/current", o->text[1], sizeof(o->text[1]));
    int fd = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (fd < 0) { o->error = errno; return; }
    struct sockaddr_in address = {.sin_family = AF_INET, .sin_port = ip_work.port, .sin_addr.s_addr = htonl(INADDR_LOOPBACK)};
    if (connect(fd, (struct sockaddr *)&address, sizeof(address))) o->error = errno;
    unsigned char options[64] = {0}; socklen_t length = sizeof(options);
    if (!o->error && getsockopt(fd, SOL_IP, IP_OPTIONS, options, &length)) o->error = errno;
    o->values[0] = (int)length; o->values[1] = p4_cipso_options(options, length);
    if (!o->error) {
        ssize_t sent = send(fd, ip_payload, sizeof(ip_payload), MSG_NOSIGNAL);
        o->values[2] = (int)sent;
        if (sent != (ssize_t)sizeof(ip_payload)) o->error = sent < 0 ? errno : EPROTO;
    }
    close(fd);
}

static void p4_udp_receiver(struct observation *o, int unused)
{
    (void)unused; close(ip_work.transport[0]);
    if (setns(ip_work.selected ? initial_net : selected_net, CLONE_NEWNET) || change_pair('b', 1, 1) || drop_identity()) { o->error = errno; return; }
    o->caps = caps_zero();
    read_text("/proc-selected/self/attr/current", o->text[2], sizeof(o->text[2]));
    read_text("/proc/self/attr/apparmor/current", o->text[3], sizeof(o->text[3]));
    int fd = receive_fd(ip_work.transport[1]);
    if (fd < 0) { o->error = errno; return; }
    struct stat info; if (fstat(fd, &info) || info.st_ino != ip_work.inode) { o->error = errno ? errno : EPROTO; close(fd); return; }
    o->values[4] = 1;
    unsigned char data[128] = {0};
    union { struct cmsghdr alignment; unsigned char bytes[1024]; } ancillary = {0};
    struct iovec vector = {data, sizeof(data)};
    struct msghdr message = {.msg_iov = &vector, .msg_iovlen = 1, .msg_control = ancillary.bytes, .msg_controllen = sizeof(ancillary.bytes)};
    ssize_t got = recvmsg(fd, &message, 0); o->values[0] = (int)got;
    if (got != (ssize_t)sizeof(ip_payload) || memcmp(data, ip_payload, sizeof(ip_payload)) || (message.msg_flags & (MSG_TRUNC | MSG_CTRUNC))) o->error = got < 0 ? errno : EPROTO;
    for (struct cmsghdr *c = CMSG_FIRSTHDR(&message); !o->error && c; c = CMSG_NXTHDR(&message, c)) {
        if (c->cmsg_level != SOL_IP || c->cmsg_len < CMSG_LEN(0)) { o->error = EPROTO; break; }
        size_t length = c->cmsg_len - CMSG_LEN(0);
        if (c->cmsg_type == SCM_SECURITY) {
            if (o->values[1]++ || !length || length >= sizeof(o->text[0]) || strnlen((char *)CMSG_DATA(c), length) != length - 1) { o->error = EPROTO; break; }
            memcpy(o->text[0], CMSG_DATA(c), length);
        } else if (c->cmsg_type == IP_RECVOPTS) {
            if (o->values[2]++ || !p4_cipso_options(CMSG_DATA(c), length)) { o->error = EPROTO; break; }
            o->values[3] = (int)length;
        } else { o->error = EPROTO; break; }
    }
    close(fd); close(ip_work.transport[1]);
}

static void p4_udp_control(int selected, int setup_error)
{
    memset(&ip_work, 0, sizeof(ip_work)); ip_work.selected = selected;
    ip_work.receiver = ip_work.transport[0] = ip_work.transport[1] = -1;
    int error = setup_error, enabled = 1, up = 0, retired = 0; short original_flags = 0;
    struct observation sent = {0}, received = {0}; struct sockaddr_in address = {.sin_family = AF_INET, .sin_addr.s_addr = htonl(INADDR_LOOPBACK)};
    if (!error && setns(selected ? selected_net : initial_net, CLONE_NEWNET)) error = errno;
    if (!error) { if (p4_loopback(0, &original_flags)) error = errno; else up = 1; }
    if (!error && (ip_work.receiver = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0)) < 0) error = errno;
    struct timeval timeout = {.tv_sec = 3};
    if (!error && (setsockopt(ip_work.receiver, SOL_IP, IP_PASSSEC, &enabled, sizeof(enabled)) ||
                   setsockopt(ip_work.receiver, SOL_IP, IP_RECVOPTS, &enabled, sizeof(enabled)) ||
                   setsockopt(ip_work.receiver, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) ||
                   bind(ip_work.receiver, (struct sockaddr *)&address, sizeof(address)))) error = errno;
    socklen_t length = sizeof(address);
    if (!error && getsockname(ip_work.receiver, (struct sockaddr *)&address, &length)) error = errno;
    ip_work.port = address.sin_port;
    struct stat info;
    if (!error && fstat(ip_work.receiver, &info)) error = errno;
    if (!error) ip_work.inode = info.st_ino;
    if (setns(initial_net, CLONE_NEWNET) && !error) error = errno;
    if (!error && socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, ip_work.transport)) error = errno;
    if (!error && worker(p4_udp_sender, 0, &sent)) error = errno;
    if (!error && sent.error) error = sent.error;
    if (!error && send_fd(ip_work.transport[0], ip_work.receiver)) error = errno;
    if (ip_work.receiver >= 0) { close(ip_work.receiver); ip_work.receiver = -1; }
    if (!error && worker(p4_udp_receiver, 0, &received)) error = errno;
    if (!error && received.error) error = received.error;
    for (unsigned i = 0; i < 2; i++) if (ip_work.transport[i] >= 0) close(ip_work.transport[i]);
    if (up) {
        if (setns(selected ? selected_net : initial_net, CLONE_NEWNET) || p4_loopback(1, &original_flags)) { if (!error) error = errno; }
        else retired = 1;
    }
    if (setns(initial_net, CLONE_NEWNET) && !error) error = errno;
    int passed = !error && retired && sent.caps && received.caps && sent.values[1] && received.values[2] == 1 && received.values[4] &&
        !strcmp(sent.text[0], SEL_A) && !strcmp(sent.text[1], AA_A) && !strcmp(received.text[2], SEL_B) && !strcmp(received.text[3], AA_B);
    if (selected) passed = passed && received.values[1] == 1 && !strcmp(received.text[0], P4_PACKET_CONTEXT);
    else passed = passed && !received.values[1] && !received.text[0][0];
    report(selected ? "ip_passsec_selected_cipso_after_fd_netns_transfer" : "ip_passsec_default_cipso_no_fallback", passed, error,
           "UDP 127.0.0.1 only; DOI=%u source_CIPSO=%d/%dB sender_sent=%d sender_error=%d receive_CIPSO=%d/%dB payload=%d "
           "SCM=%s count=%d expected=%s inode_preserved=%d; sender=%s receiver=%s caps_zero=[%d,%d] loopback_restored=%d",
           P4_CIPSO_DOI, sent.values[1], sent.values[0], sent.values[2], sent.error, received.values[2], received.values[3], received.values[0],
           received.text[0], received.values[1], selected ? P4_PACKET_CONTEXT : "none", received.values[4],
           sent.text[0], received.text[2], sent.caps, received.caps, retired);
}

static void ip_positive_controls(void)
{
    uint16_t cipso = 0, management = 0; int error = 0, doi_added = 0, domain_added = 0;
    if (setns(initial_net, CLONE_NEWNET) || p4_genl_family("NLBL_CIPSOv4", &cipso) || p4_genl_family("NLBL_MGMT", &management)) error = errno;
    if (!error) {
        if (!p4_cipso_query(cipso)) error = EEXIST;
        /* Original netlbl_cipsov4_list returns EINVAL for an absent DOI. */
        else if (errno != EINVAL) error = errno;
    }
    if (!error) { if (p4_cipso_change(cipso, 1)) error = errno; else doi_added = 1; }
    if (!error) { if (p4_domain_change(management, 1)) error = errno; else domain_added = 1; }
    if (!error && p4_cipso_query(cipso)) error = errno;
    report("ip_guest_only_cipso_setup", !error && doi_added && domain_added, error,
           "NetLabel v3 families=[%u,%u] owned DOI=%u pass-through MLS0; exact domain=p4_context_a_t; no external NIC", cipso, management, P4_CIPSO_DOI);
    p4_udp_control(0, error); p4_udp_control(1, error);
    int cleanup_error = 0;
    if (domain_added && p4_domain_change(management, 0)) cleanup_error = errno;
    if (doi_added && p4_cipso_change(cipso, 0) && !cleanup_error) cleanup_error = errno;
    int absent = 0;
    if (doi_added) { absent = p4_cipso_query(cipso) < 0 && errno == EINVAL; if (!absent && !cleanup_error) cleanup_error = EPROTO; }
    report("ip_guest_cipso_objects_retired", !error && !cleanup_error && absent, cleanup_error,
           "only owned domain/DOI removed; DOI lookup original-ABI EINVAL=%d; guest has no external network or disk", absent);
}
