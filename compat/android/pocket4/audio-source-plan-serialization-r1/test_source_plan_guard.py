import copy
import unittest
from source_plan_guard import sparse_paths, validate_plan_expansion


def fixture():
    previous = [{'path': 'a', 'url': 'https://android.googlesource.com/platform/a',
                 'commit': '1' * 40, 'purpose': 'original'}]
    expected = [{'path': 'a', 'name': 'platform/a', 'commit': '1' * 40, 'purpose': 'original'}]
    closure = {'previous_project_count': 1, 'project_count': 1, 'projects': expected,
               'added_projects': [], 'added_cones': {}}
    return previous, copy.deepcopy(previous), closure


class SourcePlanGuardTests(unittest.TestCase):
    def test_original_bug_reproduced_and_omitted_empty_accepted(self):
        old, current, closure = fixture()
        with self.assertRaises(KeyError):
            current[0]['sparse_paths']
        self.assertEqual(validate_plan_expansion(old, current, closure)['omitted_empty_sparse_paths'], 1)

    def test_explicit_empty_matches_omission(self):
        old, current, closure = fixture(); current[0]['sparse_paths'] = []
        self.assertTrue(validate_plan_expansion(old, current, closure)['exact_expansion'])

    def test_original_cone_extension(self):
        old, current, closure = fixture(); old[0]['sparse_paths'] = ['first']
        current[0]['sparse_paths'] = ['first', 'second']; closure['projects'][0]['sparse_paths'] = ['first', 'second']
        closure['added_cones'] = {'a': ['second']}
        self.assertTrue(validate_plan_expansion(old, current, closure)['exact_expansion'])

    def test_complete_project_cannot_be_narrowed(self):
        old, current, closure = fixture(); current[0]['sparse_paths'] = ['first']
        closure['projects'][0]['sparse_paths'] = ['first']; closure['added_cones'] = {'a': ['first']}
        with self.assertRaises(ValueError): validate_plan_expansion(old, current, closure)

    def test_null_rejected(self):
        with self.assertRaises(ValueError): sparse_paths({'sparse_paths': None})

    def test_scalar_and_bool_rejected(self):
        for value in ('src', False, 0, 0.0):
            with self.subTest(value=value), self.assertRaises(ValueError): sparse_paths({'sparse_paths': value})

    def test_invalid_and_duplicate_paths_rejected(self):
        for paths in ([True], ['src', 'src'], ['../src'], ['/src'], ['src//a'], ['src/./a'], ['src\\a']):
            with self.subTest(paths=paths), self.assertRaises(ValueError): sparse_paths({'sparse_paths': paths})

    def test_unreviewed_cone_rejected(self):
        old, current, closure = fixture(); current[0]['sparse_paths'] = ['extra']
        with self.assertRaises(ValueError): validate_plan_expansion(old, current, closure)

    def test_changed_commit_rejected(self):
        old, current, closure = fixture(); current[0]['commit'] = '2' * 40
        with self.assertRaises(ValueError): validate_plan_expansion(old, current, closure)

    def test_duplicate_project_rejected(self):
        old, current, closure = fixture(); current.append(copy.deepcopy(current[0]))
        with self.assertRaises(ValueError): validate_plan_expansion(old, current, closure)

    def test_missing_project_rejected(self):
        old, current, closure = fixture(); current.clear()
        with self.assertRaises(ValueError): validate_plan_expansion(old, current, closure)

    def test_unknown_project_field_rejected(self):
        old, current, closure = fixture(); current[0]['trust_me'] = True
        with self.assertRaises(ValueError): validate_plan_expansion(old, current, closure)


if __name__ == '__main__':
    unittest.main()
