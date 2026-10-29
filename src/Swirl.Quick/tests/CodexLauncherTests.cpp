#include "tools/CodexLaunchSupport.h"
#include <winsock2.h>
#include <windows.h>
#include <wininet.h>
#include <algorithm>
#include <cstdio>
#include <functional>

namespace {
unsigned assertions=0;
void require(bool condition,const char *message){if(!condition)throw message;++assertions;}
void rejected(const std::function<void()> &action){bool failed=false;try{action();}catch(const CodexLaunch::Error &){failed=true;}require(failed,"unsafe input accepted");}
std::wstring variable(const wchar_t *name){wchar_t value[32768]{};GetEnvironmentVariableW(name,value,32768);return value;}
}
int wmain(int argc,wchar_t **argv) {
    if(variable(L"SWIRL_CODEX_TEST_CHILD")==L"1") {
        const bool valid=variable(L"HTTP_PROXY")==L"http://127.0.0.1:17988" && variable(L"HTTPS_PROXY")==L"http://127.0.0.1:17988" && variable(L"ALL_PROXY")==L"http://127.0.0.1:17988" && variable(L"NO_PROXY")==L"localhost,127.0.0.1,::1" && variable(L"SWIRL_CODEX_TEST_UNRELATED")==L"preserved-测试" && argc==3 && std::wstring(argv[1])==L"--proxy-server=http://127.0.0.1:17988" && std::wstring(argv[2])==L"--proxy-bypass-list=localhost;127.0.0.1;[::1]";
        auto file=CreateFileW(variable(L"SWIRL_CODEX_TEST_REPORT").c_str(),GENERIC_WRITE,0,nullptr,TRUNCATE_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        if(file==INVALID_HANDLE_VALUE)return 2;DWORD written=0;WriteFile(file,valid?"PASS":"FAIL",4,&written,nullptr);CloseHandle(file);return valid?0:1;
    }
    wchar_t report[MAX_PATH]{};
    try {
        using namespace CodexLaunch;
        const auto parentBefore=currentEnvironment();
        require(parseProxy(L"localhost:7897").endpoint==L"http://127.0.0.1:7897","localhost normalization");
        require(parseProxy(L"[0:0:0:0:0:0:0:1]:17988").endpoint==L"http://[::1]:17988","IPv6 normalization");
        for(const auto bad:{L"127.0.0.1:0",L"127.0.0.1:65536",L"127.0.0.1:1\n",L"127.0.0.999:7897",L"192.168.0.1:7897",L"example.com:7897",L"user:secret@127.0.0.1:7897",L"http=127.0.0.1:7897;https=127.0.0.1:7898",L"127.0.0.1:7897/path",L"[::2]:7897",L"127.0.0.1:+7897"})rejected([&]{parseProxy(bad);});
        Settings settings{3,true,L"127.0.0.1:17988",L"localhost:17988",L"",L""};
        require(validateSettings(settings).port==17988,"consistent settings rejected");
        settings.flags=11;rejected([&]{validateSettings(settings);});settings.flags=3;
        settings.registryEnabled=false;rejected([&]{validateSettings(settings);});settings.registryEnabled=true;
        settings.pac=L"https://private.invalid/pac";rejected([&]{validateSettings(settings);});settings.pac.clear();
        settings.registryPac=L"https://private.invalid/pac";rejected([&]{validateSettings(settings);});settings.registryPac.clear();
        settings.registryServer=L"127.0.0.1:7897";rejected([&]{validateSettings(settings);});
        for(const auto path:{L"\\\\server.invalid\\share\\Codex.exe",L"//server.invalid/share/Codex.exe",L"\\\\?\\C:\\Codex.exe",L"//?/C:/Codex.exe",L"Codex.exe",L"C:Codex.exe",L"C:\\Users\\example\\AppData\\Local\\OpenAI\\Codex\\bin\\v1\\codex.exe"})rejected([&]{desktopPath(path);});
        WSADATA data{};require(WSAStartup(MAKEWORD(2,2),&data)==0,"Winsock startup");
        auto listener=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);sockaddr_in address{};address.sin_family=AF_INET;address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
        require(bind(listener,reinterpret_cast<sockaddr*>(&address),sizeof(address))==0 && listen(listener,2)==0,"fixture listen");int size=sizeof(address);getsockname(listener,reinterpret_cast<sockaddr*>(&address),&size);
        const auto proxy=parseProxy(L"127.0.0.1:"+std::to_wstring(ntohs(address.sin_port)));requireListener(proxy);++assertions;closesocket(listener);rejected([&]{requireListener(proxy);});WSACleanup();
        wchar_t temp[MAX_PATH]{};GetTempPathW(MAX_PATH,temp);require(GetTempFileNameW(temp,L"scl",0,report)!=0,"temp report");
        auto parent=parentBefore;
        parent.insert(parent.end(),{L"http_proxy=http://stale.invalid:1",L"HTTPS_PROXY=http://stale.invalid:2",L"all_proxy=socks5://stale.invalid:3",L"NO_PROXY=*",L"SWIRL_CODEX_TEST_CHILD=1",L"SWIRL_CODEX_TEST_UNRELATED=preserved-测试",std::wstring(L"SWIRL_CODEX_TEST_REPORT=")+report});
        auto block=childEnvironment(parent,parseProxy(L"127.0.0.1:17988"));
        require(block.size()>2 && block.back()==0 && block[block.size()-2]==0,"environment double NUL");
        wchar_t executable[32768]{};GetModuleFileNameW(nullptr,executable,32768);
        auto unsafeProxy=parseProxy(L"127.0.0.1:17988");unsafeProxy.endpoint=L"http://127.0.0.1:17988 --no-proxy-server";
        rejected([&]{startChild(executable,block,unsafeProxy);});
        rejected([&]{startChild(L"C:\\Codex\" --no-proxy-server",block,parseProxy(L"127.0.0.1:17988"));});
        require(startChild(executable,block,parseProxy(L"127.0.0.1:17988"))!=0,"child creation");
        bool passed=false;
        for(int i=0;i<500 && !passed;++i) {
            auto file=CreateFileW(report,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
            if(file!=INVALID_HANDLE_VALUE){char value[5]{};DWORD read=0;ReadFile(file,value,4,&read,nullptr);CloseHandle(file);if(read==4){passed=std::string(value)=="PASS";break;}}
            Sleep(10);
        }
        require(passed,"real child did not receive Chromium arguments, scoped proxy and preserved environment");
        require(currentEnvironment()==parentBefore,"parent environment changed");DeleteFileW(report);
        std::printf("Codex native launcher: %u assertions passed; real child environment and live/closed listener verified.\n",assertions);return 0;
    } catch(const char *error){if(*report)DeleteFileW(report);std::fprintf(stderr,"%s\n",error);return 1;}
      catch(...){if(*report)DeleteFileW(report);std::fprintf(stderr,"unexpected native launcher test failure\n");return 1;}
}
