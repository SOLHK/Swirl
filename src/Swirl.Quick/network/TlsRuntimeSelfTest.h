#pragma once
#include <QString>

// Read-only package verification; no sockets, settings or proxy ownership.
int runTlsRuntimeSelfTest(const QString &reportPath);
