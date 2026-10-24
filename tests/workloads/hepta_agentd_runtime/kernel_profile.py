"""Ordinary-kernel admission shared by fresh builds and retained evidence."""
import shlex


TRUSTED_INPUTS = (
    "HEPTA_TRUSTED_INITIAL_ELF",
    "HEPTA_G1C_TRUSTED_OBSERVE",
    "HEPTA_G1D_TRUSTED_CONTROL",
    "HEPTA_G2_TRUSTED_DAEMON",
    "g1c-trusted-observe",
    "g1d-trusted-control",
    "g2-trusted-daemon",
)


def require_ordinary_command(raw_command):
    """Decode the original shell transcript, then refuse every trusted role.

    This is a profile boundary, not command execution. Even a disabled trusted
    assignment is outside the original ordinary command transcript. The later
    QueryAbi and source checks remain independently required.
    """
    if not isinstance(raw_command, str) or not raw_command.strip():
        raise ValueError("bounded ordinary build command required")
    if len(raw_command.encode("utf-8")) > 64 * 1024:
        raise ValueError("ordinary build command exceeds evidence bound")
    arguments = shlex.split(raw_command)
    if not arguments or any(marker in argument for argument in arguments for marker in TRUSTED_INPUTS):
        raise ValueError("ordinary build must not select a trusted role or image")
    return arguments
