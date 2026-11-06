def fixture_xml_version_absence(raw):
    """Decode the exact observed fixture XML root; never infer absence from a missing dump."""
    need(len(raw) == FIXTURE_XML_PIN["bytes"] and sha(raw) == FIXTURE_XML_PIN["sha256"],
         "EXACT_OBSERVED_FIXTURE_XML_REQUIRED")
    text = raw.decode("utf-8", "strict")
    lines = text.splitlines()
    need(lines and lines[0] == "N: android=http://schemas.android.com/apk/res/android",
         "FIXTURE_XML_ANDROID_NAMESPACE_REQUIRED")
    roots = [i for i, line in enumerate(lines) if re.fullmatch(r"  E: manifest \(line=[0-9]+\)", line)]
    need(len(roots) == 1 and roots[0] == 1, "ONE_EXACT_FIXTURE_XML_MANIFEST_ROOT_REQUIRED")
    attributes = {}
    for line in lines[roots[0] + 1:]:
        if re.fullmatch(r"    E: [A-Za-z0-9_.:-]+ \(line=[0-9]+\)", line):
            break
        match = re.fullmatch(r"    A: ([A-Za-z0-9_.:-]+)(?:\(0x[0-9a-fA-F]+\))?=(.*)", line)
        need(match is not None and match[1] not in attributes, "FIXTURE_XML_ROOT_ATTRIBUTE_UNPARSED_OR_DUPLICATE")
        attributes[match[1]] = match[2]
    version_keys = ("android:versionCode", "android:versionCodeMajor", "android:versionName")
    need(not any(key in attributes for key in version_keys), "FIXTURE_VERSION_ATTRIBUTES_MUST_ACTUALLY_BE_ABSENT")
    package = attributes.get("package")
    literal = re.fullmatch(r'("(?:[^"\\]|\\.)*") \(Raw: ("(?:[^"\\]|\\.)*")\)', package or "")
    need(literal is not None and json.loads(literal[1]) == json.loads(literal[2]) == FIXTURE_SCOPE["package"],
         "EXACT_FIXTURE_XML_PACKAGE_REQUIRED")
    return {"xml_stream": FIXTURE_XML_PIN, "root_package": FIXTURE_SCOPE["package"],
            "root_version_attributes": {key: None for key in version_keys},
            "all_three_version_attributes_absent": True, "missing_XML_accepted": False}


def manifest_with_exact_fixture_default(raw, xml_raw, package, expected, apk, signature):
    """Only the one signed, fixed fixture may use Android's absent-version default.

    All other packages retain the original strict badging parser unchanged.
    Empty raw values stay empty in evidence; absence stays null. The separate
    effective long code is 0 only after XML, fresh signature and PM agree.
    """
    if package != FIXTURE_SCOPE["package"]:
        return badging_manifest(raw)
    need(expected == FIXTURE_SCOPE and expected["uid"] == 10115 and
         type(expected["version_code"]) is int and expected["version_code"] == 0 and
         expected["apks"] == [apk], "ONLY_EXACT_ALREADY_INSTALLED_FIXTURE_SCOPE")
    need(signature is not None and signature.get("verified") is True and
         signature.get("cryptographic_verification_performed") is True and
         signature.get("API_minimum_override_used") is False and signature.get("integrity_check_bypassed") is False and
         signature.get("signer_certificate_sha256") == expected["package_manager_certificate_sha256"],
         "FRESH_NORMAL_SIGNATURE_AND_FIXED_PM_SIGNER_REQUIRED_BEFORE_DEFAULT")
    need(len(raw) == FIXTURE_BADGING_PIN["bytes"] and sha(raw) == FIXTURE_BADGING_PIN["sha256"],
         "EXACT_OBSERVED_EMPTY_FIXTURE_BADGING_REQUIRED")
    absence = fixture_xml_version_absence(xml_raw)
    text = raw.decode("utf-8", "strict")
    lines = [line for line in text.splitlines() if line.startswith("package: ")]
    need(len(lines) == 1, "UNIQUE_AAPT_PACKAGE_LINE")
    attrs, at = {}, len("package:")
    while at < len(lines[0]):
        match = re.match(r"\s+([A-Za-z][A-Za-z0-9_-]*)='([^']*)'", lines[0][at:])
        need(match is not None and match[1] not in attrs, "BADGING_ATTRIBUTE_UNPARSED_OR_DUPLICATE")
        attrs[match[1]] = match[2]
        at += match.end()
    need(attrs.get("name") == package and attrs.get("versionCode") == "" and attrs.get("versionName") == "" and
         "versionCodeMajor" not in attrs and "split" not in attrs, "ONLY_EXACT_EMPTY_ABSENT_FIXTURE_VERSION_FORM")
    value = {"package": package, "version_code": None, "version_code_major": None, "version_name": None,
             "version_code_raw": attrs["versionCode"], "version_name_raw": attrs["versionName"],
             "split_name": None, "package_line_raw": lines[0], "long_version_code": 0,
             "effective_version_code_source": "ANDROID_ABSENT_ATTRIBUTE_DEFAULT_CONFIRMED_WITH_FIXED_PM_ZERO",
             "version_default_evidence": {"schema": "pocket4-exact-fixture-absent-version-evidence-v1",
                 "badging_stream": FIXTURE_BADGING_PIN, "xml_absence": absence,
                 "fixed_APK_sha256": apk["sha256"], "fixed_PM_version_code": 0,
                 "fresh_signature_matches_fixed_PM": True, "declared_version_name_invented": False,
                 "Android_parser_reference": ANDROID_VERSION_DEFAULT_REFERENCE}}
    # This is the identical SDK/ABI parsing contract used by the original
    # parser; no existing package receives a new version default.
    for name, prefixes in (("min_sdk", ("sdkVersion:", "minSdkVersion:")),
                           ("target_sdk", ("targetSdkVersion:",)), ("max_sdk", ("maxSdkVersion:",))):
        found = [line for line in text.splitlines() if line.startswith(prefixes)]
        need(len(found) <= 1, "AMBIGUOUS_AAPT_SDK")
        if found:
            parsed = re.fullmatch(r"(?:sdkVersion|minSdkVersion|targetSdkVersion|maxSdkVersion):'([^']+)'", found[0])
            need(parsed is not None, "MALFORMED_AAPT_SDK_LINE")
            value[name] = parsed[1]
        else:
            value[name] = None
    native = [line for line in text.splitlines() if line.startswith("native-code:")]
    need(len(native) <= 1, "AMBIGUOUS_AAPT_ABI")
    value["native_abis"] = re.findall(r"'([^']*)'", native[0]) if native else []
    value["native_abi_source"] = "aapt2_dump_badging_current_APK"
    return value
