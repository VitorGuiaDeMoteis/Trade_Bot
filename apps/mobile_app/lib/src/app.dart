import 'package:flutter/material.dart';

import 'decisions/controller.dart';
import 'live_paper/controller.dart';
import 'market/controller.dart';
import 'shell/app_shell.dart';

class TradingBotApp extends StatelessWidget {
  const TradingBotApp({
    super.key,
    this.controller,
    this.decisionsController,
    this.livePaperController,
    this.useMockLivePaper = false,
    this.mockPreview = false,
    this.initialDestination = AppDestination.summary,
  });

  final MarketController? controller;
  final DecisionsController? decisionsController;
  final LivePaperController? livePaperController;
  final bool useMockLivePaper;
  final bool mockPreview;
  final AppDestination initialDestination;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Trading Bot Dashboard',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF7AA2FF),
          brightness: Brightness.dark,
          surface: const Color(0xFF121820),
        ),
        scaffoldBackgroundColor: const Color(0xFF0A0E14),
        visualDensity: VisualDensity.standard,
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            minimumSize: const Size(48, 56),
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          ),
        ),
      ),
      home: AppShell(
        marketController: controller,
        decisionsController: decisionsController,
        livePaperController: livePaperController,
        useMockLivePaper: useMockLivePaper,
        mockPreview: mockPreview,
        initialDestination: initialDestination,
      ),
    );
  }
}
