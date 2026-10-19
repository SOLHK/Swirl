#!/usr/bin/env python3
"""Compile the exact production JSONLines reader and exercise a live pipe.

No fonts are read. Supports Linux Swift and native macOS Swift, with an optional
old source to diagnose (but not accept) the historical EOF-dependent reader.
"""
import argparse
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import tempfile
import time


def extract(source):
    text = source.read_text()
    start = text.index('final class JSONLines {')
    end = text.index('\nfunc run() throws {', start)
    return ('import Foundation\n#if canImport(Darwin)\nimport Darwin\n#else\nimport Glibc\n#endif\n'
            'enum OracleError: Error { case invalid(String) }\n' + text[start:end] +
            '\nlet lines = JSONLines()\nwhile let data = try lines.next() { '
            'FileHandle.standardOutput.write(data + Data([10])) }\n')


def probe(binary):
    process = subprocess.Popen([str(binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    records = []
    pending = bytearray()
    def line(timeout):
        stop = time.monotonic() + timeout
        while b'\n' not in pending:
            left = stop - time.monotonic()
            if left <= 0 or not selector.select(left):
                return None
            data = os.read(process.stdout.fileno(),65536)
            if not data:
                return None
            pending.extend(data)
        index = pending.index(10)
        result = bytes(pending[:index+1]); del pending[:index+1]
        return result
    try:
        for payload in (b'{"request":"one"}\n', b'{"request":"two","text":"\xe4\xb8\xad"}\n'):
            process.stdin.write(payload); process.stdin.flush()
            reply = line(2.0)
            records.append({'response_before_eof':reply is not None,'response_exact':reply == payload})
            if reply is None:
                break
        process.stdin.close()
        after_close = line(2.0)
        process.wait(timeout=3.0)
        return {'requests':records, 'response_after_eof':after_close is not None,
                'exit_code':process.returncode,
                'passed':len(records)==2 and all(r['response_exact'] for r in records)}
    finally:
        selector.close()
        if process.poll() is None:
            process.kill(); process.wait(timeout=3)
        for stream in (process.stdin,process.stdout,process.stderr):
            stream.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path(__file__).with_name('coretext_extract.swift'))
    parser.add_argument('--baseline-source',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    report={'platform':sys.platform,'font_data_used':False,'production_reader':{},'baseline_reader':None}
    compiler=shutil.which('swiftc')
    if compiler is None:
        raise RuntimeError('swiftc required; no native execution claimed')
    with tempfile.TemporaryDirectory(prefix='swirl-stream-test-') as tmp:
        for label, source in [('production_reader',args.source),('baseline_reader',args.baseline_source)]:
            if source is None: continue
            swift=Path(tmp)/f'{label}.swift'; binary=Path(tmp)/label
            swift.write_text(extract(source))
            built=subprocess.run([compiler,str(swift),'-o',str(binary)],capture_output=True,text=True,timeout=90)
            if built.returncode:
                raise RuntimeError(built.stderr)
            report[label]=probe(binary)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if report['production_reader']['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
