"""Local Codex compatibility check/apply/rollback. Python >=3.11; Windows DPAPI.

Never reads auth.json, restarts an app, changes system proxy/DNS, or writes
permanent environment variables. Apply/rollback require --allow-write.
"""
import argparse
import base64
import copy
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tomllib

spec=importlib.util.spec_from_file_location('private_capture',Path(__file__).with_name('SubscriptionCapture.py'))
private=importlib.util.module_from_spec(spec);spec.loader.exec_module(private)
FEATURE='respect_system_proxy'

class Error(Exception):pass
@contextmanager
def mutation_lock(home):
    if not home.is_dir():raise Error('CodexHomeMissing')
    path=home/'.swirl-proxy-management.lock'
    try:fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:raise Error('ManagementBusyOrInterrupted') from None
    try:yield
    finally:os.close(fd);path.unlink(missing_ok=True)
def sha(data):return hashlib.sha256(data).hexdigest()
def decode(raw):
    try:return tomllib.loads(raw.decode('utf-8-sig'))
    except (ValueError,UnicodeError):raise Error('InvalidToml') from None
def saved(data):
    features=data.get('features',{})
    if not isinstance(features,dict):raise Error('InvalidFeaturesTable')
    value=features.get(FEATURE)
    if value is not None and not isinstance(value,bool):raise Error('InvalidFeatureValue')
    return value
def without_feature(data):
    result=copy.deepcopy(data)
    if isinstance(result.get('features'),dict):
        result['features'].pop(FEATURE,None)
        if not result['features']:result.pop('features')
    return result
def local_path(path):
    path=Path(path).absolute()
    if str(path).startswith('\\\\') or any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in (path,*path.parents)):
        raise Error('LocalUnredirectedPathRequired')
    return path
def read_config(home):
    path=local_path(home/'config.toml')
    if not path.exists():return b'',False
    if not path.is_file() or path.stat().st_size>4*1024*1024:raise Error('ConfigBounds')
    return path.read_bytes(),True
def invoke(cli,home,*args):
    try:
        result=subprocess.run([str(cli),*args],cwd=home,env={**os.environ,'CODEX_HOME':str(home)},capture_output=True,timeout=20,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except (OSError,subprocess.TimeoutExpired):raise Error('CliExecutionFailed') from None
    if result.returncode:raise Error('CliCommandFailed')
    if len(result.stdout)>1024*1024:raise Error('CliOutputBounds')
    return result.stdout.decode('utf-8','replace').strip()
def inspect(home,cli):
    raw,exists=read_config(home);data=decode(raw)
    version=invoke(cli,home,'--version')
    if not re.fullmatch(r'codex-cli [0-9][0-9A-Za-z.+-]*',version):raise Error('UnexpectedCliIdentity')
    lines=invoke(cli,home,'features','list').splitlines()
    found=[re.fullmatch(r'respect_system_proxy\s+(.+?)\s+(true|false)',line.strip()) for line in lines]
    found=[m for m in found if m]
    if len(found)!=1:raise Error('FeatureUnsupportedOrAmbiguous')
    return {'code':'Checked','cliVersion':version,'cliPath':str(cli),'codexHome':str(home),
            'configPath':str(home/'config.toml'),'configExists':exists,'savedValue':saved(data),
            'effectiveCliValue':found[0][2]=='true','stage':found[0][1],
            'scope':'CLI effective state in CODEX_HOME; desktop/project/session overrides require separate verification',
            'changed':False,'restartPerformed':False,'systemProxyOwnership':'not-verified',
            'remoteControlVerified':False}
def apply(home,cli,journal,allow_write=False):
    if not allow_write:raise Error('ExplicitWriteAuthorizationRequired')
    with mutation_lock(home):return apply_locked(home,cli,journal)
def apply_locked(home,cli,journal):
    before=inspect(home,cli)
    if before['effectiveCliValue']:
        return {**before,'code':'AlreadyEnabledNoChange'}
    if journal.exists():raise Error('NewJournalRequired')
    raw,existed=read_config(home);before_data=decode(raw)
    if saved(before_data)!=before['savedValue']:raise Error('ConfigChangedBeforeApply')
    record={'schema':1,'home':str(home),'cli':str(cli),'status':'prepared','existed':existed,
            'beforeBase64':base64.b64encode(raw).decode(),'beforeSha256':sha(raw)}
    private.save_private(journal,record)
    if read_config(home)!=(raw,existed):raise Error('ConfigChangedBeforeApply')
    try:invoke(cli,home,'features','enable',FEATURE)
    except Error:
        record['status']='cli-failed';private.save_private(journal,record);raise
    after,_=read_config(home)
    record.update(afterSha256=sha(after),afterBase64=base64.b64encode(after).decode())
    if without_feature(decode(after))!=without_feature(before_data) or saved(decode(after)) is not True:
        record['status']='unexpected-change';private.save_private(journal,record)
        raise Error('UnexpectedCliConfigChangeBackupRetained')
    record['status']='applied';private.save_private(journal,record)
    checked=inspect(home,cli)
    if not checked['effectiveCliValue']:raise Error('SavedButEffectiveOverrideRemains')
    return {**checked,'code':'Applied','changed':True,'journal':str(journal),'restartRequiredForExistingDesktop':True}
def rollback(home,journal,allow_write=False):
    if not allow_write:raise Error('ExplicitWriteAuthorizationRequired')
    with mutation_lock(home):return rollback_locked(home,journal)
def rollback_locked(home,journal):
    record=private.read_private(journal)
    if record.get('schema')!=1 or record.get('home')!=str(home) or record.get('status')!='applied':raise Error('JournalNotApplicable')
    current,exists=read_config(home)
    if not exists or sha(current)!=record.get('afterSha256'):raise Error('ConfigChangedRollbackRefused')
    original=base64.b64decode(record['beforeBase64'],validate=True)
    if sha(original)!=record['beforeSha256']:raise Error('JournalIntegrity')
    decode(original)
    # Whole-byte restore is permitted only when the file is still exactly the
    # post-CLI result; any later user edit blocks restoration instead of being lost.
    if read_config(home)!=(current,True):raise Error('ConfigChangedRollbackRefused')
    if record['existed']:private.atomic_write(home/'config.toml',original)
    else:(home/'config.toml').unlink()
    record['status']='rolled-back';private.save_private(journal,record)
    return {'code':'RolledBack','changed':True,'restartPerformed':False,'systemProxyChanged':False}

def windows_context():
    if os.name!='nt':return {'desktopDetection':'not-windows'}
    system=Path(os.environ['SystemRoot'])/'System32'
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    result={'desktopDetection':'unavailable','runningUser':'unavailable','systemProxy':'unavailable'}
    try:
        identity=subprocess.run([str(system/'whoami.exe')],capture_output=True,timeout=5,creationflags=flags)
        if identity.returncode==0:result['runningUser']=identity.stdout.decode('utf-8','replace').strip()
        package=subprocess.run([str(system/'WindowsPowerShell/v1.0/powershell.exe'),'-NoProfile','-NonInteractive','-Command',
            '[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); Get-AppxPackage -Name OpenAI.Codex | Select-Object Version,InstallLocation | ConvertTo-Json -Compress'],capture_output=True,timeout=10,creationflags=flags)
        if package.returncode==0:
            result['desktopPackages']=json.loads(package.stdout.decode('utf-8-sig') or 'null');result['desktopDetection']='current-user-appx'
    except (OSError,ValueError,subprocess.TimeoutExpired):pass
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Internet Settings') as key:
            enabled=bool(winreg.QueryValueEx(key,'ProxyEnable')[0]);server=winreg.QueryValueEx(key,'ProxyServer')[0]
        match=re.fullmatch(r'(?:http=)?127\.0\.0\.1:(\d{1,5})',server)
        result['systemProxy']={'enabled':enabled,'loopbackPort':int(match[1]) if match and 1<=int(match[1])<=65535 else None,'ownerVerified':False}
    except OSError:pass
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['check','apply','rollback'])
    p.add_argument('--codex',type=Path);p.add_argument('--home',type=Path)
    p.add_argument('--journal',type=Path);p.add_argument('--allow-write',action='store_true')
    a=p.parse_args()
    try:
        home=local_path(a.home or os.environ.get('CODEX_HOME') or Path.home()/'.codex')
        if not home.is_dir():raise Error('CodexHomeMissing')
        journal=local_path(a.journal) if a.journal else None
        if a.action!='check' and not journal:raise Error('EncryptedJournalRequired')
        if a.action=='rollback':result=rollback(home,journal,a.allow_write)
        else:
            executable=a.codex or shutil.which('codex')
            if not executable:raise Error('CliNotFound')
            cli=local_path(executable)
            if not cli.is_file() or (os.name=='nt' and cli.suffix.lower()!='.exe'):raise Error('CliExecutableRequired')
            result=inspect(home,cli) if a.action=='check' else apply(home,cli,journal,a.allow_write)
        if a.action=='check':result['windows']=windows_context()
        print(json.dumps(result,ensure_ascii=False));return 0
    except (Error,private.CaptureError) as error:
        print(json.dumps({'code':str(error),'configContentsPrinted':False}));return 1
    except Exception:
        print('{"code":"ManagementFailed","configContentsPrinted":false}');return 1

if __name__=='__main__':raise SystemExit(main())
