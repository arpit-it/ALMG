import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';

import 'app_name.dart';

import 'chat.dart';

/// Starts the Flutter desktop application.
void main() => runApp(const ModelStudio());

/// Defines the ALMG theme and launch dashboard.
class ModelStudio extends StatelessWidget {
  /// Creates the root ALMG application.
  const ModelStudio({super.key});

  /// Creates the themed application and its dashboard.
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: appName,
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff315c51)),
      fontFamily: 'Inter',
      useMaterial3: true,
    ),
    home: const DashboardPage(),
  );
}

/// Provides a launch point for the three ALMG workspaces.
class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key});

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  final _client = HttpClient()..connectionTimeout = const Duration(seconds: 4);
  late Future<Map<String, dynamic>> _dashboard = _load();

  Future<Map<String, dynamic>> _load() async {
    final request = await _client.getUrl(
      Uri.parse('http://127.0.0.1:8766/dashboard'),
    );
    request.headers.set('X-Model-Studio', 'desktop');
    final response = await request.close().timeout(const Duration(seconds: 8));
    final data = jsonDecode(
      await response.transform(utf8.decoder).join(),
    ) as Map<String, dynamic>;
    if (response.statusCode != 200) {
      throw const FormatException('Could not load dashboard.');
    }
    return data;
  }

  Future<void> _addProject() async {
    var name = '';
    String? directory;
    final project = await showDialog<Map<String, String>>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, update) => AlertDialog(
          title: const Text('Add Project'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                autofocus: true,
                maxLength: 80,
                decoration: const InputDecoration(labelText: 'Project name'),
                onChanged: (value) => update(() => name = value.trim()),
              ),
              OutlinedButton.icon(
                icon: const Icon(Icons.folder_open),
                label: const Text('Choose folder'),
                onPressed: () async {
                  final selected = await getDirectoryPath();
                  if (context.mounted && selected != null) {
                    update(() => directory = selected);
                  }
                },
              ),
              if (directory != null) SelectableText(directory!),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: name.isEmpty || directory == null
                  ? null
                  : () => Navigator.pop(context, {
                      'name': name,
                      'directory': directory!,
                    }),
              child: const Text('Create project'),
            ),
          ],
        ),
      ),
    );
    if (project == null || !mounted) return;
    try {
      final request = await _client.postUrl(
        Uri.parse('http://127.0.0.1:8766/projects'),
      );
      request.headers.set('X-Model-Studio', 'desktop');
      request.headers.contentType = ContentType.json;
      final bytes = utf8.encode(jsonEncode(project));
      request.contentLength = bytes.length;
      request.add(bytes);
      final response = await request.close().timeout(
        const Duration(seconds: 8),
      );
      final data =
          jsonDecode(await response.transform(utf8.decoder).join()) as Map;
      if (response.statusCode != 201) {
        throw FormatException(
          data['error']?.toString() ?? 'Could not create project.',
        );
      }
      if (!mounted) return;
      setState(() => _dashboard = _load());
      final projectId = data['id'] as String;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('${project['name']} created'),
          action: SnackBarAction(
            label: 'Open Model Training',
            onPressed: () => _open(StudioPage(initialProject: projectId)),
          ),
        ),
      );
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.toString())));
      }
    }
  }

  Future<void> _open(Widget page) async {
    await Navigator.of(context)
        .push(MaterialPageRoute<void>(builder: (_) => page));
    if (mounted) setState(() => _dashboard = _load());
  }

  @override
  void dispose() {
    _client.close(force: true);
    super.dispose();
  }

  Widget _activity() => FutureBuilder<Map<String, dynamic>>(
    future: _dashboard,
    builder: (context, snapshot) {
      if (snapshot.hasError) {
        return const Text(
          'Could not load projects and chats. Check the local backend and refresh.',
        );
      }
      if (!snapshot.hasData) return const LinearProgressIndicator();
      final projects = snapshot.data!['projects'] as List;
      final chats = snapshot.data!['chats'] as List;
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Projects', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          if (projects.isEmpty) const Text('No projects yet.'),
          LayoutBuilder(
            builder: (context, constraints) {
              final columns = constraints.maxWidth >= 620
                  ? 3
                  : constraints.maxWidth >= 380
                  ? 2
                  : 1;
              return GridView.builder(
                shrinkWrap: true,
                primary: false,
                physics: const NeverScrollableScrollPhysics(),
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: columns,
                  mainAxisExtent: 155,
                  crossAxisSpacing: 8,
                  mainAxisSpacing: 8,
                ),
                itemCount: projects.length,
                itemBuilder: (context, index) {
                  final project = projects[index] as Map;
                  final model = project['model'] as Map?;
                  final status = switch (model?['status']) {
                    'passed' => 'Released',
                    'preview_ready' => 'Ready for preview',
                    'approval' ||
                    'image_candidates' ||
                    'dataset_ready' => 'Awaiting approval',
                    'cancelled' => 'Training cancelled',
                    'waiting_idle' => 'Waiting for idle time',
                    'clarification' => 'Waiting for details',
                    'failed' => 'Failed',
                    final String value => value.replaceAll('_', ' '),
                    _ => 'No training sessions',
                  };
                  return Card(
                    clipBehavior: Clip.antiAlias,
                    child: InkWell(
                      onTap: () => _open(
                        StudioPage(initialProject: project['id'] as String),
                      ),
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Icon(Icons.folder_outlined),
                            const SizedBox(height: 4),
                            Text(
                              project['name'] as String,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: Theme.of(context).textTheme.titleMedium,
                            ),
                            if (model != null)
                              Text(
                                model['name'] as String,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                              ),
                            const Spacer(),
                            Text(
                              status,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ],
                        ),
                      ),
                    ),
                  );
                },
              );
            },
          ),
          const SizedBox(height: 20),
          Text('Recent chats', style: Theme.of(context).textTheme.titleLarge),
          if (chats.isEmpty) const Text('No saved chats yet.'),
          for (final chat in chats)
            ListTile(
              leading: const Icon(Icons.chat_bubble_outline),
              title: Text(
                chat['title'] as String,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              subtitle: Text(
                chat['project_name'] as String? ?? 'Personal chats',
              ),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => _open(
                ChatPage(
                  trainingPage: const StudioPage(),
                  modelLibraryPage: const ModelLibraryPage(),
                  initialProject: chat['project_id'] as String?,
                  initialChat: chat['id'] as String,
                ),
              ),
            ),
        ],
      );
    },
  );

  @override
  Widget build(BuildContext context) {
    final destinations = <(String, String, IconData, Widget)>[
      (
        'New Model Training',
        'Start a training conversation in a project.',
        Icons.model_training_outlined,
        const StudioPage(),
      ),
      (
        'Model Library',
        'Open and run a saved candidate or release.',
        Icons.inventory_2_outlined,
        const ModelLibraryPage(),
      ),
      (
        'Chat',
        'Open your conversations, projects, and model settings.',
        Icons.chat_bubble_outline,
        const ChatPage(
          trainingPage: StudioPage(),
          modelLibraryPage: ModelLibraryPage(),
        ),
      ),
    ];
    return Scaffold(
      appBar: AppBar(
        title: const Text('ALMG'),
        actions: [
          TextButton.icon(
            onPressed: _addProject,
            icon: const Icon(Icons.create_new_folder_outlined),
            label: const Text('Add Project'),
          ),
          IconButton(
            tooltip: 'Refresh dashboard',
            icon: const Icon(Icons.refresh),
            onPressed: () => setState(() => _dashboard = _load()),
          ),
        ],
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 760),
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              Text(
                'Dashboard',
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              const SizedBox(height: 20),
              for (final (title, description, icon, destination)
                  in destinations)
                Card(
                  child: ListTile(
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 20,
                      vertical: 10,
                    ),
                    leading: Icon(icon),
                    title: Text(title),
                    subtitle: Text(description),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => _open(destination),
                  ),
                ),
              const SizedBox(height: 24),
              _activity(),
            ],
          ),
        ),
      ),
    );
  }
}

/// Lists local models across training projects.
class ModelLibraryPage extends StatefulWidget {
  const ModelLibraryPage({super.key});

  @override
  State<ModelLibraryPage> createState() => _ModelLibraryPageState();
}

class _ModelLibraryPageState extends State<ModelLibraryPage> {
  final _client = HttpClient()..connectionTimeout = const Duration(seconds: 4);
  late Future<List<dynamic>> _models = _load();
  String _query = '';

  Future<List<dynamic>> _load() async {
    final request = await _client.getUrl(
      Uri.parse('http://127.0.0.1:8766/models'),
    );
    request.headers.set('X-Model-Studio', 'desktop');
    final response = await request.close().timeout(const Duration(seconds: 8));
    final data =
        jsonDecode(await response.transform(utf8.decoder).join()) as Map;
    if (response.statusCode != 200) {
      throw FormatException(
        data['error']?.toString() ?? 'Could not load models.',
      );
    }
    return data['models'] as List;
  }

  @override
  void dispose() {
    _client.close(force: true);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Model Library'),
      actions: [
        IconButton(
          tooltip: 'Refresh models',
          onPressed: () => setState(() => _models = _load()),
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
    body: FutureBuilder<List<dynamic>>(
      future: _models,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return const Center(
            child: Text(
              'Could not load models. Check the local backend and refresh.',
            ),
          );
        }
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        final allModels = snapshot.data!.cast<Map>();
        if (allModels.isEmpty) {
          return const Center(
            child: Text('Trained candidates and releases will appear here.'),
          );
        }
        final query = _query.trim().toLowerCase();
        final models = allModels.where((model) {
          return [
            model['name'],
            model['project'],
          ].any((value) => value.toString().toLowerCase().contains(query));
        }).toList();
        return Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: TextFormField(
                initialValue: _query,
                onChanged: (value) => setState(() => _query = value),
                decoration: const InputDecoration(
                  labelText: 'Search models or projects',
                  prefixIcon: Icon(Icons.search),
                  border: OutlineInputBorder(),
                ),
              ),
            ),
            Expanded(
              child: models.isEmpty
                  ? const Center(child: Text('No matching models.'))
                  : ListView.builder(
                      itemCount: models.length,
                      itemBuilder: (context, index) {
                        final model = models[index];
                        final missing =
                            (model['missing_files'] as List?) ?? const [];
                        final availability = missing.isEmpty
                            ? ''
                            : '\nMissing local files: ${missing.join(', ')}';
                        final created = model['created_at'] as num?;
                        final date = created == null
                            ? ''
                            : ' · ${MaterialLocalizations.of(context).formatCompactDate(DateTime.fromMillisecondsSinceEpoch((created * 1000).round()))}';
                        final recipe = switch (model['recipe']) {
                          'text_to_image' => 'Text to image',
                          _ => 'Text classifier',
                        };
                        return ListTile(
                          leading: const Icon(Icons.memory),
                          title: Text(
                            model['name'] as String,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                          subtitle: Text(
                            "${model['project']} · $recipe · ${model['status'] == 'passed' ? 'Released' : 'Candidate'}$date$availability",
                          ),
                          trailing: const Icon(Icons.chevron_right),
                          onTap: missing.isNotEmpty
                              ? null
                              : () => Navigator.of(context).push(
                                  MaterialPageRoute<void>(
                                    builder: (_) => StudioPage(
                                      initialModel: model['id'] as String,
                                    ),
                                  ),
                                ),
                        );
                      },
                    ),
            ),
          ],
        );
      },
    ),
  );
}

/// Presents the workflow for planning and training a text classifier.
class StudioPage extends StatefulWidget {
  /// Creates the classifier training page.
  const StudioPage({super.key, this.initialModel, this.initialProject});

  final String? initialProject;

  final String? initialModel;

  /// Creates the state for the training workflow.
  @override
  State<StudioPage> createState() => _StudioPageState();
}

/// Tracks the currently selected training job and its progress.
class _StudioPageState extends State<StudioPage> {
  final _http = HttpClient()..connectionTimeout = const Duration(seconds: 4);
  final _prompt = TextEditingController();
  final _target = TextEditingController(text: '0.80');
  final _previewInput = TextEditingController();
  final _conversation = <(String, String)>[];
  final _predictions = <(String, String, String?)>[];

  bool get _imageRecipe => _job?['recipe'] == 'text_to_image';
  Map<String, dynamic>? _job;
  final Set<String> _excludedTextSources = {};
  String? _error;
  bool _busy = false;
  bool _idle = true;
  bool _allowRepair = false;
  Timer? _poll;
  String? _activeJob;

  List<Map<String, dynamic>> _projects = [];
  List<Map<String, dynamic>> _sessions = [];
  String? _project;

  @override
  void initState() {
    super.initState();
    if (widget.initialModel case final String id) {
      _loadModel(id);
    } else {
      _loadProjects();
    }
  }

  Future<void> _loadModel(String id) async {
    try {
      final job = await _request('/jobs/$id');
      if (mounted) _openSession(job);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _loadProjects() async {
    try {
      final response = await _request('/projects');
      if (!mounted) return;
      setState(
        () => _projects = (response['projects'] as List)
            .cast<Map<String, dynamic>>(),
      );
      if (_projects.isNotEmpty) {
        await _selectProject(
          widget.initialProject ?? _projects.first['id'] as String,
        );
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _selectProject(String id) async {
    _resetSession();
    setState(() {
      _project = id;
      _sessions = [];
    });
    await _loadSessions();
  }

  void _resetSession() {
    _poll?.cancel();
    _activeJob = null;
    setState(() {
      _job = null;
      _error = null;
      _conversation.clear();
      _predictions.clear();
      _prompt.clear();
      _previewInput.clear();
      _target.text = '0.80';
      _idle = true;
      _allowRepair = false;
    });
  }

  Future<void> _loadSessions() async {
    final project = _project;
    final path = Uri(
      path: '/jobs',
      queryParameters: {'project_id': project},
    ).toString();
    try {
      final response = await _request(path);
      if (mounted && _project == project) {
        setState(
          () => _sessions = (response['jobs'] as List)
              .cast<Map<String, dynamic>>(),
        );
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  void _openSession(Map<String, dynamic> job) {
    _resetSession();
    setState(() {
      _job = job;
      if (job['target'] case final num target) _target.text = target.toString();
      if (job['idle'] case final bool idle) _idle = idle;
      _allowRepair = job['allow_repair'] == true;
      _conversation.addAll(
        (job['messages'] as List? ?? []).map((text) => ('You', text as String)),
      );
      for (final prediction in job['predictions'] as List? ?? []) {
        _predictions.add(('You', prediction['text'] as String, null));
        _predictions.add((
          'Trained model',
          prediction['label'] as String? ?? '',
          prediction['image'] as String?,
        ));
      }
    });
    _activeJob = job['id'] as String;
    _refresh(_activeJob!);
  }

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
      if (!mounted || _activeJob != id) return;
      setState(() {
        if (_job?['id'] != job['id'] || job['status'] != 'text_candidates') {
          _excludedTextSources.clear();
        }
        _job = job;
      });
      const active = {
        'planning',
        'queued',
        'waiting_idle',
        'searching_images',
        'searching_text',
        'creating_dataset',
        'training',
        'exporting',
      };
      if (active.contains(job['status'])) {
        _poll = Timer(const Duration(seconds: 2), () => _refresh(id));
      }
    } catch (error) {
      if (mounted && _activeJob == id) {
        setState(() => _error = 'Could not read job status. $error');
        _poll = Timer(const Duration(seconds: 3), () => _refresh(id));
      }
    }
  }

  Future<void> _editPlanItems(
    String id,
    List items, {
    bool labels = false,
  }) async {
    final values = items.cast<String>().toList();
    final classifierQueries = !labels && !_imageRecipe;
    if (classifierQueries && values.length < 6) values.add('');
    final itemName = labels ? 'Label' : 'Query';
    final field = labels ? 'labels' : 'queries';
    final edited = await showDialog<List<String>>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(labels ? 'Edit labels' : 'Edit web queries'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (var index = 0; index < values.length; index++)
                TextFormField(
                  initialValue: values[index],
                  autofocus: index == 0,
                  maxLength: 160,
                  decoration: InputDecoration(
                    labelText: '$itemName ${index + 1}',
                    helperText: !labels && !_imageRecipe
                        ? 'Leave blank to remove this query'
                        : null,
                  ),
                  onChanged: (value) => values[index] = value,
                ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(
              context,
              !labels && !_imageRecipe
                  ? values.where((value) => value.trim().isNotEmpty).toList()
                  : values,
            ),
            child: Text('Save $field'),
          ),
        ],
      ),
    );
    if (edited != null && mounted) {
      await _submit('/jobs/$id/edit-$field', {field: edited});
    }
  }

  Future<void> _importDataset(String id) async {
    try {
      final file = await openFile(
        acceptedTypeGroups: [
          const XTypeGroup(label: 'CSV', extensions: ['csv']),
        ],
      );
      if (file == null || !mounted || _activeJob != id) return;
      if (await file.length() > 30000) {
        throw const FormatException('Choose a CSV file up to 30 KB.');
      }
      final String csv;
      try {
        csv = utf8.decode(await file.readAsBytes());
      } on FormatException {
        throw const FormatException('Save the CSV as UTF-8 and try again.');
      }
      if (!mounted || _activeJob != id) return;
      await _submit('/jobs/$id/import-csv', {'csv': csv});
    } catch (error) {
      if (mounted && _activeJob == id) {
        setState(() => _error = error is FormatException
            ? error.message
            : error.toString());
      }
    }
  }

  Future<void> _editDatasetSize(String id, int current) async {
    var input = current.toString();
    final count = await showDialog<int>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Local dataset size'),
        content: TextFormField(
          initialValue: input,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
            labelText: 'Examples per label (10–40)',
          ),
          onChanged: (value) => input = value,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              final value = int.tryParse(input.trim());
              if (value == null || value < 10 || value > 40) return;
              Navigator.pop(context, value);
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (count != null && mounted) {
      await _submit('/jobs/$id/edit-dataset-size', {
        'examples_per_label': count,
      });
    }
  }

  Future<void> _submit(String path, Map<String, dynamic> body) async {
    setState(() {
      _error = null;
      _busy = true;
    });
    try {
      final result = await _request(path, body);
      _poll?.cancel();
      _activeJob = result['id'] as String;
      await _refresh(_activeJob!);
      if (mounted) unawaited(_loadSessions());
    } catch (error) {
      if (mounted) {
        setState(
          () => _error = error is SocketException
              ? 'Start the Python backend, then try again.'
              : error is FormatException
              ? error.message
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
    _previewInput.dispose();
    super.dispose();
  }

  /// Shows the training conversation beside the live model creation panel.
  @override
  Widget build(BuildContext context) {
    if (widget.initialModel != null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Run Model')),
        body: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 760),
            child: _job == null
                ? _error == null
                      ? const CircularProgressIndicator()
                      : SelectableText(_error!)
                : _modelProgress(),
          ),
        ),
      );
    }
    final conversation = _trainingChat();
    final progress = _modelProgress();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Model Training'),
        actions: [
          if (_projects.isNotEmpty)
            DropdownButton<String>(
              value: _project,
              hint: const Text('Project'),
              items: [
                for (final project in _projects)
                  DropdownMenuItem(
                    value: project['id'] as String,
                    child: Text(project['name'] as String),
                  ),
              ],
              onChanged: _busy ? null : (id) => _selectProject(id!),
            ),
          PopupMenuButton<Map<String, dynamic>>(
            tooltip: 'Training conversations',
            enabled: !_busy && _sessions.isNotEmpty,
            icon: const Icon(Icons.history),
            onSelected: _openSession,
            itemBuilder: (_) => [
              for (final session in _sessions)
                PopupMenuItem(
                  value: session,
                  child: Text(
                    (session['messages'] as List).first as String,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
            ],
          ),
          IconButton(
            tooltip: 'New training conversation',
            onPressed: _busy || _project == null ? null : _resetSession,
            icon: const Icon(Icons.edit_square),
          ),
        ],
      ),
      body: LayoutBuilder(
        builder: (context, constraints) {
          if (constraints.maxWidth < 760) {
            return DefaultTabController(
              length: 2,
              child: Column(
                children: [
                  const TabBar(
                    tabs: [
                      Tab(text: 'Conversation'),
                      Tab(text: 'Model creation'),
                    ],
                  ),
                  Expanded(
                    child: TabBarView(children: [conversation, progress]),
                  ),
                ],
              ),
            );
          }
          return Row(
            children: [
              Expanded(flex: 3, child: conversation),
              const VerticalDivider(width: 1),
              Expanded(flex: 2, child: progress),
            ],
          );
        },
      ),
    );
  }

  /// Renders the prompt history and lets the user request a plan or revisions.
  Widget _trainingChat() {
    final status = _job?['status'];
    final canPlan =
        _project != null &&
        !_busy &&
        (status == null ||
            {
              'approval',
              'clarification',
              'preview_ready',
              'failed',
              'passed',
              'needs_review',
            }.contains(status));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              Text(
                'Training conversation',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 12),
              if (_project == null)
                const Text(
                  'Create a project in Chat to begin a training conversation.',
                ),
              if (_job == null)
                const Text(
                  'Describe what the model should do and give an example of its input and output.',
                ),
              for (final (speaker, message) in _conversation)
                _message(speaker, message),
              if (_job?['planner_message'] case final String explanation)
                _message('Qwen', explanation),
              if (_job?['plan'] case final Map plan when !_imageRecipe)
                _message(
                  'Qwen',
                  "Proposed labels: ${(plan['labels'] as List).join(', ')}. Review the dataset proposal in Model creation.",
                ),
              if (_error case final String error)
                Text(
                  error,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(16),
          child: TextField(
            controller: _prompt,
            enabled: canPlan,
            minLines: 1,
            maxLines: 4,
            maxLength: 3000,
            decoration: InputDecoration(
              border: const OutlineInputBorder(),
              hintText: status == 'approval'
                  ? 'Request a revision to the plan'
                  : 'Describe your model goal',
              suffixIcon: IconButton(
                tooltip: 'Send training message',
                onPressed: canPlan ? _sendGoal : null,
                icon: const Icon(Icons.arrow_upward),
              ),
            ),
          ),
        ),
      ],
    );
  }

  /// Builds a single message shared by training and the inference preview.
  Widget _message(String speaker, String text) => Card(
    margin: const EdgeInsets.only(top: 10),
    child: Padding(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(speaker, style: Theme.of(context).textTheme.labelLarge),
          const SizedBox(height: 4),
          if (speaker == 'Qwen')
            MarkdownBody(data: text, selectable: true)
          else
            SelectableText(text),
        ],
      ),
    ),
  );

  /// Turns a training message into a new plan proposal.
  Future<void> _sendGoal() async {
    final text = _prompt.text.trim();
    if (text.length < 5) return;
    final previous =
        {'approval', 'clarification', 'preview_ready'}.contains(_job?['status'])
        ? (_job!['prompt'] as String?)
        : null;
    final goal = previous == null
        ? text
        : '$previous\n\nRequested changes: $text';
    if (goal.length > 3000) {
      setState(
        () =>
            _error = 'The goal and revisions must fit within 3,000 characters.',
      );
      return;
    }
    setState(() {
      _conversation.add(('You', text));
      _predictions.clear();
      _prompt.clear();
    });
    await _submit('/jobs', {
      'project_id': _project,
      'prompt': goal,
      'message': text,
      if (previous != null) 'previous_id': _job?['id'],
    });
  }

  void _showDiscoveryProviders() {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Web discovery providers'),
        content: const SizedBox(
          width: 460,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Available',
                  style: TextStyle(fontWeight: FontWeight.bold),
                ),
                ListTile(
                  title: Text('English Wikipedia'),
                  subtitle: Text('Text classification'),
                ),
                ListTile(
                  title: Text('Wikimedia Commons'),
                  subtitle: Text('Images and captions'),
                ),
                Text('Planned', style: TextStyle(fontWeight: FontWeight.bold)),
                ListTile(
                  title: Text('Library of Congress'),
                  subtitle: Text('Archives and public collections'),
                ),
                ListTile(
                  title: Text('Europe PMC'),
                  subtitle: Text('Research literature'),
                ),
                ListTile(
                  title: Text('Wikidata'),
                  subtitle: Text('Entities and knowledge graphs'),
                ),
                ListTile(
                  title: Text('World Bank Open Data'),
                  subtitle: Text('Development indicators'),
                ),
                ListTile(
                  title: Text('Federal Register'),
                  subtitle: Text('Public notices and regulations'),
                ),
                ListTile(
                  title: Text('SEC EDGAR'),
                  subtitle: Text('Company filings'),
                ),
                ListTile(
                  title: Text('Crossref'),
                  subtitle: Text('Bibliographic metadata'),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }

  /// Shows the current proposal, dataset preview, evaluation, and release gate.
  Widget _modelProgress() {
    final job = _job;
    final webImages = job?['mode'] == 'web_images';
    final id = job?['id'];
    final status = job?['status'];
    final plan = job?['plan'] as Map?;
    final metrics = job?['metrics'] as Map?;
    final states = {
      'planning': 'Qwen is drafting the plan',
      'approval': 'Dataset approval required',
      'clarification': 'Waiting for more details',
      'searching_images': 'Searching for images',
      'searching_text': 'Searching Wikipedia',
      'text_candidates': 'Review Wikipedia sources',
      'image_candidates': 'Image search results',
      'creating_dataset': 'Preparing dataset',
      'cancelled': 'Training cancelled',
      'dataset_ready': 'Training approval required',
      'queued': 'Training queued',
      'waiting_idle': 'Waiting for idle time and AC power',
      'training': 'Training and evaluating the model',
      'preview_ready': 'Ready for inference preview',
      'exporting': 'Exporting approved model',
      'passed': 'Model released',
      'failed': 'Task failed',
      'needs_review': 'Model needs review',
    };
    final activity = (job?['activity'] as List?) ?? const [];
    final working = {
      'planning',
      'creating_dataset',
      'queued',
      'waiting_idle',
      'training',
      'exporting',
    }.contains(status);
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        Text('Model creation', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 12),
        Text(states[status] ?? 'Waiting for a model goal'),
        if (_busy || working) ...[
          const SizedBox(height: 12),
          const LinearProgressIndicator(),
        ],
        if (activity.isNotEmpty) ...[
          const SizedBox(height: 12),
          Semantics(
            liveRegion: working,
            child: Text((activity.last as Map)['message'] as String),
          ),
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: const Text('Activity history'),
            children: [
              for (final entry in activity.reversed)
                ListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: Text(entry['message'] as String),
                  subtitle: Text(
                    MaterialLocalizations.of(context).formatTimeOfDay(
                      TimeOfDay.fromDateTime(
                        DateTime.fromMillisecondsSinceEpoch(
                          ((entry['timestamp'] as num) * 1000).round(),
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ],
        if (job?['error'] case final String error when _error == null)
          SelectableText(error),
        if (plan != null)
          Text(
            _imageRecipe
                ? 'Workflow: Text to image'
                : 'Workflow: Text classification',
          ),
        if (plan != null && !_imageRecipe) ...[
          const SizedBox(height: 16),
          Text('Labels: ${(plan['labels'] as List).join(', ')}'),
        ],
        if (status == 'approval' || status == 'dataset_ready')
          TextField(
            controller: _target,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: InputDecoration(
              labelText: _imageRecipe
                  ? 'Target pixel score (0–1)'
                  : 'Target macro F1 (0–1)',
            ),
          ),
        if (status == 'approval' && plan != null) ...[
          if (!_imageRecipe)
            TextButton.icon(
              onPressed: _busy
                  ? null
                  : () => _editPlanItems(
                      id as String,
                      plan['labels'] as List,
                      labels: true,
                    ),
              icon: const Icon(Icons.edit_outlined),
              label: const Text('Edit labels'),
            ),
          const SizedBox(height: 12),
          if (_imageRecipe)
            const Text(
              'ALMG will render 45 local examples of circles, squares, and triangles in five colors. Some color and shape combinations are held out for evaluation.',
            )
          else ...[
            TextButton.icon(
              onPressed: _busy
                  ? null
                  : () => _editDatasetSize(
                      id as String,
                      plan['synthetic_examples_per_label'] as int? ?? 40,
                    ),
              icon: const Icon(Icons.edit_outlined),
              label: Text(
                'Local examples per label: ${plan['synthetic_examples_per_label'] ?? 40}',
              ),
            ),
            if ((plan['queries'] as List).isNotEmpty) ...[
              const ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text('English Wikipedia'),
                subtitle: Text('en.wikipedia.org · Text classification'),
              ),
              const Text(
                'Approving these queries sends them to this provider for up to 20 results per query. '
                'Review the excerpts and source URLs before approving them for the dataset.',
              ),
            ],
            for (final query in plan['queries'] as List)
              SelectableText('• $query'),
          ],
          TextButton(
            onPressed: _showDiscoveryProviders,
            child: const Text('Browse discovery providers'),
          ),
          if (_imageRecipe && (plan['queries'] as List).isNotEmpty) ...[
            const ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text('Wikimedia Commons'),
              subtitle: Text('commons.wikimedia.org · Images and captions'),
            ),
            const Text(
              'Approving these queries sends them to this provider for up to 20 results.',
            ),
            for (final query in plan['queries'] as List)
              SelectableText(query as String),
            OutlinedButton(
              onPressed: _busy
                  ? null
                  : () => _submit('/jobs/$id/search-images', {
                      'approved_queries': plan['queries'],
                    }),
              child: const Text('Approve image search'),
            ),
          ],
          const SizedBox(height: 12),
          if (!_imageRecipe || (plan['queries'] as List).isNotEmpty)
            TextButton.icon(
              onPressed: _busy
                  ? null
                  : () => _editPlanItems(id as String, plan['queries'] as List),
              icon: const Icon(Icons.edit_outlined),
              label: const Text('Edit web queries'),
            ),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              FilledButton(
                onPressed: _busy
                    ? null
                    : () => _submit('/jobs/$id/prepare', {'mode': 'synthetic'}),
                child: const Text('Approve local dataset'),
              ),
              if (!_imageRecipe)
                OutlinedButton(
                  onPressed: _busy ? null : () => _importDataset(id as String),
                  child: const Text('Import labeled CSV'),
                ),
              if (!_imageRecipe && (plan['queries'] as List).isNotEmpty)
                OutlinedButton(
                  onPressed: _busy
                      ? null
                      : () => _submit('/jobs/$id/prepare', {
                          'mode': 'web',
                          'approved_queries': plan['queries'],
                        }),
                  child: const Text('Approve web queries'),
                ),
            ],
          ),
        ],
        if (status == 'text_candidates') ...[
          TextButton(
            onPressed: _busy
                ? null
                : () => _editPlanItems(id as String, plan!['queries'] as List),
            child: const Text('Edit web queries'),
          ),
          for (final candidate in job!['text_candidates'] as List)
            ListTile(
              title: SelectableText(candidate['text'] as String),
              subtitle: SelectableText(
                "Approved query: ${candidate['approved_query']}\n"
                "${candidate['source']}",
              ),
              trailing: Checkbox(
                value: !_excludedTextSources.contains(candidate['source']),
                onChanged: _busy
                    ? null
                    : (checked) => setState(() {
                        final source = candidate['source'] as String;
                        if (checked == true) {
                          _excludedTextSources.remove(source);
                        } else {
                          _excludedTextSources.add(source);
                        }
                      }),
                semanticLabel: "Include ${candidate['source']}",
              ),
            ),
          FilledButton(
            onPressed: _busy ||
                    (job['text_candidates'] as List).every(
                      (candidate) =>
                          _excludedTextSources.contains(candidate['source']),
                    )
                ? null
                : () => _submit('/jobs/$id/use-text-excerpts', {
                    'approved_urls': [
                      for (final candidate in job['text_candidates'] as List)
                        if (!_excludedTextSources.contains(candidate['source']))
                          candidate['source'],
                    ].toSet().toList(),
                  }),
            child: const Text('Approve excerpts from selected sources'),
          ),
        ],
        if (status == 'image_candidates') ...[
          if ((job!['image_candidates'] as List).isEmpty)
            const Text(
              'No supported image files found. Try a new training task.',
            ),
          for (final candidate in job['image_candidates'] as List)
            ListTile(
              title: Text(candidate['title'] as String),
              subtitle: SelectableText(
                "${candidate['url']}\n${candidate['license'] ?? 'License unavailable'}",
              ),
            ),
          if ((job['image_candidates'] as List).isNotEmpty)
            FilledButton(
              onPressed: _busy
                  ? null
                  : () => _submit('/jobs/$id/download-images', {
                      'approved_urls': [
                        for (final candidate in job['image_candidates'] as List)
                          candidate['url'],
                      ],
                    }),
              child: const Text('Approve listed image downloads (8 MiB each)'),
            ),
        ],
        if (job?['examples'] case final int count) ...[
          const SizedBox(height: 16),
          Text('Dataset · $count examples'),
        ],
        if (status == 'queued' ||
            status == 'waiting_idle' ||
            status == 'training')
          OutlinedButton(
            onPressed: _busy ? null : () => _submit('/jobs/$id/cancel', {}),
            child: Text(
              status == 'training'
                  ? 'Cancel training'
                  : 'Cancel queued training',
            ),
          ),
        if (status == 'dataset_ready') ...[
          if (!_imageRecipe)
            OutlinedButton(
              onPressed: _busy ? null : () => _importDataset(id as String),
              child: const Text('Replace dataset with CSV'),
            ),
          if (job?['usable_counts'] case final Map counts)
            for (final entry in counts.entries)
              if ((entry.value as int) < 8)
                Text(
                  '${entry.key} has ${entry.value} usable examples. Training needs 8 per label.',
                ),
          if ((job?['symbol_only_rows'] as int? ?? 0) > 0)
            Text('Rows without letters or numbers: ${job?['symbol_only_rows']}'),
          if ((job?['duplicate_rows'] as int? ?? 0) > 0)
            Text(
              'Repeated rows: ${job?['duplicate_rows']}. '
              'Training and evaluation skip every copy of the repeated text.',
            ),
          if ((job?['near_duplicate_groups'] as int? ?? 0) > 0)
            Text(
              'Near-duplicate groups (Unicode and punctuation variants): ${job?['near_duplicate_groups']}',
            ),
          if ((job?['conflicting_texts'] as int? ?? 0) > 0)
            Text(
              'Groups with conflicting labels: ${job?['conflicting_texts']}. '
              'Training and evaluation skip these examples.',
            ),
          if (job?['label_counts'] case final Map counts)
            for (final entry in counts.entries.where(
              (entry) => entry.value == 0,
            ))
              Text(
                'No dataset examples for ${entry.key}.',
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
          if (job?['label_counts'] case final Map counts
              when counts.isNotEmpty) ...[
            Text(
              'Class balance',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            for (final entry in counts.entries)
              Text('${entry.key}: ${entry.value}'),
          ],
          for (final row in job!['preview'] as List)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(
                row['label_conflict'] == true
                    ? "${row['label']} · Conflicting label"
                    : row['label'] as String,
              ),
              subtitle: Text(
                row['image'] == null
                    ? [
                        row['text'] as String,
                        if (row['no_words'] == true)
                          'No letters or numbers. Check the label.',
                        if (row['duplicate_kind'] == 'exact') 'Duplicate text',
                        if (row['duplicate_kind'] == 'near') 'Near-duplicate text',
                        if (row['csv_end_line'] case final int line)
                          'CSV record ends on line $line',
                        if (row['csv_group'] case final String group)
                          'Source group: $group',
                        if (row['approved_query'] case final String query) ...[
                          'Approved query: $query',
                          'Source: ${row['source']}',
                        ],
                      ].join('\n')
                    : "${row['text']}\n${row['source']}\n${row['license'] ?? 'License unavailable'}",
              ),
              leading: row['image'] == null
                  ? null
                  : Image.memory(
                      base64Decode(row['image'] as String),
                      width: 48,
                      height: 48,
                    ),
            ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            value: _idle,
            onChanged: _busy ? null : (value) => setState(() => _idle = value),
            title: const Text('Wait for idle time and AC power'),
          ),
          if (!_imageRecipe)
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              value: _allowRepair,
              onChanged: _busy
                  ? null
                  : (value) => setState(() => _allowRepair = value),
              title: const Text('Allow one retry with local examples'),
              subtitle: const Text(
                'Qwen uses validation mistakes to generate additional training examples.',
              ),
            ),
          FilledButton(
            onPressed:
                _busy ||
                    ((job['label_counts'] as Map?)?.containsValue(0) ?? false)
                ? null
                : () => _approveTraining(id as String),
            child: const Text('Approve training and evaluation'),
          ),
        ],
        if (metrics != null) ...[
          const SizedBox(height: 16),
          Text(metrics['algorithm'].toString()),
          if (webImages) ...[
            Text(
              'Held-out pixel similarity: ${_score(metrics['held_out_pixel_similarity'])}',
            ),
            const Text(
              'Pixel similarity measures color differences. Review prompt relevance in preview.',
            ),
            for (final prompt in metrics['test_prompts'] as List)
              SelectableText(prompt as String),
          ] else if (_imageRecipe) ...[
            Text(
              'Held-out pixel accuracy: ${_score(metrics['held_out_pixel_accuracy'])}',
            ),
            Text('Target: ${_score(metrics['target_pixel_accuracy'])}'),
          ] else ...[
            Text(
              'Validation macro F1: ${_score(metrics['validation_macro_f1'])}',
            ),
            Text('Held-out macro F1: ${_score(metrics['test_macro_f1'])}'),
            Text('Target: ${_score(metrics['target_macro_f1'])}'),
          ],
        ],
        if (status == 'preview_ready' || status == 'passed') ...[
          const SizedBox(height: 20),
          Text('Model preview', style: Theme.of(context).textTheme.titleMedium),
          Text('Candidate ${(id as String).substring(0, 8)}'),
          Text(
            webImages
                ? 'Try a held-out caption listed above. This experimental model generates 48 × 48 images.'
                : _imageRecipe
                ? 'Try a red circle and a blue square. Use up to three circles, squares, or triangles in red, green, blue, yellow, or purple.'
                : 'Enter representative examples and review the predicted labels.',
          ),
          for (final (speaker, text, image) in _predictions)
            if (image == null)
              _message(speaker, text)
            else
              Align(
                alignment: Alignment.centerLeft,
                child: Image.memory(
                  base64Decode(image),
                  width: 192,
                  height: 192,
                  filterQuality: FilterQuality.none,
                  semanticLabel: 'Generated image',
                ),
              ),
          const SizedBox(height: 12),
          TextField(
            controller: _previewInput,
            readOnly: _busy,
            onSubmitted: (_) => _predict(id),
            decoration: InputDecoration(
              border: const OutlineInputBorder(),
              hintText: 'Enter an example',
              suffixIcon: IconButton(
                tooltip: 'Send to trained model',
                onPressed: _busy ? null : () => _predict(id),
                icon: const Icon(Icons.arrow_upward),
              ),
            ),
          ),
          const SizedBox(height: 12),
          if (metrics?['passed'] != true)
            const Text(
              'The model must meet the evaluation target before release.',
            ),
          if (status == 'preview_ready' && !webImages)
            FilledButton(
              onPressed:
                  _busy || _predictions.isEmpty || metrics?['passed'] != true
                  ? null
                  : () => _submit('/jobs/$id/release', {}),
              child: const Text('Approve predictions and release'),
            ),
        ],
        if (status == 'preview_ready' &&
            job?['candidate_directory'] is String) ...[
          const SizedBox(height: 16),
          const Text('Candidate model and dataset folder'),
          SelectableText(job!['candidate_directory'] as String),
        ],
        if (job?['output'] case final String output) ...[
          const SizedBox(height: 16),
          const Text('Model, dataset, and evaluation report'),
          SelectableText(output),
          OutlinedButton.icon(
            onPressed: () {
              final filename = _imageRecipe ? 'model.json' : 'model.joblib';
              Clipboard.setData(ClipboardData(text: '$output/$filename'));
              ScaffoldMessenger.of(
                context,
              ).showSnackBar(SnackBar(content: Text('$filename path copied')));
            },
            icon: const Icon(Icons.copy_outlined),
            label: Text(
              _imageRecipe ? 'Copy JSON model path' : 'Copy Joblib model path',
            ),
          ),
        ],
      ],
    );
  }

  /// Formats a training metric for display.
  String _score(dynamic value) => (value as num).toStringAsFixed(3);

  /// Starts training on the approved dataset.
  void _approveTraining(String id) {
    final target = double.tryParse(_target.text);
    if (target == null || !target.isFinite || target <= 0 || target > 1) {
      setState(
        () => _error = 'Enter a target score greater than 0 and at most 1.',
      );
      return;
    }
    _submit('/jobs/$id/start', {
      'target': target,
      'idle': _idle,
      'allow_repair': _allowRepair,
    });
  }

  /// Sends one example to the trained candidate and adds its label to the preview.
  Future<void> _predict(String id) async {
    final text = _previewInput.text.trim();
    if (_busy || text.isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await _request('/jobs/$id/preview', {'text': text});
      if (!mounted) return;
      setState(() {
        _predictions.addAll([
          ('You', text, null),
          (
            'Trained model',
            result['label'] as String? ?? '',
            result['image'] as String?,
          ),
        ]);
        _previewInput.clear();
      });
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }
}
