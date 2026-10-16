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
    handle=None;start=time.monotonic()
    try:
        response=command(op='start',config={'schema':1,'listen':'127.0.0.1:0','selected':'isolated',
            'nodes':[{'id':'isolated','outbound':outbound}],'limits':{'max_connections':2,'handshake_timeout_ms':10000}})
        if not response.get('ok'):return {'success':False,'phase':'configuration','code':'RustStartRejected'}
        handle=response['handle'];port=int(response['status']['address'].rsplit(':',1)[1])
        u=urllib.parse.urlsplit(target)
        authority=f'{u.hostname}:{u.port or 443}'
        with socket.create_connection(('127.0.0.1',port),timeout=12) as raw:
            raw.sendall(f'CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n'.encode('ascii'))
            if not header(raw).startswith(b'HTTP/1.1 200'):
                return {'success':False,'phase':'upstream','code':'ConnectRejected'}
            with ssl.create_default_context().wrap_socket(raw,server_hostname=u.hostname) as tls:
                path=u.path or '/'
                tls.sendall(f'HEAD {path} HTTP/1.1\r\nHost: {u.hostname}\r\nConnection: close\r\n\r\n'.encode('ascii'))
                first=header(tls).split(b'\r\n')[0].split()
                code=int(first[1])
        return {'success':200<=code<400,'phase':'http','httpStatus':code,'elapsedMs':round((time.monotonic()-start)*1000),
                'engine':'swirl-rust','certificateVerified':True,'scope':'single TCP HTTPS HEAD; UDP and full config not verified'}
    except ssl.SSLError:return {'success':False,'phase':'tls','code':'TlsFailed'}
    except Exception:return {'success':False,'phase':'network-or-control','code':'ProbeFailed'}
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


def analyze(cache_dir,inspector,private_output,harness=None,test_limit=0,target='https://example.com/'):
    cache_dir=Path(cache_dir).resolve();index=capture.read_private(cache_dir/'index.dpapi')
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
            public.append({'source':number,'sameContentAs':documents[prior]['sourceOrdinal'],'report':documents[prior]['analysis']['report']})
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
            if outcome.get('success'):
                analysis['report']['nodes'][node_index-1]['real_network_verified']=True
        seen_documents[checksum]=len(documents)
        documents.append({'sourceOrdinal':number,'sources':entry['sources'],'cacheFile':entry['file'],'analysis':analysis,'probes':probes})
        public.append({'source':number,'sourceMappings':len(entry['sources']),'report':analysis['report'],'probes':probes})
    capture.save_private(private_output,{'schema':1,'documents':documents,'testTarget':target,'report':public})
    return {'schema':1,'sourceRequests':len(index['entries']),'distinctDocuments':len(documents),'realTcpProbes':tested,
            'privateDetailsEncrypted':True,'fullConfigurationExecutionVerified':False,'sources':public}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache',required=True,type=Path);p.add_argument('--inspector',required=True,type=Path)
    p.add_argument('--private-output',required=True,type=Path);p.add_argument('--report',required=True,type=Path)
    p.add_argument('--harness',type=Path);p.add_argument('--test-limit',type=int,default=0)
    p.add_argument('--target',default='https://example.com/')
    a=p.parse_args()
    try:
        u=urllib.parse.urlsplit(a.target)
        if not 0<=a.test_limit<=32 or u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment:raise ValueError()
        if a.test_limit and not a.harness:raise ValueError()
        report=analyze(a.cache,a.inspector,a.private_output,a.harness,a.test_limit,a.target)
        capture.atomic_write(a.report,capture.packed(report))
        print(json.dumps({k:v for k,v in report.items() if k!='sources'}))
    except Exception:
        print('{"error":"LocalAnalysisFailed","privateDataPrinted":false}')
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
