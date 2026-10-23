#pragma once
#include <QString>

// Explicit, isolated package verification. Never reads NodeStore or changes
// system proxy, DNS, TUN, or application settings.
int runRustCoreSelfTest(const QString &reportPath);
