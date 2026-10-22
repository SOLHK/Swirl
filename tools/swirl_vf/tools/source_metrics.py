"""Evaluate unhinted source metrics without replacing native observations.

The caller supplies already verified normalized design coordinates. This module
does not normalize user axes, interpret avar, round coordinates, modify the font,
or claim that CoreText returned its values. In particular, native integer
vertical advances and missing blank-glyph origins remain separate evidence.

The returned vertical_origin_x is the standard DirectWrite convention, the
horizontal origin plus half the current advance width. Neither vmtx nor VORG
stores this x coordinate; VORG supplies y only. Native measurements of the
original HVGL font have rejected the assumption that CoreText always returns
this x value. For HVGL it remains a standard-platform reference, never an
accepted native-origin model or authorization for conversion.

References: OpenType hmtx, vmtx, HVAR, VVAR, VORG, and gvar specifications;
fontTools' VarStoreInstancer and supportScalar are used through their public APIs.
https://learn.microsoft.com/en-us/typography/opentype/spec/vmtx
https://learn.microsoft.com/en-us/windows/win32/api/dwrite/ns-dwrite-dwrite_glyph_metrics
"""
from __future__ import annotations

import math

from fontTools.varLib.models import supportScalar
from fontTools.varLib.varStore import VarStoreInstancer
from fontTools.varLib.iup import iup_delta
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates


class SourceMetricError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise SourceMetricError(message)


class SourceMetrics:
    """Exact table evaluation in a specified design space, not a native oracle.

    Supported source outlines are standard TrueType (including empty glyphs)
    and Apple's HVGL with explicit VORG. TrueType composite USE_MY_METRICS is
    rejected: a future implementation must evaluate its component semantics.
    No unsupported outline is assigned an invented origin.
    """

    def __init__(self, font):
        self.font = font
        require(all(tag in font for tag in ('hmtx', 'vmtx', 'head', 'maxp')),
                'source needs explicit horizontal and vertical metrics')
        self.names = font.getGlyphOrder()
        self.axes = list(font['fvar'].axes) if 'fvar' in font else []
        self.tags = tuple(a.axisTag for a in self.axes)
        require(len(self.tags) == len(set(self.tags)), 'duplicate source axis')
        require('glyf' in font or ('hvgl' in font and 'VORG' in font),
                'source outline needs a supported explicit origin')
        if 'VORG' in font:
            table = font['VORG']
            require((table.majorVersion, table.minorVersion) == (1, 0),
                    'unsupported VORG version')
        self._bases = {}
        self._locations = {}

    def _base(self, gid):
        require(type(gid) is int and 0 <= gid < len(self.names), 'source GID out of range')
        if gid in self._bases:
            return self._bases[gid]
        name = self.names[gid]
        width, left_bearing = self.font['hmtx'].metrics[name]
        height, top_bearing = self.font['vmtx'].metrics[name]
        if 'glyf' in self.font:
            glyph = self.font['glyf'][name]
            if glyph.isComposite():
                require(not any(component.flags & 0x0200 for component in glyph.components),
                        'composite USE_MY_METRICS needs component evaluation')
            # SFNT glyf bounds are control-point bounds, not curve extrema.
            x_min = getattr(glyph, 'xMin', 0)
            y_max = getattr(glyph, 'yMax', 0)
            origin_x = x_min - left_bearing
            origin_y = y_max + top_bearing
            origin_basis = 'glyf_control_yMax_plus_vmtx_tsb_and_gvar_top_phantom'
        else:
            # HVGL native paths have the original horizontal origin at zero;
            # hmtx.lsb is not a substitute for the actual native curve bound.
            origin_x = 0
            origin_y = self.font['VORG'][name]
            origin_basis = 'source_VORG'
        require(all(isinstance(v, (int, float)) and math.isfinite(v) for v in
                    (width, height, origin_x, origin_y)), 'nonfinite source base metric')
        require(width >= 0 and height >= 0, 'negative source advance')
        base = (name, float(width), float(height), float(origin_x), float(origin_y), origin_basis)
        self._bases[gid] = base
        return base

    def _location(self, coordinates):
        require(set(coordinates) == set(self.tags),
                'explicit normalized coordinates required for every source axis')
        require(all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(v) and -1 <= v <= 1 for v in coordinates.values()),
                'normalized source coordinate out of range or nonfinite')
        key = tuple(coordinates[tag] for tag in self.tags)
        if key not in self._locations:
            stores = {}
            for tag in ('HVAR', 'VVAR'):
                if tag in self.font:
                    table = self.font[tag].table
                    require(table.Version == 0x00010000, f'unsupported {tag} version')
                    require(table.VarStore.VarRegionList.RegionAxisCount == len(self.tags),
                            f'{tag} axis count differs from fvar')
                    stores[tag] = VarStoreInstancer(table.VarStore, self.axes, coordinates)
            self._locations[key] = stores
        return self._locations[key]

    def _delta(self, stores, tag, field, gid, name):
        table = self.font[tag].table
        mapping = getattr(table, field)
        # A missing advance map means implicit outer=0 / inner=GID indexing;
        # a missing optional bearing/origin map means no explicit delta.
        if mapping is None:
            if field not in ('AdvWidthMap', 'AdvHeightMap'):
                return None
            index = gid
        else:
            require(name in mapping.mapping, f'{tag}.{field} missing source glyph')
            index = mapping.mapping[name]
        value = float(stores[tag][index])
        require(math.isfinite(value), f'nonfinite {tag}.{field} delta')
        return value

    def _control_extrema(self, name, coordinates):
        glyph = self.font['glyf'][name]
        require(not glyph.isComposite(), 'composite bearing maps need component bounds')
        points, control = self.font['glyf']._getCoordinatesAndControls(
            name, self.font['hmtx'].metrics, self.font['vmtx'].metrics)
        original = points.copy()
        for variation in (self.font['gvar'].variations.get(name, []) if 'gvar' in self.font else []):
            scalar = supportScalar(coordinates, variation.axes)
            if not scalar:
                continue
            deltas = variation.coordinates
            require(len(deltas) == len(points), 'gvar point count differs from source glyph')
            if None in deltas:
                deltas = iup_delta(deltas, original, control.endPts)
            points += GlyphCoordinates(deltas) * scalar
        outline = points[:-4]
        return min((x for x, _ in outline), default=0.), max((y for _, y in outline), default=0.)

    def at(self, gid, normalized_coordinates):
        name, width, height, origin_x, origin_y, basis = self._base(gid)
        stores = self._location(normalized_coordinates)
        phantoms = [[0., 0.] for _ in range(4)]
        if 'gvar' in self.font:
            for variation in self.font['gvar'].variations.get(name, []):
                require(len(variation.coordinates) >= 4, 'gvar phantom data truncated')
                require(set(variation.axes) <= set(self.tags), 'gvar support uses unknown axis')
                scalar = supportScalar(normalized_coordinates, variation.axes)
                # Unreferenced phantom points have zero deltas; contour IUP
                # must never interpolate a phantom from adjacent outline points.
                for index, pair in enumerate(variation.coordinates[-4:]):
                    if pair is None:
                        continue
                    require(len(pair) == 2 and all(isinstance(v, (int, float))
                            and math.isfinite(v) for v in pair), 'invalid gvar phantom delta')
                    for axis in range(2):
                        phantoms[index][axis] += scalar * pair[axis]
        origin_x += phantoms[0][0]
        origin_y += phantoms[2][1]
        width += (self._delta(stores, 'HVAR', 'AdvWidthMap', gid, name) if 'HVAR' in stores
                  else phantoms[1][0] - phantoms[0][0])
        height += (self._delta(stores, 'VVAR', 'AdvHeightMap', gid, name) if 'VVAR' in stores
                   else phantoms[2][1] - phantoms[3][1])
        lsb_delta = (self._delta(stores, 'HVAR', 'LsbMap', gid, name)
                     if 'HVAR' in stores else None)
        tsb_delta = (self._delta(stores, 'VVAR', 'TsbMap', gid, name)
                     if 'VVAR' in stores else None)
        if lsb_delta is not None or tsb_delta is not None:
            require('glyf' in self.font, 'non-TrueType bearing map needs native control extrema')
            x_min, y_max = self._control_extrema(name, normalized_coordinates)
            if lsb_delta is not None:
                origin_x = x_min - self.font['hmtx'].metrics[name][1] - lsb_delta
            if tsb_delta is not None:
                origin_y = y_max + self.font['vmtx'].metrics[name][1] + tsb_delta
                basis = 'varied_glyf_control_yMax_plus_vmtx_tsb_and_VVAR_TsbMap'
        if 'VVAR' in stores and self.font['VVAR'].table.VOrgMap is not None:
            require('glyf' not in self.font and 'VORG' in self.font,
                    'VVAR VOrgMap requires a VORG outline source')
            origin_y += self._delta(stores, 'VVAR', 'VOrgMap', gid, name)
        require(width >= 0 and height >= 0, 'negative varied source advance')
        return {'advance_width': width, 'advance_height': height,
                'horizontal_origin_x': origin_x, 'horizontal_origin_y': 0.,
                'vertical_origin_x': origin_x + width / 2, 'vertical_origin_y': origin_y,
                'metric_source': 'unhinted_standard_source_tables_not_CoreText_API',
                'vertical_origin_x_basis': 'DirectWrite_horizontal_origin_plus_half_current_advance_not_stored_in_VORG',
                'vertical_origin_x_is_native_observation': False,
                'native_HVGL_vertical_origin_x_acceptance': 'NOT_ESTABLISHED',
                # This basis describes the y component only; x uses the
                # separately labelled standard-platform reference above.
                'vertical_origin_basis': basis,
                'normalized_design_location': dict(normalized_coordinates)}
