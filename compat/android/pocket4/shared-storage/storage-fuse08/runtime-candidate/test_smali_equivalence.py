import unittest
from smali_equivalence import method_ir, header_ir


FIXTURE='''.method public f()V
    .registers 2
    :start
    const-string v0, "literal :destination"
    if-eqz v0, :finish
    invoke-static {}, LExample;->g()V
    :finish
    :end
    return-void
    .catch Ljava/lang/Exception; {:start .. :end} :handler
    :handler
    move-exception v1
    throw v1
.end method'''


class SemanticBoundaryTests(unittest.TestCase):
    def test_renamed_labels_preserve_instruction_destinations(self):
        other=FIXTURE.replace(':start',':a').replace(':finish',':b').replace(':end',':c').replace(':handler',':d')
        self.assertEqual(method_ir(FIXTURE),method_ir(other))

    def test_retargeted_branch_is_different(self):
        other=FIXTURE.replace('if-eqz v0, :finish','if-eqz v0, :handler')
        self.assertNotEqual(method_ir(FIXTURE),method_ir(other))

    def test_changed_catch_coverage_is_different(self):
        other=FIXTURE.replace('{:start .. :end}','{:finish .. :end}')
        self.assertNotEqual(method_ir(FIXTURE),method_ir(other))

    def test_changed_handler_is_different(self):
        other=FIXTURE.replace('} :handler','} :finish')
        self.assertNotEqual(method_ir(FIXTURE),method_ir(other))

    def test_width_normalization_requires_the_same_string(self):
        self.assertEqual(method_ir(FIXTURE),method_ir(FIXTURE.replace('const-string ','const-string/jumbo ')))
        other=FIXTURE.replace('literal :destination','literal :different')
        self.assertNotEqual(method_ir(FIXTURE),method_ir(other))

    def test_nop_insertion_is_not_silently_ignored(self):
        other=FIXTURE.replace('    :finish\n','    nop\n    :finish\n')
        self.assertNotEqual(method_ir(FIXTURE),method_ir(other))

    def test_catch_type_is_preserved(self):
        other=FIXTURE.replace('.catch Ljava/lang/Exception;','.catch Ljava/lang/RuntimeException;')
        self.assertNotEqual(method_ir(FIXTURE),method_ir(other))

    def test_only_boolean_default_is_normalized_in_fields(self):
        self.assertEqual(header_ir('.field static a:Z = false'),header_ir('.field static a:Z'))
        self.assertNotEqual(header_ir('.field static a:Z = true'),header_ir('.field static a:Z'))

    def test_nested_annotations_do_not_become_instructions(self):
        annotation='''    .annotation runtime LExampleAnnotation;
        value = .subannotation LNested;
            name = "label :finish"
        .end subannotation
    .end annotation
'''
        other=FIXTURE.replace('    .registers 2\n','    .registers 2\n'+annotation)
        self.assertEqual(method_ir(FIXTURE)['instructions'],method_ir(other)['instructions'])
        self.assertEqual(method_ir(FIXTURE)['exception_coverage'],method_ir(other)['exception_coverage'])
        self.assertNotEqual(method_ir(FIXTURE)['metadata'],method_ir(other)['metadata'])


if __name__=='__main__':unittest.main()
