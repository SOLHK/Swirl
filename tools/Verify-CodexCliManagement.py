"""Run the existing Windows management suite with a verified, real Codex CLI.

The installed-CLI opt-in is mandatory here. A skip, missing feature, wrong binary,
or absent phase receipt fails the CI gate. Only synthetic temporary homes are used.
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import time
import unittest
import xml.etree.ElementTree as ET


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []
        self.started = {}

    def startTest(self, test):
        self.started[test.id()] = time.monotonic()
        super().startTest(test)

    def record(self, test, status, detail=None):
        self.records.append({'id': test.id(), 'status': status,
                             'seconds': time.monotonic() - self.started[test.id()], 'detail': detail})

    def addSuccess(self, test):
        super().addSuccess(test)
        self.record(test, 'passed')

    def addError(self, test, err):
        super().addError(test, err)
        self.record(test, 'error', self.errors[-1][1])

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.record(test, 'failed', self.failures[-1][1])

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.record(test, 'skipped', reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.record(test, 'expected-failure', self.expectedFailures[-1][1])

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.record(test, 'unexpected-success')


def test_ids(suite):
    result = []
    for test in suite:
        result.extend(test_ids(test) if isinstance(test, unittest.TestSuite) else [test.id()])
    return result


def write_junit(path, records):
    suite = ET.Element('testsuite', name='Codex CLI management', tests=str(len(records)),
                       failures=str(sum(row['status'] in ('failed', 'unexpected-success') for row in records)),
                       errors=str(sum(row['status'] == 'error' for row in records)),
                       skipped=str(sum(row['status'] in ('skipped', 'expected-failure') for row in records)),
                       time=str(sum(row['seconds'] for row in records)))
    for row in records:
        classname, _, name = row['id'].rpartition('.')
        case = ET.SubElement(suite, 'testcase', name=name, classname=classname, time=str(row['seconds']))
        if row['status'] != 'passed':
            element = 'skipped' if row['status'] in ('skipped', 'expected-failure') else ('error' if row['status'] == 'error' else 'failure')
            ET.SubElement(case, element, message=row['status']).text = row.get('detail') or row['status']
    ET.ElementTree(suite).write(path, encoding='utf-8', xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cli', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--lock', type=Path, default=Path(__file__).with_name('codex-cli-windows.lock.json'))
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    report = {'schema': 1, 'status': 'failed', 'run_id': os.environ.get('GITHUB_RUN_ID'),
              'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'tests': [], 'tests_run': 0}
    output = io.StringIO()
    original_env = {name: os.environ.get(name) for name in ('SWIRL_CODEX_CLI_TEST', 'SWIRL_CODEX_CLI_EVIDENCE')}
    try:
        if os.name != 'nt':
            raise RuntimeError('WindowsDPAPIRequired; this acceptance gate cannot be skipped')
        root = Path(__file__).resolve().parents[1]
        source = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, text=True, capture_output=True, check=True).stdout.strip()
        tree = subprocess.run(['git', 'rev-parse', 'HEAD^{tree}'], cwd=root, text=True, capture_output=True, check=True).stdout.strip()
        report.update(source_sha=source, source_tree=tree)
        if os.environ.get('GITHUB_SHA') and source != os.environ['GITHUB_SHA']:
            raise RuntimeError('CheckedOutSourceMismatch')
        provision = load_module('codex_cli_provisioning', Path(__file__).with_name('Install-CodexCli.py'))
        lock = provision.read_lock(args.lock)
        installation = json.loads((args.evidence/'provisioning.json').read_text(encoding='utf-8'))
        cli = args.cli.resolve()
        binary_sha = provision.file_sha256(cli)
        if (installation.get('status') != 'passed' or installation.get('source_sha') != source
                or installation.get('lock_sha256') != provision.file_sha256(args.lock)
                or Path(installation['binary']['path']).resolve() != cli
                or installation['binary']['sha256'] != binary_sha or binary_sha != lock['binary']['sha256']
                or cli.stat().st_size != lock['binary']['size']):
            raise RuntimeError('VerifiedProvisioningRequired')
        report['cli_sha256'] = binary_sha
        report['release_tag'] = lock['release_tag']
        os.environ['SWIRL_CODEX_CLI_TEST'] = str(cli)
        os.environ['SWIRL_CODEX_CLI_EVIDENCE'] = str(args.evidence.resolve())
        # Import after opt-in is set, so the original class decorator evaluates it.
        module = load_module('codex_management_tests', root/'tools/tests/test_codex_management.py')
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        expected_ids = test_ids(suite)
        real_test = 'codex_management_tests.InstalledCliTests.test_installed_cli_apply_and_rollback_only_in_temporary_home'
        if expected_ids.count(real_test) != 1:
            raise RuntimeError('OriginalInstalledCliTestMissing')
        result = unittest.TextTestRunner(stream=output, verbosity=2, resultclass=RecordedResult).run(suite)
        report.update(tests=result.records, tests_run=result.testsRun, expected_test_ids=expected_ids,
                      passed=sum(row['status'] == 'passed' for row in result.records),
                      failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped))
        if (not result.wasSuccessful() or any(row['status'] != 'passed' for row in result.records)
                or sorted(row['id'] for row in result.records) != sorted(expected_ids)
                or result.testsRun != len(expected_ids)):
            raise RuntimeError('EveryManagementTestMustExecuteAndPass')
        phases = json.loads((args.evidence/'management.json').read_text(encoding='utf-8'))
        if (phases.get('status') != 'passed' or phases['cli']['version'] != lock['version_output']
                or phases['cli']['sha256'] != binary_sha or phases.get('source_sha') != source
                or [row['action'] for row in phases['phases']] != ['inspect', 'apply', 'rollback', 'inspect-after-rollback']
                or phases['phases'][2].get('original_bytes_equal') is not True
                or phases.get('temporary_home_removed') is not True):
            raise RuntimeError('RealCliPhaseEvidenceMismatch')
        report['real_cli_test'] = real_test
        report['status'] = 'passed'
        return 0
    except Exception as error:
        report['error'] = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        output.write('\nCodex CLI acceptance failed: ' + report['error'] + '\n')
        return 1
    finally:
        for name, value in original_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        (args.evidence/'unittest.txt').write_text(output.getvalue(), encoding='utf-8')
        (args.evidence/'unittest.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        write_junit(args.evidence/'unittest.xml', report['tests'])
        print(output.getvalue(), end='')


if __name__ == '__main__':
    raise SystemExit(main())
