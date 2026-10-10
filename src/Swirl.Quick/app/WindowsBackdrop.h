#pragma once
#include <QObject>
class WindowsBackdrop final : public QObject
{
    Q_OBJECT
public:
    using QObject::QObject;
    Q_INVOKABLE void apply(QObject *window, bool enabled);
};
