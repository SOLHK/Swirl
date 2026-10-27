#pragma once
#include <QObject>
#include <QString>
#include <functional>

class QQuickWindow;
int runRouteBench(QQuickWindow *, const QString &);

class RouteBenchSignalTap final : public QObject {
    Q_OBJECT
public:
    using QObject::QObject;
    std::function<void()> callback;
public slots:
    void record() { if (callback) callback(); }
};
