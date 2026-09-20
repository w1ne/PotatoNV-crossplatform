# This code originaly based on:
# * https://github.com/WorkHardes/fastbootpy
# * https://github.com/w1ne/PotatoNV-crossplatform/blob/master/usrlock/main.py
# * https://github.com/kitsuned/PotatoNV-crossplatform/blob/master/usrlock/fastboot.py
#
# Reworked by OpenA @ 2026
#
import usb.core
import usb.util
import hashlib

HUAWEI_VENDOR_ID = 0x12D1

S_SEP = f"\n|{'=' * 32}\n"
E_SEP = f"\n|{'-' * 32}\n"

class Fastboot:

    TIMEOUT_READ  = 1500
    TIMEOUT_WRITE = 1500

    def __init__(self):
        self._device = None
        self._s_name = None
        self._w_port = None
        self._r_port = None

    def is_ready(self) -> bool:
        return self._w_port != None and self._r_port != None

    def connect(self) -> bool:
        device = self.select_usb_device()
        if device is None:
            return False
        self._device = device
        config = device.get_active_configuration()
        interface = usb.util.find_descriptor(config, bInterfaceClass=0xff,
                                             bInterfaceSubClass=0x42,
                                             bInterfaceProtocol=3)
        if interface is None:
            raise RuntimeError("No active fastboot interface")
        number = interface.bInterfaceNumber
        try:
            if device.is_kernel_driver_active(number):
                device.detach_kernel_driver(number)
        except NotImplementedError:
            pass  # Windows backends do not support kernel driver queries.
        usb.util.claim_interface(device, number)
        for endpoint in interface:
            if usb.util.endpoint_type(endpoint.bmAttributes) != usb.util.ENDPOINT_TYPE_BULK:
                continue
            if usb.util.endpoint_direction(endpoint.bEndpointAddress) == usb.util.ENDPOINT_IN:
                self._r_port = endpoint
            else:
                self._w_port = endpoint
        if not self.is_ready():
            raise RuntimeError("Fastboot bulk endpoints not found")
        return True

    def close(self):
        if self._device is not None:
            usb.util.dispose_resources(self._device)
        self._device = self._r_port = self._w_port = None

    def _execute(self, command):
        if not self.send(command):
            raise RuntimeError("Fastboot command was not sent")
        response = self.recv()
        if not response.startswith(b'OKAY'):
            raise RuntimeError("Fastboot command failed: " + response.decode(errors='replace'))
        return response[4:]

    def write_nvme(self, prop, data):
        self._execute(('getvar:nve:' + prop + '@').encode() + data)
        print('Updated ' + prop)

    def erase(self, *parts):
        for part in parts:
            self._execute(('erase:' + part).encode())
            print('Erased ' + part)

    def oem_unlock(self, key):
        self._execute(('oem unlock ' + key).encode())
        print('OEM unlock completed')

    def send(self, command):
        if not self.is_ready():
            raise RuntimeError("Fastboot is not connected")
        return self._w_port.write(command, self.TIMEOUT_WRITE) == len(command)

    def recv(self, cap=1024):
        # INFO packets are progress; only OKAY/FAIL/DATA terminate a reply.
        # Converting PyUSB arrays explicitly avoids bytes/array concatenation.
        for _ in range(1024):
            packet = bytes(self._r_port.read(cap, self.TIMEOUT_READ))
            if packet.startswith(b'INFO'):
                print(packet[4:].decode(errors='replace'))
            elif packet[:4] in (b'OKAY', b'FAIL', b'DATA'):
                return packet
            else:
                raise RuntimeError('Invalid or missing fastboot response')
        raise RuntimeError('Too many fastboot progress packets')

    def command(self):
        while True:
            c = input("⌨️  ")
            if c == 'q' or c == 'exit' or c == 'quit':
                break
            elif c.startswith('reboot'):
                self.reboot(mode=c[7:])
                break
            else:
                d = self.send(c.encode())
                r = self.recv().decode()
                o = '🚫' if not d or r.startswith('FAIL') else '📄'
                print(f"{o} {r[:4]} {r[4:]}", end='\n\n')

    def reboot(self, mode=''):
        self._execute(('reboot' + ('-' + mode if mode else '')).encode())

    @staticmethod
    def match_usb_device(d):
        #if d.idVendor == HUAWEI_VENDOR_ID:
        #    return True
        for cfg in d:
            if usb.util.find_descriptor(cfg,
                bInterfaceClass   = 0xFF, # FASTBOOT CLASS
                bInterfaceSubClass= 0x42, # FASTBOOT SUBCLASS
                bInterfaceProtocol= 0x3   # FASTBOOT PROTOCOL
            ) is not None:
                return True
        return False

    @staticmethod
    def select_usb_device():
        devices = list(usb.core.find(find_all=True, custom_match=Fastboot.match_usb_device))
        if not devices:
            print('No fastboot device found')
            return None
        if len(devices) == 1:
            return devices[0]
        for index, device in enumerate(devices):
            print('%d: %s' % (index, device.serial_number or 'Unknown serial'))
        try:
            index = int(input('Device number: '))
        except ValueError:
            return None
        return devices[index] if 0 <= index < len(devices) else None

    def usrlock(self, key: str = '', fblock: str = ''):

        if key and len(key) != 16:
            print(f"🚫 USRKEY must be a 16-char string ({len(key)} == '{key}')")
            return

        if fblock and fblock != '0' and fblock != '1':
            print(f"🚫 FBLOCK value must between 0-1 (you pass: {fblock})")
            return

        if fblock:
            self.write_nvme('FBLOCK', fblock.encode())
        if key:
            sha = hashlib.sha256(key.encode())
            self.write_nvme('USRKEY', sha.digest())
            self.write_nvme('WVLOCK', key.encode())
            if 'y' == input("🚧 Attempt to OEM unlock? (y/n) "):
                self.oem_unlock(key)

        if 'y' == input("🚧 Do FRP/Data wipe before reboot...? (y/n) "):
            self.erase('frp', 'userdata')
        if 'y' == input("🚧 Want to reboot? (y/n) "):
            self.reboot()
        else:
            self.command()
