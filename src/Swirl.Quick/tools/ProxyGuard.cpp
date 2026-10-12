#include <QCoreApplication>
#include "engine/SystemProxySession.h"
int main(int argc,char **argv) {
    QCoreApplication app(argc,argv);
    if(app.arguments().size()!=2)return 2;
    return SystemProxySession::guard(app.arguments().at(1));
}
