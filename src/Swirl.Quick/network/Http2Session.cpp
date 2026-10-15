#include "Http2Session.h"
#include <QSslSocket>
#include <QPointer>
#include <QHash>
#include <QTimer>
#include <nghttp2/nghttp2.h>
#include <cstring>
#include <algorithm>
namespace { constexpr int BodyLimit=1024*1024,HeaderLimit=64*1024,StreamLimit=32; }
struct Http2Session::Impl {
    struct Stream {Request request;int headerBytes=0;bool dispatched=false,responded=false,streaming=false,finished=false;QByteArray response;qint64 offset=0;std::function<void()> cancel;};
    Http2Session *owner=nullptr;QPointer<QSslSocket> socket;Handler handler;nghttp2_session *session=nullptr;QHash<int,std::shared_ptr<Stream>> streams;
    ~Impl(){if(session)nghttp2_session_del(session);}
    static int begin(nghttp2_session *session,const nghttp2_frame *frame,void *user) {
        auto *self=static_cast<Impl *>(user);if(frame->hd.type!=NGHTTP2_HEADERS||frame->headers.cat!=NGHTTP2_HCAT_REQUEST)return 0;
        if(self->streams.size()>=StreamLimit){nghttp2_submit_rst_stream(session,NGHTTP2_FLAG_NONE,frame->hd.stream_id,NGHTTP2_REFUSED_STREAM);return NGHTTP2_ERR_TEMPORAL_CALLBACK_FAILURE;}
        auto stream=std::make_shared<Stream>();stream->request.id=frame->hd.stream_id;self->streams.insert(frame->hd.stream_id,stream);return 0;
    }
    static int header(nghttp2_session *,const nghttp2_frame *frame,const uint8_t *name,size_t nameSize,const uint8_t *value,size_t valueSize,uint8_t,void *user) {
        auto *self=static_cast<Impl *>(user);const auto stream=self->streams.value(frame->hd.stream_id);if(!stream||stream->dispatched)return 0;
        if(nameSize+valueSize>HeaderLimit||stream->headerBytes+nameSize+valueSize>HeaderLimit)return NGHTTP2_ERR_TEMPORAL_CALLBACK_FAILURE;
        stream->headerBytes+=int(nameSize+valueSize);const QByteArray n(reinterpret_cast<const char *>(name),nameSize),v(reinterpret_cast<const char *>(value),valueSize);
        if(n==":method")stream->request.method=v;else if(n==":path")stream->request.path=v;else if(n==":authority")stream->request.authority=v;else if(n==":scheme")stream->request.scheme=v;
        else if(!n.startsWith(':'))stream->request.headers.append({n,v});return 0;
    }
    static int data(nghttp2_session *session,uint8_t,int32_t id,const uint8_t *bytes,size_t size,void *user) {
        auto *self=static_cast<Impl *>(user);const auto stream=self->streams.value(id);if(!stream)return 0;
        if(stream->dispatched||stream->request.body.size()+size>BodyLimit){nghttp2_submit_rst_stream(session,0,id,NGHTTP2_ENHANCE_YOUR_CALM);return 0;}
        stream->request.body.append(reinterpret_cast<const char *>(bytes),size);return 0;
    }
    static int frame(nghttp2_session *,const nghttp2_frame *frame,void *user) {
        if((frame->hd.type!=NGHTTP2_HEADERS&&frame->hd.type!=NGHTTP2_DATA)||!(frame->hd.flags&NGHTTP2_FLAG_END_STREAM))return 0;
        auto *self=static_cast<Impl *>(user);const auto stream=self->streams.value(frame->hd.stream_id);if(!stream||stream->dispatched)return 0;
        stream->dispatched=true;const auto request=stream->request;
        QTimer::singleShot(0,self->owner,[self,request]{if(self->streams.contains(request.id))self->handler(request);});return 0;
    }
    static int close(nghttp2_session *,int32_t id,uint32_t error,void *user) {
        auto *self=static_cast<Impl *>(user);const auto stream=self->streams.take(id);if(stream&&error&&stream->cancel)QTimer::singleShot(0,self->owner,stream->cancel);return 0;
    }
    static nghttp2_ssize read(nghttp2_session *,int32_t,uint8_t *bytes,size_t length,uint32_t *flags,nghttp2_data_source *source,void *) {
        auto *stream=static_cast<Stream *>(source->ptr);const auto size=qMin<qint64>(qint64(length),stream->response.size()-stream->offset);
        if(size==0&&stream->streaming&&!stream->finished)return NGHTTP2_ERR_DEFERRED;
        if(size>0)std::memcpy(bytes,stream->response.constData()+stream->offset,size);stream->offset+=size;if(stream->offset==stream->response.size()&&(!stream->streaming||stream->finished))*flags|=NGHTTP2_DATA_FLAG_EOF;return size;
    }
};
Http2Session::Http2Session(QSslSocket *socket,Handler handler):QObject(socket),d(std::make_unique<Impl>()) {
    d->owner=this;d->socket=socket;d->handler=std::move(handler);nghttp2_session_callbacks *callbacks=nullptr;
    if(nghttp2_session_callbacks_new(&callbacks)!=0){socket->abort();return;}
    nghttp2_session_callbacks_set_on_begin_headers_callback(callbacks,Impl::begin);
    nghttp2_session_callbacks_set_on_header_callback(callbacks,Impl::header);
    nghttp2_session_callbacks_set_on_data_chunk_recv_callback(callbacks,Impl::data);
    nghttp2_session_callbacks_set_on_frame_recv_callback(callbacks,Impl::frame);
    nghttp2_session_callbacks_set_on_stream_close_callback(callbacks,Impl::close);
    const int result=nghttp2_session_server_new(&d->session,callbacks,d.get());nghttp2_session_callbacks_del(callbacks);
    if(result!=0){socket->abort();return;}
    const nghttp2_settings_entry settings[]={{NGHTTP2_SETTINGS_MAX_CONCURRENT_STREAMS,StreamLimit},{NGHTTP2_SETTINGS_MAX_HEADER_LIST_SIZE,HeaderLimit},{NGHTTP2_SETTINGS_INITIAL_WINDOW_SIZE,256*1024}};
    nghttp2_submit_settings(d->session,0,settings,3);
    connect(socket,&QSslSocket::readyRead,this,&Http2Session::receive);
    connect(socket,&QSslSocket::bytesWritten,this,[this]{flush();});flush();
}
Http2Session::~Http2Session()=default;
void Http2Session::receive() {
    if(!d->session||!d->socket)return;const auto bytes=d->socket->readAll();
    const auto consumed=nghttp2_session_mem_recv2(d->session,reinterpret_cast<const uint8_t *>(bytes.constData()),bytes.size());
    if(consumed<0){d->socket->abort();return;}flush();
}
void Http2Session::flush() {
    if(!d->session||!d->socket||d->socket->state()!=QAbstractSocket::ConnectedState)return;
    while(d->socket->bytesToWrite()<4*1024*1024){const uint8_t *bytes=nullptr;const auto size=nghttp2_session_mem_send2(d->session,&bytes);if(size<0){d->socket->abort();return;}if(size==0)break;
        if(d->socket->write(reinterpret_cast<const char *>(bytes),size)!=size){d->socket->abort();return;}}
}
bool Http2Session::respond(int id,int status,const Headers &headers,const QByteArray &body,bool head) {
    const auto stream=d->streams.value(id);if(!stream||stream->responded||!d->socket||body.size()>2*1024*1024)return false;
    stream->responded=true;stream->response=head?QByteArray():body;
    Headers pairs{{":status",QByteArray::number(status)}};for(const auto &header:headers){const auto name=header.first.toLower();if(name.startsWith(':')||name=="connection"||name=="transfer-encoding"||name=="keep-alive"||name=="upgrade"||name=="proxy-connection")continue;pairs.append({name,header.second});}
    QList<nghttp2_nv> fields;for(auto &pair:pairs)fields.append({reinterpret_cast<uint8_t *>(pair.first.data()),reinterpret_cast<uint8_t *>(pair.second.data()),size_t(pair.first.size()),size_t(pair.second.size()),NGHTTP2_NV_FLAG_NONE});
    nghttp2_data_provider2 provider{};provider.source.ptr=stream.get();provider.read_callback=Impl::read;
    if(nghttp2_submit_response2(d->session,id,fields.data(),fields.size(),stream->response.isEmpty()?nullptr:&provider)!=0)return false;
    flush();return true;
}
void Http2Session::setCancelHandler(int id,std::function<void()> handler) {const auto stream=d->streams.value(id);if(stream)stream->cancel=std::move(handler);}
bool Http2Session::beginStreaming(int id,int status,const Headers &headers) {
    const auto stream=d->streams.value(id);if(!stream||stream->responded||!d->socket)return false;
    stream->responded=true;stream->streaming=true;
    Headers pairs{{":status",QByteArray::number(status)}};
    for(const auto &header:headers){const auto name=header.first.toLower();if(name.startsWith(':')||name=="connection"||name=="transfer-encoding"||name=="keep-alive"||name=="upgrade"||name=="proxy-connection")continue;pairs.append({name,header.second});}
    QList<nghttp2_nv> fields;for(auto &pair:pairs)fields.append({reinterpret_cast<uint8_t *>(pair.first.data()),reinterpret_cast<uint8_t *>(pair.second.data()),size_t(pair.first.size()),size_t(pair.second.size()),NGHTTP2_NV_FLAG_NONE});
    nghttp2_data_provider2 provider{};provider.source.ptr=stream.get();provider.read_callback=Impl::read;
    if(nghttp2_submit_response2(d->session,id,fields.data(),fields.size(),&provider)!=0)return false;flush();return true;
}
int Http2Session::writableBytes(int id) const {
    const auto stream=d->streams.value(id);if(!stream||!d->socket||d->socket->bytesToWrite()>=4*1024*1024)return 0;
    return qMax(0,512*1024-int(stream->response.size()-stream->offset));
}
bool Http2Session::appendStreaming(int id,const QByteArray &body,bool finished) {
    const auto stream=d->streams.value(id);if(!stream||!stream->streaming||stream->finished||body.size()>writableBytes(id))return false;
    if(stream->offset){stream->response.remove(0,stream->offset);stream->offset=0;}stream->response+=body;stream->finished=finished;
    nghttp2_session_resume_data(d->session,id);flush();return true;
}
void Http2Session::resetStream(int id) {if(d->session){nghttp2_submit_rst_stream(d->session,0,id,NGHTTP2_INTERNAL_ERROR);flush();}}
