#include "JavascriptHighlighter.h"
#include <QRegularExpression>
#include <QTextDocument>
#include <QTextCharFormat>
#include <QColor>

JavascriptHighlighter::JavascriptHighlighter(QObject *parent)
    : QSyntaxHighlighter(parent) {}

void JavascriptHighlighter::setQmlDocument(QQuickTextDocument *document)
{
    if (m_document == document) return;
    m_document = document;
    setDocument(document ? document->textDocument() : nullptr);
    emit qmlDocumentChanged();
}

void JavascriptHighlighter::highlightBlock(const QString &text)
{
    auto mark = [&text, this](const QRegularExpression &pattern, const QColor &color) {
        QTextCharFormat fmt;
        fmt.setForeground(color);
        auto matches = pattern.globalMatch(text);
        while (matches.hasNext()) {
            const auto match = matches.next();
            setFormat(match.capturedStart(), match.capturedLength(), fmt);
        }
    };
    mark(QRegularExpression(QStringLiteral(R"(\b(const|let|var|async|await|function|return|if|else|for|of|new|throw|try|catch)\b)")), QColor("#669DE2"));
    mark(QRegularExpression(QStringLiteral(R"(\b(true|false|null|undefined|console)\b|\$request|\$response|\$done)")), QColor("#54B7A0"));
    mark(QRegularExpression(QStringLiteral(R"("([^"\\]|\\.)*"|'([^'\\]|\\.)*')")), QColor("#DEA970"));
    mark(QRegularExpression(QStringLiteral(R"(//.*$)")), QColor("#8097A6"));
}
