import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart';

class VoiceService {
  final SpeechToText _speech = SpeechToText();
  final FlutterTts _tts = FlutterTts();

  bool _speechReady = false;
  bool _ttsReady = false;
  bool isListening = false;
  bool isSpeaking = false;

  Future<void> initTts({
    VoidCallback? onSpeakStart,
    VoidCallback? onSpeakDone,
  }) async {
    if (_ttsReady) return;
    await _tts.setLanguage('en-US');
    await _tts.setSpeechRate(0.5);
    await _tts.setVolume(1.0);
    await _tts.setPitch(1.0);

    _tts.setStartHandler(() {
      isSpeaking = true;
      onSpeakStart?.call();
    });
    _tts.setCompletionHandler(() {
      isSpeaking = false;
      onSpeakDone?.call();
    });
    _tts.setCancelHandler(() {
      isSpeaking = false;
      onSpeakDone?.call();
    });
    _tts.setErrorHandler((_) {
      isSpeaking = false;
      onSpeakDone?.call();
    });

    _ttsReady = true;
  }

  Future<bool> startListening({
    required void Function(String words, bool isFinal) onResult,
    required void Function(bool listening) onListeningChanged,
    required void Function(String message) onError,
  }) async {
    await stopSpeaking();

    if (!_speechReady) {
      _speechReady = await _speech.initialize(
        onStatus: (status) {
          final active = status == 'listening';
          isListening = active;
          onListeningChanged(active);
        },
        onError: (err) {
          isListening = false;
          onListeningChanged(false);
          onError(err.errorMsg);
        },
      );
    }

    if (!_speechReady) {
      onError('Microphone or speech recognition is unavailable on this device.');
      return false;
    }

    isListening = true;
    onListeningChanged(true);

    await _speech.listen(
      onResult: (result) {
        onResult(result.recognizedWords, result.finalResult);
        if (result.finalResult) {
          isListening = false;
          onListeningChanged(false);
        }
      },
      listenFor: const Duration(seconds: 30),
      pauseFor: const Duration(seconds: 4),
      listenOptions: SpeechListenOptions(
        listenMode: ListenMode.confirmation,
        partialResults: true,
        cancelOnError: true,
      ),
    );
    return true;
  }

  Future<void> stopListening() async {
    if (_speech.isListening) {
      await _speech.stop();
    }
    isListening = false;
  }

  Future<void> speak(String text) async {
    final cleaned = _cleanForSpeech(text);
    if (cleaned.isEmpty) return;
    await initTts();
    await _tts.stop();
    await _tts.speak(cleaned);
  }

  Future<void> stopSpeaking() async {
    if (isSpeaking) {
      await _tts.stop();
      isSpeaking = false;
    }
  }

  String _cleanForSpeech(String raw) {
    return raw
        .replaceAll(RegExp(r'```[\s\S]*?```'), ' Code snippet provided on screen. ')
        .replaceAll(RegExp(r'[*_`#>]'), '')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }

  Future<void> dispose() async {
    await stopListening();
    await stopSpeaking();
  }
}