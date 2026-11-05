"""Isolated TOML + real Windows DPAPI; never changes the user's Codex home."""
import importlib.util
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

s=importlib.util.spec_from_file_location('management',Path(__file__).parents[1]/'SwirlCodexManage.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

@unittest.skipUnless(os.name=='nt','Windows DPAPI required')
class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name);self.cli=self.home/'codex.exe';self.journal=self.home/'backup.dpapi'
        self.original=b'# keep comments\r\nmodel="synthetic"\r\n[features]\r\nrespect_system_proxy=false # keep\r\n[tools]\r\nprivate_value="PRIVATE_VALUE"\r\n'
        (self.home/'config.toml').write_bytes(self.original)
        self.mock=patch.object(m,'invoke',side_effect=self.invoke);self.mock.start();self.addCleanup(self.mock.stop)
    def invoke(self,cli,home,*args):
        if args==('--version',):return 'codex-cli 0.163.0-test'
        if args==('features','list'):
            return 'respect_system_proxy under development '+str(m.saved(m.decode(m.read_config(home)[0])) is True).lower()
        if args==('features','enable',m.FEATURE):
            path=home/'config.toml';raw=path.read_bytes() if path.exists() else b''
            if b'respect_system_proxy=false' in raw:raw=raw.replace(b'respect_system_proxy=false',b'respect_system_proxy=true')
            else:raw+=b'\n[features]\nrespect_system_proxy=true\n'
            path.write_bytes(raw);return 'Enabled'
        raise AssertionError('unexpected command')
    def test_apply_and_exact_rollback_preserve_comments_and_other_settings(self):
        result=m.apply(self.home,self.cli,self.journal,True)
        self.assertTrue(result['changed']);self.assertNotIn(b'PRIVATE_VALUE',self.journal.read_bytes())
        self.assertEqual(m.without_feature(m.decode(m.read_config(self.home)[0])),m.without_feature(m.decode(self.original)))
        m.rollback(self.home,self.journal,True);self.assertEqual(m.read_config(self.home)[0],self.original)
    def test_later_user_edits_block_rollback(self):
        m.apply(self.home,self.cli,self.journal,True)
        changed=m.read_config(self.home)[0]+b'new_setting=true\n';(self.home/'config.toml').write_bytes(changed)
        with self.assertRaisesRegex(m.Error,'ConfigChangedRollbackRefused'):m.rollback(self.home,self.journal,True)
        self.assertEqual(m.read_config(self.home)[0],changed)
    def test_already_enabled_does_not_write(self):
        (self.home/'config.toml').write_bytes(self.original.replace(b'proxy=false',b'proxy=true'))
        self.assertEqual(m.apply(self.home,self.cli,self.journal,True)['code'],'AlreadyEnabledNoChange');self.assertFalse(self.journal.exists())
    def test_no_authorization_no_mutation(self):
        with self.assertRaisesRegex(m.Error,'ExplicitWriteAuthorizationRequired'):m.apply(self.home,self.cli,self.journal)
        self.assertEqual(m.read_config(self.home)[0],self.original);self.assertFalse(self.journal.exists())
    def test_cli_failure_retains_backup(self):
        original=self.invoke
        def fail(cli,home,*args):
            if args[:2]==('features','enable'):raise m.Error('CliCommandFailed')
            return original(cli,home,*args)
        with patch.object(m,'invoke',side_effect=fail),self.assertRaisesRegex(m.Error,'CliCommandFailed'):m.apply(self.home,self.cli,self.journal,True)
        self.assertEqual(m.read_config(self.home)[0],self.original);self.assertTrue(self.journal.exists())
    def test_unknown_feature_and_unexpected_identity_fail_closed(self):
        for value in ('other_feature stable true','not-codex'):
            with patch.object(m,'invoke',return_value=value),self.assertRaises(m.Error):m.apply(self.home,self.cli,self.journal,True)
        self.assertFalse(self.journal.exists())
    def test_changed_unrelated_settings_are_not_silently_accepted(self):
        original=self.invoke
        def change(cli,home,*args):
            result=original(cli,home,*args)
            if args[:2]==('features','enable'):
                path=home/'config.toml';path.write_bytes(path.read_bytes().replace(b'synthetic',b'user-later-edit'))
            return result
        with patch.object(m,'invoke',side_effect=change),self.assertRaisesRegex(m.Error,'UnexpectedCliConfigChangeBackupRetained'):m.apply(self.home,self.cli,self.journal,True)
        self.assertIn(b'user-later-edit',m.read_config(self.home)[0])
    def test_new_config_is_removed_only_when_unchanged(self):
        (self.home/'config.toml').unlink();m.apply(self.home,self.cli,self.journal,True);m.rollback(self.home,self.journal,True)
        self.assertFalse((self.home/'config.toml').exists())
    def test_wrong_home_and_reused_journal_are_rejected(self):
        m.apply(self.home,self.cli,self.journal,True)
        (self.home/'different').mkdir()
        with self.assertRaisesRegex(m.Error,'JournalNotApplicable'):m.rollback(self.home/'different',self.journal,True)
        m.rollback(self.home,self.journal,True)
        with self.assertRaisesRegex(m.Error,'NewJournalRequired'):m.apply(self.home,self.cli,self.journal,True)
    def test_management_lock_blocks_concurrent_mutations(self):
        with m.mutation_lock(self.home),self.assertRaisesRegex(m.Error,'ManagementBusyOrInterrupted'):
            m.apply(self.home,self.cli,self.journal,True)
        self.assertEqual(m.read_config(self.home)[0],self.original)

@unittest.skipUnless(os.name=='nt' and os.environ.get('SWIRL_CODEX_CLI_TEST'),'opt-in real CLI with isolated home')
class InstalledCliTests(unittest.TestCase):
    def test_installed_cli_apply_and_rollback_only_in_temporary_home(self):
        receipt={'schema':1,'status':'failed','source_sha':os.environ.get('GITHUB_SHA'),
                 'scope':'Real native CLI feature management in a temporary home; no login or model request',
                 'phases':[]}
        parent_home=os.environ.get('CODEX_HOME')
        try:
            cli=m.local_path(os.environ['SWIRL_CODEX_CLI_TEST'])
            self.assertTrue(cli.is_file());self.assertEqual(cli.suffix.lower(),'.exe')
            with cli.open('rb') as stream:
                receipt['cli']={'path':str(cli),'size':cli.stat().st_size,
                                'sha256':hashlib.file_digest(stream,'sha256').hexdigest()}
            # Query the current token identity without retaining its user name/SID.
            identity=subprocess.run([str(Path(os.environ['SystemRoot'])/'System32/whoami.exe'),
                                     '/user','/fo','csv','/nh'],capture_output=True,check=True,timeout=10)
            rows=[row for row in csv.reader(io.StringIO(identity.stdout.decode('utf-8','replace'))) if row]
            self.assertEqual(len(rows),1);self.assertEqual(len(rows[0]),2)
            sid=rows[0][1];self.assertRegex(sid,r'^S-1-\d+(?:-\d+)+$')
            receipt['current_user_sid_sha256']=hashlib.sha256(sid.encode('ascii')).hexdigest()
            with tempfile.TemporaryDirectory(prefix='swirl-codex-cli-',dir=os.environ.get('RUNNER_TEMP')) as folder:
                home=m.local_path(folder);journal=home/'backup.dpapi';config=home/'config.toml'
                self.assertNotEqual(home,m.local_path(Path.home()/'.codex'))
                if parent_home:self.assertNotEqual(home,m.local_path(parent_home))
                receipt['temporary_home']=str(home)
                self.assertEqual(list(home.iterdir()),[])
                original=b'# isolated test, no account state\n[features]\nrespect_system_proxy=false\n'
                config.write_bytes(original)
                original_sha=m.sha(original)
                before=m.inspect(home,cli)
                self.assertFalse(before['effectiveCliValue']);self.assertFalse(before['savedValue'])
                self.assertEqual(config.read_bytes(),original)
                receipt['cli']['version']=before['cliVersion']
                receipt['phases'].append({'action':'inspect','effective':before['effectiveCliValue'],
                                          'saved':before['savedValue'],'stage':before['stage'],
                                          'config_sha256':m.sha(config.read_bytes())})
                applied=m.apply(home,cli,journal,True)
                self.assertTrue(applied['effectiveCliValue']);self.assertTrue(applied['savedValue'])
                self.assertTrue(applied['changed']);self.assertEqual(applied['code'],'Applied')
                after=config.read_bytes();sealed=journal.read_bytes()
                self.assertTrue(sealed.startswith(m.private.MAGIC));self.assertNotIn(original,sealed)
                owned=m.private.read_private(journal)  # Real CryptUnprotectData, never mocked.
                self.assertEqual(owned['home'],str(home));self.assertEqual(owned['cli'],str(cli))
                self.assertEqual(owned['status'],'applied');self.assertEqual(owned['beforeSha256'],original_sha)
                self.assertEqual(base64.b64decode(owned['beforeBase64'],validate=True),original)
                self.assertEqual(owned['afterSha256'],m.sha(after))
                other=home/'different-home';other.mkdir()
                with self.assertRaisesRegex(m.Error,'JournalNotApplicable'):m.rollback(other,journal,True)
                self.assertEqual(config.read_bytes(),after);self.assertEqual(journal.read_bytes(),sealed)
                self.assertFalse((other/'config.toml').exists())
                receipt['dpapi']={'current_user_unprotect_succeeded':True,'home_binding_verified':True,
                                   'cli_binding_verified':True,'wrong_home_rejected':True,
                                   'wrong_home_attempt_left_config_and_journal_unchanged':True,
                                   'plaintext_absent_from_sealed_journal':True,
                                   'sealed_journal_sha256':m.sha(sealed),
                                   'scope':'CurrentUser (production CryptProtectData flags=1); no cross-user test claimed'}
                receipt['phases'].append({'action':'apply','effective':applied['effectiveCliValue'],
                                          'saved':applied['savedValue'],'config_sha256':m.sha(after)})
                rolled=m.rollback(home,journal,True)
                self.assertEqual(rolled['code'],'RolledBack');self.assertFalse(rolled['systemProxyChanged'])
                self.assertEqual(config.read_bytes(),original)
                self.assertEqual(m.private.read_private(journal)['status'],'rolled-back')
                receipt['phases'].append({'action':'rollback','config_sha256':m.sha(config.read_bytes()),
                                          'original_sha256':original_sha,'original_bytes_equal':True,
                                          'journal_status':'rolled-back'})
                restored=m.inspect(home,cli)
                self.assertFalse(restored['effectiveCliValue']);self.assertFalse(restored['savedValue'])
                self.assertEqual(config.read_bytes(),original)
                receipt['phases'].append({'action':'inspect-after-rollback','effective':restored['effectiveCliValue'],
                                          'saved':restored['savedValue'],'config_sha256':m.sha(config.read_bytes())})
                self.assertFalse((home/'auth.json').exists())
                self.assertFalse((home/'auth.json.enc').exists())
                self.assertFalse((home/'.swirl-proxy-management.lock').exists())
                receipt['authentication_files_absent']=True
                receipt['management_lock_released']=True
            receipt['temporary_home_removed']=not home.exists()
            self.assertTrue(receipt['temporary_home_removed'])
            self.assertEqual(os.environ.get('CODEX_HOME'),parent_home)
            receipt['parent_codex_home_environment_unchanged']=True
            receipt['status']='passed'
        except Exception as error:
            receipt['error']=str(error) if isinstance(error,(m.Error,m.private.CaptureError)) else type(error).__name__
            raise
        finally:
            output=os.environ.get('SWIRL_CODEX_CLI_EVIDENCE')
            if output:
                destination=Path(output);destination.mkdir(parents=True,exist_ok=True)
                (destination/'management.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':unittest.main(verbosity=2)
