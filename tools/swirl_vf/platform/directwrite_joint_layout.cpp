// Authored CFF2/avar2/GSUB control through actual DirectWrite TextLayout.
// stdin: numeric-id omitted|explicit WDTH wght HGHT. No proprietary input.
// cl /std:c++17 /EHsc directwrite_joint_layout.cpp /link dwrite.lib
#include <cstdio>
#if !defined(_WIN32)
int main(){std::puts("{\"type\":\"summary\",\"status\":\"NOT_RUN\",\"reason\":\"Windows runtime unavailable\"}");return 77;}
#else
#define NOMINMAX
#include <windows.h>
#include <dwrite_3.h>
#include <d2d1.h>
#include <wrl/client.h>
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <vector>
using Microsoft::WRL::ComPtr;
static void require(bool value,const char* message){if(!value)throw std::runtime_error(message);}
static void check(HRESULT hr,const char* message){if(FAILED(hr)){std::ostringstream s;s<<message<<" HRESULT="<<std::hex<<UINT32(hr);throw std::runtime_error(s.str());}}
static UINT16 u16(const BYTE* p){return UINT16(p[0]*256+p[1]);}
static UINT32 u32(const BYTE* p){return (UINT32(p[0])<<24)|(UINT32(p[1])<<16)|(UINT32(p[2])<<8)|p[3];}
static UINT32 tag(const BYTE* p){return UINT32(p[0])|(UINT32(p[1])<<8)|(UINT32(p[2])<<16)|(UINT32(p[3])<<24);}
static const wchar_t FAMILY[]=L"Swirl Joint DirectWrite Control";

struct Fixture {
    HANDLE lock=INVALID_HANDLE_VALUE;
    std::vector<BYTE> bytes;
    std::map<UINT32,std::pair<UINT32,UINT32>> tables;
    std::vector<DWRITE_FONT_AXIS_VALUE> defaults;
    explicit Fixture(const wchar_t* path){
        lock=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,0,nullptr);
        require(lock!=INVALID_HANDLE_VALUE,"font_lock_failed");
        LARGE_INTEGER size{};require(GetFileSizeEx(lock,&size)&&size.QuadPart>12&&size.QuadPart<8*1024*1024,"authored_fixture_size_required");
        bytes.resize(size_t(size.QuadPart));DWORD read=0;
        require(ReadFile(lock,bytes.data(),DWORD(bytes.size()),&read,nullptr)&&read==bytes.size(),"font_read_failed");
        require(u32(bytes.data())==0x4f54544f,"OTTO_required");
        UINT16 n=u16(bytes.data()+4);require(12+size_t(n)*16<=bytes.size(),"bad_directory");
        for(UINT16 i=0;i<n;++i){const BYTE* p=bytes.data()+12+16*i;UINT32 a=u32(p+8),b=u32(p+12);
            require(a<=bytes.size()&&b<=bytes.size()-a&&tables.emplace(tag(p),std::make_pair(a,b)).second,"bad_table");}
        auto fvar=tables.at(DWRITE_MAKE_OPENTYPE_TAG('f','v','a','r'));const BYTE* p=bytes.data()+fvar.first;
        require(fvar.second>=16&&u16(p+8)==7&&u16(p+10)==20,"seven_authored_axes_required");
        UINT16 offset=u16(p+4);require(size_t(offset)+140<=fvar.second,"truncated_fvar");
        for(unsigned i=0;i<7;++i){const BYTE* a=p+offset+20*i;defaults.push_back({DWRITE_FONT_AXIS_TAG(tag(a)),float(int32_t(u32(a+8))/65536.0)});}
    }
    ~Fixture(){if(lock!=INVALID_HANDLE_VALUE)CloseHandle(lock);}
    void verify(IDWriteFontFace* face,const std::vector<DWRITE_FONT_AXIS_VALUE>& wanted)const{
        require(face->GetIndex()==0&&face->GetSimulations()==DWRITE_FONT_SIMULATIONS_NONE,"wrong_face_or_simulation");
        for(const char* name:{"CFF2","fvar","avar","GSUB","cmap"}){
            UINT32 t=tag(reinterpret_cast<const BYTE*>(name));auto reference=tables.at(t);
            const void* data=nullptr;UINT32 size=0;void* context=nullptr;BOOL exists=FALSE;
            check(face->TryGetFontTable(t,&data,&size,&context,&exists),"TryGetFontTable");
            bool same=exists&&size==reference.second&&std::memcmp(data,bytes.data()+reference.first,size)==0;
            if(context)face->ReleaseFontTable(context);require(same,"actual_run_table_identity_mismatch");
        }
        ComPtr<IDWriteFontFace5> variable;check(face->QueryInterface(IID_PPV_ARGS(&variable)),"FontFace5");
        std::vector<DWRITE_FONT_AXIS_VALUE> actual(variable->GetFontAxisValueCount());
        check(variable->GetFontAxisValues(actual.data(),UINT32(actual.size())),"GetFontAxisValues");
        for(auto a:wanted){auto b=std::find_if(actual.begin(),actual.end(),[&](auto x){return x.axisTag==a.axisTag;});
            require(b!=actual.end()&&b->value==a.value,"actual_axis_readback_mismatch");}
    }
};

struct Sink final:IDWriteGeometrySink {
    std::atomic<ULONG> refs{1};std::ostringstream out;unsigned count=0;bool closed=true;
    Sink(){out<<std::setprecision(17)<<'[';}
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid,void** p)override{if(!p)return E_POINTER;*p=nullptr;if(iid==__uuidof(IUnknown)||iid==__uuidof(IDWriteGeometrySink)){*p=this;AddRef();return S_OK;}return E_NOINTERFACE;}
    ULONG STDMETHODCALLTYPE AddRef()override{return ++refs;} ULONG STDMETHODCALLTYPE Release()override{auto n=--refs;if(!n)delete this;return n;}
    void start(const char* name){out<<(count++?",":"")<<"[\""<<name<<'"';}
    void point(D2D1_POINT_2F p){require(std::isfinite(p.x)&&std::isfinite(p.y),"nonfinite_outline");out<<','<<p.x<<','<<-p.y;}
    void STDMETHODCALLTYPE SetFillMode(D2D1_FILL_MODE)override{} void STDMETHODCALLTYPE SetSegmentFlags(D2D1_PATH_SEGMENT)override{}
    void STDMETHODCALLTYPE BeginFigure(D2D1_POINT_2F p,D2D1_FIGURE_BEGIN)override{start("moveTo");point(p);out<<']';}
    void STDMETHODCALLTYPE AddLines(const D2D1_POINT_2F* p,UINT32 n)override{for(UINT32 i=0;i<n;++i){start("lineTo");point(p[i]);out<<']';}}
    void STDMETHODCALLTYPE AddBeziers(const D2D1_BEZIER_SEGMENT* b,UINT32 n)override{for(UINT32 i=0;i<n;++i){start("curveTo");point(b[i].point1);point(b[i].point2);point(b[i].point3);out<<']';}}
    void STDMETHODCALLTYPE EndFigure(D2D1_FIGURE_END end)override{closed&=end==D2D1_FIGURE_END_CLOSED;start("closePath");out<<']';}
    HRESULT STDMETHODCALLTYPE Close()override{return count&&closed?S_OK:E_FAIL;}
};

struct Renderer final:IDWriteTextRenderer {
    std::atomic<ULONG> refs{1};const Fixture& fixture;std::vector<DWRITE_FONT_AXIS_VALUE> axes;
    std::string error,commands;UINT16 gid=0;float advance=0;unsigned runs=0;
    Renderer(const Fixture& f,std::vector<DWRITE_FONT_AXIS_VALUE> a):fixture(f),axes(std::move(a)){}
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid,void** p)override{if(!p)return E_POINTER;*p=nullptr;if(iid==__uuidof(IUnknown)||iid==__uuidof(IDWritePixelSnapping)||iid==__uuidof(IDWriteTextRenderer)){*p=this;AddRef();return S_OK;}return E_NOINTERFACE;}
    ULONG STDMETHODCALLTYPE AddRef()override{return ++refs;} ULONG STDMETHODCALLTYPE Release()override{auto n=--refs;if(!n)delete this;return n;}
    HRESULT STDMETHODCALLTYPE IsPixelSnappingDisabled(void*,BOOL* p)override{*p=TRUE;return S_OK;}
    HRESULT STDMETHODCALLTYPE GetCurrentTransform(void*,DWRITE_MATRIX* p)override{*p={1,0,0,1,0,0};return S_OK;}
    HRESULT STDMETHODCALLTYPE GetPixelsPerDip(void*,FLOAT* p)override{*p=1;return S_OK;}
    HRESULT STDMETHODCALLTYPE DrawGlyphRun(void*,FLOAT,FLOAT,DWRITE_MEASURING_MODE,const DWRITE_GLYPH_RUN* r,const DWRITE_GLYPH_RUN_DESCRIPTION*,IUnknown*)override{
        try{require(r&&r->glyphCount==1&&r->fontEmSize==1000&&!r->isSideways&&!r->bidiLevel,"unexpected_layout_run");fixture.verify(r->fontFace,axes);
            ComPtr<Sink> sink;sink.Attach(new Sink);check(r->fontFace->GetGlyphRunOutline(1000,r->glyphIndices,nullptr,nullptr,1,FALSE,FALSE,sink.Get()),"GetGlyphRunOutline");check(sink->Close(),"outline_close");
            commands=sink->out.str()+']';gid=r->glyphIndices[0];advance=r->glyphAdvances[0];++runs;return S_OK;
        }catch(const std::exception& e){error=e.what();return E_FAIL;}}
    HRESULT STDMETHODCALLTYPE DrawUnderline(void*,FLOAT,FLOAT,const DWRITE_UNDERLINE*,IUnknown*)override{return E_NOTIMPL;}
    HRESULT STDMETHODCALLTYPE DrawStrikethrough(void*,FLOAT,FLOAT,const DWRITE_STRIKETHROUGH*,IUnknown*)override{return E_NOTIMPL;}
    HRESULT STDMETHODCALLTYPE DrawInlineObject(void*,FLOAT,FLOAT,IDWriteInlineObject*,BOOL,BOOL,IUnknown*)override{return E_NOTIMPL;}
};

int wmain(int argc,wchar_t** argv){
    try{require(argc==2,"font_path_required");Fixture fixture(argv[1]);ComPtr<IDWriteFactory6> factory;
        check(DWriteCreateFactory(DWRITE_FACTORY_TYPE_ISOLATED,__uuidof(IDWriteFactory6),reinterpret_cast<IUnknown**>(factory.GetAddressOf())),"CreateFactory6");
        ComPtr<IDWriteFontFile> file;check(factory->CreateFontFileReference(argv[1],nullptr,&file),"CreateFontFileReference");
        ComPtr<IDWriteFontSetBuilder1> builder;check(factory->CreateFontSetBuilder(&builder),"CreateFontSetBuilder");check(builder->AddFontFile(file.Get()),"AddFontFile");
        ComPtr<IDWriteFontSet> set;check(builder->CreateFontSet(&set),"CreateFontSet");ComPtr<IDWriteFontCollection2> collection;
        check(factory->CreateFontCollectionFromFontSet(set.Get(),DWRITE_FONT_FAMILY_MODEL_TYPOGRAPHIC,&collection),"CreateFontCollection");
        ComPtr<IDWriteFontFallbackBuilder> fb;ComPtr<IDWriteFontFallback> fallback;check(factory->CreateFontFallbackBuilder(&fb),"FallbackBuilder");check(fb->CreateFontFallback(&fallback),"EmptyFallback");
        OSVERSIONINFOEXW version{};version.dwOSVersionInfoSize=sizeof(version);using Version=LONG(WINAPI*)(OSVERSIONINFOW*);
        auto v=reinterpret_cast<Version>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"),"RtlGetVersion"));require(v&&v(reinterpret_cast<OSVERSIONINFOW*>(&version))==0,"Windows_version_query_failed");
        std::cout<<"{\"type\":\"metadata\",\"Windows_build\":"<<version.dwBuildNumber<<",\"product_type\":"<<unsigned(version.wProductType)<<",\"backend\":\"DirectWrite_TextLayout4\"}"<<std::endl;
        unsigned id,total=0;std::string mode;float x,y,z;
        while(std::cin>>id>>mode>>x>>y>>z){require(mode=="omitted"||mode=="explicit","invalid_axis_mode");auto axes=fixture.defaults;axes[0].value=x;axes[1].value=y;axes[2].value=z;
            auto supplied=axes;if(mode=="omitted")supplied.resize(3);
            ComPtr<IDWriteTextFormat3> format;check(factory->CreateTextFormat(FAMILY,collection.Get(),supplied.data(),UINT32(supplied.size()),1000,L"en-US",&format),"CreateTextFormat");
            check(format->SetAutomaticFontAxes(DWRITE_AUTOMATIC_FONT_AXES_NONE),"DisableAutomaticAxes");check(format->SetFontFallback(fallback.Get()),"SetEmptyFallback");
            ComPtr<IDWriteTextLayout> base;check(factory->CreateTextLayout(L"A",1,format.Get(),10000,10000,&base),"CreateTextLayout");ComPtr<IDWriteTextLayout4> layout;check(base.As(&layout),"TextLayout4");
            check(layout->SetFontAxisValues(supplied.data(),UINT32(supplied.size()),{0,1}),"SetFontAxisValues");check(layout->SetAutomaticFontAxes(DWRITE_AUTOMATIC_FONT_AXES_NONE),"LayoutAutomaticAxes");
            ComPtr<Renderer> renderer;renderer.Attach(new Renderer(fixture,axes));HRESULT hr=layout->Draw(nullptr,renderer.Get(),0,0);
            if(!renderer->error.empty())throw std::runtime_error(renderer->error);check(hr,"TextLayoutDraw");require(renderer->runs==1,"missing_or_multiple_runs");
            std::cout<<std::setprecision(17)<<"{\"type\":\"sample\",\"id\":"<<id<<",\"gid\":"<<renderer->gid<<",\"advance\":"<<renderer->advance<<",\"commands\":"<<renderer->commands<<'}'<<std::endl;++total;
        }
        require(std::cin.eof()&&total,"malformed_or_empty_requests");std::cout<<"{\"type\":\"summary\",\"requests\":"<<total<<",\"actual_tables_and_axes_verified\":true}"<<std::endl;return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<std::endl;return 1;}
}
#endif
