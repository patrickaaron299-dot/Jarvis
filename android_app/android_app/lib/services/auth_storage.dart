import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../config/app_config.dart';

class AuthStorage {
  static const _keyServerUrl = 'jarvis_server_url';
  static const _keyToken = 'jarvis_access_token';
  static const _keyUsername = 'jarvis_username';
  static const _keyAutoSpeak = 'jarvis_auto_speak';

  final FlutterSecureStorage _storage = const FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  Future<String> getServerUrl() async {
    final saved = await _storage.read(key: _keyServerUrl);
    if (saved == null || saved.trim().isEmpty) {
      return AppConfig.defaultServerUrl;
    }
    return _normalizeUrl(saved);
  }

  Future<void> saveServerUrl(String url) async {
    await _storage.write(key: _keyServerUrl, value: _normalizeUrl(url));
  }

  Future<String?> getToken() => _storage.read(key: _keyToken);

  Future<String?> getUsername() => _storage.read(key: _keyUsername);

  Future<void> saveSession({
    required String serverUrl,
    required String token,
    required String username,
  }) async {
    await _storage.write(key: _keyServerUrl, value: _normalizeUrl(serverUrl));
    await _storage.write(key: _keyToken, value: token);
    await _storage.write(key: _keyUsername, value: username);
  }

  Future<bool> getAutoSpeak() async {
    final raw = await _storage.read(key: _keyAutoSpeak);
    if (raw == null) return true;
    return raw == 'true';
  }

  Future<void> setAutoSpeak(bool enabled) async {
    await _storage.write(key: _keyAutoSpeak, value: enabled ? 'true' : 'false');
  }

  Future<void> clearSession() async {
    await _storage.delete(key: _keyToken);
    await _storage.delete(key: _keyUsername);
  }

  String _normalizeUrl(String url) {
    var clean = url.trim();
    while (clean.endsWith('/')) {
      clean = clean.substring(0, clean.length - 1);
    }
    return clean;
  }
}