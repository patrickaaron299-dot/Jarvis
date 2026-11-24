import 'package:flutter/material.dart';
import '../config/app_config.dart';
import '../services/api_service.dart';
import '../services/auth_storage.dart';
import '../services/voice_service.dart';
import '../widgets/jarvis_orb.dart';
import 'login_screen.dart';
import 'memory_screen.dart';
import 'tools_screen.dart';

class _ChatMessage {
  final String role;
  final String content;
  final List<String> toolsUsed;

  _ChatMessage({
    required this.role,
    required this.content,
    this.toolsUsed = const [],
  });
}

class HomeScreen extends StatefulWidget {
  final ApiService api;
  final AuthStorage storage;
  final VoiceService voice;

  const HomeScreen({
    super.key,
    required this.api,
    required this.storage,
    required this.voice,
  });

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _inputController = TextEditingController();
  final _scrollController = ScrollController();

  final List<_ChatMessage> _messages = [];
  int? _conversationId;
  bool _serverOnline = false;
  bool _autoSpeak = true;
  bool _isThinking = false;
  bool _isListening = false;
  bool _isSpeaking = false;

  @override
  void initState() {
    super.initState();
    _initScreen();
  }

  Future<void> _initScreen() async {
    _autoSpeak = await widget.storage.getAutoSpeak();
    await widget.voice.initTts(
      onSpeakStart: () {
        if (mounted) setState(() => _isSpeaking = true);
      },
      onSpeakDone: () {
        if (mounted) setState(() => _isSpeaking = false);
      },
    );
    await _checkServerHealth();
  }

  Future<void> _checkServerHealth() async {
    try {
      final url = await widget.storage.getServerUrl();
      await widget.api.checkHealth(url);
      if (mounted) setState(() => _serverOnline = true);
    } catch (_) {
      if (mounted) setState(() => _serverOnline = false);
    }
  }

  @override
  void dispose() {
    _inputController.dispose();
    _scrollController.dispose();
    widget.voice.dispose();
    super.dispose();
  }

  JarvisOrbState get _orbState {
    if (_isListening) return JarvisOrbState.listening;
    if (_isThinking) return JarvisOrbState.thinking;
    if (_isSpeaking) return JarvisOrbState.speaking;
    return JarvisOrbState.idle;
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _handleAuthExpired() async {
    await widget.storage.clearSession();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(
        builder: (_) => LoginScreen(
          api: widget.api,
          storage: widget.storage,
          voice: widget.voice,
        ),
      ),
      (_) => false,
    );
  }

  Future<void> _sendMessage([String? overrideText]) async {
    final text = (overrideText ?? _inputController.text).trim();
    if (text.isEmpty || _isThinking) return;

    _inputController.clear();
    await widget.voice.stopSpeaking();

    setState(() {
      _messages.add(_ChatMessage(role: 'user', content: text));
      _isThinking = true;
    });
    _scrollToBottom();

    try {
      final res = await widget.api.sendChat(
        message: text,
        conversationId: _conversationId,
      );
      _conversationId = res['conversation_id'] as int?;
      final reply = (res['reply'] ?? '').toString();
      final rawTools = (res['tools_used'] as List<dynamic>? ?? []);
      final toolsUsed = rawTools
          .map((t) => '${t['tool_name']} (${t['status']})')
          .toList();

      if (!mounted) return;
      setState(() {
        _serverOnline = true;
        _messages.add(
          _ChatMessage(role: 'assistant', content: reply, toolsUsed: toolsUsed),
        );
        _isThinking = false;
      });
      _scrollToBottom();

      if (_autoSpeak && reply.isNotEmpty) {
        await widget.voice.speak(reply);
      }
    } on ApiException catch (e) {
      if (e.statusCode == 401) {
        await _handleAuthExpired();
        return;
      }
      if (!mounted) return;
      setState(() {
        _isThinking = false;
        _messages.add(
          _ChatMessage(role: 'error', content: e.message),
        );
      });
      _scrollToBottom();
    }
  }

  Future<void> _toggleVoice() async {
    if (_isSpeaking) {
      await widget.voice.stopSpeaking();
      return;
    }

    if (_isListening) {
      await widget.voice.stopListening();
      setState(() => _isListening = false);
      return;
    }

    await widget.voice.startListening(
      onResult: (words, isFinal) {
        if (!mounted) return;
        setState(() {
          _inputController.text = words;
          _inputController.selection = TextSelection.fromPosition(
            TextPosition(offset: words.length),
          );
        });
        if (isFinal && words.trim().isNotEmpty) {
          _sendMessage(words);
        }
      },
      onListeningChanged: (active) {
        if (mounted) setState(() => _isListening = active);
      },
      onError: (msg) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Voice input: $msg')),
        );
      },
    );
  }

  Future<void> _openHistorySheet() async {
    try {
      final conversations = await widget.api.getConversations();
      if (!mounted) return;
      showModalBottomSheet(
        context: context,
        backgroundColor: AppConfig.surfaceDark,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
        ),
        builder: (ctx) {
          return SafeArea(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Padding(
                  padding: EdgeInsets.all(16),
                  child: Text(
                    'CONVERSATION HISTORY',
                    style: TextStyle(
                      color: AppConfig.cyanPrimary,
                      letterSpacing: 1.8,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                if (conversations.isEmpty)
                  const Padding(
                    padding: EdgeInsets.all(24),
                    child: Text(
                      'No past conversations yet.',
                      style: TextStyle(color: AppConfig.textMuted),
                    ),
                  )
                else
                  Flexible(
                    child: ListView.builder(
                      shrinkWrap: true,
                      itemCount: conversations.length,
                      itemBuilder: (_, index) {
                        final conv = conversations[index];
                        final convId = conv['id'] as int;
                        return ListTile(
                          title: Text(
                            conv['title']?.toString() ?? 'Conversation',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(color: AppConfig.textPrimary),
                          ),
                          trailing: IconButton(
                            icon: const Icon(Icons.delete_outline, color: AppConfig.textMuted),
                            onPressed: () async {
                              await widget.api.deleteConversation(convId);
                              if (_conversationId == convId && mounted) {
                                setState(() {
                                  _conversationId = null;
                                  _