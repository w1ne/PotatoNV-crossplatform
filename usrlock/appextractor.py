#!/usr/bin/env python3

# Huawei 'UPDATE.APP' files Extractor.
#
# Reworked from:
# * https://github.com/96boards-hikey/tools-images-hikey970/blob/hikey970_v1.0/hisi-idt.py
# 
# Made by OpenA @ 2026
#

import os, argparse, re, time, binascii

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
                crc_ok = self.crc_check(img_path, crc_data)
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

    # Find the next file block in the main file
    @staticmethod
    def crc16(data: bytes) -> int:
        crc = 0xFFFF
        for b in data:
            for i in range(0,8):
                crc = (crc >> 1) ^ (0x8408 if (crc ^ b) & 1 else 0)
                b >>= 1
        crc = (~crc) & 0xFFFF
        # Swap high and low bytes to match the final assembly operations
        return crc # (crc >> 8) | (crc << 8)

    # Find the next file block in the main file
    @staticmethod
    def crc_check(file_path: str, crc_data: bytes) -> int:
        crc_ok = True
        with open(file_path, mode='rb') as m:
            k = 0
            while k < len(crc_data):
                chunk = m.read(4096)
                c_sum = int.from_bytes(crc_data[k:k+2], 'little', signed=False)
                if c_sum != ImageExtractor.crc16(chunk):
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
            while magic := f.read(4):
                if magic == self.IMAGE_HEADER_ID:
                    self.dump_img(f, out_dir)

if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        usage="\n  appextractor.py [--filter='RECOVERY*'] [--output=<name|path>] <UPDATE.APP>",
        description="A tool for extract .img files from Huawei UPDATE.APP pack."
    )
    parser.add_argument("-N", "--no-crc-check", help="disable checksum test", action="store_true")
    parser.add_argument("-O", "--output"      , help="name or path of directory, where will extract files")
    parser.add_argument("-F", "--filter"      , help="extract only specific .img according to regex")
    parser.add_argument(      "app_path"      , help="path to UPDATE.APP file")

    args = parser.parse_args()
    if os.path.isfile(args.app_path):
        hwu = ImageExtractor(crc_check=not args.no_crc_check, filter=args.filter)
        if not args.output:
            d = os.path.dirname (args.app_path)
            b = os.path.basename(args.app_path)
            args.output = os.path.join(d, b.replace('.', '_'))
        if not os.path.isdir(args.output):
            os.mkdir(args.output)
        hwu.extract(args.app_path, args.output)
    else:
        print(f"\n file '{args.app_path}' - is not exist!", end='\n\n')
