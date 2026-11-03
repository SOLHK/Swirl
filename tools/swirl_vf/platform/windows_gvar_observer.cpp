// Direct file-backed gvar observation. Raw axis mismatches are retained;
// the independent verifier compares geometry against the REQUESTED position.
// This does not alter directwrite_probe.cpp's exact-readback failure gate.
#include <cstdio>
#if !defined(_WIN32)
int main() { std::puts("{\"status\":\"NOT_RUN\"}"); return 77; }
#else
#define NOMINMAX
#include <windows.h>
#include <dwrite_3.h>
#include <d2d1.h>
#include <wrl/client.h>
#include <atomic>
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <vector>
using Microsoft::WRL::ComPtr;
static void check(HRESULT hr) { if (FAILED(hr)) { std::ostringstream s; s << "HRESULT=" << std::hex << UINT32(hr); throw std::runtime_error(s.str()); } }
struct Outline final : IDWriteGeometrySink {
    std::atomic<ULONG> refs{1}; std::ostringstream text; unsigned count=0; bool finite=true;
    Outline() { text << std::setprecision(17) << '['; }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** p) override {
        if (!p) return E_POINTER; *p=nullptr;
        if (iid == __uuidof(IUnknown) || iid == __uuidof(IDWriteGeometrySink)) { *p=this; AddRef(); return S_OK; }
        return E_NOINTERFACE;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++refs; }
    ULONG STDMETHODCALLTYPE Release() override { auto n=--refs; if (!n) delete this; return n; }
    void start(const char* op) { text << (count++ ? "," : "") << "[\"" << op << '"'; }
    void point(D2D1_POINT_2F p) { finite &= std::isfinite(p.x) && std::isfinite(p.y); text << ',' << p.x << ',' << p.y; }
    void STDMETHODCALLTYPE SetFillMode(D2D1_FILL_MODE) override {}
    void STDMETHODCALLTYPE SetSegmentFlags(D2D1_PATH_SEGMENT) override {}
    void STDMETHODCALLTYPE BeginFigure(D2D1_POINT_2F p, D2D1_FIGURE_BEGIN) override { start("moveTo"); point(p); text << ']'; }
    void STDMETHODCALLTYPE AddLines(const D2D1_POINT_2F* p, UINT32 n) override { for (UINT32 i=0;i<n;++i) { start("lineTo"); point(p[i]); text << ']'; } }
    void STDMETHODCALLTYPE AddBeziers(const D2D1_BEZIER_SEGMENT* p, UINT32 n) override {
        for (UINT32 i=0;i<n;++i) { start("curveTo"); point(p[i].point1); point(p[i].point2); point(p[i].point3); text << ']'; }
    }
    void STDMETHODCALLTYPE EndFigure(D2D1_FIGURE_END end) override { finite &= end == D2D1_FIGURE_END_CLOSED; start("closePath"); text << ']'; }
    HRESULT STDMETHODCALLTYPE Close() override { return finite ? S_OK : E_FAIL; }
};
struct Registration {
    const wchar_t* path; int count;
    explicit Registration(const wchar_t* p) : path(p), count(AddFontResourceExW(p, FR_PRIVATE, nullptr)) {}
    ~Registration() { if (count) RemoveFontResourceExW(path, FR_PRIVATE, nullptr); }
};
int wmain(int argc, wchar_t** argv) {
    try {
        if (argc != 2) throw std::runtime_error("TTC path required");
        ComPtr<IDWriteFactory6> factory;
        check(DWriteCreateFactory(DWRITE_FACTORY_TYPE_ISOLATED, __uuidof(IDWriteFactory6), reinterpret_cast<IUnknown**>(factory.GetAddressOf())));
        ComPtr<IDWriteFontFile> file; check(factory->CreateFontFileReference(argv[1], nullptr, &file));
        BOOL supported=FALSE; DWRITE_FONT_FILE_TYPE ft{}; DWRITE_FONT_FACE_TYPE faceType{}; UINT32 faces=0;
        check(file->Analyze(&supported, &ft, &faceType, &faces));
        if (!supported || faces != 4) throw std::runtime_error("four supported physical faces required");
        Registration registration(argv[1]);
        std::cout << "{\"record\":\"header\",\"faces\":" << faces << ",\"private_GDI_registered_fonts\":" << registration.count << "}\n";
        const DWRITE_FONT_AXIS_TAG tags[] = {DWRITE_FONT_AXIS_TAG_WIDTH, DWRITE_FONT_AXIS_TAG_WEIGHT,
            DWRITE_FONT_AXIS_TAG(DWRITE_MAKE_OPENTYPE_TAG('H','G','H','T'))};
        const char* names[] = {"wdth", "wght", "HGHT"};
        unsigned id, fi, glyph, total=0, mismatchTotal=0; float width, weight, height;
        while (std::cin >> id >> fi >> glyph >> width >> weight >> height) {
            if (fi >= faces || glyph > 65535) throw std::runtime_error("invalid face/GID");
            DWRITE_FONT_AXIS_VALUE wanted[] = {{tags[0], width}, {tags[1], weight}, {tags[2], height}};
            for (auto value : wanted) if (!std::isfinite(value.value)) throw std::runtime_error("nonfinite input");
            ComPtr<IDWriteFontResource> resource; check(factory->CreateFontResource(file.Get(), fi, &resource));
            ComPtr<IDWriteFontFace5> face; check(resource->CreateFontFace(DWRITE_FONT_SIMULATIONS_NONE, wanted, 3, &face));
            if (face->GetIndex() != fi || face->GetSimulations() != DWRITE_FONT_SIMULATIONS_NONE || glyph >= face->GetGlyphCount())
                throw std::runtime_error("wrong physical face or simulation");
            std::vector<DWRITE_FONT_AXIS_VALUE> readback(face->GetFontAxisValueCount()); check(face->GetFontAxisValues(readback.data(), UINT32(readback.size())));
            unsigned mismatches=0; float maxError=0;
            for (auto request : wanted) {
                bool found=false;
                for (auto actual : readback) if (actual.axisTag == request.axisTag) {
                    if (!std::isfinite(actual.value)) throw std::runtime_error("nonfinite readback");
                    found=true; mismatches += actual.value != request.value;
                    maxError=std::max(maxError, std::abs(actual.value-request.value));
                }
                if (!found) throw std::runtime_error("missing axis");
            }
            DWRITE_FONT_METRICS metrics{}; static_cast<IDWriteFontFace*>(face.Get())->GetMetrics(&metrics);
            UINT16 gid=UINT16(glyph); DWRITE_GLYPH_METRICS gm{}; check(face->GetDesignGlyphMetrics(&gid, 1, &gm, FALSE));
            ComPtr<Outline> sink; sink.Attach(new Outline);
            check(face->GetGlyphRunOutline(float(metrics.designUnitsPerEm), &gid, nullptr, nullptr, 1, FALSE, FALSE, sink.Get())); check(sink->Close());
            std::cout << std::setprecision(17) << "{\"record\":\"outline\",\"id\":" << id << ",\"face_index\":" << fi << ",\"glyph_id\":" << glyph
                      << ",\"case\":\"request-" << id << "\",\"upm\":" << metrics.designUnitsPerEm << ",\"axes\":{";
            for (unsigned i=0;i<3;++i) std::cout << (i?",":"") << '"' << names[i] << "\":" << wanted[i].value;
            std::cout << "},\"readback_axes\":{";
            for (unsigned i=0;i<3;++i) {
                for (auto actual : readback) if (actual.axisTag == tags[i])
                    std::cout << (i?",":"") << '"' << names[i] << "\":" << actual.value;
            }
            std::cout << "},\"axis_readback_mismatches\":" << mismatches << ",\"max_axis_readback_error\":" << maxError
                      << ",\"advance_width\":" << gm.advanceWidth << ",\"commands\":" << sink->text.str() << "]}\n";
            mismatchTotal += mismatches; ++total;
        }
        if (!std::cin.eof() || !total) throw std::runtime_error("malformed requests");
        std::cout << "{\"record\":\"summary\",\"requests\":" << total << ",\"axis_readback_mismatches\":" << mismatchTotal
                  << ",\"exact_axis_gate_passed\":" << (mismatchTotal ? "false" : "true") << "}\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
#endif
