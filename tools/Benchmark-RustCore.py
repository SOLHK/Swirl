"""Repeatable loopback baseline for the Rust harness; never a public node benchmark."""
import argparse
import concurrent.futures
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import socket
import socketserver
import ssl
import subprocess
import threading
import time


def header(sock):
    data=b''
    while not data.endswith(b'\r\n\r\n'):
        part=sock.recv(1)
        if not part:raise EOFError()
        data+=part
        if len(data)>16384:raise ValueError('header limit')
    return data


class Echo(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(10)
        try:
            while block:=self.request.recv(65536):self.request.sendall(block)
        except OSError:pass


class Server(socketserver.ThreadingTCPServer):
    daemon_threads=True


def process_usage(process):
    class Memory(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('pageFaults',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in ('peakWorkingSet','workingSet','peakPaged','paged','peakNonPaged','nonPaged','pagefile','peakPagefile')]
    api=ctypes.WinDLL('psapi',use_last_error=True)
    api.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD]
    api.GetProcessMemoryInfo.restype=wintypes.BOOL
    mem=Memory();mem.cb=ctypes.sizeof(mem)
    if not api.GetProcessMemoryInfo(int(process._handle),ctypes.byref(mem),mem.cb):raise OSError('process memory query')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    times=[wintypes.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(int(process._handle),*(ctypes.byref(t) for t in times)):raise OSError('process time query')
    cpu=sum((v.dwHighDateTime<<32)|v.dwLowDateTime for v in times[2:])/1e7
    return {'cpuSeconds':cpu,'workingSetBytes':mem.workingSet,'peakWorkingSetBytes':mem.peakWorkingSet}


def main():
    p=argparse.ArgumentParser();p.add_argument('--harness',required=True);p.add_argument('--output',required=True);p.add_argument('--public-check',action='store_true');a=p.parse_args()
    process=subprocess.Popen([a.harness],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    def command(**value):
        process.stdin.write(json.dumps(value)+'\n');process.stdin.flush();return json.loads(process.stdout.readline())
    server=Server(('127.0.0.1',0),Echo);threading.Thread(target=server.serve_forever,daemon=True).start()
    report={'scope':'Windows loopback Rust harness; synthetic direct route; no throughput comparison or private node acceptance'}
    try:
        result=command(op='start',config={'schema':1,'listen':'127.0.0.1:0','selected':'direct','nodes':[{'id':'direct','outbound':{'type':'direct'}}]})
        if not result['ok']:raise RuntimeError('core start failed')
        port=int(result['status']['address'].rsplit(':',1)[1]);handle=result['handle']
        def connect(target):
            s=socket.create_connection(('127.0.0.1',port),timeout=10)
            s.sendall(f'CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n'.encode())
            if not header(s).startswith(b'HTTP/1.1 200'):s.close();raise OSError('CONNECT rejected')
            return s
        target=f'127.0.0.1:{server.server_address[1]}'
        samples=[]
        before=process_usage(process);start=time.perf_counter()
        for _ in range(100):
            t=time.perf_counter()
            with connect(target) as s:
                s.sendall(b'probe');assert s.recv(5)==b'probe'
            samples.append((time.perf_counter()-t)*1000)
        payload=b'x'*65536
        def transfer(_):
            with connect(target) as s:
                for _ in range(32):
                    s.sendall(payload);received=0
                    while received<len(payload):
                        block=s.recv(len(payload)-received)
                        if not block:raise EOFError()
                        assert block==b'x'*len(block);received+=len(block)
        transfer_start=time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:list(pool.map(transfer,range(16)))
        seconds=time.perf_counter()-transfer_start;wall=time.perf_counter()-start
        after=process_usage(process);samples.sort()
        report.update({'concurrency':16,'bytesEachDirection':16*32*65536,'transferSeconds':seconds,
            'payloadMbpsEachDirection':16*32*65536*8/seconds/1e6,'connectAndEchoMs':{'p50':samples[49],'p95':samples[94],'p99':samples[98],'samples':100},
            'processBefore':before,'processAfter':after,'cpuPercentOneCore':100*(after['cpuSeconds']-before['cpuSeconds'])/wall})
        state=command(op='snapshot',handle=handle)['status'];report['totals']={k:state[k] for k in ('accepted','failed','rejected','upload','download')}
        if a.public_check:
            for host in ['example.com','www.rust-lang.org']:
                try:
                    t=time.perf_counter()
                    with connect(host+':443') as raw:
                        with ssl.create_default_context().wrap_socket(raw,server_hostname=host) as tls:
                            tls.sendall(f'HEAD / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n'.encode())
                            response=header(tls).split(b'\r\n')[0].decode('ascii')
                    report.setdefault('publicDirectChecks',[]).append({'host':host,'response':response,'seconds':time.perf_counter()-t,'certificateVerified':True})
                except Exception as exc:
                    report.setdefault('publicDirectChecks',[]).append({'host':host,'failureType':type(exc).__name__,'verified':False})
        command(op='stop',handle=handle)
    finally:
        process.stdin.close();process.wait(timeout=5);process.stdout.close();process.stderr.close();server.shutdown();server.server_close()
    Path(a.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
