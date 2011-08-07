#!/usr/bin/env python
# coding: utf8
from distutils.core import setup
from glob import glob
import shutil

shutil.copyfile('sendtokindle.py', 'data/sendtokindle')

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
    author="Michael Eldsdörfer",
    author_email="michale@elsdoerfer.com",
    url="https://elsdoerfer.com/sendtokindle",
    license="AGPL",
    description="Utility to send documents to your Kindle",
    data_files=data_files,
    scripts=["data/sendtokindle"],
)
