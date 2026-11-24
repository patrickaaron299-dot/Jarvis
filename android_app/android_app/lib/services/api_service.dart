import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'auth_storage.dart';

class ApiException implements Exception {
  final String message;
  final int? statusCode;

  ApiException(this.message, {this.statusCode});

  @override
  String toString() => message;
}

class ApiService {
  final AuthStorage storage;

  ApiService(this.storage);

  String _normalizeUrl(String url) {
    var clean = url.trim();
    while (clean.endsWith('/')) {
      clean = clean.substring(0, clean.length - 1);
    }
    return clean;
  }

  Future<Map<String, String>> _authHeaders() async {
    final token = await storage.getToken();
    if (token == null || token.isEmpty) {
      throw ApiException('You are not logged in.', statusCode: 401);
    }
    return {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $token',
    };
  }

  Map<String, dynamic> _decodeResponse(http.Response res) {
    Map<String, dynamic> data = {};
    if (res.body.isNotEmpty) {
      try {
        final decoded = jsonDecode(res.body);
        if (decoded is Map<String, dynamic>) {
          data = decoded;
        }
      } catch (_) {
        // Non-JSON response body
      }
    }

    if (res.statusCode >= 200 && res.statusCode < 300) {
      return data;
    }

    final detail = data['detail']?.toString();
    throw ApiException(
      detail ?? 'Server error (HTTP ${res.statusCode}).',
      statusCode: res.statusCode,
    );
  }

  Future<Map<String, dynamic>> checkHealth(String serverUrl) async {
    final base = _normalizeUrl(serverUrl);
    try {
      final res = await http
          .get(Uri.parse('$base/health'))
          .timeout(const Duration(seconds: 12));
      return _decodeResponse(res);
    } on ApiException {
      rethrow;
    } on TimeoutException {
      throw ApiException('Server took too long to respond.');
    } catch (_) {
      throw ApiException('Could not reach server at $base');
    }
  }

  Future<Map<String, dynamic>> register({
    required String serverUrl,
    required String username,
    required String password,
  }) async {
    final base = _normalizeUrl(serverUrl);
    try {
      final res = await http
          .post(
            Uri.parse('$base/auth/register'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'username': username, 'password': password}),
          )
          .timeout(const Duration(seconds: 20));
      final data = _decodeResponse(res);
      await storage.saveSession(
        serverUrl: base,
        token: data['access_token'] as String,
        username: (data['user'] as Map<String, dynamic>)['username'] as String,
      );
      return data;
    } on ApiException {
      rethrow;
    } on TimeoutException {
      throw ApiException('Connection timed out. Server may be waking up—try again.');
    } catch (_) {
      throw ApiException('Network error while connecting to $base');
    }
  }

  Future<Map<String, dynamic>> login({
    required String serverUrl,
    required String username,
    required String password,
  }) async {
    final base = _normalizeUrl(serverUrl);
    try {
      final res = await http
          .post(
            Uri.parse('$base/auth/login'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'username': username, 'password': password}),
          )
          .timeout(const Duration(seconds: 20));
      final data = _decodeResponse(res);
      await storage.saveSession(
        serverUrl: base,
        token: data['access_token'] as String,
        username: (data['user'] as Map<String, dynamic>)['username'] as String,
      );
      return data;
    } on ApiException {
      rethrow;
    } on TimeoutException {
      throw ApiException('Connection timed out. Server may be waking up—try again.');
    } catch (_) {
      throw ApiException('Network error while connecting to $base');
    }
  }

  Future<Map<String, dynamic>> sendChat({
    required String message,
    int? conversationId,
  }) async {
    final base = await storage.getServerUrl();
    final headers = await _authHeaders();
    try {
      final res = await http
          .post(
            Uri.parse('$base/chat'),
            headers: headers,
            body: jsonEncode({
              'message': message,
              if (conversationId != null) 'conversation_id': conversationId,
            }),
          )
          .timeout(const Duration(seconds: 65));
      return _decodeResponse(res);
    } on ApiException {
      rethrow;
    } on TimeoutException {
      throw ApiException('JARVIS took too long to respond. Please try again.');
    } catch (_) {
      throw ApiException('Lost connection to JARVIS server.');
    }
  }

  Future<List<Map<String, dynamic>>> getConversations() async {
    final base = await storage.getServerUrl();
    final headers = await _authHeaders();
    final res = await http
        .get(Uri.parse('$base/conversations'), headers: headers)
        .timeout(const Duration(seconds: 15));
    final data = _decodeResponse(res);
    return List<Map<String, dynamic>>.from(data['conversations'] ?? const []);
  }

  Future<List<Map<String, dynamic>>> getConversationMessages(int conversationId) async {
    final base = await storage.getServerUrl();
    final headers = await _authHeaders();
    final res = await http
        .get(Uri.parse('$base/conversations/$conversationId/messages'), headers: headers)
        .timeout(const Duration(seconds: 15));
    final data = _decodeResponse(res);
    return List<Map<String, dynamic>>.from(data['messages'] ?? const []);
  }

  Future<void> deleteConversation(int conversationId) async {
    final base = await storage.getServerUrl();
    final headers = await _authHeaders();
    final res = await http
        .delete(Uri.parse('$base/conversations/$conversationId'), headers: headers)
        .timeout(const Duration(seconds: 15));
    _decodeResponse(res);
  }

  Future<List<Map<String, dynamic>>> getMemories() async {
    final base = await storage.getServerUrl();
    final headers = await _authHeaders();
    final res = await http
        .get(Uri.parse('$base/memories'), headers: headers)
        .timeout(const Duration(seconds: 15));
    final data = _decodeResponse(res);
    return List<Map<String, dynamic>>.from(data['memories'] ?? const []);
  }

  Future<Map<String, dynamic>> createMemory({
    required String content,
    String category = 'general',
    int importance = 3,
  }) async {
    final base = await storage.getServerUrl();
    final headers = await _authHeaders();
    final res = await http
        .post(
          Uri.parse('$base/memories'),
          headers: headers,
          body: jsonEncode({
            'content': content,
            'category': category,
            'importance': importance,
          }),
        )
        .timeout(const Duration(seconds: 15));
    final data = _decodeResponse(res);
    return Map<String, dynamic>.from(data['memory'] ?? {});
  }

  Future<void> deleteMemory(int memoryId) async {
    final base = await storage.getServerUrl();
    final headers = await _authHeaders();
    final res = await http
        .delete(Uri.parse('$base/memories/$memoryId'), headers: headers)
        .timeout(const Duration(seconds: 15));
    _decodeResponse(res);
  }

  Future<List<Map<String, dynamic>>> getTools() async {
    final base = await storage.getServerUrl();
    final headers = await _authHeaders();
    final res = await http
        .get(Uri.parse('$base/tools'), headers: headers)
        .timeout(const Duration(seconds: 15));
    final data = _decodeResponse(res);
    return List<Map<String, dynamic>>.from(data['tools'] ?? const []);
  }

  Future<void> setToolPermission(String toolName, bool isAllowed) async {
    final base = await storage.getServerUrl();
    final headers = await _authHeaders();
    final res = await http
        .put(
          Uri.parse('$base/tools/$toolName'),
          headers: headers,
          body: jsonEncode({'is_allowed': isAllowed}),
        )
        .timeout(const Duration(seconds: 15));
    _decodeResponse(res);
  }

  Future<List<Map<String, dynamic>>> getToolLogs() async {
    final base = await storage.getServerUrl();
    final headers = await _authHeaders();
    final res = await http
        .get(Uri.parse('$base/tools/logs'), headers: headers)
        .timeout(const Duration(seconds: 15));
    final data = _decodeResponse(res);
    return List<Map<String, dynamic>>.from(data['logs'] ?? const []);
  }
}