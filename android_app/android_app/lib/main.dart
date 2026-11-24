import 'package:flutter/material.dart';
import 'config/app_config.dart';
import 'screens/home_screen.dart';
import 'screens/login_screen.dart';
import 'services/api_service.dart';
import 'services/auth_storage.dart';
import 'services/voice_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const JarvisApp());
}

class JarvisApp extends StatefulWidget {
  const JarvisApp({super.key});

  @override
  State<JarvisApp> createState() => _JarvisAppState();
}

class _JarvisAppState extends State<JarvisApp> {
  late final AuthStorage _storage;
  late final ApiService _api;
  late final VoiceService _voice;

  @override
  void initState() {
    super.initState();
    _storage = AuthStorage();
    _api = ApiService(_storage);
    _voice = VoiceService();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: AppConfig.appTitle,
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: AppConfig.bgDark,
        colorScheme: const ColorScheme.dark(
          primary: AppConfig.cyanPrimary,
          secondary: AppConfig.cyanGlow,
          surface: AppConfig.surfaceDark,
        ),
        inputDecorationTheme: InputDecorationTheme(
          labelStyle: const TextStyle(color: AppConfig.textMuted),
          hintStyle: const TextStyle(color: AppConfig.textMuted),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: AppConfig.borderCyan),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: AppConfig.cyanPrimary),
          ),
        ),
      ),
      home: _StartupGate(
        api: _api,
        storage: _storage,
        voice: _voice,
      ),
    );
  }
}

class _StartupGate extends StatefulWidget {
  final ApiService api;
  final AuthStorage storage;
  final VoiceService voice;

  const _StartupGate({
    required this.api,
    required this.storage,
    required this.voice,
  });

  @override
  State<_StartupGate> createState() => _StartupGateState();
}

class _StartupGateState extends State<_StartupGate> {
  bool? _hasToken;

  @override
  void initState() {
    super.initState();
    _checkAuth();
  }

  Future<void> _checkAuth() async {
    final token = await widget.storage.getToken();
    if (mounted) {
      setState(() => _hasToken = token != null && token.isNotEmpty);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_hasToken == null) {
      return const Scaffold(
        backgroundColor: AppConfig.bgDark,
        body: Center(
          child: CircularProgressIndicator(color: AppConfig.cyanPrimary),
        ),
      );
    }

    if (_hasToken == true) {
      return HomeScreen(
        api: widget.api,
        storage: widget.storage,
        voice: widget.voice,
      );
    }

    return LoginScreen(
      api: widget.api,
      storage: widget.storage,
      voice: widget.voice,
    );
  }
}