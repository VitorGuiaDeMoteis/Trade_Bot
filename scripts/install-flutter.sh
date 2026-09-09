#!/bin/bash
set -e
PROJECT_ROOT="$(dirname "$(dirname "$(realpath "${BASH_SOURCE[0]}")")")"
FLUTTER_DIR="$PROJECT_ROOT/.tools/flutter"
FLUTTER_TAR_URL="https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_3.44.7-stable.tar.xz"
FLUTTER_SHA256="a0edd646c159c0e816788c0e46a4f071199c1320495898f5a679599b583a05a4"

mkdir -p "$PROJECT_ROOT/.tools"

if [ -f "$FLUTTER_DIR/bin/flutter" ]; then
    VERSION=$("$FLUTTER_DIR/bin/flutter" --version | head -n 1)
    if [[ "$VERSION" == *"3.44.7"* ]]; then
        echo "Flutter 3.44.7 ja esta instalado em $FLUTTER_DIR"
        exit 0
    fi
    echo "Removendo versao incorreta do Flutter ($VERSION)..."
    rm -rf "$FLUTTER_DIR"
fi

# Clean up any leftover git clone flutter
if [ -d "$FLUTTER_DIR/.git" ]; then
    echo "Removendo checkout antigo do git..."
    rm -rf "$FLUTTER_DIR"
fi

echo "Baixando Flutter 3.44.7 (tarball oficial)..."
cd "$PROJECT_ROOT/.tools"
wget -q "$FLUTTER_TAR_URL" -O flutter.tar.xz

DOWNLOADED_SHA256=$(sha256sum flutter.tar.xz | awk '{print $1}')
if [ "$DOWNLOADED_SHA256" != "$FLUTTER_SHA256" ]; then
    echo "Erro de checksum do Flutter! Esperado: $FLUTTER_SHA256, Obtido: $DOWNLOADED_SHA256"
    rm -f flutter.tar.xz
    exit 1
fi

echo "Extraindo Flutter..."
tar xf flutter.tar.xz
rm -f flutter.tar.xz

echo "Flutter 3.44.7 instalado com sucesso."
