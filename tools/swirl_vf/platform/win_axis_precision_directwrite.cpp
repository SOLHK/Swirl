// D1: original synthetic-font precision observations, never Apple acceptance.
// Reuse the existing audited file lock, COM error checks and font helpers.
// Its renamed entry point is not called; no production code is changed.
#if !defined(_WIN32)
#include <cstdio>
int main() {
    std::puts("{\"record\":\"summary\",\"status\":\"NOT_RUN\",\"reason\":\"Windows required\"}");
    return 77;
}
#else
#define wmain swirlExistingDirectWriteProbeEntry
#include "directwrite_probe.cpp"
#undef wmain
#include <chrono>

static uint32_t d1Bits(float x) {
    uint32_t b; static_assert(sizeof(x)==sizeof(b)); std::memcpy(&b,&x,sizeof(b)); return b;
}
static std::string d1Hash(const void *bytes, size_t size) {
    BCRYPT_ALG_HANDLE alg=nullptr; BCRYPT_HASH_HANDLE hash=nullptr;
    nativeChecked(BCryptOpenAlgorithmProvider(&alg,BCRYPT_SHA256_ALGORITHM,nullptr,0),"SHA256 provider");
    struct Done { BCRYPT_ALG_HANDLE &a; BCRYPT_HASH_HANDLE &h;
        ~Done(){if(h)BCryptDestroyHash(h);if(a)BCryptCloseAlgorithmProvider(a,0);}
    } done{alg,hash};
    DWORD n=0,received=0;
    nativeChecked(BCryptGetProperty(alg,BCRYPT_OBJECT_LENGTH,reinterpret_cast<PUCHAR>(&n),sizeof(n),&received,0),"SHA256 size");
    std::vector<UCHAR> object(n);
    nativeChecked(BCryptCreateHash(alg,&hash,object.data(),n,nullptr,0,0),"SHA256 create");
    if(size>MAXDWORD)throw std::runtime_error("Oversized hash input");
    if(size)nativeChecked(BCryptHashData(hash,static_cast<PUCHAR>(const_cast<void *>(bytes)),ULONG(size),0),"SHA256 data");
    std::array<UCHAR,32> digest{};
    nativeChecked(BCryptFinishHash(hash,digest.data(),ULONG(digest.size()),0),"SHA256 finish");
    std::ostringstream s;for(auto b:digest)s<<std::hex<<std::setw(2)<<std::setfill('0')<<unsigned(b);return s.str();
}
static std::vector<uint8_t> d1Table(IDWriteFontFace *face, const char *tag) {
    const void *data=nullptr;UINT32 size=0;void *context=nullptr;BOOL exists=FALSE;
    checked(face->TryGetFontTable(DWRITE_MAKE_OPENTYPE_TAG(tag[0],tag[1],tag[2],tag[3]),&data,&size,&context,&exists),"D1 identity table");
    struct Release {IDWriteFontFace *f;void *c;~Release(){if(c)f->ReleaseFontTable(c);}} release{face,context};
    if(!exists)throw std::runtime_error(std::string("Required fixture table missing: ")+tag);
    const auto *p=static_cast<const uint8_t *>(data);return {p,p+size};
}
static std::string d1Identity(IDWriteFontFace *expected,IDWriteFontFace *actual) {
    std::ostringstream s;s<<'{';bool first=true;
    for(const auto *tag:{"head","maxp","name","cmap","fvar","avar","glyf","gvar","hmtx","HVAR","STAT"}){
        auto a=d1Table(expected,tag),b=d1Table(actual,tag);
        if(a!=b)throw std::runtime_error(std::string("Wrong physical font table: ")+tag);
        s<<(first?"":",")<<quoted(tag)<<':'<<quoted(d1Hash(b.data(),b.size()));first=false;
    }
    return s.str()+'}';
}
struct D1Case {std::string id;std::array<std::string,3> decimal;std::array<double,3> values;};
static std::vector<D1Case> d1Cases(const fs::path &path) {
    std::ifstream f(path);if(!f)throw std::runtime_error("Cannot read request TSV");
    std::string line;std::getline(f,line);if(!line.empty()&&line.back()=='\r')line.pop_back();
    if(line!="id\twght\tWDTH\tHGHT")throw std::runtime_error("Unexpected case TSV schema");
    std::vector<D1Case> out;std::set<std::string> seen;
    while(std::getline(f,line)){
        if(!line.empty()&&line.back()=='\r')line.pop_back();if(line.empty())continue;
        std::istringstream row(line);D1Case c;std::getline(row,c.id,'\t');
        if(c.id.empty()||c.id.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")!=std::string::npos||!seen.insert(c.id).second)
            throw std::runtime_error("Unsafe/duplicate case id");
        for(size_t i=0;i<3;++i){
            if(!std::getline(row,c.decimal[i],'\t'))throw std::runtime_error("Truncated case");
            size_t used=0;c.values[i]=std::stod(c.decimal[i],&used);
            if(used!=c.decimal[i].size()||!std::isfinite(c.values[i]))throw std::runtime_error("Invalid case coordinate");
        }
        if(std::getline(row,line,'\t'))throw std::runtime_error("Extra case columns");
        out.push_back(c);
    }
    for(const auto *id:{"pair_lo","pair_hi","default","wght_min","wght_max","WDTH_min","WDTH_max","HGHT_min","HGHT_max"})
        if(!seen.count(id))throw std::runtime_error(std::string("Missing case: ")+id);
    if(out.size()>512)throw std::runtime_error("Unexpectedly large case set");return out;
}
static const std::array<DWRITE_FONT_AXIS_TAG,3> d1Tags{
    DWRITE_FONT_AXIS_TAG_WEIGHT,
    DWRITE_FONT_AXIS_TAG(DWRITE_MAKE_OPENTYPE_TAG('W','D','T','H')),
    DWRITE_FONT_AXIS_TAG(DWRITE_MAKE_OPENTYPE_TAG('H','G','H','T'))};
static std::string d1Inputs(const D1Case &c) {
    std::ostringstream s;s<<std::setprecision(17)<<"\"requested\":{";
    for(size_t i=0;i<3;++i)s<<(i?",":"")<<quoted(axisTag(d1Tags[i]))<<':'<<c.values[i];
    s<<"},\"requested_decimal\":{";
    for(size_t i=0;i<3;++i)s<<(i?",":"")<<quoted(axisTag(d1Tags[i]))<<':'<<quoted(c.decimal[i]);
    s<<"},\"input_float\":{";
    for(size_t i=0;i<3;++i)s<<(i?",":"")<<quoted(axisTag(d1Tags[i]))<<':'<<double(float(c.values[i]));
    s<<"},\"input_float_bits\":{";
    for(size_t i=0;i<3;++i)s<<(i?",":"")<<quoted(axisTag(d1Tags[i]))<<':'<<d1Bits(float(c.values[i]));
    return s.str()+'}';
}

// Raw operation stream, including every unrounded FLOAT coordinate as bits.
// Equality compares complete vectors, not only their SHA256 summaries.
struct D1Sink final : IDWriteGeometrySink {
    std::atomic<ULONG> refs{1};std::vector<uint32_t> words;bool finite=true;
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid,void **o)override{
        if(!o)return E_POINTER;*o=nullptr;
        if(iid==__uuidof(IUnknown)||iid==__uuidof(IDWriteGeometrySink)){*o=static_cast<IDWriteGeometrySink *>(this);AddRef();return S_OK;}return E_NOINTERFACE;
    }
    ULONG STDMETHODCALLTYPE AddRef()override{return ++refs;}
    ULONG STDMETHODCALLTYPE Release()override{auto n=--refs;if(!n)delete this;return n;}
    void p(D2D1_POINT_2F a){finite=finite&&std::isfinite(a.x)&&std::isfinite(a.y);words.push_back(d1Bits(a.x));words.push_back(d1Bits(a.y));}
    void STDMETHODCALLTYPE SetFillMode(D2D1_FILL_MODE m)override{words.insert(words.end(),{1,uint32_t(m)});}
    void STDMETHODCALLTYPE SetSegmentFlags(D2D1_PATH_SEGMENT m)override{words.insert(words.end(),{2,uint32_t(m)});}
    void STDMETHODCALLTYPE BeginFigure(D2D1_POINT_2F a,D2D1_FIGURE_BEGIN b)override{words.insert(words.end(),{3,uint32_t(b)});p(a);}
    void STDMETHODCALLTYPE AddLines(const D2D1_POINT_2F *a,UINT32 n)override{words.insert(words.end(),{4,n});for(UINT32 i=0;i<n;++i)p(a[i]);}
    void STDMETHODCALLTYPE AddBeziers(const D2D1_BEZIER_SEGMENT *a,UINT32 n)override{words.insert(words.end(),{5,n});for(UINT32 i=0;i<n;++i){p(a[i].point1);p(a[i].point2);p(a[i].point3);}}
    void STDMETHODCALLTYPE EndFigure(D2D1_FIGURE_END m)override{words.insert(words.end(),{6,uint32_t(m)});}
    HRESULT STDMETHODCALLTYPE Close()override{return finite?S_OK:E_FAIL;}
};

// Analyze the actual text; do not guess a script code when obtaining natural
// fractional advances. One scalar per measurement avoids unrelated ligatures.
struct D1Analysis final : IDWriteTextAnalysisSource, IDWriteTextAnalysisSink {
    std::atomic<ULONG> refs{1};wchar_t text;DWRITE_SCRIPT_ANALYSIS script{};bool analyzed=false;
    explicit D1Analysis(wchar_t c):text(c){}
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid,void **o)override{
        if(!o)return E_POINTER;*o=nullptr;
        if(iid==__uuidof(IUnknown)||iid==__uuidof(IDWriteTextAnalysisSource))*o=static_cast<IDWriteTextAnalysisSource *>(this);
        else if(iid==__uuidof(IDWriteTextAnalysisSink))*o=static_cast<IDWriteTextAnalysisSink *>(this);
        else return E_NOINTERFACE;AddRef();return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef()override{return ++refs;}
    ULONG STDMETHODCALLTYPE Release()override{auto n=--refs;if(!n)delete this;return n;}
    HRESULT STDMETHODCALLTYPE GetTextAtPosition(UINT32 p,WCHAR const **s,UINT32 *n)override{*s=p==0?&text:nullptr;*n=p==0?1:0;return S_OK;}
    HRESULT STDMETHODCALLTYPE GetTextBeforePosition(UINT32 p,WCHAR const **s,UINT32 *n)override{*s=p==1?&text:nullptr;*n=p==1?1:0;return S_OK;}
    DWRITE_READING_DIRECTION STDMETHODCALLTYPE GetParagraphReadingDirection()override{return DWRITE_READING_DIRECTION_LEFT_TO_RIGHT;}
    HRESULT STDMETHODCALLTYPE GetLocaleName(UINT32 p,UINT32 *n,WCHAR const **s)override{*n=p==0?1:0;*s=L"en-us";return S_OK;}
    HRESULT STDMETHODCALLTYPE GetNumberSubstitution(UINT32 p,UINT32 *n,IDWriteNumberSubstitution **s)override{*n=p==0?1:0;*s=nullptr;return S_OK;}
    HRESULT STDMETHODCALLTYPE SetScriptAnalysis(UINT32 p,UINT32 n,DWRITE_SCRIPT_ANALYSIS const *s)override{if(p!=0||n!=1)return E_INVALIDARG;script=*s;analyzed=true;return S_OK;}
    HRESULT STDMETHODCALLTYPE SetLineBreakpoints(UINT32,UINT32,DWRITE_LINE_BREAKPOINT const *)override{return S_OK;}
    HRESULT STDMETHODCALLTYPE SetBidiLevel(UINT32,UINT32,UINT8,UINT8)override{return S_OK;}
    HRESULT STDMETHODCALLTYPE SetNumberSubstitution(UINT32,UINT32,IDWriteNumberSubstitution *)override{return S_OK;}
};
static std::array<float,3> d1Placement(IDWriteTextAnalyzer *analyzer,IDWriteFontFace *face,UINT32 scalar,UINT16 expected,float em) {
    ComPtr<D1Analysis> analysis;analysis.Attach(new D1Analysis(wchar_t(scalar)));
    checked(analyzer->AnalyzeScript(analysis.Get(),0,1,analysis.Get()),"AnalyzeScript");
    if(!analysis->analyzed)throw std::runtime_error("Missing script analysis");
    UINT16 cluster=0;DWRITE_SHAPING_TEXT_PROPERTIES textProps{};
    std::array<UINT16,16> glyphs{};std::array<DWRITE_SHAPING_GLYPH_PROPERTIES,16> properties{};UINT32 count=0;
    checked(analyzer->GetGlyphs(&analysis->text,1,face,FALSE,FALSE,&analysis->script,L"en-us",nullptr,nullptr,nullptr,0,16,&cluster,&textProps,glyphs.data(),properties.data(),&count),"GetGlyphs");
    if(count!=1||glyphs[0]!=expected)throw std::runtime_error("Unexpected shaping or missing glyph");
    float advance=0;DWRITE_GLYPH_OFFSET offset{};
    checked(analyzer->GetGlyphPlacements(&analysis->text,&cluster,&textProps,1,glyphs.data(),properties.data(),count,face,em,FALSE,FALSE,&analysis->script,L"en-us",nullptr,nullptr,0,&advance,&offset),"GetGlyphPlacements");
    if(!std::isfinite(advance)||!std::isfinite(offset.advanceOffset)||!std::isfinite(offset.ascenderOffset))throw std::runtime_error("Nonfinite placement");
    return {advance,offset.advanceOffset,offset.ascenderOffset};
}
struct D1Raster {std::array<LONG,4> bounds;std::vector<uint8_t> bytes;};
static D1Raster d1Raster(IDWriteFactory *factory,IDWriteFontFace *face,UINT16 glyph,float em,float dpr) {
    DWRITE_GLYPH_RUN run{};run.fontFace=face;run.fontEmSize=em;run.glyphCount=1;run.glyphIndices=&glyph;
    float advance=0;run.glyphAdvances=&advance;
    ComPtr<IDWriteGlyphRunAnalysis> analysis;
    checked(factory->CreateGlyphRunAnalysis(&run,dpr,nullptr,DWRITE_RENDERING_MODE_CLEARTYPE_NATURAL_SYMMETRIC,DWRITE_MEASURING_MODE_NATURAL,0,0,&analysis),"CreateGlyphRunAnalysis");
    RECT r{};checked(analysis->GetAlphaTextureBounds(DWRITE_TEXTURE_CLEARTYPE_3x1,&r),"GetAlphaTextureBounds");
    int64_t width=int64_t(r.right)-r.left,height=int64_t(r.bottom)-r.top;
    if(width<=0||height<=0||width*height>8*1024*1024)throw std::runtime_error("Empty or excessive raster bounds");
    D1Raster result{{r.left,r.top,r.right,r.bottom},std::vector<uint8_t>(size_t(width*height*3))};
    checked(analysis->CreateAlphaTexture(DWRITE_TEXTURE_CLEARTYPE_3x1,&r,result.bytes.data(),UINT32(result.bytes.size())),"CreateAlphaTexture");
    if(std::none_of(result.bytes.begin(),result.bytes.end(),[](uint8_t b){return b!=0;}))throw std::runtime_error("Blank raster");
    return result;
}
template<class T>static std::string d1Array(const T &a){std::ostringstream s;s<<std::setprecision(17)<<'[';bool first=true;for(auto v:a){s<<(first?"":",")<<v;first=false;}return s.str()+']';}
struct D1Capture {
    std::string outline,metrics,placement,raster,readback;
    std::vector<uint8_t> rasterBytes;
    bool operator==(const D1Capture &x)const{return outline==x.outline&&metrics==x.metrics&&placement==x.placement&&raster==x.raster&&readback==x.readback&&rasterBytes==x.rasterBytes;}
};
static D1Capture d1Capture(IDWriteFactory *factory,IDWriteTextAnalyzer *analyzer,IDWriteFontFace5 *face,UINT16 upem,const fs::path &output,const std::string &id,bool save) {
    D1Capture out;std::ostringstream paths,metrics,placements,rasters;
    paths<<'[';metrics<<'[';placements<<std::setprecision(17)<<'[';rasters<<'[';
    const std::array<UINT32,4> scalars{0x41,0x42,0x4E2D,0x6587};
    std::array<UINT16,4> glyphs{};checked(face->GetGlyphIndices(scalars.data(),UINT32(scalars.size()),glyphs.data()),"Fixture cmap");
    for(size_t i=0;i<scalars.size();++i){
        if(!glyphs[i])throw std::runtime_error("Missing fixture glyph");
        ComPtr<D1Sink> sink;sink.Attach(new D1Sink);
        checked(face->GetGlyphRunOutline(float(upem),&glyphs[i],nullptr,nullptr,1,FALSE,FALSE,sink.Get()),"Raw outline");
        checked(sink->Close(),"Finite outline");
        if(sink->words.size()<8)throw std::runtime_error("Empty outline");
        DWRITE_GLYPH_METRICS m{};checked(face->GetDesignGlyphMetrics(&glyphs[i],1,&m,FALSE),"Raw design metrics");
        paths<<(i?",":"")<<"{\"gid\":"<<glyphs[i]<<",\"operations_u32\":"<<d1Array(sink->words)<<'}';
        metrics<<(i?",":"")<<"{\"gid\":"<<glyphs[i]<<",\"advanceWidth\":"<<m.advanceWidth<<",\"leftSideBearing\":"<<m.leftSideBearing<<",\"rightSideBearing\":"<<m.rightSideBearing<<",\"advanceHeight\":"<<m.advanceHeight<<",\"topSideBearing\":"<<m.topSideBearing<<",\"bottomSideBearing\":"<<m.bottomSideBearing<<",\"verticalOriginY\":"<<m.verticalOriginY<<'}';
        auto p=d1Placement(analyzer,face,scalars[i],glyphs[i],float(upem));
        placements<<(i?",":"")<<"{\"gid\":"<<glyphs[i]<<",\"em\":"<<upem<<",\"advance\":"<<p[0]<<",\"offset\":["<<p[1]<<','<<p[2]<<"]}";
    }
    // A deterministic glyph raster is a separate observable from path/metrics.
    bool first=true;
    for(float em:{16.f,32.f})for(float dpr:{1.f,1.25f,1.5f,2.f}){
        auto r=d1Raster(factory,face,glyphs[0],em,dpr);
        rasters<<(first?"":",")<<"{\"em\":"<<em<<",\"dpr\":"<<dpr<<",\"bounds\":"<<d1Array(r.bounds)<<",\"bytes\":"<<r.bytes.size()<<",\"sha256\":"<<quoted(d1Hash(r.bytes.data(),r.bytes.size()))<<'}';first=false;
        out.rasterBytes.insert(out.rasterBytes.end(),r.bytes.begin(),r.bytes.end());
        if(save&&em==32.f&&dpr==1.f){
            auto path=output/(id+"-A-cleartype3x1.bin");std::ofstream raw(path,std::ios::binary);raw.write(reinterpret_cast<const char *>(r.bytes.data()),std::streamsize(r.bytes.size()));if(!raw)throw std::runtime_error("Cannot save alpha raster");
            std::ofstream pgm(output/(id+"-A.pgm"),std::ios::binary);pgm<<"P5\n"<<(r.bounds[2]-r.bounds[0])<<' '<<(r.bounds[3]-r.bounds[1])<<"\n255\n";
            for(size_t j=0;j<r.bytes.size();j+=3){unsigned total=unsigned(r.bytes[j])+r.bytes[j+1]+r.bytes[j+2];char pixel=char(255-total/3);pgm.write(&pixel,1);}if(!pgm)throw std::runtime_error("Cannot save raster preview");
        }
    }
    out.outline=paths.str()+']';out.metrics=metrics.str()+']';out.placement=placements.str()+']';out.raster=rasters.str()+']';
    std::vector<DWRITE_FONT_AXIS_VALUE> readback(face->GetFontAxisValueCount());checked(face->GetFontAxisValues(readback.data(),UINT32(readback.size())),"Native axis readback");
    std::sort(readback.begin(),readback.end(),[](auto a,auto b){return a.axisTag<b.axisTag;});
    std::ostringstream rb;rb<<std::setprecision(17)<<'[';
    for(size_t i=0;i<readback.size();++i){const auto a=readback[i];rb<<(i?",":"")<<"{\"tag\":"<<quoted(axisTag(a.axisTag))<<",\"value\":"<<double(a.value)<<",\"bits\":"<<d1Bits(a.value)<<'}';}out.readback=rb.str()+']';
    return out;
}
static std::string d1Family(IDWriteFontFace5 *face){ComPtr<IDWriteLocalizedStrings> s;checked(face->GetFamilyNames(&s),"Family names");return names(s.Get());}
static ComPtr<IDWriteFontResource> d1Installed(IDWriteFactory6 *factory,IDWriteFontFace5 *expected) {
    const auto family=d1Family(expected);
    int count=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,family.data(),int(family.size()),nullptr,0);
    if(!count)throw std::runtime_error("Invalid fixture family");std::wstring wide(size_t(count),L'\0');
    MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,family.data(),int(family.size()),wide.data(),count);
    ComPtr<IDWriteFontCollection> collection;
    checked(static_cast<IDWriteFactory *>(factory)->GetSystemFontCollection(&collection,TRUE),"Refreshed system font collection");
    UINT32 index=0;BOOL exists=FALSE;checked(collection->FindFamilyName(wide.c_str(),&index,&exists),"Installed family lookup");
    if(!exists)throw std::runtime_error("Fixture not found in real system font collection");
    ComPtr<IDWriteFontFamily> found;checked(collection->GetFontFamily(index,&found),"Installed font family");
    ComPtr<IDWriteFont> font;checked(found->GetFirstMatchingFont(DWRITE_FONT_WEIGHT_NORMAL,DWRITE_FONT_STRETCH_NORMAL,DWRITE_FONT_STYLE_NORMAL,&font),"Installed matching font");
    ComPtr<IDWriteFontFace> base;checked(font->CreateFontFace(&base),"Installed CreateFontFace");
    ComPtr<IDWriteFontFace5> face;checked(base.As(&face),"Installed variable face interface");
    d1Identity(expected,face.Get());ComPtr<IDWriteFontResource> resource;checked(face->GetFontResource(&resource),"Installed GetFontResource");return resource;
}
int wmain(int argc,wchar_t **argv) {
    if(argc<3){std::fputs("Usage: win_axis_precision_directwrite FONT OUTPUT --cases REQUESTS.tsv [--installed] [--reverse]\n",stderr);return 2;}
    fs::path input=fs::absolute(argv[1]),output=fs::absolute(argv[2]),casesPath;bool installed=false,reverse=false;
    for(int i=3;i<argc;++i){if(!std::wcscmp(argv[i],L"--installed"))installed=true;else if(!std::wcscmp(argv[i],L"--reverse"))reverse=true;else if(!std::wcscmp(argv[i],L"--cases")&&i+1<argc)casesPath=argv[++i];else return 2;}
    if(casesPath.empty())return 2;fs::create_directories(output);auto logPath=output/L"directwrite-axis-precision.jsonl";
    if(fs::exists(logPath)){std::fputs("Use a new output directory\n",stderr);return 2;}
    std::ofstream log(logPath);log<<std::setprecision(17);if(!log)return 2;
    auto start=std::chrono::steady_clock::now();HRESULT apartment=CoInitializeEx(nullptr,COINIT_MULTITHREADED);
    struct Uninit{bool yes;~Uninit(){if(yes)CoUninitialize();}}uninit{SUCCEEDED(apartment)};
    try{
        checked(apartment,"COM init");LockedInput locked(input);auto requests=d1Cases(casesPath);
        ComPtr<IDWriteFactory6> factory;checked(DWriteCreateFactory(DWRITE_FACTORY_TYPE_ISOLATED,__uuidof(IDWriteFactory6),reinterpret_cast<IUnknown **>(factory.GetAddressOf())),"Factory6");
        ComPtr<IDWriteFontFile> file;checked(factory->CreateFontFileReference(input.c_str(),nullptr,&file),"Fixture reference");
        ComPtr<IDWriteFontResource> direct;checked(factory->CreateFontResource(file.Get(),0,&direct),"Direct font resource");
        std::vector<DWRITE_FONT_AXIS_VALUE> defaults(direct->GetFontAxisCount());checked(direct->GetDefaultFontAxisValues(defaults.data(),UINT32(defaults.size())),"Default axis values");
        auto expected=instance(direct.Get(),defaults);const auto family=d1Family(expected.Get());
        if(family!="Swirl D1 Precision"&&family!="Swirl D1 Precision Gain")throw std::runtime_error("This probe only accepts original D1 synthetic fixtures");
        DWRITE_FONT_METRICS fm{};static_cast<IDWriteFontFace *>(expected.Get())->GetMetrics(&fm);
        if(fm.designUnitsPerEm!=1000||expected->GetGlyphCount()!=6)throw std::runtime_error("Unexpected fixture topology");
        const auto axes=fvarAxes(expected.Get());if(axes.size()!=3)throw std::runtime_error("Unexpected physical axis count");
        auto resource=installed?d1Installed(factory.Get(),expected.Get()):direct;
        auto actual=instance(resource.Get(),defaults);const auto identity=d1Identity(expected.Get(),actual.Get());
        ComPtr<IDWriteTextAnalyzer> analyzer;checked(factory->CreateTextAnalyzer(&analyzer),"Text analyzer");
        log<<"{\"record\":\"header\",\"schema\":1,\"input_sha256\":"<<quoted(locked.sha256)<<",\"input_bytes\":"<<locked.bytes<<",\"family\":"<<quoted(family)<<",\"load_mode\":"<<quoted(installed?"system_collection":"direct_file")<<",\"first_order\":"<<quoted(reverse?"reverse":"forward")<<",\"case_count\":"<<requests.size()<<",\"api_axis_type\":\"IEEE754_binary32\",\"units_per_em\":"<<fm.designUnitsPerEm<<",\"glyph_count\":"<<expected->GetGlyphCount()<<",\"physical_table_sha256\":"<<identity<<",\"original_ttc_acceptance\":\"NOT_RUN\",\"windows11_desktop_acceptance\":\"NOT_RUN\"}\n";
        std::map<std::string,D1Capture> observations;std::map<std::string,std::array<uint32_t,3>> inputBits;size_t count=0;
        if(reverse)std::reverse(requests.begin(),requests.end());
        for(unsigned pass=0;pass<2;++pass){
            if(pass)std::reverse(requests.begin(),requests.end());
            for(const auto &c:requests){
                auto values=defaults;std::array<uint32_t,3> bits{};
                for(size_t i=0;i<3;++i){
                    auto a=std::find_if(axes.begin(),axes.end(),[&](auto x){return x.tag==d1Tags[i];});
                    if(a==axes.end()||c.values[i]<a->lo||c.values[i]>a->hi)throw std::runtime_error("Case outside physical axis range");
                    auto v=std::find_if(values.begin(),values.end(),[&](auto x){return x.axisTag==d1Tags[i];});
                    if(v==values.end())throw std::runtime_error("Missing API axis");v->value=float(c.values[i]);bits[i]=d1Bits(v->value);
                }
                auto face=instance(resource.Get(),values);d1Identity(expected.Get(),face.Get());
                const bool save=pass==0&&(c.id=="pair_lo"||c.id=="pair_hi"||c.id=="default"||c.id=="wght_max");
                auto capture=d1Capture(factory.Get(),analyzer.Get(),face.Get(),fm.designUnitsPerEm,output,c.id,save);
                if(pass==0){observations.emplace(c.id,capture);inputBits.emplace(c.id,bits);}else if(!(observations.at(c.id)==capture))throw std::runtime_error("Reverse-order raw payload mismatch: "+c.id);
                log<<"{\"record\":\"observation\",\"case_id\":"<<quoted(c.id)<<",\"pass\":"<<pass<<','<<d1Inputs(c)<<",\"api_readback\":"<<capture.readback<<",\"outline\":"<<capture.outline<<",\"design_metrics\":"<<capture.metrics<<",\"natural_placement\":"<<capture.placement<<",\"raster\":"<<capture.raster<<"}\n";++count;
            }
        }
        const auto &a=observations.at("pair_lo"),&b=observations.at("pair_hi");
        const bool bitEqual=inputBits.at("pair_lo")==inputBits.at("pair_hi");
        if(!bitEqual||!(a==b))throw std::runtime_error("Pair collision did not reproduce deterministically");
        for(const auto *tag:{"wght","WDTH","HGHT"}){
            auto lo=observations.at(std::string(tag)+"_min"),hi=observations.at(std::string(tag)+"_max");
            if(lo.outline==hi.outline)throw std::runtime_error(std::string("Axis positive outline control ignored: ")+tag);
            if(std::string(tag)!="HGHT"&&lo.placement==hi.placement)throw std::runtime_error(std::string("Axis positive advance control ignored: ")+tag);
        }
        double elapsed=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
        log<<"{\"record\":\"summary\",\"status\":\"PASS_DWRITE_SYNTHETIC\",\"observation_count\":"<<count<<",\"pair_input_bits_equal\":true,\"pair_outline_equal\":true,\"pair_design_metrics_equal\":true,\"pair_placement_equal\":true,\"pair_raster_equal\":true,\"reverse_replay_equal\":true,\"axis_positive_controls_passed\":3,\"elapsed_ms\":"<<elapsed<<",\"internal_normalization_algorithm\":\"NOT_INFERRED_FROM_READBACK\",\"original_ttc_acceptance\":\"NOT_RUN\"}\n";
        log.flush();if(!log)throw std::runtime_error("Report write failed");std::puts("PASS_DWRITE_SYNTHETIC");return 0;
    }catch(const std::exception &e){log<<"{\"record\":\"summary\",\"status\":\"FAILED\",\"error\":"<<quoted(e.what())<<"}\n";std::fprintf(stderr,"%s\n",e.what());return 1;}
}
#endif
