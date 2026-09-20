# Reworked from:
# * https://github.com/96boards-hikey/tools-images-hikey970/blob/hikey970_v1.0/hisi-idt.py
# 
# Copyright 2019 Penn Mackintosh
# Copyright 2020 Andrey Smirnoff
#
# Modyfied by OpenA @ 2026
#
import serial, os, hashlib, time, binascii
import serial.tools.list_ports

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

    def send_frame(self, data: bytes) -> bool:
        crc = binascii.crc_hqx(data, 0)
        data += crc.to_bytes(2, byteorder="big", signed=False)
        try:
            self.serial.reset_output_buffer()
            self.serial.reset_input_buffer()
            if self.serial.write(data) != len(data):
                return False
            ack = self.serial.read(1)
            if ack != self.ack:
                print(f"Invalid or missing ACK: {ack!r}; expected {self.ack!r}")
                return False
        except Exception as e:
            print(f"⛔ {e}", end='\n\n')
            return False
        return True

    def send_head_frame(self, length: int, address: int) -> bool:
        if self.serial:
            self.serial.timeout = 0.09
        print("; 🗳️  Sending header frame...", end=E_SEP)
        data = self.headframe
        data += length.to_bytes(4, byteorder="big", signed=False)
        data += address.to_bytes(4, byteorder="big", signed=False)
        return self.send_frame(data)

    def send_data_frame(self, n: int, data: bytes, n_frames: int) -> bool:
        if self.serial:
            self.serial.timeout = 0.45
        print(f"; ... [{n}/{n_frames}]{' '*12}", end='\r')
        head = bytearray(self.dataframe)
        head.append(n & 0xFF)
        head.append((~ n) & 0xFF)
        return self.send_frame(bytes(head) + data)

    def send_tail_frame(self, n: int) -> bool:
        if self.serial:
            self.serial.timeout = 0.01
        print(E_SEP +"; 🍤 Sending tail frame...", end=E_SEP)
        data = bytearray(self.tailframe)
        data.append(n & 0xFF)
        data.append((~ n) & 0xFF)
        return self.send_frame(bytes(data))

    def send_data(self, data, length: int, address: int) -> bool:
        if isinstance(data, bytes):
            length = len(data)
        n_frames = (length + MAX_DATA_LEN - 1) // MAX_DATA_LEN
        if not self.send_head_frame(length, address):
            return False
        for n in range(n_frames):
            count = min(length - n * MAX_DATA_LEN, MAX_DATA_LEN)
            chunk = data[n * MAX_DATA_LEN:n * MAX_DATA_LEN + count] if isinstance(data, bytes) else data.read(count)
            if len(chunk) != count or not self.send_data_frame(n + 1, chunk, n_frames):
                return False
        if not self.send_tail_frame(n_frames + 1):
            return False
        time.sleep(0.5)
        return True

    @staticmethod
    def boot_flash(el, img_paths):
        if not ImageFlasher.test_hash(el, img_paths):
            raise ValueError("Bootloader checksum mismatch")
        flasher = ImageFlasher()
        try:
            if not flasher.connect_serial():
                return False
            for item, image in zip(el['imgs'], img_paths):
                with open(image, 'rb') as source:
                    if not flasher.send_data(source, os.fstat(source.fileno()).st_size, item['addr']):
                        return False
            print("Bootloader uploaded.")
            return True
        finally:
            if flasher.serial is not None:
                flasher.serial.close()

    @staticmethod
    def test_hash(el: dict, img_paths: list[str]):
        if len(el['imgs']) != len(img_paths):
            return False
        idx = mis = 0
        print("%s; 🛅 Testing images \033[1m%s\033[0m"% (S_SEP, el['path']), end=S_SEP)
        for p_img in img_paths:
            sha1 = hashlib.sha1()
            role = el['imgs'][idx]['role']
            hash = el['imgs'][idx]['hash']
            print('; ┌ %s.img ┐\n; └── \033[1;37;42m%s\033[0m'% (role, hash))
            with open(p_img, 'rb') as f:
                while chunk := f.read(4096):
                    sha1.update(chunk)
            hsum = sha1.hexdigest()
            print(';   ╚ \033[1;37;4%dm%s\033[0m'% ((hsum == hash) + 1, hsum))
            mis += hash != hsum
            idx += 1
        print("%s; 🛂 Passed %d/%d"% (E_SEP[1:], idx - mis, idx), end='\n\n')

        return mis == 0

    def connect_serial(self, device=None) -> bool:
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
