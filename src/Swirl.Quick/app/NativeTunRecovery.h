#pragma once
#include <QString>

enum class NativeTunRecoveryState { Clear, Pending, Unknown };

// Read-only evidence, not an ownership claim: a new engine must distinguish a
// marker inherited from a previous process from one it wrote for its own TUN.
// Unknown is not proof that capture routes are absent. No helper is launched.
NativeTunRecoveryState nativeTunRecoveryState(QString *error = nullptr);
bool setNativeTunRecoveryPending(bool pending, QString *error = nullptr);
int recoverNativeTunForMaintenance(QString *error = nullptr);
