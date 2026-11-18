import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';

import 'app_name.dart';
import 'backend_address.dart';

import 'chat.dart';
import 'catalog_selection.dart';
import 'project_settings.dart';

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
      Uri.parse('http://127.0.0.1:$backendPort/dashboard'),
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
        Uri.parse('http://127.0.0.1:$backendPort/projects'),
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
      Uri.parse('http://127.0.0.1:$backendPort/models'),
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
  final Set<String> _excludedCatalogSources = {};
  final Set<String> _excludedPublications = {};
  final Set<String> _excludedEntities = {};
  final Set<String> _excludedImageSources = {};
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
      Uri.parse('http://127.0.0.1:$backendPort$path'),
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
        if (_job?['id'] != job['id'] || job['status'] != 'image_candidates') {
          _excludedImageSources.clear();
        }
        if (_job?['id'] != job['id'] ||
            !{'catalog_candidates', 'reviewing_catalog_item'}.contains(job['status'])) {
          _excludedCatalogSources.clear();
        }
        if (_job?['id'] != job['id'] ||
            !{'publication_candidates', 'reviewing_publication'}.contains(job['status'])) {
          _excludedPublications.clear();
        }
        if (_job?['id'] != job['id'] || job['status'] != 'entity_candidates') {
          _excludedEntities.clear();
        }
        _job = job;
      });
      const active = {
        'planning',
        'queued',
        'waiting_idle',
        'searching_images',
        'searching_text',
        'searching_catalog',
        'searching_publications',
        'searching_entities',
        'loading_indicators',
        'reviewing_publication',
        'reviewing_catalog_item',
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
              value: _projects.any((project) => project['id'] == _project)
                  ? _project
                  : null,
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

  Future<void> _approveCatalogReuse(String id, Map record, {String action = 'approve-catalog-reuse'}) async {
    var basis = '';
    final approved = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Approve item reuse'),
        content: SizedBox(
          width: 460,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SelectableText(record['source'] as String),
              const Text('Confirm you have permission to use this item for the project dataset. Record the license, permission, or other basis you reviewed.'),
              TextField(
                autofocus: true,
                minLines: 2,
                maxLines: 4,
                maxLength: 2000,
                decoration: const InputDecoration(labelText: 'Basis for reuse permission'),
                onChanged: (value) => basis = value,
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Confirm reuse permission'),
          ),
        ],
      ),
    );
    if (approved == true && mounted) {
      await _submit('/jobs/$id/$action', {
        'approved_url': record['source'],
        'permission_basis': basis,
        'confirmed': true,
      });
    }
  }

  String _datasetSourceLabel(Map row, String source) {
    final provider = row['provider'];
    if (provider == 'wikipedia' ||
        (provider == null && source.startsWith('https://en.wikipedia.org/wiki/'))) {
      return 'English Wikipedia: $source';
    }
    if (provider == 'loc') return 'Library of Congress: $source';
    if (provider == 'europe_pmc') return 'Europe PMC: $source';
    if (provider == 'wikidata') return 'Wikidata: $source';
    if (provider == 'commons' ||
        (provider == null && source.startsWith('https://upload.wikimedia.org/'))) {
      return 'Wikimedia Commons: $source';
    }
    return source;
  }

  String _commonsFilePage(String title) =>
      'File page: https://commons.wikimedia.org/wiki/File:${Uri.encodeComponent(title)}';

  Future<void> _showDiscoveryProviders(bool hasQueries) async {
    final projectId = _project;
    final website = _projects
        .where((project) => project['id'] == projectId)
        .firstOrNull?['source_website'] as String? ?? '';
    final editWebsite = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Web discovery providers'),
        content: SizedBox(
          width: 460,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Available',
                  style: TextStyle(fontWeight: FontWeight.bold),
                ),
                ListTile(
                  title: const Text('English Wikipedia'),
                  trailing: hasQueries && !_imageRecipe ? const Text('Current plan') : null,
                  subtitle: const Text('en.wikipedia.org · Text classification'),
                ),
                ListTile(
                  title: const Text('Wikimedia Commons'),
                  trailing: hasQueries && _imageRecipe ? const Text('Current plan') : null,
                  subtitle: const Text('commons.wikimedia.org · Images and captions'),
                ),
                if (projectId != null) ...[
                  const Text(
                    'Project website',
                    style: TextStyle(fontWeight: FontWeight.bold),
                  ),
                  if (website.isEmpty)
                    const ListTile(title: Text('No website added'))
                  else
                    ListTile(
                      title: SelectableText(website),
                      subtitle: const Text('Discovery unavailable'),
                    ),
                ],
                const ListTile(
                  title: Text('Library of Congress'),
                  subtitle: Text('www.loc.gov · Catalog preview for text classification'),
                ),
                const ListTile(
                  title: Text('Europe PMC'),
                  subtitle: Text('www.ebi.ac.uk · Publication preview for text classification'),
                ),
                const ListTile(
                  title: Text('Wikidata'),
                  subtitle: Text('www.wikidata.org · Entity preview for text classification'),
                ),
                const ListTile(
                  title: Text('World Bank Open Data'),
                  subtitle: Text('api.worldbank.org · Indicator catalog preview'),
                ),
                const Text('Planned', style: TextStyle(fontWeight: FontWeight.bold)),
                const Text('These providers cannot be used for discovery yet.'),
                const ListTile(
                  title: Text('Federal Register'),
                  subtitle: Text('federalregister.gov · Public notices and regulations'),
                ),
                const ListTile(
                  title: Text('SEC EDGAR'),
                  subtitle: Text('sec.gov · Company filings'),
                ),
                const ListTile(
                  title: Text('Crossref'),
                  subtitle: Text('crossref.org · Bibliographic metadata'),
                ),
              ],
            ),
          ),
        ),
        actions: [
          if (projectId != null)
            TextButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: Text(website.isEmpty ? 'Add project website' : 'Edit project website'),
            ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Close'),
          ),
        ],
      ),
    );
    if (!mounted || editWebsite != true || projectId == null) return;
    try {
      final path = '/projects/$projectId';
      final project = await _request(path);
      if (!mounted) return;
      final saved = await showDialog<bool>(
        context: context,
        builder: (_) => ProjectSettings(
          project: project,
          request: (path, {body}) =>
              _request(path, body as Map<String, dynamic>?),
        ),
      );
      if (!mounted) return;
      if (saved == true) {
        final updated = await _request(path);
        if (!mounted) return;
        setState(() {
          _projects = [
            for (final item in _projects)
              if (item['id'] == projectId) updated else item,
          ];
        });
      }
      if (_project == projectId) await _showDiscoveryProviders(hasQueries);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  /// Shows the current proposal, dataset preview, evaluation, and release gate.
  Widget _modelProgress() {
    final job = _job;
    final webImages = job?['mode'] == 'web_images';
    final id = job?['id'];
    final status = job?['status'];
    final plan = job?['plan'] as Map?;
    final metrics = job?['metrics'] as Map?;
    final imageCandidates = job?['image_candidates'] as List? ?? const [];
    final selectedImageUrls = [
      for (final candidate in imageCandidates)
        if (!_excludedImageSources.contains(candidate['url'])) candidate['url'],
    ];
    final textCandidates = job?['text_candidates'] as List? ?? const [];
    final selectedTextUrls = {
      for (final candidate in textCandidates)
        if (!_excludedTextSources.contains(candidate['source']))
          candidate['source'] as String,
    };
    final catalogRecords = job?['catalog_candidates'] as List? ?? const [];
    final selectedCatalogUrls = selectedCatalogSources(catalogRecords, _excludedCatalogSources);
    final publicationRecords = job?['publication_candidates'] as List? ?? const [];
    final selectedPublicationUrls = [
      for (final record in publicationRecords)
        if (collectablePublication(record as Map) && !_excludedPublications.contains(record['source']))
          record['source'] as String,
    ];
    final entityRecords = job?['entity_candidates'] as List? ?? const [];
    final selectedEntityUrls = [
      for (final record in entityRecords)
        if (collectableEntity(record as Map) && !_excludedEntities.contains(record['source']))
          record['source'] as String,
    ];
    final indicatorPage = job?['indicator_page'] as int? ?? 1;
    final indicatorPages = job?['indicator_pages'] as int? ?? indicatorPage;
    final states = {
      'planning': 'Qwen is drafting the plan',
      'approval': 'Dataset approval required',
      'clarification': 'Waiting for more details',
      'searching_images': 'Searching for images',
      'searching_text': 'Searching Wikipedia',
      'searching_catalog': 'Searching the Library of Congress',
      'searching_publications': 'Searching Europe PMC',
      'searching_entities': 'Searching Wikidata',
      'loading_indicators': 'Loading World Bank indicator catalog',
      'indicator_candidates': 'Review World Bank indicators',
      'entity_candidates': 'Review Wikidata entities',
      'publication_candidates': 'Review Europe PMC publications',
      'reviewing_publication': 'Loading publication abstract metadata',
      'catalog_candidates': 'Review Library of Congress records',
      'reviewing_catalog_item': 'Loading catalog item advisories',
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
    final searchLimit = job?['search_result_limit'] as int? ?? 20;
    final downloadLimit = job?['image_download_limit_mib'] as int? ?? 8;
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
              Text(
                'Approving these queries sends them to Wikipedia for up to '
                '$searchLimit results per query and ${(plan['queries'] as List).length * searchLimit} total. '
                'Review the excerpts and source URLs before approving them for the dataset.',
              ),
            ],
            for (final query in plan['queries'] as List)
              SelectableText('• $query'),
          ],
          TextButton(
            onPressed: () =>
                _showDiscoveryProviders((plan['queries'] as List).isNotEmpty),
            child: const Text('Browse discovery providers'),
          ),
          if (_imageRecipe && (plan['queries'] as List).isNotEmpty) ...[
            const ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text('Wikimedia Commons'),
              subtitle: Text('commons.wikimedia.org · Images and captions'),
            ),
            Text(
              'Approving this query sends it to Wikimedia Commons for up to $searchLimit results.',
            ),
            for (final query in plan['queries'] as List)
              SelectableText(query as String),
            OutlinedButton(
              onPressed: _busy
                  ? null
                  : () => _submit('/jobs/$id/search-images', {
                      'approved_provider': 'commons',
                      'approved_result_limit': searchLimit,
                      'approved_queries': plan['queries'],
                    }),
              child: const Text('Approve Wikimedia Commons search'),
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
                          'approved_provider': 'wikipedia',
                          'approved_result_limit': searchLimit,
                          'approved_queries': plan['queries'],
                        }),
                  child: const Text('Approve Wikipedia search'),
                ),
            ],
          ),
        ],
        if (status == 'approval' && !_imageRecipe &&
            plan != null && (plan['queries'] as List).isNotEmpty) ...[
          Text(
            'Library of Congress catalog preview · www.loc.gov. '
            'Sends the listed queries for up to $searchLimit records per query and 40 total.',
          ),
          for (final query in plan['queries'] as List)
            SelectableText('• $query'),
          OutlinedButton(
            onPressed: _busy ? null : () => _submit('/jobs/$id/search-catalog', {
              'approved_provider': 'loc',
              'approved_queries': plan['queries'],
              'approved_total_limit': 40,
              'approved_result_limit': searchLimit,
            }),
            child: const Text('Approve Library of Congress search'),
          ),
        ],
        if (status == 'approval' && !_imageRecipe &&
            plan != null && (plan['queries'] as List).isNotEmpty) ...[
          const Text('Europe PMC publication preview · www.ebi.ac.uk. '
              'Sends the listed queries for up to 20 records per query and 40 total.'),
          for (final query in plan['queries'] as List)
            SelectableText('• $query'),
          OutlinedButton(
            onPressed: _busy ? null : () => _submit('/jobs/$id/search-publications', {
              'approved_provider': 'europe_pmc',
              'approved_queries': plan['queries'],
              'approved_total_limit': 40,
              'approved_result_limit': 20,
            }),
            child: const Text('Approve Europe PMC search'),
          ),
        ],
        if (status == 'approval' && !_imageRecipe &&
            plan != null && (plan['queries'] as List).isNotEmpty) ...[
          const Text('Wikidata entity preview · www.wikidata.org. '
              'Sends the listed queries in English for up to 20 items per query and 40 total.'),
          for (final query in plan['queries'] as List) SelectableText('• $query'),
          OutlinedButton(
            onPressed: _busy ? null : () => _submit('/jobs/$id/search-entities', {
              'approved_provider': 'wikidata', 'approved_queries': plan['queries'],
              'approved_result_limit': 20, 'approved_total_limit': 40,
            }),
            child: const Text('Approve Wikidata search'),
          ),
        ],
        if (status == 'approval' && !_imageRecipe) ...[
          const Text('World Bank indicator catalog preview · api.worldbank.org. '
              'Loads the first catalog page, up to 20 indicators, unfiltered by model queries. Country/year observations are not loaded.'),
          OutlinedButton(
            onPressed: _busy ? null : () => _submit('/jobs/$id/load-indicators', {
              'approved_provider': 'world_bank', 'approved_scope': 'indicator_catalog',
              'approved_page': 1, 'approved_result_limit': 20,
            }),
            child: const Text('Approve World Bank catalog preview'),
          ),
        ],
        if (status == 'indicator_candidates') ...[
          Text('World Bank catalog page $indicatorPage of $indicatorPages · up to 20 indicators. '
              'Reuse rights are unverified. Observation and dataset collection are not available yet.'),
          for (final record in job?['indicator_candidates'] as List? ?? const [])
            ListTile(
              title: Text('${record['title']} (${record['indicator_id']})'),
              subtitle: SelectableText('${record['description']}\nSource ${record['source_id']}: ${record['source_name']}\n${record['organization']}\n${record['source']}'),
            ),
          if (indicatorPage < indicatorPages) ...[
            Text('Loads catalog page ${indicatorPage + 1} from api.worldbank.org, up to 20 indicators. Replaces this preview.'),
            OutlinedButton(
              onPressed: _busy ? null : () => _submit('/jobs/$id/next-indicators', {
                'approved_provider': 'world_bank', 'approved_scope': 'indicator_catalog',
                'approved_page': indicatorPage + 1, 'approved_result_limit': 20,
              }),
              child: Text('Approve loading catalog page ${indicatorPage + 1}'),
            ),
          ],
          TextButton(
            onPressed: _busy ? null : () => _submit('/jobs/$id/close-indicators', {}),
            child: const Text('Return to dataset approval'),
          ),
        ],
        if (status == 'entity_candidates') ...[
          const Text('Review entity labels, descriptions and source URLs. Approve reuse before collecting selected descriptions for text classification.'),
          const Text('Wikidata structured entity data is supplied under CC0. Review the source and project use before recording permission.'),
          const SelectableText('Terms source: https://www.wikidata.org/wiki/Wikidata:Copyright'),
          for (final record in job?['entity_candidates'] as List? ?? const [])
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ListTile(
                  title: Text('${record['title']} (${record['entity_id']})'),
                  subtitle: SelectableText('${record['description']}\n${record['source']}\nApproved query: ${record['approved_query']}'),
                  trailing: collectableEntity(record as Map) ? Checkbox(
                    value: !_excludedEntities.contains(record['source']),
                    semanticLabel: "Include entity description: ${record['title']}",
                    onChanged: _busy ? null : (checked) => setState(() {
                      final source = record['source'] as String;
                      if (checked == true) { _excludedEntities.remove(source); }
                      else { _excludedEntities.add(source); }
                    }),
                  ) : null,
                ),
                if (record['reuse_approval'] case final Map approval)
                  SelectableText('User reuse approval: ${approval['permission_basis']}')
                else
                  TextButton(
                    onPressed: _busy ? null : () => _approveCatalogReuse(id as String, record,
                        action: 'approve-entity-reuse'),
                    child: const Text('Record entity reuse approval'),
                  ),
              ],
            ),
          if (entityRecords.any((record) => collectableEntity(record as Map)))
            OutlinedButton(
              onPressed: _busy || selectedEntityUrls.isEmpty ? null
                  : () => _submit('/jobs/$id/use-entity-descriptions', {'approved_urls': selectedEntityUrls}),
              child: Text('Approve entity description collection (${selectedEntityUrls.length} selected)'),
            ),
          TextButton(
            onPressed: _busy ? null : () => _submit('/jobs/$id/close-entities', {}),
            child: const Text('Return to dataset approval'),
          ),
        ],
        if (status == 'publication_candidates') ...[
          const Text('Review publication metadata and record permission for each abstract. '
              'Only selected, reuse-approved abstracts can enter the dataset. Full-text loading is not available yet.'),
          for (final record in job?['publication_candidates'] as List? ?? const [])
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ListTile(
                  title: Text(record['title'] as String),
                  subtitle: SelectableText('${record['source']}\nApproved query: ${record['approved_query']}'),
                  trailing: collectablePublication(record as Map) ? Checkbox(
                    value: !_excludedPublications.contains(record['source']),
                    semanticLabel: "Include abstract: ${record['title']}",
                    onChanged: _busy ? null : (checked) => setState(() {
                      final source = record['source'] as String;
                      if (checked == true) { _excludedPublications.remove(source); }
                      else { _excludedPublications.add(source); }
                    }),
                  ) : null,
                ),
                if (record['abstract_reviewed'] == true)
                  SelectableText((record['abstract'] as String).isEmpty
                      ? 'No abstract was supplied for this publication.'
                      : 'Abstract: ${record['abstract']}'),
                if (record['reuse_approval'] case final Map approval)
                  SelectableText('User reuse approval: ${approval['permission_basis']}\nReviewed abstract SHA-256: ${approval['abstract_sha256']}')
                else if (record['abstract_reviewed'] == true && (record['abstract'] as String).isNotEmpty)
                  TextButton(
                    onPressed: _busy ? null : () => _approveCatalogReuse(id as String, record,
                        action: 'approve-publication-reuse'),
                    child: const Text('Record abstract reuse approval'),
                  ),
                const Text('Loads abstract metadata from www.ebi.ac.uk for this publication. Loading clears earlier reuse approval.'),
                OutlinedButton(
                  onPressed: _busy ? null : () => _submit('/jobs/$id/review-publication', {
                    'approved_url': record['source'],
                  }),
                  child: const Text('Approve loading abstract metadata'),
                ),
              ],
            ),
          if (publicationRecords.any((record) => collectablePublication(record as Map)))
            OutlinedButton(
              onPressed: _busy || selectedPublicationUrls.isEmpty ? null
                  : () => _submit('/jobs/$id/use-publication-abstracts', {
                      'approved_urls': selectedPublicationUrls,
                    }),
              child: Text('Approve abstract collection (${selectedPublicationUrls.length} selected)'),
            ),
          TextButton(
            onPressed: _busy ? null : () => _submit('/jobs/$id/close-publications', {}),
            child: const Text('Return to dataset approval'),
          ),
        ],
        if (status == 'catalog_candidates') ...[
          const Text('Review the item advisories and record permission before dataset collection.'),
          for (final record in job?['catalog_candidates'] as List? ?? const [])
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ListTile(
                  title: Text(record['title'] as String),
                  subtitle: SelectableText([
                    record['source'],
                    if (record['approved_query'] case final String query)
                      'Approved catalog query: $query',
                  ].join('\n')),
                  trailing: collectableCatalogRecord(record as Map)
                      ? Checkbox(
                          value: !_excludedCatalogSources.contains(record['source']),
                          semanticLabel: "Include catalog description: ${record['title']}",
                          onChanged: _busy ? null : (checked) => setState(() {
                            final source = record['source'] as String;
                            if (checked == true) {
                              _excludedCatalogSources.remove(source);
                            } else {
                              _excludedCatalogSources.add(source);
                            }
                          }),
                        )
                      : null,
                ),
                if (record['metadata_reviewed'] == true) ...[
                  if (record['description'] case final String text when text.isNotEmpty)
                    SelectableText('Catalog description: $text'),
                  if ((record['description'] as String? ?? '').length < 40)
                    const Text(
                      'This item has no collectable catalog description. '
                      'Dataset collection needs at least 40 characters. '
                      'Review another item or return to dataset approval.',
                    ),
                  if ((record['advisories'] as Map).isEmpty)
                    const Text('No rights or access advisories were supplied for this item.'),
                  for (final entry in (record['advisories'] as Map).entries)
                    SelectableText(
                      "${entry.key}: ${(entry.value as List).join('\n')}",
                    ),
                  if (record['reuse_approval'] case final Map approval)
                    SelectableText('User reuse approval: ${approval['permission_basis']}')
                  else
                    TextButton(
                      onPressed: _busy ? null : () => _approveCatalogReuse(id as String, record),
                      child: const Text('Record reuse approval'),
                    ),
                ],
                Text(
                  'Loads item metadata from ${record['source']}?fo=json.',
                ),
                OutlinedButton(
                  onPressed: _busy ? null : () => _submit('/jobs/$id/review-catalog-item', {
                    'approved_url': record['source'],
                  }),
                  child: const Text('Approve loading item advisories'),
                ),
              ],
            ),
          if (catalogRecords.any((record) => collectableCatalogRecord(record as Map)))
            OutlinedButton(
              onPressed: _busy || selectedCatalogUrls.isEmpty ? null
                  : () => _submit('/jobs/$id/use-catalog-descriptions', {
                      'approved_urls': selectedCatalogUrls,
                    }),
              child: Text('Approve catalog descriptions (${selectedCatalogUrls.length} selected)'),
            ),
          TextButton(
            onPressed: _busy ? null : () => _submit('/jobs/$id/close-catalog', {}),
            child: const Text('Return to dataset approval'),
          ),
        ],
        if (status == 'text_candidates' || status == 'image_candidates')
          TextButton(
            onPressed: () => _showDiscoveryProviders(
              (plan?['queries'] as List?)?.isNotEmpty ?? false,
            ),
            child: const Text('Browse discovery providers'),
          ),
        if (status == 'text_candidates') ...[
          TextButton(
            onPressed: _busy
                ? null
                : () => _editPlanItems(id as String, plan!['queries'] as List),
            child: const Text('Edit web queries'),
          ),
          if (textCandidates.isNotEmpty)
            TextButton(
              onPressed: _busy
                  ? null
                  : () => setState(() {
                      if (selectedTextUrls.length == textCandidates.length) {
                        _excludedTextSources.addAll(
                          textCandidates.map((candidate) => candidate['source'] as String),
                        );
                      } else {
                        _excludedTextSources.clear();
                      }
                    }),
              child: Text(
                selectedTextUrls.length == textCandidates.length
                    ? 'Clear excerpt selection'
                    : 'Select all excerpts',
              ),
            ),
          for (final candidate in textCandidates)
            ListTile(
              title: SelectableText(
                (candidate['title'] as String?)?.isNotEmpty == true
                    ? "${candidate['title']}\n${candidate['text']}"
                    : candidate['text'] as String,
              ),
              subtitle: SelectableText(
                [
                  if (candidate['approved_query'] case final String query)
                    'Approved query: $query',
                  candidate['source'],
                ].join('\n'),
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
                semanticLabel: [
                  if (candidate['title'] case final String title when title.isNotEmpty)
                    'Include $title'
                  else
                    'Include excerpt',
                  candidate['source'],
                ].join('. '),
              ),
            ),
          const Text(
            'ALMG labels the selected search excerpts locally. '
            'Approving excerpts does not fetch full articles.',
          ),
          FilledButton(
            onPressed: _busy || selectedTextUrls.isEmpty
                ? null
                : () => _submit('/jobs/$id/use-text-excerpts', {
                    'approved_urls': selectedTextUrls.toList(),
                  }),
            child: Text('Approve excerpts (${selectedTextUrls.length} selected)'),
          ),
        ],
        if (status == 'image_candidates') ...[
          if (imageCandidates.isNotEmpty)
            const Text('Review each image’s source and license before approving.'),
          TextButton(
            onPressed: _busy
                ? null
                : () => _editPlanItems(id as String, plan!['queries'] as List),
            child: const Text('Edit web queries'),
          ),
          if (imageCandidates.isEmpty)
            const Text(
              'No supported image files found. Try a new training task.',
            ),
          if (imageCandidates.isNotEmpty)
            TextButton(
              onPressed: _busy
                  ? null
                  : () => setState(() {
                      if (selectedImageUrls.length == imageCandidates.length) {
                        _excludedImageSources.addAll(
                          imageCandidates.map((candidate) => candidate['url'] as String),
                        );
                      } else {
                        _excludedImageSources.clear();
                      }
                    }),
              child: Text(
                selectedImageUrls.length == imageCandidates.length
                    ? 'Clear image selection'
                    : 'Select all images',
              ),
            ),
          for (final candidate in imageCandidates)
            ListTile(
              trailing: Checkbox(
                value: !_excludedImageSources.contains(candidate['url']),
                semanticLabel: "Include ${candidate['title']}. "
                    "${candidate['license'] ?? 'License unavailable'}. "
                    "${candidate['url']}",
                onChanged: _busy
                    ? null
                    : (checked) => setState(() {
                        final url = candidate['url'] as String;
                        if (checked == true) {
                          _excludedImageSources.remove(url);
                        } else {
                          _excludedImageSources.add(url);
                        }
                      }),
              ),
              title: Text(candidate['title'] as String),
              subtitle: SelectableText(
                [
                  candidate['url'],
                  candidate['license'] ?? 'License unavailable',
                  if (candidate['artist'] case final String artist)
                    'Creator: $artist',
                  if (candidate['attribution_required'] == true)
                    candidate['artist'] == null && candidate['credit'] == null
                        ? 'Attribution required. Check the file page for credit.'
                        : 'Attribution required',
                  if (candidate['restrictions'] case final String restrictions)
                    'Reuse restrictions: $restrictions',
                  if (candidate['credit'] case final String credit)
                    'Credit: $credit',
                  if (candidate['license_url'] case final String licenseUrl)
                    'License terms: $licenseUrl',
                  _commonsFilePage(candidate['title'] as String),
                  if (candidate['approved_query'] case final String query)
                    'Approved query: $query',
                ].join('\n'),
              ),
            ),
          if (imageCandidates.isNotEmpty)
            const Text(
              'Select at least five images to prepare a dataset.',
            ),
          if (selectedImageUrls.length >= 5)
            Text(
              'Download from upload.wikimedia.org. '
              'Up to ${selectedImageUrls.length * downloadLimit} MiB total.',
            ),
          if (imageCandidates.isNotEmpty)
            FilledButton(
              onPressed: _busy || selectedImageUrls.length < 5
                  ? null
                  : () => _submit('/jobs/$id/download-images', {
                      'approved_urls': selectedImageUrls,
                      'approved_download_limit_mib': downloadLimit,
                    }),
              child: Text(
                'Approve ${selectedImageUrls.length} image downloads ($downloadLimit MiB each)',
              ),
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
                        if (row['title'] case final String title when title.isNotEmpty)
                          row['provider'] == 'loc'
                              ? 'Catalog record: $title'
                              : row['provider'] == 'europe_pmc'
                                  ? 'Publication: $title'
                                  : row['provider'] == 'wikidata'
                                      ? 'Entity: $title'
                                      : 'Article: $title',
                        if ({'loc', 'europe_pmc', 'wikidata'}.contains(row['provider']) && row['reuse_approval'] is Map)
                          'User reuse approval: ${row['reuse_approval']['permission_basis']}',
                        if (row['approved_query'] case final String query)
                          'Approved query: $query',
                        if (row['source'] case final String source
                            when row['provider'] != null ||
                                source.startsWith('https://en.wikipedia.org/wiki/'))
                          _datasetSourceLabel(row, source),
                      ].join('\n')
                    : [
                        row['text'],
                        if (row['source'] case final String source)
                          _datasetSourceLabel(row, source),
                        row['license'] ?? 'License unavailable',
                        if (row['artist'] case final String artist)
                          'Creator: $artist',
                        if (row['attribution_required'] == true)
                          row['artist'] == null && row['credit'] == null &&
                                  row['title'] is String
                              ? 'Attribution required. Check the file page for credit.'
                              : 'Attribution required',
                        if (row['restrictions'] case final String restrictions)
                          'Reuse restrictions: $restrictions',
                        if (row['credit'] case final String credit)
                          'Credit: $credit',
                        if (row['license_url'] case final String licenseUrl)
                          'License terms: $licenseUrl',
                        if (row['title'] case final String title when title.isNotEmpty)
                          _commonsFilePage(title),
                        if (row['approved_query'] case final String query)
                          'Approved query: $query',
                      ].join('\n'),
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
