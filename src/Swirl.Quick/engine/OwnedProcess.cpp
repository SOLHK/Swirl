#include "OwnedProcess.h"
#ifdef Q_OS_WIN
#include <windows.h>
#endif

struct OwnedProcess::Native {
#ifdef Q_OS_WIN
    HANDLE job = nullptr;
    STARTUPINFOEXW startup{};
    QByteArray attributes;
#endif
    bool ready = true;
};

OwnedProcess::OwnedProcess(QObject *parent) : QProcess(parent), m_native(new Native) {
#ifdef Q_OS_WIN
    auto &n = *m_native;
    n.ready = false;
    n.job = CreateJobObjectW(nullptr, nullptr);
    if (!n.job) return;
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!SetInformationJobObject(n.job, JobObjectExtendedLimitInformation, &limits, sizeof(limits))) return;
    SIZE_T size = 0;
    InitializeProcThreadAttributeList(nullptr, 1, 0, &size);
    n.attributes.resize(qsizetype(size));
    n.startup.lpAttributeList = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(n.attributes.data());
    if (!InitializeProcThreadAttributeList(n.startup.lpAttributeList, 1, 0, &size)) {
        n.startup.lpAttributeList = nullptr;
        return;
    }
    // PROC_THREAD_ATTRIBUTE_JOB_LIST (Windows 10+); also supported by older SDK headers.
    constexpr DWORD_PTR jobListAttribute = ProcThreadAttributeValue(13, FALSE, TRUE, FALSE);
    if (!UpdateProcThreadAttribute(n.startup.lpAttributeList, 0, jobListAttribute,
                                   &n.job, sizeof(n.job), nullptr, nullptr)) return;
    setCreateProcessArgumentsModifier([this](CreateProcessArguments *args) {
        m_native->startup.StartupInfo = *reinterpret_cast<STARTUPINFOW *>(args->startupInfo);
        m_native->startup.StartupInfo.cb = sizeof(STARTUPINFOEXW);
        args->startupInfo = reinterpret_cast<Q_STARTUPINFO *>(&m_native->startup);
        args->flags |= EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW;
    });
    n.ready = true;
#endif
}

OwnedProcess::~OwnedProcess() {
    if (state() != NotRunning) { kill(); waitForFinished(3000); }
#ifdef Q_OS_WIN
    if (m_native->startup.lpAttributeList) DeleteProcThreadAttributeList(m_native->startup.lpAttributeList);
    if (m_native->job) CloseHandle(m_native->job);
#endif
    delete m_native;
}
bool OwnedProcess::ownershipReady() const { return m_native->ready; }
