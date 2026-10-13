#include <QCoreApplication>
#include <QFileInfo>
#include <QDir>
#include "engine/SystemProxySession.h"
#ifdef Q_OS_WIN
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shobjidl.h>
#include <propkey.h>
#include <propvarutil.h>
#include <shlobj.h>
static int repairShortcut(const QStringList &args) {
    const auto linkPath=QFileInfo(args.at(2)),expected=QFileInfo(args.at(3)),icon=QFileInfo(args.at(4));
    if(linkPath.fileName().compare("Swirl.lnk",Qt::CaseInsensitive)||!expected.exists()||!icon.exists())return 2;
    if(FAILED(CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED)))return 3;
    IShellLinkW *link=nullptr;IPersistFile *file=nullptr;IPropertyStore *store=nullptr;
    HRESULT hr=CoCreateInstance(CLSID_ShellLink,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&link));
    if(SUCCEEDED(hr))hr=link->QueryInterface(IID_PPV_ARGS(&file));
    if(SUCCEEDED(hr))hr=file->Load(reinterpret_cast<LPCWSTR>(linkPath.absoluteFilePath().utf16()),STGM_READWRITE);
    wchar_t target[32768]{};
    if(SUCCEEDED(hr))hr=link->GetPath(target,32768,nullptr,SLGP_RAWPATH);
    // Only links targeting THIS Swirl installation may be updated. Existing
    // user pins or another application's same-named shortcut are not retargeted.
    if(SUCCEEDED(hr)&&QFileInfo(QString::fromWCharArray(target)).canonicalFilePath().compare(expected.canonicalFilePath(),Qt::CaseInsensitive))hr=E_ACCESSDENIED;
    const auto nativeIcon=QDir::toNativeSeparators(icon.absoluteFilePath());
    if(SUCCEEDED(hr))hr=link->SetIconLocation(reinterpret_cast<LPCWSTR>(nativeIcon.utf16()),0);
    if(SUCCEEDED(hr))hr=link->QueryInterface(IID_PPV_ARGS(&store));
    PROPVARIANT value{};
    if(SUCCEEDED(hr))hr=InitPropVariantFromString(L"SOLHK.Swirl.Desktop",&value);
    if(SUCCEEDED(hr))hr=store->SetValue(PKEY_AppUserModel_ID,value);
    if(SUCCEEDED(hr))hr=store->Commit();
    PropVariantClear(&value);
    if(SUCCEEDED(hr))hr=file->Save(reinterpret_cast<LPCWSTR>(linkPath.absoluteFilePath().utf16()),TRUE);
    if(SUCCEEDED(hr))SHChangeNotify(SHCNE_UPDATEITEM,SHCNF_PATHW,linkPath.absoluteFilePath().utf16(),nullptr);
    if(SUCCEEDED(hr))SHChangeNotify(SHCNE_UPDATEITEM,SHCNF_PATHW,icon.absoluteFilePath().utf16(),nullptr);
    if(store)store->Release();if(file)file->Release();if(link)link->Release();CoUninitialize();
    return SUCCEEDED(hr)?0:4;
}
#endif
int main(int argc,char **argv) {
    QCoreApplication app(argc,argv);
#ifdef Q_OS_WIN
    if(app.arguments().size()==4&&app.arguments().at(1)=="--repair-owned-pins") {
        const auto root=qEnvironmentVariable("APPDATA")+"/Microsoft/Internet Explorer/Quick Launch/User Pinned/TaskBar";
        const auto link=QDir(root).filePath("Swirl.lnk");
        if(!QFileInfo::exists(link))return 0;
        return repairShortcut({app.arguments().first(),"--repair-shortcut",link,app.arguments().at(2),app.arguments().at(3)});
    }
    if(app.arguments().size()==5&&app.arguments().at(1)=="--repair-shortcut")return repairShortcut(app.arguments());
#endif
    if(app.arguments().size()!=2)return 2;
    return SystemProxySession::guard(app.arguments().at(1));
}
