// Explicit x86_64/i386 ABI fixture, not the actual AOSP generated header.
// The native entries are checked against this host's UAPI in constructor.cc.
#pragma once
inline constexpr long __x86_64_setresuid = 117;
inline constexpr long __x86_64_setresgid = 119;
inline constexpr long __x86_64_setfsuid = 122;
inline constexpr long __x86_64_setfsgid = 123;
inline constexpr long __x86_setresuid = 208;
inline constexpr long __x86_setresgid = 210;
inline constexpr long __x86_setfsuid = 215;
inline constexpr long __x86_setfsgid = 216;
