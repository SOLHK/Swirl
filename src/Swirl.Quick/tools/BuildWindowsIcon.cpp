// Builds the mandatory Windows ICO from the Swirl SVG source.
// Uncompressed BGRA DIB frames support NSIS, Windows Explorer and RC.
#include <QGuiApplication>
#include <QSvgRenderer>
#include <QImage>
#include <QPainter>
#include <QFile>
#include <QDataStream>
#include <QByteArray>
#include <QVector>
#include <QtGlobal>
#include <cstdio>

static QByteArray makeDib(const QImage &source, int size)
{
    const QImage frame = source.scaled(size, size, Qt::IgnoreAspectRatio,
                                       Qt::SmoothTransformation)
                               .convertToFormat(QImage::Format_ARGB32);
    QByteArray dib;
    QDataStream out(&dib, QIODevice::WriteOnly);
    out.setByteOrder(QDataStream::LittleEndian);
    const int maskStride = ((size + 31) / 32) * 4;
    out << quint32(40) << qint32(size) << qint32(size * 2)
        << quint16(1) << quint16(32) << quint32(0)
        << quint32(size * size * 4 + maskStride * size)
        << qint32(0) << qint32(0) << quint32(0) << quint32(0);
    for (int y = size - 1; y >= 0; --y) {
        for (int x = 0; x < size; ++x) {
            const QRgb pixel = frame.pixel(x, y);
            out << quint8(qBlue(pixel)) << quint8(qGreen(pixel))
                << quint8(qRed(pixel)) << quint8(qAlpha(pixel));
        }
    }
    for (int y = size - 1; y >= 0; --y) {
        QByteArray mask(maskStride, char(0));
        for (int x = 0; x < size; ++x) {
            if (qAlpha(frame.pixel(x, y)) < 128) {
                const unsigned char bit = static_cast<unsigned char>(0x80u >> (x & 7));
                mask[x / 8] = char(static_cast<unsigned char>(mask[x / 8]) | bit);
            }
        }
        out.writeRawData(mask.constData(), mask.size());
    }
    return dib;
}

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);
    if (app.arguments().size() != 3) {
        std::fprintf(stderr, "Usage: SwirlIconBuilder source.svg output.ico\n");
        return 2;
    }
    QSvgRenderer renderer(app.arguments().at(1));
    if (!renderer.isValid()) {
        std::fprintf(stderr, "Invalid Swirl brand SVG\n");
        return 3;
    }
    QImage source(1024, 1024, QImage::Format_ARGB32);
    source.fill(Qt::transparent);
    {
        QPainter painter(&source);
        renderer.render(&painter);
    }
    // Crop transparent margins, then add a consistent 6% safe edge. The path
    // itself is unchanged; the knot now occupies 88% of the Windows canvas.
    QRect bounds;
    for(int y=0;y<source.height();++y)for(int x=0;x<source.width();++x)
        if(qAlpha(source.pixel(x,y))>0)bounds=bounds.united(QRect(x,y,1,1));
    if(bounds.isEmpty())return 3;
    QImage enlarged(1024,1024,QImage::Format_ARGB32);enlarged.fill(Qt::transparent);
    {QPainter p(&enlarged);p.setRenderHint(QPainter::SmoothPixmapTransform);
     const auto fitted=bounds.size().scaled(900,900,Qt::KeepAspectRatio);
     p.drawImage(QRect((1024-fitted.width())/2,(1024-fitted.height())/2,fitted.width(),fitted.height()),source,bounds);}
    source=enlarged;
    const QVector<int> sizes = {16, 20, 24, 32, 40, 48, 64, 128, 256};
    QVector<QByteArray> frames;
    for (int size : sizes) frames.append(makeDib(source, size));
    QByteArray icon;
    QDataStream header(&icon, QIODevice::WriteOnly);
    header.setByteOrder(QDataStream::LittleEndian);
    header << quint16(0) << quint16(1) << quint16(sizes.size());
    quint32 offset = quint32(6 + 16 * sizes.size());
    for (qsizetype i = 0; i < sizes.size(); ++i) {
        const int size = sizes.at(i);
        const QByteArray &frame = frames.at(i);
        header << quint8(size == 256 ? 0 : size) << quint8(size == 256 ? 0 : size)
               << quint8(0) << quint8(0) << quint16(1) << quint16(32)
               << quint32(frame.size()) << offset;
        offset += quint32(frame.size());
    }
    for (const auto &frame : frames) icon.append(frame);
    QFile file(app.arguments().at(2));
    if (!file.open(QIODevice::WriteOnly) || file.write(icon) != icon.size()) {
        std::fprintf(stderr, "Unable to write Swirl icon\n");
        return 4;
    }
    file.close();
    return 0;
}
