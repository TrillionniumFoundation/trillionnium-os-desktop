#!/usr/bin/env node
// Reconstruct the exact reviewed input packet from the already published Git blobs.
// Never starts Android, changes a selector, or reads user data.
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { closeSync, fsyncSync, openSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

export const COMMIT = '1af163b21f5c7dcaaf94084d7cc1ef19aed05ae1';
export const PACKAGE = 'compat/android/pocket4/current-app-acceptance/system-cp3a-provider-rebind-20261120';
export const ORIGINAL = 'compat/android/pocket4/current-app-acceptance/system-cp3a-source-adapter-20261119/ORIGINAL-SOURCE-MANIFEST.json';
const ORIGINAL_SHA = 'dfe01692552abdb112575362e9ab80fb5b9782f1e7a878035b152198a2bec53d';
const INPUT_SHA = 'c38a0ef25c51497f2056169ca130d3ff6e13fa710d3159444604341af33c4b25';
const INPUT_BYTES = 454653;

function requireValue(value, message) {
  if (!value) throw new Error(message);
}
function sha256(raw) { return createHash('sha256').update(raw).digest('hex'); }

export function reconstruct(originalRaw, sourceFiles) {
  requireValue(Buffer.isBuffer(originalRaw) && sha256(originalRaw) === ORIGINAL_SHA,
    'Exact published original source manifest required');
  requireValue(sourceFiles.length === 26, 'Exactly 24 postimages plus two metadata files required');
  const files = [...sourceFiles].sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0)
    .map(({ path, raw, git_blob }) => {
      requireValue(path === 'prepared/SOURCE-CONTRACT.json' || path === 'prepared/TRANSFORM.json'
        || /^prepared\/postimages\/[a-z0-9.-]+\/[a-z0-9_]+\.py$/.test(path), 'Unexpected source path');
      requireValue(Buffer.isBuffer(raw), 'Whole source blob bytes required');
      const digest = createHash('sha1').update(Buffer.from(`blob ${raw.length}\0`)).update(raw).digest('hex');
      requireValue(digest === git_blob, 'Published Git blob changed');
      const text = raw.toString('utf8');
      requireValue(Buffer.from(text, 'utf8').equals(raw), 'Exact UTF-8 source representation required');
      return { path, git_blob, bytes: raw.length, text };
    });
  requireValue(new Set(files.map(f => f.path)).size === 26, 'Duplicate input path');
  // Match the recorded JavaScript JSON representation, including its historical
  // numeric metadata representation. Raw files themselves are verified by SHA256.
  const packet = { repository: 'TrillionniumFoundation/trillionnium-os-desktop', commit: COMMIT,
    original_manifest: JSON.parse(originalRaw.toString('utf8')), files };
  const encoded = Buffer.from(JSON.stringify(packet), 'utf8');
  requireValue(encoded.length === INPUT_BYTES && sha256(encoded) === INPUT_SHA,
    'Reconstructed input packet differs from the exact reviewed packet');
  return encoded;
}

function main() {
  const [repo, output] = process.argv.slice(2);
  requireValue(repo && output && process.argv.length === 4,
    'Usage: node reconstruct_inputs.mjs /path/to/repository /absolute/new/reviewed-inputs.json');
  requireValue(output.startsWith('/'), 'Absolute create-only output path required');
  function git(args) { return execFileSync('git', ['-C', repo, ...args], { maxBuffer: 2 * 1024 * 1024 }); }
  requireValue(git(['rev-parse', `${COMMIT}^{commit}`]).toString().trim() === COMMIT, 'Pinned source commit missing');
  const prefix = `${PACKAGE}/`;
  const paths = git(['ls-tree', '-r', '--name-only', COMMIT, '--', `${PACKAGE}/prepared`])
    .toString('utf8').trim().split('\n').filter(path => path === `${prefix}prepared/SOURCE-CONTRACT.json`
      || path === `${prefix}prepared/TRANSFORM.json` || path.startsWith(`${prefix}prepared/postimages/`));
  const sourceFiles = paths.map(path => ({ path: path.slice(prefix.length),
    raw: git(['show', `${COMMIT}:${path}`]), git_blob: git(['rev-parse', `${COMMIT}:${path}`]).toString().trim() }));
  const encoded = reconstruct(git(['show', `${COMMIT}:${ORIGINAL}`]), sourceFiles);
  const fd = openSync(output, 'wx', 0o600);
  try { writeFileSync(fd, encoded); fsyncSync(fd); } finally { closeSync(fd); }
  process.stdout.write(JSON.stringify({ path: output, bytes: encoded.length, sha256: sha256(encoded), source_only: true }) + '\n');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
