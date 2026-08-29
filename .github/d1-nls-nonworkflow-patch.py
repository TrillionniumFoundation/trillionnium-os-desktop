from pathlib import Path
import json


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"{path}: expected exactly one replacement target, found {count}: {old!r}"
        )
    path.write_text(text.replace(old, new), encoding="utf-8")


manifest_path = Path("manifests/e2fsprogs-host-toolchain.v1.json")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
if manifest["build"]["configure_flags"] != ["--disable-nls"]:
    raise SystemExit("unexpected prior e2fsprogs configure contract")
manifest["build"]["configure_flags"] = ["--enable-nls"]
manifest["build"]["runtime_locale"] = "C.UTF-8"
manifest["build"]["utf8_tar_import_probe_required"] = True
manifest_path.write_text(
    json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
    encoding="utf-8",
)

helper = Path("tools/build_pinned_e2fsprogs.sh")
replace_once(
    helper,
    "for command in git jq make sha256sum gcc; do\n",
    "for command in git jq make sha256sum gcc msgfmt locale tar truncate python3; do\n",
)
replace_once(
    helper,
    """tag_object=$(jq -er '.tag_object' "$manifest")
if ! [[ "$commit" =~ ^[0-9a-f]{40}$ && "$tag_object" =~ ^[0-9a-f]{40}$ ]]; then
""",
    """tag_object=$(jq -er '.tag_object' "$manifest")
runtime_locale=$(jq -er '.build.runtime_locale' "$manifest")
mapfile -t configure_flags < <(jq -er '.build.configure_flags[]' "$manifest")
if (( ${#configure_flags[@]} != 1 )) || [[ ${configure_flags[0]} != --enable-nls ]]; then
  echo "pinned e2fsprogs must use the reviewed --enable-nls build contract" >&2
  exit 1
fi
if [[ $(LC_ALL="$runtime_locale" LANG="$runtime_locale" locale charmap) != UTF-8 ]]; then
  echo "pinned e2fsprogs runtime locale is not UTF-8: $runtime_locale" >&2
  exit 1
fi
if ! [[ "$commit" =~ ^[0-9a-f]{40}$ && "$tag_object" =~ ^[0-9a-f]{40}$ ]]; then
""",
)
replace_once(
    helper,
    'stamp="$work_dir/PASS"\n\nvalid_existing=false\n',
    'stamp="$work_dir/PASS"\n'
    'build_fingerprint="$commit:${configure_flags[*]}:$runtime_locale"\n\n'
    'valid_existing=false\n',
)
replace_once(
    helper,
    '  if [[ "$installed_version" == "$version" && "$(cat "$stamp")" == "$commit" ]]; then\n',
    '  if [[ "$installed_version" == "$version" && "$(cat "$stamp")" == "$build_fingerprint" ]]; then\n',
)
replace_once(
    helper,
    """      --prefix="$prefix" \\
      --disable-nls
""",
    """      --prefix="$prefix" \\
      "${configure_flags[@]}"
""",
)
replace_once(
    helper,
    """  printf '%s\\n' "$commit" > "$stamp"
fi

compiler=$(gcc --version | head -n1)
""",
    """  printf '%s\\n' "$build_fingerprint" > "$stamp"
fi

probe="$work_dir/utf8-probe"
rm -rf "$probe"
mkdir -p "$probe/root"
printf 'utf8-path-probe\\n' > "$probe/root/路径.txt"
LC_ALL=C tar \\
  --sort=name \\
  --format=pax \\
  --pax-option=delete=atime,delete=ctime,exthdr.name=%d/PaxHeaders/%f \\
  --numeric-owner \\
  --mtime='@1700000000' \\
  -C "$probe/root" \\
  -cf "$probe/rootfs.tar" .
truncate -s 64M "$probe/probe.ext4"
probe_uuid=7f453284-a1e5-4f17-9c30-7c5bde91ffff
E2FSPROGS_FAKE_TIME=1700000000 \\
  LC_ALL="$runtime_locale" LANG="$runtime_locale" \\
  "$bin_dir/mke2fs" \\
  -F -q -t ext4 -b 4096 -I 256 -m 0 \\
  -L TOSD1PROBE -U "$probe_uuid" \\
  -E "root_owner=0:0,lazy_itable_init=0,lazy_journal_init=0,hash_seed=$probe_uuid" \\
  -d "$probe/rootfs.tar" \\
  "$probe/probe.ext4"
"$bin_dir/e2fsck" -fn "$probe/probe.ext4" >/dev/null
probe_image_sha256=$(sha256sum "$probe/probe.ext4" | awk '{print $1}')
rm -rf "$probe"

compiler=$(gcc --version | head -n1)
""",
)
replace_once(
    helper,
    """  "$compiler" "$make_version" "$git_version" "$bin_dir" <<'PY'
""",
    """  "$compiler" "$make_version" "$git_version" "$bin_dir" \\
  "${configure_flags[*]}" "$runtime_locale" "$probe_image_sha256" <<'PY'
""",
)
replace_once(
    helper,
    """    git_version,
    bin_dir,
) = sys.argv[1:]
""",
    """    git_version,
    bin_dir,
    configure_flag,
    runtime_locale,
    probe_image_sha256,
) = sys.argv[1:]
""",
)
replace_once(
    helper,
    """    "version": version,
    "compiler": compiler,
""",
    """    "version": version,
    "configure_flags": [configure_flag],
    "runtime_locale": runtime_locale,
    "utf8_tar_import_probe": {
        "status": "PASS",
        "image_sha256": probe_image_sha256,
    },
    "source_patch_count": 0,
    "compiler": compiler,
""",
)

test_path = Path("tests/d1/test_d1_tool_binding.py")
replace_once(
    test_path,
    "from pathlib import Path\nimport unittest\n",
    "import json\nfrom pathlib import Path\nimport unittest\n",
)
replace_once(
    test_path,
    "class D1FilesystemToolBindingTests(unittest.TestCase):\n",
    """class D1FilesystemToolBindingTests(unittest.TestCase):
    def test_exact_e2fsprogs_build_initializes_utf8_ctype_before_tar_import(self) -> None:
        manifest = json.loads(
            (REPOSITORY_ROOT / "manifests/e2fsprogs-host-toolchain.v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["build"]["configure_flags"], ["--enable-nls"])
        self.assertEqual(manifest["build"]["runtime_locale"], "C.UTF-8")
        self.assertTrue(manifest["build"]["utf8_tar_import_probe_required"])

        workflow = (
            REPOSITORY_ROOT / ".github/workflows/d1-final-qualification.yml"
        ).read_text(encoding="utf-8")
        helper = (REPOSITORY_ROOT / "tools/build_pinned_e2fsprogs.sh").read_text(
            encoding="utf-8"
        )
        for source in (workflow, helper):
            self.assertIn("--enable-nls", source)
            self.assertNotIn("--disable-nls", source)
            self.assertIn("路径.txt", source)
        self.assertIn("gettext", workflow)
        self.assertIn("e2fsprogs-utf8-probe.json", workflow)
        self.assertIn("LC_ALL=C.UTF-8 LANG=C.UTF-8", workflow)
        self.assertIn("build_fingerprint", helper)
        self.assertIn("msgfmt", helper)
        self.assertIn("runtime_locale", helper)

""",
)
