# Bootloader archive support originally by OpenA, 2026.
import json
from pathlib import Path
import re
import shutil
import tarfile

BOOTLOADERS_ARC = 'HiSiBootloaders.tar.xz'


class Bootloaders:
    def __init__(self, wrkdir, lst=None):
        self._lst = [] if lst is None else lst
        self._dir = str(Path(wrkdir).resolve())

    def wrkdir(self):
        return self._dir

    def items(self):
        return self._lst

    def find(self, kw):
        return next((el for el in self._lst if kw == el['path'] or kw in el['dev_models']), None)

    def extract_images(self, el):
        out = []
        root = Path(self._dir)
        with tarfile.open(root / BOOTLOADERS_ARC, 'r:xz') as archive:
            for img in el['imgs']:
                if not all(re.fullmatch(r'[A-Za-z0-9_-]+', value) for value in (el['path'], img['role'])):
                    raise ValueError('Unsafe bootloader path')
                target = root / el['path'] / (img['role'] + '.img')
                target.parent.mkdir(exist_ok=True)
                if target.parent.is_symlink() or target.is_symlink():
                    raise ValueError('Bootloader output cannot be a symlink')
                if not target.exists():
                    member = archive.getmember('bootloaders/%s/%s.img' % (el['path'], img['role']))
                    if not member.isfile():
                        raise ValueError('Bootloader archive member must be a regular file')
                    with archive.extractfile(member) as source, target.open('xb') as output:
                        shutil.copyfileobj(source, output)
                out.append(str(target))
        return out

    @staticmethod
    def load(manifest_path):
        manifest = Path(manifest_path).resolve()
        with manifest.open() as source:
            return Bootloaders(manifest.parent, json.load(source))
