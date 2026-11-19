"""Local training admission estimates; not a guarantee against runtime exhaustion."""
import json
import os
import platform
import re
import shutil
import subprocess

MIB = 1024 * 1024


class ResourceUnavailable(ValueError):
    pass


def memory_from_vm_stat(output):
    page_size = re.search(r'page size of (\d+) bytes', output)
    counts = [re.search(r'^' + re.escape(name) + r':\s+(\d+)\.', output, re.MULTILINE)
              for name in ('Pages free', 'Pages inactive', 'Pages speculative')]
    if page_size is None or any(count is None for count in counts):
        raise ValueError('Unrecognized memory statistics.')
    return int(page_size[1]) * sum(int(count[1]) for count in counts)


def available_memory():
    if platform.system() == 'Darwin':
        return memory_from_vm_stat(subprocess.check_output(['/usr/bin/vm_stat'], text=True, timeout=3))
    return os.sysconf('SC_AVPHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')


def check(rows, directory):
    """Require a minimum reserve scaled to the prepared dataset's encoded size."""
    dataset_bytes = len(json.dumps(rows, ensure_ascii=False).encode('utf-8'))
    return check_size(dataset_bytes, directory)


def check_size(dataset_bytes, directory):
    """Check reserves for a validated conservative encoded-data budget."""
    if type(dataset_bytes) is not int or dataset_bytes < 0:
        raise ValueError('A nonnegative integer data budget is required.')
    try:
        available = available_memory()
        existing = directory
        while not existing.exists() and existing != existing.parent:
            existing = existing.parent
        free_disk = shutil.disk_usage(existing).free
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError) as error:
        raise ResourceUnavailable('Could not check local training resources. Retry after checking system memory and disk space.') from error
    required_memory = 256 * MIB + dataset_bytes * 8
    required_disk = 64 * MIB + dataset_bytes * 4
    if available < required_memory:
        raise ResourceUnavailable(f'Not enough available memory for training: {available // MIB} MiB available; estimated reserve {required_memory // MIB} MiB. Close other apps and approve training again.')
    if free_disk < required_disk:
        raise ResourceUnavailable(f'Not enough free disk space for training: {free_disk // MIB} MiB available; estimated reserve {required_disk // MIB} MiB. Free space and approve training again.')
    return {'available_memory_bytes': available, 'free_disk_bytes': free_disk,
            'estimated_memory_reserve_bytes': required_memory, 'estimated_disk_reserve_bytes': required_disk}
