#pragma once
#include <QString>
struct MihomoLogDiagnostic { QString code, message; };
// Never returns raw payload text, node names, addresses or credentials.
MihomoLogDiagnostic classifyMihomoLog(const QString &payload);
