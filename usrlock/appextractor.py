#
# Module for extracting .img files from Huawei 'UPDATE.APP' packs.
#
# Based on:
# * https://github.com/marcominetti/split_updata.pl
# 
# Made by OpenA @ 2026
#

import os, re, time, binascii, crcmod

class ImageExtractor:

    IMAGE_HEADER_ID = b'\x55\xAA\x5A\xA5'

    def __init__(self, crc_check=True, filter=''):
        self._filter = re.compile(filter or r'.+')
        self._crc_check = crc_check

    def dump_img(self, f, out_dir: str = ''):
        ## 'UPDATE.APP' data structure
        # * First 92 bytes are 0x00
        # * Each file are started with 55AA 5AA5
        # +  4 bytes for Header Length
        # +  4 bytes for Unknown1
        # +  8 bytes for Hardware ID
        # +  4 bytes for File Sequence
        # +  4 bytes for File Size
        # + 16 bytes for File Date
        # + 16 bytes for File Time
        # + 16 bytes for File Type
        # + 16 bytes for Blank1
        # +  2 bytes for Header Checksum
        # +  2 bytes for BlockSize
        # +  2 bytes for Blank2
        # +  (headerLen - 98) for calc file checksum
        # +  (fileSize) of .img data
        # *  padding bytes
        headerLen= int.from_bytes(f.read(4), 'little', signed=False)
        crcLen   = headerLen - 98
        _______  = f.read(4) # Unknown1
        hardwarId= f.read(8)
        fileSeq  = f.read(4)
        fileSize = int.from_bytes(f.read(4), 'little', signed=False)
        fileDate = f.read(16).strip(b'\0').decode()
        fileTime = f.read(16).strip(b'\0').decode()
        fileName = f.read(16).strip(b'\0').decode()
        ________ = f.seek(16+2+2+2, os.SEEK_CUR) # Blank1 + HeaderChecksum + BlockSize + Blank2

        hashLen  = headerLen - 98
        numBytes = self.pretty_bytes(fileSize)
        fileTime = fileTime.replace('.',':')

        if self._filter.search(fileName):
            print(f"📂 Extracting...")
            crc_data = f.read(hashLen)
            img_path = os.path.join(out_dir, fileName+'.img')

            with open(img_path, mode='wb') as o:
                i = 0
                while   i < fileSize:
                    l_max = fileSize - i
                    chunk = f.read(l_max if l_max < 4096 else 4096)
                    i    += o.write(chunk)

            print(f"  💽 {fileName}.img ~ {numBytes}")
            print(f"  🗓️  Created - {fileDate} {fileTime}")
            
            if self._crc_check:
                print(f"  ⏳ Checksum...", end='\r')
                perf_t = time.process_time()
                crc_ok = self.crc_x25_check(img_path, crc_data)
                shortCRC = binascii.b2a_hex(crc_data[0:6]).decode()
                if hashLen > 6:
                    shortCRC += '...'
                print("  %s Checksum [ %s ] ~ %.3f sec."% (
                    '✅' if crc_ok else '🅾️ ', shortCRC, time.process_time() - perf_t))
        else:
            f.seek(fileSize + hashLen, os.SEEK_CUR)
            print(f'🗑️ Skipping {fileName}.img\t{fileDate}\t{numBytes}')

        remaind = 4 - (f.tell() % 4)
        if remaind < 4:
            # We can ignore the remaining padding.
            f.seek(remaind, os.SEEK_CUR)

    # Huawei packs stores CRC-16/X-25 sums of every 4096 bytes
    crc_x25_calc = crcmod.mkCrcFun(0x11021, initCrc=0x0000, rev=True, xorOut=0xFFFF)

    @staticmethod
    def crc_x25_check(file_path: str, crc_data: bytes) -> int:
        crc_ok = True
        with open(file_path, mode='rb') as m:
            k = 0
            while k < len(crc_data):
                chunk = m.read(4096)
                c_dat = int.from_bytes(crc_data[k:k+2], 'little', signed=False)
                c_val = ImageExtractor.crc_x25_calc(chunk)
                if c_dat != c_val:
                    crc_ok = False
                k += 2
        return crc_ok

    @staticmethod
    def pretty_bytes(size: int):
        if size < 1e3: return '%d B'   % size
        if size < 1e4: return '%.2f KB'% (float(size) / 1e3)
        if size < 1e6: return '%.1f KB'% (float(size) / 1e3)
        if size < 1e7: return '%.2f MB'% (float(size) / 1e6) # ~ 1.52  Mb
        if size < 1e9: return '%.1f MB'% (float(size) / 1e6) # ~ 48.3  Mb
        else         : return '%.2f GB'% (float(size) / 1e9)

    @staticmethod
    def parse_filters(match: str):
        s = i = 0
        out = []
        for c in match:
            if c == ',' or c == ' ':
                if s != i:
                    out.append(match[s:i])
                s = i + 1
            i += 1
        if s != i:
            out.append(match[s:])
        return out

    def extract(self, path_to_app: str, out_dir: str = ''):
        with open(path_to_app, mode='rb') as f:
            out_dir = self.touch_output(path_to_app, out_dir)
            # Find the next img block in the file
            while magic := f.read(4):
                if magic == self.IMAGE_HEADER_ID:
                    self.dump_img(f, out_dir)

    @staticmethod
    def touch_output(app_path: str, out_dir: str) -> str:
        if not out_dir:
            f_path  = os.path.dirname (app_path)
            f_name  = os.path.basename(app_path)
            out_dir = os.path.join(f_path, f_name.replace('.', '_'))
        if not os.path.isdir(out_dir):
            os.mkdir(out_dir)
        return out_dir
