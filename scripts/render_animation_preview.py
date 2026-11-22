"""Export the actual renderer as an 18-second, single-play transparent APNG.

Uses Qt and Python's standard library only. This is a development artifact,
not a browser component in the companion. APNG framing follows W3C PNG Third Edition.
"""
import argparse
from pathlib import Path
import struct
import sys
import zlib


def chunk(kind, data):
    return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data) & 0xFFFFFFFF)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('.runtime/animation-preview.png'))
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QSize, QBuffer, QIODevice
    from PySide6.QtGui import QImage
    from app.avatar.motion import IdleMotion
    from app.avatar.placeholder import PlaceholderRenderer
    app = QApplication([])
    renderer, motion = PlaceholderRenderer(), IdleMotion(17)
    width, height, fps, frames = 240, 360, 30, 540
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sequence = 0
    with args.output.open('wb') as stream:
        stream.write(b'\x89PNG\r\n\x1a\n')
        stream.write(chunk(b'IHDR', struct.pack('!IIBBBBB', width, height, 8, 6, 0, 0, 0)))
        stream.write(chunk(b'acTL', struct.pack('!II', frames, 1)))
        for frame in range(frames):
            if frame: motion.advance(1 / fps)
            image = renderer.render(QSize(width, height), 1, pose=motion.pose).convertToFormat(QImage.Format.Format_RGBA8888)
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            if not image.save(buffer, 'PNG'):
                raise RuntimeError('Qt failed to encode a preview frame')
            png = bytes(buffer.data()); offset = 8; pieces = []
            while offset < len(png):
                length = struct.unpack_from('!I', png, offset)[0]
                kind = png[offset + 4:offset + 8]
                payload = png[offset + 8:offset + 8 + length]
                if kind == b'IHDR':
                    assert payload == struct.pack('!IIBBBBB', width, height, 8, 6, 0, 0, 0)
                if kind == b'IDAT': pieces.append(payload)
                offset += length + 12
            data = b''.join(pieces)
            stream.write(chunk(b'fcTL', struct.pack('!IIIIIHHBB', sequence, width, height, 0, 0, 1, fps, 0, 0)))
            sequence += 1
            if frame == 0:
                stream.write(chunk(b'IDAT', data))
            else:
                stream.write(chunk(b'fdAT', struct.pack('!I', sequence) + data))
                sequence += 1
        stream.write(chunk(b'IEND', b''))
    renderer.close()
    print(f'{frames} frames at {fps} FPS: {args.output} ({args.output.stat().st_size} bytes)')


if __name__ == '__main__': main()
