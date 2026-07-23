
import sys, usb, hashlib

HUAWEI_VENDOR_ID = 0x12D1

S_SEP = f"\n|{'=' * 32}\n"
E_SEP = f"\n|{'-' * 32}\n"

class Fastboot:

    TIMEOUT_READ  = 1500
    TIMEOUT_WRITE = 1500

    def __init__(self):
        self._s_name = None
        self._w_port = None
        self._r_port = None

    def is_ready(self) -> bool:
        return self._w_port != None and self._r_port != None

    def connect(self) -> bool:
        fb_dev = self.select_usb_device()
        if fb_dev is not None:
            self._s_name = fb_dev.serial_number or '%x:%x'%(fb_dev.idVendor,fb_dev.idProduct)

            print(f"| 📲 Connect to \033[1m{self._s_name}\033[0m")
            try:
                # fb_dev.reset() -- generate exception
                if fb_dev.is_kernel_driver_active(0):
                    fb_dev.detach_kernel_driver(0)
            except usb.USBError as error:
                print(f"| ⚠️  Failed \033[1m{self._s_name}\033[0m {error}"+ E_SEP)
                return False

            for cfg in fb_dev:
                for iface in cfg:
                    for ep in iface:
                        if usb.core.util.endpoint_direction(ep.bEndpointAddress) == usb.core.util.ENDPOINT_IN:
                            self._r_port = ep
                        else:
                            self._w_port = ep
            _____ = self.recv() # clear buffer
            print("| ✅ Ready to communicate."+ E_SEP)
            return True
        return False

    def write_nvme(self, prop: str, data: bytes):
        print(f"🍥 Writing {prop} data to NVE...")
        done = self.send(f'getvar:nve:{prop}@'.encode() + data)
        resp = self.recv().decode()
        if not done or resp.startswith('FAIL'):
              print(f"❌ Failed to write {prop}. {resp[4:]}", end='\n\n')
        else: print(f"🧩 Write {prop} {resp}", end='\n\n')

    def erase(self, *parts: str):
        print("🧹 Erasing partitions...")
        for p in parts:
            d = self.send(f'erase:{p}'.encode())
            r = self.recv().decode()
            if not d or r.startswith('FAIL'):
                  print(f"❌ Failed '{p}' {r[4:]}")
            else: print(f"✔️  Erased '{p}' {r}")
        print("")

    def oem_unlock(self, key: str):
        print("📦 Sending OEM Key...")
        done = self.send(b'oem unlock '+ key.encode())
        resp = self.recv().decode()
        if not done or resp.startswith('FAIL'):
              print(f"❌ OEM Unlock failed. {resp[4:]}", end='\n\n')
        else: print(f"✅ Successful OEM unlocking. {resp}", end='\n\n')

    def send(self, cmd: bytes) -> bool:
        done = False
        while not done:
            try:
                self._w_port.write(cmd, self.TIMEOUT_WRITE)
                done = True
            except usb.USBError as error:
                if 'y' != input(f"⚠️  {error}\n ** Retry? (y/n) "):
                    break
        return done

    def recv(self, cap = 1024) -> bytes:
        resp = bytes()
        while True:
            try:
                buff = self._r_port.read(cap, self.TIMEOUT_READ)
                if buff is None or buff == b'':
                    break
                resp += buff
            except usb.USBError as e:
                break
        return resp

    def reboot(self, mode = ''):
        cmd = b'reboot'
        if mode: cmd += (b'-' if mode == 'bootloader' else b':') + mode.encode()
        else   : mode = 'device'
        print(f"♻️  Reboot {mode}... ")
        done = self.send(cmd)
        resp = self.recv().decode() if done else 'FAIL'
        print(f' ↪︎ {resp}', end='\n\n')

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
        print("⏱️  Waiting for fastboot device...", end=S_SEP)
        device = usb.core.find(custom_match = Fastboot.match_usb_device)
        if device is None:
            print("| 📵  No any device found (check you phone cable)"+ E_SEP)
        elif not isinstance(device, usb.core.Device):
            promt = []
            for n,dev in enumerate(device):
                vendor  = usb.util.get_string(dev, 1)
                product = usb.util.get_string(dev, 2)
                mtp     = usb.util.get_string(dev, 5)
                serial  = usb.util.get_string(dev, dev.iSerialNumber)
                promt.append(f"| {n}: {'📱' if mtp == 'MTP' else '🖥️'} {vendor} {product} \033[1m{serial}\033[0m")
            idx = int(input(
                f"{'\n'.join(promt) + E_SEP}| ** Enter you device number: "))
            if idx >= len(device):
                print(f"| ‼️  Wrong device index ({idx} > {len(device) - 1}){E_SEP}")
                return None
            else:
                return device[idx]
        return device

    @staticmethod
    def usrlock(key: str, fblock: str = ''):

        sha = hashlib.sha256()
        fb  = Fastboot()

        if len(key) != 16:
            print(f"🚫 USRKEY must be a 16-char string ({len(key)} == '{key}')")
            return

        if fblock and fblock != '0' and fblock != '1':
            print(f"🚫 FBLOCK value must between 0-1 (you pass: {fblock})")
            return

        if fb.connect():
            sha.update(key.encode())

            if fblock:
                fb.write_nvme('FBLOCK', fblock.encode())
            fb.write_nvme('USRKEY', sha.digest())
            fb.write_nvme('WVLOCK', key.encode())

            if 'y' == input("🚧 Attempt to OEM unlock? (y/n) "):
                fb.oem_unlock(key)
            if fblock and 'y' == input("🚧 Do FRP/Data wipe before reboot...? (y/n) "):
                fb.erase('frp', 'userdata')
            if 'y' == input("🚧 Want to reboot? (y/n) "):
                fb.reboot()

if __name__ == '__main__':
    Fastboot.usrlock( key=sys.argv[1], fblock=sys.argv[2] )
