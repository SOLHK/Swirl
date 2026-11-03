// Native Windows collection matching: Medium must select real wght=500.
// Uses the Microsoft DirectWrite FontSet and typographic-family interfaces.
#include <cstdio>
#if !defined(_WIN32)
int main() { std::puts("{\"status\":\"NOT_RUN\",\"reason\":\"Windows required\"}"); return 77; }
#else
#define NOMINMAX
#include <windows.h>
#include <dwrite_3.h>
#include <wrl/client.h>
#include <vector>
#include <stdexcept>
#include <iostream>
using Microsoft::WRL::ComPtr;
static void check(HRESULT hr) { if (FAILED(hr)) { std::cerr << std::hex << hr << '\n'; throw std::runtime_error("DirectWrite call failed"); } }
int wmain(int argc, wchar_t** argv) {
    try {
        if (argc != 2) throw std::runtime_error("TTC path required");
        ComPtr<IDWriteFactory6> factory;
        check(DWriteCreateFactory(DWRITE_FACTORY_TYPE_ISOLATED, __uuidof(IDWriteFactory6), reinterpret_cast<IUnknown**>(factory.GetAddressOf())));
        ComPtr<IDWriteFontFile> file; check(factory->CreateFontFileReference(argv[1], nullptr, &file));
        ComPtr<IDWriteFontSetBuilder1> builder; check(factory->CreateFontSetBuilder(&builder));
        check(builder->AddFontFile(file.Get()));
        ComPtr<IDWriteFontSet> set; check(builder->CreateFontSet(&set));
        ComPtr<IDWriteFontCollection2> collection;
        check(factory->CreateFontCollectionFromFontSet(set.Get(), DWRITE_FONT_FAMILY_MODEL_TYPOGRAPHIC, &collection));
        if (collection->GetFontFamilyCount() != 4) throw std::runtime_error("four families required");
        for (UINT32 i = 0; i < 4; ++i) {
            ComPtr<IDWriteFontFamily> family; check(collection->GetFontFamily(i, &family));
            ComPtr<IDWriteFont> font;
            check(family->GetFirstMatchingFont(DWRITE_FONT_WEIGHT_MEDIUM, DWRITE_FONT_STRETCH_NORMAL, DWRITE_FONT_STYLE_NORMAL, &font));
            ComPtr<IDWriteFontFace> base; check(font->CreateFontFace(&base));
            ComPtr<IDWriteFontFace5> face; check(base.As(&face));
            if (face->GetSimulations() != DWRITE_FONT_SIMULATIONS_NONE) throw std::runtime_error("synthetic face selected");
            std::vector<DWRITE_FONT_AXIS_VALUE> axes(face->GetFontAxisValueCount());
            check(face->GetFontAxisValues(axes.data(), UINT32(axes.size())));
            bool matched = false;
            for (const auto& axis : axes) {
                if (axis.axisTag == DWRITE_FONT_AXIS_TAG_WEIGHT) matched = axis.value == 500.f;
            }
            if (!matched) throw std::runtime_error("Medium did not select wght 500");
        }
        std::cout << "{\"status\":\"PASS\",\"families\":4,\"Medium_weight\":500,\"simulations\":false}\n";
        return 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
#endif
