"""An uncertain task removal must never become a second removal or media cleanup."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

spec=importlib.util.spec_from_file_location('gallery_owned_flow',Path(__file__).with_name('run_gallery01.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class CloseBoundary(unittest.TestCase):
    def flow(self,fail):
        value=module.Gallery.__new__(module.Gallery)
        value.close_pending=None;value.closed=[];value.pending=None
        value.install_pending=value.uninstall_pending=False
        value.installed={'uid':19999};value.staged=None
        value.folder_fd=value.folder_parent=None
        value.ui=SimpleNamespace(owned=(123,{7}),removals=0,result={},calls=0)
        def close():
            value.ui.calls+=1
            value.ui.owned=None  # Mirrors the retained Trial's before-command transition.
            value.ui.removals+=1
            if fail:raise RuntimeError('REMOVAL_RECEIPT_UNKNOWN')
            value.ui.result['other_tasks_preserved']=True
        value.ui.close=close
        def forbidden(*args):raise AssertionError('UNKNOWN_CLOSE_MUST_NOT_TOUCH_FIXTURE')
        value.prefs=forbidden;value.instrument=forbidden
        value.doc=SimpleNamespace(absent=forbidden,identity=forbidden)
        return value

    def test_unknown_close_keeps_independent_fence_and_never_replays(self):
        value=self.flow(True)
        with self.assertRaisesRegex(RuntimeError,'REMOVAL_RECEIPT_UNKNOWN'):value.close()
        self.assertIsNone(value.ui.owned)
        self.assertEqual(value.close_pending['task'],123)
        with self.assertRaisesRegex(RuntimeError,'PENDING_NO_REPLAY'):value.close()
        self.assertEqual(value.ui.calls,1)
        self.assertEqual(value.closed,[])

    def test_unknown_close_preserves_installed_fixture_during_cleanup(self):
        value=self.flow(True)
        with self.assertRaises(RuntimeError):value.close()
        result=value.cleanup()
        self.assertFalse(result['package_absent'])
        self.assertFalse(result['image_deleted'])
        self.assertEqual(value.ui.calls,1)
        self.assertEqual(len(result['errors']),2)
        self.assertTrue(any('UNKNOWN_EFFECT_PRESERVE_FIXTURE' in x for x in result['errors']))

    def test_joined_normal_close_clears_fence_and_records_only_own_task(self):
        value=self.flow(False);value.close();value.close()
        self.assertIsNone(value.close_pending)
        self.assertEqual(value.closed,[123])
        self.assertEqual(value.ui.calls,1)


if __name__=='__main__':unittest.main()
