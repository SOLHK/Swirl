"""Native validation around independently derived nested HVF branch contacts.

Reuses the existing float64 symbolic line partition, without fitting native
results. Contacts and adjacent coordinates are a finite diagnostic cohort,
not interval-certified roots or a proof over the three-dimensional cube.
"""
import argparse
from collections import Counter
from pathlib import Path

import numpy as np
from fontTools.ttLib import TTCollection

from export_mac_handoff import SOURCE_SHA, HVGL, digest, require, write_json, variations
from hvf_piecewise_axes import segment_partition


def plan_boundaries(source):
    requests, contacts, counts = [], [], Counter()
    chords = [([-1., -1., -1.], [1., 1., 1.]),
              ([-1., 1., -.75], [1., -1., .875]),
              ([.314159265, -1., -.271828183], [.314159265, 1., -.271828183])]
    with TTCollection(source, lazy=True) as collection:
        table = HVGL(collection.fonts[0].reader['hvgl'])
        for gid in (1166, 19177, 35045, 14813):
            for start, end in chords:
                partition = segment_partition(table, gid, start, end)
                # Preserve every located contact, including coincident contacts.
                for event in partition['events']:
                    contacts.append({'gid': gid, 'start': start, 'end': end, **event})
                    counts[event['kind']] += 1
                # Limit export size independently of source hierarchy depth.
                # At most eight roots per kind per glyph/chord; excluded count
                # is explicit in the receipt, never described as full coverage.
                selected = Counter()
                for event in partition['events']:
                    if selected[event['kind']] >= 8: continue
                    selected[event['kind']] += 1
                    for dt in (-2**-24, 0., 2**-24):
                        t = event['parameter']+dt
                        if 0 <= t <= 1:
                            q = ((1-t)*np.asarray(start)+t*np.asarray(end)).tolist()
                            requests.append([gid, q])
    unique = {}
    for gid, q in requests: unique[(gid, *q)] = [gid, q]
    require(bool(unique), 'no_branch_contacts_located')
    return {'cohorts': ['validation'], 'validation_requests': list(unique.values()),
            'contacts': contacts, 'located_contact_counts': dict(counts),
            'selection': 'first eight contacts per kind per glyph/chord; t plus/minus 2^-24',
            'native_sample_count_per_face': len(unique),
            'root_arithmetic': 'float64 symbolic candidate, not certified exact root',
            'continuous_space_acceptance': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'oracle', 'output'): p.add_argument('--'+name, type=Path, required=True)
    args = p.parse_args()
    require(digest(args.source) == SOURCE_SHA, 'source_identity_differs')
    require(not args.output.exists() and not any((a/'.git').exists() for a in
            (args.output.absolute(), *args.output.absolute().parents)), 'fresh_private_output_required')
    args.output.mkdir(parents=True, mode=0o700)
    plan = plan_boundaries(args.source)
    write_json(args.output/'sampling-plan.json', plan)
    variations(args.source, args.oracle, args.output, plan)
