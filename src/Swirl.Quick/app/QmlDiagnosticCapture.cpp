#include "QmlDiagnosticCapture.h"
#include "SwirlBuildIdentity.h"

#include <QCoreApplication>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMetaEnum>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQmlIncubationController>
#include <QQuickItem>
#include <QRegularExpression>
#include <QScopedValueRollback>
#include <QTextStream>

#include <QtQml/private/qqmlcontextdata_p.h>
#include <QtQml/private/qqmldata_p.h>
#include <QtQml/private/qqmlengine_p.h>
#include <QtQml/private/qqmlobjectcreator_p.h>
#include <QtQml/private/qqmlsourcecoordinate_p.h>
#include <QtQml/private/qqmlvmemetaobject_p.h>
#include <QtQml/private/qv4engine_p.h>
#include <QtQml/private/qv4mm_p.h>

#ifdef SWIRL_UI_TESTS
#include <QtQuickTemplates2/private/qquickcontrol_p_p.h>
#endif

namespace {

QString qmlWarningAddress(const void *value)
{
    return value ? QString::number(reinterpret_cast<quintptr>(value), 16) : QString();
}

QJsonObject qmlWarningObjectState(QObject *object)
{
    QJsonObject result{{"present", object != nullptr}, {"address", qmlWarningAddress(object)}};
    if (!object) return result;
    const auto *objectState = QObjectPrivate::get(object);
    result.insert("wasDeleted", bool(objectState->wasDeleted));
    result.insert("isDeletingChildren", bool(objectState->isDeletingChildren));
    if (objectState->wasDeleted || objectState->isDeletingChildren) return result;
    result.insert("type", QString::fromLatin1(object->metaObject()->className()));
    // QObject::objectName() can register a binding dependency and allocate ExtraData.
    // Read only its already-stored value, without invoking that getter.
    result.insert("objectName", objectState->extraData
                      ? objectState->extraData->objectName.valueBypassingBindings() : QString());
    result.insert("parentAddress", qmlWarningAddress(object->parent()));
    result.insert("ownership", QQmlEngine::objectOwnership(object) == QQmlEngine::CppOwnership
                      ? QStringLiteral("CppOwnership") : QStringLiteral("JavaScriptOwnership"));
    const auto *data = QQmlData::get(object, false);
    result.insert("qmlDataPresent", data != nullptr);
    if (data) result.insert("qmlData", QJsonObject{
        {"indestructible", bool(data->indestructible)},
        {"explicitIndestructibleSet", bool(data->explicitIndestructibleSet)},
        {"isQueuedForDeletion", bool(data->isQueuedForDeletion)},
        {"rootObjectInCreation", bool(data->rootObjectInCreation)},
        {"hasVMEMetaObject", bool(data->hasVMEMetaObject)},
        {"jsWrapperAllocated", data->jsWrapper.valueRef() != nullptr},
        {"jsWrapperUndefined", data->jsWrapper.isUndefined()}});
    if (const auto *vme = QQmlVMEMetaObject::get(object)) result.insert("vme", QJsonObject{
        {"memberStoragePresent", vme->propertyAndMethodStorageAsMemberData() != nullptr},
        {"qmlObjectId", vme->qmlObjectId()},
        {"contextValid", vme->contextData() && vme->contextData()->isValid()}});
    if (const auto *item = qobject_cast<QQuickItem *>(object))
        result.insert("visualParentAddress", qmlWarningAddress(item->parentItem()));
    return result;
}

QJsonObject qmlWarningContextChain(QQmlContextData *context)
{
    QJsonArray entries;
    constexpr int maximumContexts = 8;
    while (context && entries.size() < maximumContexts) {
        const auto parent = context->parent();
        entries.append(QJsonObject{
            {"address", qmlWarningAddress(context)},
            {"valid", context->isValid()},
            {"rootObjectInCreation", context->isRootObjectInCreation()},
            {"contextObject", qmlWarningObjectState(context->contextObject())},
            {"parentContextAddress", qmlWarningAddress(parent.data())}});
        context = parent.data();
    }
    return QJsonObject{{"entries", entries}, {"truncated", context != nullptr}};
}

QJsonObject qmlWarningGcState(QQmlApplicationEngine &engine)
{
    const auto *v4 = engine.handle();
    const auto *memory = v4 ? v4->memoryManager : nullptr;
    QJsonObject result{{"memoryManagerPresent", memory != nullptr}};
    if (!memory) return result;
    const auto *state = memory->gcStateMachine.get();
    result.insert("isGCOngoing", v4->isGCOngoing);
    result.insert("gcBlocked", static_cast<int>(memory->gcBlocked));
    result.insert("markStackPresent", memory->m_markStack != nullptr);
    result.insert("stateMachinePresent", state != nullptr);
    if (state) {
        result.insert("state", static_cast<int>(state->state));
        result.insert("stateName", QString::fromLatin1(
            QMetaEnum::fromType<QV4::GCStateMachine::GCState>().valueToKey(state->state)));
    }
    return result;
}

QJsonObject qmlWarningCreationCandidates(QQmlApplicationEngine &engine, const QQmlError &warning)
{
    // Qt 6.12's qmlWarning(QObject *) records source coordinates but does not
    // set QQmlError::object(). These guarded objects are location candidates,
    // never a recovered error-object identity. Suspended incubators and the
    // complete QObject tree are outside this current creator's scope.
    auto *creator = QQmlEnginePrivate::get(&engine)->activeObjectCreator;
    constexpr int maximumScanned = 8192;
    constexpr int maximumCandidates = 16;
    const bool locationAvailable = !warning.url().isEmpty()
        && warning.line() > 0 && warning.column() > 0;
    QJsonArray candidates;
    QJsonObject result{
        {"creatorPresent", creator != nullptr}, {"creatorAddress", qmlWarningAddress(creator)},
        {"sourceLocationAvailable", locationAvailable},
        {"scanLimit", maximumScanned}, {"candidateLimit", maximumCandidates},
        {"scannedGuards", 0}, {"matchingGuards", 0}, {"scanTruncated", false},
        {"candidatesTruncated", false}, {"candidates", candidates},
        {"scope", QStringLiteral("Current active creator only; guarded objects matched by outerContext URL and instance line/column. Candidates are not QQmlError::object identities. Suspended incubators and the full object tree are not covered.")}};
    if (!creator || !locationAvailable) return result;
    const auto &created = creator->allCreatedObjects();
    int scanned = 0;
    int matching = 0;
    for (const auto &guard : created) {
        if (scanned >= maximumScanned) break;
        ++scanned;
        auto *object = guard.data();
        if (!object) continue;
        const auto *objectState = QObjectPrivate::get(object);
        if (objectState->wasDeleted || objectState->isDeletingChildren) continue;
        const auto *data = QQmlData::get(object, false);
        if (!data || !data->outerContext || data->outerContext->url() != warning.url()
            || qmlConvertSourceCoordinate<quint16, int>(data->lineNumber) != warning.line()
            || qmlConvertSourceCoordinate<quint16, int>(data->columnNumber) != warning.column()) continue;
        ++matching;
        if (candidates.size() >= maximumCandidates) continue;
        QJsonArray parents;
        auto *parent = object->parent();
        while (parent && parents.size() < 16) {
            parents.append(qmlWarningObjectState(parent));
            const auto *parentState = QObjectPrivate::get(parent);
            if (parentState->wasDeleted || parentState->isDeletingChildren) break;
            parent = parent->parent();
        }
        candidates.append(QJsonObject{
            {"identityScope", QStringLiteral("source-location candidate from QQmlGuard")},
            {"guardIndex", scanned - 1}, {"object", qmlWarningObjectState(object)},
            {"parents", parents}, {"parentsTruncated", parent != nullptr},
            {"context", qmlWarningContextChain(data->context)},
            {"outerContext", qmlWarningContextChain(data->outerContext)}});
    }
    result.insert("scannedGuards", scanned);
    result.insert("matchingGuards", matching);
    result.insert("scanTruncated", created.size() > static_cast<size_t>(scanned));
    result.insert("candidatesTruncated", matching > maximumCandidates);
    result.insert("candidates", candidates);
    return result;
}

// Collect Qt/QML diagnostics in a file because the Windows GUI subsystem
// does not attach stderr to GitHub Actions' PowerShell console.
void recordQtDiagnostic(QtMsgType type, const QMessageLogContext &, const QString &message)
{
    const auto name = qApp ? qApp->property("qtDiagnosticFile").toString() : QString();
    QFile file(QCoreApplication::applicationDirPath() + "/"
               + (name.isEmpty() ? QStringLiteral("Swirl-diagnostics.txt") : name));
    if (!file.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text))
        return;
    QTextStream out(&file);
    out << static_cast<int>(type) << ": " << message << '\n';
}

} // namespace

void recordQmlVmeWarningContext(QQmlApplicationEngine &engine,
                                QmlVmeWarningCapture &capture,
                                const QList<QQmlError> &warnings)
{
    // Only inspect the first bounded cluster. This records C++/QML ownership
    // metadata and never reads a QML property, evaluates JavaScript, drains an
    // incubator, or creates a public QQmlContext wrapper.
    if (capture.reporting) return;
    constexpr int maximumWarnings = 16;
    constexpr qint64 firstClusterMs = 250;
    for (const auto &warning : warnings) {
        const auto description = warning.description();
        const bool matches = description.contains(QStringLiteral("Cannot find member data"))
            || (description.contains(QStringLiteral("is not a function"))
                && (description.contains(QStringLiteral("'scheduleRefresh'"))
                    || description.contains(QStringLiteral("'contourPath'"))
                    || description.contains(QStringLiteral("'finish'"))
                    || description.contains(QStringLiteral("'retarget'"))));
        if (!matches) continue;
        if (!capture.firstMatch.isValid()) capture.firstMatch.start();
        if (capture.firstMatch.elapsed() > firstClusterMs
            || capture.capturedWarnings >= maximumWarnings) return;
        auto *object = warning.object();
        QString objectSource = object ? QStringLiteral("QQmlError::object") : QString();
        // Missing-method exceptions carry an address but no QQmlError object
        // or column. Match it against live trees, never dereference log text.
        int scannedObjects = 0;
        if (!object) {
            const auto address = QRegularExpression(QStringLiteral("\\(0x([0-9a-fA-F]+)(?:,|\\))")).match(description);
            if (address.hasMatch()) {
                const auto expected = address.captured(1).toULongLong(nullptr, 16);
                QList<QObject *> pending = engine.rootObjects();
                QSet<QObject *> visited;
                while (!pending.isEmpty() && scannedObjects < 8192) {
                    auto *candidate = pending.takeLast();
                    if (!candidate || visited.contains(candidate)) continue;
                    visited.insert(candidate); ++scannedObjects;
                    if (reinterpret_cast<quintptr>(candidate) == expected) {
                        object = candidate;
                        objectSource = QStringLiteral("warning address matched in live QObject/visual tree");
                        break;
                    }
                    const auto *state = QObjectPrivate::get(candidate);
                    if (state->wasDeleted || state->isDeletingChildren) continue;
                    for (auto *child : candidate->children()) pending.append(child);
                    if (auto *item = qobject_cast<QQuickItem *>(candidate))
                        for (auto *child : item->childItems()) pending.append(child);
                }
            }
        }
        if (object && capture.observedObjects.contains(object)) continue;
        if (object) capture.observedObjects.insert(object);
        ++capture.capturedWarnings;
        QScopedValueRollback<bool> reporting(capture.reporting, true);
        const auto *engineState = QQmlEnginePrivate::get(&engine);
        const int inProgressBefore = engineState->inProgressCreations;
        const auto gcState = qmlWarningGcState(engine);
        const auto creationCandidates = object ? QJsonObject{} : qmlWarningCreationCandidates(engine, warning);
        auto *controller = engine.incubationController();
        QJsonArray parents;
        const auto *objectState = object ? QObjectPrivate::get(object) : nullptr;
        const bool objectAlive = objectState && !objectState->wasDeleted && !objectState->isDeletingChildren;
        auto *parent = objectAlive ? object->parent() : nullptr;
        constexpr int maximumParents = 16;
        while (parent && parents.size() < maximumParents) {
            parents.append(qmlWarningObjectState(parent));
            const auto *parentState = QObjectPrivate::get(parent);
            if (parentState->wasDeleted || parentState->isDeletingChildren) break;
            parent = parent->parent();
        }
        const auto *data = objectAlive ? QQmlData::get(object, false) : nullptr;
        const auto url = warning.url();
        const QJsonObject record{
            {"phase", QString::fromLatin1(capture.phase)},
            {"source_sha", QStringLiteral(SWIRL_SOURCE_SHA)},
            {"elapsedMs", capture.firstMatch.elapsed()},
            {"runtimeMs", capture.runtime.elapsed()},
            {"captureLimit", maximumWarnings}, {"clusterWindowMs", firstClusterMs},
            {"capturedWarnings", capture.capturedWarnings},
            {"capturedObjects", static_cast<int>(capture.observedObjects.size())},
            {"description", description},
            {"url", url.scheme() == QStringLiteral("qrc") ? url.toString() : url.fileName()},
            {"line", warning.line()}, {"column", warning.column()},
            {"object", qmlWarningObjectState(object)},
            {"objectSource", objectSource}, {"scannedObjects", scannedObjects},
            {"parents", parents}, {"parentsTruncated", parent != nullptr},
            {"context", qmlWarningContextChain(data ? data->context : nullptr)},
            {"outerContext", qmlWarningContextChain(data ? data->outerContext : nullptr)},
            {"gc", gcState}, {"creationCandidates", creationCandidates},
            {"inProgressCreations", inProgressBefore},
            {"publicIncubators", controller ? controller->incubatingObjectCount() : 0},
            {"inProgressAfterObservation", engineState->inProgressCreations},
            {"scope", QStringLiteral("First matching warning cluster in isolated node UI/smoke checks; raw metadata only. No QML property evaluation or warning suppression.")}};
        qInfo().noquote() << "QML_VME_WARNING_CONTEXT" << QJsonDocument(record).toJson(QJsonDocument::Compact);
    }
}

#ifdef SWIRL_UI_TESTS
void recordQmlCreationLifecycle(QQmlApplicationEngine &engine, const char *phase)
{
    // The public controller counts incubators, while the engine also counts
    // synchronous and Qt Controls deferred creation. Observe both without
    // completing, cancelling or reading any deferred QML property.
    auto *engineState = QQmlEnginePrivate::get(&engine);
    const int inProgressBefore = engineState->inProgressCreations;
    auto *controller = engine.incubationController();
    QJsonArray pendingControls;
    QSet<QObject *> visited;
    QList<QObject *> pending = engine.rootObjects();
    int controlCount = 0;
    int pendingControlCount = 0;
    constexpr int maximumObjects = 8192;
    constexpr int maximumReportedControls = 128;
    const auto flags = [](const QQuickUntypedDeferredPointer &pointer) {
        return QJsonObject{{"hasDeferredState", pointer.deferredState() != nullptr},
                           {"executing", pointer.isExecuting()},
                           {"executed", pointer.wasExecuted()}};
    };
    while (!pending.isEmpty() && visited.size() < maximumObjects) {
        auto *object = pending.takeLast();
        if (!object || visited.contains(object)) continue;
        visited.insert(object);
        for (auto *child : object->children()) pending.append(child);
        if (auto *item = qobject_cast<QQuickItem *>(object))
            for (auto *child : item->childItems()) pending.append(child);
        if (auto *control = qobject_cast<QQuickControl *>(object)) {
            ++controlCount;
            auto *state = QQuickControlPrivate::get(control);
            if (!state->background.deferredState() && !state->contentItem.deferredState()) continue;
            ++pendingControlCount;
            if (pendingControls.size() >= maximumReportedControls) continue;
            auto *context = qmlContext(control);
            pendingControls.append(QJsonObject{
                {"objectName", control->objectName()},
                {"type", QString::fromLatin1(control->metaObject()->className())},
                {"parentName", control->parent() ? control->parent()->objectName() : QString()},
                {"contextUrl", context ? context->baseUrl().toString() : QString()},
                {"background", flags(state->background)},
                {"contentItem", flags(state->contentItem)}});
        }
    }
    qInfo().noquote() << "QML_CREATION_LIFECYCLE" << QJsonDocument(QJsonObject{
        {"phase", QString::fromLatin1(phase)},
        {"inProgressCreations", inProgressBefore},
        {"inProgressAfterObservation", engineState->inProgressCreations},
        {"controllerPresent", controller != nullptr},
        {"publicIncubators", controller ? controller->incubatingObjectCount() : 0},
        {"visitedObjects", static_cast<int>(visited.size())},
        {"traversalTruncated", !pending.isEmpty()},
        {"controls", controlCount},
        {"pendingControlCount", pendingControlCount},
        {"pendingControls", pendingControls},
        {"pendingControlsTruncated", pendingControlCount > maximumReportedControls},
        {"scope", QStringLiteral("Root QObject/visual trees; raw Control background/contentItem flags only. Other deferred properties and engine-owned singletons are not enumerated.")}
    }).toJson(QJsonDocument::Compact);
}
#endif

QString selectQtDiagnosticLogFile(const QStringList &arguments)
{
    QString file;
    if (arguments.contains("--ui-quality-test")) file = QStringLiteral("Swirl-ui-quality.txt");
    if (arguments.contains("--appearance-test") || arguments.contains("--appearance-restore-test"))
        file = arguments.contains("--appearance-restore-test")
            ? QStringLiteral("Swirl-appearance-restore.txt")
            : QStringLiteral("Swirl-appearance.txt");
    if (arguments.contains("--hero-test")) {
        file = arguments.contains("--hero-material-only")
            ? QStringLiteral("Swirl-hero-material-diagnostics.txt")
            : QStringLiteral("Swirl-hero-diagnostics.txt");
    } else if (arguments.contains("--motion-test")) {
        file = QStringLiteral("Swirl-motion-diagnostics.txt");
        if (qEnvironmentVariableIsSet("SWIRL_ACTIVITY_PERF_CHECKS")) {
            const int rows = qEnvironmentVariableIsSet("SWIRL_ACTIVITY_PERF_ROWS")
                ? qEnvironmentVariableIntValue("SWIRL_ACTIVITY_PERF_ROWS") : 600;
            file = rows == 600 ? QStringLiteral("Swirl-activity-perf-600-diagnostics.txt")
                 : rows == 2000 ? QStringLiteral("Swirl-activity-perf-2000-diagnostics.txt")
                                : QStringLiteral("Swirl-activity-perf-invalid-diagnostics.txt");
        } else if (qEnvironmentVariableIsSet("SWIRL_ACTIVITY_DETAIL_CHECKS"))
            file = QStringLiteral("Swirl-activity-details-diagnostics.txt");
        else if (qEnvironmentVariableIsSet("SWIRL_APEC_GLASS_CHECKS"))
            file = QStringLiteral("Swirl-apec-glass-diagnostics.txt");
        else if (qEnvironmentVariableIsSet("SWIRL_APEC_MOTION_CHECKS"))
            file = QStringLiteral("Swirl-apec-motion-diagnostics.txt");
        else if (qEnvironmentVariableIsSet("SWIRL_ROUTE_BENCH"))
            file = QStringLiteral("Swirl-route-bench-diagnostics.txt");
        else if (qEnvironmentVariableIsSet("SWIRL_U2_CHECKS"))
            file = QStringLiteral("Swirl-u2-diagnostics.txt");
        else if (qEnvironmentVariableIsSet("SWIRL_LIQUID_GLASS_CHECKS"))
            file = QStringLiteral("Swirl-liquid-glass-diagnostics.txt");
        else if (qEnvironmentVariableIsSet("SWIRL_6A_CHECKS"))
            file = QStringLiteral("Swirl-6a-diagnostics.txt");
        else if (qEnvironmentVariableIsSet("SWIRL_RECORD_INTERACTIONS"))
            file = QStringLiteral("Swirl-record-interactions-diagnostics.txt");
        else if (qEnvironmentVariableIsSet("SWIRL_SCROLL_BENCH"))
            file = QStringLiteral("Swirl-scroll-bench-diagnostics.txt");
    }
    if (arguments.contains("--node-self-test")) {
        file = qEnvironmentVariableIntValue("SWIRL_NODE_UI_REQUIRE_NATIVE") == 1
            ? QStringLiteral("Swirl-node-ui-native-diagnostics.txt")
            : QStringLiteral("Swirl-node-ui-diagnostics.txt");
    }
    if (arguments.contains("--policy-self-test"))
        file = QStringLiteral("Swirl-policy-ui-diagnostics.txt");
    else if (arguments.contains("--interaction-test"))
        file = QStringLiteral("Swirl-input-diagnostics.txt");
    if (arguments.contains("--engine-self-test"))
        file = QStringLiteral("Swirl-engine-ui-diagnostics.txt");
    if (arguments.contains("--xray-import-ui-test"))
        file = QStringLiteral("Swirl-xray-ui-diagnostics.txt");
    return file;
}

void installQtDiagnosticFileHandler(const QString &logFileName)
{
    const QString dir = QCoreApplication::applicationDirPath();
    if (!logFileName.isEmpty()) {
        qApp->setProperty("qtDiagnosticFile", logFileName);
        QFile::remove(dir + QStringLiteral("/") + logFileName);
    }
    QFile::remove(dir + QStringLiteral("/Swirl-diagnostics.txt"));
    qInstallMessageHandler(recordQtDiagnostic);
}
