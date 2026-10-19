#!/usr/bin/env python3
"""Freeze a small, byte-bound publication selection without the official ZIP."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import lzma
import re

ROOT = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads((ROOT / path).read_text())


def api(path):
    result = read_json(path)
    return json.loads(result['result']['structuredContent']['content']), result


def save(path, value):
    target = ROOT / path
    assert not target.exists(), path
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    target.write_bytes(raw)
    return raw


def main():
    green = read_json('green-independent-review/review.json')
    negative = read_json('negative-independent-review/review.json')
    checks, checks_envelope = api('api/final-head-checks-completed.json')
    run, run_envelope = api('api/final-a06-run-completed.json')
    jobs, jobs_envelope = api('api/final-a06-jobs-completed.json')
    artifacts, artifacts_envelope = api('api/final-a06-artifacts-completed.json')
    pr, pr_envelope = api('api/final-pr205-completed.json')
    head, tree = green['head'], green['tree']
    assert green['passed'] and negative['passed'] and (negative['head'], negative['tree']) == (head, tree)
    assert pr['head']['sha'] == head and run['head_sha'] == head and run['conclusion'] == 'success'
    assert len(checks['check_runs']) == 5 and all(c['head_sha'] == head and c['status'] == 'completed' and c['conclusion'] == 'success' for c in checks['check_runs'])
    assert len(jobs['jobs']) == 1
    job = jobs['jobs'][0]
    assert job['id'] == 118020615962 and job['head_sha'] == head and job['conclusion'] == 'success'
    assert all(s['status'] == 'completed' and s['conclusion'] == 'success' for s in job['steps'])
    assert len(artifacts['artifacts']) == 1
    artifact = artifacts['artifacts'][0]
    assert artifact['id'] == 12182038203 and artifact['workflow_run']['head_sha'] == head
    assert artifact['digest'] == 'sha256:' + green['archive']['sha256'] and artifact['size_in_bytes'] == green['archive']['bytes']
    first = read_json('api/first-g0-failure-log.json')
    first_log = first['result']['structuredContent']['content']
    assert 'Ran 36 tests' in first_log and 'FAILED (failures=1)' in first_log
    assert 'test_process_death_path_charges_thread_owned_snapshot' in first_log
    assert "owner.charge(self.bandwidth_accounted_through, now)" in first_log
    summary = {
        'schema': 1, 'frozen_at_utc': datetime.now(timezone.utc).isoformat(),
        'kind': 'Independent review of official #205 final A06 artifact; source and runtime receipts, not a new product execution.',
        'repository': 'TrillionniumFoundation/trillionnium-os-desktop', 'pr': 205,
        'head': head, 'tree': tree,
        'official_artifact': {'id': artifact['id'], 'name': artifact['name'], 'bytes': artifact['size_in_bytes'], 'sha256': green['archive']['sha256'],
                              'created_at': artifact['created_at'], 'expires_at': artifact['expires_at'],
                              'safe_api_url': artifact['url'], 'safe_download_endpoint': artifact['archive_download_url'],
                              'run_id': run['id'], 'run_url': run['html_url'], 'job_id': job['id'], 'job_url': job['html_url']},
        'recorded_final_ci': {'observation_started_at': min(e['request_started_at'] for e in [checks_envelope, run_envelope, jobs_envelope, artifacts_envelope, pr_envelope]),
                              'observation_finished_at': max(e['request_finished_at'] for e in [checks_envelope, run_envelope, jobs_envelope, artifacts_envelope, pr_envelope]),
                              'run_started_at': run['run_started_at'], 'job_started_at': job['started_at'], 'job_completed_at': job['completed_at'],
                              'job_step_count': len(job['steps']), 'all_job_steps_success': True,
                              'checks': [{'id': c['id'], 'name': c['name'], 'status': c['status'], 'conclusion': c['conclusion'], 'completed_at': c['completed_at']} for c in checks['check_runs']],
                              'pr_state_at_this_observation': pr['state'], 'pr_draft_at_this_observation': pr['draft'], 'pr_merged_at_this_observation': pr['merged'], 'mergeable_state_at_this_observation': pr['mergeable_state'],
                              'merging_or_later_pr_status_not_performed_or_inferred': True},
        'verified': {'source_file_count': 7054, 'all_git_blob_mode_sha256_size_equal_final_head': True,
                     'full_source_tree_independently_recomputed': tree, 'before_after_candidate_source_equal': True,
                     'core': {'reported_passed': 220, 'failed': 0, 'filtered': 0, 'soft_skipped': 0},
                     'ostd': {'reported_passed': 221, 'failed': 0, 'filtered': 0, 'soft_skipped': 3, 'soft_skip_tests': green['crates'][1]['soft_skip_tests']},
                     'reported_passed': 441, 'exercised_passed_lower_bound': 438,
                     'new_usage_tests': 19, 'complete_green_names_equal_old_201_union_new_19': True,
                     'negative_controls': [{'name': c['control'], 'complete_suite': c['complete_tests'], 'passed': c['passed'], 'failed': c['failed'], 'exact_failed_names': c['expected_exact_failed_names'], 'single_mutated_path': c['only_changed_path'], 'negative_tree': c['negative_tree_independently_recomputed']} for c in negative['controls']],
                     'green_ordinary_ostd_elf_members': green['kernels_independently_stream_hashed'],
                     'negative_elf_members': len(negative['retained_elf_members_independently_stream_hashed']),
                     'ordinary_queryabi': green['product_queryabi'], 'archive_members': 1172, 'all_archive_crc_validated': True},
        'preserved_prior_failure': {'head': 'f9669912e2886190429187e14753d62b2060bd5f', 'job_id': 118018209972,
                                   'observed_raw_result': '36 host spec tests; one stale source-string assertion failed.',
                                   'test_name': 'test_process_death_path_charges_thread_owned_snapshot',
                                   'source_path': 'tests/spec/test_a06_final_accounting_source.py',
                                   'old_expected_call': 'owner.charge(self.bandwidth_accounted_through, now)', 'new_typed_call': 'owner.charge(from_ns, until_ns)',
                                   'final_head_change': 'Only that host source guard changed from f966 to 4d; final 4d owns its own successful CI.',
                                   'original_tool_response': 'api/first-g0-failure-log.json'},
        'qualification_boundaries': [
            'The ordinary full32/SCM27/NOFILE37/CPU metrics are assigned to a separate independent reviewer; this report does not decide those semantic results.',
            'The 19 kernel tests use actual kernel implementations and explicitly scoped fixtures. They do not establish live physical cross-CPU scheduler migration or Hepta authorization.',
            'The three OSTD VMX soft skips remain excluded from the exercised lower bound. Seven repeated negative runs are not counted as extra unique green tests.',
            'QueryAbi retains all four disabled operations and native grants/effects/Hepta durability remain false.',
            'No A10, original Objective/Operations owner, G1-c/d, ARM/mobile device, Debian13 or original Asterinas W1 qualification is created by this evidence.',
            'Source snapshots, fixed build inputs and raw runtime records bind this CI execution. A separate bit-for-bit reproducible build was not attempted.',
        ],
        'read_only_review_passed': True,
        'transport_exclusions': ['original.zip', '*.partial', 'api/download-reference-redacted.json', 'download-artifact.py', '/tmp/r11-pr205-artifact-private-download.json', 'temporary signed download URL', 'download file_uri/file_id', 'any downloaded ELF/executable'],
    }
    save('SUMMARY.json', summary)
    readme = '''# PR #205 最终 A06 产物独立复核

本包核对官方 GitHub Actions 已产生的原始字节，没有重新构建内核、启动 QEMU、重跑测试或改变门禁。源提交是 `4d3011cf9f92e25fc1b0d7371e9cdbbd5a8b7930`，树是 `8eb809136a402cc54ba049b1e40dd174308c923f`。

## 已证实的结果

完整绿色套件为 **aster-core 220 项通过、OSTD 221 项报告通过**。OSTD 保留 3 项 VMX 条件不可用的软跳过，因此合计报告数为 441，**实际执行下界为 438**。新增 19 项 usage 测试全部出现一次并通过；绿色测试名集合严格等于 #203 的原 201 项加这 19 项，未删原测试。原始串口中的测试开始、唯一终态、汇总、零过滤与 QEMU 退出 33 均已独立读取。

7054 个源文件逐项核对路径、模式、Git blob、大小和 SHA256，并独立重新计算 Git tree；普通启动前、启动后、guest 后及七次负控前后的候选快照一致。七个负控各运行完整 220 项，精确失败数为 **3 / 4 / 3 / 1 / 4 / 1 / 2**，每项失败名字均与固定源码中的预期相同，没有额外失败、跳过或过滤。每个负控仅改变声明的一个生产文件。声明 patch 与产物中的实际 applied diff 均只应用到临时文本副本，所得 blob、大小、SHA256 与负控快照一致；七个负控 tree 也重新计算相符。

绿色 core、OSTD、ordinary 的 3 个内核 ELF 与七组保留的绿色/负控共 14 个 ELF 均经过流式字节哈希。负控保留原 QEMU 65 与原 gate 1，没有超时。ordinary QueryAbi 的 14 个记录标记和四个 disabled 操作均与原始 serial 一致。未执行任何产物中的代码或 ELF。

## 官方执行与原始失败

2026-10-19 **11:17:31 UTC** 的精确读取显示最终 4d 的五项检查全部成功；A06 run `39240728276`、job `118020615962` 于 **10:53:58—11:13:24 UTC** 执行，23 个记录步骤全部成功。当时 PR 已 Ready、open、未合并且 mergeable_state 为 clean；这只是有时间界限的快照，不冒称之后的合并状态。

唯一官方 artifact 为 `12182038203`，**154,979,607 字节**，SHA256：

`ef5d93159c1663fb30d3cf8e39e969525bbfa03b4fedc4db10ef4c87b035d655`

ZIP 的 1172 个成员无重复或不安全路径，CRC 全部通过。原 ZIP 不进入本次 Git 交付；精简选集保留可复核的原始 JSON/serial/patch 无损压缩字节及源、ELF、成员身份。

首个 f966 提交的 G0 失败仍保留：原日志为 36 项 host spec 测试、1 项旧 source-string 断言失败。该断言仍要求旧调用，而新 typed ns 路径调用 `owner.charge(from_ns, until_ns)`。最终 4d 相对 f966 只调整该 host source guard，生产、工作流与七个 patch 没有改变，最终成功来自 4d 自己的新执行。

## 范围与入口

本包不替代另一位审查者对 full32 / SCM27 / NOFILE37 / CPU 数值与阈值的独立语义报告。内核 fixture 的通过也不扩大为真实跨 CPU 物理调度、A10、原 Objective/Operations owner、G1-c/d、ARM/移动设备或原始 Asterinas W1 资格。QueryAbi 中 native grants、native resource effects 与 Hepta durability 仍为 false。

`SUMMARY.json` 是简明机器摘要；`green-independent-review/review.json` 与 `negative-independent-review/review.json` 给出完整复核方法、失败集合与边界。`publication-selection.json` 列出允许复制的文件，`files-manifest.json` 对每份成员绑定大小与 SHA256。`publication-raw/` 是原件的无损 XZ 副本，内部身份和上游源字节均可复核。临时签名下载 URL、file_uri/file_id、下载配置、ZIP/partial 和 ELF 均排除。
'''
    assert not (ROOT / 'README.md').exists()
    (ROOT / 'README.md').write_text(readme)

    selected = []
    raw_bindings = []
    def add(path, role):
        file = ROOT / path
        raw = file.read_bytes()
        assert not re.search(rb'"file_uri"\s*:', raw)
        assert not re.search(rb'https?[^\s"<>]+[?&](?:sig|se|sv|sp|sr)=', raw)
        selected.append({'path': path, 'bytes': len(raw), 'sha256': sha(raw), 'role': role})

    def compress(path, role):
        raw = (ROOT / path).read_bytes()
        compressed = lzma.compress(raw, preset=6)
        assert lzma.decompress(compressed) == raw
        target = Path('publication-raw') / (path + '.xz')
        out = ROOT / target
        out.parent.mkdir(parents=True, exist_ok=True)
        assert not out.exists()
        out.write_bytes(compressed)
        raw_bindings.append({'published_path': str(target), 'original_path': path, 'original_bytes': len(raw), 'original_sha256': sha(raw)})
        add(str(target), role)

    for path in ['README.md', 'SUMMARY.json', 'download-receipt.json', 'download-receipt-sandbox-failure.json',
                 'prepare-source.py', 'review-green-archive.py', 'review-negative-archive.py', 'freeze-review.py',
                 'green-independent-review/review.json', 'green-independent-review/manifest.json',
                 'negative-independent-review/review.json', 'negative-independent-review/manifest.json']:
        add(path, 'Readable review, source preparation or bounded validation receipt')
    for path in ['source-git-map.json', 'negative-independent-review/archive-member-index.json']:
        compress(path, 'Lossless original source/ZIP member identity map')
    for parent in ['api', 'g0-first']:
        for file in sorted((ROOT / parent).rglob('*')):
            if file.is_file() and file.name != 'download-reference-redacted.json':
                compress(str(file.relative_to(ROOT)), 'Lossless original API, failure or local fixed-host receipt; timestamps and source scopes preserved')
    for parent in ['green-independent-review/selected', 'negative-independent-review/selected', 'fixed-source']:
        for file in sorted((ROOT / parent).rglob('*')):
            if file.is_file():
                add(str(file.relative_to(ROOT)), 'Original artifact selected raw member compressed losslessly' if '/selected' in parent else 'Exact reviewed source from immutable final Git blob')
    assert len(selected) == len({row['path'] for row in selected})
    save('publication-selection.json', {'schema': 1, 'scope': 'Small explicit list only; no ZIP/ELF/download token/partial/cache.',
                                      'artifact_id': 12182038203, 'artifact_sha256': summary['official_artifact']['sha256'],
                                      'head': head, 'tree': tree, 'selection': selected,
                                      'selected_count': len(selected), 'selected_bytes': sum(row['bytes'] for row in selected),
                                      'lossless_original_bindings': raw_bindings, 'excluded': summary['transport_exclusions'],
                                      'copy_this_selection_file_and_files_manifest_in_addition': True})
    add('publication-selection.json', 'Exact publication allowlist and original compressed-file bindings')
    manifest = {'schema': 1, 'frozen_at_utc': datetime.now(timezone.utc).isoformat(), 'root': str(ROOT),
                'head': head, 'tree': tree, 'files': selected, 'file_count': len(selected),
                'total_bytes': sum(row['bytes'] for row in selected), 'manifest_excludes_itself': True,
                'must_copy_files_manifest_itself_in_addition': True, 'no_temporary_signed_url_or_file_uri': True,
                'zip_and_elf_bytes_excluded': True, 'archive_sha256': summary['official_artifact']['sha256']}
    manifest_raw = save('files-manifest.json', manifest)
    print(json.dumps({'producer': str(ROOT), 'selected_files_including_manifest': len(selected) + 1,
                      'selected_bytes_including_manifest': manifest['total_bytes'] + len(manifest_raw),
                      'manifest_bytes': len(manifest_raw), 'manifest_sha256': sha(manifest_raw)}))


if __name__ == '__main__':
    main()
