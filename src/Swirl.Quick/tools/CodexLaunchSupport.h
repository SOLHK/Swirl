#pragma once
#include <string>
#include <vector>

namespace CodexLaunch {
struct Error { std::wstring message; };
struct Proxy { std::wstring host, endpoint; unsigned short port; };
struct Settings { unsigned flags=0; bool registryEnabled=false; std::wstring server, registryServer, pac, registryPac; };
Proxy parseProxy(const std::wstring &server);
Proxy validateSettings(const Settings &settings);
Settings readSettings();
std::wstring desktopPath(const std::wstring &requested={});
unsigned existingDesktops(const std::wstring &path);
void requireListener(const Proxy &proxy);
std::vector<wchar_t> childEnvironment(const std::vector<std::wstring> &parent, const Proxy &proxy);
std::vector<std::wstring> currentEnvironment();
unsigned long startChild(const std::wstring &path, std::vector<wchar_t> &environment, const Proxy &proxy);
}
