#include "tools/CodexLaunchSupport.h"
#include <winsock2.h>
#include <ws2tcpip.h>
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
bool proxyRoundTrip(const std::wstring &endpoint,const std::wstring &originPort) {
    const auto proxy=CodexLaunch::parseProxy(endpoint.substr(7));
    const auto origin=CodexLaunch::parseProxy(L"127.0.0.1:"+originPort);
    WSADATA data{};if(WSAStartup(MAKEWORD(2,2),&data)!=0)return false;
    const bool ipv6=proxy.host.find(L':')!=std::wstring::npos;
    const auto connection=socket(ipv6?AF_INET6:AF_INET,SOCK_STREAM,IPPROTO_TCP);
    bool passed=false;
    if(connection!=INVALID_SOCKET){
        const auto deadline=GetTickCount64()+6000;
        const auto ready=[&](bool writing){
            const auto now=GetTickCount64();if(now>=deadline)return false;
            const auto remaining=deadline-now;
            timeval timeout{long(remaining/1000),long((remaining%1000)*1000)};
            fd_set read,write,error;FD_ZERO(&read);FD_ZERO(&write);FD_ZERO(&error);
            FD_SET(connection,writing?&write:&read);FD_SET(connection,&error);
            return select(0,writing?nullptr:&read,writing?&write:nullptr,&error,&timeout)>0&&!FD_ISSET(connection,&error);
        };
        do {
            u_long nonblocking=1;if(ioctlsocket(connection,FIONBIO,&nonblocking)!=0)break;
            sockaddr_storage address{};int size=0;
            if(ipv6){auto *v6=reinterpret_cast<sockaddr_in6*>(&address);v6->sin6_family=AF_INET6;v6->sin6_port=htons(proxy.port);if(InetPtonW(AF_INET6,proxy.host.c_str(),&v6->sin6_addr)!=1)break;size=sizeof(*v6);}
            else {auto *v4=reinterpret_cast<sockaddr_in*>(&address);v4->sin_family=AF_INET;v4->sin_port=htons(proxy.port);if(InetPtonW(AF_INET,proxy.host.c_str(),&v4->sin_addr)!=1)break;size=sizeof(*v4);}
            if(connect(connection,reinterpret_cast<sockaddr*>(&address),size)==SOCKET_ERROR){
                if(WSAGetLastError()!=WSAEWOULDBLOCK||!ready(true))break;
                int error=1;int bytes=sizeof(error);if(getsockopt(connection,SOL_SOCKET,SO_ERROR,reinterpret_cast<char*>(&error),&bytes)!=0||error!=0)break;
            }
            const auto authority="127.0.0.1:"+std::to_string(origin.port);
            const auto request="GET http://"+authority+"/codex-ab HTTP/1.1\r\nHost: "+authority+"\r\nConnection: close\r\n\r\n";
            size_t sent=0;
            while(sent<request.size()&&ready(true)){
                const auto count=send(connection,request.data()+sent,int(request.size()-sent),0);
                if(count>0)sent+=size_t(count);
                else if(count==0||WSAGetLastError()!=WSAEWOULDBLOCK)break;
            }
            if(sent!=request.size())break;
            std::string response;bool complete=false;
            while(response.size()<65536&&ready(false)){
                char buffer[2048];const auto count=recv(connection,buffer,int((std::min)(sizeof(buffer),size_t(65536)-response.size())),0);
                if(count==0){complete=true;break;}
                if(count<0){if(WSAGetLastError()==WSAEWOULDBLOCK)continue;break;}
                response.append(buffer,size_t(count));
            }
            const auto headers=response.find("\r\n\r\n");
            const bool okStatus=response.rfind("HTTP/1.0 200 ",0)==0||response.rfind("HTTP/1.1 200 ",0)==0;
            passed=complete&&okStatus&&headers!=std::string::npos&&response.substr(headers+4)=="swirl-codex-ab-ok\n";
        }while(false);
        closesocket(connection);
    }
    WSACleanup();return passed;
}
std::string childReport(const wchar_t *report,unsigned milliseconds) {
    const auto deadline=GetTickCount64()+milliseconds;
    while(GetTickCount64()<deadline){
        auto file=CreateFileW(report,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        if(file!=INVALID_HANDLE_VALUE){char value[4]{};DWORD read=0;const bool ok=ReadFile(file,value,4,&read,nullptr);CloseHandle(file);if(ok&&read==4)return std::string(value,4);}
        Sleep(10);
    }
    return {};
}
}
int wmain(int argc,wchar_t **argv) {
    if(variable(L"SWIRL_CODEX_TEST_CHILD")==L"1") {
        auto expected=variable(L"SWIRL_CODEX_TEST_EXPECTED_PROXY");if(expected.empty())expected=L"http://127.0.0.1:17988";
        const bool valid=variable(L"HTTP_PROXY")==expected && variable(L"HTTPS_PROXY")==expected && variable(L"ALL_PROXY")==expected && variable(L"NO_PROXY")==L"localhost,127.0.0.1,::1" && variable(L"SWIRL_CODEX_TEST_UNRELATED")==L"preserved-测试" && argc==3 && std::wstring(argv[1])==L"--proxy-server="+expected && std::wstring(argv[2])==L"--proxy-bypass-list=localhost;127.0.0.1;[::1]";
        const auto origin=variable(L"SWIRL_CODEX_TEST_ORIGIN_PORT");bool roundTrip=origin.empty();
        if(valid&&!origin.empty()){try{roundTrip=proxyRoundTrip(variable(L"HTTP_PROXY"),origin);}catch(const CodexLaunch::Error &){roundTrip=false;}}
        const char *result=!valid?"ENV!":!roundTrip?"NET!":"PASS";
        auto file=CreateFileW(variable(L"SWIRL_CODEX_TEST_REPORT").c_str(),GENERIC_WRITE,0,nullptr,TRUNCATE_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        if(file==INVALID_HANDLE_VALUE)return 2;DWORD written=0;const bool saved=WriteFile(file,result,4,&written,nullptr)&&written==4;CloseHandle(file);return saved&&valid&&roundTrip?0:1;
    }
    wchar_t report[MAX_PATH]{};
    try {
        using namespace CodexLaunch;
        const auto parentBefore=currentEnvironment();
        if(argc>1&&std::wstring(argv[1])==L"--proxy-ab"){
            require(argc==4,"usage: --proxy-ab <loopback-host:port> <origin-port>");
            const auto proxy=parseProxy(argv[2]);const auto origin=parseProxy(L"127.0.0.1:"+std::wstring(argv[3]));
            wchar_t temp[MAX_PATH]{};GetTempPathW(MAX_PATH,temp);require(GetTempFileNameW(temp,L"sca",0,report)!=0,"temp A/B report");
            auto parent=parentBefore;
            parent.erase(std::remove_if(parent.begin(),parent.end(),[](const auto &entry){return _wcsnicmp(entry.c_str(),L"SWIRL_CODEX_TEST_",17)==0;}),parent.end());
            parent.insert(parent.end(),{L"SWIRL_CODEX_TEST_CHILD=1",L"SWIRL_CODEX_TEST_UNRELATED=preserved-测试",std::wstring(L"SWIRL_CODEX_TEST_REPORT=")+report,L"SWIRL_CODEX_TEST_EXPECTED_PROXY="+proxy.endpoint,L"SWIRL_CODEX_TEST_ORIGIN_PORT="+std::to_wstring(origin.port)});
            auto environment=childEnvironment(parent,proxy);wchar_t executable[32768]{};GetModuleFileNameW(nullptr,executable,32768);
            const bool launched=startChild(executable,environment,proxy)!=0;
            const auto result=launched?childReport(report,8000):std::string();
            const bool environmentMatched=result=="PASS"||result=="NET!",originMatched=result=="PASS",unchanged=currentEnvironment()==parentBefore;
            const std::string endpoint(proxy.endpoint.begin(),proxy.endpoint.end());
            std::printf("{\"mode\":\"proxy-ab\",\"proxy\":\"%s\",\"childLaunched\":%s,\"childEnvironmentMatched\":%s,\"originResponseMatched\":%s,\"parentEnvironmentUnchanged\":%s,\"scope\":\"Actual proxy to controlled loopback origin; not Codex Desktop acceptance\"}\n",endpoint.c_str(),launched?"true":"false",environmentMatched?"true":"false",originMatched?"true":"false",unchanged?"true":"false");
            DeleteFileW(report);return launched&&environmentMatched&&originMatched&&unchanged?0:1;
        }
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
        const bool passed=childReport(report,5000)=="PASS";
        require(passed,"real child did not receive Chromium arguments, scoped proxy and preserved environment");
        require(currentEnvironment()==parentBefore,"parent environment changed");DeleteFileW(report);
        std::printf("Codex native launcher: %u assertions passed; real child environment and live/closed listener verified.\n",assertions);return 0;
    } catch(const char *error){if(*report)DeleteFileW(report);std::fprintf(stderr,"%s\n",error);return 1;}
      catch(...){if(*report)DeleteFileW(report);std::fprintf(stderr,"unexpected native launcher test failure\n");return 1;}
}
