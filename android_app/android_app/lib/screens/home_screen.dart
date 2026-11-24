import 'package:flutter/material.dart';
import '../config/app_config.dart';
import '../services/api_service.dart';
import '../widgets/jarvis_orb.dart';

class ToolsScreen extends StatefulWidget {
  final ApiService api;

  const ToolsScreen({super.key, required this.api});

  @override
  State<ToolsScreen> createState() => _ToolsScreenState();
}

class _ToolsScreenState extends State<ToolsScreen> {
  List<Map<String, dynamic>> _tools = [];
  List<Map<String, dynamic>> _logs = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final results = await Future.wait([
        widget.api.getTools(),
        widget.api.getToolLogs(),
      ]);
      if (!mounted) return;
      setState(() {
        _tools = results[0];
        _logs = results[1];
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

  Future<void> _toggleTool(int index, bool nextValue) async {
    final tool = _tools[index];
    final name = tool['name'].toString();
    final previous = tool['is_allowed'] == true;

    setState(() {
      _tools[index] = {...tool, 'is_allowed': nextValue};
    });

    try {
      await widget.api.setToolPermission(name, nextValue);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _tools[index] = {...tool, 'is_allowed': previous};
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString())),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        backgroundColor: AppConfig.bgDark,
        appBar: AppBar(
          backgroundColor: AppConfig.surfaceDark,
          foregroundColor: AppConfig.textPrimary,
          title: const Text(
            'AUTHORISED TOOLS',
            style: TextStyle(fontSize: 15, letterSpacing: 1.8),
          ),
          bottom: const TabBar(
            indicatorColor: AppConfig.cyanPrimary,
            labelColor: AppConfig.cyanPrimary,
            unselectedLabelColor: AppConfig.textMuted,
            tabs: [
              Tab(text: 'PERMISSIONS'),
              Tab(text: 'AUDIT LOG'),
            ],
          ),
        ),
        body: Stack(
          children: [
            Positioned.fill(child: CustomPaint(painter: DotGridPainter())),
            if (_loading)
              const Center(
                child: CircularProgressIndicator(color: AppConfig.cyanPrimary),
              )
            else if (_error != null)
              Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(
                    _error!,
                    style: const TextStyle(color: AppConfig.statusError),
                  ),
                ),
              )
            else
              TabBarView(
                children: [
                  _buildPermissionsTab(),
                  _buildLogsTab(),
                ],
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildPermissionsTab() {
    return RefreshIndicator(
      color: AppConfig.cyanPrimary,
      onRefresh: _loadData,
      child: ListView.builder(
        padding: const EdgeInsets.all(14),
        itemCount: _tools.length,
        itemBuilder: (_, index) {
          final tool = _tools[index];
          final name = tool['name'].toString();
          final description = (tool['description'] ?? '').toString();
          final isAllowed = tool['is_allowed'] == true;

          return Container(
            margin: const EdgeInsets.only(bottom: 10),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            decoration: BoxDecoration(
              color: AppConfig.surfaceDark.withAlpha(230),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: isAllowed ? AppConfig.cyanPrimary.withAlpha(110) : AppConfig.borderCyan,
              ),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        name,
                        style: const TextStyle(
                          color: AppConfig.cyanPrimary,
                          fontWeight: FontWeight.bold,
                          fontSize: 14.5,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        description,
                        style: const TextStyle(
                          color: AppConfig.textMuted,
                          fontSize: 13,
                          height: 1.35,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                Switch(
                  value: isAllowed,
                  activeThumbColor: AppConfig.cyanPrimary,
                  onChanged: (val) => _toggleTool(index, val),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildLogsTab() {
    return RefreshIndicator(
      color: AppConfig.cyanPrimary,
      onRefresh: _loadData,
      child: _logs.isEmpty
          ? ListView(
              padding: const EdgeInsets.all(32),
              children: const [
                Center(
                  child: Text(
                    'No tool activity recorded yet.',
                    style: TextStyle(color: AppConfig.textMuted),
                  ),
                ),
              ],
            )
          : ListView.builder(
              padding: const EdgeInsets.all(14),
              itemCount: _logs.length,
              itemBuilder: (_, index) {
                final log = _logs[index];
                final status = (log['status'] ?? '').toString();
                final isGood = status == 'executed' || status == 'allowed';

                return Container(
                  margin: const EdgeInsets.only(bottom: 10),
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: AppConfig.surfaceDark.withAlpha(230),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: AppConfig.borderCyan),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            (log['tool_name'] ?? '').toString(),
                            style: const TextStyle(
                              color: AppConfig.textPrimary,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          Text(
                            status.toUpperCase(),
                            style: TextStyle(
                              color: isGood ? AppConfig.cyanPrimary : AppConfig.statusError,
                              fontSize: 11,
                              letterSpacing: 1.2,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'Args: ${log['arguments_json'] ?? '{}'}',
                        style: const TextStyle(color: AppConfig.textMuted, fontSize: 12),
                      ),
                      if ((log['result_summary'] ?? '').toString().isNotEmpty) ...[
                        const SizedBox(height: 4),
                        Text(
                          log['result_summary'].toString(),
                          maxLines: 3,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(color: AppConfig.textPrimary, fontSize: 12.5),
                        ),
                      ],
                    ],
                  ),
                );
              },
            ),
    );
  }
}