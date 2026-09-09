#!/bin/bash
set -e
PROJECT_ROOT="$(dirname "$(dirname "$(realpath "${BASH_SOURCE[0]}")")")"
SDK_DIR="$PROJECT_ROOT/.tools/android-sdk"

MISSING=0
if [ ! -d "$SDK_DIR/platform-tools" ]; then MISSING=1; fi
if [ ! -d "$SDK_DIR/platforms/android-36" ]; then MISSING=1; fi
if [ ! -d "$SDK_DIR/build-tools/36.0.0" ]; then MISSING=1; fi
if [ ! -d "$SDK_DIR/ndk/28.2.13676358" ]; then MISSING=1; fi

if [ "$MISSING" -eq 0 ]; then
    echo "Android SDK e componentes necessarios ja estao presentes."
    exit 0
fi

CMDLINE_URL="https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip"
CMDLINE_CHECKSUM="2d2d50857e4eb553af5a6dc3ad507a17adf43d115264b1afc116f95c92e5e258"

if [ ! -d "$SDK_DIR/cmdline-tools/latest/bin" ]; then
    echo "Baixando Android Command Line Tools..."
    mkdir -p "$SDK_DIR/cmdline-tools"
    cd "$SDK_DIR/cmdline-tools"
    
    wget -q "$CMDLINE_URL" -O cmdline-tools.zip
    
    DOWNLOADED_CHECKSUM=$(sha256sum cmdline-tools.zip | awk '{print $1}')
    if [ "$DOWNLOADED_CHECKSUM" != "$CMDLINE_CHECKSUM" ]; then
        echo "Erro de checksum! Esperado: $CMDLINE_CHECKSUM, Obtido: $DOWNLOADED_CHECKSUM"
        rm -f cmdline-tools.zip
        exit 1
    fi
    
    unzip -q cmdline-tools.zip
    mv cmdline-tools latest
    rm cmdline-tools.zip
fi

echo "Aceitando licencas e instalando platform-tools, platforms;android-36, build-tools;36.0.0, ndk;28.2.13676358..."
yes | "$SDK_DIR/cmdline-tools/latest/bin/sdkmanager" --licenses > /dev/null
if ! "$SDK_DIR/cmdline-tools/latest/bin/sdkmanager" "platform-tools" "platforms;android-36" "build-tools;36.0.0" "ndk;28.2.13676358"; then
    echo "Falha ao instalar componentes do Android SDK."
    exit 1
fi

echo "SDK atualizado com sucesso em $SDK_DIR"
