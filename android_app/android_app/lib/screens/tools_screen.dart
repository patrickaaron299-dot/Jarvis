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
      await widget.api.setToolPe