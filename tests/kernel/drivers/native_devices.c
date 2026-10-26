// SPDX-License-Identifier: MPL-2.0
// Disposable Asterinas guest probe; never execute this program on the host.
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <linux/input.h>
#include <linux/kd.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/utsname.h>
#include <unistd.h>

static const char *nonce;

static void fail(const char *stage)
{
	fprintf(stderr, "TRILL_NATIVE_DRIVER_FAIL stage=%s errno=%d\n", stage,
		errno);
	exit(65);
}

static void require(int condition, const char *stage)
{
	if (!condition)
		fail(stage);
}

static void json_string(const char *text)
{
	putchar('"');
	for (; *text; text++) {
		unsigned char ch = *text;
		if (ch == '"' || ch == '\\')
			printf("\\%c", ch);
		else if (ch < 32 || ch > 126)
			printf("\\u%04x", ch);
		else
			putchar(ch);
	}
	putchar('"');
}

static void guest_guard(void)
{
	char cmdline[4097], marker[96];
	int fd = open("/proc/cmdline", O_RDONLY | O_CLOEXEC);
	require(fd >= 0, "guest_cmdline_open");
	ssize_t count = read(fd, cmdline, sizeof(cmdline) - 1);
	require(count > 0 && count < (ssize_t)sizeof(cmdline) - 1,
		"guest_cmdline_bound");
	cmdline[count] = 0;
	close(fd);
	snprintf(marker, sizeof(marker), "trill_driver_probe=%s", nonce);
	require(strstr(cmdline, marker) != NULL, "guest_command_binding");
	require(geteuid() == 0, "guest_root_required");
}

static int open_keyboard(char *path, char *name, struct input_id *id,
			 struct stat *metadata)
{
	DIR *directory = opendir("/dev/input");
	require(directory != NULL, "evdev_directory_missing");
	struct dirent *entry;
	int selected = -1;
	while ((entry = readdir(directory)) != NULL) {
		if (strncmp(entry->d_name, "event", 5) != 0)
			continue;
		char candidate[256], candidate_name[128] = { 0 };
		require(snprintf(candidate, sizeof(candidate), "/dev/input/%s",
				 entry->d_name) < (int)sizeof(candidate),
			"evdev_path_bound");
		int fd = open(candidate, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
		require(fd >= 0, "evdev_open");
		require(ioctl(fd, EVIOCGNAME(sizeof(candidate_name)),
			      candidate_name) >= 0,
			"evdev_name");
		if (strcmp(candidate_name, "QEMU Virtio Keyboard") != 0) {
			close(fd);
			continue;
		}
		require(selected < 0, "ambiguous_virtio_keyboard");
		int version = 0;
		unsigned char keys[(KEY_MAX + 8) / 8] = { 0 };
		require(ioctl(fd, EVIOCGVERSION, &version) == 0 &&
				version == EV_VERSION,
			"evdev_version");
		require(ioctl(fd, EVIOCGID, id) == 0, "evdev_id");
		require(ioctl(fd, EVIOCGBIT(EV_KEY, sizeof(keys)), keys) >= 0 &&
				(keys[KEY_A / 8] & (1U << (KEY_A % 8))),
			"evdev_key_capability");
		require(fstat(fd, metadata) == 0 && S_ISCHR(metadata->st_mode),
			"evdev_character_identity");
		strcpy(path, candidate);
		strcpy(name, candidate_name);
		selected = fd;
	}
	closedir(directory);
	require(selected >= 0, "virtio_keyboard_missing");
	return selected;
}

static uint32_t channel(unsigned char value, struct fb_bitfield field)
{
	require(field.length > 0 && field.length <= 8 && field.msb_right == 0 &&
			field.offset + field.length <= 32,
		"framebuffer_channel");
	return ((uint32_t)value * ((1U << field.length) - 1) / 255)
	       << field.offset;
}

static int draw_frame(struct fb_var_screeninfo *variable,
		      struct fb_fix_screeninfo *fixed, struct stat *metadata)
{
	int fd = open("/dev/fb0", O_RDWR | O_CLOEXEC);
	require(fd >= 0, "framebuffer_missing");
	require(fstat(fd, metadata) == 0 && S_ISCHR(metadata->st_mode),
		"framebuffer_character_identity");
	require(ioctl(fd, FBIOGET_VSCREENINFO, variable) == 0 &&
			ioctl(fd, FBIOGET_FSCREENINFO, fixed) == 0,
		"framebuffer_geometry_ioctl");
	fprintf(stderr, "TRILL_NATIVE_DRIVER_FB_OBSERVED width=%u height=%u bpp=%u xoffset=%u yoffset=%u pitch=%u bytes=%u\n",
		variable->xres, variable->yres, variable->bits_per_pixel,
		variable->xoffset, variable->yoffset, fixed->line_length,
		fixed->smem_len);
	require(variable->xres == 1024 && variable->yres == 768 &&
			variable->xoffset == 0 && variable->yoffset == 0 &&
			(variable->bits_per_pixel == 16 ||
			 variable->bits_per_pixel == 24 ||
			 variable->bits_per_pixel == 32),
		"framebuffer_explicit_mode");
	unsigned int pixel_bytes = variable->bits_per_pixel / 8;
	require(fixed->smem_len > 0 && fixed->smem_len <= 16 * 1024 * 1024 &&
			fixed->line_length >= variable->xres * pixel_bytes &&
			fixed->smem_len >= fixed->line_length * variable->yres,
		"framebuffer_mapping_bound");
	int tty = open("/dev/tty0", O_RDWR | O_CLOEXEC);
	require(tty >= 0 && ioctl(tty, KDSETMODE, KD_GRAPHICS) == 0,
		"framebuffer_graphics_mode");
	close(tty);
	unsigned char *map = mmap(NULL, fixed->smem_len, PROT_READ | PROT_WRITE,
				 MAP_SHARED, fd, 0);
	require(map != MAP_FAILED, "framebuffer_map");
	static const unsigned char colors[4][3] = {
		{ 255, 0, 0 }, { 0, 255, 0 }, { 0, 0, 255 }, { 255, 255, 255 }
	};
	for (unsigned int y = 0; y < variable->yres; y++) {
		for (unsigned int x = 0; x < variable->xres; x++) {
			const unsigned char *color =
				colors[x / (variable->xres / 4)];
			uint32_t pixel = channel(color[0], variable->red) |
					 channel(color[1], variable->green) |
					 channel(color[2], variable->blue);
			unsigned char *dest = map + y * fixed->line_length +
					      x * pixel_bytes;
			memcpy(dest, &pixel, pixel_bytes);
			require(memcmp(dest, &pixel, pixel_bytes) == 0,
				"framebuffer_mapping_readback");
		}
	}
	require(munmap(map, fixed->smem_len) == 0, "framebuffer_unmap");
	return fd;
}

static uint64_t retain_storage(const char *mode, struct stat *metadata)
{
	require(mkdir("/driver-state", 0700) == 0, "storage_mount_directory");
	require(mount("/dev/vda", "/driver-state", "ext2", 0, NULL) == 0,
		"virtio_block_ext2_mount");
	unsigned char expected[4096], actual[4096];
	for (size_t i = 0; i < sizeof(expected); i++)
		expected[i] = ((unsigned char)nonce[i % 64]) ^ (i & 255);
	int flags = O_RDONLY | O_CLOEXEC | O_NOFOLLOW;
	if (strcmp(mode, "write") == 0)
		flags = O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW;
	int fd = open("/driver-state/original-driver-state.bin", flags, 0600);
	require(fd >= 0, "storage_open");
	if (strcmp(mode, "write") == 0) {
		require(write(fd, expected, sizeof(expected)) == sizeof(expected),
			"storage_original_write");
		require(fsync(fd) == 0, "storage_original_fsync");
	}
	require(fstat(fd, metadata) == 0 && S_ISREG(metadata->st_mode) &&
			metadata->st_size == sizeof(expected) &&
			metadata->st_nlink == 1,
		"storage_original_identity");
	require(pread(fd, actual, sizeof(actual), 0) == sizeof(actual) &&
			memcmp(actual, expected, sizeof(actual)) == 0,
		"storage_exact_readback");
	uint64_t hash = UINT64_C(14695981039346656037);
	for (size_t i = 0; i < sizeof(actual); i++)
		hash = (hash ^ actual[i]) * UINT64_C(1099511628211);
	close(fd);
	int dir = open("/driver-state", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
	require(dir >= 0 && fsync(dir) == 0, "storage_parent_fsync");
	close(dir);
	require(umount("/driver-state") == 0, "storage_unmount");
	return hash;
}

static void key_roundtrip(int fd)
{
	int pressed = 0, released = 0;
	for (int attempt = 0; attempt < 100 && !released; attempt++) {
		struct pollfd pollfd = { .fd = fd, .events = POLLIN };
		int ready = poll(&pollfd, 1, 100);
		require(ready >= 0, "keyboard_poll");
		if (!ready)
			continue;
		require(pollfd.revents & POLLIN, "keyboard_readiness");
		struct input_event events[16];
		ssize_t count = read(fd, events, sizeof(events));
		require(count > 0 && count % sizeof(events[0]) == 0,
			"keyboard_event_frame");
		for (size_t i = 0; i < (size_t)count / sizeof(events[0]); i++) {
			if (events[i].type != EV_KEY)
				continue;
			require(events[i].code == KEY_A, "keyboard_exact_code");
			if (events[i].value == 1) {
				require(!pressed && !released, "keyboard_single_press");
				pressed = 1;
			} else if (events[i].value == 0) {
				require(pressed && !released, "keyboard_single_release");
				released = 1;
			} else
				fail("keyboard_repeat_not_requested");
		}
	}
	require(pressed && released, "keyboard_roundtrip_timeout");
}

int main(int argc, char **argv)
{
	require(argc == 3, "arguments");
	nonce = argv[1];
	require(strlen(nonce) == 64 && strspn(nonce, "0123456789abcdef") == 64,
		"nonce");
	const char *mode = argv[2];
	require(strcmp(mode, "write") == 0 || strcmp(mode, "read") == 0,
		"storage_mode");
	guest_guard();
	struct utsname system;
	require(uname(&system) == 0, "uname");
	char input_path[256], input_name[128];
	struct input_id input_id;
	struct stat input_stat, fb_stat, storage_stat;
	int keyboard = open_keyboard(input_path, input_name, &input_id, &input_stat);
	struct fb_var_screeninfo variable;
	struct fb_fix_screeninfo fixed;
	int framebuffer = draw_frame(&variable, &fixed, &fb_stat);
	uint64_t storage_hash = retain_storage(mode, &storage_stat);
	printf("TRILL_NATIVE_DRIVER_V1 {\"nonce\":\"%s\",\"event\":\"ready\","
	       "\"mode\":\"%s\",\"input_path\":", nonce, mode);
	json_string(input_path);
	printf(",\"input_name\":");
	json_string(input_name);
	printf(",\"input_major\":%u,\"input_minor\":%u,\"input_bus\":%u,"
	       "\"input_vendor\":%u,\"input_product\":%u,\"width\":%u,"
	       "\"height\":%u,\"bpp\":%u,\"pitch\":%u,\"fb_bytes\":%u,"
	       "\"storage_device\":%llu,\"storage_inode\":%llu,"
	       "\"storage_bytes\":%llu,\"storage_hash\":\"%016llx\",\"system\":",
	       major(input_stat.st_rdev), minor(input_stat.st_rdev),
	       input_id.bustype, input_id.vendor, input_id.product, variable.xres,
	       variable.yres, variable.bits_per_pixel, fixed.line_length,
	       fixed.smem_len, (unsigned long long)storage_stat.st_dev,
	       (unsigned long long)storage_stat.st_ino,
	       (unsigned long long)storage_stat.st_size,
	       (unsigned long long)storage_hash);
	json_string(system.sysname);
	printf("}\n");
	fflush(stdout);
	key_roundtrip(keyboard);
	close(keyboard);
	close(framebuffer);
	printf("TRILL_NATIVE_DRIVER_V1 {\"nonce\":\"%s\",\"event\":\"complete\","
	       "\"mode\":\"%s\",\"key_code\":%d,\"presses\":1,\"releases\":1}\n",
	       nonce, mode, KEY_A);
	fflush(stdout);
	return 0;
}
