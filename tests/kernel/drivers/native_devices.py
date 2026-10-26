#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Bounded evidence rules for the actual disposable device guest.

These functions parse evidence. They never manufacture a device, execute a
probe on Linux, or confer physical-hardware/production qualification.
"""

import json
import re


PREFIX = b"TRILL_NATIVE_DRIVER_V1 "
SERIAL_LIMIT = 1024 * 1024
FRAME_WIDTH, FRAME_HEIGHT = 1024, 768
COLORS = ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def grub_loader_image(original):
    """Undo only OSDK make_elf_for_qemu's documented e_machine conversion."""
    require(isinstance(original, bytes) and 64 <= len(original) <= 64 * 1024 * 1024,
            "bounded original ELF required")
    require(original[:7] == b"\x7fELF\x02\x01\x01" and original[16:20] == b"\x02\x00\x03\x00",
            "original OSDK x86_64/QEMU ELF64 EM_386 required")
    result = original[:18] + b"\x3e\x00" + original[20:]
    require(result[:18] == original[:18] and result[20:] == original[20:],
            "only the documented loader header may differ")
    return result


def original_pattern(nonce):
    require(isinstance(nonce, str) and re.fullmatch(r"[0-9a-f]{64}", nonce), "exact nonce required")
    return bytes(ord(nonce[i % 64]) ^ (i & 255) for i in range(4096))


def original_hash(nonce):
    value = 14695981039346656037
    for byte in original_pattern(nonce):
        value = ((value ^ byte) * 1099511628211) & ((1 << 64) - 1)
    return f"{value:016x}"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate device record field")
        result[key] = value
    return result


def records(serial, nonce, mode, *, complete):
    require(isinstance(serial, bytes) and len(serial) <= SERIAL_LIMIT, "bounded serial required")
    require(mode in ("write", "read"), "named storage mode required")
    require(b"TRILL_NATIVE_DRIVER_FAIL" not in serial and b"Kernel panic" not in serial
            and b"ERROR: Uncaught panic" not in serial,
            "actual guest reported failure")
    result = []
    for line in serial.splitlines():
        if line.startswith(PREFIX):
            require(len(line) <= 4096, "bounded device record required")
            value = json.loads(line[len(PREFIX):], object_pairs_hook=unique_object)
            require(isinstance(value, dict) and value.get("nonce") == nonce
                    and value.get("mode") == mode, "guest record identity mismatch")
            result.append(value)
    expected = ["ready", "complete"] if complete else ["ready"]
    require([row.get("event") for row in result] == expected, "exact original event order required")
    ready = result[0]
    required = {"nonce", "event", "mode", "input_path", "input_name", "input_major", "input_minor",
                "input_bus", "input_vendor", "input_product", "width", "height", "bpp", "pitch",
                "fb_bytes", "storage_device", "storage_inode", "storage_bytes", "storage_hash", "system"}
    require(set(ready) == required, "device record fields differ")
    require(ready["input_name"] == "QEMU Virtio Keyboard"
            and isinstance(ready["input_path"], str)
            and re.fullmatch(r"/dev/input/event[0-9]+", ready["input_path"]),
            "explicit virtual keyboard not observed")
    require(all(type(ready[key]) is int and ready[key] >= 0 for key in
                ("input_major", "input_minor", "input_bus", "input_vendor", "input_product",
                 "width", "height", "bpp", "pitch", "fb_bytes", "storage_device", "storage_inode", "storage_bytes")),
            "device measurements must be actual nonnegative integers")
    require(ready["input_major"] == 13 and ready["input_bus"] == 6,
            "actual evdev/virtio input identity required")
    require(ready["width"] == FRAME_WIDTH and ready["height"] == FRAME_HEIGHT
            and ready["bpp"] in (16, 24, 32), "explicit framebuffer geometry required")
    require(ready["pitch"] >= FRAME_WIDTH * (ready["bpp"] // 8)
            and FRAME_HEIGHT * ready["pitch"] <= ready["fb_bytes"] <= 16 * 1024 * 1024,
            "framebuffer extent is inconsistent")
    require(ready["storage_inode"] > 0 and ready["storage_device"] > 0
            and ready["storage_bytes"] == 4096 and ready["storage_hash"] == original_hash(nonce),
            "actual storage identity and exact original payload required")
    require(isinstance(ready["system"], str) and 0 < len(ready["system"]) <= 64, "bounded actual uname required")
    if complete:
        require(result[1] == {"nonce": nonce, "event": "complete", "mode": mode,
                              "key_code": 30, "presses": 1, "releases": 1},
                "one exact original key press/release required")
    return result


def framebuffer_pixels(data):
    """Check real QMP P6 bytes against the guest's complete four-band image."""
    require(isinstance(data, bytes) and len(data) <= 4 * 1024 * 1024, "bounded screenshot required")
    # QEMU's P6 encoder has this exact header and no optional PPM comments.
    expected = f"P6\n{FRAME_WIDTH} {FRAME_HEIGHT}\n255\n".encode()
    require(data.startswith(expected), "exact QMP P6 geometry required")
    pixels = data[len(expected):]
    require(len(pixels) == FRAME_WIDTH * FRAME_HEIGHT * 3, "complete framebuffer pixels required")
    # Check each pixel; a readable mapped byte or one painted point is not a frame.
    row = b"".join(bytes(color) * (FRAME_WIDTH // 4) for color in COLORS)
    require(pixels == row * FRAME_HEIGHT, "display did not show the original complete four-band image")
    return {"width": FRAME_WIDTH, "height": FRAME_HEIGHT, "pixels_checked": FRAME_WIDTH * FRAME_HEIGHT,
            "exact_original_colors": True, "model_or_human_visual_review": False}


def retained_boots(first, second):
    keys = ("storage_device", "storage_inode", "storage_bytes", "storage_hash")
    require(first["mode"] == "write" and second["mode"] == "read"
            and first["nonce"] == second["nonce"], "ordered retained-disk boots required")
    require({key: first[key] for key in keys} == {key: second[key] for key in keys},
            "original storage identity or payload changed across reboot")
    return {"original_inode_retained": True, "original_payload_retained": True,
            "second_boot_writes_payload": False, "clean_guest_reboot_only": True,
            "power_loss_qualified": False}
