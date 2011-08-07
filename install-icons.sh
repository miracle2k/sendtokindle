#!/bin/bash
#
# Stolen from hamster-appindicator
#
# As an alternative to using setup.py.

install_icon() {
    file="$1"
    name="$2"
    theme="$3"
    size="$4"

    xdg-icon-resource install --novendor --theme "$theme" --size "$size" "$file" "$name"
}

# XXX: These themes don't define 64x64 icons - why does it work anyway?
for theme in ubuntu-mono-light ubuntu-mono-dark; do
    install_icon data/icons/$theme/sendtokindle-indicator.png sendtokindle-indicator $theme 64
    install_icon data/icons/$theme/sendtokindle-indicator-error.png sendtokindle-indicator-error $theme 64
done

install_icon data/icons/hicolor/sendtokindle.png sendtokindle hicolor 256
install_icon data/icons/hicolor/sendtokindle-pay.png sendtokindle-pay hicolor 16
