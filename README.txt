Usrlock - CLI utility for unlocking Huawei devices on Kirin SoCs.
Copyright (C) 2019  Penn Mackintosh (penn5)
Copyright (C) 2020  Andrey Smirnoff (mashed-potatoes)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

Recovered fork improvements
---------------------------
Python 3.10 or newer is required. Install dependencies into a virtual environment:

    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt
    .venv/bin/python -m usrlock --help

On Windows use .venv\Scripts\python.exe instead. Fastboot requires a working
libusb backend and OS USB permissions; test-point serial access requires access
to the selected serial device.

Commands (module invocation works on all platforms):

    python -m usrlock -C extract UPDATE.APP -O extracted -T
    python -m usrlock -C extract UPDATE.APP -S '^RECOVERY' -O recovery -T
    python -m usrlock -C bootloader -S hisi620 -T
    python -m usrlock -C bootloader -S hisi620
    python -m usrlock -C fastboot
    python -m usrlock -C fastboot -K 1234567890123456 -F 0

The first three commands only read local firmware. For bootloader, -T checks
SHA-1 hashes without connecting to hardware; an actual upload also verifies
hashes before opening the serial port. For extract, -T validates each 4096-byte
CRC block. Existing output images are never overwritten. --search is a regular
expression for extract and an exact bootloader path/model for bootloader.

The last three commands access hardware and can modify the device. Fastboot
key/flag writes only happen when their options are supplied. OEM unlocking,
partition erasure and reboot remain separate interactive choices.

On Unix, activate the virtual environment and use ./potato extract ..., ./potato
bootloader ..., or ./potato fastboot. The wrapper works outside the repository
working directory. Running without arguments prints help and accesses no device.

Migration: the previous combined workflow in main.py is superseded by explicit
bootloader and fastboot commands. Replace -b NAME with -C bootloader -S NAME;
replace --skip-bootloader -k KEY with -C fastboot -K KEY. Bootloader upload no
longer implicitly starts key writing. There is no implemented GUI in this tree.

Attribution and scope
---------------------
CLI, UPDATE.APP extraction, bootloader archive packaging, CRC acceleration and
serial/fastboot improvements originate from OpenA-forks/PotatoNV-cross-gui,
main-rework through eabab28. Original authors are retained in the imported
commits and source headers. Bootloader images originate from
https://github.com/kitsuned/HiSiBootloaders as documented in bootloaders/README.md.
The fork's data-decryption script and its instructions are intentionally omitted;
they alter recovery/encryption state and are outside this tool recovery scope.
The unimplemented GUI dispatch and dialout-only shell gate are also omitted.

Validation
----------
    python -m unittest discover -s tests -v
    python -m compileall -q usrlock tests

Tests use synthetic UPDATE.APP files, mocked USB/serial transports, and checksums
of the bundled images. They do not open physical devices or prove hardware
compatibility. The device table was inherited from the fork, not revalidated.

A proposed GitHub Actions matrix is in docs/ci-tests.yml. It is not active: the
publishing OAuth credential lacks workflow scope. A maintainer can enable it by
moving it to .github/workflows/tests.yml with a workflow-capable credential.
