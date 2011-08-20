#!/usr/bin/env python
# coding: utf8
from distutils.core import setup
from glob import glob
import os
import shutil


# So we can deploy the file with file extension.
# Kind of a hack, setuptools would make this a lot
# easier. Or we could install sendtokindle.py to
# site-packages, and have a script wrapper.
here = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(here, 'sendtokindle.py')):
    shutil.copyfile(os.path.join(here, 'sendtokindle.py'), 
                    os.path.join(here, 'data/sendtokindle'))

# Figure out the version.
import re
here = os.path.dirname(os.path.abspath(__file__))
fp = open(os.path.join(here, 'data', 'sendtokindle'))
match = re.search(r'__version__ = (\(.*?\))', fp.read())
if match:
    version = eval(match.group(1))
else:
    raise Exception("Cannot find version in __init__.py")
fp.close()


data_files = [
    ('share/icons/hicolor/256x256/apps', ['data/icons/hicolor/sendtokindle.png']),
    ('share/icons/hicolor/16x16/apps', ['data/icons/hicolor/sendtokindle-pay.png']),
    # XXX: These themes don't define 64x64 icons - why does it work anyway?
    ("share/icons/ubuntu-mono-dark/apps/64", glob("data/icons/ubuntu-mono-dark/*")),
    ("share/icons/ubuntu-mono-light/apps/64", glob("data/icons/ubuntu-mono-light/*")),
    ('share/applications', ['data/sendtokindle.desktop']),
    ('share/sendtokindle/gui', glob("data/gui/*")),
]

setup(
    name="sendtokindle",
    version=".".join(map(str, version)),
    author="Michael Eldsdörfer",
    author_email="michale@elsdoerfer.com",
    url="https://elsdoerfer.com/sendtokindle",
    license="AGPL",
    description="Utility to send documents to your Kindle",
    data_files=data_files,
    scripts=["data/sendtokindle"],
)
