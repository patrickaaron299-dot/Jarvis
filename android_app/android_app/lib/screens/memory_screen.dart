import 'package:flutter/material.dart';
import '../config/app_config.dart';
import '../services/api_service.dart';
import '../widgets/jarvis_orb.dart';

class MemoryScreen extends StatefulWidget {
  final ApiService api;

  const MemoryScreen({super.key, required this.api});

  @override
  State<MemoryScreen> createState() => _MemoryScreenState();
}

class _MemoryScreenState extends State<MemoryScreen> {
  List<Map<String, dynamic>> _memories = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadMemories();
  }

  Future<void> _loadMemories() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final items = await widget.api.getMemories();
      if (!mounted) return;
      setState(() {
        _memories = items;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _deleteMemory(int id) async {
    try {
      await widget.api.deleteMemory(id);
      if (!mounted) return;
      setState(() {
        _memories.removeWhere((m) => m['id'] == id);
      });
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString())),
      );
    }
  }

  Future<void> _showAddMemoryDialog() async {
    final contentCtrl = TextEditingController();
    final categoryCtrl = TextEditingController(text: 'general');
    int importance = 3;

    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setDialogState) {
            return AlertDialog(
              backgroundColor: AppConfig.surfaceDark,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(14),
                side: const BorderSide(color: AppConfig.borderCyan),
              ),
              title: const Text(
                'ADD MEMORY',
                style: TextStyle(
                  color: AppConfig.cyanPrimary,
                  fontSize: 15,
                  letterSpacing: 1.6,
                ),
              ),
              content: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    TextField(
                      controller: contentCtrl,
                      maxLines: 3,
                      style: const TextStyle(color: AppConfig.textPrimary),
                      decoration: const InputDecoration(
                        labelText: 'What should JARVIS remember?',
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: categoryCtrl,
                      style: const TextStyle(color: AppConfig.textPrimary),
                      decoration: const InputDecoration(
                        labelText: 'Category (e.g. preference, profile, reminder)',
                      ),
                    ),
                    const SizedBox(height: 14),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'Importance:',
                          style: TextStyle(color: AppConfig.textMuted),
                        ),
                        Text(
                          '$importance / 5',
                          style: const TextStyle(
                            color: AppConfig.cyanPrimary,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ],
                    ),
                    Slider(
                      value: importance.toDouble(),
                      min: 1,
                      max: 5,
                      divisions: 4,
                      activeColor: AppConfig.cyanPrimary,
                      onChanged: (v) => setDialogState(() => importance = v.round()),
                    ),
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(ctx, false),
                  child: const Text('Cancel', style: TextStyle(color: AppConfig.textMuted)),
                ),
                ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppConfig.cyanPrimary.withAlpha(45),
                    foregroundColor: AppConfig.cyanPrimary,
                    side: const BorderSide(color: AppConfig.cyanPrimary),
                  ),
                  onPressed: () => Navigator.pop(ctx, true),
                  child: const Text('Save'),
                ),
              ],
            );
          },
        );
      },
    );

    if (saved == true && contentCtrl.text.trim().isNotEmpty) {
      try {
        await widget.api.createMemory(
          content: contentCtrl.text.trim(),
          category: categoryCtrl.text.trim().isEmpty ? 'general' : categoryCtrl.text.trim(),
          importance: importance,
        );
        await _loadMemories();
      } catch (e) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.toString())),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppConfig.bgDark,
      appBar: AppBar(
        backgroundColor: AppConfig.surfaceDark,
        foregroundColor: AppConfig.textPrimary,
        title: const Text(
          'PERSISTENT MEMORY',
          style: TextStyle(fontSize: 15, letterSpacing: 1.8),
        ),
      ),
      floatingActionButton: FloatingActionButton(
        backgroundColor: AppConfig.cyanPrimary.withAlpha(55),
        foregroundColor: AppConfig.cyanPrimary,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: const BorderSide(color: AppConfig.cyanPrimary),
        ),
        onPressed: _showAddMemoryDialog,
        child: const Icon(Icons.add),
      ),
      body: Stack(
        children: [
          Positioned.fill(child: CustomPaint(painter: DotGridPainter())),
          RefreshIndicator(
            color: AppConfig.cyanPrimary,
            onRefresh: _loadMemories,
            child: _loading
                ? const Center(
                    child: CircularProgressIndicator(color: AppConfig.cyanPrimary),
                  )
                : _error != null
                    ? ListView(
                        padding: const EdgeInsets.all(24),
                        children: [
                          Text(
                            _error!,
                            style: const TextStyle(color: AppConfig.statusError),
                          ),
                        ],
                      )
                    : _memories.isEmpty
                        ? ListView(
                            padding: const EdgeInsets.all(32),
                            children: const [
                              Center(
                                child: Text(
                                  'No saved memories yet.\nTap + or tell JARVIS something to remember.',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(color: AppConfig.textMuted, height: 1.5),
                                ),
                              ),
                            ],
                          )
                        : ListView.builder(
                            padding: const EdgeInsets.all(14),
                            itemCount: _memories.length,
                            itemBuilder: (_, index) {
                              final mem = _memories[index];
                              final id = mem['id'] as int;
                              final category = (mem['category'] ?? 'general').toString();
                              final importance = mem['importance'] ?? 3;
                              final content = (mem['content'] ?? '').toString();

                              return Container(
                                margin: const EdgeInsets.only(bottom: 10),
                                padding: const EdgeInsets.all(14),
                                decoration: BoxDecoration(
                                  color: AppConfig.surfaceDark.withAlpha(230),
                                  borderRadius: BorderRadius.circular(12),
                                  border: Border.all(color: AppConfig.borderCyan),
                                ),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            '${category.toUpperCase()}  •  IMPORTANCE $importance/5',
                                            style: const TextStyle(
                                              color: AppConfig.cyanPrimary,
                                              fontSize: 11,
                                              letterSpacing: 1.3,
                                            ),
                                          ),
                                          const SizedBox(height: 6),
                                          Text(
                                            content,
                                            style: const TextStyle(
                                              color: AppConfig.textPrimary,
                                              fontSize: 14.5,
                                              height: 1.4,
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                    IconButton(
                                      icon: const Icon(
                                        Icons.delete_outline,
                                        color: AppConfig.textMuted,
                                      ),
                                      onPressed: () => _deleteMemory(id),
                                    ),
                                  ],
                                ),
                              );
                            },
                          ),
          ),
        ],
      ),
    );
  }
}