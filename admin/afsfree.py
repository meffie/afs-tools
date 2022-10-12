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


def vos(command, server=None):
    """
    Execute a vos query command and return the stdout as a list of strings.
    """
    args = ['vos', command, '-noauth']
    if server:
        args.extend(['-server', server])
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
    for server in sorted(vos('listaddrs')):
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


def column_widths(table):
    """
    Calculate the column widths needed for virtical alignment.
    """
    min_width = 4
    widths = []
    for column in zip(*table):
        widths.append(max([len(x) for x in column] + [min_width]))
    return widths


def make_template(output):
    """
    Generate the format template.
    """
    t = []
    for i, w in enumerate(column_widths(output)):
        align = '<' if i == 0 else '>'
        t.append('{%d:%c%d}' % (i, align, w))
    return '  '.join(t)


def print_text(table):
    """
    Format the results as readable text table.
    """
    output = [('host', 'part', 'size', 'used', 'free', 'used%')]
    for r in table:
        usedp_str = '{:.0f}%'.format(r[5])
        output.append((r[0], r[1], humanize(r[2]), humanize(r[3]),
                      humanize(r[4]), usedp_str))
    template = make_template(output)
    for row in output:
        print(template.format(*row))


def print_json(table):
    print(json.dumps(table))


def print_raw(table):
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