#include <QCoreApplication>
#include <QFile>
#include <QJSEngine>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#ifdef Q_OS_WIN
#include <windows.h>
#endif
int main(int argc,char **argv) {
    QCoreApplication app(argc,argv);
#ifdef Q_OS_WIN
    HANDLE limits=CreateJobObjectW(nullptr,nullptr);
    if(!limits)return 3;
    if(limits){JOBOBJECT_EXTENDED_LIMIT_INFORMATION information{};information.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_PROCESS_MEMORY;information.ProcessMemoryLimit=128*1024*1024;
        if(!SetInformationJobObject(limits,JobObjectExtendedLimitInformation,&information,sizeof(information))||!AssignProcessToJobObject(limits,GetCurrentProcess()))return 3;}
#endif
    QFile input;input.open(stdin,QIODevice::ReadOnly);const auto bytes=input.read(512*1024+1);
    if(bytes.size()>512*1024)return 2;const auto object=QJsonDocument::fromJson(bytes).object();
    if(!object.value("source").isString())return 2;
    QJSEngine engine;
    // Catch arbitrary thrown JS values (including strings/numbers), and reject
    // cyclic/non-JSON results inside JavaScript before converting to Qt types.
    auto execute=engine.evaluate(QStringLiteral(R"JS((function(source,input){
        const logs=[],stringify=JSON.stringify,string=String;
        const console={log:function(){if(logs.length<100)logs.push(Array.prototype.map.call(arguments,string).join(' ').slice(0,512));},error:function(){console.log.apply(console,arguments);}};
        try {
            const entry=new Function('console',source+'\n;if(typeof main!=="function")throw new Error("脚本需要定义 function main(input)。");return main;')(console);
            return stringify({ok:true,result:entry(input),logs:logs});
        } catch(error) { return stringify({ok:false,error:string(error).slice(0,2048),logs:logs}); }
    }))JS"));
    const auto value=execute.call({QJSValue(object.value("source").toString()),engine.toScriptValue(object.value("input").toVariant())});
    if(value.isError()||!value.isString())return 2;
    const auto output=value.toString().toUtf8();if(output.size()>64*1024)return 4;
    const bool ok=QJsonDocument::fromJson(output).object().value("ok").toBool();
    QFile out;out.open(stdout,QIODevice::WriteOnly);out.write(output);out.flush();
#ifdef Q_OS_WIN
    if(limits)CloseHandle(limits);
#endif
    return ok?0:2;
}
