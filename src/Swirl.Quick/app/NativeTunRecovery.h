#pragma once
#include <QString>

bool setNativeTunRecoveryPending(bool pending, QString *error = nullptr);
int recoverNativeTunForMaintenance(QString *error = nullptr);
