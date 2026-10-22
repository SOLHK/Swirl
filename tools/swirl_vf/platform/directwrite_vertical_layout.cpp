// Independent DirectWrite TextLayout/GPOS experiment. No font payload is stored.
// Build: cl /std:c++17 /EHsc /W4 /utf-8 directwrite_vertical_layout.cpp
//        /link dwrite.lib d2d1.lib bcrypt.lib
// The Python driver supplies only its independent geometric-symbol fixture.
// stdin: id H|V zh-CN|zh-HK vert|vrt2|vkrn default|enabled|disabled
//        WDTH wght HGHT mixed|single_han (one request per line).
// This observes real TextLayout::Draw callbacks, not a reconstructed glyph run.
// It does not certify rasterization, Windows 11, Qt, or an Apple conversion.
// API references consulted for this independent implementation:
// https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nn-dwrite_3-idwritefactory6
// https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nn-dwrite_3-idwritetextlayout4
// https://learn.microsoft.com/en-us/windows/win32/api/dwrite_2/nn-dwrite_2-idwritetextrenderer1
// https://learn.microsoft.com/en-us/windows/win32/api/dwrite_2/nf-dwrite_2-idwritetextanalyzer2-getglyphorientationtransform
#include <cstdio>
#if !defined(_WIN32)
int main() {
    std::puts("{\"type\":\"summary\",\"status\":\"NOT_RUN\",\"reason\":\"Windows DirectWrite runtime unavailable\"}");
    return 77;
}
#else
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
#include <dwrite_3.h>
#include <d2d1.h>
#include <wrl/client.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <cwchar>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using Microsoft::WRL::ComPtr;
static const wchar_t FAMILY[] = L"Swirl Original GPOS Laboratory";
static constexpr DWRITE_FONT_AXIS_TAG TAGS[] = {
    DWRITE_MAKE_FONT_AXIS_TAG('W','D','T','H'),
    DWRITE_MAKE_FONT_AXIS_TAG('w','g','h','t'),
    DWRITE_MAKE_FONT_AXIS_TAG('H','G','H','T')};
static constexpr double MINIMUM[] = {1,100,1}, DEFAULT[] = {500,400,500}, MAXIMUM[] = {1000,900,1000};

struct ProbeError final : std::runtime_error { using std::runtime_error::runtime_error; };
static void require(bool ok, const char* why) { if (!ok) throw ProbeError(why); }
static void checked(HRESULT hr, const char* where) {
    if (FAILED(hr)) {
        std::ostringstream out; out << where << ":HRESULT=0x" << std::hex << uint32_t(hr);
        throw ProbeError(out.str());
    }
}
static std::string quoted(const std::string& value) {
    std::ostringstream out; out << '"';
    for (unsigned char c : value) {
        if (c == '"' || c == '\\') out << '\\' << char(c);
        else if (c < 32) out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << unsigned(c) << std::dec;
        else out << char(c);
    }
    return out.str() + '"';
}
static std::string utf8(const wchar_t* text, size_t length) {
    if (!length) return {};
    require(length <= 4096, "oversized_UTF16_observation");
    int count = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text, int(length), nullptr, 0, nullptr, nullptr);
    require(count > 0, "invalid_UTF16_observation");
    std::string out(size_t(count), '\0');
    require(WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text, int(length), out.data(), count, nullptr, nullptr) == count,
            "UTF16_conversion_failed");
    return out;
}
static uint16_t be16(const uint8_t* p) { return uint16_t(uint16_t(p[0])*256+p[1]); }
static uint32_t be32(const uint8_t* p) { return (uint32_t(p[0])<<24)|(uint32_t(p[1])<<16)|(uint32_t(p[2])<<8)|p[3]; }
static UINT32 tag(const uint8_t* p) { return UINT32(p[0])|(UINT32(p[1])<<8)|(UINT32(p[2])<<16)|(UINT32(p[3])<<24); }
static std::string tagString(UINT32 value) {
    std::string out(4,' '); for (int i=0;i<4;++i) out[size_t(i)] = char(value>>(8*i)); return out;
}
static std::string axisJSON(const std::vector<DWRITE_FONT_AXIS_VALUE>& axes) {
    std::ostringstream out; out << std::setprecision(17) << '{';
    for (size_t i=0;i<axes.size();++i) out << (i?",":"") << quoted(tagString(axes[i].axisTag)) << ':' << axes[i].value;
    return out.str()+'}';
}
static void verifyAxes(const std::vector<DWRITE_FONT_AXIS_VALUE>& actual,
                       const std::vector<DWRITE_FONT_AXIS_VALUE>& requested) {
    std::set<UINT32> seen;
    for (const auto& a : actual) require(std::isfinite(a.value) && seen.insert(a.axisTag).second, "invalid_or_duplicate_axis_observation");
    for (const auto& wanted : requested) {
        auto found = std::find_if(actual.begin(),actual.end(),[&](auto a){return a.axisTag == wanted.axisTag;});
        require(found != actual.end() && found->value == wanted.value, "actual_layout_face_axis_ignored_or_clamped");
    }
}

// Denying writes and deletion binds hashing, collection loading and all callback
// identities to the same physical input. Keys and raw table bytes stay private.
struct LockedFixture {
    HANDLE handle = INVALID_HANDLE_VALUE;
    std::vector<uint8_t> bytes;
    std::map<UINT32,std::pair<UINT32,UINT32>> tables;
    std::string digest;
    explicit LockedFixture(const wchar_t* path) {
        handle = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
        require(handle != INVALID_HANDLE_VALUE, "cannot_lock_fixture");
        try {
            LARGE_INTEGER size{};
            require(GetFileSizeEx(handle,&size) && size.QuadPart >= 12 && size.QuadPart <= 8*1024*1024, "fixture_size_out_of_scope");
            bytes.resize(size_t(size.QuadPart)); DWORD count = 0;
            require(ReadFile(handle,bytes.data(),DWORD(bytes.size()),&count,nullptr) && count == bytes.size(), "fixture_read_failed");
            require(be32(bytes.data()) == 0x00010000, "single_TrueType_fixture_required");
            UINT32 n = be16(bytes.data()+4); require(n && 12+16*n <= bytes.size(), "invalid_sfnt_directory");
            for (UINT32 i=0;i<n;++i) {
                const uint8_t* p = bytes.data()+12+16*i;
                UINT32 offset = be32(p+8), length = be32(p+12);
                require(offset <= bytes.size() && length <= bytes.size()-offset && tables.emplace(tag(p),std::make_pair(offset,length)).second,
                        "invalid_or_duplicate_sfnt_table");
            }
            auto get = [&](UINT32 t,UINT32 minimum) -> const uint8_t* {
                auto found = tables.find(t); require(found != tables.end() && found->second.second >= minimum,"missing_fixture_identity_table");
                return bytes.data()+found->second.first;
            };
            require(be16(get(DWRITE_MAKE_OPENTYPE_TAG('m','a','x','p'),6)+4)==8, "fixture_requires_eight_glyphs");
            require(be16(get(DWRITE_MAKE_OPENTYPE_TAG('h','e','a','d'),20)+18)==1000, "fixture_requires_UPM_1000");
            const auto fvar = tables.at(DWRITE_MAKE_OPENTYPE_TAG('f','v','a','r'));
            const uint8_t* p = get(DWRITE_MAKE_OPENTYPE_TAG('f','v','a','r'),16);
            UINT32 offset = be16(p+4), stride = be16(p+10);
            require(be16(p)==1 && be16(p+8)==3 && stride>=20 && offset+3*stride<=fvar.second, "fixture_fvar_identity_mismatch");
            for (unsigned i=0;i<3;++i) {
                const uint8_t* a = p+offset+i*stride;
                require(tag(a)==TAGS[i] && int32_t(be32(a+4))/65536.0==MINIMUM[i]
                        && int32_t(be32(a+8))/65536.0==DEFAULT[i] && int32_t(be32(a+12))/65536.0==MAXIMUM[i],
                        "fixture_axis_tag_or_range_mismatch");
            }
            BCRYPT_ALG_HANDLE algorithm = nullptr;
            require(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0,"sha256_provider_failed");
            std::array<UCHAR,32> hash{};
            NTSTATUS status = BCryptHash(algorithm,nullptr,0,bytes.data(),ULONG(bytes.size()),hash.data(),ULONG(hash.size()));
            BCryptCloseAlgorithmProvider(algorithm,0);
            require(status>=0,"sha256_failed");
            std::ostringstream out;
            for (auto c : hash) out << std::hex << std::setw(2) << std::setfill('0') << unsigned(c);
            digest = out.str();
        } catch (...) { CloseHandle(handle); handle = INVALID_HANDLE_VALUE; throw; }
    }
    ~LockedFixture() { if (handle != INVALID_HANDLE_VALUE) CloseHandle(handle); }
    void verifyTables(IDWriteFontFace* face) const {
        for (const auto& entry : tables) {
            const void* data = nullptr; UINT32 size = 0; void* context = nullptr; BOOL exists = FALSE;
            checked(face->TryGetFontTable(entry.first,&data,&size,&context,&exists),"TryGetFontTable(actual_layout_face)");
            bool equal = exists && size == entry.second.second && (!size || std::memcmp(data,bytes.data()+entry.second.first,size)==0);
            if (context) face->ReleaseFontTable(context);
            require(equal,"actual_layout_face_source_table_mismatch");
        }
    }
};

struct Request {
    unsigned id = 0;
    std::string direction, locale, route, policy, textKind;
    std::array<double,3> requested{};
    std::vector<DWRITE_FONT_AXIS_VALUE> axes;
    std::wstring text;
    explicit Request(const std::string& line) {
        require(line.size()<=512,"request_line_too_long");
        std::istringstream in(line); std::string extra; long long parsedId=0;
        require(bool(in>>parsedId>>direction>>locale>>route>>policy>>requested[0]>>requested[1]>>requested[2]>>textKind) && !(in>>extra), "invalid_request_fields");
        require(parsedId>0 && parsedId<=100000, "request_id_out_of_scope"); id=unsigned(parsedId);
        require((direction=="H" || direction=="V") && (locale=="zh-CN" || locale=="zh-HK")
                && (route=="vert" || route=="vrt2" || route=="vkrn")
                && (policy=="default" || policy=="enabled" || policy=="disabled")
                && (textKind=="mixed" || textKind=="single_han"),"unsupported_layout_request");
        for (unsigned i=0;i<3;++i) {
            require(std::isfinite(requested[i]) && requested[i]>=MINIMUM[i] && requested[i]<=MAXIMUM[i],"requested_axis_out_of_range");
            axes.push_back({TAGS[i],float(requested[i])});
        }
        text = textKind=="mixed" ? L"\u4e2d AB" : L"\u4e2d";
    }
};

struct Environment {
    const LockedFixture& source;
    ComPtr<IDWriteFactory6> factory;
    ComPtr<ID2D1Factory> d2d;
    ComPtr<IDWriteTextAnalyzer2> analyzer;
    ComPtr<IDWriteFontFile> file;
    ComPtr<IDWriteFontCollection2> collection;
    ComPtr<IDWriteFontFallback> noFallback;
    ComPtr<IUnknown> loaderIdentity;
    std::vector<uint8_t> fileKey;
    explicit Environment(const LockedFixture& input,const wchar_t* path) : source(input) {
        checked(DWriteCreateFactory(DWRITE_FACTORY_TYPE_ISOLATED,__uuidof(IDWriteFactory6),reinterpret_cast<IUnknown**>(factory.GetAddressOf())),"DWriteCreateFactory6");
        checked(D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED,d2d.GetAddressOf()),"D2D1CreateFactory");
        ComPtr<IDWriteTextAnalyzer> baseAnalyzer;
        checked(factory->CreateTextAnalyzer(baseAnalyzer.GetAddressOf()),"CreateTextAnalyzer");
        checked(baseAnalyzer.As(&analyzer),"QueryInterface(TextAnalyzer2)");
        checked(factory->CreateFontFileReference(path,nullptr,file.GetAddressOf()),"CreateFontFileReference");
        BOOL supported=FALSE; DWRITE_FONT_FILE_TYPE fileType{}; DWRITE_FONT_FACE_TYPE faceType{}; UINT32 faces=0;
        checked(file->Analyze(&supported,&fileType,&faceType,&faces),"Analyze");
        require(supported && faces==1 && faceType==DWRITE_FONT_FACE_TYPE_TRUETYPE,"single_supported_TrueType_face_required");
        const void* key=nullptr; UINT32 size=0;
        checked(file->GetReferenceKey(&key,&size),"GetReferenceKey");
        require(key && size,"empty_reference_key");
        fileKey.assign(static_cast<const uint8_t*>(key),static_cast<const uint8_t*>(key)+size);
        ComPtr<IDWriteFontFileLoader> loader;
        checked(file->GetLoader(loader.GetAddressOf()),"GetLoader"); checked(loader.As(&loaderIdentity),"QueryInterface(loader identity)");
        ComPtr<IDWriteFontSetBuilder1> builder;
        checked(factory->CreateFontSetBuilder(builder.GetAddressOf()),"CreateFontSetBuilder1");
        checked(builder->AddFontFile(file.Get()),"AddFontFile");
        ComPtr<IDWriteFontSet> fontSet;
        checked(builder->CreateFontSet(fontSet.GetAddressOf()),"CreateFontSet");
        checked(factory->CreateFontCollectionFromFontSet(fontSet.Get(),DWRITE_FONT_FAMILY_MODEL_TYPOGRAPHIC,collection.GetAddressOf()),"CreateFontCollectionFromFontSet");
        UINT32 family=0; BOOL found=FALSE;
        checked(collection->FindFamilyName(FAMILY,&family,&found),"FindFamilyName");
        require(found && family==0 && collection->GetFontFamilyCount()==1,"isolated_fixture_family_not_matched");
        ComPtr<IDWriteFontFallbackBuilder> fallbackBuilder;
        checked(factory->CreateFontFallbackBuilder(fallbackBuilder.GetAddressOf()),"CreateFontFallbackBuilder");
        checked(fallbackBuilder->CreateFontFallback(noFallback.GetAddressOf()),"CreateEmptyFontFallback");
    }
    std::vector<DWRITE_FONT_AXIS_VALUE> verifyFace(IDWriteFontFace* face,const Request& request) const {
        require(face && face->GetIndex()==0 && face->GetGlyphCount()==8 && face->GetSimulations()==DWRITE_FONT_SIMULATIONS_NONE,
                "wrong_physical_face_or_font_simulation");
        UINT32 count=0; checked(face->GetFiles(&count,nullptr),"GetFiles(count)"); require(count==1,"layout_face_file_count_mismatch");
        ComPtr<IDWriteFontFile> actualFile;
        checked(face->GetFiles(&count,actualFile.GetAddressOf()),"GetFiles");
        const void* key=nullptr; UINT32 size=0;
        checked(actualFile->GetReferenceKey(&key,&size),"GetReferenceKey(actual_layout_face)");
        require(size==fileKey.size() && key && std::memcmp(key,fileKey.data(),size)==0,"layout_fallback_or_different_source_file");
        ComPtr<IDWriteFontFileLoader> loader; ComPtr<IUnknown> identity;
        checked(actualFile->GetLoader(loader.GetAddressOf()),"GetLoader(actual_layout_face)");
        checked(loader.As(&identity),"QueryInterface(actual loader identity)");
        require(identity.Get()==loaderIdentity.Get(),"layout_font_loader_mismatch");
        source.verifyTables(face);
        DWRITE_FONT_METRICS metrics{}; face->GetMetrics(&metrics); require(metrics.designUnitsPerEm==1000,"layout_UPM_mismatch");
        ComPtr<IDWriteFontFace5> axisFace; checked(face->QueryInterface(IID_PPV_ARGS(axisFace.GetAddressOf())),"QueryInterface(actual layout FontFace5)");
        require(axisFace->HasVariations(),"static_face_fallback");
        std::vector<DWRITE_FONT_AXIS_VALUE> values(axisFace->GetFontAxisValueCount());
        checked(axisFace->GetFontAxisValues(values.data(),UINT32(values.size())),"GetFontAxisValues(actual_layout_face)");
        verifyAxes(values,request.axes); return values;
    }
};

static std::string rectJSON(const D2D1_RECT_F& box) {
    require(std::isfinite(box.left) && std::isfinite(box.top) && std::isfinite(box.right) && std::isfinite(box.bottom)
            && box.left<=box.right && box.top<=box.bottom,"invalid_actual_run_geometry_bounds");
    std::ostringstream out; out << std::setprecision(17) << '[' << box.left << ',' << box.top << ',' << box.right << ',' << box.bottom << ']'; return out.str();
}

struct Renderer final : IDWriteTextRenderer1 {
    std::atomic<ULONG> refs{1};
    const Environment& env; const Request& request;
    std::vector<std::string> runs;
    std::vector<unsigned> textCoverage;
    std::string error;
    unsigned glyphCount=0;
    Renderer(const Environment& e,const Request& r) : env(e),request(r),textCoverage(r.text.size(),0) {}
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid,void** out) override {
        if (!out) return E_POINTER; *out=nullptr;
        if (iid==__uuidof(IUnknown) || iid==__uuidof(IDWritePixelSnapping) || iid==__uuidof(IDWriteTextRenderer) || iid==__uuidof(IDWriteTextRenderer1)) {
            *out=static_cast<IDWriteTextRenderer1*>(this); AddRef(); return S_OK;
        }
        return E_NOINTERFACE;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++refs; }
    ULONG STDMETHODCALLTYPE Release() override { ULONG count=--refs; if(!count) delete this; return count; }
    HRESULT STDMETHODCALLTYPE IsPixelSnappingDisabled(void*,BOOL* value) override { if(!value)return E_POINTER; *value=TRUE; return S_OK; }
    HRESULT STDMETHODCALLTYPE GetCurrentTransform(void*,DWRITE_MATRIX* value) override { if(!value)return E_POINTER; *value={1,0,0,1,0,0}; return S_OK; }
    HRESULT STDMETHODCALLTYPE GetPixelsPerDip(void*,FLOAT* value) override { if(!value)return E_POINTER; *value=1; return S_OK; }
    HRESULT STDMETHODCALLTYPE DrawGlyphRun(void* c,FLOAT x,FLOAT y,DWRITE_MEASURING_MODE m,const DWRITE_GLYPH_RUN* r,const DWRITE_GLYPH_RUN_DESCRIPTION* d,IUnknown* e) override {
        return DrawGlyphRun(c,x,y,DWRITE_GLYPH_ORIENTATION_ANGLE_0_DEGREES,m,r,d,e);
    }
    HRESULT STDMETHODCALLTYPE DrawGlyphRun(void*,FLOAT x,FLOAT y,DWRITE_GLYPH_ORIENTATION_ANGLE angle,DWRITE_MEASURING_MODE mode,
                                           const DWRITE_GLYPH_RUN* run,const DWRITE_GLYPH_RUN_DESCRIPTION* desc,IUnknown*) override {
        try {
            require(run && desc && run->glyphCount>0 && run->glyphCount<=8 && run->glyphIndices && run->glyphAdvances && run->glyphOffsets
                    && desc->clusterMap && desc->string && desc->stringLength>0 && desc->textPosition<=request.text.size()
                    && desc->stringLength<=request.text.size()-desc->textPosition
                    && std::isfinite(x) && std::isfinite(y) && run->fontEmSize==1000 && run->bidiLevel==0,"invalid_layout_callback");
            require(std::wstring(desc->string,desc->stringLength)==request.text.substr(desc->textPosition,desc->stringLength),"layout_description_text_mismatch");
            for (UINT32 i=0;i<desc->stringLength;++i)
                require(++textCoverage[desc->textPosition+i]==1,"duplicate_layout_text_range");
            auto values=env.verifyFace(run->fontFace,request);
            std::vector<DWRITE_GLYPH_METRICS> metrics(run->glyphCount);
            checked(run->fontFace->GetDesignGlyphMetrics(run->glyphIndices,run->glyphCount,metrics.data(),FALSE),"GetDesignGlyphMetrics(actual layout glyphs)");
            DWRITE_MATRIX orientation{};
            checked(env.analyzer->GetGlyphOrientationTransform(angle,run->isSideways,x,y,&orientation),"GetGlyphOrientationTransform");
            // Local GetGlyphRunOutline coordinates first receive the actual
            // callback baseline, then the official rotation about that baseline.
            D2D1_MATRIX_3X2_F transform{orientation.m11,orientation.m12,orientation.m21,orientation.m22,
                x*orientation.m11+y*orientation.m21+orientation.dx,x*orientation.m12+y*orientation.m22+orientation.dy};
            ComPtr<ID2D1PathGeometry> geometry; ComPtr<ID2D1GeometrySink> sink;
            checked(env.d2d->CreatePathGeometry(geometry.GetAddressOf()),"CreatePathGeometry");
            checked(geometry->Open(sink.GetAddressOf()),"PathGeometry.Open");
            checked(run->fontFace->GetGlyphRunOutline(run->fontEmSize,run->glyphIndices,run->glyphAdvances,run->glyphOffsets,
                run->glyphCount,run->isSideways,BOOL(run->bidiLevel&1),sink.Get()),"GetGlyphRunOutline(actual complete layout run)");
            checked(sink->Close(),"GeometrySink.Close"); UINT32 segments=0;
            checked(geometry->GetSegmentCount(&segments),"GetSegmentCount");
            std::string local="null", placed="null", relative="null";
            if (segments) {
                D2D1_RECT_F box{};
                checked(geometry->GetBounds(nullptr,&box),"GetBounds(local actual run)"); local=rectJSON(box);
                checked(geometry->GetBounds(&transform,&box),"GetBounds(placed actual run)"); placed=rectJSON(box);
                box.left-=x; box.right-=x; box.top-=y; box.bottom-=y; relative=rectJSON(box);
            }
            std::ostringstream out; out << std::setprecision(17) << "{\"text_position\":" << desc->textPosition
                << ",\"string_length\":" << desc->stringLength << ",\"locale\":" << quoted(desc->localeName?utf8(desc->localeName,std::wcslen(desc->localeName)):"")
                << ",\"baseline\":[" << x << ',' << y << "],\"orientation_angle\":" << unsigned(angle)
                << ",\"is_sideways\":" << (run->isSideways?"true":"false") << ",\"bidi_level\":" << run->bidiLevel
                << ",\"measuring_mode\":" << unsigned(mode) << ",\"font_em_size\":" << run->fontEmSize
                << ",\"source_identity_verified\":true,\"physical_face_index\":0,\"simulations\":0,\"actual_face_axes\":" << axisJSON(values)
                << ",\"orientation_transform\":[" << orientation.m11 << ',' << orientation.m12 << ',' << orientation.m21 << ',' << orientation.m22 << ',' << orientation.dx << ',' << orientation.dy
                << "],\"local_ink_bounds\":" << local << ",\"layout_ink_bounds\":" << placed << ",\"baseline_relative_ink_bounds\":" << relative << ",\"cluster_map\":[";
            for (UINT32 i=0;i<desc->stringLength;++i) { require(desc->clusterMap[i]<run->glyphCount,"cluster_map_out_of_bounds"); out << (i?",":"") << desc->clusterMap[i]; }
            out << "],\"glyphs\":[";
            for (UINT32 i=0;i<run->glyphCount;++i) {
                const auto& m=metrics[i]; const auto& o=run->glyphOffsets[i];
                require(run->glyphIndices[i]>0 && run->glyphIndices[i]<8 && std::isfinite(run->glyphAdvances[i])
                        && std::isfinite(o.advanceOffset) && std::isfinite(o.ascenderOffset),"missing_glyph_or_nonfinite_placement");
                out << (i?",":"") << "{\"gid\":" << run->glyphIndices[i] << ",\"advance\":" << run->glyphAdvances[i]
                    << ",\"advance_offset\":" << o.advanceOffset << ",\"ascender_offset\":" << o.ascenderOffset
                    << ",\"design_metrics\":{\"advance_width\":" << m.advanceWidth << ",\"advance_height\":" << m.advanceHeight
                    << ",\"left_side_bearing\":" << m.leftSideBearing << ",\"right_side_bearing\":" << m.rightSideBearing
                    << ",\"top_side_bearing\":" << m.topSideBearing << ",\"bottom_side_bearing\":" << m.bottomSideBearing
                    << ",\"vertical_origin_y\":" << m.verticalOriginY << "}}";
            }
            out << "]}"; glyphCount+=run->glyphCount; runs.push_back(out.str()); return S_OK;
        } catch (const std::exception& ex) {
            error=dynamic_cast<const ProbeError*>(&ex)?ex.what():"unexpected_native_layout_exception"; return E_FAIL;
        }
    }
    HRESULT STDMETHODCALLTYPE DrawUnderline(void*,FLOAT,FLOAT,const DWRITE_UNDERLINE*,IUnknown*) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE DrawUnderline(void*,FLOAT,FLOAT,DWRITE_GLYPH_ORIENTATION_ANGLE,const DWRITE_UNDERLINE*,IUnknown*) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE DrawStrikethrough(void*,FLOAT,FLOAT,const DWRITE_STRIKETHROUGH*,IUnknown*) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE DrawStrikethrough(void*,FLOAT,FLOAT,DWRITE_GLYPH_ORIENTATION_ANGLE,const DWRITE_STRIKETHROUGH*,IUnknown*) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE DrawInlineObject(void*,FLOAT,FLOAT,IDWriteInlineObject*,BOOL,BOOL,IUnknown*) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE DrawInlineObject(void*,FLOAT,FLOAT,DWRITE_GLYPH_ORIENTATION_ANGLE,IDWriteInlineObject*,BOOL,BOOL,IUnknown*) override { return E_NOTIMPL; }
};

static std::string observe(const Environment& env,const Request& request) {
    ComPtr<IDWriteTextFormat3> format; const wchar_t* locale=request.locale=="zh-HK"?L"zh-HK":L"zh-CN";
    checked(env.factory->CreateTextFormat(FAMILY,env.collection.Get(),request.axes.data(),UINT32(request.axes.size()),1000,locale,format.GetAddressOf()),"CreateTextFormat(axis values)");
    checked(format->SetAutomaticFontAxes(DWRITE_AUTOMATIC_FONT_AXES_NONE),"TextFormat.SetAutomaticFontAxes(NONE)");
    checked(format->SetFontFallback(env.noFallback.Get()),"SetEmptyFontFallback");
    checked(format->SetReadingDirection(request.direction=="V"?DWRITE_READING_DIRECTION_TOP_TO_BOTTOM:DWRITE_READING_DIRECTION_LEFT_TO_RIGHT),"SetReadingDirection");
    checked(format->SetFlowDirection(request.direction=="V"?DWRITE_FLOW_DIRECTION_RIGHT_TO_LEFT:DWRITE_FLOW_DIRECTION_TOP_TO_BOTTOM),"SetFlowDirection");
    checked(format->SetVerticalGlyphOrientation(DWRITE_VERTICAL_GLYPH_ORIENTATION_DEFAULT),"SetVerticalGlyphOrientation(DEFAULT)");
    checked(format->SetWordWrapping(DWRITE_WORD_WRAPPING_NO_WRAP),"SetWordWrapping");
    ComPtr<IDWriteTextLayout> base; ComPtr<IDWriteTextLayout4> layout;
    checked(env.factory->CreateTextLayout(request.text.data(),UINT32(request.text.size()),format.Get(),30000,30000,base.GetAddressOf()),"CreateTextLayout");
    checked(base.As(&layout),"QueryInterface(TextLayout4)");
    const DWRITE_TEXT_RANGE range{0,UINT32(request.text.size())};
    checked(layout->SetFontAxisValues(request.axes.data(),UINT32(request.axes.size()),range),"TextLayout.SetFontAxisValues");
    checked(layout->SetAutomaticFontAxes(DWRITE_AUTOMATIC_FONT_AXES_NONE),"TextLayout.SetAutomaticFontAxes(NONE)");
    std::vector<DWRITE_FONT_AXIS_VALUE> layoutAxes(layout->GetFontAxisValueCount(0));
    checked(layout->GetFontAxisValues(0,layoutAxes.data(),UINT32(layoutAxes.size()),nullptr),"TextLayout.GetFontAxisValues");
    verifyAxes(layoutAxes,request.axes);
    if (request.policy!="default") {
        ComPtr<IDWriteTypography> typography; checked(env.factory->CreateTypography(typography.GetAddressOf()),"CreateTypography");
        const auto* route=reinterpret_cast<const uint8_t*>(request.route.data());
        checked(typography->AddFontFeature({DWRITE_FONT_FEATURE_TAG(tag(route)),request.policy=="enabled"?1u:0u}),"AddFontFeature(route)");
        if (request.route=="vrt2" && request.policy=="enabled")
            checked(typography->AddFontFeature({DWRITE_FONT_FEATURE_TAG_VERTICAL_WRITING,0}),"AddFontFeature(disable vert for vrt2)");
        checked(layout->SetTypography(typography.Get(),range),"SetTypography");
    }
    ComPtr<Renderer> renderer; renderer.Attach(new Renderer(env,request));
    HRESULT drawn=layout->Draw(nullptr,renderer.Get(),31,47); // nonzero origin exposes incorrect transform composition
    if (!renderer->error.empty()) throw ProbeError(renderer->error);
    checked(drawn,"TextLayout.Draw");
    require(renderer->glyphCount==request.text.size() && !renderer->runs.empty(),"incomplete_true_layout_observation");
    require(std::all_of(renderer->textCoverage.begin(),renderer->textCoverage.end(),[](unsigned n){return n==1;}),"incomplete_layout_text_coverage");
    DWRITE_TEXT_METRICS metrics{}; checked(layout->GetMetrics(&metrics),"TextLayout.GetMetrics");
    require(std::isfinite(metrics.left) && std::isfinite(metrics.top) && std::isfinite(metrics.width)
            && std::isfinite(metrics.widthIncludingTrailingWhitespace) && std::isfinite(metrics.height),"nonfinite_layout_metrics");
    std::ostringstream out; out << std::setprecision(17) << "{\"type\":\"layout\",\"request_id\":" << request.id
        << ",\"direction\":" << quoted(request.direction) << ",\"locale\":" << quoted(request.locale)
        << ",\"route\":" << quoted(request.route) << ",\"policy\":" << quoted(request.policy) << ",\"text_kind\":" << quoted(request.textKind)
        << ",\"requested_user_axes\":{\"WDTH\":" << request.requested[0] << ",\"wght\":" << request.requested[1] << ",\"HGHT\":" << request.requested[2]
        << "},\"float32_input_axes\":" << axisJSON(request.axes) << ",\"layout_reported_axes\":" << axisJSON(layoutAxes)
        << ",\"layout_metrics\":{\"left\":" << metrics.left << ",\"top\":" << metrics.top << ",\"width\":" << metrics.width
        << ",\"width_including_trailing_whitespace\":" << metrics.widthIncludingTrailingWhitespace << ",\"height\":" << metrics.height
        << ",\"line_count\":" << metrics.lineCount << "},\"glyph_count\":" << renderer->glyphCount << ",\"runs\":[";
    for (size_t i=0;i<renderer->runs.size();++i) out << (i?",":"") << renderer->runs[i];
    return out.str()+"]}";
}

int wmain(int argc,wchar_t** argv) {
    unsigned currentId=0, requests=0, glyphs=0;
    try {
        require(argc==2,"usage_directwrite_vertical_layout_FONT");
        const auto path=std::filesystem::absolute(argv[1]);
        LockedFixture source(path.c_str()); Environment env(source,path.c_str());
        OSVERSIONINFOEXW version{}; version.dwOSVersionInfoSize=sizeof(version);
        using VersionFn=LONG (WINAPI*)(OSVERSIONINFOW*);
        auto versionFn=reinterpret_cast<VersionFn>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"),"RtlGetVersion"));
        require(versionFn && versionFn(reinterpret_cast<OSVERSIONINFOW*>(&version))==0,"cannot_observe_Windows_version");
        std::cout << "{\"type\":\"metadata\",\"backend\":\"DirectWrite_TextLayout4_TextRenderer1\",\"source_sha256\":" << quoted(source.digest)
            << ",\"source_bytes\":" << source.bytes.size() << ",\"physical_face_count\":1,\"glyph_count\":8,\"units_per_em\":1000,\"font_em_size_DIP\":1000"
            << ",\"font_family\":\"Swirl Original GPOS Laboratory\",\"custom_collection_only\":true,\"empty_fallback\":true,\"pixel_snapping_disabled\":true"
            << ",\"Windows_version\":{\"major\":" << version.dwMajorVersion << ",\"minor\":" << version.dwMinorVersion << ",\"build\":" << version.dwBuildNumber
            << ",\"product_type\":" << unsigned(version.wProductType) << "},\"windows_11_acceptance\":\"NOT_RUN\",\"Qt_acceptance\":\"NOT_RUN\"}" << std::endl;
        std::set<unsigned> seen; std::string line;
        while (std::getline(std::cin,line)) {
            currentId=0;
            // Recover only the integer ID for a malformed-request error; never
            // emit a caller-supplied path, raw line, table bytes or outline.
            std::istringstream id(line); id>>currentId;
            Request request(line); currentId=request.id;
            require(seen.insert(request.id).second,"duplicate_request_id");
            std::string record=observe(env,request);
            std::cout << record << std::endl; ++requests; glyphs+=unsigned(request.text.size());
        }
        require(std::cin.eof(),"request_input_stream_error");
        require(requests>0,"empty_layout_experiment");
        std::cout << "{\"type\":\"summary\",\"status\":\"ALL_REQUESTED_LAYOUT_OBSERVATIONS_COMPLETE\",\"source_sha256\":" << quoted(source.digest)
            << ",\"request_count\":" << requests << ",\"glyph_count\":" << glyphs << ",\"error_count\":0,\"font_file_locked_through_summary\":true}" << std::endl;
        return 0;
    } catch (const std::exception& error) {
        const std::string safeError=dynamic_cast<const ProbeError*>(&error)?error.what():"unexpected_native_exception";
        std::cout << "{\"type\":\"request_error\",\"request_id\":" << currentId << ",\"error\":" << quoted(safeError) << '}';
        std::cout << std::endl; return 1;
    }
}
#endif
