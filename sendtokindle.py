#!/usr/bin/env python
# coding: utf8
"""
Graphical Send to Kindle Utility.

Created 2011 by Michael Elsdörfer <michael@elsdoerfer.com>.

Licensed under GNU AGPL 3.
"""

import os
import re
import sys
from os import path
from StringIO import StringIO
import json
from decimal import Decimal
from email import encoders
from email.generator import Generator
from email.mime.base import MIMEBase
from email.MIMEMultipart import MIMEMultipart
import smtplib
import threading

from gi.repository import Gtk, Gdk, Gio, GObject, AppIndicator, Notify


__version__ = ('0', '5', '2')


# TODO: This does't make much sense, since libindicator doesn't seem
# to respect it; so we really need to install our icons system-wide,
# even for development.
#p =  path.normpath(path.abspath(path.join(path.dirname(__file__), 'data', 'icons')))
#Gtk.IconTheme.get_default().prepend_search_path(p)


def sizeof_fmt(num):
    """Format number of bytes in human readable form.

    http://blogmag.net/blog/read/38/Print_human_readable_file_size
    """
    for x in ['bytes', 'KB', 'MB', 'GB', 'TB']:
        if num < 1024.0:
            return "%3.1f %s" % (num, x)
        num /= 1024.0
    return num


def get_layout_file_path(name):
    """Return path to layout file; check running from source,
    or globally installed scenarios.
    """
    script = path.abspath(sys.argv[0])
    if script.startswith('/usr/local'):
        filename= path.join('/usr', 'local', 'share', 'sendtokindle', 'gui', name)
    elif script.startswith('/usr'):
        filename= path.join('/usr', 'share', 'sendtokindle', 'gui', name)
    else:
        # assume running from dev
        filename = path.join(path.dirname(__file__), 'data', 'gui', name)

    if path.isfile(filename):
        return filename
    raise RuntimeError("Layout file not found: %s" % name)


class SendKindleException(StandardError):
    pass


class SendKindle(object):
    """Takes a SMTP configuration, can send files to the Amazon
    Kindle delivery service.

    Adapted from:
        https://github.com/kparal/sendKindle/blob/master/sendKindle.py
    """

    def __init__(self, settings):
        self.user_email = settings['user']['email']
        self.smtp_host = settings['smtp']['host']
        # smtplib breaks on unicode port string
        self.smtp_port = str(settings['smtp']['port']) or 25
        self.smtp_username = settings['smtp']['username']
        self.smtp_password = settings['smtp']['password']
        self.smtp_type = settings['smtp']['type']

    def send_mail(self, recipient, files, convert=True):
        """Send email with attachments"""

        # create MIME message
        msg = MIMEMultipart()
        msg['From'] = self.user_email
        msg['To'] = recipient
        msg['Subject'] = 'convert' if convert else ''

        # attach files
        for file_path in files:
            try:
                msg.attach(self.get_attachment(file_path))
            except IOError, e:
                print e
                raise SendKindleException(e)

        # convert MIME message to string
        fp = StringIO()
        gen = Generator(fp, mangle_from_=False)
        gen.flatten(msg)
        msg = fp.getvalue()

        # send email
        klass = smtplib.SMTP_SSL if self.smtp_type == 'tls' else smtplib.SMTP
        try:
            smtp = klass(host=self.smtp_host, port=self.smtp_port)
            if self.smtp_type == 'starttls':
                smtp.starttls()
            if self.smtp_username:
                smtp.login(self.smtp_username, self.smtp_password)
            smtp.sendmail(self.user_email, recipient, msg)
            smtp.close()
        except smtplib.SMTPException, e:
            print e
            raise SendKindleException(e)

    def get_attachment(self, file_path):
        """Get file as MIMEBase message"""

        # TODO Use GIO to support GVFS etc.
        file_ = open(file_path, 'rb')
        attachment = MIMEBase('application', 'octet-stream')
        attachment.set_payload(file_.read())
        file_.close()
        encoders.encode_base64(attachment)

        attachment.add_header('Content-Disposition', 'attachment',
                              filename=path.basename(file_path))
        return attachment


class SendThread(threading.Thread):
    """Wraps ``SendKindle`` in a thread so we don't block the UI.
    """

    def __init__(self, send_kindle_instance, *args, **kwargs):
        super(SendThread, self).__init__()
        self.send_kindle_instance = send_kindle_instance
        self.args = args
        self.kwargs = kwargs
        self.on_done = None

        # There's really not good way to abort a smptlib send operation,
        # as far as I know. Using a daemon thread allows us to abort
        # by shutting down the main thread.
        self.daemon = True

    def run(self):
        if os.environ.get('STK_SLEEP', False) == '1':
            # For debugging purposes.
            import time
            time.sleep(5)
        else:
            error = False
            try:
                self.send_kindle_instance.send_mail(*self.args, **self.kwargs)
            except SendKindleException, e:
                error = e

        if self.on_done:
            self.on_done(error)

    def stop(self):
        # Nothing we can do really.
        pass


class ConfigureWindow(object):
    """Encapsulates the configure window.
    """

    LAYOUT_FILE = get_layout_file_path('configure.ui')

    def __init__(self, application):
        self.application = application
        self._construct_ui()
        self.apply_settings(self.application.config['settings'])

    def _construct_ui(self):
        self.objects = objects = Gtk.Builder()
        objects.add_from_file(self.LAYOUT_FILE)

        self.window = self.objects.get_object('configure-window')

        self.save_button = objects.get_object('save-button')
        self.save_button.connect("clicked", self._save_button_clicked)
        self.cancel_button = objects.get_object('cancel-button')
        self.cancel_button.connect("clicked", self._cancel_button_clicked)

        # Get all the input fields
        for name in ('kindle-username-entry', 'sender-email-entry',
                     'us-checkbox', 'smtp-host-entry', 'smtp-port-entry',
                     'smtp-username-entry', 'smtp-password-entry',
                     'smtp-type-combobox'):
            widget = objects.get_object(name)
            setattr(self, name.replace('-', '_'), widget)
            if isinstance(widget, Gtk.Entry):
                widget.connect_after("changed", self._widget_changed)

        # Surely there is a less verbose way.
        self.smtp_type_choices = choices = Gtk.ListStore(str, str)
        choices.append(('', 'No encryption'))
        choices.append(('tls', 'TLS/SSL'))
        choices.append(('starttls', 'STARTLS'))
        self.smtp_type_combobox.set_model(choices)
        cell = Gtk.CellRendererText()
        self.smtp_type_combobox.pack_start(cell, True)
        self.smtp_type_combobox.add_attribute(cell, 'text', 1)

    def _save_button_clicked(self, widget):
        if not self.validate():
            return
        self.update_settings(self.application.config['settings'])
        self.application.notify_config_changed()
        self.application.save_config()
        self.window.destroy()

    def _cancel_button_clicked(self, widget):
        self.window.destroy()

    def _widget_changed(self, widget):
        """One of the many value widgets has changed.
        """
        self.validate(typing=True)

    def apply_settings(self, settings):
        """Initialize GUI from settings object.
        """
        self.kindle_username_entry.set_text(settings['user']['kindle-name'])
        self.sender_email_entry.set_text(settings['user']['email'])
        self.us_checkbox.set_active(settings['user']['in_us'])
        self.smtp_host_entry.set_text(settings['smtp']['host'])
        self.smtp_port_entry.set_text("%s" % settings['smtp']['port'])
        self.smtp_username_entry.set_text(settings['smtp']['username'])
        self.smtp_password_entry.set_text(settings['smtp']['password'])
        # Surely there is a less verbose way for this too
        self.smtp_type_combobox.set_active(0)
        for index, item in enumerate(self.smtp_type_choices):
            if item[0] == settings['smtp']['type']:
                self.smtp_type_combobox.set_active(index)
                break

    def update_settings(self, settings):
        """Write GUI values to the settings object.
        """
        settings['user']['kindle-name'] = self.kindle_username_entry.get_text()
        settings['user']['email'] = self.sender_email_entry.get_text()
        settings['user']['in-us'] = self.us_checkbox.get_active()
        settings['smtp']['host'] = self.smtp_host_entry.get_text()
        settings['smtp']['port'] = self.smtp_port_entry.get_text()
        settings['smtp']['username'] = self.smtp_username_entry.get_text()
        settings['smtp']['password'] = self.smtp_password_entry.get_text()
        settings['smtp']['type'] = \
            self.smtp_type_choices[self.smtp_type_combobox.get_active()][0]

    def validate(self, typing=False):
        """Validate the form.

        Mark erroneous input fields appropriately. If typing=False,
        be less aggressive: Empty fields are not marked.

        Return True/False.
        """
        errors = {}

        # Required fields - don't validate this on the fly
        if not typing:
            for name in ('kindle_username_entry', 'sender_email_entry',
                         'smtp_host_entry',):
                widget = getattr(self, name)
                if not widget.get_text():
                    errors[widget] = 'This is a required field.'
                else:
                    errors[widget] = False

        # Port must be numeric
        if not errors.get(self.smtp_port_entry):
            text = self.smtp_port_entry.get_text()
            if text and not text.isdigit():
                errors[self.smtp_port_entry] = 'This must be a numeric value.'
            else:
                errors[self.smtp_port_entry] = False

        # E-mail must match a format
        if not errors.get(self.sender_email_entry):
            text = self.sender_email_entry.get_text()
            # Don't validate email while typing (in a different
            # field potentially)
            if (text or not typing):
                if not re.match(r'[^@]+@.+\..+$', text):
                    errors[self.sender_email_entry] = \
                        'This must be a valid E-mail address.'
                else:
                    errors[self.sender_email_entry] = False

        # Update widget error messages
        for widget, msg in errors.items():
            if msg:
                widget.set_property('secondary-icon-name', 'gtk-dialog-warning')
                widget.set_property('secondary-icon-tooltip-text', msg)
                if not typing:
                    widget.grab_focus()
            else:
                widget.set_property('secondary-icon-name', None)
                widget.set_property('secondary-icon-tooltip-text', None)

        return not any(errors.values())

    def show(self):
        self.window.show_all()


class MainWindow(object):

    LAYOUT_FILE = get_layout_file_path('main.ui')

    def __init__(self, application):
        self.application = application
        self.application.connect('config-changed', self._config_changed)
        self._construct_ui()

    def _construct_ui(self):
        self.objects = objects = Gtk.Builder()
        objects.add_from_file(self.LAYOUT_FILE)

        # Set up various events
        self.window = window = objects.get_object('main-window')
        window.connect_after('destroy', self._window_destroy)

        self.send_button = objects.get_object('send-button')
        self.send_button.connect("clicked", self._send_button_clicked)

        self.configure_button = objects.get_object('configure-button')
        self.configure_button.connect("clicked", self._configure_button_clicked)

        self.free_radiobutton = objects.get_object('free-radiobutton')
        self.free_radiobutton.connect(
            "toggled", self._free_paid_radiobutton_toggled)
        self.paid_radiobutton = objects.get_object('paid-radiobutton')
        self.paid_radiobutton.connect(
            "toggled", self._free_paid_radiobutton_toggled)

        self.cost_label = self.objects.get_object('cost-label')

        # Create app indicator - this needs to be done before Gtk.main().
        self.indicator = Indicator(self)

    def _configure_button_clicked(self, widget):
        self.show_configure_window()

    def _send_button_clicked(self, widget):
        if not self.application.is_configured():
            # As long as were we are not yet configured, the send
            # button is the one used for open the config dialog.
            # It's label is also updated appropriately in ``update_ui``.
            self.show_configure_window()
            return

        self.window.hide()
        self.indicator.show()

        # Store the window current options in the settings, so
        # they'll be the default next time around.
        # Note: An alternative would be updating those whenever the
        # widget are changed, as opposed to only on send.
        do_convert = self.objects.get_object('convert-checkbox').get_active()
        self.application.config['state']['convert'] = do_convert
        self.application.config['state']['free'] = \
            self.free_radiobutton.get_active()
        self.application.notify_config_changed()

        # Actual start a thread to send the documents
        sender = SendKindle(self.application.config['settings'])
        self.current_op = SendThread(
            sender, self.get_recipient(), [self.filename], convert=do_convert)
        self.current_op.on_done = self._current_op_done
        self.current_op.start()

    def _free_paid_radiobutton_toggled(self, widget):
        self.update_ui(state=False)

    def _window_destroy(self, widget):
        self.application.stop()

    def _current_op_done(self, error):
        if not error:
            # File has been sent; show a notification and exit.
            n = Notify.Notification.new(
                "Sent to Kindle",
                'The document "%s" has been sent.' % self.filename,
                "dialog-ok")
            n.show()
            self.application.stop()
        else:
            # File has not been sent. Show an error
            n = Notify.Notification.new(
                "Failed to send to Kindle",
                'The document "%s" could not be sent: %s' % (
                    self.filename, error),
                "dialog-error")
            n.show()

            # Put the indicator in error mode, the user may have
            # missed the notification
            self.indicator.set_error(error)

        self.current_op = None

    def _config_changed(self, app, settings):
        self.update_ui()

    def update_ui(self, state=True):
        """Updates various UI elements to match current settings,
        UI selections etc.
        """

        # Cost
        in_us = self.application.config['settings']['user']['in_us']
        cost_per_mb = Decimal("0.15") if in_us else Decimal("0.99")
        free = self.free_radiobutton.get_active()
        if free:
            cost = 0
        else:
            cost = Decimal.from_float(
                self.filesize / 1024.0 / 1024) / cost_per_mb
        self.cost_label.set_label("Estimated Cost: $%.2f" % round(cost, 2))
        self.cost_label.set_visible(cost!=0)

        # If not yet configured, force the user to do so first
        if not self.application.is_configured():
            self.send_button.set_label('Setup your Kindle first')
            self.configure_button.hide()
        else:
            self.send_button.set_label('Send to %s' % self.get_recipient())
            self.configure_button.show()

        # State
        if state:
            state = self.application.config['state']
            self.free_radiobutton.set_active(state['free'])
            self.objects.get_object('convert-checkbox').set_active(
                state['convert'])

    def get_recipient(self):
        """Return the currently configured recipient.
        """
        username = self.application.config['settings']['user']['kindle-name']
        free = self.free_radiobutton.get_active()
        host = 'free.kindle.com' if free else 'kindle.com'
        return "%s@%s" % (username, host)

    def show_configure_window(self):
        configure_window = ConfigureWindow(self.application)
        configure_window.show()

    def use_file(self, filename):
        """Make the window preview the send of the given file.
        """
        # Let GIO make us an absolute path
        file = Gio.file_new_for_path(filename)
        self.filename = filename = file.get_path()

        # Get icon and filesize
        fileinfo = file.query_info(
            'standard::icon,standard::size',
            Gio.FileQueryInfoFlags.NONE, None)
        self.filesize = fileinfo.get_size()

        # Update the UI - show the filename
        label = self.objects.get_object('filename-label')
        label.set_markup("%s\n<small><i>%s</i></small>" % (
            filename, sizeof_fmt(self.filesize)))
        # Show the icon
        image = self.objects.get_object('file-icon-image')
        image.set_from_gicon(fileinfo.get_icon(), Gtk.IconSize.DIALOG)

        self.update_ui()

    def abort_upload(self):
        """Abort the current upload operation.
        """
        if self.current_op:
            self.current_op.stop()
            # Give the thread a bit of time to complete
            self.current_op.join(timeout=2)
        self.application.stop()

    def show(self):
        self.window.show_all()


def merge(dict1, dict2):
    """Merge ``dict2`` into ``dict1``.

    This is basically a recursive update.
    """
    for key, val in dict2.items():
        if isinstance(val, dict):
            child = dict1.setdefault(key, {})
            merge(child, val)
        else:
            dict1[key] = val


class Application(GObject.GObject):

    __gsignals__ = {
        "config-changed": (
            GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self, filename):
        super(Application, self).__init__()

        # For some reason this seems to be disabled by default.
        Gtk.Settings.get_default().set_long_property(
            'gtk-button-images', True, 'main')

        self.set_default_config()
        self.load_config()

        self.window = MainWindow(self)
        self.window.use_file(filename)

    def get_config_path(self):
        """Return the folder where we store our configuration files.

        Will create the folder if it doesn't exist.
        """
        # http://standards.freedesktop.org/basedir-spec/latest/ar01s03.html
        base = os.environ.get('XDG_CONFIG_HOME') or path.expanduser('~/.config')
        dir = path.join(base, 'sendtokindle')
        if not path.exists(dir):
            os.mkdir(dir)
        return dir

    def set_default_config(self):
        """Initialize the default configuration.
        """
        self.config = {
            # Permanent settings
            'settings': {
                'user': {
                    'email': '',
                    'kindle-name': '',
                    'in_us': False,
                },
                'smtp': {
                    'host': '',
                    'port': '',
                    'username': '',
                    'password': '',
                    'type': '',
                }
            },
            # Transient window state
            'state': {
                'convert': True,
                'free': True,
            }
        }

    def load_config(self):
        """Load configuration from a file.

        Note that we have two different types of config values, the
        actual settings, and the last window state that we store and
        restore.
        """
        config_path = self.get_config_path()

        permanent_config = path.join(config_path, 'settings.json')
        if path.isfile(permanent_config):
            with open(permanent_config) as f:
                merge(self.config['settings'], json.load(f))

        state_config = path.join(config_path, 'state.json')
        if path.isfile(state_config):
            with open(state_config) as f:
                merge(self.config['state'], json.load(f))

        self.notify_config_changed()

    def save_config(self):
        """Write current configuration to a file.
        """
        config_path = self.get_config_path()

        permanent_config = path.join(config_path, 'settings.json')
        with open(permanent_config, 'w') as f:
            json.dump(self.config['settings'], f)

        state_config = path.join(config_path, 'state.json')
        with open(state_config, 'w') as f:
            json.dump(self.config['state'], f)

    def notify_config_changed(self):
        """Should be called by whoever modifies the configuration
        after he is done.
        """
        self.emit('config-changed', self.config)

    def is_configured(self):
        """Check if we are configured, and ready to send documents.
        """
        for key in ('email', 'kindle-name'):
            if not self.config['settings']['user'][key]:
                return False
        for key in ('host',):
            if not self.config['settings']['smtp'][key]:
                return False
        return True

    def run(self):
        """Run the application.
        """
        self.window.show()

        Gdk.threads_enter()
        Gtk.main()
        Gdk.threads_leave()

    def stop(self):
        """Sto the application.
        """
        # Before we go, save the config; in particular, we're
        # interested in saving the state.
        self.save_config()

        Gtk.main_quit()


class Indicator(object):
    """Encapsulates the Ubuntu App indicator.
    """

    def __init__(self, main_window):
        self.main_window = main_window
        self._create_indicator()

    def _create_indicator(self):
        self.ind = ind = AppIndicator.Indicator.new(
            "sendtokindle",
            "sendtokindle-indicator",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS)
        ind.set_status(AppIndicator.IndicatorStatus.PASSIVE)
        ind.set_attention_icon ("sendtokindle-indicator-error")

        # Attach the required menu
        self.menu = Gtk.Menu()

        self.abort_menuitem = item = Gtk.MenuItem()
        item.connect("activate", self._abort_item_activate)
        item.show()
        self.menu.append(item)

        # TODO: It would be nicer if this were not a submenu, but
        # clicking the indicator itself shows the error. Apparently
        # this might be possible in AppIndicator3.
        self.error_menuitem = item = Gtk.MenuItem()
        item.connect("activate", self._error_item_activate)
        item.show()
        self.menu.append(item)

        self.menu.show()
        ind.set_menu(self.menu)

    def _abort_item_activate(self, widget):
        self.main_window.abort_upload()

    def _error_item_activate(self, widget):
        self.main_window.show()
        self.hide()
        md = Gtk.MessageDialog(
            self.main_window.window,
            Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.ERROR,
            Gtk.ButtonsType.OK,
            "An error occurred trying to send the documents: %s" % self.error)
        md.set_title('Failed to send to Kindle')
        md.run()
        md.destroy()

    def set_error(self, error):
        """Set indicator in error mode (or normal mode if error=None).

        Error mode represents state after a failed send.
        """
        #self.abort_menuitem.set_visible(not bool(error))
        #self.error_menuitem.set_visible(bool(error))
        self.error = error
        # On Natty, sometimes this works, sometimes a menu item
        # is not shown when it should (usually the error item).
        # Sometimes there is segmentation fault.
        if error:
            self.abort_menuitem.hide()
            self.error_menuitem.show()

            self.ind.set_status(AppIndicator.IndicatorStatus.ATTENTION)
        else:
            self.abort_menuitem.show()
            self.error_menuitem.hide()

    def show(self):
        """Show the indicator, refresh the menu to current state.
        """
        self.abort_menuitem.set_label(
            'Abort sending "%s"' % self.main_window.filename)
        # There are a number of strange bugs I ran across with changing
        # the menu item visibility and text dynamically. Setting this
        # as early as possible helps.
        self.error_menuitem.set_label(
            'Error sending "%s"' % self.main_window.filename)
        self.set_error(None)
        self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)

    def hide(self):
        self.ind.set_status(AppIndicator.IndicatorStatus.PASSIVE)


def main():
    if len(sys.argv) <= 1:
        # No filename was passed, let the user choose one.
        dialog = Gtk.FileChooserDialog(title="Choose a file to send", parent=None,
                action=Gtk.FileChooserAction.OPEN,
                buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                         Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        try:
            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                filename = dialog.get_filename()
            else:
                # Nothing for us to do, exit with error code
                return 1

        finally:
            dialog.destroy()
    else:
        filename = sys.argv[1]

    Gdk.threads_init()
    GObject.threads_init()
    Notify.init('send-to-kindle')
    application = Application(filename)
    application.run()

if __name__ == '__main__':
    sys.exit(main() or 0)
