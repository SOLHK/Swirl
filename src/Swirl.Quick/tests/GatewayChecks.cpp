#include "GatewayChecks.h"
#include "network/DhcpServer.h"
#include "network/GatewayRouting.h"
#include <QTemporaryDir>
#include <QFile>
#include <QUdpSocket>
#include <QNetworkDatagram>
#include <QNetworkProxy>
#include <QElapsedTimer>
#include <QCoreApplication>
#include <QDebug>
#include <QtEndian>
int runGatewayChecks(){int checks=0,failures=0;const auto check=[&](bool ok,const char *name){++checks;if(ok)qInfo()<<"PASS"<<name;else {++failures;qCritical()<<"FAIL"<<name;}};
    QTemporaryDir temporary;DhcpServer server(true);server.setLeaseStorePath(temporary.filePath("leases.json"));DhcpServer::Config config{QHostAddress("192.0.2.1"),QHostAddress("192.0.2.100"),QHostAddress("192.0.2.102"),QHostAddress("192.0.2.1"),24,0,3600};
    check(server.configure(config),"valid DHCP subnet and bounded pool configure");auto invalid=config;invalid.first=QHostAddress("192.0.2.1");check(!DhcpServer::validate(invalid),"DHCP pool cannot allocate its gateway");invalid=config;invalid.last=QHostAddress("198.51.100.1");check(!DhcpServer::validate(invalid),"DHCP pool cannot cross its configured subnet");
    check(server.reserve("02:00:00:00:00:01","192.0.2.101","Fixture client"),"MAC reservation validates against the pool");check(!server.reserve("02:00:00:00:00:02","192.0.2.101","Conflicting"),"duplicate reserved address is rejected");
    check(server.start(config)&&server.port()!=67,"isolated DHCP socket starts only on a loopback ephemeral port");
    QUdpSocket client;client.setProxy(QNetworkProxy::NoProxy);client.bind(QHostAddress::LocalHost,0);
    const auto message=[](int type,const QByteArray &mac,const QByteArray &extra=QByteArray()){QByteArray packet(236,char(0));packet[0]=1;packet[1]=1;packet[2]=6;packet[4]=char(0x42);packet[10]=char(0x80);packet.replace(28,6,mac);packet+=QByteArray::fromHex("63825363");packet+=QByteArray::fromHex("3501")+char(type);packet+=extra;packet+=char(255);return packet;};
    const auto exchange=[&](const QByteArray &packet){while(client.hasPendingDatagrams())client.receiveDatagram();client.writeDatagram(packet,QHostAddress::LocalHost,server.port());QElapsedTimer timer;timer.start();while(!client.hasPendingDatagrams()&&timer.elapsed()<500){QCoreApplication::processEvents();}return client.hasPendingDatagrams()?client.receiveDatagram().data():QByteArray();};
    const auto mac=QByteArray::fromHex("020000000001"),second=QByteArray::fromHex("020000000002");const auto offer=exchange(message(1,mac));
    check(offer.size()>=300&&offer.contains(QByteArray::fromHex("350102")),"real UDP DHCPDISCOVER receives DHCPOFFER");check(offer.mid(4,4)==QByteArray::fromHex("42000000")&&offer.mid(16,4)==QByteArray::fromHex("c0000265"),"offer preserves transaction ID and MAC reservation");
    const auto ack=exchange(message(3,mac,QByteArray::fromHex("3204c00002653604c0000201")));check(ack.contains(QByteArray::fromHex("350105")),"real UDP DHCPREQUEST receives DHCPACK");check(server.leases().size()==1&&server.leases().first().toMap().value("status")==QString::fromUtf8("租用中"),"committed lease is a real acknowledged client");
    const auto other=exchange(message(1,second));check(!other.isEmpty()&&other.mid(16,4)!=offer.mid(16,4),"second client receives a different available address");
    const auto foreign=exchange(message(3,second,QByteArray::fromHex("3204c00002643604c00002fe")));check(foreign.isEmpty(),"requests selecting another DHCP server are ignored");
    const auto unavailable=exchange(message(3,second,QByteArray::fromHex("3204c0000265")));check(unavailable.contains(QByteArray::fromHex("350106")),"request for another client's reserved address receives NAK");
    const auto malformed=exchange(message(1,second,QByteArray::fromHex("0cff01")));check(malformed.isEmpty(),"truncated DHCP option is rejected");
    auto release=message(7,mac);release.replace(12,4,QByteArray::fromHex("c0000265"));exchange(release);check(server.leases().size()==1,"DHCPRELEASE removes only the releasing client's lease");
    const auto clientId=QByteArray::fromHex("3d0701020000000003"),third=QByteArray::fromHex("020000000003");
    const auto identified=exchange(message(1,third,clientId));check(identified.contains(clientId),"DHCP response echoes a real client identifier");
    const auto identifiedAck=exchange(message(3,third,QByteArray::fromHex("3204")+identified.mid(16,4)+clientId));
    check(identifiedAck.contains(QByteArray::fromHex("350105")),"client identifier is retained across offer and ACK");
    exchange(message(4,third,QByteArray::fromHex("3204")+identified.mid(16,4)+clientId));
    server.stop();check(!server.running(),"DHCP stop closes the actual UDP socket");
    DhcpServer reloaded(true);reloaded.setLeaseStorePath(temporary.filePath("leases.json"));
    check(reloaded.configure(config)&&reloaded.leases().size()==1,"leases survive restart without reallocating occupied addresses");
    check(!reloaded.reserve("02:00:00:00:00:04",QHostAddress(qFromBigEndian<quint32>(reinterpret_cast<const uchar *>(identified.constData()+16))).toString(),"Declined"),"declined address quarantine survives restart");
    const auto before=reloaded.reservations();
    check(!reloaded.replaceReservations({QVariantMap{{"mac","02:00:00:00:00:05"},{"ip","192.0.2.101"}},QVariantMap{{"mac","02:00:00:00:00:06"},{"ip","192.0.2.101"}}})&&reloaded.reservations()==before,"invalid client import preserves all existing reservations");
    QFile damaged(temporary.filePath("broken.json"));damaged.open(QIODevice::WriteOnly);damaged.write("corrupt");damaged.close();DhcpServer corrupted(true);corrupted.setLeaseStorePath(damaged.fileName());
    check(!corrupted.configure(config),"corrupt lease store prevents address allocation");
    QString recoveryError;check(!GatewayRouting::cleanup(damaged.fileName(),&recoveryError)&&damaged.exists(),"invalid recovery journal cannot change Windows interfaces");
#ifdef Q_OS_WIN
    bool scriptsValid=true;
    for(const auto &script:{GatewayRouting::startScript(temporary.filePath("quote's journal.json")),GatewayRouting::cleanupScript(temporary.filePath("quote's journal.json"))}){
        QFile scriptFile(temporary.filePath("routing.ps1"));if(!scriptFile.open(QIODevice::WriteOnly)){scriptsValid=false;break;}scriptFile.write(script.toUtf8());scriptFile.close();
        auto path=scriptFile.fileName();path.replace("'","''");QProcess parser;
        GatewayRouting::prepareProcess(parser,QString("$tokens=$null;$errors=$null;[Management.Automation.Language.Parser]::ParseFile('%1',[ref]$tokens,[ref]$errors)|Out-Null;if($errors.Count){$errors|Out-String|Write-Error;exit 1}").arg(path));
        parser.start();scriptsValid=parser.waitForStarted(3000)&&parser.waitForFinished(10000)&&parser.exitCode()==0&&scriptsValid;
        if(parser.state()!=QProcess::NotRunning){parser.kill();parser.waitForFinished(1000);}
    }
    check(scriptsValid,"forwarding and recovery scripts parse without executing network changes");
#endif
    qInfo()<<"DHCP integration checks:"<<checks<<"checks,"<<failures<<"failures";return failures?2:0;}
