"""Independent new-Main component; no historical Session, Main or execute entry."""
import time
MAX_SEGMENTS = 72

def need(value, reason):
    if not value:
        raise RuntimeError(reason)

class Segments:

    def __init__(self, trial, diagnostic_module, record, uid=10061):
        self.trial, self.diag, self.record, self.uid = (trial, diagnostic_module, record, uid)
        self.first = self.previous = None
        self.last_sample = None
        self.proofs = []
        self.failed = False

    def start(self, before):
        need(self.first is None and type(before.get('guest_seconds')) is int, 'ONE_DIAGNOSTIC_BASELINE_REQUIRED')
        self.first = self.previous = before
        self.last_sample = time.monotonic()

    def accept(self, after, label):
        need(self.previous is not None and (not self.failed) and (len(self.proofs) < MAX_SEGMENTS), 'DIAGNOSTIC_CHAIN_MISSING_FAILED_OR_OVER_BUDGET')
        try:
            need(type(after.get('guest_seconds')) is int and after['guest_seconds'] >= self.previous['guest_seconds'], 'DIAGNOSTIC_GUEST_TIME_MOVED_BACKWARD')
            proof = self.diag.fresh_crashes(self.previous, after, self.uid, self.previous['guest_seconds'])
            need(proof['clear'], 'FRESH_CRASH_OR_ANR_IN_DIAGNOSTIC_SEGMENT')
            row = {'label': label, 'from_guest_seconds': self.previous['guest_seconds'], 'to_guest_seconds': after['guest_seconds'], 'proof': proof}
            self.record('diagnostic-segment-' + str(len(self.proofs) + 1), row)
            self.proofs.append(row)
            self.previous = after
            self.last_sample = time.monotonic()
        except BaseException:
            self.failed = True
            raise

    def checkpoint(self, label, force=False):
        need(self.first is not None and (not self.failed), 'DIAGNOSTIC_CHAIN_NOT_ACTIVE')
        if force or time.monotonic() - self.last_sample >= 12:
            need(len(self.proofs) < MAX_SEGMENTS, 'DIAGNOSTIC_CHAIN_OVER_BUDGET')
            after = self.trial.diagnostics('segment-' + str(len(self.proofs) + 1), self.uid)
            self.accept(after, label)

    def finish(self, after):
        self.accept(after, 'final')
        return {'clear': True, 'coverage': 'all_contiguous_segments_pass_original_parser', 'from_guest_seconds': self.first['guest_seconds'], 'to_guest_seconds': after['guest_seconds'], 'segments': self.proofs, 'old_core13_result_rewritten': False, 'maximum_segments': MAX_SEGMENTS, 'background_workers': 0, 'automatic_retry': False}
