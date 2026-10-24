"""Lossless pixels and a focus target on the caller-owned private X11 display."""
import ctypes as C
import hashlib
import os
from pathlib import Path
import struct
import zlib


class XImage(C.Structure):
    _fields_ = [(name, C.c_int) for name in ("width", "height", "xoffset", "format")] + [
        ("data", C.c_void_p)] + [(name, C.c_int) for name in (
            "byte_order", "bitmap_unit", "bitmap_bit_order", "bitmap_pad", "depth",
            "bytes_per_line", "bits_per_pixel")] + [
        (name, C.c_ulong) for name in ("red_mask", "green_mask", "blue_mask")]


class Display:
    def __init__(self):
        self.lib = C.CDLL("libX11.so.6")
        definitions = {
            "XOpenDisplay": ([C.c_char_p], C.c_void_p),
            "XDefaultRootWindow": ([C.c_void_p], C.c_ulong),
            "XCloseDisplay": ([C.c_void_p], C.c_int),
            "XGetGeometry": ([C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong),
                C.POINTER(C.c_int), C.POINTER(C.c_int), C.POINTER(C.c_uint),
                C.POINTER(C.c_uint), C.POINTER(C.c_uint), C.POINTER(C.c_uint)], C.c_int),
            "XGetImage": ([C.c_void_p, C.c_ulong, C.c_int, C.c_int, C.c_uint,
                C.c_uint, C.c_ulong, C.c_int], C.POINTER(XImage)),
            "XDestroyImage": ([C.POINTER(XImage)], C.c_int),
            "XCreateSimpleWindow": ([C.c_void_p, C.c_ulong, C.c_int, C.c_int,
                C.c_uint, C.c_uint, C.c_uint, C.c_ulong, C.c_ulong], C.c_ulong),
            "XMapWindow": ([C.c_void_p, C.c_ulong], C.c_int),
            "XStoreName": ([C.c_void_p, C.c_ulong, C.c_char_p], C.c_int),
            "XDestroyWindow": ([C.c_void_p, C.c_ulong], C.c_int),
            "XSync": ([C.c_void_p, C.c_int], C.c_int),
        }
        for name, (arguments, result) in definitions.items():
            getattr(self.lib, name).argtypes = arguments
            getattr(self.lib, name).restype = result
        self.handle = self.lib.XOpenDisplay(os.environ["DISPLAY"].encode())
        if not self.handle:
            raise RuntimeError("Cannot open the private X11 display")
        self.root = self.lib.XDefaultRootWindow(self.handle)
        self.focus_target = None

    def focus_window(self):
        if self.focus_target is None:
            self.focus_target = self.lib.XCreateSimpleWindow(self.handle, self.root,
                1350, 10, 70, 50, 0, 0, 0x334455)
            self.lib.XStoreName(self.handle, self.focus_target, b"Owned native UI focus probe")
            self.lib.XMapWindow(self.handle, self.focus_target)
            self.lib.XSync(self.handle, 0)
        return self.focus_target

    def screenshot(self, destination, window=None):
        window = self.root if window is None else window
        root = C.c_ulong()
        x, y = C.c_int(), C.c_int()
        width, height, border, depth = C.c_uint(), C.c_uint(), C.c_uint(), C.c_uint()
        if not self.lib.XGetGeometry(self.handle, window, C.byref(root), C.byref(x), C.byref(y),
                C.byref(width), C.byref(height), C.byref(border), C.byref(depth)):
            raise RuntimeError("Cannot obtain owned window geometry")
        if not (0 < width.value <= 4096 and 0 < height.value <= 4096):
            raise RuntimeError("Unexpected capture dimensions")
        image = self.lib.XGetImage(self.handle, window, 0, 0, width, height, C.c_ulong(-1).value, 2)
        if not image:
            raise RuntimeError("XGetImage did not return actual pixels")
        try:
            value = image.contents
            if (value.bits_per_pixel, value.byte_order, value.red_mask, value.green_mask, value.blue_mask) != (32, 0, 0xff0000, 0xff00, 0xff):
                raise RuntimeError("Unsupported private framebuffer pixel format")
            raw = C.string_at(value.data, value.bytes_per_line * value.height)
            rows = []
            for row_index in range(value.height):
                row = raw[row_index * value.bytes_per_line:row_index * value.bytes_per_line + value.width * 4]
                rgb = bytearray(value.width * 3)
                rgb[0::3], rgb[1::3], rgb[2::3] = row[2::4], row[1::4], row[0::4]
                rows.append(b"\0" + rgb)
        finally:
            self.lib.XDestroyImage(image)
        def chunk(kind, body):
            return struct.pack("!I", len(body)) + kind + body + struct.pack("!I", zlib.crc32(kind + body) & 0xffffffff)
        png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!2I5B", width.value, height.value, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))
        Path(destination).write_bytes(png)
        return {"file": Path(destination).name, "window": window, "width": width.value,
                "height": height.value, "bytes": len(png), "sha256": hashlib.sha256(png).hexdigest(),
                "capture": "XGetImage actual private X11 framebuffer", "human_visual_review_required": True}

    def close(self):
        if self.handle:
            if self.focus_target is not None:
                self.lib.XDestroyWindow(self.handle, self.focus_target)
            self.lib.XCloseDisplay(self.handle)
            self.handle = None
