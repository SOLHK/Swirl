#pragma once
#include <QProcess>

// Windows assigns the job atomically in CreateProcess, before any child code runs.
// Closing Swirl (including crashes) closes the job and kills its process tree.
class OwnedProcess final : public QProcess {
public:
    explicit OwnedProcess(QObject *parent = nullptr);
    ~OwnedProcess() override;
    bool ownershipReady() const;
private:
    struct Native;
    Native *m_native;
};
