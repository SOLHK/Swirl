#!/usr/bin/env python3
"""Conditional capacity bounds, not a file-size extrapolation or format theorem."""
import argparse,json
from pathlib import Path


def capacity(total_glyphs,nonempty_glyphs,minimum_cells=8):
    if not (type(total_glyphs) is type(nonempty_glyphs) is type(minimum_cells) is int
            and 0<=nonempty_glyphs<=total_glyphs<=65535 and minimum_cells>=1):
        raise ValueError('invalid_capacity_population')
    lower=total_glyphs-nonempty_glyphs+nonempty_glyphs*minimum_cells
    retained=total_glyphs+nonempty_glyphs*minimum_cells
    return dict(total_source_glyphs=total_glyphs,nonempty_source_glyphs=nonempty_glyphs,
        minimum_cells_per_nonempty_glyph=minimum_cells,maxp_numGlyphs_limit=65535,
        aliasing_base_to_one_patch_glyph_lower_bound=lower,
        retaining_original_base_plus_all_patches_glyph_count=retained,
        capacity_fits_even_with_base_aliasing=lower<=65535,
        assumptions=['Current compiler starts with eight octants and emits one distinct glyph per cell.',
                     'Every nonempty source glyph is retained; no cross-source glyph aliasing is assumed.'],
        conclusion_scope='Current patch-per-glyph architecture only; other OpenType representations are not ruled out.',
        projected_full_font_bytes=None,projected_full_font_compile_seconds=None)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--selection',type=Path,required=True)
    a=p.parse_args();d=json.loads(a.selection.read_text())
    print(json.dumps(capacity(d['faces'][0]['glyphs'],d['eligible_root_glyphs']),indent=2))
