#include "CodexLaunchSupport.h"
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <wininet.h>
#include <appmodel.h>
#include <tlhelp32.h>
#include <algorithm>
#include <cwctype>

namespace CodexLaunch {
namespace {
[[noreturn]] void fail(const wchar_t *message) { throw Error{message}; }
bool equal(const std::wstring &a,const std::wstring &b) { return _wcsicmp(a.c_str(),b.c_str())==0; }
std::wstring lower(std::wstring value) { for(auto &c:value)c=std::towlower(c);return value; }
std::wstring registryText(HKEY key,const wchar_t *name) {
    DWORD bytes=0;
    const auto first=RegGetValueW(key,nullptr,name,RRF_RT_REG_SZ,nullptr,nullptr,&bytes);
    if(first==ERROR_FILE_NOT_FOUND)return {};
    if(first!=ERROR_SUCCESS || bytes>65536)fail(L"无法核对 Windows 代理字符串。");
    std::vector<wchar_t> text(bytes/sizeof(wchar_t)+1);
    if(RegGetValueW(key,nullptr,name,RRF_RT_REG_SZ,nullptr,text.data(),&bytes)!=ERROR_SUCCESS)fail(L"读取 Windows 代理失败。");
    return text.data();
}
}
Proxy parseProxy(const std::wstring &server) {
    if(server.empty() || server.size()>128)fail(L"需要单一回环 host:port 代理。");
    std::wstring host,port;
    if(server.front()==L'[') {
        const auto end=server.find(L']');
        if(end==std::wstring::npos || end+1>=server.size() || server[end+1]!=L':')fail(L"IPv6 代理格式无效。");
        host=server.substr(1,end-1);port=server.substr(end+2);
    } else {
        const auto colon=server.find(L':');
        if(colon==std::wstring::npos || server.find(L':',colon+1)!=std::wstring::npos)fail(L"需要单一回环 host:port 代理。");
        host=server.substr(0,colon);port=server.substr(colon+1);
    }
    if(port.empty() || port.size()>5 || !std::all_of(port.begin(),port.end(),[](wchar_t c){return c>=L'0' && c<=L'9';}))fail(L"代理端口无效。");
    unsigned value=0;for(auto c:port)value=value*10+unsigned(c-L'0');
    if(value==0 || value>65535)fail(L"代理端口必须在 1–65535 之间。");
    if(equal(host,L"localhost"))host=L"127.0.0.1";
    IN_ADDR ipv4{};IN6_ADDR ipv6{};wchar_t canonical[INET6_ADDRSTRLEN]{};
    if(InetPtonW(AF_INET,host.c_str(),&ipv4)==1 && (ntohl(ipv4.s_addr)>>24)==127) {
        InetNtopW(AF_INET,&ipv4,canonical,INET6_ADDRSTRLEN);host=canonical;
    } else if(InetPtonW(AF_INET6,host.c_str(),&ipv6)==1 && IN6_IS_ADDR_LOOPBACK(&ipv6)) {
        host=L"::1";
    } else fail(L"仅接受本机回环代理；不接受远程地址、凭据、PAC 或协议映射。");
    return {host,L"http://"+(host.find(L':')!=std::wstring::npos?L"["+host+L"]":host)+L":"+std::to_wstring(value),static_cast<unsigned short>(value)};
}
Proxy validateSettings(const Settings &settings) {
    if(!(settings.flags&PROXY_TYPE_PROXY) || !settings.registryEnabled)fail(L"请先在 Swirl 中连接节点并启用系统代理。纯 TUN 模式请直接启动 Codex。");
    if((settings.flags&(PROXY_TYPE_AUTO_PROXY_URL|PROXY_TYPE_AUTO_DETECT)) || !settings.pac.empty() || !settings.registryPac.empty())fail(L"存在 PAC 或自动代理；代理路径不明确，未启动 Codex。");
    const auto proxy=parseProxy(settings.server);
    if(proxy.endpoint!=parseProxy(settings.registryServer).endpoint)fail(L"WinINET 与注册表代理不一致，未启动 Codex。");
    return proxy;
}
Settings readSettings() {
    Settings settings;
    INTERNET_PER_CONN_OPTIONW options[3]{};
    options[0].dwOption=INTERNET_PER_CONN_FLAGS_UI;options[1].dwOption=INTERNET_PER_CONN_PROXY_SERVER;options[2].dwOption=INTERNET_PER_CONN_AUTOCONFIG_URL;
    INTERNET_PER_CONN_OPTION_LISTW list{};list.dwSize=sizeof(list);list.dwOptionCount=3;list.pOptions=options;
    DWORD bytes=sizeof(list);
    bool ok=InternetQueryOptionW(nullptr,INTERNET_OPTION_PER_CONNECTION_OPTION,&list,&bytes);
    if(!ok) {
        for(auto i:{1,2}){if(options[i].Value.pszValue)GlobalFree(options[i].Value.pszValue);options[i].Value.pszValue=nullptr;}
        options[0].dwOption=INTERNET_PER_CONN_FLAGS;bytes=sizeof(list);
        ok=InternetQueryOptionW(nullptr,INTERNET_OPTION_PER_CONNECTION_OPTION,&list,&bytes);
    }
    if(ok){settings.flags=options[0].Value.dwValue;if(options[1].Value.pszValue)settings.server=options[1].Value.pszValue;if(options[2].Value.pszValue)settings.pac=options[2].Value.pszValue;}
    for(auto i:{1,2})if(options[i].Value.pszValue)GlobalFree(options[i].Value.pszValue);
    if(!ok)fail(L"无法只读查询 WinINET 代理。");
    HKEY key=nullptr;
    if(RegOpenKeyExW(HKEY_CURRENT_USER,L"Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings",0,KEY_QUERY_VALUE,&key)!=ERROR_SUCCESS)fail(L"无法只读查询 Windows 代理注册表。");
    try {
        DWORD enabled=0,size=sizeof(enabled);
        const auto read=RegGetValueW(key,nullptr,L"ProxyEnable",RRF_RT_REG_DWORD,nullptr,&enabled,&size);
        if(read!=ERROR_SUCCESS && read!=ERROR_FILE_NOT_FOUND)fail(L"Windows 代理启用值格式无效。");
        settings.registryEnabled=enabled==1;
        settings.registryServer=registryText(key,L"ProxyServer");settings.registryPac=registryText(key,L"AutoConfigURL");
    } catch(...) {RegCloseKey(key);throw;}
    RegCloseKey(key);return settings;
}
std::wstring desktopPath(const std::wstring &requested) {
    if(!requested.empty()) {
        // Reject remote and device paths BEFORE touching the filesystem.
        if(requested.size()<3 || !((requested[0]>=L'A' && requested[0]<=L'Z') || (requested[0]>=L'a' && requested[0]<=L'z')) || requested[1]!=L':' || (requested[2]!=L'\\' && requested[2]!=L'/'))fail(L"Codex 路径必须是本机驱动器上的绝对路径。");
        std::vector<wchar_t> full(32768);
        const auto length=GetFullPathNameW(requested.c_str(),DWORD(full.size()),full.data(),nullptr);
        if(!length || length>=full.size())fail(L"Codex 路径无效。");
        std::wstring path=full.data();const auto name=path.substr(path.find_last_of(L"\\/")+1);
        if((!equal(name,L"ChatGPT.exe") && !equal(name,L"Codex.exe")) || lower(path).find(L"\\openai\\codex\\bin\\")!=std::wstring::npos)fail(L"请选择 Codex 桌面程序，不能选择后台 CLI。");
        const auto attributes=GetFileAttributesW(path.c_str());
        if(attributes==INVALID_FILE_ATTRIBUTES || attributes&FILE_ATTRIBUTE_DIRECTORY)fail(L"未找到 Codex 桌面 EXE。");
        return path;
    }
    UINT32 count=0,length=0;
    auto status=GetPackagesByPackageFamily(L"OpenAI.Codex_2p2nqsd0c76g0",&count,nullptr,&length,nullptr);
    if(status!=ERROR_INSUFFICIENT_BUFFER || !count)fail(L"没有找到 Codex 桌面应用。可使用 --codex 指定本机桌面 EXE。");
    std::vector<PWSTR> names(count);std::vector<wchar_t> buffer(length);
    if(GetPackagesByPackageFamily(L"OpenAI.Codex_2p2nqsd0c76g0",&count,names.data(),&length,buffer.data())!=ERROR_SUCCESS)fail(L"无法读取 Codex 安装信息。");
    UINT64 latest=0;std::wstring selected;
    for(auto name:names) {
        UINT32 idSize=0;PackageIdFromFullName(name,0,&idSize,nullptr);std::vector<BYTE> id(idSize);
        if(!idSize || PackageIdFromFullName(name,0,&idSize,id.data())!=ERROR_SUCCESS)continue;
        const auto version=reinterpret_cast<PACKAGE_ID*>(id.data())->version.Version;
        UINT32 size=0;GetPackagePathByFullName(name,&size,nullptr);std::vector<wchar_t> path(size);
        if(!size || GetPackagePathByFullName(name,&size,path.data())!=ERROR_SUCCESS)continue;
        for(const auto file:{L"\\app\\ChatGPT.exe",L"\\app\\Codex.exe"}) {
            const std::wstring candidate=std::wstring(path.data())+file;
            if(GetFileAttributesW(candidate.c_str())!=INVALID_FILE_ATTRIBUTES && (selected.empty() || version>latest)){latest=version;selected=candidate;}
        }
    }
    if(selected.empty())fail(L"Codex 安装包中没有找到桌面 EXE。");return selected;
}
unsigned existingDesktops(const std::wstring &path) {
    const auto snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);
    if(snapshot==INVALID_HANDLE_VALUE)fail(L"无法核对现有 Codex 进程。");
    unsigned count=0;PROCESSENTRY32W entry{};entry.dwSize=sizeof(entry);
    if(!Process32FirstW(snapshot,&entry)){CloseHandle(snapshot);fail(L"无法枚举进程，未启动 Codex。");}
    do {
        if(!equal(entry.szExeFile,L"ChatGPT.exe") && !equal(entry.szExeFile,L"Codex.exe"))continue;
        auto process=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,entry.th32ProcessID);
        wchar_t executable[32768]{};DWORD size=32768;
        const bool readable=process && QueryFullProcessImageNameW(process,0,executable,&size);
        if(process)CloseHandle(process);
        if(!readable){CloseHandle(snapshot);fail(L"部分 Codex 进程身份无法核对，请自行完全退出 Codex 后重试。");}
        const auto name=lower(executable);
        if(equal(executable,path) || (name.find(L"\\openai.codex_")!=std::wstring::npos && name.find(L"\\app\\")!=std::wstring::npos))++count;
    } while(Process32NextW(snapshot,&entry));
    const auto error=GetLastError();CloseHandle(snapshot);
    if(error!=ERROR_NO_MORE_FILES)fail(L"进程枚举未完成，未启动 Codex。");return count;
}
void requireListener(const Proxy &proxy) {
    WSADATA data{};if(WSAStartup(MAKEWORD(2,2),&data)!=0)fail(L"无法检查回环代理端口。");
    const bool ipv6=proxy.host.find(L':')!=std::wstring::npos;
    auto socket=::socket(ipv6?AF_INET6:AF_INET,SOCK_STREAM,IPPROTO_TCP);
    bool ok=false;
    if(socket!=INVALID_SOCKET) {
        u_long nonblocking=1;ioctlsocket(socket,FIONBIO,&nonblocking);
        SOCKADDR_STORAGE address{};int length=0;
        if(ipv6){auto *v=reinterpret_cast<sockaddr_in6*>(&address);v->sin6_family=AF_INET6;v->sin6_port=htons(proxy.port);InetPtonW(AF_INET6,proxy.host.c_str(),&v->sin6_addr);length=sizeof(*v);}
        else {auto *v=reinterpret_cast<sockaddr_in*>(&address);v->sin_family=AF_INET;v->sin_port=htons(proxy.port);InetPtonW(AF_INET,proxy.host.c_str(),&v->sin_addr);length=sizeof(*v);}
        const auto connected=connect(socket,reinterpret_cast<sockaddr*>(&address),length);
        if(connected==0)ok=true;
        else if(WSAGetLastError()==WSAEWOULDBLOCK) {
            fd_set write,error;FD_ZERO(&write);FD_ZERO(&error);FD_SET(socket,&write);FD_SET(socket,&error);timeval timeout{1,500000};
            if(select(0,nullptr,&write,&error,&timeout)>0 && FD_ISSET(socket,&write) && !FD_ISSET(socket,&error)){int code=1;int size=sizeof(code);ok=getsockopt(socket,SOL_SOCKET,SO_ERROR,reinterpret_cast<char*>(&code),&size)==0 && code==0;}
        }
        closesocket(socket);
    }
    WSACleanup();if(!ok)fail(L"系统代理端口未监听；请先连接 Swirl 节点，再启动 Codex。");
}
std::vector<std::wstring> currentEnvironment() {
    auto block=GetEnvironmentStringsW();if(!block)fail(L"无法读取当前进程环境。");
    std::vector<std::wstring> values;for(auto value=block;*value;value+=wcslen(value)+1)values.emplace_back(value);
    FreeEnvironmentStringsW(block);return values;
}
std::vector<wchar_t> childEnvironment(const std::vector<std::wstring> &parent,const Proxy &proxy) {
    std::vector<std::wstring> values;
    for(const auto &entry:parent){const auto key=lower(entry.substr(0,entry.find(L'=')));if(key!=L"http_proxy" && key!=L"https_proxy" && key!=L"all_proxy" && key!=L"no_proxy")values.push_back(entry);}
    for(const auto key:{L"HTTP_PROXY=",L"HTTPS_PROXY=",L"ALL_PROXY="})values.push_back(std::wstring(key)+proxy.endpoint);
    values.emplace_back(L"NO_PROXY=localhost,127.0.0.1,::1");
    std::sort(values.begin(),values.end(),[](const auto &a,const auto &b){return _wcsicmp(a.c_str(),b.c_str())<0;});
    std::vector<wchar_t> block;for(const auto &value:values){block.insert(block.end(),value.begin(),value.end());block.push_back(0);}block.push_back(0);return block;
}
unsigned long startChild(const std::wstring &path,std::vector<wchar_t> &environment) {
    auto command=L"\""+path+L"\"";std::vector<wchar_t> args(command.begin(),command.end());args.push_back(0);
    const auto directory=path.substr(0,path.find_last_of(L"\\/"));STARTUPINFOW startup{};startup.cb=sizeof(startup);PROCESS_INFORMATION process{};
    if(!CreateProcessW(path.c_str(),args.data(),nullptr,nullptr,FALSE,CREATE_UNICODE_ENVIRONMENT,environment.data(),directory.c_str(),&startup,&process))throw Error{L"Windows 无法创建 Codex 进程，错误 "+std::to_wstring(GetLastError())+L"。"};
    const auto pid=process.dwProcessId;CloseHandle(process.hThread);CloseHandle(process.hProcess);return pid;
}
}
