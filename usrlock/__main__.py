
import os, sys, argparse

if sys.version_info < (3, 6, 0):
    print("error: Python version is too old.")
    exit(1)

g_tree = os.getenv('USRLOCK_DEV_TAB')
g_warn = os.getenv('USRLOCK_WARN')
g_help = os.getenv('USRLOCK_HELP', '-C <command> [options]')
parser = argparse.ArgumentParser(
    prog   = os.getenv('USRLOCK_PROG', __package__),
    epilog = os.getenv('USRLOCK_INFO', '\n'),

    formatter_class=argparse.RawDescriptionHelpFormatter,

    usage      ='\n  %(prog)s '+ g_help,
    description="""
possible commands:
  bootloader - Load device specific bootloader (for test-point mode only).
  fastboot   - An interface for send commands and receive messages from the device.
  extract    - A tool for extract .img files from Huawei UPDATE.APP pack.
  gui        - A graphical window mode (ui toolkit required)
""")
tspm = parser.add_argument_group(
    title='factory (test-point) mode only'
)
parser.add_argument("-T", "--test-hash", help="enable checksum validation for .img files", action="store_true")
parser.add_argument("-C", "--command"  , help="(check the commands section above)", metavar='<cmd>')
parser.add_argument("-S", "--search"   , help="finds and extract only a certain .img files.", metavar='<kword>')
parser.add_argument("-O", "--output"   , help="name or path of directory, where will place output files", metavar='<dir>')
tspm  .add_argument("-F", "--fblock"   , help="change fastboot status flag (not recomend)", metavar='{0:1}')
tspm  .add_argument("-K", "--key"      , help="rewrite OEM password key in device NVE", metavar='<16-chr>')
parser.add_argument(      "input"      , help="name or path of input file (UPDATE.APP for example)", metavar='<filename>')

def app_extract(app_path:str, crc_check = False, filter = '', out_dir = ''):

    from .appextractor import ImageExtractor

    hwu = ImageExtractor(crc_check, filter)
    hwu.extract(app_path, out_dir)

def fastboot_mode(key = '', fblock = ''):

    from .fastboot import Fastboot

    fb = Fastboot()

    if fb.connect():
        if key or fblock:
            fb.usrlock( key, fblock )
        else:
            fb.command()

def flash_bootloader(manifest_path: str, sha1_test = False, hisi_xxxx = ''):

    from .bootloaders  import Bootloaders
    from .imageflasher import ImageFlasher

    bl = Bootloaders.load(manifest_path)
    el = None

    print("(  If you don't know which one is yours, check here:")
    print(f"   \033[0;33m{g_tree}\033[0m  )", end='\n\n')
    print("List of avilable bootloaders:", end='\n\n')
    if not hisi_xxxx:
        cnt = 0
        for it in bl.items():
            cnt += 1
            pad = ' ' * (14 - len(it['name']))
            print('  \033[2m[\033[0m%d\033[2m]\033[0m \033[1m%s\033[2m~ %s\033[0m'% (cnt, it['name']+pad, it['path']))
        i = int( input("Type the bootloader number: ") )

        if i < 1 or i > cnt:
            print("\033[0;31mNumber is out of range\033[0m")
            exit(1)
        else:
            el = bl.items()[i-1]
    elif not (el := bl.find(hisi_xxxx)):
        print(f"'{hisi_xxxx}' is not found!")
        exit(1)

    imgs = bl.extract_images(el)

    if sha1_test:
        ImageFlasher.test_hash( el, imgs )
    elif g_warn:
        print(f"\033[1;33m{g_warn}\033[0m")
    else:
        ImageFlasher.boot_flash( el, imgs )
        if input("Connecting to fastboot? (y/n) ") in 'yY':
            fastboot_mode(args.key, args.fblock)

def gui_window(ui_xml: str):

    from .main import MainWindow

    sys.exit( MainWindow.create(ui_xml) )

if __name__ == '__main__':

    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"\n file '{args.input}' - is not exist!", end='\n\n')
    elif 'b' == args.command[0]: # bootloader
        flash_bootloader(args.input, args.test_hash, args.search)
    elif 'f' == args.command[0]: # fastboot
        fastboot_mode(args.key, args.fblock)
    elif 'e' == args.command[0]: # extract
        app_extract(args.input, args.test_hash, args.search, args.output)
    elif 'g' == args.command[0]: # gui
        gui_window(args.input)
