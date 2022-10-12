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
import subprocess
import sys

options = None

KiB = 1024
MiB = KiB * 1024
GiB = MiB * 1024
TiB = GiB * 1024


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
    Execute a vos query command and return the stdout as a list of strings.
    """
    args = ['vos', command, '-noauth']
    for name, value in kwargs.items():
        if value is True:
            args.append('-%s' % name)
        else:
            args.extend(['-%s' % name, value])
    if options and options.cell:
        args.extend(['-cell', options.cell])
    if options and options.noresolve:
        args.append('-noresolve')
    proc = subprocess.Popen(args,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    output = proc.communicate()[0].decode('utf-8')
    error = proc.communicate()[1].decode('utf-8')
    if error:
        sys.stderr.write('ERROR: {0}'.format(error))
    return output.splitlines()

def find_servers():
    output = vos('listaddrs', printuuid=True)
    pp(output)

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
        usedp = (used / total) * 100.0
    else:
        usedp = 100.0
    if usedp < 0.1:
        usedp = 0.0
    if usedp > 100.0:
        usedp = 100.0
    return (used, usedp)


def afsfree():
    """
    Get the free, used, and total space on each partition on each server
    in the given cell.
    """
    table = []
    for server in sorted(set(vos('listaddrs'))):
        for partition in vos('partinfo', server=server):
            m = re.match(r'Free space on partition /vicep([a-z]+): '
                         r'(\d+) K blocks out of total (\d+)', partition)
            if m:
                partid = m.group(1)
                free = int(m.group(2))
                total = int(m.group(3))
                used, usedp = calculate_used(free, total)
                row = (server, partid, total, used, free, usedp)
                table.append(row)
    return table


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


def print_text(table):
    """
    Output the results as text table, one line per server/partition pair.
    """
    text_table = [('host', 'part', 'size', 'used', 'free', 'used%')]
    for row in table:
        server, part, size, used, free, usedp = row
        text_table.append((server, part, humanize(size), humanize(used),
                          humanize(free), '{:.0f}%'.format(usedp)))
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
    for row in table:
        print(' '.join([str(x) for x in row]))


def main():
    global options
    parser = argparse.ArgumentParser(
        description='Show free and used space on OpenAFS file servers.')
    parser.add_argument('--cell', '-cell')
    parser.add_argument('--noresolve', '-noresolve', action='store_true')
    parser.add_argument('--format', '-format', choices=['text', 'json', 'raw'],
                        default='text')
    options = parser.parse_args()

    find_servers()
    return 0

    table = afsfree()
    if options.format == 'text':
        print_text(table)
    elif options.format == 'json':
        print_json(table)
    elif options.format == 'raw':
        print_raw(table)
    else:
        raise AssertionError(
            'Invalid format option: {}'.format(options.format))


if __name__ == '__main__':
    main()
