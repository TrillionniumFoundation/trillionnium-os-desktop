#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/socket.h>
#include <unistd.h>

/* Isolated loopback ABI diagnostic. Never opens an external network route. */
static int bound_socket(struct sockaddr_in *address) {
    int fd = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
    if (fd < 0) return -1;
    *address = (struct sockaddr_in){.sin_family = AF_INET,
                                  .sin_addr.s_addr = htonl(INADDR_LOOPBACK)};
    socklen_t len = sizeof(*address);
    if (bind(fd, (struct sockaddr *)address, sizeof(*address)) ||
        getsockname(fd, (struct sockaddr *)address, &len)) {
        int saved = errno;
        close(fd);
        errno = saved;
        return -1;
    }
    return fd;
}

static int positive_control(void) {
    struct sockaddr_in address;
    int receiver = bound_socket(&address);
    int sender = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
    int setup = receiver >= 0 && sender >= 0;
    if (setup) setup = connect(sender, (struct sockaddr *)&address, sizeof(address)) == 0;
    int setup_errno = setup ? 0 : errno;
    errno = 0;
    ssize_t sent = setup ? send(sender, "U", 1, 0) : -1;
    int send_errno = errno;
    struct pollfd wait = {.fd = receiver, .events = POLLIN};
    errno = 0;
    int polled = setup ? poll(&wait, 1, 500) : -1;
    int poll_errno = errno;
    char byte = 0;
    errno = 0;
    ssize_t received = setup ? recv(receiver, &byte, 1, 0) : -1;
    int recv_errno = errno;
    int passed = setup && sent == 1 && polled == 1 && (wait.revents & POLLIN)
                 && received == 1 && byte == 'U';
    printf("HEPTA_UDP_ERROR case=loopback-positive passed=%s setup=%d setup_errno=%d "
           "send_rc=%ld send_errno=%d poll_rc=%d poll_errno=%d revents=%x recv_rc=%ld recv_errno=%d\n",
           passed ? "true" : "false", setup, setup_errno, (long)sent, send_errno,
           polled, poll_errno, (unsigned short)wait.revents, (long)received, recv_errno);
    if (sender >= 0) close(sender);
    if (receiver >= 0) close(receiver);
    return passed;
}

static int closed_port_control(void) {
    struct sockaddr_in address;
    struct sockaddr_in sender_address;
    int reservation = bound_socket(&address);
    /* Keep the destination reserved until the sender has a distinct port. */
    int sender = bound_socket(&sender_address);
    int setup = reservation >= 0 && sender >= 0;
    if (setup && address.sin_port == sender_address.sin_port) {
        errno = EADDRINUSE;
        setup = 0;
    }
    if (reservation >= 0) close(reservation);
    if (setup) setup = connect(sender, (struct sockaddr *)&address, sizeof(address)) == 0;
    int setup_errno = setup ? 0 : errno;
    errno = 0;
    ssize_t sent = setup ? send(sender, "U", 1, 0) : -1;
    int send_errno = errno;
    struct pollfd wait = {.fd = sender, .events = POLLIN};
    errno = 0;
    int polled = setup ? poll(&wait, 1, 500) : -1;
    int poll_errno = errno;
    int socket_error = -1;
    socklen_t length = sizeof(socket_error);
    errno = 0;
    int got_error = setup ? getsockopt(sender, SOL_SOCKET, SO_ERROR, &socket_error, &length) : -1;
    int get_errno = errno;
    int passed = setup && sent == 1 && polled == 1 && (wait.revents & POLLERR)
                 && got_error == 0 && length == sizeof(socket_error) && socket_error == ECONNREFUSED;
    printf("HEPTA_UDP_ERROR case=connected-closed-port passed=%s setup=%d setup_errno=%d "
           "send_rc=%ld send_errno=%d poll_rc=%d poll_errno=%d revents=%x "
           "getsockopt_rc=%d getsockopt_errno=%d so_error=%d destination_port=%u sender_port=%u\n",
           passed ? "true" : "false", setup, setup_errno, (long)sent, send_errno,
           polled, poll_errno, (unsigned short)wait.revents, got_error, get_errno, socket_error,
           reservation >= 0 ? (unsigned)ntohs(address.sin_port) : 0,
           sender >= 0 ? (unsigned)ntohs(sender_address.sin_port) : 0);
    if (sender >= 0) close(sender);
    return passed;
}

int main(void) {
    alarm(5);
    setvbuf(stdout, NULL, _IONBF, 0);
    int positive = positive_control();
    int closed = closed_port_control();
    int failures = !positive + !closed;
    printf("HEPTA_UDP_ERROR_COMPLETE cases=2 failures=%d\n", failures);
    return failures ? 1 : 0;
}
