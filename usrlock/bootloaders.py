
import os, sys, json, tarfile, hashlib

BOOTLOADERS_ARC = 'HiSiBootloaders.tar.xz'

class Bootloaders():

    def __init__(self, wrkdir: str, lst: list = []):
        self._lst = lst
        self._dir = wrkdir

    def wrkdir(self) -> str:
        return self._dir

    def items(self) -> list:
        return self._lst

    def find(self, kw: str) -> dict | None:
        for el in self._lst:
            if kw == el['path'] or kw in el['dev_models']:
                return el
        return None

    def hash_images(self, el: dict) -> list[str]:
        idx = 0
        out = []
        for f_img in self.extract_images(el):
            sha1 = hashlib.sha1()
            with open(f_img, "rb") as f:
                while chunk := f.read(4096):
                    sha1.update(chunk)
                out.append(sha1.hexdigest())
            idx += 1
        return out

    def extract_images(self, el: dict) -> list[str]:
        i = BOOTLOADERS_ARC.rfind('.') + 1
        p = os.path.join(self._dir, BOOTLOADERS_ARC)
        out = []
        # Open the archive (works for .tar, .tar.gz, .tgz, etc.)
        with tarfile.open(p, 'r:'+ BOOTLOADERS_ARC[i:]) as tar:
            for img in el['imgs']:
                img_path = os.path.join(self._dir, el['path'], img['role'] +'.img')
            	# Extract a single file by its exact path inside the archive
                if not os.path.isfile(img_path):
                	tar.extract('bootloaders/%s/%s.img'% (el['path'], img['role']))
                out.append(img_path)
        return out

    @staticmethod
    def load( manifest_path: str):
        with open( manifest_path, 'r') as f:
            wrkdir = os.path.dirname(manifest_path)
            return Bootloaders(wrkdir, json.load(f))

if __name__ == '__main__':
    bll = Bootloaders.load(sys.argv[1])
    cmd = sys.argv[2]

    if cmd.startswith('puts:'):
        print('\n'.join(map(lambda el: el[cmd[5:]], bll.items())))
    elif cmd.startswith('find:'):
        print('Y' if bll.find(cmd[5:]) else '')
