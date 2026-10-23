// SPDX-License-Identifier: MPL-2.0

// Regression for unbounded aggregate argv/envp copying during exec.
// Exercise real exec syscalls; every successful image reaches a known SIGILL.

#define _GNU_SOURCE
#include <elf.h>
#include <limits.h>
#include <signal.h>
#include <stddef.h>
#include <sys/fcntl.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

#include "../../common/test.h"

#define KIB ((size_t)1024)
#define MIB (1024 * KIB)
#define ARG_CHUNK (16 * KIB)
#define ARG_STRING_MAX (128 * KIB)
#define BASE_ADDRESS 0x10000

#if defined(__x86_64__)
#define ELF_MACHINE EM_X86_64
static const unsigned char illegal_instr[] = { 0x0f, 0x0b };
#elif defined(__riscv) && __riscv_xlen == 64
#define ELF_MACHINE EM_RISCV
static const unsigned char illegal_instr[] = { 0, 0, 0, 0 };
#elif defined(__aarch64__)
#define ELF_MACHINE EM_AARCH64
static const unsigned char illegal_instr[] = { 0, 0, 0, 0 };
#else
#error "unsupported architecture"
#endif

static char directory[] = "/tmp/execve-args-XXXXXX";
static char exe_path[PATH_MAX];
static char script_path[PATH_MAX];

enum exec_mode { USE_EXECVE, USE_EXECVEAT, USE_SCRIPT };
enum exec_result { IMAGE_RAN, RETURNED_E2BIG, UNEXPECTED_RESULT };

FN_SETUP(init_exec_args)
{
	struct {
		Elf64_Ehdr ehdr;
		Elf64_Phdr phdr;
		unsigned char code[4];
	} elf = { 0 };
	char shebang[PATH_MAX + 4];
	int fd, len;

	CHECK_WITH(mkdtemp(directory), _ret != NULL);
	CHECK_WITH(snprintf(exe_path, sizeof(exe_path), "%s/elf", directory),
		   _ret > 0 && (size_t)_ret < sizeof(exe_path));
	CHECK_WITH(snprintf(script_path, sizeof(script_path), "%s/script", directory),
		   _ret > 0 && (size_t)_ret < sizeof(script_path));

	memcpy(elf.ehdr.e_ident, ELFMAG, SELFMAG);
	elf.ehdr.e_ident[EI_CLASS] = ELFCLASS64;
	elf.ehdr.e_ident[EI_DATA] = ELFDATA2LSB;
	elf.ehdr.e_ident[EI_VERSION] = EV_CURRENT;
	elf.ehdr.e_type = ET_EXEC;
	elf.ehdr.e_machine = ELF_MACHINE;
	elf.ehdr.e_version = EV_CURRENT;
	elf.ehdr.e_entry = BASE_ADDRESS + offsetof(typeof(elf), code);
	elf.ehdr.e_phoff = offsetof(typeof(elf), phdr);
	elf.ehdr.e_phentsize = sizeof(Elf64_Phdr);
	elf.ehdr.e_phnum = 1;
	elf.phdr.p_type = PT_LOAD;
	elf.phdr.p_flags = PF_R | PF_X;
	elf.phdr.p_vaddr = BASE_ADDRESS;
	elf.phdr.p_filesz = sizeof(elf);
	elf.phdr.p_memsz = 4096;
	memcpy(elf.code, illegal_instr, sizeof(illegal_instr));

	fd = CHECK(open(exe_path, O_WRONLY | O_CREAT | O_EXCL, 0700));
	CHECK_WITH(write(fd, &elf, sizeof(elf)), _ret == sizeof(elf));
	CHECK(close(fd));
	len = CHECK_WITH(snprintf(shebang, sizeof(shebang), "#!%s\n", exe_path),
			 _ret > 0 && (size_t)_ret < sizeof(shebang));
	fd = CHECK(open(script_path, O_WRONLY | O_CREAT | O_EXCL, 0700));
	CHECK_WITH(write(fd, shebang, len), _ret == len);
	CHECK(close(fd));
}
END_SETUP()

static enum exec_result run_exec(char **argv, char **envp, rlim_t stack_bytes,
				 enum exec_mode mode)
{
	struct rlimit limit;
	pid_t pid;
	int status;

	CHECK(getrlimit(RLIMIT_STACK, &limit));
	CHECK_WITH(stack_bytes, _ret <= limit.rlim_max);
	pid = CHECK(fork());
	if (pid == 0) {
		struct rlimit no_core = { 0, 0 };
		const char *path = mode == USE_SCRIPT ? script_path : exe_path;

		limit.rlim_cur = stack_bytes;
		if (setrlimit(RLIMIT_STACK, &limit) ||
		    setrlimit(RLIMIT_CORE, &no_core))
			_exit(125);
		if (mode == USE_EXECVEAT)
			syscall(SYS_execveat, AT_FDCWD, path, argv, envp, 0);
		else
			execve(path, argv, envp);
		// Reaching _exit also proves an E2BIG failure returned to the
		// original image instead of killing it after exec admission.
		_exit(errno == E2BIG ? 77 : 126);
	}
	CHECK_WITH(waitpid(pid, &status, 0), _ret == pid);
	if (WIFSIGNALED(status) && WTERMSIG(status) == SIGILL)
		return IMAGE_RAN;
	if (WIFEXITED(status) && WEXITSTATUS(status) == 77)
		return RETURNED_E2BIG;
	fprintf(stderr, "unexpected child status=%#x mode=%d\n", status, mode);
	return UNEXPECTED_RESULT;
}

struct argument_vectors {
	char **argv;
	char **envp;
	char *full;
	char *tail;
};

// Only two buffers hold the nonempty strings. Repeated user pointers must
// still be charged repeatedly for the actual copies made by exec.
static struct argument_vectors make_vectors(size_t count, size_t total_bytes,
					    int argv_only, int empty_argv0)
{
	struct argument_vectors vectors;
	size_t argc = argv_only ? count : count / 2;
	size_t envc = count - argc;
	size_t full_count = count - 1 - empty_argv0;
	size_t tail_bytes = total_bytes - count * sizeof(char *) -
			    full_count * ARG_CHUNK - empty_argv0;

	CHECK_WITH(count, _ret >= 2);
	CHECK_WITH(tail_bytes, _ret > 0 && _ret <= ARG_STRING_MAX);
	vectors.argv = CHECK_WITH(calloc(argc + 1, sizeof(char *)), _ret != NULL);
	vectors.envp = CHECK_WITH(calloc(envc + 1, sizeof(char *)), _ret != NULL);
	vectors.full = CHECK_WITH(malloc(ARG_CHUNK), _ret != NULL);
	vectors.tail = CHECK_WITH(malloc(tail_bytes), _ret != NULL);
	memset(vectors.full, 'A', ARG_CHUNK - 1);
	vectors.full[ARG_CHUNK - 1] = 0;
	memset(vectors.tail, 'B', tail_bytes - 1);
	vectors.tail[tail_bytes - 1] = 0;
	for (size_t i = 0; i < count; ++i) {
		char *string = i == count - 1 ? vectors.tail : vectors.full;

		if (empty_argv0 && i == 0)
			string = "";
		if (i < argc)
			vectors.argv[i] = string;
		else
			vectors.envp[i - argc] = string;
	}
	return vectors;
}

static void free_vectors(struct argument_vectors *vectors)
{
	free(vectors->argv);
	free(vectors->envp);
	free(vectors->full);
	free(vectors->tail);
}

static size_t argument_bytes(size_t budget_bytes)
{
#ifndef __asterinas__
	// Linux additionally copies the executable filename onto its stack.
	// Asterinas has no such copy; compare each kernel at its actual boundary.
	budget_bytes -= strlen(exe_path) + 1;
#endif
	return budget_bytes;
}

static enum exec_result run_boundary(rlim_t stack_bytes, size_t budget_bytes,
				    size_t excess_bytes, int argv_only,
				    enum exec_mode mode)
{
	struct argument_vectors vectors = make_vectors(
		budget_bytes / ARG_CHUNK,
		argument_bytes(budget_bytes) + excess_bytes, argv_only, 0);
	enum exec_result result = run_exec(vectors.argv, vectors.envp,
					   stack_bytes, mode);

	free_vectors(&vectors);
	return result;
}

FN_TEST(combined_argv_envp_exact_limit)
{
	TEST_RES(run_boundary(8 * MIB, 2 * MIB, 0, 0, USE_EXECVE), _ret == IMAGE_RAN);
	TEST_RES(run_boundary(8 * MIB, 2 * MIB, 1, 0, USE_EXECVE), _ret == RETURNED_E2BIG);
}
END_TEST()

FN_TEST(argv_alone_exact_limit)
{
	TEST_RES(run_boundary(8 * MIB, 2 * MIB, 0, 1, USE_EXECVE), _ret == IMAGE_RAN);
	TEST_RES(run_boundary(8 * MIB, 2 * MIB, 1, 1, USE_EXECVE), _ret == RETURNED_E2BIG);
}
END_TEST()

FN_TEST(execveat_shares_the_total_limit)
{
	TEST_RES(run_boundary(8 * MIB, 2 * MIB, 0, 0, USE_EXECVEAT), _ret == IMAGE_RAN);
	TEST_RES(run_boundary(8 * MIB, 2 * MIB, 1, 0, USE_EXECVEAT), _ret == RETURNED_E2BIG);
}
END_TEST()

FN_TEST(stack_limit_has_a_128k_floor)
{
	TEST_RES(run_boundary(256 * KIB, 128 * KIB, 0, 0, USE_EXECVE), _ret == IMAGE_RAN);
	TEST_RES(run_boundary(256 * KIB, 128 * KIB, 1, 0, USE_EXECVE), _ret == RETURNED_E2BIG);
}
END_TEST()

FN_TEST(stack_limit_uses_one_quarter)
{
	TEST_RES(run_boundary(1 * MIB, 256 * KIB, 0, 0, USE_EXECVE), _ret == IMAGE_RAN);
	TEST_RES(run_boundary(1 * MIB, 256 * KIB, 1, 0, USE_EXECVE), _ret == RETURNED_E2BIG);
}
END_TEST()

FN_TEST(stack_limit_has_a_6m_ceiling)
{
	TEST_RES(run_boundary(32 * MIB, 6 * MIB, 0, 0, USE_EXECVE), _ret == IMAGE_RAN);
	TEST_RES(run_boundary(32 * MIB, 6 * MIB, 1, 0, USE_EXECVE), _ret == RETURNED_E2BIG);
}
END_TEST()

FN_TEST(empty_strings_still_consume_pointer_storage)
{
	size_t bytes = argument_bytes(128 * KIB);
	size_t count = bytes / (sizeof(char *) + 1);
	size_t remainder = bytes % (sizeof(char *) + 1);
	char tail[sizeof(char *) + 1];
	char **argv = CHECK_WITH(calloc(count + 2, sizeof(char *)), _ret != NULL);

	memset(tail, 'x', remainder);
	tail[remainder] = 0;
	for (size_t i = 0; i < count; ++i)
		argv[i] = "";
	argv[count - 1] = tail;
	TEST_RES(run_exec(argv, NULL, 256 * KIB, USE_EXECVE), _ret == IMAGE_RAN);
	argv[count] = "";
	TEST_RES(run_exec(argv, NULL, 256 * KIB, USE_EXECVE), _ret == RETURNED_E2BIG);
	free(argv);
}
END_TEST()

FN_TEST(single_string_limit_includes_nul)
{
	char *string = CHECK_WITH(malloc(ARG_STRING_MAX + 1), _ret != NULL);
	char *argv[] = { string, NULL };

	memset(string, 'x', ARG_STRING_MAX + 1);
	string[ARG_STRING_MAX - 1] = 0;
	TEST_RES(run_exec(argv, NULL, 8 * MIB, USE_EXECVE), _ret == IMAGE_RAN);
	string[ARG_STRING_MAX - 1] = 'x';
	string[ARG_STRING_MAX] = 0;
	TEST_RES(run_exec(argv, NULL, 8 * MIB, USE_EXECVE), _ret == RETURNED_E2BIG);
	free(string);
}
END_TEST()

#ifdef __asterinas__
FN_TEST(shebang_replacement_consumes_the_same_budget)
{
	// argv[0] is replaced by the interpreter and script paths. Its one-byte
	// empty string and pointer are refunded; the two new entries are charged.
	size_t extra = strlen(exe_path) + 1 + strlen(script_path) + 1 +
		       sizeof(char *) - 1;
	for (size_t excess = 0; excess <= 1; ++excess) {
		struct argument_vectors vectors = make_vectors(
			2 * MIB / ARG_CHUNK, 2 * MIB - extra + excess, 0, 1);
		enum exec_result expected = excess ? RETURNED_E2BIG : IMAGE_RAN;

		TEST_RES(run_exec(vectors.argv, vectors.envp, 8 * MIB, USE_SCRIPT),
			 _ret == expected);
		free_vectors(&vectors);
	}
}
END_TEST()
#endif

FN_TEST(null_vectors_remain_accepted)
{
	TEST_RES(run_exec(NULL, NULL, 8 * MIB, USE_EXECVE), _ret == IMAGE_RAN);
}
END_TEST()

FN_SETUP(cleanup_exec_args)
{
	CHECK(unlink(script_path));
	CHECK(unlink(exe_path));
	CHECK(rmdir(directory));
}
END_SETUP()
