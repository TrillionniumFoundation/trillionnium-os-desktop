/* Focused public-library ABI tests. The getsockopt provider below is an
 * explicit test double; this executable is not a kernel/runtime qualification.
 */
#define _GNU_SOURCE
#include <sys/apparmor.h>
#include <sys/socket.h>
#include <dlfcn.h>
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define P4_SO_PEERSEC_LSM 0x50340001
struct peer_header {
	uint32_t size, version;
	uint64_t lsm_id;
	uint32_t flags, reserved, context_len, reserved2;
	unsigned char context[];
};
_Static_assert(sizeof(struct peer_header) == 32, "wire size");

static const char *test_case;
static unsigned int new_calls, old_calls;
static char growing_label[261];

static void require(int truth, const char *message)
{
	if (!truth) {
		fprintf(stderr, "%s: %s (errno=%d)\n", test_case, message, errno);
		exit(1);
	}
}

static int named(const char *name)
{
	return strcmp(test_case, name) == 0;
}

int getsockopt(int fd, int level, int option, void *value, socklen_t *length)
{
	const char *label = named("grow") ? growing_label :
		named("wrong-label") ? "u:r:kernel:s0" :
		named("unconfined") ? "unconfined" : "peer-test (enforce)";
	size_t n = strlen(label);
	require(fd == 37 && level == SOL_SOCKET, "unexpected socket request");
	if (option == SO_PEERSEC) {
		old_calls++;
		require(named("legacy"), "fallback after a supported or denied request");
		require(*length >= n, "legacy test buffer too short");
		memcpy(value, label, n);
		*length = n;
		return 0;
	}
	require(option == P4_SO_PEERSEC_LSM, "wrong per-call option");
	new_calls++;
	struct peer_header *h = value;
	require(*length >= sizeof(*h), "header capacity");
	require(h->size == sizeof(*h) && h->version == 1 && h->lsm_id == 104 &&
		!h->flags && !h->reserved && !h->context_len && !h->reserved2,
		"request did not select exactly AppArmor with a clean header");
	if (named("legacy")) {
		errno = ENOPROTOOPT;
		return -1;
	}
	const struct { const char *name; int error; } errors[] = {
		{"eacces", EACCES}, {"eperm", EPERM}, {"einval", EINVAL},
		{"eopnotsupp", EOPNOTSUPP}, {"eintr", EINTR}, {"enosys", ENOSYS},
	};
	for (size_t i = 0; i < sizeof(errors) / sizeof(errors[0]); ++i)
		if (named(errors[i].name)) {
			errno = errors[i].error;
			return -1;
		}
	socklen_t capacity = *length - sizeof(*h);
	h->context_len = n;
	*length = sizeof(*h) + n;
	if (named("bad-size")) h->size--;
	if (named("bad-version")) h->version++;
	if (named("bad-provider")) h->lsm_id = 101;
	if (named("flags")) h->flags = 1;
	if (named("reserved")) h->reserved = 1;
	if (named("reserved2")) h->reserved2 = 1;
	if (named("short-header")) *length = sizeof(*h) - 1;
	if (named("bad-length")) (*length)++;
	if (named("empty")) h->context_len = 0;
	if (named("oversized")) {
		h->context_len = capacity + 1;
		*length = sizeof(*h) + h->context_len;
		return 0;
	}
	if (named("range-within-capacity")) {
		errno = ERANGE;
		return -1;
	}
	if (capacity < n) {
		errno = ERANGE;
		return -1;
	}
	memcpy(h->context, label, n);
	return 0;
}

int main(int argc, char **argv)
{
	require(argc == 3, "case and actual library required");
	test_case = argv[1];
	Dl_info info;
	void *symbol = dlsym(RTLD_DEFAULT, "aa_getpeercon_raw");
	require(symbol && dladdr(symbol, &info), "actual public symbol provider");
	char *actual = realpath(info.dli_fname, NULL);
	char *wanted = realpath(argv[2], NULL);
	require(actual && wanted && strcmp(actual, wanted) == 0,
		"test did not load the exact candidate package library");
	free(actual);
	free(wanted);
	memset(growing_label, 'p', sizeof(growing_label));
	memcpy(growing_label + 250, " (enforce)", 11);
	if (named("grow")) {
		char *label = NULL, *mode = NULL;
		int rc = aa_getpeercon(37, &label, &mode);
		require(rc == 261 && label && strlen(label) == 250 &&
			mode && strcmp(mode, "enforce") == 0, "growth/termination");
		require(new_calls == 3 && old_calls == 0, "precise ERANGE retries");
		free(label);
	} else {
		char buffer[128];
		memset(buffer, 0x5a, sizeof(buffer));
		char *mode = NULL;
		socklen_t size = named("range") ? 5 :
			named("overflow") ? UINT_MAX : sizeof(buffer);
		errno = 0;
		int rc = aa_getpeercon_raw(37, buffer, &size, &mode);
		int err = errno;
		if (named("success") || named("legacy")) {
			require(rc == 20 && size == 20 && strcmp(buffer, "peer-test") == 0 &&
				mode && strcmp(mode, "enforce") == 0, "normal context parsing");
			require(new_calls == 1 && old_calls == (unsigned int)named("legacy"),
				"only unsupported option falls back");
		} else if (named("unconfined")) {
			require(rc == 11 && strcmp(buffer, "unconfined") == 0 &&
				!mode && new_calls == 1 && !old_calls, "unconfined context");
		} else if (named("range")) {
			require(rc == -1 && err == ERANGE && size == 19 &&
				buffer[0] == 0x5a && new_calls == 1 && !old_calls,
				"required size without partial context");
		} else if (named("overflow")) {
			require(rc == -1 && err == EOVERFLOW && !new_calls && !old_calls,
				"oversized length accepted");
		} else {
			int expected = EPROTO;
			if (named("eacces")) expected = EACCES;
			if (named("eperm")) expected = EPERM;
			if (named("einval") || named("wrong-label")) expected = EINVAL;
			if (named("eopnotsupp")) expected = EOPNOTSUPP;
			if (named("eintr")) expected = EINTR;
			if (named("enosys")) expected = ENOSYS;
			require(rc == -1 && err == expected && new_calls == 1 && !old_calls,
				"error was bypassed, misclassified or retried");
		}
	}
	printf("{\"case\":\"%s\",\"new_calls\":%u,\"legacy_calls\":%u,"
		"\"kernel_test_double\":true,\"passed\":true}\n",
		test_case, new_calls, old_calls);
	return 0;
}
