Send To Kindle
==============

A utility to send documents to your Kindle via the Internet.

Currently only works on Ubuntu, because it uses an app indicator.
Patches to supported other distributions are welcome.

.. image:: http://elsdoerfer.name/media/images/sendtokindle/merged.png

See http://elsdoerfer.com/sendtokindle for more screenshots.


Installation
============

You currently must install via ``pip`` (``easy_install`` does not place the
data files in the correct place):

     $ sudo easy_install pip
     $ sudo pip install sendtokindle

It will add itself to the Gnome Main Menu, as well as the "Open With"
menu of supported file types.


Credits
=======

Incorporates code from https://github.com/kparal/sendKindle, which is
a command line tool that does the same thing.
