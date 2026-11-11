#pragma once
#include <QString>
#include <QUuid>
#include <cstdio>
#include <cstdlib>

#ifdef Q_OS_WIN
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#endif

// Automated fixtures only. The random subtree is volatile, and HKCU redirection
// applies only to this process. Never use this in ordinary or preview startup.
class IsolatedUserRegistry final {
public:
    IsolatedUserRegistry()=default;
    IsolatedUserRegistry(const IsolatedUserRegistry &)=delete;
    IsolatedUserRegistry &operator=(const IsolatedUserRegistry &)=delete;
    ~IsolatedUserRegistry(){
        if(!close()){
            std::fputs("Isolated registry cleanup failed.\n",stderr);
            std::abort();
        }
    }
    bool initialize(){
#ifdef Q_OS_WIN
        if(m_overridden)return true;
        if(RegOpenCurrentUser(KEY_ALL_ACCESS|KEY_WOW64_32KEY,&m_user)!=ERROR_SUCCESS)return false;
        m_path=QStringLiteral("Software\\SwirlVolatileTests-")+QUuid::createUuid().toString(QUuid::WithoutBraces);
        if(RegCreateKeyExW(m_user,reinterpret_cast<LPCWSTR>(m_path.utf16()),0,nullptr,
            REG_OPTION_VOLATILE,KEY_ALL_ACCESS|KEY_WOW64_32KEY,nullptr,&m_fixture,nullptr)!=ERROR_SUCCESS)return false;
        if(RegOverridePredefKey(HKEY_CURRENT_USER,m_fixture)!=ERROR_SUCCESS)return false;
        m_overridden=true;
#endif
        return true;
    }
    bool close(){
#ifdef Q_OS_WIN
        if(m_overridden&&RegOverridePredefKey(HKEY_CURRENT_USER,nullptr)!=ERROR_SUCCESS)return false;
        m_overridden=false;
        if(m_fixture){RegCloseKey(m_fixture);m_fixture=nullptr;}
        const auto removed=m_user&&!m_path.isEmpty()?RegDeleteTreeW(m_user,reinterpret_cast<LPCWSTR>(m_path.utf16())):ERROR_SUCCESS;
        if(m_user){RegCloseKey(m_user);m_user=nullptr;}
        m_path.clear();
        return removed==ERROR_SUCCESS||removed==ERROR_FILE_NOT_FOUND;
#else
        return true;
#endif
    }
private:
#ifdef Q_OS_WIN
    HKEY m_user=nullptr,m_fixture=nullptr;
    QString m_path;
    bool m_overridden=false;
#endif
};
