# Demonstração — M1

## Preparar

Seguir [RUNBOOK](RUNBOOK.md): Compose saudável, migração 0002_m1, API loopback, adb reverse e flutter run com API_BASE_URL. SIMULATOR_INTERVAL_SECONDS=2; sem qualquer chave externa.

## Roteiro de 3 minutos

1. Abrir app normal no Xiaomi 1791a20e. Mostrar SIMULADO, Conectado, ACELERADA, TEST / 1h e horário de recebimento em UTC.
2. Mostrar histórico carregado e esperar dois novos candles. Cada candle representa uma hora virtual; não se trata de preço de mercado real.
3. Tocar um candle ou usar anterior/próximo; conferir abertura, máxima, mínima, fechamento, volume e regime fictício. A inspeção não salta enquanto chegam candles novos, salvo saída da janela dos últimos 60.
4. Ver retrato/paisagem. Na falta de rotação física, usar script de captura temporária e confirmar restauração.
5. Parar **somente o backend da demo**, no terminal correspondente. App mostra Offline e conserva gráfico/último horário. Reiniciar com mesma seed/início; app preenche lacuna via REST e volta a acompanhar WS.
6. Conferir /health e SQL de unicidade. Não existem ordens, carteira, lucro ou decisões de estratégia.

## Evidências desta execução

- [Resultados de integração no tablet](evidence/m1-tablet-tests.txt): REST + WS + inspeção nas duas orientações; backend interrompido, seis candles recuperados, segunda conexão.
- [Retrato em janela Android de compatibilidade](evidence/m1-tablet-integration-portrait.png).
- [Paisagem na integração](evidence/m1-tablet-integration-landscape.png).
- [Offline com gráfico preservado](evidence/m1-tablet-offline.png).
- [Conexão recuperada](evidence/m1-tablet-recovered.png).
- [544 candles/eventos sem duplicação](evidence/m1-sql-integrity.txt).
- [494 candles anteriores preservados integralmente](evidence/m1-restart-preservation.json).
- [PostgreSQL parado/recuperado](evidence/m1-database-outage.json).

Capturas foram inspecionadas: textos/selos legíveis e sem overflow visível; detalhes são acessíveis por rolagem. Testes verificam botões >=48 dp e toque funcional.

## Pendência para repetir no app normal

A integração passou, mas a reinstalação posterior do APK normal foi recusada pelo instalador Android (INSTALL_FAILED_USER_RESTRICTED). O app normal não ficou instalado após essas tentativas. É necessário confirmar a instalação no tablet quando flutter run solicitar. Não desativar proteções para contornar.

Capturas de retrato ocupando o display inteiro e revisão visual final do app normal aguardam essa confirmação. A captura atual de retrato é 984×1200 em janela de compatibilidade, não prova display inteiro de 1200×1920. O modo de rotação permanece free, user_rotation=0, accelerometer_rotation=1.

Resultado final e eventuais atualizações dessa pendência ficam em [STATUS](STATUS.md). M2 não está implementado.
