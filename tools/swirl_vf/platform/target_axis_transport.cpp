// Optional authored-twin DirectWrite representation control; never a font-only
// conversion solution, original-font acceptance, or production mapping repair.
// args: normalized-control.ttc transported-control.ttc requests.tsv summary.json
// TSV: faceIndex qWidth qWeight qHeight targetWidth targetWeight targetHeight
// q is an externally supplied signed 2.14 integer, not inferred from Apple x.
// Primary APIs inspected before implementation:
// https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nf-dwrite_3-idwritefactory6-createfontresource
// https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nf-dwrite_3-idwritefontresource-createfontface
// https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/ns-dwrite_3-dwrite_font_axis_value
#include <cstdio>
#if !defined(_WIN32)
int main() {
    std::puts("{\"status\":\"NOT_RUN\",\"reason\":\"Windows DirectWrite runtime unavailable\"}");
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
#include <charconv>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <locale>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using Microsoft::WRL::ComPtr;
namespace fs = std::filesystem;
static constexpr double LIMIT = 1.0 / 32;
static constexpr std::array<DWRITE_FONT_AXIS_TAG, 3> USER_TAGS{{
    DWRITE_MAKE_FONT_AXIS_TAG('W','D','T','H'), DWRITE_MAKE_FONT_AXIS_TAG('w','g','h','t'),
    DWRITE_MAKE_FONT_AXIS_TAG('H','G','H','T')}};
static constexpr std::array<DWRITE_FONT_AXIS_TAG, 3> Q_TAGS{{
    DWRITE_MAKE_FONT_AXIS_TAG('X','W','D','T'), DWRITE_MAKE_FONT_AXIS_TAG('X','W','G','T'),
    DWRITE_MAKE_FONT_AXIS_TAG('X','H','G','T')}};
struct ProbeError final : std::runtime_error { using std::runtime_error::runtime_error; };
static void need(bool ok, const char* code) { if (!ok) throw ProbeError(code); }
static void checked(HRESULT hr, const char* code) { need(SUCCEEDED(hr), code); }
static uint32_t bits(float value) { uint32_t out; std::memcpy(&out, &value, 4); return out; }
static uint16_t be16(const uint8_t* p) { return uint16_t((uint16_t(p[0]) << 8) | p[1]); }
static uint32_t be32(const uint8_t* p) { return (uint32_t(p[0])<<24)|(uint32_t(p[1])<<16)|(uint32_t(p[2])<<8)|p[3]; }
static UINT32 tag(const uint8_t* p) { return UINT32(p[0])|(UINT32(p[1])<<8)|(UINT32(p[2])<<16)|(UINT32(p[3])<<24); }
static UINT32 tableTag(const char* p) { return tag(reinterpret_cast<const uint8_t*>(p)); }
static std::string sha(const std::vector<uint8_t>& bytes) {
    BCRYPT_ALG_HANDLE provider = nullptr;
    need(BCryptOpenAlgorithmProvider(&provider, BCRYPT_SHA256_ALGORITHM, nullptr, 0) >= 0, "sha_provider_failed");
    std::array<UCHAR,32> digest{};
    auto result = BCryptHash(provider, nullptr, 0, const_cast<PUCHAR>(bytes.data()), ULONG(bytes.size()),
                             digest.data(), ULONG(digest.size()));
    BCryptCloseAlgorithmProvider(provider, 0);
    need(result >= 0, "sha_failed");
    std::ostringstream out;
    for (auto c : digest) out << std::hex << std::setw(2) << std::setfill('0') << unsigned(c);
    return out.str();
}

struct Axis { double lo, value, hi; };
struct FaceData {
    std::map<UINT32, std::pair<UINT32, UINT32>> tables;
    std::array<Axis,3> axes;
    UINT16 glyphs = 0, upm = 0;
};
struct LockedFont {
    HANDLE handle = INVALID_HANDLE_VALUE;
    std::vector<uint8_t> bytes;
    std::vector<FaceData> faces;
    std::string digest;
    std::vector<uint8_t> read() const {
        LARGE_INTEGER size{}, zero{};
        need(GetFileSizeEx(handle, &size) && size.QuadPart >= 12 && size.QuadPart <= 64*1024*1024,
             "fixture_size_out_of_scope");
        need(SetFilePointerEx(handle, zero, nullptr, FILE_BEGIN), "fixture_seek_failed");
        std::vector<uint8_t> data(size_t(size.QuadPart));
        DWORD got = 0;
        need(ReadFile(handle, data.data(), DWORD(data.size()), &got, nullptr) && got == data.size(), "fixture_read_failed");
        return data;
    }
    const uint8_t* table(const FaceData& face, UINT32 t, size_t minimum) const {
        auto found = face.tables.find(t);
        need(found != face.tables.end() && found->second.second >= minimum, "fixture_table_missing");
        return bytes.data() + found->second.first;
    }
    LockedFont(const fs::path& path, bool normalized) {
        // Deny writes/deletion throughout hashing, loading and observations.
        handle = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING,
                             FILE_ATTRIBUTE_NORMAL, nullptr);
        need(handle != INVALID_HANDLE_VALUE, "fixture_lock_failed");
        try {
            bytes = read(); digest = sha(bytes);
            need(std::memcmp(bytes.data(), "ttcf", 4) == 0, "fixture_ttc_required");
            need(be32(bytes.data()+4) == 0x10000 || be32(bytes.data()+4) == 0x20000, "fixture_ttc_version");
            UINT32 count = be32(bytes.data()+8);
            need(count >= 1 && count <= 32 && 12 + size_t(count)*4 <= bytes.size(), "fixture_face_count");
            faces.resize(count);
            for (UINT32 index = 0; index < count; ++index) {
                size_t directory = be32(bytes.data()+12+4*index);
                need(directory <= bytes.size() && 12 <= bytes.size()-directory, "fixture_directory_range");
                need(be32(bytes.data()+directory) == 0x10000, "fixture_glyf_sfnt_required");
                UINT32 n = be16(bytes.data()+directory+4);
                need(n && n <= 256 && 12+size_t(n)*16 <= bytes.size()-directory, "fixture_table_count");
                auto& face = faces[index];
                for (UINT32 j = 0; j < n; ++j) {
                    auto p = bytes.data()+directory+12+16*j;
                    UINT32 offset=be32(p+8), length=be32(p+12);
                    need(offset <= bytes.size() && length <= bytes.size()-offset &&
                         face.tables.emplace(tag(p), std::make_pair(offset,length)).second, "fixture_table_range");
                }
                face.glyphs = be16(table(face,tableTag("maxp"),6)+4);
                face.upm = be16(table(face,tableTag("head"),20)+18);
                need(face.glyphs && face.glyphs <= 1024 && face.upm >= 16, "fixture_glyph_or_upm_scope");
                auto p = table(face,tableTag("fvar"),16);
                UINT32 offset=be16(p+4), stride=be16(p+10), length=face.tables.at(tableTag("fvar")).second;
                need(be16(p)==1 && be16(p+8)==3 && stride>=20 && offset<=length &&
                     3*stride<=length-offset, "fixture_fvar_structure");
                for (unsigned a=0; a<3; ++a) {
                    auto row=p+offset+a*stride;
                    need(tag(row)==(normalized ? Q_TAGS[a] : USER_TAGS[a]), "fixture_axis_order_or_tag");
                    face.axes[a]={int32_t(be32(row+4))/65536.0, int32_t(be32(row+8))/65536.0,
                                  int32_t(be32(row+12))/65536.0};
                    auto axis=face.axes[a];
                    need(axis.lo<axis.value && axis.value<axis.hi, "fixture_axis_range");
                    if (normalized) need(axis.lo==-1 && axis.value==0 && axis.hi==1, "normalized_fixture_range");
                    else need(axis.lo>=1 && axis.hi<=1000 && axis.lo==std::floor(axis.lo) &&
                              axis.value==std::floor(axis.value) && axis.hi==std::floor(axis.hi), "transport_fixture_integer_range");
                }
                p=table(face,tableTag("avar"),8);
                length=face.tables.at(tableTag("avar")).second;
                need(be16(p)==1 && be16(p+2)==0 && be16(p+4)==0 && be16(p+6)==3,
                     "fixture_identity_avar_header");
                size_t position=8;
                for(unsigned a=0;a<3;++a) {
                    need(position+14<=length && be16(p+position)==3, "fixture_identity_avar_records");
                    position+=2;
                    for(int q:{-16384,0,16384}) {
                        need(int16_t(be16(p+position))==q && int16_t(be16(p+position+2))==q,
                             "fixture_nonidentity_avar_not_admitted");
                        position+=4;
                    }
                }
                need(position==length, "fixture_identity_avar_extent");
            }
        } catch (...) { CloseHandle(handle); handle=INVALID_HANDLE_VALUE; throw; }
    }
    ~LockedFont() { if (handle!=INVALID_HANDLE_VALUE) CloseHandle(handle); }
    void unchanged() const { need(sha(read()) == digest, "fixture_changed_during_probe"); }
    void identity(IDWriteFontFace5* face, UINT32 index) const {
        need(index<faces.size() && face->GetIndex()==index && face->GetGlyphCount()==faces[index].glyphs &&
             face->GetSimulations()==DWRITE_FONT_SIMULATIONS_NONE, "native_physical_face_identity");
        for (auto item : faces[index].tables) {
            const void* actual=nullptr; UINT32 size=0; void* context=nullptr; BOOL exists=FALSE;
            checked(face->TryGetFontTable(item.first,&actual,&size,&context,&exists), "native_table_read_failed");
            bool equal=exists && size==item.second.second && (!size ||
                std::memcmp(actual,bytes.data()+item.second.first,size)==0);
            if (context) face->ReleaseFontTable(context);
            need(equal, "native_source_table_identity");
        }
    }
};

struct Request { UINT32 face; std::array<int,3> q; std::array<double,3> y; };
static std::vector<Request> requests(const fs::path& path) {
    std::ifstream stream(path); stream.imbue(std::locale::classic());
    need(bool(stream), "request_plan_open_failed");
    std::vector<Request> out; std::string line;
    while (std::getline(stream,line)) {
        need(!line.empty() && line.size()<=4096 && out.size()<100000, "request_plan_line_or_budget");
        std::istringstream row(line); row.imbue(std::locale::classic()); Request r{}; std::string extra;
        need(bool(row>>r.face>>r.q[0]>>r.q[1]>>r.q[2]>>r.y[0]>>r.y[1]>>r.y[2]) && !(row>>extra),
             "request_plan_fields");
        for (unsigned a=0;a<3;++a) need(r.q[a]>=-16384 && r.q[a]<=16384 && std::isfinite(r.y[a]), "request_plan_value");
        out.push_back(r);
    }
    need(stream.eof() && !out.empty(), "request_plan_incomplete");
    return out;
}

struct Geometry final : IDWriteGeometrySink {
    std::atomic<ULONG> refs{1};
    std::vector<uint32_t> structure;
    std::vector<D2D1_POINT_2F> points;
    bool finite=true;
    void point(D2D1_POINT_2F p) { finite=finite&&std::isfinite(p.x)&&std::isfinite(p.y); points.push_back(p); }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid,void** out) override {
        if (!out) return E_POINTER; *out=nullptr;
        if (iid==__uuidof(IUnknown) || iid==__uuidof(IDWriteGeometrySink)) { *out=this; AddRef(); return S_OK; }
        return E_NOINTERFACE;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++refs; }
    ULONG STDMETHODCALLTYPE Release() override { ULONG n=--refs; if(!n) delete this; return n; }
    void STDMETHODCALLTYPE SetFillMode(D2D1_FILL_MODE m) override { structure.insert(structure.end(),{1,uint32_t(m)}); }
    void STDMETHODCALLTYPE SetSegmentFlags(D2D1_PATH_SEGMENT f) override { structure.insert(structure.end(),{2,uint32_t(f)}); }
    void STDMETHODCALLTYPE BeginFigure(D2D1_POINT_2F p,D2D1_FIGURE_BEGIN b) override { structure.insert(structure.end(),{3,uint32_t(b)}); point(p); }
    void STDMETHODCALLTYPE AddLines(const D2D1_POINT_2F* p,UINT32 n) override { structure.insert(structure.end(),{4,n}); for(UINT32 i=0;i<n;++i) point(p[i]); }
    void STDMETHODCALLTYPE AddBeziers(const D2D1_BEZIER_SEGMENT* p,UINT32 n) override { structure.insert(structure.end(),{5,n}); for(UINT32 i=0;i<n;++i){point(p[i].point1);point(p[i].point2);point(p[i].point3);} }
    void STDMETHODCALLTYPE EndFigure(D2D1_FIGURE_END e) override { structure.insert(structure.end(),{6,uint32_t(e)}); }
    HRESULT STDMETHODCALLTYPE Close() override { return finite ? S_OK : E_FAIL; }
};
static ComPtr<IDWriteFontFace5> instance(IDWriteFontResource* resource,
        const std::array<DWRITE_FONT_AXIS_TAG,3>& tags, const std::array<double,3>& values,
        uint64_t& bit_checks) {
    std::array<DWRITE_FONT_AXIS_VALUE,3> submitted;
    for(unsigned a=0;a<3;++a) {
        submitted[a]={tags[a],float(values[a])};
        need(double(submitted[a].value)==values[a], "actual_FLOAT_lost_input");
        ++bit_checks;
    }
    ComPtr<IDWriteFontFace5> face;
    checked(resource->CreateFontFace(DWRITE_FONT_SIMULATIONS_NONE,submitted.data(),3,&face), "native_instance_failed");
    std::vector<DWRITE_FONT_AXIS_VALUE> actual(face->GetFontAxisValueCount());
    checked(face->GetFontAxisValues(actual.data(),UINT32(actual.size())), "native_axis_readback_failed");
    std::set<UINT32> seen;
    for(auto axis:actual) need(std::isfinite(axis.value)&&seen.insert(axis.axisTag).second, "native_axis_duplicate_or_nonfinite");
    for(auto axis:submitted) {
        auto found=std::find_if(actual.begin(),actual.end(),[&](auto v){return v.axisTag==axis.axisTag;});
        need(found!=actual.end() && bits(found->value)==bits(axis.value), "actual_FLOAT_readback_bits_differ");
        ++bit_checks;
    }
    return face;
}
static std::array<int64_t,7> fields(const DWRITE_GLYPH_METRICS& m) {
    return {{m.leftSideBearing,m.advanceWidth,m.rightSideBearing,m.topSideBearing,
             m.advanceHeight,m.bottomSideBearing,m.verticalOriginY}};
}

int wmain(int argc,wchar_t** argv) {
    uint64_t completed=0,glyphs=0,metric_fields=0,outline_pairs=0,point_pairs=0,bit_equal_points=0,axis_bits=0;
    double max_metric=0,max_geometry=0;
    std::set<UINT32> seen_faces;
    std::string left_sha,right_sha,error;
    bool pass=false,unchanged=false;
    if(argc!=5) { std::puts("{\"status\":\"FAILED\",\"error\":\"four_arguments_required\"}"); return 2; }
    try {
        LockedFont left(argv[1],true),right(argv[2],false);
        left_sha=left.digest;right_sha=right.digest;
        need(left.faces.size()==right.faces.size(), "twin_face_count_differs");
        for(size_t i=0;i<left.faces.size();++i) {
            need(left.faces[i].glyphs==right.faces[i].glyphs && left.faces[i].upm==right.faces[i].upm, "twin_glyph_or_upm_differs");
            for(auto name: {"glyf","loca","gvar","hmtx","vmtx","HVAR","VVAR","cmap"}) {
                auto a=left.faces[i].tables.find(tableTag(name)),b=right.faces[i].tables.find(tableTag(name));
                need(a!=left.faces[i].tables.end() && b!=right.faces[i].tables.end() && a->second.second==b->second.second &&
                     std::memcmp(left.bytes.data()+a->second.first,right.bytes.data()+b->second.first,a->second.second)==0,
                     "twin_protected_table_differs");
            }
        }
        auto plan=requests(argv[3]);
        ComPtr<IDWriteFactory6> factory;
        checked(DWriteCreateFactory(DWRITE_FACTORY_TYPE_ISOLATED,__uuidof(IDWriteFactory6),
                reinterpret_cast<IUnknown**>(factory.GetAddressOf())), "native_factory_failed");
        ComPtr<IDWriteFontFile> left_file,right_file;
        checked(factory->CreateFontFileReference(argv[1],nullptr,&left_file), "left_font_file_failed");
        checked(factory->CreateFontFileReference(argv[2],nullptr,&right_file), "right_font_file_failed");
        for(auto file:{left_file.Get(),right_file.Get()}) {
            BOOL supported=FALSE;DWRITE_FONT_FILE_TYPE type{};DWRITE_FONT_FACE_TYPE face_type{};UINT32 n=0;
            checked(file->Analyze(&supported,&type,&face_type,&n), "native_analyze_failed");
            need(supported && n==left.faces.size(), "native_face_count_or_support");
        }
        for(const auto& request:plan) {
            need(request.face<left.faces.size(), "request_face_out_of_range");
            std::array<double,3> normalized;
            for(unsigned a=0;a<3;++a) {
                normalized[a]=request.q[a]/16384.0;
                auto axis=right.faces[request.face].axes[a];
                double expected=axis.value+normalized[a]*(request.q[a]<0 ? axis.value-axis.lo : axis.hi-axis.value);
                need(request.y[a]==expected, "request_target_y_not_exact_q_transport");
            }
            ComPtr<IDWriteFontResource> lr,rr;
            checked(factory->CreateFontResource(left_file.Get(),request.face,&lr), "left_font_resource_failed");
            checked(factory->CreateFontResource(right_file.Get(),request.face,&rr), "right_font_resource_failed");
            auto lf=instance(lr.Get(),Q_TAGS,normalized,axis_bits),rf=instance(rr.Get(),USER_TAGS,request.y,axis_bits);
            left.identity(lf.Get(),request.face);right.identity(rf.Get(),request.face);
            auto count=left.faces[request.face].glyphs;
            std::vector<UINT16> ids(count);for(UINT32 i=0;i<count;++i) ids[i]=UINT16(i);
            std::vector<DWRITE_GLYPH_METRICS> lm(count),rm(count);
            checked(lf->GetDesignGlyphMetrics(ids.data(),count,lm.data(),FALSE), "left_native_metrics_failed");
            checked(rf->GetDesignGlyphMetrics(ids.data(),count,rm.data(),FALSE), "right_native_metrics_failed");
            for(UINT32 i=0;i<count;++i) {
                auto l=fields(lm[i]),r=fields(rm[i]);
                for(unsigned j=0;j<7;++j){max_metric=std::max(max_metric,double(std::abs(l[j]-r[j])));++metric_fields;}
                for(BOOL sideways:{FALSE,TRUE}) {
                    ComPtr<Geometry> ls,rs;ls.Attach(new Geometry);rs.Attach(new Geometry);
                    checked(lf->GetGlyphRunOutline(float(left.faces[request.face].upm),&ids[i],nullptr,nullptr,1,sideways,FALSE,ls.Get()), "left_native_outline_failed");
                    checked(rf->GetGlyphRunOutline(float(right.faces[request.face].upm),&ids[i],nullptr,nullptr,1,sideways,FALSE,rs.Get()), "right_native_outline_failed");
                    checked(ls->Close(), "left_outline_nonfinite");checked(rs->Close(), "right_outline_nonfinite");
                    need(ls->structure==rs->structure && ls->points.size()==rs->points.size(), "native_outline_topology_differs");
                    for(size_t j=0;j<ls->points.size();++j) {
                        auto p=ls->points[j],q=rs->points[j];
                        max_geometry=std::max(max_geometry,std::hypot(double(p.x)-q.x,double(p.y)-q.y));
                        bit_equal_points+=bits(p.x)==bits(q.x)&&bits(p.y)==bits(q.y);++point_pairs;
                    }
                    ++outline_pairs;
                }
                ++glyphs;
            }
            ++completed;seen_faces.insert(request.face);
        }
        left.unchanged();right.unchanged();unchanged=true;
        need(max_metric<=LIMIT && max_geometry<=LIMIT, "native_target_q_transport_exceeds_1_32");
        pass=true;
    } catch(const ProbeError& e) { error=e.what(); }
      catch(const std::exception&) { error="unexpected_probe_failure"; }
    // Error strings above are fixed codes; no paths, glyph coordinates or font
    // table data enter the public summary. Inputs remain locked until checks end.
    std::ostringstream out;out<<std::setprecision(17)
        <<"{\"schema\":1,\"status\":\""<<(pass?"PASS_SYNTHETIC_TARGET_Q_TRANSPORT":"FAILED")
        <<"\",\"backend\":\"DirectWrite_CreateFontResource\",\"data_origin\":\"self_authored_twins\","
        <<"\"role\":\"optional_q_representation_control_not_font_only_solution\","
        <<"\"original_font_acceptance\":\"NOT_RUN\",\"source_x_to_q_proven\":false,\"production_accepted\":false,"
        <<"\"windows11_acceptance\":\"NOT_RUN\",\"qt_swirl_acceptance\":\"NOT_RUN\","
        <<"\"normalized_twin_sha256\":\""<<left_sha<<"\",\"transported_twin_sha256\":\""<<right_sha
        <<"\",\"source_unchanged\":"<<(unchanged?"true":"false")<<",\"requests_completed\":"<<completed
        <<",\"physical_faces_observed\":"<<seen_faces.size()<<",\"glyph_pairs_checked\":"<<glyphs
        <<",\"metric_fields_checked\":"<<metric_fields<<",\"outline_pairs_checked\":"<<outline_pairs
        <<",\"outline_point_pairs_checked\":"<<point_pairs<<",\"bit_exact_outline_point_pairs\":"<<bit_equal_points
        <<",\"actual_FLOAT_and_readback_bits_checked\":"<<axis_bits<<",\"max_metric_error_font_units\":"<<max_metric
        <<",\"max_outline_error_font_units\":"<<max_geometry<<",\"limit_font_units\":"<<LIMIT
        <<",\"error\":\""<<error<<"\"}\n";
    auto result=out.str();
    HANDLE file=CreateFileW(argv[4],GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE) { std::puts("{\"status\":\"FAILED\",\"error\":\"summary_no_clobber_open_failed\"}");return 2; }
    DWORD wrote=0;bool saved=WriteFile(file,result.data(),DWORD(result.size()),&wrote,nullptr)&&wrote==result.size()&&FlushFileBuffers(file);
    CloseHandle(file);if(!saved) return 2;
    std::cout<<result;
    return pass?0:1;
}
#endif
