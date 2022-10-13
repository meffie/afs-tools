#!/usr/bin/env python3
#
# Copyright (c) 2016-2022, Sine Nomine Associates
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
#

"""
Report free and used space on OpenAFS file servers.
"""

from pprint import pprint as pp

import argparse
import json
import re
import socket
import subprocess
import sys


KiB = 1024
MiB = KiB * 1024
GiB = MiB * 1024
TiB = GiB * 1024

HEADINGS = ('host', 'part', 'size', 'used', 'free', 'used%')

def humanize(kbytes):
    """
    Convert KiB bytes to more human readable units.
    """
    if kbytes >= TiB:
        value = kbytes / TiB
        unit = 'P'
    elif kbytes >= GiB:
        value = kbytes / GiB
        unit = 'T'
    elif kbytes >= MiB:
        value = kbytes / MiB
        unit = 'G'
    elif kbytes >= KiB:
        value = kbytes / KiB
        unit = 'M'
    else:
        value = float(kbytes)
        unit = 'K'
    return '{:.0f}{}'.format(value, unit)


def vos(command, **kwargs):
    """
    Execute a vos command and return the stdout as a list of strings.
    """
    args = ['vos', command]
    for name, value in kwargs.items():
        if value is None:
            pass
        elif value is True:
            args.append('-%s' % name)
        else:
            args.extend(['-%s' % name, value])
    sys.stdout.write('DEBUG: Running {0}\n'.format(' '.join(args)))
    proc = subprocess.Popen(args,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    output = proc.communicate()[0].decode('utf-8')
    error = proc.communicate()[1].decode('utf-8')
    for line in error.splitlines():
        if 'running unauthenticated' not in line:
            sys.stderr.write('ERROR: {0}\n'.format(line))
    return output.splitlines()


def lookup_servers(cell=None):
    """
    Lookup the file servers for this cell.
    """
    file_servers = {}
    uuid = None
    listaddrs = vos('listaddrs', cell=cell, printuuid=True, noresolve=True)
    for i, line in enumerate(listaddrs):
        if not line:
            uuid = None
        elif line.startswith('UUID:'):
            uuid = line.replace('UUID:', '', 1).strip()
            if uuid not in file_servers:
                file_servers[uuid] = []
        else:
            if not uuid:
                raise ValueError('Unexpected vos listaddrs output on line '
                                 '{1}: {2}', i, line)
            file_servers[uuid].append(line)

    addrs = set()
    for a in file_servers.values():
        if a:
            addrs.add(a[0])   # try just this one?

    return list(addrs)


def calculate_used(free, total):
    """
    Calculate the used space and the used percent from the
    available and the total space.
    """
    if total > free:
        used = total - free
    else:
        used = total
    if total > 0:
        usedp = round((used / total) * 100.0, 1)
    else:
        usedp = 100.0
    if usedp < 0.1:
        usedp = 0.0
    if usedp > 100.0:
        usedp = 100.0
    return (used, usedp)


def lookup_hostname(address):
    """
    Resolve the hostname from the IP address.
    """
    try:
        hostname, _, _ = socket.gethostbyaddr(address)
    except Exception as e:
        sys.stderr.write('WARNING: failed to resolve '
                         '{0}: {1}\n'.format(address), e)
        hostname = address
    return hostname


def lookup_address(hostname):
    try:
        address = socket.gethostbyname(hostname)
    except Exception as e:
        sys.stderr.write('WARNING: failed to resolve '
                         '{0}: {1}\n'.format(hostname), e)
        address = hostname
    return address


def get_partinfo(cell, server):
    parts = {}
    output = vos('partinfo', cell=cell, server=server)
    for partition in output:
        m = re.match(r'Free space on partition /vicep([a-z]+): '
                     r'(\d+) K blocks out of total (\d+)', partition)
        if m:
            partid = m.group(1)
            free = int(m.group(2))
            total = int(m.group(3))
            used, usedp = calculate_used(free, total)
            parts[partid] = dict(total=total, used=used, free=free, usedp=usedp)
    return parts


def afsfree(cell, servers):
    """
    Get the free, used, and total space on each partition on each server
    in the given cell.
    """
    results = {}
    if not servers:
        servers = lookup_servers(cell)
    for server in servers:
        results[server] = get_partinfo(cell, server)
    return results


def make_template(text_table):
    """
    Generate the format template for text output lines.

    Find the column format width for each table column. Left align the first
    column and right align the rest of the columns.  The columns will be
    vertically aligned when the output is printed with a monospaced font.
    """
    spacer = '   '
    column_formats = []
    for i, column in enumerate(zip(*text_table)):
        align = '<' if i == 0 else '>'
        width = max([len(s) for s in column])
        column_format = '{%d:%c%d}' % (i, align, width)
        column_formats.append(column_format)
    return spacer.join(column_formats)

def flatten(tree):
    table = []
    for key0, values0 in tree.items():
        for key1, values1 in values0.items():
            table.amend(dict(host=key0, part=key1, **values1))
    return table

def print_text(table, sort):
    """
    Output the results as text table, one line per server/partition pair.
    """
    #text_table = [HEADINGS]
    text_table = []
    for row in table:
        site, size, used, free, usedp = row
        server, part = site
        text_table.append((server, part, humanize(size), humanize(used),
                          humanize(free), '{:.0f}%'.format(usedp)))

    pp(text_table)
    if sort:
        print(sort)
        return

    template = make_template(text_table)
    for row in text_table:
        print(template.format(*row))


def print_json(table):
    """
    Output the results as json.
    """
    print(json.dumps(table))


def print_raw(table):
    """
    Output unformatted text, one line per server/partition pair.
    """
    for hostname, info in table.items():
        for partid, part in info['parts'].items():
            values = [hostname, info['ip'], partid] + part.values()
            print(' '.join([str(x) for x in values]))


def main():
    parser = argparse.ArgumentParser(
        description='Show free and used space on OpenAFS file servers.')
    parser.add_argument('--servers', '-servers', nargs='*',
                        default=None)
    parser.add_argument('--cell', '-cell')
    parser.add_argument('--format', '-format', choices=['text', 'json', 'raw'],
                        default='text')
    parser.add_argument('--sort', '-sort', choices=[HEADINGS],
                        default=HEADINGS[0])

    options = parser.parse_args()

    results = afsfree(options.cell, options.servers)
    pp(results)
    return 0

    if options.format == 'text':
        print_text(results, options.sort)
    elif options.format == 'json':
        print_json(results)
    elif options.format == 'raw':
        print_raw(results)
    else:
        raise AssertionError(
            'Invalid format option: {}'.format(options.format))


if __name__ == '__main__':
    main()
