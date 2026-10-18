"""Generate tiny original fonts for local metadata tests; never read user fonts."""
import sys
from pathlib import Path
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import newTable
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
for name,limits in [('static',None),('variable',(1,500,1000)),('range',(100,300,600))]:
 b=FontBuilder(1000,isTTF=True);b.setupGlyphOrder(['.notdef','A']);b.setupCharacterMap({65:'A'})
 pen=TTGlyphPen(None);pen.moveTo((100,0));pen.lineTo((300,700));pen.lineTo((500,0));pen.closePath();glyph=pen.glyph()
 b.setupGlyf({'.notdef':TTGlyphPen(None).glyph(),'A':glyph});b.setupHorizontalMetrics({'.notdef':(600,0),'A':(600,100)})
 b.setupHorizontalHeader(ascent=800,descent=-200);b.setupNameTable({'familyName':'Swirl Metadata Probe','styleName':'Regular','uniqueFontIdentifier':'SwirlMetadataProbe-'+name,'fullName':'Swirl Metadata Probe Regular','psName':'SwirlMetadataProbe-Regular','version':'Version 1.0'})
 b.setupOS2(sTypoAscender=800,sTypoDescender=-200,usWinAscent=800,usWinDescent=200);b.setupPost();b.setupMaxp()
 if limits:
  b.setupFvar([('HGHT',*limits,'Height')],[]);g=newTable('gvar');g.version=1;g.reserved=0;g.variations={'.notdef':[],'A':[]};b.font['gvar']=g
 b.save(out/(name+'.ttf'))
print('Generated original tiny static/variable/range fixtures at',out)

# Independent original CFF/OpenType fixture: no external outlines or font bytes.
from fontTools.pens.t2CharStringPen import T2CharStringPen
b=FontBuilder(1000,isTTF=False);b.setupGlyphOrder(['.notdef','A']);b.setupCharacterMap({65:'A'})
chars={}
for name in ['.notdef','A']:
 pen=T2CharStringPen(600,None)
 if name=='A':
  pen.moveTo((100,0));pen.lineTo((300,700));pen.lineTo((500,0));pen.closePath()
 chars[name]=pen.getCharString()
b.setupHorizontalMetrics({'.notdef':(600,0),'A':(600,100)});b.setupHorizontalHeader(ascent=800,descent=-200)
b.setupNameTable({'familyName':'Swirl CFF Probe','styleName':'Regular','uniqueFontIdentifier':'SwirlCFFProbe','fullName':'Swirl CFF Probe Regular','psName':'SwirlCFFProbe-Regular','version':'Version 1.0'})
b.setupOS2(sTypoAscender=800,sTypoDescender=-200,usWinAscent=800,usWinDescent=200);b.setupPost()
b.setupCFF('SwirlCFFProbe-Regular',{'FullName':'Swirl CFF Probe Regular','FamilyName':'Swirl CFF Probe','Weight':'Regular'},chars,{})
b.save(out/'cff.otf')

# Public, original automation fixtures. These have actual gvar outline deltas,
# not just fvar declarations. They exercise routing and axis application; the
# shapes do not establish the visual quality of any user's production font.
from fontTools.ttLib.tables.TupleVariation import TupleVariation


def automation_font(filename, family, axes):
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(['.notdef', 'A'])
    builder.setupCharacterMap({65: 'A'})
    # An original angular A, drawn here rather than copied from a typeface.
    # The counter runs opposite to the outer contour and all metrics are fixed.
    points = [(80, 0), (270, 720), (390, 720), (580, 0),
              (440, 0), (400, 180), (260, 180), (220, 0),
              (285, 300), (375, 300), (330, 510)]
    pen = TTGlyphPen(None)
    for start, end in [(0, 8), (8, 11)]:
        pen.moveTo(points[start])
        for point in points[start + 1:end]:
            pen.lineTo(point)
        pen.closePath()
    builder.setupGlyf({'.notdef': TTGlyphPen(None).glyph(), 'A': pen.glyph()})
    builder.setupHorizontalMetrics({'.notdef': (660, 0), 'A': (660, 80)})
    builder.setupHorizontalHeader(ascent=900, descent=-200)
    postscript = family.replace(' ', '') + '-Regular'
    builder.setupNameTable({
        'familyName': family, 'styleName': 'Regular',
        'uniqueFontIdentifier': postscript + '-1.0',
        'fullName': family + ' Regular', 'psName': postscript,
        'version': 'Version 1.0',
        'copyright': 'Original Swirl test geometry; distributed under the repository license.'})
    builder.setupOS2(sTypoAscender=900, sTypoDescender=-200,
                     usWinAscent=1000, usWinDescent=200,
                     usWeightClass=int(axes[0][2]))
    builder.setupPost()
    builder.setupMaxp()
    builder.setupFvar(axes, [])

    weight = [(-30, 0), (-20, 0), (20, 0), (30, 0), (-30, 0),
              (-25, 0), (25, 0), (30, 0), (15, 25), (-15, 25), (0, -40)]
    optical = [(10, 0), (35, 0), (-35, 0), (-10, 0), (0, 0),
               (0, 10), (0, 10), (0, 0), (-10, 10), (10, 10), (0, 80)]
    deltas = {
        'wght': weight,
        'opsz': optical,
        'HGHT': [(0, round(y * .18)) for x, y in points],
        'wdth': [(round((x - 330) * .15), 0) for x, y in points],
        'TEST': [(round(y * .10), 0) for x, y in points],
    }
    variations = []
    for tag, minimum, default, maximum, name in axes:
        for sign in [-1, 1]:
            region = (-1.0, -1.0, 0.0) if sign < 0 else (0.0, 1.0, 1.0)
            # Four zero deltas are the TrueType phantom points: this fixture
            # intentionally keeps advance/vertical metrics stable for every axis.
            coordinates = [(sign * dx, sign * dy) for dx, dy in deltas[tag]] + [(0, 0)] * 4
            variations.append(TupleVariation({tag: region}, coordinates))
    gvar = newTable('gvar')
    gvar.version = 1
    gvar.reserved = 0
    gvar.variations = {'.notdef': [], 'A': variations}
    builder.font['gvar'] = gvar
    builder.font.recalcTimestamp = False
    builder.font['head'].created = builder.font['head'].modified = 3800000000
    builder.save(out / filename)


automation_font('automation.ttf', 'Swirl Automation Probe', [
    ('wght', 100, 400, 900, 'Weight'), ('opsz', 8, 12, 72, 'Optical size'),
    ('HGHT', 100, 250, 1000, 'Test height'), ('wdth', 75, 100, 125, 'Width'),
    ('TEST', -2, 0, 3, 'Original test shear'),
])
automation_font('automation-other.ttf', 'Swirl Other Probe', [
    ('wght', 500, 600, 750, 'Weight'), ('opsz', 16, 24, 48, 'Optical size'),
    ('HGHT', 1, 500, 900, 'Test height'), ('wdth', 90, 95, 110, 'Width'),
    ('TEST', 10, 20, 30, 'Original test shear'),
])
print('Generated original multi-axis outline fixtures for public automation tests')
