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
