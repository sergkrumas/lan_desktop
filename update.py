








import os
import time
import urllib.request
import zipfile
import shutil
import builtins


def clear_current_folder(print):
    print(f'cleaning current folder ... ')
    current_dir = os.path.dirname(__file__)
    for filename in os.listdir(current_dir):
        file_path = os.path.join(current_dir, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                if not (file_path.endswith('.git') or file_path.startswith('peers_list')):
                    shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')

def download(zip_FILENAME, print):
    zip_URL = "https://github.com/sergkrumas/lan_desktop/archive/refs/heads/master.zip"
    print(f'downloading .zip from {zip_URL}')

    urllib.request.urlretrieve(zip_URL, zip_FILENAME)
    zf = zipfile.ZipFile(zip_FILENAME)
    zf.extractall()
    zf.close()

    start_time = time.time()
    while time.time() - start_time < 4:
        try:
            os.remove(zip_FILENAME)
            print(f'{zip_FILENAME} removed')
            break
        except:
            print('next try...')
        time.sleep(1)

def moving_files(zip_FILENAME, print):
    # moving files from lan_desktop-master to current folder
    current_dir = os.path.dirname(__file__)
    updated_folder = os.path.join(current_dir, 'lan_desktop-master')

    for cur_walk_dir, dirs, filenames in os.walk(updated_folder):
        rel_path = os.path.relpath(cur_walk_dir, start=updated_folder)

        for filename in filenames:
            src_path = os.path.join(cur_walk_dir, filename)
            dst_path = os.path.abspath(os.path.join(current_dir, rel_path, filename))

            # создаём папки, если их нет
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)

            shutil.move(src_path, dst_path)

    print(f'removing {zip_FILENAME}... ')
    shutil.rmtree(updated_folder)

def do_update(print_func):

    if print_func is None:
        print_func = builtins.print

    zip_FILENAME = "update.zip"

    if 'lan_desktop.py' in os.listdir('.'):
        clear_current_folder(print_func)
        download(zip_FILENAME, print_func)
        moving_files(zip_FILENAME, print_func)

        print_func('DONE!')
    else:
        print_func('no lan_desktop.py file found! Abort!')

    if print_func is builtins.print:
        input('\tPress any key to exit...')
