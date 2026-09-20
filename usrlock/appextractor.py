# UPDATE.APP extractor based on marcominetti/split_updata.pl.
# Original Python implementation by OpenA, 2026.
import os
from pathlib import Path
import re
import struct
import crcmod


class ImageExtractor:
    IMAGE_HEADER_ID = b'\x55\xAA\x5A\xA5'
    crc_x25_calc = staticmethod(crcmod.mkCrcFun(0x11021, initCrc=0, rev=True, xorOut=0xFFFF))

    def __init__(self, crc_check=True, filter=''):
        self._filter = re.compile(filter or r'.+')
        self._crc_check = crc_check

    @staticmethod
    def _read_exact(stream, size):
        data = stream.read(size)
        if len(data) != size:
            raise ValueError('Truncated UPDATE.APP record')
        return data

    def dump_img(self, stream, out_dir=''):
        start = stream.tell() - 4
        header = self.IMAGE_HEADER_ID + self._read_exact(stream, 94)
        header_size = struct.unpack_from('<I', header, 4)[0]
        size = struct.unpack_from('<I', header, 24)[0]
        end = os.fstat(stream.fileno()).st_size
        if header_size < 98 or start + header_size + size > end:
            raise ValueError('Invalid or truncated UPDATE.APP record length')
        crc_size = header_size - 98
        expected_crc_size = ((size + 4095) // 4096) * 2
        if self._crc_check and crc_size != expected_crc_size:
            raise ValueError('Missing or invalid UPDATE.APP checksum table')
        name = header[60:76].split(b'\0', 1)[0].decode('ascii')
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', name):
            raise ValueError('Unsafe UPDATE.APP image name')
        if not self._filter.search(name):
            stream.seek(start + header_size + size)
        else:
            checksums = self._read_exact(stream, crc_size)
            target = Path(out_dir) / (name + '.img')
            # Exclusive creation prevents following existing output symlinks or
            # silently replacing files from a previous extraction.
            with target.open('xb') as output:
                try:
                    remaining = size
                    block = 0
                    while remaining:
                        chunk = self._read_exact(stream, min(4096, remaining))
                        if self._crc_check:
                            expected = int.from_bytes(checksums[block: block+2], 'little')
                            if self.crc_x25_calc(chunk) != expected:
                                raise ValueError('Checksum mismatch for ' + name)
                        output.write(chunk)
                        remaining -= len(chunk)
                        block += 2
                except BaseException:
                    output.close()
                    target.unlink()
                    raise
            print('Extracted ' + str(target))
        stream.seek((-stream.tell()) % 4, os.SEEK_CUR)

    @staticmethod
    def crc_x25_check(file_path, crc_data):
        size = os.path.getsize(file_path)
        if len(crc_data) != ((size + 4095) // 4096) * 2:
            return False
        with open(file_path, 'rb') as source:
            for index in range(0, len(crc_data), 2):
                if ImageExtractor.crc_x25_calc(source.read(4096)) != int.from_bytes(crc_data[index:index+2], 'little'):
                    return False
        return True

    def extract(self, path_to_app, out_dir=''):
        count = 0
        with open(path_to_app, 'rb') as stream:
            out_dir = self.touch_output(path_to_app, out_dir)
            while True:
                magic = stream.read(4)
                if not magic:
                    break
                if magic == self.IMAGE_HEADER_ID:
                    self.dump_img(stream, out_dir)
                    count += 1
            if not count:
                raise ValueError('No UPDATE.APP image records found')

    @staticmethod
    def touch_output(app_path, out_dir):
        target = Path(out_dir) if out_dir else Path(app_path).with_name(Path(app_path).name.replace('.', '_'))
        target.mkdir(parents=True, exist_ok=True)
        return str(target)
