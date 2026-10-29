"""Isolated TOML + real Windows DPAPI; never changes the user's Codex home."""
import importlib.util
import os
from pathlib import Path
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
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder);cli=Path(os.environ['SWIRL_CODEX_CLI_TEST']);journal=home/'backup.dpapi'
            original=b'# isolated test, no account state\n[features]\nrespect_system_proxy=false\n'
            (home/'config.toml').write_bytes(original)
            self.assertFalse(m.inspect(home,cli)['effectiveCliValue'])
            self.assertTrue(m.apply(home,cli,journal,True)['effectiveCliValue'])
            m.rollback(home,journal,True)
            self.assertEqual((home/'config.toml').read_bytes(),original)
            self.assertFalse(m.inspect(home,cli)['effectiveCliValue'])

if __name__=='__main__':unittest.main(verbosity=2)
