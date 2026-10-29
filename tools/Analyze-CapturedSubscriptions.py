"""Decrypt local cache into the Rust inspector over stdin; persist private results
with DPAPI. Optional limited Rust-only TCP checks run after caching, never during
the website download window. No converter, browser or complete proxy core.
"""
import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import queue
import socket
import ssl
import subprocess
import threading
import time
import urllib.parse

spec=importlib.util.spec_from_file_location('capture',Path(__file__).with_name('SubscriptionCapture.py'))
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)


# Public output is an allowlist, not a copy of a future inspector response.
# Raw field names, source labels, IDs, keys and free-text errors stay encrypted.
PROTOCOLS = frozenset('ss ssr http socks4 socks4a socks5 trojan vless vmess hysteria hysteria2 tuic anytls snell mieru wireguard ssh naive direct reject unknown'.split())
DIAGNOSTICS = frozenset('''
CertificateVerificationDisabledUnsupported CipherNotImplemented ConflictingAlpn
ConflictingCipher ConflictingIniTls ConflictingServerPort ConflictingUriParameter
DocumentSize DocumentSyntaxOrBudget DuplicateIniParameter DuplicateIniSection
DuplicatePluginParameter DuplicateUriParameter EncodingDepth EncodingNotUtf8 EmptyDocument
IniFields IniSectionLimit IniAssignment IniControlCharacter IniEndpoint IniMissingSection
IniPort IniQuotation IniSectionHeader InvalidAlpn InvalidBase64 InvalidUriAlpn
InvalidUriBoolean InvalidUriEncoding NodeCountLimit NodeParameters
PluginNotImplemented PluginParameters PluginParametersLimit PluginEscape ProtocolNotImplemented
RealityConflictingFingerprint RealityConflictingPublicKey RealityConflictingServerName
RealityConflictingShortId RealityConflictingTransport RealityDiagnosticUnsupported
RealityFingerprintAlpnUnsupported RealityFingerprintRequired RealityFingerprintUnsupported
RealityNotImplemented RealityPublicKey RealityServerName RealityShortId RealityAlpn RealityParameterType
RealitySecurityConflict RealitySecurityRequired RealitySpiderUnsupported
RealityTransportUnsupported RealityUnmappedFields Socks4ExtensionNotImplemented
Socks4NetworkNotImplemented Socks4Parameters Socks4PasswordUnsupported
Socks4UnmappedFields Socks4Version Socks4Port Socks4Server Socks4UriPath Socks4UserId
Socks5UdpTlsUnsupported SsAuthentication SsrUri TcpCandidateNotYetVerified
TcpFastOpenNotImplemented TransportNotImplemented TrojanUsernameUnsupported
UnknownConfigurationShape UnmappedFields UnmappedOrInvalidParameters UriEncoding UriHost UriPort
UriSyntax VlessEncryptionUnsupported VlessFlowUnsupported VlessMultiplexUnsupported
VlessEndpointCount VlessUriPassword VlessUriPath VlessUserCount VmessJson
VlessParameters VlessUdpUnsupported WebSocketConflictingTransport WebSocketParameters
WebSocketProtocolNotImplemented WebSocketUdpNotImplemented WebSocketUnmappedHeaders
WebSocketUnmappedOptions WebSocketAlpnUnsupported WebSocketHeaders WebSocketHost WebSocketPath
RustStartRejected ConnectRejected TlsFailed ProbeFailed ProbeEvidenceIncomplete
NotTested NoNetworkEvidence ProbeCompleted PrivateDiagnosticSuppressed
'''.split())


def safe_code(value):
    return value if isinstance(value, str) and value in DIAGNOSTICS else 'PrivateDiagnosticSuppressed'


def safe_choice(value, choices, default='unknown'):
    return value if isinstance(value, str) and value in choices else default


def safe_count(value, maximum=100000):
    return value if type(value) is int and 0 <= value <= maximum else 0


def new_output_path(path, cache_dir):
    path = Path(path).resolve()
    if path.exists() or path.is_relative_to(Path(cache_dir).resolve()):
        raise capture.CaptureError('NewIsolatedAnalysisRequired')
    return path


def public_report(report):
    """Project only fixed enums, booleans and bounded counts from Rust."""
    rows = []
    for ordinal, node in enumerate(report.get('nodes', [])[:2000], 1):
        rows.append({
            'index': ordinal,
            'protocol': safe_choice(node.get('protocol'), PROTOCOLS),
            'version': safe_choice(node.get('version'), {'0', '1', '2', '4', '4a', '5', 'cipher-family-2022', 'not-declared', 'declared-unrecognized'}),
            'transport': safe_choice(node.get('transport'), {'tcp', 'ws', 'grpc', 'h2', 'http', 'httpupgrade', 'xhttp', 'quic', 'unsupported'}),
            'obfuscation': safe_choice(node.get('obfuscation'), {'none', 'http', 'tls', 'declared-unrecognized'}),
            'tls': safe_choice(node.get('tls'), {'tls', 'reality', 'not-enabled'}),
            'cipher': safe_choice(node.get('cipher'), {'aes-128-gcm', 'aes-256-gcm', 'chacha20-ietf-poly1305', '2022-blake3-aes-128-gcm', '2022-blake3-aes-256-gcm', '2022-blake3-chacha20-poly1305', 'none', 'auto', 'aes-128-cfb', 'rc4-md5', 'not-declared-or-unrecognized'}),
            'udp_declared': node.get('udp_declared') is True,
            'unrecognized_fields': safe_count(node.get('unrecognized_fields')),
            'native_tcp_candidate': node.get('native_tcp_candidate') is True,
            'native_udp_supported': node.get('native_udp_supported') is True,
            # The offline inspector never supplies network evidence.
            'real_network_verified': False,
            'diagnostic': safe_code(node.get('diagnostic')),
        })
    counts = {}
    for node in rows:
        counts[node['protocol']] = counts.get(node['protocol'], 0) + 1
    return {
        'schema': 2,
        'format': safe_choice(report.get('format'), {'clash-yaml', 'clash-json', 'sing-box-json', 'xray-v2ray-json', 'ini', 'uri-list', 'base64'}),
        'recognized': report.get('recognized') is True,
        'parsed': report.get('parsed') is True,
        'error': None if report.get('error') is None else safe_code(report['error']),
        'original_preserved': report.get('original_preserved') is True,
        'nodes': rows, 'protocols': counts,
        'full_configuration_sections_preserved': safe_count(report.get('full_configuration_sections_preserved')),
        'configuration_sections_unvalidated': safe_count(report.get('configuration_sections_unvalidated')),
        'complete_configuration_execution_supported': report.get('complete_configuration_execution_supported') is True,
    }


def public_probe(probe):
    result = {'node': safe_count(probe.get('node'), 2000),
              'success': probe.get('success') is True,
              'phase': safe_choice(probe.get('phase'), {'configuration', 'upstream', 'http', 'tls', 'network-or-control', 'pending'}),
              'code': safe_code(probe.get('code', 'ProbeCompleted'))}
    for key in ('runtimeStarted', 'proxyConnectAccepted', 'certificateVerified', 'reusedIdenticalNodeEvidence'):
        result[key] = probe.get(key) is True
    if type(probe.get('httpStatus')) is int and 100 <= probe['httpStatus'] <= 599:
        result['httpStatus'] = probe['httpStatus']
    if type(probe.get('elapsedMs')) is int and 0 <= probe['elapsedMs'] <= 3600000:
        result['elapsedMs'] = probe['elapsedMs']
    return result


def header(s):
    data=b''
    while not data.endswith(b'\r\n\r\n'):
        part=s.recv(1)
        if not part:raise EOFError()
        data+=part
        if len(data)>16384:raise ValueError('HeaderLimit')
    return data


def test_node(harness,outbound,target):
    process=subprocess.Popen([str(harness)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    replies=queue.Queue(maxsize=4)
    def read():
        for line in process.stdout:
            try:replies.put(line,timeout=1)
            except queue.Full:return
    reader=threading.Thread(target=read,daemon=True);reader.start()
    def command(**value):
        process.stdin.write(json.dumps(value)+'\n');process.stdin.flush()
        return json.loads(replies.get(timeout=15))
    handle=None;start=time.monotonic();progress={'runtimeStarted':False,'proxyConnectAccepted':False}
    try:
        response=command(op='start',config={'schema':1,'listen':'127.0.0.1:0','selected':'isolated',
            'nodes':[{'id':'isolated','outbound':outbound}],'limits':{'max_connections':2,'handshake_timeout_ms':10000}})
        if not response.get('ok'):return {'success':False,'phase':'configuration','code':'RustStartRejected',**progress}
        handle=response['handle'];port=int(response['status']['address'].rsplit(':',1)[1])
        progress['runtimeStarted']=True
        u=urllib.parse.urlsplit(target)
        authority=f'{u.hostname}:{u.port or 443}'
        with socket.create_connection(('127.0.0.1',port),timeout=12) as raw:
            raw.sendall(f'CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n'.encode('ascii'))
            if not header(raw).startswith(b'HTTP/1.1 200'):
                return {'success':False,'phase':'upstream','code':'ConnectRejected',**progress}
            progress['proxyConnectAccepted']=True
            with ssl.create_default_context().wrap_socket(raw,server_hostname=u.hostname) as tls:
                path=u.path or '/'
                tls.sendall(f'HEAD {path} HTTP/1.1\r\nHost: {u.hostname}\r\nConnection: close\r\n\r\n'.encode('ascii'))
                first=header(tls).split(b'\r\n')[0].split()
                code=int(first[1])
        return {'success':200<=code<400,'phase':'http','httpStatus':code,'elapsedMs':round((time.monotonic()-start)*1000),
                'engine':'swirl-rust','certificateVerified':True,'scope':'single TCP HTTPS HEAD; UDP and full config not verified',**progress}
    except ssl.SSLError:return {'success':False,'phase':'tls','code':'TlsFailed',**progress}
    except Exception:return {'success':False,'phase':'network-or-control','code':'ProbeFailed',**progress}
    finally:
        try:
            if handle:command(op='stop',handle=handle)
        except Exception:pass
        process.stdin.close()
        try:process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            # Only our own isolated harness, never Swirl/Codex/user applications.
            process.terminate();process.wait(timeout=3)
        reader.join(timeout=1);process.stdout.close()


def test_cases(report, probes, capture_reloaded=False):
    """Keep each proof stage separate; an offline candidate is not a connection."""
    report = public_report(report)
    outcomes = {probe['node']: probe for probe in map(public_probe, probes)}
    cases = []
    for node in report.get('nodes', []):
        parsed = report['parsed'] and report['recognized']
        candidate = parsed and node['native_tcp_candidate']
        case = {'node': node['index'], 'parse': 'passed' if parsed else 'failed',
                'completeParameterMapping': 'passed' if candidate else 'blocked',
                'capturedResponseDpapiReload': 'passed' if capture_reloaded else 'not-tested',
                'qtNodeStoreReload': 'not-tested',
                'nativeEligibility': 'passed' if candidate else 'blocked',
                'runtimeStart': 'not-tested', 'proxyConnect': 'not-tested',
                'realityConnection': 'not-tested', 'realityAuthentication': 'not-tested',
                'vision': 'not-tested', 'visionDirect': 'not-tested',
                'http': 'not-tested', 'https': 'not-tested',
                'tcp': 'blocked', 'tcpReason': node['diagnostic'],
                'udp': 'not-tested' if node['native_udp_supported'] else 'blocked',
                'fullConfiguration': 'not-tested'}
        if candidate:
            probe = outcomes.get(node['index'], {})
            if not probe or probe.get('code') == 'NotTested':
                case.update(tcp='not-tested', tcpReason='NoNetworkEvidence')
            else:
                verified = (probe.get('success') and probe.get('certificateVerified')
                            and probe.get('proxyConnectAccepted') and probe.get('runtimeStarted')
                            and 200 <= probe.get('httpStatus', 0) < 400)
                case.update(tcp='passed' if verified else 'failed',
                            tcpReason=probe['code'] if not probe.get('success') or verified else 'ProbeEvidenceIncomplete',
                            runtimeStart='passed' if probe['runtimeStarted'] else 'failed',
                            proxyConnect='passed' if probe['proxyConnectAccepted'] else 'failed',
                            https='passed' if verified else 'failed')
        cases.append(case)
    return cases


def analyze(cache_dir,inspector,private_output,harness=None,test_limit=0,target='https://example.com/'):
    cache_dir=Path(cache_dir).resolve();private_output=new_output_path(private_output,cache_dir)
    index=capture.read_private(cache_dir/'index.dpapi')
    documents=[];public=[];tested=0;seen_nodes={};seen_documents={}
    for number,entry in enumerate(index['entries'].values(),1):
        path=(cache_dir/entry['file']).resolve()
        if not path.is_relative_to(cache_dir):raise capture.CaptureError('CachePathRejected')
        record=capture.read_private(path);raw=base64.b64decode(record['rawBase64'],validate=True)
        if hashlib.sha256(raw).hexdigest()!=record['rawSha256']:raise capture.CaptureError('CacheIntegrityFailed')
        decoded=capture.decode_body(raw,record['headers'].get('content-encoding',''))
        checksum=hashlib.sha256(decoded).hexdigest()
        if checksum!=record['decodedSha256']:raise capture.CaptureError('CacheIntegrityFailed')
        if checksum in seen_documents:
            prior=seen_documents[checksum];documents[prior]['sources'].extend(entry['sources'])
            public.append({'source':number,'sameContentAs':documents[prior]['sourceOrdinal'],'report':public_report(documents[prior]['analysis']['report']),
                           'tests':test_cases(documents[prior]['analysis']['report'],documents[prior]['probes'],True)})
            continue
        try:
            result=subprocess.run([str(inspector),'--private-json'],input=decoded,capture_output=True,timeout=30,check=False)
            if result.returncode!=0:raise capture.CaptureError('RustInspectorFailed')
            analysis=json.loads(result.stdout)
        except Exception:
            public.append({'source':number,'error':'RustInspectionFailed'});continue
        probes=[]
        for node_index,outbound in enumerate(analysis.get('tcpCandidates',[]),1):
            if outbound is None:continue
            identity=hashlib.sha256(capture.packed(outbound)).hexdigest()
            if identity in seen_nodes:
                outcome={**seen_nodes[identity],'reusedIdenticalNodeEvidence':True}
            elif harness and tested<test_limit:
                outcome=test_node(harness,outbound,target);tested+=1;seen_nodes[identity]=outcome
            else:
                outcome={'success':False,'code':'NotTested','phase':'pending'}
            probes.append({'node':node_index,**outcome})
        seen_documents[checksum]=len(documents)
        documents.append({'sourceOrdinal':number,'sources':entry['sources'],'cacheFile':entry['file'],'analysis':analysis,'probes':probes})
        public.append({'source':number,'sourceMappings':len(entry['sources']),'report':public_report(analysis['report']),
                       'probes':[public_probe(probe) for probe in probes],
                       'tests':test_cases(analysis['report'],probes,True)})
    private_result={'schema':2,'documents':documents,'testTarget':target,'report':public}
    capture.save_private(private_output,private_result)
    if capture.read_private(private_output)!=private_result:raise capture.CaptureError('AnalysisReloadFailed')
    return {'schema':2,'sourceRequests':len(index['entries']),'distinctDocuments':len(documents),'realTcpProbes':tested,
            'privateDetailsEncrypted':True,'privateAnalysisReloadVerified':True,
            'offlineOnly':tested==0,'qtProductExecutionVerified':False,
            'fullConfigurationExecutionVerified':False,'sources':public}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache',required=True,type=Path);p.add_argument('--inspector',required=True,type=Path)
    p.add_argument('--private-output',required=True,type=Path);p.add_argument('--report',required=True,type=Path)
    p.add_argument('--harness',type=Path);p.add_argument('--test-limit',type=int,default=0)
    p.add_argument('--target',default='https://example.com/')
    a=p.parse_args()
    try:
        private_path=new_output_path(a.private_output,a.cache)
        report_path=new_output_path(a.report,a.cache)
        if private_path==report_path:raise capture.CaptureError('DistinctOutputsRequired')
        u=urllib.parse.urlsplit(a.target)
        if not 0<=a.test_limit<=32 or u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment:raise ValueError()
        if a.test_limit and not a.harness:raise ValueError()
        report=analyze(a.cache,a.inspector,private_path,a.harness,a.test_limit,a.target)
        capture.atomic_write(report_path,capture.packed(report))
        print(json.dumps({k:v for k,v in report.items() if k!='sources'}))
    except Exception:
        print('{"error":"LocalAnalysisFailed","privateDataPrinted":false}')
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
