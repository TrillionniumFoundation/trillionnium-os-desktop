#!/bin/sh
# A03-only host validation; no kernel or durable Hepta claims.
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$repo_root"
output_dir=${1:?usage: sh tests/control/run-validation.sh OUTPUT_DIR}
mkdir -p "$output_dir"
output_dir=$(CDPATH= cd -- "$output_dir" && pwd)
a03_cargo=${A03_CARGO:-cargo}

git rev-parse HEAD > "$output_dir/source-commit.txt"
git diff -- libs/os-control tests/control > "$output_dir/source-diff.patch"
rustc -vV > "$output_dir/rustc.txt"
uname -srm > "$output_dir/host.txt"

run_check() {
    check_name=$1
    shift
    if "$@" > "$output_dir/$check_name.log" 2>&1; then
        cat "$output_dir/$check_name.log"
    else
        check_status=$?
        cat "$output_dir/$check_name.log"
        return "$check_status"
    fi
}

run_check fmt "$a03_cargo" fmt --manifest-path libs/os-control/Cargo.toml --all -- --check
run_check std-tests "$a03_cargo" test --locked --manifest-path libs/os-control/Cargo.toml
run_check std-clippy "$a03_cargo" clippy --locked --manifest-path libs/os-control/Cargo.toml --all-targets -- -D warnings
run_check spin-tests "$a03_cargo" test --locked --manifest-path libs/os-control/Cargo.toml --no-default-features --features portable-spin
run_check spin-clippy "$a03_cargo" clippy --locked --manifest-path libs/os-control/Cargo.toml --no-default-features --features portable-spin --all-targets -- -D warnings
run_check no-std-target "$a03_cargo" check --locked --manifest-path libs/os-control/Cargo.toml --no-default-features --features portable-spin --lib --target x86_64-unknown-none
run_check no-std-build "$a03_cargo" build --locked --manifest-path libs/os-control/Cargo.toml --no-default-features --features portable-spin --lib --target x86_64-unknown-none
run_check custom-no-std-fmt "$a03_cargo" fmt --manifest-path tests/control/backend_no_std/Cargo.toml -- --check
run_check custom-no-std-build "$a03_cargo" build --locked --manifest-path tests/control/backend_no_std/Cargo.toml --lib --target x86_64-unknown-none
run_check custom-no-std-clippy "$a03_cargo" clippy --locked --manifest-path tests/control/backend_no_std/Cargo.toml --lib --target x86_64-unknown-none -- -D warnings
run_check api-compatibility python3 tests/control/api_compat/run-checks.py "$output_dir/api-compatibility"
run_check bounded-models env CARGO="$a03_cargo" python3 tests/control/loom/run-models.py "$output_dir/loom"
run_check lock-allocation env CARGO="$a03_cargo" python3 tests/control/lock_alloc/run-checks.py "$output_dir/lock-allocation"
