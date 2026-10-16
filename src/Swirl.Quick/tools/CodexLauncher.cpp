#include "CodexLaunchSupport.h"
#include <windows.h>
#include <shellapi.h>
#include <string>

int WINAPI wWinMain(HINSTANCE,HINSTANCE,PWSTR,int) {
    bool check=false;HANDLE mutex=nullptr;
    try {
        int count=0;auto args=CommandLineToArgvW(GetCommandLineW(),&count);
        if(!args)throw CodexLaunch::Error{L"无法读取启动参数。"};
        std::wstring requested;bool invalid=false;
        for(int i=1;i<count;++i){const std::wstring argument=args[i];if(argument==L"--check-only")check=true;else if(argument==L"--codex" && i+1<count)requested=args[++i];else invalid=true;}
        LocalFree(args);if(invalid)throw CodexLaunch::Error{L"用法：SwirlCodexLauncher.exe [--check-only] [--codex 本机桌面EXE路径]"};
        mutex=CreateMutexW(nullptr,FALSE,L"Local\\SwirlCodexProxyLauncher");
        if(!mutex || GetLastError()==ERROR_ALREADY_EXISTS)throw CodexLaunch::Error{L"另一个 Codex 启动器正在检查，请稍后重试。"};
        const auto path=CodexLaunch::desktopPath(requested);
        const auto proxy=CodexLaunch::validateSettings(CodexLaunch::readSettings());
        CodexLaunch::requireListener(proxy);
        const auto existing=CodexLaunch::existingDesktops(path);
        if(check) {
            const std::string report="{\"checkOnly\":true,\"explicitLoopbackProxy\":true,\"listenerReady\":true,\"existingDesktopCount\":"+std::to_string(existing)+",\"launchAllowed\":"+(existing?"false":"true")+",\"persistentSettingsChanged\":false}\n";
            DWORD written=0;WriteFile(GetStdHandle(STD_OUTPUT_HANDLE),report.data(),DWORD(report.size()),&written,nullptr);
            CloseHandle(mutex);return existing?2:0;
        }
        if(existing)throw CodexLaunch::Error{L"Codex 桌面已在运行。请保存工作并自行完全退出 Codex 后，再双击此启动器。现有进程不会被停止。"};
        auto environment=CodexLaunch::childEnvironment(CodexLaunch::currentEnvironment(),proxy);
        if(CodexLaunch::validateSettings(CodexLaunch::readSettings()).endpoint!=proxy.endpoint || CodexLaunch::existingDesktops(path))throw CodexLaunch::Error{L"代理或 Codex 进程在检查期间发生变化，请重试。"};
        CodexLaunch::startChild(path,environment);CloseHandle(mutex);return 0;
    } catch(const CodexLaunch::Error &error) {
        if(mutex)CloseHandle(mutex);
        if(!check)MessageBoxW(nullptr,error.message.c_str(),L"通过 Swirl 启动 Codex",MB_OK|MB_ICONINFORMATION);
        return 3;
    } catch(...) {if(mutex)CloseHandle(mutex);if(!check)MessageBoxW(nullptr,L"启动检查失败；没有修改系统设置。",L"通过 Swirl 启动 Codex",MB_OK|MB_ICONERROR);return 4;}
}
