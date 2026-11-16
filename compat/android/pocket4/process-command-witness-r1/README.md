# Owned process command witnesses

An actual Linux build observation captured an empty command line during the
`exec` window. A later observation had the correct complete command, with the
same PID, start ticks, executable path and cgroup. Comparing the entire two
dictionaries rejected that unchanged process.

`validate_executed_command` separates generation equality from exact current
command validation. An initial empty argument list is retained as observed;
every current argument, including order and count, must equal the frozen
request. PID and start ticks reject booleans and floats. The executable path
and cgroup remain part of the generation check.

`PinnedExecutable` independently hashes and holds the named executable with
`O_NOFOLLOW`, then verifies the actual running executable at both observation
boundaries against its device, inode and complete metadata. It retains both
descriptors until the observation finishes and rejects replaced or changed
bytes. The caller must keep the owned child PIDFD open for the whole window,
and perform command and executable checks before and after reading inputs.

Run `python3 -m unittest -v test_process_command_witness.py`. Nine tests are
portable POSIX controls, including the original failing dictionary comparison,
wrong generation, wrong actual argv, strict types, changed pins and replaced
files. The tenth uses a real running Linux executable and is explicitly skipped
where numeric `/proc/<pid>/exe` reads are unavailable. Release validation must
run all ten on the actual Linux host. No host, device, job or private source
identities are included in these fixtures.
