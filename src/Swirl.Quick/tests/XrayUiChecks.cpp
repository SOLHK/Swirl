#include "XrayUiChecks.h"
#include "app/StoragePaths.h"
#include "engine/EngineController.h"
#include <QClipboard>
#include <QFile>
#include <QGuiApplication>
#include <QJsonDocument>
#include <QJSValue>
#include <QPointer>
#include <QQmlContext>
#include <QQmlExpression>
#include <QQuickItem>
#include <QQuickWindow>
#include <QSet>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QtQuickTest/quicktest.h>
#include <QtTest>
#include <functional>

namespace {
// Reserved domains and synthetic credentials only. The source is intentionally
// not generated through Qt JSON: the production strict parser receives it as-is.
const QByteArray fixture = R"json({"inbounds":[{"protocol":"socks","listen":"0.0.0.0","port":45991,"settings":{"accounts":[{"user":"fixture","pass":"XRAY_UI_INBOUND_SECRET"}]}}],"outbounds":[
{"protocol":"vless","tag":"UI REALITY 東京","settings":{"vnext":[{"address":"example.invalid","port":443,"users":[{"id":"11111111-2222-4333-8444-555555555555","encryption":"none","flow":"xtls-rprx-vision"}]}]},"streamSettings":{"network":"tcp","security":"reality","realitySettings":{"serverName":"example.invalid","publicKey":"CQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQk","shortId":"a1b2","spiderX":"/XRAY_UI_PRIVATE_PATH","fingerprint":"chrome"}}},
{"protocol":"vmess","tag":"UI VMess","settings":{"vnext":[{"address":"example.invalid","port":443,"users":[{"id":"22222222-3333-4444-8555-666666666666","alterId":0,"security":"auto"}]}]},"streamSettings":{"network":"grpc","security":"tls","grpcSettings":{"serviceName":"XRAY_UI_PRIVATE_GRPC"}},"mux":{"enabled":true}},
{"protocol":"trojan","tag":"UI Trojan","settings":{"servers":[{"address":"example.invalid","port":443,"password":"XRAY_UI_TROJAN_SECRET"}]},"streamSettings":{"network":"tcp","security":"tls","tlsSettings":{"serverName":"example.invalid"}}},
{"protocol":"shadowsocks","tag":"UI Shadowsocks","settings":{"servers":[{"address":"example.invalid","port":8388,"method":"aes-128-gcm","password":"XRAY_UI_SS_SECRET"}]}},
{"protocol":"socks","tag":"UI SOCKS","settings":{"servers":[{"address":"example.invalid","port":1080,"users":[{"user":"fixture-user","pass":"XRAY_UI_SOCKS_SECRET"}]}]}},
{"protocol":"http","tag":"UI HTTP","settings":{"servers":[{"address":"example.invalid","port":8080,"users":[{"user":"fixture-user","pass":"XRAY_UI_HTTP_SECRET"}]}]}}
]})json";

// A separate node exercises the existing native subset. Unsupported fields in
// the six-protocol fixture above remain intact and must remain inspectable.
const QByteArray runnableFixture = R"json({"protocol":"vless","tag":"UI Native selection","settings":{"vnext":[{"address":"127.0.0.1","port":9,"users":[{"id":"00112233-4455-6677-8899-aabbccddeeff","encryption":"none","flow":"xtls-rprx-vision"}]}]},"streamSettings":{"network":"tcp","security":"reality","realitySettings":{"serverName":"camouflage.invalid","fingerprint":"chrome","publicKey":"CQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQk","shortId":"a1B2"}}})json";

const QStringList privateValues{
    QStringLiteral("11111111-2222-4333-8444-555555555555"),
    QStringLiteral("22222222-3333-4444-8555-666666666666"),
    QStringLiteral("00112233-4455-6677-8899-aabbccddeeff"),
    QStringLiteral("XRAY_UI_INBOUND_SECRET"), QStringLiteral("XRAY_UI_TROJAN_SECRET"),
    QStringLiteral("XRAY_UI_SS_SECRET"), QStringLiteral("XRAY_UI_SOCKS_SECRET"),
    QStringLiteral("XRAY_UI_HTTP_SECRET"), QStringLiteral("XRAY_UI_PRIVATE_PATH"),
    QStringLiteral("XRAY_UI_PRIVATE_GRPC"), QStringLiteral("XRAY_UI_INVALID_SECRET")};

bool hasPrivateValue(const QString &value) {
    for (const auto &secret : privateValues)
        if (value.contains(secret)) return true;
    return false;
}

// Popups reparent their visual content to Overlay. Traverse both QObject and
// visual children, with a visited set, so tests address the actual mounted UI.
QList<QObject *> objects(QObject *root) {
    QList<QObject *> result, pending{root};
    QSet<QObject *> visited;
    while (!pending.isEmpty()) {
        auto *object = pending.takeLast();
        if (!object || visited.contains(object)) continue;
        visited.insert(object);
        result.append(object);
        for (auto *child : object->children()) pending.append(child);
        if (auto *item = qobject_cast<QQuickItem *>(object))
            for (auto *child : item->childItems()) pending.append(child);
        if (auto *window = qobject_cast<QQuickWindow *>(object)) pending.append(window->contentItem());
    }
    return result;
}

QObject *named(QObject *root, const char *name) {
    const auto wanted = QString::fromLatin1(name);
    for (auto *object : objects(root)) if (object->objectName() == wanted) return object;
    return nullptr;
}

bool hasVisibleText(QObject *root, const QString &text) {
    for (auto *object : objects(root)) {
        const auto *item = qobject_cast<QQuickItem *>(object);
        if (item && item->isVisible() && item->property("text").toString() == text) return true;
    }
    return false;
}

QStringList identities(const QVariantList &rows) {
    QStringList result;
    for (const auto &row : rows) result.append(row.toMap().value("id").toString());
    result.sort();
    return result;
}

QVariant plainValue(const QVariant &value) {
    return value.metaType() == QMetaType::fromType<QJSValue>()
        ? value.value<QJSValue>().toVariant() : value;
}

class Checks {
public:
    explicit Checks(QQuickWindow *window) : m_window(window) {}
    bool require(bool passed, const char *code) {
        if (!passed) qCritical().noquote() << "XRAY_UI_FAIL" << code;
        return passed;
    }
    bool wait(const std::function<bool()> &condition, const char *code, int timeout = 10000) {
        return require(QTest::qWaitFor(condition, timeout), code);
    }
    bool click(const char *name) { return clickObject(named(m_window, name), name); }
    bool clickObject(QObject *object, const char *code) {
        const auto fail = [code](const char *phase) {
            qCritical().noquote() << "XRAY_UI_FAIL" << code << phase;
            return false;
        };
        QPointer<QQuickItem> item = qobject_cast<QQuickItem *>(object);
        if (!item || item->window() != m_window) return fail("missing-or-detached");
        // Preview/busy changes can leave a visible button at its old positive
        // geometry until its parent RowLayout is polished. Wait for the whole
        // window: the button itself need not have a pending polish request.
        if (!QQuickTest::qWaitForPolish(m_window, 2000)) return fail("pending-layout");
        if (!item || !item->isVisible() || !item->isEnabled() || item->window() != m_window
            || item->width() <= 0 || item->height() <= 0) return fail("not-interactable");
        const auto point = item->mapToScene(QPointF(item->width() / 2, item->height() / 2));
        if (!QRectF(QPointF(0, 0), m_window->size()).contains(point)) return fail("outside-window");
        QSignalSpy clicked(item.data(), SIGNAL(clicked()));
        if (!clicked.isValid()) return fail("clicked-signal");
        QTest::mouseClick(m_window, Qt::LeftButton, Qt::NoModifier, point.toPoint());
        if (!QTest::qWaitFor([&] { return clicked.count() == 1; }, 2000)) return fail("click-not-observed");
        return true;
    }
    bool clickRow(QObject *table, const QString &identity, const char *code) {
        auto *tableItem = qobject_cast<QQuickItem *>(table);
        auto *viewport = qobject_cast<QQuickItem *>(named(table, "tableRowsViewport"));
        auto *hero = named(m_window, "nodeHero");
        if (!require(tableItem && viewport && hero && !identity.isEmpty(), code)
            || !wait([&] { return !hero->property("moving").toBool(); }, code)) return false;
        int index = -1;
        if (!wait([&] {
                const auto rows = plainValue(table->property("rows")).toList();
                index = -1;
                for (int i = 0; i < rows.size(); ++i)
                    if (rows.at(i).toMap().value("id").toString() == identity) { index = i; break; }
                return index >= 0 && viewport->property("count").toInt() == rows.size();
            }, code)) return false;
        if (!eval(viewport, QStringLiteral("positionViewAtIndex(%1, ListView.Center); forceLayout()").arg(index))) return false;
        QPointer<QQuickItem> row;
        QPointF point;
        if (!wait([&] {
                for (auto *object : objects(viewport)) {
                    auto *item = qobject_cast<QQuickItem *>(object);
                    if (!item || plainValue(item->property("record")).toMap().value("id").toString() != identity
                        || !item->isVisible() || !item->isEnabled() || item->window() != m_window
                        || item->width() <= 0 || item->height() <= 0) continue;
                    const auto center = item->mapToScene(QPointF(item->width() / 2, item->height() / 2));
                    if (!QRectF(QPointF(0, 0), viewport->size()).contains(viewport->mapFromScene(center))
                        || !QRectF(QPointF(0, 0), tableItem->size()).contains(tableItem->mapFromScene(center))
                        || !QRectF(QPointF(0, 0), m_window->size()).contains(center)) continue;
                    row = item;
                    point = center;
                    return true;
                }
                return false;
            }, code)) return false;
        QSignalSpy selected(table, SIGNAL(rowSelected(QVariant)));
        if (!require(selected.isValid(), code)) return false;
        QTest::mouseClick(m_window, Qt::LeftButton, Qt::NoModifier, point.toPoint());
        return wait([&] {
            return row && selected.count() == 1 && !selected.first().isEmpty()
                && plainValue(selected.first().first()).toMap().value("id").toString() == identity
                && qvariant_cast<QQuickItem *>(table->property("selectedItem")) == row;
        }, code, 2000);
    }
    bool fill(const QString &text) {
        auto *field = named(m_window, "importContentField");
        return require(field && field->property("enabled").toBool()
                           && field->setProperty("text", text) && field->property("text").toString() == text,
                       "text-input");
    }
    bool eval(QObject *scope, const QString &expression) {
        QQmlExpression command(qmlContext(scope), scope, expression);
        command.evaluate();
        return require(!command.hasError(), "qml-command");
    }
    bool noPrivateDisplay(const QVariantList &rows) {
        if (!require(!hasPrivateValue(QString::fromUtf8(QJsonDocument::fromVariant(rows).toJson())),
                     "public-model-redaction")) return false;
        for (auto *object : objects(m_window))
            if (!require(!hasPrivateValue(object->property("text").toString()), "ui-redaction")) return false;
        return true;
    }
private:
    QQuickWindow *m_window;
};
}

int runXrayUiChecks(QQuickWindow *window, EngineController *controller, const QString &isolatedStorePath) {
    Checks check(window);
    if (!check.require(window && controller && controller->rustCoreBuild(), "native-controller")) return 1;
    bool validExpectedDpr = false;
    const auto expectedDpr = qEnvironmentVariable("SWIRL_EXPECTED_DPR").toDouble(&validExpectedDpr);
    const auto actualDpr = window->devicePixelRatio();
    qInfo().noquote() << "XRAY_UI_DPR actual=" + QString::number(actualDpr, 'f', 3)
                     << "expected=" + QString::number(expectedDpr, 'f', 3);
    if (!check.require(validExpectedDpr && qIsFinite(expectedDpr) && expectedDpr > 0
                           && qIsFinite(actualDpr) && qAbs(actualDpr - expectedDpr) <= 0.01,
                       "device-pixel-ratio")) return 1;
    const auto root = SwirlPaths::testRoot();
    const auto storageParent = QFileInfo(isolatedStorePath).absolutePath();
    if (!check.require(!root.isEmpty() && QFileInfo(storageParent).canonicalFilePath().startsWith(root + '/')
                           && !QFile::exists(isolatedStorePath), "isolated-new-store")) return 1;
    auto *service = controller->imports();
    QSignalSpy applied(service, &NodeImportService::nodesApplied);
    if (!check.require(applied.isValid() && controller->nodes().isEmpty() && !controller->processAlive()
                           && !controller->requestSucceeded(), "empty-inactive-state")) return 1;

    window->resize(1450, 940);
    if (!check.eval(window, QStringLiteral("AppState.navigate('proxies')"))) return 1;
    if (!check.wait([&] {
            auto *host = named(window, "pageLoader");
            auto *active = host ? qvariant_cast<QObject *>(host->property("activeLoader")) : nullptr;
            return active && active->property("routeId").toString() == "proxies"
                && !host->property("moving").toBool() && !host->property("pendingGrab").toBool()
                && named(window, "nodeImportButton");
        }, "proxies-page-ready")) return 1;
    if (!check.click("nodeImportButton")) return 1;
    if (!check.wait([&] {
            auto *dialog = named(window, "nodeImportDialog");
            return dialog && dialog->property("opened").toBool() && named(window, "importContentField");
        }, "import-dialog-open")) return 1;

    const auto previewReady = [&] {
        auto *preview = named(window, "jsonImportPreview");
        return !service->busy() && service->hasPreview() && service->preview().size() == 6
            && preview && preview->property("visible").toBool() && preview->property("count").toInt() == 6;
    };
    const auto cancelPreview = [&] {
        auto *button = named(named(window, "nodeImportDialog"), "importCancelPreviewButton");
        return check.clickObject(button, "cancel-preview-button")
            && check.wait([&] { return !service->busy() && !service->hasPreview(); }, "cancel-preview");
    };
    const auto inputCleared = [&] {
        auto *field = named(window, "importContentField");
        return field && field->property("text").toString().isEmpty();
    };

    // Real text field and pointer input call the production NodeImportService.
    if (!check.fill(QString::fromUtf8(fixture)) || !check.click("importApplyButton")
        || !check.wait(previewReady, "text-preview")) return 1;
    if (!check.require(controller->nodes().isEmpty() && applied.count() == 0 && inputCleared(),
                       "preview-before-confirmation")) return 1;
    const QStringList expectedLabels{QStringLiteral("VLESS"), QStringLiteral("VMess"),
        QStringLiteral("Trojan"), QStringLiteral("Shadowsocks"), QStringLiteral("SOCKS5"), QStringLiteral("HTTP")};
    const auto rows = service->preview();
    auto *preview = named(window, "jsonImportPreview");
    for (int index = 0; index < expectedLabels.size(); ++index) {
        const auto row = rows.at(index).toMap();
        if (!check.require(row.value("protocolLabel").toString() == expectedLabels.at(index)
                               && row.value("jsonParsed").toBool() && !row.value("networkVerified").toBool(),
                           "six-protocol-model")) return 1;
        if (!check.eval(preview, QStringLiteral("positionViewAtIndex(%1, ListView.Beginning); forceLayout()").arg(index))) return 1;
        if (!check.wait([&] { return hasVisibleText(preview, row.value("name").toString()
                    + QStringLiteral(" · ") + expectedLabels.at(index)); }, "six-protocol-delegates", 3000)) return 1;
    }
    if (!check.require(rows.first().toMap().value("securityLabel").toString() == "REALITY"
                           && rows.first().toMap().value("visionEnabled").toBool(), "reality-vision-model")
        || !check.noPrivateDisplay(rows) || !cancelPreview()
        || !check.require(controller->nodes().isEmpty() && applied.count() == 0, "cancel-is-read-only")) return 1;

    // Exercise the existing clipboard button with synthetic text, then restore
    // the original clipboard immediately. No private clipboard data is logged.
    auto *clipboard = QGuiApplication::clipboard();
    if (!check.require(clipboard != nullptr, "clipboard-available")) return 1;
    const auto previousClipboard = clipboard->text();
    clipboard->setText(QString::fromUtf8(fixture));
    const bool clipboardClicked = check.click("importClipboardButton");
    clipboard->setText(previousClipboard);
    if (!clipboardClicked || !check.wait(previewReady, "clipboard-preview") || !cancelPreview()) return 1;

    // Native file-picker interaction is outside this headless test. The real
    // file API drives the same mounted preview and confirmation controls.
    QTemporaryDir sourceDirectory(root + QStringLiteral("/xray-ui-source-XXXXXX"));
    if (!check.require(sourceDirectory.isValid(), "fixture-directory")) return 1;
    const auto sourcePath = sourceDirectory.filePath(QStringLiteral("节点_日本語.json"));
    QFile source(sourcePath);
    if (!check.require(source.open(QIODevice::WriteOnly) && source.write(fixture) == fixture.size(),
                       "fixture-write")) return 1;
    source.close();
    service->importFile(QUrl::fromLocalFile(sourcePath));
    if (!check.wait(previewReady, "unicode-file-preview")
        || !check.require(controller->nodes().isEmpty() && applied.count() == 0
                              && service->preview().first().toMap().value("importSource").toString() == "file",
                          "file-preview-before-confirmation")) return 1;
    // QTest pointer delivery pumps events; a fast DPAPI worker may complete
    // before mouseClick returns. Observe the pending state while it occurs.
    bool sawPendingSave = false;
    const auto saveObserver = QObject::connect(service, &NodeImportService::changed, service, [&] {
        if (service->busy() && controller->nodes().isEmpty()) sawPendingSave = true;
    });
    const bool confirmed = check.click("importApplyButton");
    QObject::disconnect(saveObserver);
    if (!confirmed || !check.require(sawPendingSave, "asynchronous-atomic-save")) return 1;
    if (!check.wait([&] { return !service->busy(); }, "encrypted-save-completion")
        || !check.require(controller->nodes().size() == 6 && applied.count() == 1, "dpapi-updates-live-list")) return 1;
    if (!check.require(source.open(QIODevice::ReadOnly) && source.read(fixture.size() + 1) == fixture,
                       "source-file-unchanged")) return 1;
    source.close();
    QFile encrypted(isolatedStorePath);
    if (!check.require(encrypted.open(QIODevice::ReadOnly) && encrypted.size() > 10 && encrypted.size() < 1024 * 1024,
                       "encrypted-file-created")) return 1;
    const auto ciphertext = encrypted.read(1024 * 1024);
    if (!check.require(ciphertext.startsWith("SWIRLNODE1\n") && !hasPrivateValue(QString::fromUtf8(ciphertext))
                           && !ciphertext.contains(fixture), "encrypted-file-hides-source")) return 1;
    encrypted.close();
    {
        NodeStore restored(isolatedStorePath);
        if (!check.require(restored.error().isEmpty() && restored.nodes().size() == 6
                               && identities(restored.publicRows()) == identities(controller->nodes()),
                           "dpapi-reload-identities")) return 1;
        for (const auto &node : restored.nodes())
            if (!check.require(node.sourceDocument == fixture && node.importSource == "file",
                               "dpapi-reload-exact-parameters")) return 1;
    }

    const auto beforeIds = identities(controller->nodes());
    const auto selectedBefore = controller->selectedNodeId();
    if (!check.fill(QString::fromUtf8(fixture)) || !check.click("importApplyButton")
        || !check.wait(previewReady, "repeat-text-preview") || !check.click("importApplyButton")
        || !check.wait([&] { return !service->busy(); }, "repeat-text-save")) return 1;
    if (!check.require(applied.count() == 2 && identities(controller->nodes()) == beforeIds
                           && controller->selectedNodeId() == selectedBefore, "dedup-selection-stable")) return 1;

    if (!check.fill(QStringLiteral(R"({"protocol":"vless","protocol":"vmess","settings":{"password":"XRAY_UI_INVALID_SECRET"}})"))
        || !check.click("importApplyButton") || !check.wait([&] { return !service->busy(); }, "strict-error-completion")) return 1;
    auto *message = named(window, "importResultMessage");
    if (!check.require(!service->hasPreview() && service->message().contains("DuplicateJsonKey")
                           && message && message->property("text").toString() == service->message()
                           && applied.count() == 2 && identities(controller->nodes()) == beforeIds
                           && controller->selectedNodeId() == selectedBefore && inputCleared(),
                       "strict-error-visible-preserves-state") || !check.noPrivateDisplay(controller->nodes())) return 1;

    if (!check.fill(QString::fromUtf8(runnableFixture)) || !check.click("importApplyButton")
        || !check.wait([&] { return !service->busy() && service->hasPreview() && service->preview().size() == 1; },
                       "native-selection-preview")) return 1;
    if (!check.require(service->preview().first().toMap().value("capability").toMap().value("native").toBool()
                           && !service->preview().first().toMap().value("networkVerified").toBool(),
                       "native-selection-real-capability") || !check.click("importApplyButton")
        || !check.wait([&] { return !service->busy(); }, "native-selection-save")
        || !check.require(controller->nodes().size() == 7 && applied.count() == 3, "native-selection-saved")) return 1;

    auto *dialog = named(window, "nodeImportDialog");
    if (!check.require(dialog && QMetaObject::invokeMethod(dialog, "close"), "close-import-dialog")
        || !check.wait([&] { return !dialog->property("visible").toBool(); }, "dialog-close-completion")) return 1;
    auto *table = named(window, "realNodeTable");
    if (!check.require(table, "node-table")) return 1;
    for (const auto &label : expectedLabels)
        if (!check.wait([&] { return hasVisibleText(table, label); }, "saved-protocol-delegates", 3000)) return 1;
    QVariantMap runnable;
    for (const auto &entry : controller->nodes())
        if (entry.toMap().value("name").toString() == QStringLiteral("UI Native selection")) runnable = entry.toMap();
    if (!check.require(!runnable.isEmpty() && runnable.value("capability").toMap().value("native").toBool(),
                       "native-selection-real-capability")
        || !check.clickRow(table, runnable.value("id").toString(), "choose-executable-row")) return 1;
    if (!check.wait([&] { return controller->selectedNodeId() == runnable.value("id").toString()
                              && table->property("selectedId").toString() == runnable.value("id").toString(); },
                    "executable-row-selected")) return 1;
    const auto reality = controller->nodes().first().toMap();
    const auto capability = reality.value("capability").toMap();
    const bool executable = capability.value("native").toBool() || capability.value("compatible").toBool();
    const auto selectionBeforeInspection = controller->selectedNodeId();
    if (!check.clickRow(table, reality.value("id").toString(), "select-real-row")) return 1;
    if (!check.wait([&] {
            auto *transport = named(window, "jsonNodeTransport");
            auto *state = named(window, "jsonNodeValidation");
            auto *hero = named(window, "nodeHero");
            const auto expectedSelection = executable ? reality.value("id").toString() : selectionBeforeInspection;
            return controller->selectedNodeId() == expectedSelection
                && table->property("selectedId").toString() == reality.value("id").toString()
                && hero && hero->property("opened").toBool() && !hero->property("moving").toBool()
                && transport && transport->property("visible").toBool()
                && transport->property("text").toString().contains("REALITY")
                && transport->property("text").toString().contains("Vision")
                && state && state->property("text").toString().contains(QStringLiteral("未验证业务流量"));
        }, "selected-reality-vision-detail") || !check.noPrivateDisplay(controller->nodes())) return 1;

    // An explicit unsupported mux keeps this fixture disabled as native
    // protocol and transport coverage grows. Browsing it must not
    // replace the saved runnable selection or enable connection/probe actions.
    QVariantMap unsupported;
    for (const auto &entry : controller->nodes()) {
        const auto row = entry.toMap(), support = row.value("capability").toMap();
        if (row.value("protocol").toString() == "vmess" && row.value("transportType").toString() == "grpc"
            && !support.value("native").toBool() && !support.value("compatible").toBool()) { unsupported = row; break; }
    }
    const auto selectedBeforeUnsupported = controller->selectedNodeId();
    if (!check.require(!unsupported.isEmpty(), "unsupported-fixture-preserved")
        || !check.clickRow(table, unsupported.value("id").toString(), "inspect-unsupported-row")) return 1;
    if (!check.wait([&] {
            auto *host = named(window, "pageLoader");
            auto *active = host ? qvariant_cast<QObject *>(host->property("activeLoader")) : nullptr;
            auto *page = active ? qvariant_cast<QObject *>(active->property("item")) : nullptr;
            auto *reason = named(window, "nodeUnsupportedReason");
            auto *transport = named(window, "jsonNodeTransport");
            auto *connectButton = named(window, "nodeConnectButton");
            auto *testButton = named(window, "nodeTestButton");
            return page && page->property("inspectedId").toString() == unsupported.value("id").toString()
                && controller->selectedNodeId() == selectedBeforeUnsupported
                && reason && reason->property("visible").toBool() && !reason->property("text").toString().isEmpty()
                && transport && transport->property("text").toString().contains("gRPC")
                && connectButton && !connectButton->property("enabled").toBool()
                && testButton && !testButton->property("enabled").toBool();
        }, "unsupported-inspection-preserves-selection")) return 1;
    if (!check.require(!controller->processAlive() && !controller->requestSucceeded()
                           && controller->requestStateText() == QStringLiteral("尚未发起实际请求"),
                       "import-is-not-network-verification")) return 1;
    QFile diagnostic(QCoreApplication::applicationDirPath() + QStringLiteral("/Swirl-xray-ui-diagnostics.txt"));
    if (!check.require(diagnostic.open(QIODevice::ReadOnly) && diagnostic.size() < 1024 * 1024
                           && !hasPrivateValue(QString::fromUtf8(diagnostic.read(1024 * 1024))),
                       "diagnostics-redaction")) return 1;
    return 0; // main emits the sole pass marker only after the QML warning gate.
}
