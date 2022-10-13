#!/usr/bin/env python3

from pprint import pprint
from clang.cindex import CursorKind, Index, CompilationDatabase
from collections import defaultdict
import sys
import json
import os
from termcolor import colored

CALLGRAPH = defaultdict(list)
FULLNAMES = defaultdict(set)
DISPLAYED=[]


def get_diag_info(diag):
    return {
        'severity': diag.severity,
        'location': diag.location,
        'spelling': diag.spelling,
        'ranges': list(diag.ranges),
        'fixits': list(diag.fixits)
    }


def fully_qualified(c):
    if c is None:
        return ''
    elif c.kind == CursorKind.TRANSLATION_UNIT:
        return ''
    else:
        res = fully_qualified(c.semantic_parent)
        if res != '':
            return res + '::' + c.spelling
        return c.spelling


def fully_qualified_pretty(c):
    if c is None:
        return ''
    elif c.kind == CursorKind.TRANSLATION_UNIT:
        return ''
    else:
        res = fully_qualified(c.semantic_parent)
        if res != '':
            return res + '::' + c.displayname
        return c.displayname


def is_excluded(node, xfiles, xprefs):
    if not node.extent.start.file:
        return False

    for xf in xfiles:
        if node.extent.start.file.name.startswith(xf):
            return True

    fqp = fully_qualified_pretty(node)

    for xp in xprefs:
        if fqp.startswith(xp):
            return True

    return False


def show_info(node, xfiles, xprefs, cur_fun=None):
    if node.kind == CursorKind.FUNCTION_TEMPLATE:
        if not is_excluded(node, xfiles, xprefs):
            cur_fun = node
            FULLNAMES[fully_qualified(cur_fun)].add(
                fully_qualified_pretty(cur_fun))

    if node.kind == CursorKind.CXX_METHOD or \
            node.kind == CursorKind.FUNCTION_DECL or node.kind == CursorKind.CONSTRUCTOR:
        if not is_excluded(node, xfiles, xprefs):
            cur_fun = node
            FULLNAMES[fully_qualified(cur_fun)].add(
                fully_qualified_pretty(cur_fun))

    if node.kind == CursorKind.CALL_EXPR or node.kind == CursorKind.CONSTRUCTOR or node.kind == CursorKind.DESTRUCTOR:
        if node.referenced and not is_excluded(node.referenced, xfiles, xprefs):
            CALLGRAPH[fully_qualified_pretty(cur_fun)].append(node.referenced)

    for c in node.get_children():
        show_info(c, xfiles, xprefs, cur_fun)


def get_annotations(node):
    return [c.displayname for c in node.get_children()
            if c.kind == CursorKind.ANNOTATE_ATTR]

def pretty_print(n):
    v = ''
    if n.is_virtual_method():
        v = ' virtual'
    if n.is_pure_virtual_method():
        v = ' = 0'
    return fully_qualified_pretty(n) + v + ' ' + ' '.join(get_annotations(n))


def print_calls(fun_name, so_far, depth=0, edit=False, attributes=[]):
    if fun_name in CALLGRAPH:
        for f in CALLGRAPH[fun_name]:
            name = pretty_print(f)
            if name not in DISPLAYED and f.kind is not CursorKind.CONSTRUCTOR and not f.is_pure_virtual_method():
                DISPLAYED.append(name)
                printed = False
                for a in attributes:
                    if a in name:
                        print(colored('  ' * (depth + 1) + name, 'green') + ' ' + str(f.location.file) + ':' + str(f.location.line))
                        printed = True
                        break
                if not printed:
                    print('  ' * (depth + 1) + name + ' ' + str(f.location.file) + ':' + str(f.location.line))
                    if edit:
                        e = os.system(f"vim +{f.location.line} {f.location.file}")
                        if e:
                            edit=False
            if f in so_far:
                continue
            so_far.append(f)
            if fully_qualified_pretty(f) in CALLGRAPH:
                print_calls(fully_qualified_pretty(f), so_far, depth + 1, edit, attributes)
            else:
                print_calls(fully_qualified(f), so_far, depth + 1, edit, attributes)


def read_compile_commands(filename):
    if filename.endswith('.json'):
        with open(filename) as compdb:
            return json.load(compdb)
    else:
        return [{'command': '', 'file': filename}]


def read_args(args):
    db = None
    clang_args = []
    excluded_prefixes = []
    excluded_paths = ['/usr']
    search_attributes = []
    edit = False
    i = 0
    while i < len(args):
        if args[i] == '-x':
            i += 1
            excluded_prefixes = args[i].split(',')
        elif args[i] == '-p':
            i += 1
            excluded_paths = args[i].split(',')
        elif args[i] == '--edit':
            edit = True
        elif args[i] == '--attribute':
            i += 1
            search_attributes = args[i].split(',')
        elif args[i][0] == '-':
            clang_args.append(args[i])
        else:
            db = args[i]
        i += 1
    return {
        'db': db,
        'clang_args': clang_args,
        'excluded_prefixes': excluded_prefixes,
        'excluded_paths': excluded_paths,
        'edit': edit,
        'search_attributes': search_attributes
    }


def main():
    if len(sys.argv) < 2:
        print('usage: ' + sys.argv[0] + ' file.cpp|compile_database.json '
              '[extra clang args...]')
        return

    cfg = read_args(sys.argv)

    print('reading source files...')
    files_read = []
    for cmd in read_compile_commands(cfg['db']):
        index = Index.create()
        c = cfg['clang_args']
        tu = index.parse(cmd['file'], c)
        if cmd['file'] not in files_read:
            files_read.append(cmd['file'])
        else:
            continue
        print(cmd['file'])
        if not tu:
            parser.error("unable to load input")

        for d in tu.diagnostics:
            if d.severity == d.Error or d.severity == d.Fatal:
                print(' '.join(c))
                pprint(('diags', list(map(get_diag_info, tu.diagnostics))))
                return
        show_info(tu.cursor, cfg['excluded_paths'], cfg['excluded_prefixes'])

    while True:
        global DISPLAYED
        DISPLAYED = []
        fun = input('> ')
        if not fun:
            break
        if fun in CALLGRAPH:
            print(fun)
            print_calls(fun, list(), edit=cfg['edit'], attributes=cfg['search_attributes'])
        else:
            print('matching:')
            for f, ff in FULLNAMES.items():
                if f.startswith(fun):
                    for fff in ff:
                        print(fff)


if __name__ == '__main__':
    main()
