#pragma once

#include <QElapsedTimer>
#include <QList>
#include <QQmlError>
#include <QSet>
#include <QString>
#include <QStringList>

class QObject;
class QQmlApplicationEngine;

struct QmlVmeWarningCapture {
    const char *phase = "setup-before-main-load";
    QElapsedTimer runtime;
    QElapsedTimer firstMatch;
    QSet<const QObject *> observedObjects;
    int capturedWarnings = 0;
    bool reporting = false;
};

void recordQmlVmeWarningContext(QQmlApplicationEngine &engine,
                                QmlVmeWarningCapture &capture,
                                const QList<QQmlError> &warnings);

#ifdef SWIRL_UI_TESTS
void recordQmlCreationLifecycle(QQmlApplicationEngine &engine, const char *phase);
#endif

QString selectQtDiagnosticLogFile(const QStringList &arguments);
void installQtDiagnosticFileHandler(const QString &logFileName);
