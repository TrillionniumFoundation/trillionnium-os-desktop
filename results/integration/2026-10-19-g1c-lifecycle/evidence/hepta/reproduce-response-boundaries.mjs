// Diagnostic only: real HTTP and exact pinned SDK methods, synthetic WASM sink.
// This does not execute or qualify the Rust UI, Rust gateway, or product gate.
import { chromium } from '../r12-hepta-fix/apps/hepta-control-ui/node_modules/playwright/index.mjs';
import { createServer } from 'node:http';
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';

const script = await readFile(new URL('./pinned-network-methods.js', import.meta.url));
const limit = 262144;
const body = Buffer.from('{"product":"hepta","status":"unavailable","error":"legacy runtime unavailable"}');
const serverRecords = [];
const server = createServer((request, response) => {
  const pathname = new URL(request.url, 'http://local').pathname;
  const name = pathname.split('/').at(-1);
  const isControl = pathname.startsWith('/control/');
  const record = { pathname, status: isControl ? 503 : 200, written: 0, finished: false, closed: false };
  serverRecords.push(record);
  let timer;
  response.once('finish', () => { record.finished = true; });
  response.once('close', () => { record.closed = true; clearTimeout(timer); });
  const write = value => { record.written += value.length; response.write(value); };
  const end = value => { record.written += value.length; response.end(value); };
  const headers = {
    'Content-Type': pathname === '/sdk.js' ? 'text/javascript' : isControl ? 'application/json; charset=utf-8' : 'text/html',
    'Cache-Control': 'no-store',
    'Connection': 'close',
    'X-Content-Type-Options': 'nosniff',
  };
  if (!isControl) {
    const value = pathname === '/sdk.js' ? script : Buffer.from('<!doctype html><script src="/sdk.js"></script>');
    response.writeHead(200, { ...headers, 'Content-Length': value.length });
    end(value);
  } else if (name === 'declared-over-limit') {
    response.writeHead(503, { ...headers, 'Content-Length': limit + 1 });
    response.flushHeaders();
    timer = setTimeout(() => end(Buffer.alloc(limit + 1, 0x61)), 100);
  } else if (name === 'streamed-over-limit') {
    response.writeHead(503, headers);
    write(Buffer.alloc(limit / 2, 0x61));
    timer = setTimeout(() => end(Buffer.alloc(limit / 2 + 1, 0x62)), 30);
  } else if (name === 'truncated') {
    response.writeHead(503, { ...headers, 'Content-Length': body.length + 1 });
    write(body.subarray(0, 6));
    timer = setTimeout(() => end(body.subarray(6)), 30);
  } else if (name === 'explicit-abort') {
    response.writeHead(503, { ...headers, 'Content-Length': body.length });
    write(body.subarray(0, 6));
    timer = setTimeout(() => end(body.subarray(6)), 500);
  } else if (name === 'complete-split') {
    response.writeHead(503, { ...headers, 'Content-Length': body.length });
    write(body.subarray(0, 6));
    timer = setTimeout(() => end(body.subarray(6)), 30);
  } else {
    response.writeHead(503, { ...headers, 'Content-Length': body.length });
    end(body);
  }
});

const within = async (promise, milliseconds) => {
  let timer;
  try {
    return await Promise.race([
      promise.then(value => ({ settled: true, value }), error => ({ settled: true, error: String(error) })),
      new Promise(resolve => { timer = setTimeout(() => resolve({ settled: false }), milliseconds); }),
    ]);
  } finally {
    clearTimeout(timer);
  }
};

const browserInputs = [
  ['153', '../r12-hepta-browsers/chrome-headless-shell-linux64/chrome-headless-shell'],
  ['157', '../r12-hepta-browsers/fixed157/chrome-headless-shell-linux64/chrome-headless-shell'],
];
const names = ['complete-single-write', 'complete-split', 'truncated', 'explicit-abort', 'declared-over-limit', 'streamed-over-limit'];
const output = {
  scope: 'Diagnostic transport only: exact pinned SDK methods and real HTTP; synthetic WASM sink; no Rust UI/gateway acceptance',
  sourceRevision: '337566c8b25d47f7e4fff6a202157b65bf183330',
  sdkMethodsSha256: createHash('sha256').update(script).digest('hex'),
  maxBody: limit,
  observationDeadlineMs: 1500,
  browserInputs: [],
  results: [],
  serverRecords,
};
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = 'http://127.0.0.1:' + server.address().port;
let browser;
try {
  for (const [label, relative] of browserInputs) {
    const binary = new URL(relative, import.meta.url).pathname;
    const binarySha256 = createHash('sha256').update(await readFile(binary)).digest('hex');
    browser = await chromium.launch({ executablePath: binary, headless: true });
    output.browserInputs.push({ label, binaryPath: binary, binarySha256, actualVersion: browser.version() });
    for (const name of names) {
      const page = await browser.newPage();
      const start = performance.now();
      const ms = () => Math.round(performance.now() - start);
      const events = [];
      let nativeResponse;
      let terminalResolve;
      const terminal = new Promise(resolve => { terminalResolve = resolve; });
      page.on('response', response => {
        if (response.url() === origin + '/control/' + name) {
          nativeResponse = response;
          events.push({ kind: 'response', ms: ms(), status: response.status() });
        }
      });
      page.on('requestfinished', request => {
        if (request.url() === origin + '/control/' + name) {
          const event = { kind: 'requestfinished', ms: ms() };
          events.push(event);
          terminalResolve(event);
        }
      });
      page.on('requestfailed', request => {
        if (request.url() === origin + '/control/' + name) {
          const event = { kind: 'requestfailed', ms: ms(), error: request.failure()?.errorText };
          events.push(event);
          terminalResolve(event);
        }
      });
      await page.goto(origin);
      await page.evaluate(({ name, limit }) => {
        const host = new window.PinnedNetwork();
        let lastBytes;
        let lastString;
        window.transportResults = [];
        window.host = host;
        Object.assign(host, {
          webgl_context_lost: false,
          network_http_requests: new Map(),
          network_http_hosts: new Map(),
          id_to_key: (lo, hi) => lo + ':' + hi,
          string_to_u8: value => { lastString = value; return { ptr: 0, len: 0 }; },
          array_to_u8: value => { lastBytes = value; return { ptr: 0, len: value.length }; },
          exports: {
            wasm_network_http_progress() {},
            wasm_network_http_response(lo, hi, mlo, mhi, status) {
              window.transportResults.push({ kind: 'response', status, bytes: lastBytes.length, body: new TextDecoder().decode(lastBytes) });
            },
            wasm_network_http_error() { window.transportResults.push({ kind: 'error', error: lastString }); },
          },
        });
        const entry = {
          request_key: '1:0', request_id_lo: 1, request_id_hi: 0,
          metadata_id_lo: 0, metadata_id_hi: 0,
          fetch_url: new URL('/control/' + name, location.href).href,
          method: 'GET', headers: new Headers(), body: undefined,
          max_body: limit, host_key: location.origin, is_archive: false,
          is_archive_range: false, tile_keys: '-', state: 'queued',
          controller: null, stall_timer: null, response_bytes: 0,
        };
        window.entry = entry;
        host.network_http_requests.set(entry.request_key, entry);
        host.network_http_dispatch(entry);
        if (name === 'explicit-abort') setTimeout(() => host.js_network_http_cancel(1, 0), 100);
      }, { name, limit });
      await page.waitForFunction(() => window.transportResults.length > 0, null, { timeout: 5000 });
      const nativeTerminal = await within(terminal, 1500);
      const responseFinished = nativeResponse ? await within(nativeResponse.finished(), 1500) : { responseObserved: false };
      const application = await page.evaluate(() => ({
        results: window.transportResults,
        entryState: window.entry.state,
        recordedResponseBytes: window.entry.response_bytes,
        controllerAborted: window.entry.controller.signal.aborted,
        activeRequests: window.host.network_http_requests.size,
        stallTimerCleared: window.entry.stall_timer === null,
      }));
      const beforeTeardown = events.map(event => ({ ...event }));
      await page.close();
      const result = { browser: label, name, nativeTerminal, responseFinished, application, beforeTeardown, afterTeardownEvents: events.slice(beforeTeardown.length) };
      const applicationErrors = application.results.filter(item => item.kind === 'error');
      const applicationResponses = application.results.filter(item => item.kind === 'response');
      if (name.startsWith('complete-')) {
        result.expectedApplicationSignal = applicationErrors.length === 0 && applicationResponses.length === 1 && applicationResponses[0].status === 503 && applicationResponses[0].body === body.toString();
        result.expectedNativeSignal = nativeTerminal.value?.kind === 'requestfinished' && responseFinished.settled && responseFinished.value === null;
      } else {
        result.expectedApplicationSignal = applicationResponses.length === 0 && applicationErrors.length === 1 && (
          name.endsWith('over-limit') ? /response body exceeds configured limit/.test(applicationErrors[0].error) :
          name === 'explicit-abort' ? /AbortError/.test(applicationErrors[0].error) :
          /TypeError/.test(applicationErrors[0].error)
        );
        // The streamed-limit browser may finish the HTTP body before the SDK rejects it.
        // Native failure is mandatory for incomplete or explicitly aborted transfers only.
        result.expectedNativeSignal = name === 'streamed-over-limit'
          ? nativeTerminal.settled && ['requestfailed', 'requestfinished'].includes(nativeTerminal.value?.kind)
          : nativeTerminal.value?.kind === 'requestfailed';
      }
      result.expectedSdkCleanup = application.entryState === 'done' && application.activeRequests === 0 && application.stallTimerCleared;
      output.results.push(result);
      console.log(JSON.stringify({ browser: label, name, application: result.expectedApplicationSignal, native: result.expectedNativeSignal, cleanup: result.expectedSdkCleanup, terminal: nativeTerminal.value }));
    }
    await browser.close();
    browser = null;
  }
} finally {
  if (browser) await browser.close();
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
  await writeFile(new URL('./response-boundaries-reproduction.json', import.meta.url), JSON.stringify(output, null, 2) + '\n');
}
