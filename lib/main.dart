import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';

import 'app_name.dart';

import 'chat.dart';

/// Starts the Flutter desktop application.
void main() => runApp(const ModelStudio());

/// Defines the ALMG theme and initial chat route.
class ModelStudio extends StatelessWidget {
  /// Creates the root ALMG application.
  const ModelStudio({super.key});

  /// Creates the themed application and its chat screen.
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: appName,
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff315c51)),
      fontFamily: 'Inter',
      useMaterial3: true,
    ),
    home: const ChatPage(trainingPage: StudioPage()),
  );
}

/// Presents the workflow for planning and training a text classifier.
class StudioPage extends StatefulWidget {
  /// Creates the classifier training page.
  const StudioPage({super.key});

  /// Creates the state for the training workflow.
  @override
  State<StudioPage> createState() => _StudioPageState();
}

/// Tracks the currently selected training job and its progress.
class _StudioPageState extends State<StudioPage> {
  final _http = HttpClient()..connectionTimeout = const Duration(seconds: 4);
  final _prompt = TextEditingController();
  final _target = TextEditingController(text: '0.80');
  Map<String, dynamic>? _job;
  String? _error;
  bool _busy = false;
  bool _idle = true;
  Timer? _poll;

  /// Sends a JSON request to the local training API.
  Future<Map<String, dynamic>> _request(
    String path, [
    Map<String, dynamic>? body,
  ]) async {
    final request = await _http.openUrl(
      body == null ? 'GET' : 'POST',
      Uri.parse('http://127.0.0.1:8766$path'),
    );
    request.headers.set('X-Model-Studio', 'desktop');
    if (body != null) {
      request.headers.contentType = ContentType.json;
      final bytes = utf8.encode(jsonEncode(body));
      request.contentLength = bytes.length;
      request.add(bytes);
    }
    final response = await request.close().timeout(const Duration(seconds: 8));
    final data = jsonDecode(
      await response.transform(utf8.decoder).join(),
    ) as Map<String, dynamic>;
    if (response.statusCode >= 400) {
      throw FormatException(data['error'].toString());
    }
    return data;
  }

  /// Polls the selected training job until it reaches a terminal state.
  Future<void> _refresh(String id) async {
    try {
      final job = await _request('/jobs/$id');
      if (!mounted) return;
      setState(() => _job = job);
      const active = {
        'planning',
        'queued',
        'waiting_idle',
        'creating_dataset',
        'training',
        'refining',
      };
      if (active.contains(job['status'])) {
        _poll = Timer(const Duration(seconds: 2), () => _refresh(id));
      }
    } catch (error) {
      if (mounted) {
        setState(() => _error = 'Could not read job status. $error');
        _poll = Timer(const Duration(seconds: 3), () => _refresh(id));
      }
    }
  }

  /// Sends a training command and refreshes the returned job.
  Future<void> _submit(String path, Map<String, dynamic> body) async {
    setState(() {
      _error = null;
      _busy = true;
    });
    try {
      final result = await _request(path, body);
      _poll?.cancel();
      await _refresh(result['id'] as String);
    } catch (error) {
      if (mounted) {
        setState(
          () => _error = error is SocketException
              ? 'Start the Python backend, then try again.'
              : error.toString(),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Cancels training polling and releases local controllers.
  @override
  void dispose() {
    _poll?.cancel();
    _http.close(force: true);
    _prompt.dispose();
    _target.dispose();
    super.dispose();
  }

  /// Builds the classifier form, job status, and evaluation metrics.
  @override
  Widget build(BuildContext context) {
    final job = _job;
    final plan = job?['plan'] as Map<String, dynamic>?;
    final metrics = job?['metrics'] as Map<String, dynamic>?;
    final status = job?['status'];
    final canPlan =
        status == null ||
        {'approval', 'failed', 'passed', 'needs_review'}.contains(status);
    const statusNames = {
      'planning': 'Qwen is designing the dataset',
      'approval': 'Review the dataset plan',
      'queued': 'Job queued',
      'waiting_idle': 'Waiting for AC power and 10 minutes of inactivity',
      'creating_dataset': 'Creating and labeling examples',
      'training': 'Training and evaluating classifiers',
      'refining': 'Qwen is generating examples to address validation errors',
      'failed': 'Job failed',
      'passed': 'Model met the score target',
      'needs_review': 'Model needs review',
    };
    return Scaffold(
      backgroundColor: const Color(0xfff5f7f2),
      appBar: AppBar(title: const Text(appName)),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 820),
          child: ListView(
            padding: const EdgeInsets.all(28),
            children: [
              Text(
                'Train a text classifier',
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              const SizedBox(height: 8),
              const Text(
                'Describe the text you want to classify and the categories it should recognize.',
              ),
              const SizedBox(height: 20),
              TextField(
                controller: _prompt,
                minLines: 3,
                maxLines: 6,
                maxLength: 3000,
                decoration: const InputDecoration(
                  border: OutlineInputBorder(),
                  labelText: 'Model goal',
                  hintText: 'Classify support messages as billing, delivery, or returns.',
                ),
              ),
              Align(
                alignment: Alignment.centerLeft,
                child: FilledButton(
                  onPressed: _busy || !canPlan
                      ? null
                      : () => _submit('/jobs', {'prompt': _prompt.text}),
                  child: const Text('Create dataset plan'),
                ),
              ),
              if (_error != null || job?['error'] != null) ...[
                const SizedBox(height: 16),
                Text(
                  _error ?? job!['error'].toString(),
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              if (job != null) ...[
                const SizedBox(height: 24),
                Text(
                  statusNames[status] ?? status.toString(),
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 10),
                if (plan != null)
                  Text('Labels: ${(plan['labels'] as List).join(', ')}'),
                if (status == 'approval' && plan != null) ...[
                  const SizedBox(height: 12),
                  const Text(
                    'Web mode sends the queries below to Brave Search. Qwen labels the returned excerpts locally. Synthetic mode generates examples locally.',
                  ),
                  const SizedBox(height: 8),
                  for (final query in plan['queries'] as List)
                    SelectableText('• $query'),
                  const SizedBox(height: 16),
                  SizedBox(
                    width: 230,
                    child: TextField(
                      controller: _target,
                      keyboardType: const TextInputType.numberWithOptions(
                        decimal: true,
                      ),
                      decoration: const InputDecoration(
                        labelText: 'Target macro F1 (0–1)',
                        border: OutlineInputBorder(),
                      ),
                    ),
                  ),
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    value: _idle,
                    onChanged: _busy
                        ? null
                        : (value) => setState(() => _idle = value),
                    title: const Text(
                      'Wait until this computer is idle and plugged in',
                    ),
                  ),
                  Wrap(
                    spacing: 12,
                    runSpacing: 8,
                    children: [
                      FilledButton(
                        onPressed: _busy
                            ? null
                            : () => _start(job, plan, 'web'),
                        child: const Text('Approve queries and train'),
                      ),
                      OutlinedButton(
                        onPressed: _busy
                            ? null
                            : () => _start(job, plan, 'synthetic'),
                        child: const Text('Generate locally and train'),
                      ),
                    ],
                  ),
                ],
                if (!canPlan) const LinearProgressIndicator(),
                if (metrics != null) ...[
                  Text(metrics['algorithm'].toString()),
                  Text(
                    'Validation macro F1: ${_score(metrics['validation_macro_f1'])}',
                  ),
                  Text(
                    'Test macro F1: ${_score(metrics['test_macro_f1'])} on ${metrics['test_examples']} examples',
                  ),
                  Text(
                    'Target: ${_score(metrics['target_macro_f1'])} · Dataset: ${job['examples']} examples',
                  ),
                  if (job['mode'] == 'synthetic')
                    const Text(
                      'Scores use synthetic examples. Check the model on real data before deployment.',
                    ),
                  const SizedBox(height: 12),
                  const Text('Model, dataset, and evaluation report'),
                  SelectableText(job['output'].toString()),
                ],
              ],
            ],
          ),
        ),
      ),
    );
  }

  /// Formats a training metric for display.
  String _score(dynamic value) => (value as num).toStringAsFixed(3);

  /// Starts the approved plan with the selected dataset source.
  void _start(Map job, Map plan, String mode) {
    final target = double.tryParse(_target.text);
    if (target == null || !target.isFinite || target <= 0 || target > 1) {
      setState(
        () => _error = 'Enter a target score greater than 0 and at most 1.',
      );
      return;
    }
    _submit('/jobs/${job['id']}/start', {
      'mode': mode,
      'target': target,
      'idle': _idle,
      if (mode == 'web') 'approved_queries': plan['queries'],
    });
  }
}
