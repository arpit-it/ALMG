import 'dart:convert';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

/// Edits a project’s instructions and local reference files.
class ProjectSettings extends StatefulWidget {
  /// Creates an editor for an existing project.
  const ProjectSettings({
    super.key,
    required this.project,
    required this.request,
  });

  /// Initial project record, including instructions and reference files.
  final Map<String, dynamic> project;

  /// Callback for requests to the project API.
  final Future<Map<String, dynamic>> Function(String path, {Object? body})
  request;

  /// Creates the state that owns the project editor.
  @override
  State<ProjectSettings> createState() => _ProjectSettingsState();
}

/// Manages project edits and refreshes the dialog after changes.
class _ProjectSettingsState extends State<ProjectSettings> {
  late Map<String, dynamic> _project = widget.project;
  late final _instructions = TextEditingController(
    text: widget.project['instructions'] as String,
  );
  bool _busy = false;
  String? _error;

  Future<void> _update(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
      final project = await widget.request('/projects/${_project['id']}');
      if (mounted) setState(() => _project = project);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Runs a project mutation and refreshes the displayed settings.
  Future<void> _addFile() => _update(() async {
    final file = await openFile(
      acceptedTypeGroups: const [
        XTypeGroup(
          label: 'Text files',
          extensions: ['txt', 'md', 'csv', 'json'],
        ),
      ],
    );
    if (file == null) return;
    if (await file.length() > 30000) {
      throw const FormatException('Choose a UTF-8 text file up to 30 KB.');
    }
    final content = utf8.decode(await file.readAsBytes());
    await widget.request(
      '/projects/files/add',
      body: {'id': _project['id'], 'name': file.name, 'content': content},
    );
  });

  /// Runs a project mutation and refreshes the displayed settings.
  Future<void> _save() => _update(() async {
    await widget.request(
      '/projects/instructions',
      body: {'id': _project['id'], 'instructions': _instructions.text},
    );
    if (mounted) Navigator.pop(context);
  });

  /// Confirms removal of a reference before calling the backend.
  Future<void> _removeFile(Map<dynamic, dynamic> file) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialog) => AlertDialog(
        title: const Text('Remove reference?'),
        content: Text('Remove “${file['name']}” from this project?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialog, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialog, true),
            child: const Text('Remove'),
          ),
        ],
      ),
    );
    if (!mounted || confirmed != true) return;
    await _update(() async {
      await widget.request(
        '/projects/files/remove',
        body: {'id': _project['id'], 'file_id': file['id']},
      );
    });
  }

  /// Disposes the project instructions controller.
  @override
  void dispose() {
    _instructions.dispose();
    super.dispose();
  }

  /// Builds the instructions editor and reference list.
  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(_project['name'] as String),
    scrollable: true,
    content: SizedBox(
      width: 460,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextField(
            controller: _instructions,
            enabled: !_busy,
            minLines: 3,
            maxLines: 6,
            maxLength: 2000,
            decoration: const InputDecoration(
              labelText: 'Instructions for all project chats',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            'Reference files',
            style: Theme.of(context).textTheme.titleSmall,
          ),
          for (final file in _project['files'] as List)
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              title: Text(file['name'] as String),
              trailing: IconButton(
                tooltip: 'Remove reference',
                icon: const Icon(Icons.remove_circle_outline),
                onPressed: _busy ? null : () => _removeFile(file as Map),
              ),
            ),
          TextButton.icon(
            onPressed: _busy ? null : _addFile,
            icon: const Icon(Icons.attach_file),
            label: const Text('Add reference file'),
          ),
          if (_busy) const LinearProgressIndicator(),
          if (_error case final String error)
            Text(
              error,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: _busy ? null : () => Navigator.pop(context),
        child: const Text('Close'),
      ),
      FilledButton(
        onPressed: _busy ? null : _save,
        child: const Text('Save instructions'),
      ),
    ],
  );
}
