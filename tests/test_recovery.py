import binascii
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

from usrlock.appextractor import ImageExtractor
from usrlock.bootloaders import Bootloaders
from usrlock.imageflasher import ImageFlasher

ROOT = Path(__file__).resolve().parents[1]


def record(name='SYSTEM', data=b'hello', declared_size=None, crc=None):
    crc = struct.pack('<H', ImageExtractor.crc_x25_calc(data)) if crc is None else crc
    head = bytearray(98)
    head[:4] = ImageExtractor.IMAGE_HEADER_ID
    struct.pack_into('<I', head, 4, 98 + len(crc))
    struct.pack_into('<I', head, 24, len(data) if declared_size is None else declared_size)
    head[60:60+len(name)] = name.encode()
    result = bytes(head) + crc + data
    return result + b'\0' * (-len(result) % 4)


class SerialTests(unittest.TestCase):
    def setUp(self):
        self.flasher = ImageFlasher()
        self.flasher.serial = Mock()
        self.flasher.serial.write.side_effect = len

    def test_timeout_is_failure(self):
        self.flasher.serial.read.return_value = b''
        self.assertFalse(self.flasher.send_frame(b'123456789'))

    def test_crc_known_vector(self):
        self.flasher.serial.read.return_value = b'\xaa'
        self.assertTrue(self.flasher.send_frame(b'123456789'))
        self.flasher.serial.write.assert_called_once_with(b'123456789\x31\xc3')

    def test_short_write_is_failure(self):
        self.flasher.serial.write.side_effect = lambda data: len(data)-1
        self.flasher.serial.read.return_value = b'\xaa'
        self.assertFalse(self.flasher.send_frame(b'abc'))

    def test_failed_upload_stops_before_tail(self):
        self.flasher.send_head_frame = Mock(return_value=True)
        self.flasher.send_data_frame = Mock(return_value=False)
        self.flasher.send_tail_frame = Mock()
        self.assertIs(self.flasher.send_data(b'data', 4, 0), False)
        self.flasher.send_tail_frame.assert_not_called()


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / 'UPDATE.APP'
        self.out = self.root / 'output'

    def extract(self, payload, check=True, filter=''):
        self.app.write_bytes(payload)
        return ImageExtractor(check, filter).extract(str(self.app), str(self.out))

    def test_extract_valid_image(self):
        self.extract(b'\0'*92 + record())
        self.assertEqual((self.out / 'SYSTEM.img').read_bytes(), b'hello')

    def test_reject_path_traversal(self):
        with self.assertRaises(ValueError):
            self.extract(record('../escape'))
        self.assertFalse((self.root / 'escape.img').exists())

    def test_reject_truncated_header(self):
        with self.assertRaises(ValueError):
            self.extract(ImageExtractor.IMAGE_HEADER_ID + b'\x01\0\0\0')

    def test_reject_checksum_mismatch(self):
        with self.assertRaises(ValueError):
            self.extract(record(crc=b'\0\0'))
        self.assertFalse((self.out / 'SYSTEM.img').exists())

    def test_reject_missing_checksums(self):
        with self.assertRaises(ValueError):
            self.extract(record(crc=b''))

    def test_existing_image_not_overwritten(self):
        self.out.mkdir()
        target = self.out / 'SYSTEM.img'
        target.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):
            self.extract(record())
        self.assertEqual(target.read_bytes(), b'keep')

    def test_truncated_payload_terminates(self):
        self.app.write_bytes(record(declared_size=10000))
        result = subprocess.run([sys.executable, '-m', 'usrlock', '-C', 'extract', str(self.app), '-O', str(self.out)], cwd=ROOT, capture_output=True, timeout=3)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.out / 'SYSTEM.img').exists())


class BootloaderTests(unittest.TestCase):
    def test_extract_relative_to_manifest_not_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with tarfile.open(root / 'HiSiBootloaders.tar.xz', 'w:xz') as archive:
                item = tarfile.TarInfo('bootloaders/chip/fastboot.img')
                item.size = 4
                archive.addfile(item, io.BytesIO(b'test'))
            loader = Bootloaders(str(root))
            paths = loader.extract_images({'path': 'chip', 'imgs': [{'role': 'fastboot'}]})
            self.assertEqual(Path(paths[0]).read_bytes(), b'test')


class CLITests(unittest.TestCase):
    def test_no_arguments_shows_help_without_hardware(self):
        result = subprocess.run([sys.executable, '-m', 'usrlock'], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('usage:', result.stdout)

    def test_unknown_command_rejected(self):
        result = subprocess.run([sys.executable, '-m', 'usrlock', '-C', 'wrong', 'README.txt'], cwd=ROOT, capture_output=True)
        self.assertEqual(result.returncode, 2)



class FastbootTests(unittest.TestCase):
    def test_empty_response_does_not_report_success(self):
        from usrlock.fastboot import Fastboot
        device = Fastboot()
        device.send = Mock(return_value=True)
        device.recv = Mock(return_value=b'')
        with self.assertRaises(RuntimeError):
            device.write_nvme('FBLOCK', b'0')

    def test_multiple_devices_require_valid_selection(self):
        from usrlock.fastboot import Fastboot
        devices = [Mock(serial_number='one'), Mock(serial_number='two')]
        with patch('usrlock.fastboot.usb.core.find', return_value=devices) as find, patch('builtins.input', return_value='-1'):
            self.assertIsNone(Fastboot.select_usb_device())
            self.assertTrue(find.call_args.kwargs['find_all'])

    def test_recv_converts_usb_arrays_and_stops_at_terminal_packet(self):
        from array import array
        from usrlock.fastboot import Fastboot
        device = Fastboot()
        device._r_port = Mock()
        device._r_port.read.side_effect = [array('B', b'INFOworking'), array('B', b'OKAYdone')]
        self.assertEqual(device.recv(), b'OKAYdone')


class AdditionalTests(unittest.TestCase):
    def test_bootloader_hash_failure_prevents_serial_connection(self):
        with patch.object(ImageFlasher, 'test_hash', return_value=False), patch.object(ImageFlasher, 'connect_serial') as connect:
            with self.assertRaises(ValueError):
                ImageFlasher.boot_flash({'imgs': []}, [])
            connect.assert_not_called()

    @unittest.skipIf(os.name == "nt", "Creating symlinks requires Windows developer mode")
    def test_bootloader_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'chip').symlink_to(root, target_is_directory=True)
            with tarfile.open(root/'HiSiBootloaders.tar.xz', 'w:xz'):
                pass
            with self.assertRaises(ValueError):
                Bootloaders(root).extract_images({'path':'chip', 'imgs':[{'role':'fastboot'}]})

    def test_checksum_known_vector(self):
        self.assertEqual(ImageExtractor.crc_x25_calc(b'123456789'), 0x906e)

class BundledBootloadersTests(unittest.TestCase):
    def test_all_bundled_images_match_manifest(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('HiSiBootloaders.tar.xz', 'manifest.json'):
                shutil.copyfile(ROOT / 'bootloaders' / name, root / name)
            loaders = Bootloaders.load(root / 'manifest.json')
            for item in loaders.items():
                with self.subTest(bootloader=item['path']):
                    self.assertTrue(ImageFlasher.test_hash(item, loaders.extract_images(item)))
