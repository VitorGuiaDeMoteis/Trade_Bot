#!/bin/bash
# Source this file: . ./scripts/use-android.sh
PROJECT_ROOT="$(dirname "$(dirname "$(realpath "${BASH_SOURCE[0]:-$0}")")")"
PROJECT_ANDROID_SDK="$PROJECT_ROOT/.tools/android-sdk"
PROJECT_FLUTTER="$PROJECT_ROOT/.tools/flutter"

if [ ! -f "$PROJECT_FLUTTER/bin/flutter" ]; then
    echo "Flutter portatil ausente. Execute: ./scripts/install-flutter.sh" >&2
    return 1 2>/dev/null || exit 1
else
    FLUTTER_VER=$("$PROJECT_FLUTTER/bin/flutter" --version | head -n 1)
    if [[ "$FLUTTER_VER" != *"3.44.7"* ]]; then
        echo "Versao incorreta do Flutter local ($FLUTTER_VER). Execute: ./scripts/install-flutter.sh" >&2
        return 1 2>/dev/null || exit 1
    fi
    export PATH="$PROJECT_FLUTTER/bin:$PATH"
fi

if [ -f "$PROJECT_ANDROID_SDK/platform-tools/adb" ]; then
    ANDROID_HOME_REAL="$(realpath "$PROJECT_ANDROID_SDK")"
    export ANDROID_HOME="$ANDROID_HOME_REAL"
    export ANDROID_SDK_ROOT="$ANDROID_HOME"
    export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"
else
    echo "Android SDK ausente. Execute: ./scripts/install-android-sdk.sh" >&2
    return 1 2>/dev/null || exit 1
fi
