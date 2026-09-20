# Command-line interface adapted from OpenA's main-rework fork, 2026.
import argparse
from pathlib import Path
import re
import sys


def create_parser():
    parser = argparse.ArgumentParser(description='Huawei bootloader and UPDATE.APP tools (Python 3.10+).')
    parser.add_argument('-C', '--command', choices=('bootloader', 'fastboot', 'extract'))
    parser.add_argument('-T', '--test-hash', action='store_true', help='Check bootloader hashes without connecting to hardware; verify UPDATE.APP CRCs')
    parser.add_argument('-S', '--search', default='', help='Bootloader model/name, or image-name regular expression')
    parser.add_argument('-O', '--output', default='', help='Image extraction output directory')
    parser.add_argument('-F', '--fblock', choices=('0', '1'), default='')
    parser.add_argument('-K', '--key', default='', help='16 ASCII character OEM key')
    parser.add_argument('input', nargs='?', help='UPDATE.APP or bootloader manifest.json')
    return parser


def fastboot_mode(key='', fblock=''):
    from .fastboot import Fastboot
    device = Fastboot()
    try:
        if not device.connect():
            return 1
        if key or fblock:
            device.usrlock(key, fblock)
        else:
            device.command()
        return 0
    finally:
        device.close()


def main(argv=None):
    parser = create_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        if args.input:
            parser.error('Select a command with -C')
        parser.print_help()
        return 0
    if args.key and (len(args.key) != 16 or not args.key.isascii()):
        parser.error('--key must contain 16 ASCII characters')
    if args.command != 'fastboot' and (args.key or args.fblock):
        parser.error('--key and --fblock require -C fastboot')
    if args.command == 'fastboot':
        if args.input or args.test_hash or args.search or args.output:
            parser.error('fastboot does not accept an input file, hash check, search or output')
    elif args.command == 'extract' and not args.input:
        parser.error('extract requires an UPDATE.APP input file')
    try:
        if args.command == 'fastboot':
            return fastboot_mode(args.key, args.fblock)
        if args.command == 'extract':
            from .appextractor import ImageExtractor
            ImageExtractor(args.test_hash, args.search).extract(args.input, args.output)
            return 0
        from .bootloaders import Bootloaders
        from .imageflasher import ImageFlasher
        manifest = args.input or str(Path(__file__).resolve().parents[1] / 'bootloaders' / 'manifest.json')
        loaders = Bootloaders.load(manifest)
        if args.search:
            selected = loaders.find(args.search)
            if selected is None:
                raise ValueError('Unknown bootloader: ' + args.search)
        else:
            for index, item in enumerate(loaders.items(), 1):
                print('%d: %s (%s)' % (index, item['name'], item['path']))
            index = int(input('Bootloader number: '))
            if index < 1 or index > len(loaders.items()):
                raise ValueError('Bootloader number out of range')
            selected = loaders.items()[index - 1]
        images = loaders.extract_images(selected)
        if args.test_hash:
            return 0 if ImageFlasher.test_hash(selected, images) else 1
        return 0 if ImageFlasher.boot_flash(selected, images) else 1
    except (OSError, ValueError, KeyError, re.error, RuntimeError) as error:
        print('Error: ' + str(error), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print('Cancelled.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    sys.exit(main())
