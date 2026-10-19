// Swirl-VF native DirectWrite acceptance probe.
// Original code using Microsoft-documented interfaces; no font payload included.
// Build: cl /std:c++17 /EHsc /W4 /utf-8 directwrite_probe.cpp
//        /link dwrite.lib d2d1.lib windowscodecs.lib ole32.lib bcrypt.lib
// Usage: directwrite_probe.exe FONT OUTPUT_DIRECTORY [--all-glyphs] [--render]
// A PASS_NATIVE_PROBE verdict is deliberately scoped: it does not compare an
// original CoreText/HVF oracle, validate shaping, or certify real Swirl layout.
#include <cstdio>
#if !defined(_WIN32)
int main() {
    std::puts("{\"record\":\"summary\",\"status\":\"NOT_RUN\",\"reason\":\"Windows DirectWrite runtime unavailable\"}");
    return 77;
}
#else
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
#include <dwrite_3.h>
#include <d2d1.h>
#include <wincodec.h>
#include <wrl/client.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cfloat>
#include <cstdint>
#include <cwchar>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using Microsoft::WRL::ComPtr;
namespace fs = std::filesystem;

static std::string quoted(const std::string &input) {
    std::ostringstream out;
    out << '"';
    for (unsigned char c : input) {
        if (c == '\\' || c == '"') out << '\\' << c;
        else if (c < 32) out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << unsigned(c) << std::dec;
        else out << c;
    }
    return out.str() + '"';
}
static std::string utf8(const std::wstring &s) {
    if (s.empty()) return {};
    int n = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, s.data(), int(s.size()), nullptr, 0, nullptr, nullptr);
    if (!n) throw std::runtime_error("Invalid UTF-16 name/path");
    std::string result(size_t(n), '\0');
    WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, s.data(), int(s.size()), result.data(), n, nullptr, nullptr);
    return result;
}
static void checked(HRESULT hr, const char *where) {
    if (FAILED(hr)) {
        std::ostringstream s; s << where << " HRESULT=0x" << std::hex << uint32_t(hr);
        throw std::runtime_error(s.str());
    }
}
static void nativeChecked(NTSTATUS status, const char *where) {
    if (status < 0) throw std::runtime_error(std::string(where) + " NTSTATUS=" + std::to_string(status));
}
static std::string axisTag(DWRITE_FONT_AXIS_TAG tag) {
    uint32_t value = uint32_t(tag);
    std::string result(4, '\0');
    for (unsigned i = 0; i < 4; ++i) result[i] = char((value >> (8 * i)) & 255);
    return result;
}
static uint16_t be16(const uint8_t *p) { return uint16_t((uint16_t(p[0]) << 8) | p[1]); }
static uint32_t be32(const uint8_t *p) { return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | p[3]; }
static DWRITE_FONT_AXIS_TAG tagFromBytes(const uint8_t *p) {
    return DWRITE_FONT_AXIS_TAG(uint32_t(p[0]) | (uint32_t(p[1]) << 8) | (uint32_t(p[2]) << 16) | (uint32_t(p[3]) << 24));
}
static std::string names(IDWriteLocalizedStrings *strings) {
    if (!strings || !strings->GetCount()) return {};
    UINT32 index = 0, length = 0; BOOL found = FALSE;
    checked(strings->FindLocaleName(L"en-us", &index, &found), "FindLocaleName");
    if (!found) index = 0;
    checked(strings->GetStringLength(index, &length), "GetStringLength");
    std::vector<wchar_t> value(size_t(length) + 1);
    checked(strings->GetString(index, value.data(), length + 1), "GetString");
    return utf8(std::wstring(value.data(), length));
}

struct LockedInput {
    HANDLE file = INVALID_HANDLE_VALUE;
    std::string sha256;
    uint64_t bytes = 0;
    explicit LockedInput(const fs::path &path) {
        // Deny write/delete sharing throughout the probe: DWrite and hashing see
        // the same immutable file, not a same-name replacement or cache race.
        file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (file == INVALID_HANDLE_VALUE) throw std::runtime_error("Cannot open and lock font input");
        BCRYPT_ALG_HANDLE algorithm = nullptr;
        BCRYPT_HASH_HANDLE hash = nullptr;
        std::vector<UCHAR> object;
        try {
            LARGE_INTEGER size{};
            if (!GetFileSizeEx(file, &size) || size.QuadPart <= 0) throw std::runtime_error("Invalid font file size");
            bytes = uint64_t(size.QuadPart);
            nativeChecked(BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0), "BCryptOpenAlgorithmProvider");
            DWORD objectSize = 0, received = 0;
            nativeChecked(BCryptGetProperty(algorithm, BCRYPT_OBJECT_LENGTH, reinterpret_cast<PUCHAR>(&objectSize), sizeof(objectSize), &received, 0), "BCryptGetProperty");
            object.resize(objectSize);
            std::vector<UCHAR> block(1 << 20);
            nativeChecked(BCryptCreateHash(algorithm, &hash, object.data(), objectSize, nullptr, 0, 0), "BCryptCreateHash");
            DWORD count = 0;
            do {
                if (!ReadFile(file, block.data(), DWORD(block.size()), &count, nullptr)) throw std::runtime_error("Font read failed");
                if (count) nativeChecked(BCryptHashData(hash, block.data(), count, 0), "BCryptHashData");
            } while (count);
            std::array<UCHAR, 32> digest{};
            nativeChecked(BCryptFinishHash(hash, digest.data(), DWORD(digest.size()), 0), "BCryptFinishHash");
            std::ostringstream formatted;
            for (UCHAR c : digest) formatted << std::hex << std::setw(2) << std::setfill('0') << unsigned(c);
            sha256 = formatted.str();
            BCryptDestroyHash(hash); hash = nullptr;
            BCryptCloseAlgorithmProvider(algorithm, 0); algorithm = nullptr;
        } catch (...) {
            if (hash) BCryptDestroyHash(hash);
            if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0);
            CloseHandle(file); file = INVALID_HANDLE_VALUE;
            throw;
        }
    }
    ~LockedInput() { if (file != INVALID_HANDLE_VALUE) CloseHandle(file); }
};

struct Axis { DWRITE_FONT_AXIS_TAG tag; float lo, value, hi; };
static std::vector<Axis> fvarAxes(IDWriteFontFace5 *face) {
    const void *data = nullptr; UINT32 size = 0; void *context = nullptr; BOOL exists = FALSE;
    checked(face->TryGetFontTable(DWRITE_MAKE_OPENTYPE_TAG('f','v','a','r'), &data, &size, &context, &exists), "TryGetFontTable(fvar)");
    struct Release { IDWriteFontFace5 *face; void *context; ~Release(){ if(context) face->ReleaseFontTable(context); } } release{face, context};
    if (!exists || size < 16) throw std::runtime_error("Missing/truncated physical fvar table");
    const auto *p = static_cast<const uint8_t *>(data);
    size_t offset = be16(p + 4), count = be16(p + 8), stride = be16(p + 10);
    if (be16(p) != 1 || !count || count > 8 || stride < 20 || offset > size || count * stride > size - offset)
        throw std::runtime_error("Invalid/unsupported physical fvar directory");
    std::vector<Axis> result;
    std::set<DWRITE_FONT_AXIS_TAG> seen;
    for (size_t i = 0; i < count; ++i) {
        auto *r = p + offset + i * stride;
        auto fixed = [](const uint8_t *q) { return float(int32_t(be32(q)) / 65536.0); };
        Axis axis{tagFromBytes(r), fixed(r + 4), fixed(r + 8), fixed(r + 12)};
        if (!seen.insert(axis.tag).second || !(axis.lo <= axis.value && axis.value <= axis.hi)) throw std::runtime_error("Duplicate or invalid fvar axis");
        result.push_back(axis);
    }
    return result;
}
static std::string axisValuesJSON(const std::vector<DWRITE_FONT_AXIS_VALUE> &values) {
    std::ostringstream out; out << std::setprecision(9) << '{';
    for (size_t i = 0; i < values.size(); ++i) out << (i ? "," : "") << quoted(axisTag(values[i].axisTag)) << ':' << values[i].value;
    return out.str() + '}';
}
static ComPtr<IDWriteFontFace5> instance(IDWriteFontResource *resource, const std::vector<DWRITE_FONT_AXIS_VALUE> &requested) {
    ComPtr<IDWriteFontFace5> face;
    checked(resource->CreateFontFace(DWRITE_FONT_SIMULATIONS_NONE, requested.data(), UINT32(requested.size()), &face), "CreateFontFace(axis values)");
    if (face->GetSimulations() != DWRITE_FONT_SIMULATIONS_NONE) throw std::runtime_error("Synthetic bold/italic was applied");
    std::vector<DWRITE_FONT_AXIS_VALUE> applied(face->GetFontAxisValueCount());
    checked(face->GetFontAxisValues(applied.data(), UINT32(applied.size())), "GetFontAxisValues");
    for (const auto &request : requested) {
        auto found = std::find_if(applied.begin(), applied.end(), [&](auto x){ return x.axisTag == request.axisTag; });
        float tolerance = std::max(1e-5f, std::abs(request.value) * 1e-6f);
        if (found == applied.end() || !std::isfinite(found->value) || std::abs(found->value - request.value) > tolerance)
            throw std::runtime_error("Axis value was ignored/clamped: " + axisTag(request.axisTag));
    }
    return face;
}

struct GeometrySink final : IDWriteGeometrySink {
    std::atomic<ULONG> refs{1};
    uint64_t hash = 14695981039346656037ull, points = 0;
    bool finite = true;
    float xmin = FLT_MAX, ymin = FLT_MAX, xmax = -FLT_MAX, ymax = -FLT_MAX;
    void word(uint32_t value) { for(unsigned i=0;i<4;++i){ hash ^= uint8_t(value >> (8*i)); hash *= 1099511628211ull; } }
    void point(D2D1_POINT_2F p) {
        finite = finite && std::isfinite(p.x) && std::isfinite(p.y);
        uint32_t x, y; std::memcpy(&x,&p.x,4); std::memcpy(&y,&p.y,4); word(x); word(y); ++points;
        xmin = std::min(xmin,p.x); ymin = std::min(ymin,p.y); xmax = std::max(xmax,p.x); ymax = std::max(ymax,p.y);
    }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void **out) override {
        if (!out) return E_POINTER; *out = nullptr;
        if (iid == __uuidof(IUnknown) || iid == __uuidof(IDWriteGeometrySink)) { *out = static_cast<IDWriteGeometrySink *>(this); AddRef(); return S_OK; }
        return E_NOINTERFACE;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++refs; }
    ULONG STDMETHODCALLTYPE Release() override { ULONG n=--refs; if(!n) delete this; return n; }
    void STDMETHODCALLTYPE SetFillMode(D2D1_FILL_MODE mode) override { word(1); word(uint32_t(mode)); }
    void STDMETHODCALLTYPE SetSegmentFlags(D2D1_PATH_SEGMENT flags) override { word(2); word(uint32_t(flags)); }
    void STDMETHODCALLTYPE BeginFigure(D2D1_POINT_2F p,D2D1_FIGURE_BEGIN begin) override { word(3); word(uint32_t(begin)); point(p); }
    void STDMETHODCALLTYPE AddLines(const D2D1_POINT_2F *p, UINT32 count) override { word(4); word(count); for(UINT32 i=0;i<count;++i) point(p[i]); }
    void STDMETHODCALLTYPE AddBeziers(const D2D1_BEZIER_SEGMENT *b, UINT32 count) override { word(5); word(count); for(UINT32 i=0;i<count;++i){point(b[i].point1);point(b[i].point2);point(b[i].point3);} }
    void STDMETHODCALLTYPE EndFigure(D2D1_FIGURE_END end) override { word(6); word(uint32_t(end)); }
    HRESULT STDMETHODCALLTYPE Close() override { return finite ? S_OK : E_FAIL; }
};
struct Snapshot { uint64_t hash=14695981039346656037ull, points=0, nonempty=0; double totalAdvance=0; };
static Snapshot snapshot(IDWriteFontFace5 *face,const std::vector<UINT16> &glyphs) {
    DWRITE_FONT_METRICS global{}; static_cast<IDWriteFontFace *>(face)->GetMetrics(&global);
    if (!global.designUnitsPerEm) throw std::runtime_error("Invalid unitsPerEm");
    std::vector<DWRITE_GLYPH_METRICS> metrics(glyphs.size());
    checked(face->GetDesignGlyphMetrics(glyphs.data(), UINT32(glyphs.size()), metrics.data(), FALSE), "GetDesignGlyphMetrics");
    Snapshot result;
    for(size_t i=0;i<glyphs.size();++i){
        ComPtr<GeometrySink> sink; sink.Attach(new GeometrySink);
        checked(face->GetGlyphRunOutline(float(global.designUnitsPerEm), &glyphs[i], nullptr, nullptr, 1, FALSE, FALSE, sink.Get()), "GetGlyphRunOutline");
        checked(sink->Close(), "Outline finite coordinates");
        sink->word(metrics[i].advanceWidth); sink->word(uint32_t(metrics[i].leftSideBearing)); sink->word(uint32_t(metrics[i].rightSideBearing));
        sink->word(metrics[i].advanceHeight); sink->word(uint32_t(metrics[i].topSideBearing)); sink->word(uint32_t(metrics[i].bottomSideBearing));
        result.hash ^= sink->hash; result.hash *= 1099511628211ull;
        result.points += sink->points; result.nonempty += sink->points != 0; result.totalAdvance += metrics[i].advanceWidth;
    }
    if (!result.points) throw std::runtime_error("All selected glyphs produced empty outlines");
    return result;
}
static double halton(unsigned index,unsigned base){ double value=0,f=1; while(index){f/=base;value+=f*(index%base);index/=base;}return value; }
struct Position {std::string name; std::vector<DWRITE_FONT_AXIS_VALUE> values; int sweep=-1;};
static std::vector<Position> positions(const std::vector<Axis> &axes) {
    std::vector<DWRITE_FONT_AXIS_VALUE> defaults;
    for(auto a:axes) defaults.push_back({a.tag,a.value});
    std::vector<Position> result{{"default",defaults,-1}};
    for(size_t a=0;a<axes.size();++a){
        for(double f: {0.0,.1732050807569,.3819660112501,.6180339887499,.8267949192431,1.0}){
            auto values=defaults; values[a].value=float(axes[a].lo+f*(axes[a].hi-axes[a].lo));
            result.push_back({"sweep_"+axisTag(axes[a].tag)+"_"+std::to_string(f),values,int(a)});
        }
    }
    if(axes.size()<=4){
        size_t total=1; for(size_t i=0;i<axes.size();++i) total*=3;
        for(size_t n=0;n<total;++n){
            auto values=defaults; size_t m=n;
            for(size_t a=0;a<axes.size();++a){unsigned choice=unsigned(m%3);m/=3;values[a].value=choice==0?axes[a].lo:choice==1?axes[a].value:axes[a].hi;}
            result.push_back({"grid_"+std::to_string(n),values,-1});
        }
    }
    static const unsigned primes[]={2,3,5,7,11,13,17,19};
    for(unsigned n=1;n<=16;++n){auto values=defaults;for(size_t a=0;a<axes.size();++a)values[a].value=float(axes[a].lo+halton(n+31,primes[a])*(axes[a].hi-axes[a].lo));result.push_back({"internal_"+std::to_string(n),values,-1});}
    return result;
}

static void raster(IDWriteFontFace5 *face, const fs::path &path, float dpi, bool dark) {
    ComPtr<IWICImagingFactory> wic;
    checked(CoCreateInstance(CLSID_WICImagingFactory,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&wic)),"WIC factory");
    ComPtr<ID2D1Factory> d2d;
    checked(D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED,d2d.GetAddressOf()),"Direct2D factory");
    UINT width=UINT(std::ceil(900.0*dpi/96)),height=UINT(std::ceil(250.0*dpi/96));
    ComPtr<IWICBitmap> bitmap;
    checked(wic->CreateBitmap(width,height,GUID_WICPixelFormat32bppPBGRA,WICBitmapCacheOnLoad,&bitmap),"WIC bitmap");
    ComPtr<ID2D1RenderTarget> target;
    auto props=D2D1::RenderTargetProperties(D2D1_RENDER_TARGET_TYPE_SOFTWARE,D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM,D2D1_ALPHA_MODE_PREMULTIPLIED),dpi,dpi);
    checked(d2d->CreateWicBitmapRenderTarget(bitmap.Get(),props,&target),"WIC render target");
    ComPtr<ID2D1SolidColorBrush> brush;
    checked(target->CreateSolidColorBrush(D2D1::ColorF(dark ? 0xEEEEEEu : 0x111111u),&brush),"text brush");
    // This sheet intentionally uses glyph runs, not an unverified shaping path.
    const UINT32 text[]={0x4E2D,0x6587,0x5B57,0x4F53,0x6D4B,0x8BD5,0x0020,0x7BC0,0x9AD4,0x6E2F,0x6FB3,0x65E5,0x0020,0x0041,0x0042,0x0043,0x0061,0x0067,0x0030,0x0031,0x0032,0x0038,0x0039,0x0025};
    constexpr UINT32 count=sizeof(text)/sizeof(text[0]);
    std::array<UINT16,count> glyphs{};
    checked(face->GetGlyphIndices(text,count,glyphs.data()),"Raster GetGlyphIndices");
    std::array<DWRITE_GLYPH_METRICS,count> metrics{};
    checked(face->GetDesignGlyphMetrics(glyphs.data(),count,metrics.data(),FALSE),"Raster metrics");
    DWRITE_FONT_METRICS fm{};static_cast<IDWriteFontFace *>(face)->GetMetrics(&fm);
    target->SetTextAntialiasMode(D2D1_TEXT_ANTIALIAS_MODE_GRAYSCALE);
    target->BeginDraw(); target->Clear(D2D1::ColorF(dark ? 0x151515u : 0xFFFFFFu));
    float y=30;
    for(float size:{12.f,16.f,24.f,36.f}){
        std::array<float,count> advances{};for(UINT32 i=0;i<count;++i)advances[i]=metrics[i].advanceWidth*size/fm.designUnitsPerEm;
        DWRITE_GLYPH_RUN run{};run.fontFace=face;run.fontEmSize=size;run.glyphCount=count;run.glyphIndices=glyphs.data();run.glyphAdvances=advances.data();
        target->DrawGlyphRun(D2D1::Point2F(20,y),&run,brush.Get(),DWRITE_MEASURING_MODE_NATURAL);y+=size+30;
    }
    checked(target->EndDraw(),"Direct2D draw");
    ComPtr<IWICStream> stream;checked(wic->CreateStream(&stream),"WIC stream");checked(stream->InitializeFromFilename(path.c_str(),GENERIC_WRITE),"PNG destination");
    ComPtr<IWICBitmapEncoder> encoder;checked(wic->CreateEncoder(GUID_ContainerFormatPng,nullptr,&encoder),"PNG encoder");checked(encoder->Initialize(stream.Get(),WICBitmapEncoderNoCache),"PNG initialize");
    ComPtr<IWICBitmapFrameEncode> frame;checked(encoder->CreateNewFrame(&frame,nullptr),"PNG frame");checked(frame->Initialize(nullptr),"PNG frame initialize");checked(frame->SetSize(width,height),"PNG size");checked(frame->SetResolution(dpi,dpi),"PNG DPI");
    WICPixelFormatGUID format=GUID_WICPixelFormat32bppBGRA;checked(frame->SetPixelFormat(&format),"PNG format");
    checked(frame->WriteSource(bitmap.Get(),nullptr),"PNG source");checked(frame->Commit(),"PNG frame commit");checked(encoder->Commit(),"PNG commit");
}

int wmain(int argc,wchar_t **argv){
    if(argc<3){std::fputs("Usage: directwrite_probe.exe FONT OUTPUT_DIRECTORY [--all-glyphs] [--render]\n",stderr);return 2;}
    bool all=false,render=false;
    for(int i=3;i<argc;++i){if(!std::wcscmp(argv[i],L"--all-glyphs"))all=true;else if(!std::wcscmp(argv[i],L"--render"))render=true;else{std::fputs("Unknown option\n",stderr);return 2;}}
    fs::path input=fs::absolute(argv[1]),output=fs::absolute(argv[2]);
    fs::create_directories(output);
    fs::path reportPath=output/L"directwrite.jsonl";
    if(fs::exists(reportPath)){std::fputs("Use a new output directory\n",stderr);return 2;}
    std::ofstream log(reportPath);log<<std::setprecision(9);
    if(!log){std::fputs("Cannot create evidence report\n",stderr);return 2;}
    HRESULT apartment=CoInitializeEx(nullptr,COINIT_MULTITHREADED);
    struct Uninit {bool yes;~Uninit(){if(yes)CoUninitialize();}} uninit{SUCCEEDED(apartment)};
    try{
        checked(apartment,"CoInitializeEx"); LockedInput locked(input);
        ComPtr<IDWriteFactory6> factory;
        checked(DWriteCreateFactory(DWRITE_FACTORY_TYPE_ISOLATED,__uuidof(IDWriteFactory6),reinterpret_cast<IUnknown **>(factory.GetAddressOf())),"DWriteCreateFactory6");
        ComPtr<IDWriteFontFile> file;checked(factory->CreateFontFileReference(input.c_str(),nullptr,&file),"CreateFontFileReference");
        BOOL supported=FALSE;DWRITE_FONT_FILE_TYPE type{};DWRITE_FONT_FACE_TYPE faceType{};UINT32 faces=0;
        checked(file->Analyze(&supported,&type,&faceType,&faces),"Font Analyze");
        log<<"{\"record\":\"header\",\"schema\":1,\"input_sha256\":"<<quoted(locked.sha256)<<",\"input_bytes\":"<<locked.bytes
           <<",\"directwrite_supported\":"<<(supported?"true":"false")<<",\"physical_face_count\":"<<faces<<",\"all_glyphs\":"<<(all?"true":"false")
           <<",\"original_equality\":\"NOT_TESTED\",\"swirl_ui\":\"NOT_TESTED\",\"system_install\":\"NOT_TESTED\"}\n";
        if(!supported||!faces)throw std::runtime_error("DirectWrite rejected the input font file");
        UINT32 passed=0,failed=0;
        for(UINT32 faceIndex=0;faceIndex<faces;++faceIndex){
            try{
                ComPtr<IDWriteFontResource> resource;checked(factory->CreateFontResource(file.Get(),faceIndex,&resource),"CreateFontResource(TTC face index)");
                UINT32 n=resource->GetFontAxisCount();std::vector<DWRITE_FONT_AXIS_VALUE> defaults(n);std::vector<DWRITE_FONT_AXIS_RANGE> ranges(n);
                checked(resource->GetDefaultFontAxisValues(defaults.data(),n),"Resource defaults");checked(resource->GetFontAxisRanges(ranges.data(),n),"Resource ranges");
                auto base=instance(resource.Get(),defaults);auto axes=fvarAxes(base.Get());
                bool hasWeight=false,hasWidth=false,hasHeight=false;
                std::ostringstream axisReport;axisReport<<std::setprecision(9)<<'[';
                for(size_t a=0;a<axes.size();++a){
                    auto axis=axes[a];std::string tag=axisTag(axis.tag);hasWeight|=tag=="wght";hasWidth|=tag=="WDTH"||tag=="wdth";hasHeight|=tag=="HGHT";
                    auto r=std::find_if(ranges.begin(),ranges.end(),[&](auto x){return x.axisTag==axis.tag;});
                    auto d=std::find_if(defaults.begin(),defaults.end(),[&](auto x){return x.axisTag==axis.tag;});
                    if(r==ranges.end()||d==defaults.end()||std::abs(r->minValue-axis.lo)>1e-4f||std::abs(r->maxValue-axis.hi)>1e-4f||std::abs(d->value-axis.value)>1e-4f)
                        throw std::runtime_error("DirectWrite/fvar range or default mismatch for "+tag);
                    axisReport<<(a?",":"")<<"{\"tag\":"<<quoted(tag)<<",\"min\":"<<axis.lo<<",\"default\":"<<axis.value<<",\"max\":"<<axis.hi<<'}';
                }
                axisReport<<']';
                if(!hasWeight||!hasWidth||!hasHeight)throw std::runtime_error("Required original axes missing: wght, WDTH/wdth, HGHT");
                UINT16 glyphCount=base->GetGlyphCount();if(!glyphCount)throw std::runtime_error("No glyphs in selected face");
                std::set<UINT16> selected{0};
                if(all){for(UINT32 i=0;i<glyphCount;++i)selected.insert(UINT16(i));}
                else{for(UINT32 i=0;i<128;++i)selected.insert(UINT16(uint64_t(i)*(glyphCount-1)/127));}
                const UINT32 probes[]={0x0041,0x0061,0x0067,0x0030,0x0038,0x0025,0x4E2D,0x6587,0x53E3,0x56FD,0x570B,0x9AD4,0x9AA8,0x6E2F,0x6FB3,0x65E5,0x8A00};
                UINT16 probeGlyphs[sizeof(probes)/sizeof(probes[0])]{};checked(base->GetGlyphIndices(probes,UINT32(std::size(probes)),probeGlyphs),"Unicode probes");
                std::ostringstream cmap;cmap<<'[';for(size_t i=0;i<std::size(probes);++i){selected.insert(probeGlyphs[i]);cmap<<(i?",":"")<<"{\"codepoint\":"<<probes[i]<<",\"glyph_id\":"<<probeGlyphs[i]<<'}';}cmap<<']';
                std::vector<UINT16> glyphs(selected.begin(),selected.end());
                ComPtr<IDWriteLocalizedStrings> family,style;checked(base->GetFamilyNames(&family),"GetFamilyNames");checked(base->GetFaceNames(&style),"GetFaceNames");
                log<<"{\"record\":\"face\",\"face_index\":"<<faceIndex<<",\"family\":"<<quoted(names(family.Get()))<<",\"style\":"<<quoted(names(style.Get()))
                   <<",\"glyph_count\":"<<glyphCount<<",\"probed_glyph_count\":"<<glyphs.size()<<",\"axes\":"<<axisReport.str()<<",\"unicode_probes\":"<<cmap.str()<<"}\n";
                std::vector<std::set<uint64_t>> sweepHashes(axes.size());
                auto jobs=positions(axes);
                for(const auto &job:jobs){
                    auto face=instance(resource.Get(),job.values);auto measured=snapshot(face.Get(),glyphs);
                    std::vector<DWRITE_FONT_AXIS_VALUE> applied(face->GetFontAxisValueCount());checked(face->GetFontAxisValues(applied.data(),UINT32(applied.size())),"Applied axes");
                    if(job.sweep>=0)sweepHashes[size_t(job.sweep)].insert(measured.hash);
                    log<<"{\"record\":\"instance\",\"face_index\":"<<faceIndex<<",\"case\":"<<quoted(job.name)<<",\"requested\":"<<axisValuesJSON(job.values)
                       <<",\"applied\":"<<axisValuesJSON(applied)<<",\"outline_metrics_fnv1a64\":"<<quoted(std::to_string(measured.hash))<<",\"geometry_points\":"<<measured.points
                       <<",\"nonempty_glyphs\":"<<measured.nonempty<<",\"total_horizontal_advance_design_units\":"<<measured.totalAdvance<<",\"status\":\"PASS\"}\n";
                }
                for(size_t a=0;a<axes.size();++a)if(axes[a].hi>axes[a].lo&&sweepHashes[a].size()<2)throw std::runtime_error("No actual outline/metrics movement detected for "+axisTag(axes[a].tag));
                if(render&&faceIndex==0){
                    for(float dpi:{96.f,120.f,144.f,168.f,192.f})for(bool dark:{false,true}){
                        std::string name="face-0-default-dpi-"+std::to_string(int(dpi))+(dark?"-dark.png":"-light.png");
                        raster(base.Get(),output/fs::path(name),dpi,dark);
                        log<<"{\"record\":\"raster\",\"face_index\":0,\"dpi\":"<<dpi<<",\"scale_percent\":"<<dpi/96*100<<",\"theme\":"<<quoted(dark?"dark":"light")
                           <<",\"file\":"<<quoted(name)<<",\"sizes_dip\":[12,16,24,36],\"antialiasing\":\"grayscale\",\"purpose\":\"native_raster_capture_not_clarity_approval\"}\n";
                    }
                }
                log<<"{\"record\":\"face_result\",\"face_index\":"<<faceIndex<<",\"status\":\"PASS_NATIVE_PROBE\",\"positions\":"<<jobs.size()<<"}\n";++passed;
            }catch(const std::exception &e){log<<"{\"record\":\"face_result\",\"face_index\":"<<faceIndex<<",\"status\":\"FAILED\",\"error\":"<<quoted(e.what())<<"}\n";++failed;}
        }
        log<<"{\"record\":\"summary\",\"status\":"<<quoted(failed?"FAILED":"PASS_NATIVE_PROBE")<<",\"faces_passed\":"<<passed<<",\"faces_failed\":"<<failed
           <<",\"preservation\":\"NOT_EVALUATED\",\"clarity_review\":\"NOT_EVALUATED\",\"all_glyphs\":"<<(all?"true":"false")<<"}\n";
        if(!log)throw std::runtime_error("Evidence write failed");
        return failed?1:0;
    }catch(const std::exception &e){log<<"{\"record\":\"summary\",\"status\":\"FAILED\",\"error\":"<<quoted(e.what())<<"}\n";return 1;}
}
#endif
