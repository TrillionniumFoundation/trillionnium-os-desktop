// SPDX-License-Identifier: MPL-2.0

#define _GNU_SOURCE
#include <arpa/inet.h>
#include <poll.h>
#include <signal.h>
#include <sys/socket.h>
#include <unistd.h>

#include "../common/test.h"

/* Regression for the native F1 DNS worker shutdown failure: a local closed
 * UDP port must wake a connected socket with POLLERR and ECONNREFUSED. */

static int bind_loopback(struct sockaddr_in *address)
{
	int fd = CHECK(socket(AF_INET, SOCK_DGRAM | SOCK_NONBLOCK, 0));
	*address = (struct sockaddr_in){
		.sin_family = AF_INET,
		.sin_addr.s_addr = htonl(INADDR_LOOPBACK),
	};
	socklen_t length = sizeof(*address);

	CHECK(bind(fd, (struct sockaddr *)address, sizeof(*address)));
	CHECK_WITH(getsockname(fd, (struct sockaddr *)address, &length),
		   _ret == 0 && length == sizeof(*address) && address->sin_port);
	return fd;
}

static int closed_port_sender(struct sockaddr_in *destination, int connected)
{
	struct sockaddr_in local;
	int reservation = bind_loopback(destination);
	/* Bind the sender before releasing the destination so an ephemeral port
	 * allocator cannot reuse the destination and turn this into self-send. */
	int sender = bind_loopback(&local);
	CHECK_WITH(local.sin_port, _ret != destination->sin_port);
	CHECK(close(reservation));
	if (connected)
		CHECK(connect(sender, (struct sockaddr *)destination,
			      sizeof(*destination)));
	return sender;
}

FN_SETUP(deadline)
{
	alarm(5);
}
END_SETUP()

FN_TEST(connected_error_is_read_once_and_delivery_recovers)
{
	struct sockaddr_in destination;
	int sender = closed_port_sender(&destination, 1);
	struct pollfd wait = { .fd = sender, .events = POLLIN };
	int error = -1;
	socklen_t length = sizeof(error);
	char byte = 0;

	TEST_RES(send(sender, "u", 1, 0), _ret == 1);
	TEST_RES(poll(&wait, 1, 500), _ret == 1 && wait.revents == POLLERR);
	TEST_RES(getsockopt(sender, SOL_SOCKET, SO_ERROR, &error, &length),
		 _ret == 0 && length == sizeof(error) && error == ECONNREFUSED);
	TEST_RES(getsockopt(sender, SOL_SOCKET, SO_ERROR, &error, &length),
		 _ret == 0 && error == 0);
	TEST_RES(poll(&wait, 1, 0), _ret == 0 && wait.revents == 0);
	TEST_ERRNO(recv(sender, &byte, 1, 0), EAGAIN);

	int receiver = CHECK(socket(AF_INET, SOCK_DGRAM | SOCK_NONBLOCK, 0));
	CHECK(bind(receiver, (struct sockaddr *)&destination, sizeof(destination)));
	TEST_RES(send(sender, "r", 1, 0), _ret == 1);
	wait.fd = receiver;
	TEST_RES(poll(&wait, 1, 500), _ret == 1 && wait.revents == POLLIN);
	TEST_RES(recv(receiver, &byte, 1, 0), _ret == 1 && byte == 'r');
	TEST_SUCC(close(receiver));
	TEST_SUCC(close(sender));
}
END_TEST()

FN_TEST(receive_consumes_error)
{
	struct sockaddr_in destination;
	int sender = closed_port_sender(&destination, 1);
	struct pollfd wait = { .fd = sender, .events = POLLIN };
	int error = -1;
	socklen_t length = sizeof(error);
	char byte = 0;

	TEST_RES(send(sender, "u", 1, 0), _ret == 1);
	TEST_RES(poll(&wait, 1, 500), _ret == 1 && wait.revents == POLLERR);
	TEST_ERRNO(recv(sender, &byte, 1, 0), ECONNREFUSED);
	TEST_RES(poll(&wait, 1, 0), _ret == 0 && wait.revents == 0);
	TEST_RES(getsockopt(sender, SOL_SOCKET, SO_ERROR, &error, &length),
		 _ret == 0 && error == 0);
	TEST_ERRNO(recv(sender, &byte, 1, 0), EAGAIN);
	TEST_SUCC(close(sender));
}
END_TEST()

FN_TEST(send_consumes_error)
{
	struct sockaddr_in destination;
	int sender = closed_port_sender(&destination, 1);
	struct pollfd wait = { .fd = sender, .events = POLLIN };
	int error = -1;
	socklen_t length = sizeof(error);

	TEST_RES(send(sender, "u", 1, 0), _ret == 1);
	TEST_RES(poll(&wait, 1, 500), _ret == 1 && wait.revents == POLLERR);
	TEST_ERRNO(send(sender, "v", 1, 0), ECONNREFUSED);
	TEST_RES(poll(&wait, 1, 0), _ret == 0 && wait.revents == 0);
	TEST_RES(getsockopt(sender, SOL_SOCKET, SO_ERROR, &error, &length),
		 _ret == 0 && error == 0);
	TEST_RES(send(sender, "w", 1, 0), _ret == 1);
	TEST_RES(poll(&wait, 1, 500), _ret == 1 && wait.revents == POLLERR);
	TEST_SUCC(close(sender));
}
END_TEST()

FN_TEST(unconnected_socket_ignores_port_unreachable_without_recverr)
{
	struct sockaddr_in destination;
	int sender = closed_port_sender(&destination, 0);
	struct pollfd wait = { .fd = sender, .events = POLLIN };
	int error = -1;
	socklen_t length = sizeof(error);

	TEST_RES(sendto(sender, "u", 1, 0, (struct sockaddr *)&destination,
			sizeof(destination)), _ret == 1);
	TEST_RES(poll(&wait, 1, 20), _ret == 0 && wait.revents == 0);
	TEST_RES(getsockopt(sender, SOL_SOCKET, SO_ERROR, &error, &length),
		 _ret == 0 && error == 0);
	TEST_SUCC(close(sender));
}
END_TEST()

FN_TEST(connected_socket_ignores_errors_for_another_destination)
{
	struct sockaddr_in peer, other;
	int receiver = bind_loopback(&peer);
	int sender = closed_port_sender(&other, 0);
	struct pollfd wait = { .fd = sender, .events = POLLIN };
	int error = -1;
	socklen_t length = sizeof(error);
	char byte = 0;

	CHECK(connect(sender, (struct sockaddr *)&peer, sizeof(peer)));
	TEST_RES(sendto(sender, "u", 1, 0, (struct sockaddr *)&other,
			sizeof(other)), _ret == 1);
	TEST_RES(poll(&wait, 1, 20), _ret == 0 && wait.revents == 0);
	TEST_RES(getsockopt(sender, SOL_SOCKET, SO_ERROR, &error, &length),
		 _ret == 0 && error == 0);
	TEST_RES(send(sender, "p", 1, 0), _ret == 1);
	wait.fd = receiver;
	TEST_RES(poll(&wait, 1, 500), _ret == 1 && wait.revents == POLLIN);
	TEST_RES(recv(receiver, &byte, 1, 0), _ret == 1 && byte == 'p');
	TEST_SUCC(close(receiver));
	TEST_SUCC(close(sender));
}
END_TEST()

FN_TEST(self_delivery_has_no_error)
{
	struct sockaddr_in local;
	int fd = bind_loopback(&local);
	struct pollfd wait = { .fd = fd, .events = POLLIN };
	int error = -1;
	socklen_t length = sizeof(error);
	char byte = 0;

	CHECK(connect(fd, (struct sockaddr *)&local, sizeof(local)));
	TEST_RES(send(fd, "s", 1, 0), _ret == 1);
	TEST_RES(poll(&wait, 1, 500), _ret == 1 && wait.revents == POLLIN);
	TEST_RES(getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &length),
		 _ret == 0 && error == 0);
	TEST_RES(recv(fd, &byte, 1, 0), _ret == 1 && byte == 's');
	TEST_SUCC(close(fd));
}
END_TEST()
