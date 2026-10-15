#pragma once
#include <QObject>
#include <QByteArray>
#include <QList>
#include <QPair>
#include <functional>
#include <memory>
class QSslSocket;
class Http2Session final : public QObject {
public:
    using Headers=QList<QPair<QByteArray,QByteArray>>;
    struct Request { int id=0;QByteArray method,path,authority,scheme,body;Headers headers; };
    using Handler=std::function<void(const Request &)>;
    explicit Http2Session(QSslSocket *socket,Handler handler);
    ~Http2Session() override;
    bool respond(int stream,int status,const Headers &headers,const QByteArray &body,bool head=false);
    bool beginStreaming(int stream,int status,const Headers &headers);
    int writableBytes(int stream) const;
    bool appendStreaming(int stream,const QByteArray &body,bool finished=false);
    void resetStream(int stream);
    void setCancelHandler(int stream,std::function<void()> handler);
    void receive();
private:
    struct Impl;std::unique_ptr<Impl> d;
    void flush();
};
