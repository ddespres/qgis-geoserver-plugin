# -*- coding: utf-8 -*-
#
# (c) 2016 Boundless, http://boundlessgeo.com
# This code is licensed under the GPL 2.0 license.
#
import os
import xmlrpclib
import zipfile
import requests
import StringIO
import shutil

from paver.easy import *
from paver.doctools import html

import json
from collections import defaultdict

options(
    plugin = Bunch(
        name = 'geoserverexplorer',
        ext_libs = path('geoserverexplorer/extlibs'),
        ext_src = path('geoserverexplorer/ext-src'),
        source_dir = path('geoserverexplorer'),
        package_dir = path('.'),
        tests = ['test'],
        excludes = [
            '.DS_Store',  # on Mac
            'test-output',
            'ext-src',
            'coverage*',
            'nose*',
            '*.pyc',
            'gisdata'
        ],
        # skip certain files inadvertently found by exclude pattern globbing
        skip_exclude = ['coverage.xsd']
    ),

    sphinx = Bunch(
        docroot = path('docs'),
        sourcedir = path('docs/source'),
        builddir = path('docs/build')
    )
)


@task
@cmdopts([
    ('clean', 'c', 'Clean out dependencies first'),
    ('develop', 'd', 'Do not alter source dependency git checkouts'),
])
def setup(options):
    """Install run-time dependencies"""
    clean = getattr(options, 'clean', False)
    develop = getattr(options, 'develop', False)
    ext_libs = options.plugin.ext_libs
    ext_src = options.plugin.ext_src
    if clean:
        ext_libs.rmtree()
    ext_libs.makedirs()
    runtime, test = read_requirements()
    os.environ['PYTHONPATH']=ext_libs.abspath()
    for req in runtime + test:
        if '#egg' in req:
            urlspec, req = req.split('#egg=')
            localpath = ext_src / req
            if not develop:
                if localpath.exists():
                    cwd = os.getcwd()
                    os.chdir(localpath)
                    print(localpath)
                    sh('git pull')
                    os.chdir(cwd)
                else:
                    sh('git clone  %s %s' % (urlspec, localpath))
            req = localpath

        sh('easy_install -a -d %(ext_libs)s %(dep)s' % {
            'ext_libs' : ext_libs.abspath(),
            'dep' : req
        })
    get_certs()

def get_certs():
    print "Downloading and installing test certificates..."
    certsPath = os.path.abspath("./_certs")
    if os.path.exists(certsPath):
        shutil.rmtree(certsPath)
    r = requests.get("https://github.com/boundlessgeo/boundless-test-certs/archive/master.zip", stream=True)
    z = zipfile.ZipFile(StringIO.StringIO(r.content))
    z.extractall(path=certsPath)
    dstPath = "./geoserverexplorer/test/resources/auth_system/certs-keys"
    if os.path.exists(dstPath):
        shutil.rmtree(dstPath)
    shutil.copytree(os.path.join(certsPath, "boundless-test-certs-master", "certs-keys"), dstPath)
    shutil.rmtree(certsPath)


def read_requirements():
    """Return a list of runtime and list of test requirements"""
    lines = path('requirements.txt').lines()
    lines = [ l for l in [ l.strip() for l in lines] if l ]
    divider = '# test requirements'

    try:
        idx = lines.index(divider)
    except ValueError:
        raise BuildFailure(
            'Expected to find "%s" in requirements.txt' % divider)

    not_comments = lambda s,e: [ l for l in lines[s:e] if l[0] != '#']
    return not_comments(0, idx), not_comments(idx+1, None)


def _install(folder, options):
    '''install plugin to qgis'''
    builddocs(options)
    plugin_name = options.plugin.name
    src = path(__file__).dirname() / plugin_name
    dst = path('~').expanduser() / folder / 'python' / 'plugins' / plugin_name
    src = src.abspath()
    dst = dst.abspath()
    if not hasattr(os, 'symlink'):
        dst.rmtree()
        src.copytree(dst)
    elif not dst.exists():
        src.symlink(dst)
    # Symlink the build folder to the parent
    docs = path('..') / '..' / "docs" / 'build' / 'html'
    docs_dest = path(__file__).dirname() / plugin_name / "docs"
    docs_link = docs_dest / 'html'
    if not docs_dest.exists():
        docs_dest.mkdir()
    if not docs_link.islink():
        docs.symlink(docs_link)

@task
def install(options):
    _install(".qgis2", options)

@task
def installdev(options):
    _install(".qgis-dev", options)

@task
def install3(options):
    _install(".qgis3", options)

@task
@cmdopts([
    ('tests', 't', 'Package tests with plugin'),
])
def package(options):
    """Create plugin package"""
    builddocs(options)
    package_file = options.plugin.package_dir / ('%s.zip' % options.plugin.name)
    with zipfile.ZipFile(package_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        if not hasattr(options.package, 'tests'):
            options.plugin.excludes.extend(options.plugin.tests)
        _make_zip(zf, options)
    return package_file


@task
def install_devtools():
    """Install development tools"""
    try:
        import pip
    except:
        error('FATAL: Unable to import pip, please install it first!')
        sys.exit(1)

    pip.main(['install', '-r', 'requirements-dev.txt'])


@task
@consume_args
def pep8(args):
    """Check code for PEP8 violations"""
    try:
        import pep8
    except:
        error('pep8 not found! Run "paver install_devtools".')
        sys.exit(1)

    # Errors to ignore
    ignore = ['E203', 'E121', 'E122', 'E123', 'E124', 'E125', 'E126', 'E127',
        'E128', 'E402']
    styleguide = pep8.StyleGuide(ignore=ignore,
                                 exclude=['*/extlibs/*', '*/ext-src/*'],
                                 repeat=True, max_line_length=79,
                                 parse_argv=args)
    styleguide.input_dir(options.plugin.source_dir)
    info('===== PEP8 SUMMARY =====')
    styleguide.options.report.print_statistics()


@task
@consume_args
def autopep8(args):
    """Format code according to PEP8
    """
    try:
        import autopep8
    except:
        error('autopep8 not found! Run "paver install_devtools".')
        sys.exit(1)

    if any(x not in args for x in ['-i', '--in-place']):
        args.append('-i')

    args.append('--ignore=E261,E265,E402,E501')
    args.insert(0, 'dummy')

    cmd_args = autopep8.parse_args(args)

    excludes = ('ext-lib', 'ext-src')
    for p in options.plugin.source_dir.walk():
        if any(exclude in p for exclude in excludes):
            continue

        if p.fnmatch('*.py'):
            autopep8.fix_file(p, options=cmd_args)


@task
@consume_args
def pylint(args):
    """Check code for errors and coding standard violations"""
    try:
        from pylint import lint
    except:
        error('pylint not found! Run "paver install_devtools".')
        sys.exit(1)

    if not 'rcfile' in args:
        args.append('--rcfile=pylintrc')

    args.append(options.plugin.source_dir)
    lint.Run(args)


def _make_zip(zipFile, options):
    excludes = set(options.plugin.excludes)
    skips = options.plugin.skip_exclude

    src_dir = options.plugin.source_dir
    exclude = lambda p: any([path(p).fnmatch(e) for e in excludes])
    def filter_excludes(root, items):
        if not items:
            return []
        # to prevent descending into dirs, modify the list in place
        for item in list(items):  # copy list or iteration values change
            itempath = path(os.path.relpath(root)) / item
            if exclude(item) and item not in skips:
                debug('Excluding %s' % itempath)
                items.remove(item)
        return items

    for root, dirs, files in os.walk(src_dir):
        for f in filter_excludes(root, files):
            relpath = os.path.relpath(root)
            zipFile.write(path(root) / f, path(relpath) / f)
        filter_excludes(root, dirs)

    for root, dirs, files in os.walk(options.sphinx.builddir):
        for f in files:
            relpath = os.path.join(options.plugin.name, "docs", os.path.relpath(root, options.sphinx.builddir))
            zipFile.write(path(root) / f, path(relpath) / f)

def create_settings_docs(options):
    settings_file = path(options.plugin.name) / "settings.json"
    doc_file = options.sphinx.sourcedir / "settingsconf.rst"
    with open(settings_file) as f:
        settings = json.load(f)

    grouped = defaultdict(list)
    for setting in settings:
        grouped[setting["group"]].append(setting)
    with open (doc_file, "w") as f:
        f.write("Plugin settings\n===============\n\n"
                "The plugin can be adjusted using the following settings, "
                "to be found in its settings dialog.\n")
        for groupName, group in grouped.iteritems():
            section_marks = "-" * len(groupName)
            f.write("\n%s\n%s\n\n"
                    ".. list-table::\n"
                    "   :header-rows: 1\n"
                    "   :stub-columns: 1\n"
                    "   :widths: 20 80\n"
                    "   :class: non-responsive\n\n"
                    "   * - Option\n"
                    "     - Description\n"
                    % (groupName, section_marks))
            for setting in group:
                f.write("   * - %s\n"
                        "     - %s\n"
                        % (setting["label"], setting["description"]))


@task
@cmdopts([
    ('clean', 'c', 'clean out built artifacts first'),
])
def builddocs(options):
    clean = getattr(options, 'clean', False)
    try: #this might fail if the plugin code is not in a git repo
        sh("git submodule init")
        sh("git submodule update")
    except:
        pass
    create_settings_docs(options)
    cwd = os.getcwd()
    os.chdir(options.sphinx.docroot)
    if clean:
        sh("make clean")
    sh("make html")
    os.chdir(cwd)
