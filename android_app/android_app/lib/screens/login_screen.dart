import 'package:flutter/material.dart';
import '../config/app_config.dart';
import '../services/api_service.dart';
import '../services/auth_storage.dart';
import '../services/voice_service.dart';
import '../widgets/jarvis_orb.dart';
import 'home_screen.dart';

class LoginScreen extends StatefulWidget {
  final ApiService api;
  final AuthStorage storage;
  final VoiceService voice;

  const LoginScreen({
    super.key,
    required this.api,
    required this.storage,
    required this.voice,
  });

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _serverController = TextEditingController();
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();

  bool _isRegisterMode = false;
  bool _loading = false;
  String? _statusMessage;
  bool _statusIsError = false;

  @override
  void initState() {
    super.initState();
    _loadSavedUrl();
  }

  Future<void> _loadSavedUrl() async {
    final url = await widget.storage.getServerUrl();
    if (mounted) {
      _serverController.text = url;
    }
  }

  @override
  void dispose() {
    _serverController.dispose();
    _usernameController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _testServer() async {
    final url = _serverController.text.trim();
    if (url.isEmpty) return;

    setState(() {
      _loading = true;
      _statusMessage = 'Checking server status...';
      _statusIsError = false;
    });

    try {
      final health = await widget.api.checkHealth(url);
      await widget.storage.saveServerUrl(url);
      if (!mounted) return;
      setState(() {
        _statusMessage = 'ONLINE • Model: ${health['model'] ?? 'Ready'}';
        _statusIsError = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _statusMessage = e.toString();
        _statusIsError = true;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _submit() async {
    final serverUrl = _serverController.text.trim();
    final username = _usernameController.text.trim();
    final password = _passwordController.text;

    if (serverUrl.isEmpty || username.isEmpty || password.isEmpty) {
      setState(() {
        _statusMessage = 'Please fill in server URL, username, and password.';
        _statusIsError = true;
      });
      return;
    }

    setState(() {
      _loading = true;
      _statusMessage = null;
    });

    try {
      if (_isRegisterMode) {
        await widget.api.register(
          serverUrl: serverUrl,
          username: username,
          password: password,
        );
      } else {
        await widget.api.login(
          serverUrl: serverUrl,
          username: username,
          password: password,
        );
      }
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => HomeScreen(
            api: widget.api,
            storage: widget.storage,
            voice: widget.voice,
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _statusMessage = e.toString();
        _statusIsError = true;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppConfig.bgDark,
      body: Stack(
        children: [
          Positioned.fill(child: CustomPaint(painter: DotGridPainter())),
          SafeArea(
            child: Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 420),
                  child: Column(
                    children: [
                      const JarvisOrb(state: JarvisOrbState.idle, size: 170),
                      const SizedBox(height: 16),
                      const Text(
                        'J.A.R.V.I.S. // AUTHENTICATION',
                        style: TextStyle(
                          color: AppConfig.cyanPrimary,
                          letterSpacing: 2.2,
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 20),
                      Container(
                        padding: const EdgeInsets.all(20),
                        decoration: BoxDecoration(
                          color: AppConfig.surfaceDark.withAlpha(230),
                          borderRadius: BorderRadius.circular(14),
                          border: B