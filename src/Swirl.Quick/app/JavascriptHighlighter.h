#pragma once
#include <QSyntaxHighlighter>
#include <QQuickTextDocument>
#include <QtQml/qqmlregistration.h>

class JavascriptHighlighter final : public QSyntaxHighlighter
{
    Q_OBJECT
    QML_ELEMENT
    Q_PROPERTY(QQuickTextDocument* qmlDocument READ qmlDocument WRITE setQmlDocument NOTIFY qmlDocumentChanged)
public:
    explicit JavascriptHighlighter(QObject *parent = nullptr);
    QQuickTextDocument* qmlDocument() const { return m_document; }
    void setQmlDocument(QQuickTextDocument *document);
signals:
    void qmlDocumentChanged();
protected:
    void highlightBlock(const QString &text) override;
private:
    QQuickTextDocument *m_document = nullptr;
};
