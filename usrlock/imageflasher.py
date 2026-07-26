# Reworked from:
# * https://github.com/96boards-hikey/tools-images-hikey970/blob/hikey970_v1.0/hisi-idt.py
# 
# Copyright 2019 Penn Mackintosh
# Copyright 2020 Andrey Smirnoff
#
# Modyfied by OpenA @ 2026
#
import serial, os, sys, time, binascii
import serial.tools.list_ports
from  bootloaders import Bootloaders

S_SEP = f"\n:{'*' * 32}\n"
E_SEP = f"\n;{'-' * 32}\n"

def calc_crc(data, crc=0):
    for char in data:
        crc = ((crc << 8) | char) ^ binascii.crc_hqx(bytes([(crc >> 8) & 0xFF]), 0)
    for i in range(0,2):
        crc = ((crc << 8) | 0) ^ binascii.crc_hqx(bytes([(crc >> 8) & 0xFF]), 0)
    return crc & 0xFFFF


BOOT_HEAD_LEN = 0x4F00
MAX_DATA_LEN = 0x400
IDT_BAUDRATE = 115200
IDT_VID=0x12D1
IDT_PID=0x3609


class ImageFlasher:
    def __init__(self):
        self.serial = None
        self.headframe = bytes([0xFE, 0x00, 0xFF, 0x01])
        self.dataframe = bytes([0xDA])
        self.tailframe = bytes([0xED])
        self.ack = bytes([0xAA])

    def send_frame(self, data):
        crc = calc_crc(data)
        data += crc.to_bytes(2, byteorder="big", signed=False)
        try:
            self.serial.reset_output_buffer()
            self.serial.reset_input_buffer()
            self.serial.write(data)
            ack = self.serial.read(1)
            if ack and ack != self.ack:
                print(f"⛔ Invalid ACK from device! Read: {hex(ack)}, excepted: {hex(self.ack[0])}", end='\n\n')
                return False
        except Exception as e:
            print(f"⛔ {e}", end='\n\n')
            return False
        return True

    def send_head_frame(self, length, address):
        self.serial.timeout = 0.09
        print("; 🗳️  Sending header frame...", end=E_SEP)
        data = self.headframe
        data += length.to_bytes(4, byteorder="big", signed=False)
        data += address.to_bytes(4, byteorder="big", signed=False)
        return self.send_frame(data)

    def send_data_frame(self, n: int, data: bytes, n_frames: int) -> bool:
        self.serial.timeout = 0.45
        print(f"; ... [{n}/{n_frames}]{' '*12}", end='\r')
        head = bytearray(self.dataframe)
        head.append(n & 0xFF)
        head.append((~ n) & 0xFF)
        return self.send_frame(bytes(head) + data)

    def send_tail_frame(self, n):
        if self.serial:
            self.serial.timeout = 0.01
        print(E_SEP +"; 🍤 Sending tail frame...", end=E_SEP)
        data = bytearray(self.tailframe)
        data.append(n & 0xFF)
        data.append((~ n) & 0xFF)
        return self.send_frame(bytes(data))

    def send_data(self, data, length, address):
        if isinstance(data, bytes):
            length = len(data)
        n_frames = length // MAX_DATA_LEN + (1 if length % MAX_DATA_LEN > 0 else 0)
        if not self.send_head_frame(length, address):
            return
        n = 0
        print(f"; 🗃️  Sending data frames:", end='\n;> [0/0] ..')
        while length > MAX_DATA_LEN:
            if isinstance(data, bytes):
                f = data[n * MAX_DATA_LEN:(n + 1) * MAX_DATA_LEN]
            else:
                f = data.read(MAX_DATA_LEN)
            if not self.send_data_frame(n + 1, f, n_frames):
                return
            n += 1
            length -= MAX_DATA_LEN
        if length:
            if isinstance(data, bytes):
                f = data[n * MAX_DATA_LEN:]
            else:
                f = data.read()
            if not self.send_data_frame(n + 1, f, n_frames):
                return
            n += 1
        self.send_tail_frame(n + 1)
        time.sleep(0.5)

    @staticmethod
    def bootflash(manifest_path: str, hisi: str):
        flasher = ImageFlasher()
        flasher.connect_serial()

        tree = Bootloaders.load(manifest_path)
        el   = tree.find(hisi)
        idx  = 0
        for f_img in tree.extract_images(el):
            role = el['imgs'][idx]['role']
            addr = el['imgs'][idx]['addr']
            print("%s+ 💾 Flashing %s"% (S_SEP, role), end=S_SEP)

            with open(f_img, "rb") as f:
                flasher.send_data(f, os.fstat(f.fileno()).st_size, addr)
            idx += 1
        print("🍀 Bootloader uploaded.", end='\n\n')

    @staticmethod
    def testimage(manifest_path: str, hisi: str):
        tree = Bootloaders.load(manifest_path)
        el   = tree.find(hisi)
        idx  = nok = 0
        print("%s; 🛅 Testing images \033[1m%s\033[0m"% (S_SEP, el['path']), end=S_SEP)
        for sha1 in tree.hash_images(el):
            role = el['imgs'][idx]['role']
            hash = el['imgs'][idx]['hash']
            cmp  = hash == sha1
            print('; ┌ %s.img ┐\n; └── \033[1;37;42m%s\033[0m\n;   ╚ \033[1;37;4%dm%s\033[0m'% (role, hash, cmp+1, sha1))
            nok += cmp
            idx += 1
        print("%s; 🛂 Passes: %d"% (E_SEP[1:], nok), end='\n\n')

    def connect_serial(self, device=None):
        print("🔍 Waiting for device in IDT mode")
        while not device:
            ports = serial.tools.list_ports.comports(include_links=False)
            for port in ports:
                if port.vid == IDT_VID and port.pid == IDT_PID:
                    if not device:
                        print(f"📟 Autoselecting {port.hwid} aka {port.description} at {port.device}", end='\n\n')
                        device = port.device
                    else:
                        print("⚠️ Multiple devices detected in IDT mode", end='\n\n')
                        return False
            if not device:
                time.sleep(2)

        if not device:
            print(f"📵 Need a device in IDT mode plugged in to this computer", end='\n\n')
            return False
        self.serial = serial.Serial(dsrdtr=True, rtscts=True, port=device.replace("COM", r"\\.\COM"), baudrate=IDT_BAUDRATE, timeout=1)
        return True

    def __del__(self):
        try:
            self.serial.close()
        except:
            pass

if __name__ == '__main__':
    path = sys.argv[1]
    hisi = sys.argv[2]
    if hisi.startswith('test:'):
        ImageFlasher.testimage( path, hisi[5:] )
    else:
   	    ImageFlasher.bootflash( path, hisi )
