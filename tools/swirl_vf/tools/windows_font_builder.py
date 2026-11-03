"""Private Alpha/Beta HVF -> four-face Windows glyf/gvar candidate builder.

No reference-font input exists here. Geometry always comes from the specified
Apple source and the retained HVF evaluator. Private output is mandatory.
The unchanged 1/32 metric is reported, not used to mislabel an Alpha as accepted.
"""
from __future__ import annotations

import argparse
import array
from collections import Counter
from collections import deque
from concurrent.futures import ProcessPoolExecutor
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import time
import multiprocessing

import numpy as np
from fontTools.fontBuilder import FontBuilder
from fontTools.otlLib.builder import buildStatTable
from fontTools.ttLib import TTCollection, TTFont, newTable
from fontTools.ttLib.scaleUpem import ScalerVisitor
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables._g_v_a_r import compileGlyph_
from fontTools.varLib.builder import buildVarIdxMap
from fontTools.varLib.varStore import OnlineVarStoreBuilder
from fontTools.varLib.models import supportScalar

from batch_geometry import BatchGeometry
from hvf import HVGL
from source_metrics import SourceMetrics
from target_axis_mapping import axes_from_font, source_axis_plan
from ttc_staging_pack import pack_collection
from windows_font_inventory import sha256
from windows_gvar import TensorModel, TAGS, LIMIT, compile_glyph, observed_errors, require

SOURCE_SHA = '39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890'
FACE_PLAN = ((0, 'SC Text'), (5, 'SC Display'), (1, 'TC Text'), (6, 'TC Display'))
SAMPLE_TEXT = '中文简体繁體漢字龍鬱龜测试測試字体字體永國国你好世界，。！？：；、（）「」—… ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
VERSION = '0.1.0 Alpha'


def bounded_map(executor, function, items, window):
    """Ordered writes, at most window pending glyphs; worker exceptions survive."""
    items = iter(items)
    pending = deque()
    for _ in range(window):
        try:
            pending.append(executor.submit(function, next(items)))
        except StopIteration:
            break
    while pending:
        yield pending.popleft().result()
        try:
            pending.append(executor.submit(function, next(items)))
        except StopIteration:
            pass


def initialize_worker(source_path, face_index, multiplier, dense, adaptive, holdouts, optimize, quantization='vertices'):
    global WORKER
    WORKER = GlyphCompiler(source_path, face_index, multiplier, dense, adaptive, holdouts, optimize, quantization)


def worker_glyph(gid):
    return WORKER.compile(gid)


class GlyphCompiler:
    def __init__(self, source_path, face_index, multiplier, dense, adaptive, count, optimize, quantization='vertices'):
        self.source = TTFont(source_path, fontNumber=face_index, lazy=True)
        self.renderer = BatchGeometry(HVGL(self.source.reader['hvgl']), isolated_tangents=True)
        self.metrics = SourceMetrics(self.source)
        self.multiplier, self.optimize, self.adaptive = multiplier, optimize, adaptive
        self.quantization = quantization
        self.holdouts = np.floor(np.random.default_rng(2026110317).uniform(-1, 1, (count, 3))*16384+.5)/16384
        self.hq = source_locations(self.source, self.holdouts)
        self.plans = []
        for use_dense in ([True] if dense else [False, True] if adaptive else [False]):
            model = weight_grid(self.source, use_dense)
            weights = np.asarray([[supportScalar(dict(zip(TAGS, p)), s)
                                   for s in model.supports] for p in self.holdouts])
            self.plans.append((model, source_locations(self.source, model.locations), weights))

    def compile(self, gid):
        tick = time.monotonic()
        controls, _, _ = source_vectors(self.renderer, self.metrics, gid, self.hq, self.multiplier)
        previous = []
        best = None
        for model, q, weights in self.plans:
            values, flags, ends = source_vectors(self.renderer, self.metrics, gid, q, self.multiplier)
            glyph, tuples, horizontal, vertical, coefficients, row = compile_glyph(model, values, flags, ends, optimize=self.optimize, quantization=self.quantization)
            errors = observed_errors(np.tensordot(weights, coefficients, axes=(1, 0))/self.multiplier,
                                     controls/self.multiplier)
            default = model.indices.index(model.zero)
            default_error = float(np.linalg.norm((coefficients[default]-values[default])[:-4], axis=-1).max(initial=0))/self.multiplier
            error = max(errors['max_outline_control_bound'], default_error)
            row.update(gid=gid, **errors, default_quantization_bound=default_error,
                       empty_source_outline=not flags, holdouts=len(self.holdouts),
                       refinement_history=list(previous),
                       quality='sampled_high_precision' if error <= LIMIT else
                               'basic_geometry_samples' if error <= 2 else 'geometry_difference')
            if best is None or error < best[0]:
                best = (error, model, glyph, tuples, horizontal, vertical, coefficients, row, flags, ends)
            if error <= 2:
                break
            previous.append(dict(grid_vertices=len(q), error=error))
        _, model, glyph, tuples, horizontal, vertical, coefficients, row, flags, ends = best
        row['evaluated_grids'] = list(previous)
        metrics = {}
        for kind, values_ in [('HVAR', coefficients[:, -3, 0]-coefficients[:, -4, 0]),
                              ('VVAR', coefficients[:, -2, 1]-coefficients[:, -1, 1])]:
            selected = [i for i, s in enumerate(model.supports) if s and values_[i]]
            metrics[kind] = ([model.supports[i] for i in selected], [int(values_[i]) for i in selected])
        glyf_data = glyph.compile(None)
        gvar_data = compileGlyph_(2, tuples, len(flags)+4, TAGS, {}, optimizeSize=True)
        row.update(seconds=time.monotonic()-tick, glyf_bytes=len(glyf_data), gvar_bytes=len(gvar_data),
                   worker_peak_rss_bytes=peak_rss())
        bounds = tuple(getattr(glyph, k, 0) for k in ('xMin', 'yMin', 'xMax', 'yMax'))
        return glyf_data, gvar_data, horizontal, vertical, metrics, bounds, len(flags), len(ends), row


def weight_grid(font, dense=False):
    return TensorModel(np.linspace(-1, 1, 5 if dense else 3))


def source_locations(font, locations):
    """Map target post-avar design space to the actual source q interval.

    Source avar's repeated endpoint records do not reach q=-1/+1 at user
    min/max. Rebase that reachable interval, rather than discarding those
    records or writing an invalid avar. The output avar performs the inverse.
    """
    axes = axes_from_font(font)
    low = np.asarray([source_axis_plan(a, a.minimum)['source_q']/16384 for a in axes])
    high = np.asarray([source_axis_plan(a, a.maximum)['source_q']/16384 for a in axes])
    require(np.all(low < 0) and np.all(high > 0)
            and all(source_axis_plan(a, a.default)['source_q'] == 0 for a in axes), 'source_q_rebase_contract')
    p = np.asarray(locations)
    return p*np.where(p < 0, -low, high)


def rebased_avar(source):
    table = newTable('avar')
    table.majorVersion, table.minorVersion = 1, 0
    table.segments = {}
    for tag, axis in zip(TAGS, axes_from_font(source)):
        low = source_axis_plan(axis, axis.minimum)['source_q']
        high = source_axis_plan(axis, axis.maximum)['source_q']
        points = []
        for n in range(-16384, 16385):
            user = axis.default+n/16384*(axis.default-axis.minimum if n < 0 else axis.maximum-axis.default)
            q = source_axis_plan(axis, user)['source_q']
            r = int(np.floor(q/(-low if q < 0 else high)*16384+.5))
            points.append((n, r))
        require(points[0] == (-16384, -16384) and points[16384] == (0, 0)
                and points[-1] == (16384, 16384)
                and all(a[1] <= b[1] for a, b in zip(points, points[1:])), 'legal_rebased_avar_required')
        # Bound the finite F2DOT14 mapping error to one target grid step. Exact
        # stair-step preservation costs ~20,000 records without improving the
        # Alpha's geometry. Retain endpoints/default and recursively the worst
        # vertical residual (independent implementation, not copied RDP code).
        values = np.asarray(points, dtype=float)
        keep = {0, 16384, 32768}
        pending = [(0, 16384), (16384, 32768)]
        while pending:
            a, b = pending.pop()
            if b-a < 2:
                continue
            predicted = values[a, 1]+(values[b, 1]-values[a, 1])*np.arange(b-a+1)/(b-a)
            error = np.abs(predicted-values[a:b+1, 1])
            i = a+int(np.argmax(error))
            if error[i-a] > 1:
                keep.add(i)
                pending.extend(((a, i), (i, b)))
        table.segments[tag] = {points[i][0]/16384: points[i][1]/16384 for i in sorted(keep)}
    return table


def source_vectors(renderer, metrics, gid, q, multiplier):
    parts, flags, ends, count = [], [], [], 0
    for start in range(0, len(q), 256):
        batch = renderer.render(gid, q[start:start+256, :renderer.table.part(gid).axis_count])
        points = np.concatenate(batch.paths, axis=1) if batch.paths else np.empty((batch.sample_count, 0, 2))
        if start == 0:
            for p in batch.paths:
                flags.extend([1, 0]*(p.shape[1]//2))
                count += p.shape[1]
                ends.append(count-1)
        require(points.shape[1] == len(flags), 'source_topology_changed')
        phantoms = []
        for loc in q[start:start+256]:
            m = metrics.at(gid, dict(zip(('WDTH', 'wght', 'HGHT'), loc)))
            phantoms.append([(0., 0.), (m['advance_width'], 0.),
                             (0., m['vertical_origin_y']), (0., m['vertical_origin_y']-m['advance_height'])])
        parts.append(np.concatenate((points, np.asarray(phantoms)), axis=1)*multiplier)
    return np.concatenate(parts), flags, ends


def naming(font, source, label, version):
    builder = FontBuilder(font=font)
    family = 'SwirlVF '+label
    builder.setupNameTable(dict(familyName=family, styleName='Regular',
        typographicFamily=family, typographicSubfamily='Regular',
        uniqueFontIdentifier=family+';'+version, fullName=family,
        psName=family.replace(' ', '')+'-Regular', version='Version '+version,
        copyright='Private research conversion; underlying source font rights remain with its owner.'))
    original_axes = source['fvar'].axes
    axes = [(tag, *( (80, 100, 120) if tag == 'wdth' else
             (a.minValue, a.defaultValue, a.maxValue)), {'wdth': 'Width', 'wght': 'Weight', 'HGHT': 'Height'}[tag])
            for tag, a in zip(TAGS, original_axes)]
    instances = []
    required = {'Light', 'Regular', 'Medium', 'Semibold', 'Bold'}
    weights = {}
    for instance in source['fvar'].instances:
        name = source['name'].getDebugName(instance.subfamilyNameID).split()[0]
        if name in required:
            coordinates = dict(instance.coordinates)
            coordinates['wdth'] = 100.
            del coordinates['WDTH']
            weights[name] = coordinates['wght']
            instances.append(dict(location=coordinates, stylename=name))
    require(set(weights) == required, 'five_source_named_weights_required')
    builder.setupFvar(axes, instances)
    font['avar'] = rebased_avar(source)
    buildStatTable(font, [dict(tag=tag, name=title, ordering=i,
        values=[dict(value=v, name=n, flags=2 if n == 'Regular' else 0) for n, v in weights.items()] if tag == 'wght'
        else [dict(value=default, name='Normal', flags=2)])
        for i, (tag, low, default, high, title) in enumerate(axes)], elidedFallbackName='Regular')
    font['OS/2'].usWeightClass = int(original_axes[1].defaultValue)
    font['OS/2'].usWidthClass = 5
    font['OS/2'].fsSelection = (font['OS/2'].fsSelection & ~(1 | 32)) | 64
    font['head'].macStyle &= ~3
    return font


def raw_table(tag, data):
    table = DefaultTable(tag)
    table.data = data
    return table


def make_font(source, label, order, glyf_data, gvar_data, offsets, hm, vm, stores,
              metric_indices, bounds, max_points, max_contours, extrema, multiplier, full):
    font = TTFont(recalcBBoxes=False, recalcTimestamp=False)
    font.setGlyphOrder(order)
    preserve = ['head', 'hhea', 'vhea', 'OS/2', 'post']
    if full:
        preserve += [t for t in ('cmap', 'GSUB', 'GPOS', 'GDEF', 'BASE') if t in source]
    for tag in preserve:
        font[tag] = copy.deepcopy(source[tag])
        if tag != 'cmap' and tag != 'GSUB':
            ScalerVisitor(multiplier).visit(font[tag])
    font['head'].flags |= 2
    font['head'].indexToLocFormat = 1
    font['head'].xMin, font['head'].yMin, font['head'].xMax, font['head'].yMax = bounds
    font['glyf'] = raw_table('glyf', glyf_data)
    font['loca'] = raw_table('loca', struct.pack('>'+str(len(offsets))+'I', *offsets))
    font['gvar'] = raw_table('gvar', gvar_data)
    for tag, data in [('hmtx', hm), ('vmtx', vm)]:
        font[tag] = newTable(tag)
        # post format 3 reconstructs different names from SC and TC cmaps.
        # Shared binary outlines retain GID identity, never glyph-name identity.
        font[tag].metrics = dict(zip(order, data.values()))
    maxp = newTable('maxp')
    maxp.tableVersion, maxp.numGlyphs = 0x10000, len(order)
    for key in ('maxCompositePoints', 'maxCompositeContours', 'maxTwilightPoints', 'maxStorage',
                'maxFunctionDefs', 'maxInstructionDefs', 'maxStackElements', 'maxSizeOfInstructions',
                'maxComponentElements', 'maxComponentDepth'):
        setattr(maxp, key, 0)
    maxp.maxPoints, maxp.maxContours, maxp.maxZones = max_points, max_contours, 1
    font['maxp'] = maxp
    if not full:
        chosen = set(order)
        FontBuilder(font=font).setupCharacterMap({cp: n for cp, n in source.getBestCmap().items() if n in chosen})
    for kind in ('HVAR', 'VVAR'):
        wrapper = newTable(kind)
        table = getattr(otTables, kind)()
        table.Version, table.VarStore = 0x10000, stores[kind].finish()
        setattr(table, 'AdvWidthMap' if kind == 'HVAR' else 'AdvHeightMap',
                buildVarIdxMap(metric_indices[kind], order))
        for field in (('LsbMap', 'RsbMap') if kind == 'HVAR' else ('TsbMap', 'BsbMap', 'VOrgMap')):
            setattr(table, field, None)
        wrapper.table = table
        font[kind] = wrapper
    # All source bearings/extents are invalid after geometry quantization.
    for tag, metrics in [('hhea', hm), ('vhea', vm)]:
        header = font[tag]
        if tag == 'hhea':
            header.advanceWidthMax = max(v[0] for v in metrics.values())
        else:
            header.advanceHeightMax = max(v[0] for v in metrics.values())
    for key, value in extrema.items():
        setattr(font['hhea'] if key in ('minLeftSideBearing', 'minRightSideBearing', 'xMaxExtent') else font['vhea'], key, value)
    font['gasp'] = newTable('gasp')
    font['gasp'].gaspRange = {65535: 15}
    return naming(font, source, label, '0.1.0 '+('Beta' if full else 'Alpha'))


def build(args):
    output = args.output.resolve()
    repo = Path(__file__).resolve().parents[3]
    require(not output.exists() and not output.is_relative_to(repo)
            and not any((parent/'.git').exists() for parent in (output, *output.parents)),
            'fresh_output_outside_git_required')
    require(sha256(args.source) == SOURCE_SHA, 'exact_source_sha256_required')
    output.mkdir(parents=True, mode=0o700)
    started = time.monotonic()
    report = dict(version='0.1.0 '+('Beta' if args.full else 'Alpha'), source_sha256=SOURCE_SHA,
        full_glyph_coverage=args.full, source_user_mapping='RETAINED_A3_HYPOTHESIS_REBASED_LEGAL_AVAR1',
        source_avar_discontinuities='CONTINUOUS_APPROXIMATION_REQUIRES_VISUAL_REVIEW',
        precision_target=LIMIT, basic_geometry_screen_source_units=2., visual_acceptance='NOT_RUN', workers=args.workers, adaptive=args.adaptive, quantization=args.quantization, faces=[],
        Windows_DirectWrite='NOT_RUN', Windows_installation='NOT_RUN', desktop_visual='NOT_RUN',
        production_accepted=False, source_vertical_origin_x='NOT_PRESERVED_BY_VMTX',
        AAT_tracking='NOT_CONVERTED', hinting='UNHINTED', independent_native_source='NOT_RUN')
    (output/'report.json').write_text(json.dumps(report, indent=2))
    paths, reports, assets = {}, {}, {}
    with TTCollection(args.source, lazy=True) as original:
        table = HVGL(original.fonts[0].reader['hvgl'])
        renderer = BatchGeometry(table, isolated_tangents=True)
        if args.full:
            gids = list(range(original.fonts[0]['maxp'].numGlyphs))
        else:
            gids = {0, 1166, 19177}
            for fi in (0, 1):
                f = original.fonts[fi]
                cmap = f.getBestCmap()
                gids.update(f.getGlyphID(cmap[ord(c)]) for c in SAMPLE_TEXT if ord(c) in cmap)
            gids = sorted(gids)
        report['source_gids'] = gids
        for face_index, label in FACE_PLAN:
            source = original.fonts[face_index]
            require(source['name'].getDebugName(6) == '.PingFangUI'+('Text' if 'Text' in label else 'Display')+label[:2]+'-Default',
                    'source_face_identity_mismatch')
            style = label.split()[1]
            order = [source.getGlyphOrder()[gid] for gid in gids]
            if style not in assets:
                stores = {kind: OnlineVarStoreBuilder(TAGS) for kind in ('HVAR', 'VVAR')}
                indices = {kind: [] for kind in stores}
                hm, vm, offsets, g_offsets = {}, {}, [0], [0]
                bounds, max_points, max_contours = [32767, 32767, -32768, -32768], 0, 0
                extrema = dict(minLeftSideBearing=32767, minRightSideBearing=32767, xMaxExtent=-32768,
                               minTopSideBearing=32767, minBottomSideBearing=32767, yMaxExtent=-32768)
                rows, counters = [], Counter()
                glyf_path, gvar_path = output/(style+'.glyf.private'), output/(style+'.gvar.private')
                worker_args = (str(args.source), face_index, args.multiplier, args.dense, args.adaptive,
                               args.holdouts, not args.no_iup, args.quantization)
                pool = None
                if args.workers == 1:
                    compiler = GlyphCompiler(*worker_args)
                    results = map(compiler.compile, gids)
                else:
                    pool = ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context('spawn'),
                                               initializer=initialize_worker, initargs=worker_args)
                    results = bounded_map(pool, worker_glyph, gids, args.workers*2)
                try:
                    with glyf_path.open('xb') as gf, gvar_path.open('xb') as gv, (output/(style+'-progress.jsonl')).open('x') as progress:
                        for number, (name, result) in enumerate(zip(order, results)):
                            glyph_data, encoded, horizontal, vertical, variation_metrics, box, points, contours, row = result
                            counters[row['quality']] += 1
                            counters['tuples'] += row['tuples']
                            counters['refined_glyphs'] += bool(row['refinement_history'])
                            if points:
                                bounds = [min(bounds[0], box[0]), min(bounds[1], box[1]), max(bounds[2], box[2]), max(bounds[3], box[3])]
                                width, height = box[2]-box[0], box[3]-box[1]
                                lsb, tsb = horizontal[1], vertical[1]
                                for key, value in [('minLeftSideBearing', lsb), ('minRightSideBearing', horizontal[0]-lsb-width),
                                                   ('minTopSideBearing', tsb), ('minBottomSideBearing', vertical[0]-tsb-height)]:
                                    extrema[key] = min(extrema[key], value)
                                extrema['xMaxExtent'] = max(extrema['xMaxExtent'], lsb+width)
                                extrema['yMaxExtent'] = max(extrema['yMaxExtent'], tsb+height)
                            max_points, max_contours = max(max_points, points), max(max_contours, contours)
                            gf.write(glyph_data); offsets.append(gf.tell())
                            gv.write(encoded); g_offsets.append(gv.tell())
                            hm[name], vm[name] = horizontal, vertical
                            for kind, (supports, deltas) in variation_metrics.items():
                                stores[kind].setSupports(supports)
                                indices[kind].append(stores[kind].storeDeltas(deltas))
                            rows.append(row)
                            progress.write(json.dumps(row)+'\n')
                            if number % 100 == 0 or number+1 == len(gids):
                                progress.flush()
                                print(json.dumps(dict(style=style, completed=number+1, total=len(gids), seconds=time.monotonic()-started,
                                                      glyphs_per_second=(number+1)/(time.monotonic()-started), counts=counters)), flush=True)
                finally:
                    if pool:
                        pool.shutdown(wait=True, cancel_futures=True)
                header_size = 20+4*len(g_offsets)
                gvar_data = struct.pack('>HHHHIHHI', 1, 0, 3, 0, header_size, len(order), 1, header_size)
                gvar_data += struct.pack('>'+str(len(g_offsets))+'I', *g_offsets)+gvar_path.read_bytes()
                assets[style] = (glyf_path.read_bytes(), gvar_data, offsets, hm, vm, stores, indices, bounds, max_points, max_contours, extrema)
                reports[style] = dict(glyphs=len(order), grid_vertices=sorted(set(r["grid_vertices"] for r in rows)), counts=counters, results=rows)
                (output/(style+'-glyph-report.json')).write_text(json.dumps(reports[style], indent=2))
            font = make_font(source, label, order, *assets[style], args.multiplier, args.full)
            path = output/(label.replace(' ', '-')+'.ttf')
            font.save(path)
            paths[label] = path
            with TTFont(path, lazy=True) as reopened:
                require(reopened['maxp'].numGlyphs == len(gids) and 'glyf' in reopened and 'gvar' in reopened
                        and 'hvgl' not in reopened and 'CFF2' not in reopened and reopened['avar'].majorVersion == 1,
                        'serialized_font_contract_failed')
                face_report = dict(face=label, source_face=face_index, glyphs=len(gids),
                                   cmap_codepoints=len(reopened.getBestCmap()), bytes=path.stat().st_size,
                                   sha256=sha256(path), units_per_em=reopened['head'].unitsPerEm,
                                   instances=[reopened['name'].getDebugName(x.subfamilyNameID) for x in reopened['fvar'].instances])
            report['faces'].append(face_report)
        # The user explicitly requests the test delivery filename SwirlVF.ttc.
        # Use the unchanged integrity packer, then verify the labelled Alpha/Beta
        # copy. This filename does not confer the research/release acceptance gate.
        staging = output/'SwirlVF-test.ttc'
        packed = pack_collection([paths[label] for _, label in FACE_PLAN], staging)
        final = output/'SwirlVF.ttc'
        with final.open('xb') as stream:
            with staging.open('rb') as src:
                while block := src.read(1024*1024):
                    stream.write(block)
        require(sha256(final) == sha256(staging), 'test_delivery_copy_mismatch')
        report.update(file=final.name, sha256=sha256(final), bytes=final.stat().st_size,
            seconds=time.monotonic()-started, peak_rss_bytes=peak_rss(),
            packaging=packed, quality={k: v['counts'] for k, v in reports.items()},
            source_sha256_after=sha256(args.source))
        require(report['source_sha256_after'] == SOURCE_SHA, 'source_changed_during_build')
    (output/'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ('version', 'file', 'bytes', 'sha256', 'seconds', 'quality')}), flush=True)
    return report


def peak_rss():
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform == 'darwin' else 1024)
    except ImportError:
        return None


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--full', action='store_true')
    p.add_argument('--dense', action='store_true')
    p.add_argument('--adaptive', action='store_true', help='refine failed coarse geometry samples to a 5 by 5 by 5 grid')
    p.add_argument('--workers', type=int, default=1)
    p.add_argument('--quantization', choices=('vertices', 'coefficients'), default='vertices')
    p.add_argument('--no-iup', action='store_true')
    p.add_argument('--multiplier', type=int, default=15)
    p.add_argument('--holdouts', type=int, default=16)
    args = p.parse_args()
    require(1 <= args.multiplier <= 15 and 1 <= args.holdouts <= 1024 and 1 <= args.workers <= 8, 'invalid_precision_or_sample_count')
    build(args)
