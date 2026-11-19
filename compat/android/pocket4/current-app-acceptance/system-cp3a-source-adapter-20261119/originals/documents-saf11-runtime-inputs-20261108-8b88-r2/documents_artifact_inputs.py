"""Explicit references to a future helper build and same-Main pm-help proof.

Shape validation here is deliberately not source/build/runtime qualification.
The trusted case plan must admit the actual referenced receipts and their full
owned command/source/installed evidence before constructing the package fixture.
"""
from dataclasses import dataclass
from pathlib import Path
import re

QUALIFICATION = Path('/home/alex/work/pocket4-android-final/qualification')


@dataclass(frozen=True)
class HelperArtifactInputs:
    apk_path: Path
    apk_bytes: int
    apk_sha256: str
    signer_certificate_sha256: str
    build_receipt_path: Path
    build_receipt_sha256: str
    pm_help_receipt_path: Path
    pm_help_receipt_sha256: str

    def __post_init__(self):
        self.validate_reference_shapes()

    def validate_reference_shapes(self):
        if any(not isinstance(p, Path) for p in (self.apk_path, self.build_receipt_path, self.pm_help_receipt_path)):
            raise ValueError('EXPLICIT_HELPER_ARTIFACT_PATHS_REQUIRED')
        parent = self.apk_path.parent
        if (parent.parent != QUALIFICATION or re.fullmatch('business-documents-saf-helper-build-[0-9a-f]{32}', parent.name) is None
                or self.apk_path.name != 'owned-saf.apk'
                or self.build_receipt_path != parent / 'build-result.json'):
            raise ValueError('NEW_HELPER_BUILD_AND_APK_LOCATIONS_REQUIRED')
        help_parent = self.pm_help_receipt_path.parent
        if (help_parent.parent != QUALIFICATION or self.pm_help_receipt_path.name != 'result.json'
                or re.fullmatch('business-documents-saf-pm-help-[0-9a-f]{32}', help_parent.name) is None):
            raise ValueError('NEW_PM_HELP_RECEIPT_LOCATION_REQUIRED')
        if type(self.apk_bytes) is not int or not 0 < self.apk_bytes <= 1048576:
            raise ValueError('ORIGINAL_ONE_MIB_HELPER_APK_BOUND_REQUIRED')
        if any(not isinstance(v, str) or re.fullmatch('[0-9a-f]{64}', v) is None for v in (
                self.apk_sha256, self.signer_certificate_sha256,
                self.build_receipt_sha256, self.pm_help_receipt_sha256)):
            raise ValueError('EXPLICIT_FULL_ARTIFACT_DIGESTS_REQUIRED')

    @property
    def APK(self):return self.apk_path
    @property
    def APK_BYTES(self):return self.apk_bytes
    @property
    def APK_SHA(self):return self.apk_sha256
    @property
    def CERT_SHA(self):return self.signer_certificate_sha256
    @property
    def BUILD(self):return self.build_receipt_path
    @property
    def BUILD_SHA(self):return self.build_receipt_sha256
    @property
    def PM_HELP(self):return self.pm_help_receipt_path
    @property
    def PM_HELP_SHA(self):return self.pm_help_receipt_sha256
