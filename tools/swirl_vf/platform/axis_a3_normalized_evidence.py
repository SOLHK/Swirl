"""Audit immutable, wholly authored native-channel evidence; no font acceptance."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import zipfile
from probe_axis_a3_normalized_runtime import AXES, FLAGS, PAIR, array_bits, require, validate

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'axis_a3_normalized_runtime_evidence_20261020.json'
COMMIT = '73a5bc831c46b25c3480c9d28eae4216b5add2b3'
RUN = 39406852651


def canonical(value):
    """Unlike Python numeric equality, distinguish true from 1 and 0 from 0.0."""
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':'))


def load_archives(root=ROOT, manifest=None):
    manifest = json.loads(MANIFEST.read_text()) if manifest is None else manifest
    require(manifest['source_commit'] == COMMIT and manifest['workflow_run_id'] == RUN,
            'native_source_binding_changed')
    require(all(manifest[k] is False for k in
                ('mapping_accepted', 'continuous_space_accepted', 'font_conversion_accepted')),
            'native_manifest_acceptance_promoted')
    require([x['runner'] for x in manifest['artifacts']] == ['linux', 'windows-2022', 'windows-2025'],
            'native_platform_set_changed')
    reports = {}
    for item in manifest['artifacts']:
        name = item['archive_file']
        require(Path(name).name == name and name.endswith('.zip'), 'archive_name_invalid')
        raw = (Path(root) / name).read_bytes()
        require(len(raw) == item['archive_size_bytes']
                and hashlib.sha256(raw).hexdigest() == item['archive_sha256'], 'archive_hash_changed')
        with zipfile.ZipFile(Path(root) / name) as archive:
            require(sorted(archive.namelist()) == sorted(item['members']), 'archive_members_changed')
            for member, binding in item['members'].items():
                data = archive.read(member)
                require(len(data) == binding['size_bytes']
                        and hashlib.sha256(data).hexdigest() == binding['sha256'], 'member_hash_changed')
            reports[item['runner']] = json.loads(archive.read(item['runner'] + '.json'))
    audit_reports(reports, manifest)
    return reports


def audit_reports(reports, manifest):
    """Recompute observed glyph checks, counts, scope, ABI and cross-OS equality."""
    require(set(reports) == {'linux', 'windows-2022', 'windows-2025'}, 'report_platform_set_changed')
    for item in manifest['artifacts']:
        key = item['runner']
        report = reports[key]
        require(report['source_commit'] == COMMIT, 'report_source_commit_changed')
        require(all(report[k] is False for k in FLAGS), 'native_report_acceptance_promoted')
        require(report['status'] == 'PASS_FINITE_SYNTHETIC_NORMALIZED_CHANNEL_ONLY'
                and report['synthetic_only'] is True
                and report['q_is_externally_supplied_not_derived_from_binary64'] is True
                and report['conditional_channel_verified'] is True,
                'synthetic_scope_or_completion_changed')
        require(report['windows_tested'] is (key != 'linux')
                and report['platform'] == item['platform'] and report['python'] == item['python'],
                'native_platform_binding_changed')
        require(canonical(report['axes']) == canonical([list(axis) for axis in AXES])
                and report['avar'] == 'authored identity; not original Apple avar'
                and report['original_pair_binary64_bits'] == array_bits([float(x) for x in PAIR], 'd'),
                'fixture_axis_or_original_input_changed')
        actual = validate(report['processes'])
        require(canonical(actual) == canonical(report['checks']) == canonical(manifest['per_platform_checks']),
                'native_counts_changed')
        for process in report['processes']:
            require(process['fixture_sha256'] == manifest['fixture_sha256']
                    and process['versions'] == item['versions']
                    and type(process['c_long_bytes']) is int
                    and process['c_long_bytes'] == item['c_long_bytes'], 'native_binary_or_abi_changed')
            if key != 'linux':
                require([x['sha256'] for x in process['libraries']] ==
                        [manifest['windows_library_sha256'][x] for x in ('harfbuzz', 'freetype')],
                        'windows_dll_hash_changed')
    # Full native payloads, including submitted C arrays and every authored
    # point, are compared. This is not a decimal-label or getter-only match.
    baseline = reports['linux']['processes']
    for key in ('windows-2022', 'windows-2025'):
        require(all(canonical(a['rows']) == canonical(b['rows'])
                    for a, b in zip(baseline, reports[key]['processes'])), 'cross_os_payload_changed')
    totals = {'processes': 4, 'native_observations': 144, 'opposite_order_pairs': 72,
              'normalized_glyph_checks': 128, 'cross_windows_comparison_pairs': 72}
    require(canonical(totals) == canonical(manifest['windows_totals'])
            and manifest['linux_control_is_additional_not_counted_as_windows'] is True,
            'windows_totals_or_scope_changed')
    return {**totals, 'mapping_accepted': False, 'status': 'VERIFIED_AUTHORED_CHANNEL_ONLY'}


if __name__ == '__main__':
    manifest = json.loads(MANIFEST.read_text())
    print(json.dumps(audit_reports(load_archives(manifest=manifest), manifest), sort_keys=True))
