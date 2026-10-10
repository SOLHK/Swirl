#pragma once
#include <QObject>
#include <QVariantList>
class DemoDataProvider final : public QObject {
    Q_OBJECT
public:
    using QObject::QObject;
    Q_INVOKABLE QVariantList connections() const;
    Q_INVOKABLE QVariantList requests() const;
    Q_INVOKABLE QVariantList nodes() const;
    Q_INVOKABLE QVariantList events() const;
    Q_INVOKABLE QVariantList traffic() const;
    Q_INVOKABLE QVariantList logs() const;
};
