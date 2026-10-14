#include <QCoreApplication>
#include "network/GatewayRouting.h"
int main(int argc,char **argv){QCoreApplication app(argc,argv);if(app.arguments().size()!=2)return 2;return GatewayRouting::guard(app.arguments().at(1));}
