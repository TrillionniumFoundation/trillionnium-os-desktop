"""Preserve the empty refs container required by a self-contained Git checkout.

File-only transfer lists contain no empty directories. Git still requires its
refs directory even when HEAD is detached and every retained ref is packed.
No ref, object, index, configuration, worktree file, or hook is written here.
"""
import os
from pathlib import Path
import stat


def ensure_refs_container(checkout, owner_uid):
    if type(owner_uid) is not int or owner_uid < 0:
        raise ValueError('strict owner UID required')
    checkout = Path(checkout)
    if checkout.is_symlink() or not checkout.is_dir():
        raise ValueError('real checkout directory required')
    git = checkout / '.git'
    fd = os.open(git, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if before.st_uid != owner_uid:
            raise ValueError('Git directory owner differs')
        for name, directory in (('HEAD', False), ('objects', True), ('config', False)):
            meta = os.stat(name, dir_fd=fd, follow_symlinks=False)
            wanted = stat.S_ISDIR(meta.st_mode) if directory else stat.S_ISREG(meta.st_mode)
            if not wanted or meta.st_uid != owner_uid:
                raise ValueError('existing self-contained Git metadata differs: ' + name)
        created = False
        try:
            os.mkdir('refs', mode=0o755, dir_fd=fd)
            created = True
        except FileExistsError:
            pass
        child = os.open('refs', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
        try:
            actual = os.fstat(child)
            if actual.st_uid != owner_uid:
                raise ValueError('refs container owner differs')
            if created and os.listdir(child):
                raise ValueError('new refs container must be empty')
            os.fsync(child)
        finally:
            os.close(child)
        after = git.lstat()
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise ValueError('Git directory changed during metadata preparation')
        os.fsync(fd)
        return {'checkout': str(checkout), 'refs': str(git / 'refs'), 'created_empty_refs_directory': created,
                'git_device': before.st_dev, 'git_inode': before.st_ino,
                'refs_device': actual.st_dev, 'refs_inode': actual.st_ino,
                'regular_files_written': 0, 'refs_written': 0, 'objects_written': 0, 'worktree_mutations': 0}
    finally:
        os.close(fd)
