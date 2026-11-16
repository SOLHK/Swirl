// Copyright (C) 2016 basysKom GmbH.
// SPDX-License-Identifier: GPL-3.0-only
// Adapted from Qt's QTBUG-151325 regression (3459ad1d349a3a49c6ee3798d430149c6fafc270).
// Fix under test: qt/qtdeclarative 4c1054b0f997f2977a54d42523856805b309db9a.
// This standalone diagnostic is not linked into or shipped with Swirl.
#include <QCoreApplication>
#include <QQmlEngine>
#include <QQmlComponent>
#include <QVariantList>
#include <QJsonDocument>
#include <QJsonObject>
#include <QDebug>
#include <memory>
#include <private/qv4engine_p.h>
#include <private/qv4mm_p.h>
#ifdef Q_OS_WIN
#include <windows.h>
#endif

class IntListBackend : public QObject {
    Q_OBJECT
public:
    Q_INVOKABLE QVariantList ids() const { return {1, 2, 3}; }
};

int main(int argc, char **argv) {
#ifdef Q_OS_WIN
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
#endif
    QCoreApplication app(argc, argv);
    QJsonObject runtime{{"qt", QString::fromLatin1(qVersion())},
                        {"interpreter_override", qEnvironmentVariable("QV4_FORCE_INTERPRETER")}};
#ifdef Q_OS_WIN
    wchar_t modulePath[32768];
    const auto length = GetModuleFileNameW(GetModuleHandleW(L"Qt6Qml.dll"), modulePath, 32768);
    if (!length || length == 32768) return 6;
    runtime.insert("qml_module", QString::fromWCharArray(modulePath, int(length)));
#endif
    qInfo().noquote() << "JIT_GC_RUNTIME" << QJsonDocument(runtime).toJson(QJsonDocument::Compact);
    QQmlEngine engine;
    engine.handle()->memoryManager->aggressiveGC = true;
    int warnings = 0;
    QObject::connect(&engine, &QQmlEngine::warnings, &engine, [&](const auto &) { ++warnings; });
    qmlRegisterType<IntListBackend>("Test", 1, 0, "IntListBackend");
    QQmlComponent component(&engine);
    component.setData(R"(
        import QtQml
        import Test
        QtObject {
            id: root
            property var map: ({})
            property IntListBackend backend: IntListBackend {}
            function update() {
                root.map = {};
                for (const id of backend.ids()) root.map[id] = () => id;
            }
            function valid() { return map[1]()===1 && map[2]()===2 && map[3]()===3; }
        }
    )", QUrl());
    std::unique_ptr<QObject> root(component.create());
    if (!root) { qCritical() << component.errors(); return 3; }
    for (int i = 0; i < 100; ++i) {
        if (!QMetaObject::invokeMethod(root.get(), "update")) return 4;
        QVariant valid;
        if (!QMetaObject::invokeMethod(root.get(), "valid", Q_RETURN_ARG(QVariant, valid)) || !valid.toBool()) return 5;
    }
    qInfo() << "JIT_GC_RESULT" << "iterations" << 100 << "warnings" << warnings;
    return warnings ? 2 : 0;
}
#include "jit.moc"
