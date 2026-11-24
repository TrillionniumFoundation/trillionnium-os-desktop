/* Run only as PID 1 in the isolated, diskless Pocket4 peer-LSM mechanism VM.
 * This uses real socket hooks and real shared libraries, never a mock provider.
 * It deliberately does not load the production joint policy or qualify Android.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <pthread.h>
#include <stdalign.h>
#include <stddef.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <unistd.h>

#define PEER_OPTION 0x50340001
#define SE_ID 101
#define AA_ID 104
#define CAPACITY 4096
#define THREADS 8
#define ITERATIONS 5000
#define RELEASE "6.18.64-p4ctx6181-fusectl-aafs-peer-r1"
struct peer_header {
	uint32_t size, version;
	uint64_t lsm_id;
	uint32_t flags, reserved, context_len, reserved2;
	unsigned char context[];
};
_Static_assert(sizeof(struct peer_header) == 32, "fixed UAPI");
union packet {
	max_align_t align;
	unsigned char bytes[sizeof(struct peer_header) + CAPACITY];
};
struct label {
	socklen_t size;
	unsigned char bytes[CAPACITY];
};
static struct label selinux_peer, apparmor_peer;
static int peer_fd;
static atomic_int thread_error;
static atomic_uint_fast64_t completed_calls;
static unsigned int matrix_checks;
static int (*aa_peer)(int, char **, char **);
static int (*aa_current)(char **, char **);
static int (*aa_change)(const char *);
static int (*se_peer)(int, char **);
static void (*se_free)(char *);

static _Noreturn void finish(int success)
{
	fflush(NULL);
	if (getpid() == 1) {
		sync();
		reboot(RB_POWER_OFF);
	}
	_exit(success ? 0 : 1);
}
static void require(int good, const char *what)
{
	if (!good) {
		fprintf(stderr, "P4_PEER_RUNTIME_FAILED %s errno=%d\n", what, errno);
		finish(0);
	}
}
static void require_errno(int rc, int observed_errno, int wanted_errno,
			  const char *stage)
{
	if (rc != -1 || observed_errno != wanted_errno) {
		fprintf(stderr, "P4_PEER_RUNTIME_FAILED %s rc=%d errno=%d expected_rc=-1 expected_errno=%d\n",
			stage, rc, observed_errno, wanted_errno);
		finish(0);
	}
}
static void directory(const char *path)
{
	require(mkdir(path, 0755) == 0 || errno == EEXIST, path);
}
static void mount_fs(const char *type, const char *path)
{
	directory(path);
	require(mount(type, path, type, MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL) == 0,
		path);
}
static size_t read_file(const char *path, char *out, size_t capacity)
{
	int fd = open(path, O_RDONLY | O_CLOEXEC);
	require(fd >= 0, path);
	ssize_t n = read(fd, out, capacity - 1);
	require(n >= 0 && (size_t)n < capacity - 1, "bounded read");
	out[n] = 0;
	require(close(fd) == 0, "close read");
	return (size_t)n;
}
static struct peer_header *request(union packet *p, uint64_t provider)
{
	memset(p->bytes, 0xa7, sizeof(p->bytes));
	struct peer_header *h = (struct peer_header *)p->bytes;
	memset(h, 0, sizeof(*h));
	h->size = sizeof(*h);
	h->version = 1;
	h->lsm_id = provider;
	return h;
}
static int selected(int fd, uint64_t provider, struct label *label)
{
	union packet p;
	struct peer_header *h = request(&p, provider);
	socklen_t size = sizeof(p.bytes);
	if (getsockopt(fd, SOL_SOCKET, PEER_OPTION, h, &size))
		return 0;
	if (h->size != sizeof(*h) || h->version != 1 ||
	    h->lsm_id != provider || h->flags || h->reserved || h->reserved2 ||
	    !h->context_len || h->context_len > CAPACITY ||
	    size != sizeof(*h) + h->context_len)
		return 0;
	label->size = h->context_len;
	memcpy(label->bytes, h->context, label->size);
	return 1;
}
static int legacy(int fd, struct label *label)
{
	label->size = sizeof(label->bytes);
	return getsockopt(fd, SOL_SOCKET, SO_PEERSEC, label->bytes, &label->size) == 0 &&
		label->size > 0 && label->size <= sizeof(label->bytes);
}
static int same(const struct label *a, const struct label *b)
{
	return a->size == b->size && !memcmp(a->bytes, b->bytes, a->size);
}
static int text_matches(const struct label *raw, const char *text)
{
	size_t n = raw->size;
	if (n && raw->bytes[n - 1] == 0)
		n--;
	return text && strlen(text) == n && !memcmp(raw->bytes, text, n);
}
static int library_selinux(void)
{
	char *context = NULL;
	int rc = se_peer(peer_fd, &context);
	int ok = rc == 0 && text_matches(&selinux_peer, context);
	if (context)
		se_free(context);
	return ok;
}
static int library_apparmor(void)
{
	char *label = NULL, *mode = NULL;
	int rc = aa_peer(peer_fd, &label, &mode);
	char formatted[CAPACITY];
	int n = !label ? -1 : mode ?
		snprintf(formatted, sizeof(formatted), "%s (%s)", label, mode) :
		snprintf(formatted, sizeof(formatted), "%s", label);
	int ok = rc > 0 && n >= 0 && (size_t)n < sizeof(formatted) &&
		text_matches(&apparmor_peer, formatted);
	free(label);
	return ok;
}
static void *worker(void *argument)
{
	uintptr_t kind = (uintptr_t)argument;
	for (unsigned int i = 0; i < ITERATIONS; i++) {
		struct label current;
		int ok;
		if (kind == 0)
			ok = legacy(peer_fd, &current) && same(&current, &selinux_peer);
		else if (kind == 1)
			ok = selected(peer_fd, SE_ID, &current) &&
				same(&current, &selinux_peer);
		else if (kind == 2)
			ok = selected(peer_fd, AA_ID, &current) &&
				same(&current, &apparmor_peer);
		else
			ok = library_selinux() && library_apparmor();
		if (!ok) {
			atomic_store(&thread_error, 1);
			return NULL;
		}
		atomic_fetch_add(&completed_calls, kind == 3 ? 2 : 1);
	}
	return NULL;
}
static void invalid_header(unsigned int mutation)
{
	union packet p;
	struct peer_header *h = request(&p, AA_ID);
	socklen_t size = sizeof(p.bytes);
	switch (mutation) {
	case 0: size = sizeof(*h) - 1; break;
	case 1: h->size--; break;
	case 2: h->size++; break;
	case 3: h->version = 0; break;
	case 4: h->version = 2; break;
	case 5: h->flags = 1; break;
	case 6: h->reserved = 1; break;
	case 7: h->reserved2 = 1; break;
	case 8: h->context_len = 1; break;
	case 9: h->lsm_id = 0; break;
	case 10: h->lsm_id = 102; break;
	case 11: h->lsm_id = UINT64_MAX; break;
	case 12: size = (socklen_t)-1; break;
	default: require(0, "unknown matrix mutation");
	}
	errno = 0;
	int rc = getsockopt(peer_fd, SOL_SOCKET, PEER_OPTION, h, &size);
	require_errno(rc, errno, EINVAL, "invalid request rejected");
	matrix_checks++;
}
static void short_buffer(uint64_t provider, const struct label *baseline,
			 socklen_t capacity)
{
	union packet p;
	struct peer_header *h = request(&p, provider);
	socklen_t size = sizeof(*h) + capacity;
	errno = 0;
	int rc = getsockopt(peer_fd, SOL_SOCKET, PEER_OPTION, h, &size);
	require_errno(rc, errno, ERANGE, "short buffer ERANGE");
	require(h->size == sizeof(*h) && h->version == 1 &&
		h->lsm_id == provider && !h->flags && !h->reserved &&
		!h->reserved2 && h->context_len == baseline->size &&
		size == sizeof(*h) + baseline->size, "ERANGE exact header and length");
	for (size_t i = sizeof(*h); i < sizeof(p.bytes); i++)
		require(p.bytes[i] == 0xa7, "ERANGE copied no context body");
	matrix_checks++;
}
static void load_denial_profile(void)
{
	unsigned char bytes[65536];
	int fd = open("/peer-deny.bin", O_RDONLY | O_CLOEXEC);
	require(fd >= 0, "open fixed denial profile");
	struct stat st;
	require(fstat(fd, &st) == 0 && S_ISREG(st.st_mode) &&
		st.st_size > 0 && st.st_size < (off_t)sizeof(bytes), "profile bound");
	ssize_t n = read(fd, bytes, sizeof(bytes));
	require(n == st.st_size, "read fixed denial profile");
	require(close(fd) == 0, "close denial input");
	fd = open("/sys/kernel/security/apparmor/.load", O_WRONLY | O_CLOEXEC);
	require(fd >= 0, "open native AA policy loader");
	require(write(fd, bytes, (size_t)n) == n, "load fixed denial profile");
	require(close(fd) == 0, "close native AA loader");
}
static void outer_denial(void)
{
	load_denial_profile();
	pid_t child = fork();
	require(child >= 0, "fork denial witness");
	if (!child) {
		require(aa_change("p4-peer-deny") == 0, "native AA change_profile");
		char *label = NULL, *mode = NULL;
		require(aa_current(&label, &mode) > 0 && label && mode &&
			!strcmp(label, "p4-peer-deny") && !strcmp(mode, "enforce"),
			"actual enforced AppArmor test label");
		free(label);
		for (unsigned int i = 0; i < 3; i++) {
			union packet p;
			struct peer_header *h = request(&p, i == 0 ? SE_ID : AA_ID);
			socklen_t n = sizeof(p.bytes);
			errno = 0;
			int option = i == 2 ? SO_PEERSEC : PEER_OPTION;
			int rc = getsockopt(peer_fd, SOL_SOCKET, option, h, &n);
			require_errno(rc, errno, EACCES, "outer AA gate preserves denial");
		}
		_exit(0);
	}
	int status = 0;
	require(waitpid(child, &status, 0) == child && WIFEXITED(status) &&
		WEXITSTATUS(status) == 0, "real denial child normal exit");
	matrix_checks += 3;
}
static void *symbol(void *library, const char *name, const char *path)
{
	void *address = dlsym(library, name);
	Dl_info info;
	require(address && dladdr(address, &info) != 0 && info.dli_fname &&
		!strcmp(info.dli_fname, path), "actual fixed package library symbol");
	return address;
}
int main(void)
{
	if (getpid() != 1) {
		fprintf(stderr, "This test is only an isolated diskless VM init.\n");
		return 77;
	}
	struct utsname kernel;
	require(uname(&kernel) == 0 && !strcmp(kernel.release, RELEASE),
		"matching complete kernel release");
	umask(077);
	mount_fs("proc", "/proc");
	mount_fs("sysfs", "/sys");
	directory("/dev");
	require(mount("devtmpfs", "/dev", "devtmpfs", MS_NOSUID, NULL) == 0,
		"private VM devtmpfs");
	int console = open("/dev/console", O_RDWR | O_CLOEXEC);
	require(console >= 0, "console");
	for (int i = 0; i < 3; i++)
		require(dup2(console, i) == i, "console stdio");
	if (console > 2)
		close(console);
	mount_fs("securityfs", "/sys/kernel/security");
	mount_fs("selinuxfs", "/sys/fs/selinux");
	char lsms[1024], enforce[16];
	read_file("/sys/kernel/security/lsm", lsms, sizeof(lsms));
	read_file("/sys/fs/selinux/enforce", enforce, sizeof(enforce));
	char *se_position = strstr(lsms, "selinux"), *aa_position = strstr(lsms, "apparmor");
	require(se_position && aa_position && se_position < aa_position &&
		enforce[0] == '1', "real enforcing stacked LSM order");
	printf("P4_PEER_RUNTIME_START kernel=%s lsm=%s", kernel.release, lsms);
	const char *aa_path = "/usr/lib/x86_64-linux-gnu/libapparmor.so.1";
	const char *se_path = "/usr/lib/x86_64-linux-gnu/libselinux.so.1";
	void *aa = dlopen(aa_path, RTLD_NOW | RTLD_LOCAL);
	void *se = dlopen(se_path, RTLD_NOW | RTLD_LOCAL);
	require(aa && se, "actual candidate library loading");
	aa_peer = (int (*)(int, char **, char **))symbol(aa, "aa_getpeercon", aa_path);
	aa_current = (int (*)(char **, char **))symbol(aa, "aa_getcon", aa_path);
	aa_change = (int (*)(const char *))symbol(aa, "aa_change_profile", aa_path);
	se_peer = (int (*)(int, char **))symbol(se, "getpeercon_raw", se_path);
	se_free = (void (*)(char *))symbol(se, "freecon", se_path);
	int pair[2];
	require(socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, pair) == 0,
		"real connected AF_UNIX stream");
	peer_fd = pair[0];
	struct label old;
	require(selected(peer_fd, SE_ID, &selinux_peer) &&
		selected(peer_fd, AA_ID, &apparmor_peer) &&
		legacy(peer_fd, &old) && same(&old, &selinux_peer) &&
		!same(&selinux_peer, &apparmor_peer), "distinct original peer providers");
	require(text_matches(&selinux_peer, "kernel") &&
		text_matches(&apparmor_peer, "unconfined"),
		"isolated pre-production-policy mechanism scope");
	require(library_selinux() && library_apparmor(), "actual public peer APIs");
	for (unsigned int i = 0; i < 13; i++)
		invalid_header(i);
	short_buffer(SE_ID, &selinux_peer, 0);
	short_buffer(SE_ID, &selinux_peer, selinux_peer.size - 1);
	short_buffer(AA_ID, &apparmor_peer, 0);
	short_buffer(AA_ID, &apparmor_peer, apparmor_peer.size - 1);
	socklen_t n = sizeof(struct peer_header);
	errno = 0;
	int rc = getsockopt(peer_fd, SOL_SOCKET, PEER_OPTION, NULL, &n);
	require_errno(rc, errno, EFAULT, "null request EFAULT");
	matrix_checks++;
	int unconnected = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
	require(unconnected >= 0, "unconnected stream socket");
	/* The original SELinux hook initializes an unconnected stream's peer SID
	 * to UNLABELED. Preserve that real legacy result; it is not an error. */
	struct label unconnected_old;
	unconnected_old.size = sizeof(unconnected_old.bytes);
	errno = 0;
	int old_rc = getsockopt(unconnected, SOL_SOCKET, SO_PEERSEC,
			      unconnected_old.bytes, &unconnected_old.size);
	int old_errno = errno;
	union packet packet;
	struct peer_header *h = request(&packet, SE_ID);
	n = sizeof(packet.bytes);
	errno = 0;
	rc = getsockopt(unconnected, SOL_SOCKET, PEER_OPTION, h, &n);
	int selected_errno = errno;
	printf("P4_PEER_RUNTIME_OBSERVED unconnected-selinux legacy_rc=%d legacy_errno=%d legacy_len=%u selected_rc=%d selected_errno=%d selected_len=%u\n",
	       old_rc, old_errno, unconnected_old.size, rc, selected_errno, n);
	require(old_rc == 0 && rc == 0 && old_errno == selected_errno &&
		unconnected_old.size > 0 && unconnected_old.size <= CAPACITY &&
		h->size == sizeof(*h) && h->version == 1 && h->lsm_id == SE_ID &&
		!h->flags && !h->reserved && !h->reserved2 &&
		h->context_len == unconnected_old.size &&
		n == sizeof(*h) + h->context_len &&
		!memcmp(h->context, unconnected_old.bytes, unconnected_old.size) &&
		text_matches(&unconnected_old, "unlabeled"),
		"unconnected SELinux preserves exact original unlabeled context");
	/* AppArmor has no peer label on this same stream. The new option maps
	 * that provider's ENOPROTOOPT to EOPNOTSUPP, without legacy fallback. */
	h = request(&packet, AA_ID);
	n = sizeof(packet.bytes);
	errno = 0;
	rc = getsockopt(unconnected, SOL_SOCKET, PEER_OPTION, h, &n);
	require_errno(rc, errno, EOPNOTSUPP, "AppArmor stream has no peer");
	matrix_checks++;
	require(close(unconnected) == 0, "close unconnected stream");
	/* A datagram is outside the original SELinux stream hook's supported
	 * classes, so it supplies a separate real unsupported-provider check. */
	int datagram = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
	require(datagram >= 0, "unconnected datagram socket");
	h = request(&packet, SE_ID);
	n = sizeof(packet.bytes);
	errno = 0;
	rc = getsockopt(datagram, SOL_SOCKET, PEER_OPTION, h, &n);
	require_errno(rc, errno, EOPNOTSUPP, "SELinux stream hook rejects datagram");
	matrix_checks++;
	require(close(datagram) == 0, "close unconnected datagram");
	pthread_t threads[THREADS];
	for (uintptr_t i = 0; i < THREADS; i++)
		require(pthread_create(&threads[i], NULL, worker, (void *)(i % 4)) == 0,
			"start concurrent real queries");
	for (unsigned int i = 0; i < THREADS; i++)
		require(pthread_join(threads[i], NULL) == 0, "join query thread");
	require(!atomic_load(&thread_error) &&
		atomic_load(&completed_calls) == 10U * ITERATIONS,
		"all concurrent provider and public-library queries unchanged");
	require(legacy(peer_fd, &old) && same(&old, &selinux_peer),
		"legacy socket provider unchanged after concurrency");
	outer_denial();
	printf("P4_PEER_RUNTIME_RESULT {\"schema\":\"p4-peer-lsm-real-kernel-mechanism-v1\","
	       "\"kernel\":\"%s\",\"threads\":%u,\"iterations_per_thread\":%u,"
	       "\"actual_concurrent_calls\":%lu,\"error_and_denial_checks\":%u,"
	       "\"legacy_provider_unchanged\":true,\"actual_public_library_calls\":true,"
	       "\"outer_apparmor_denial_preserved\":true,\"production_policy_loaded\":false,"
	       "\"production_qualified\":false,\"exit_code\":0}\n",
	       kernel.release, THREADS, ITERATIONS,
	       (unsigned long)atomic_load(&completed_calls), matrix_checks);
	finish(1);
}
