import 'package:flutter/material.dart';

import 'market/controller.dart';
import 'market/page.dart';

class TradingBotApp extends StatelessWidget {
  const TradingBotApp({super.key, this.controller});

  final MarketController? controller;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Trading Bot Dashboard',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF8FABFF),
          brightness: Brightness.dark,
          surface: const Color(0xFF151C2A),
        ),
        scaffoldBackgroundColor: const Color(0xFF0B101A),
        visualDensity: VisualDensity.standard,
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            minimumSize: const Size(48, 56),
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          ),
        ),
      ),
      home: MarketPage(controller: controller),
    );
  }
}
