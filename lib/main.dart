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
import 'indicator_filter.dart';
import 'project_settings.dart';

/// Starts the Flutter desktop application.
void main() {
  WidgetsFlutterBinding.ensureInitialized();
  const MethodChannel('almg/power_events').setMethodCallHandler((call) async {
    if (call.method != 'powerEvent') return;
    try {
      await forwardPowerEvent(call.arguments as String);
    } catch (_) {
      // If the backend stopped, saved jobs require renewed approval on restart.
    }
  });
  runApp(const ModelStudio());
}

int _powerEventSequence = 0;

/// Forwards local native power events using bounded, idempotent retries.
Future<void> forwardPowerEvent(String event, {int port = backendPort, int attempts = 3,
    Duration retryDelay = const Duration(milliseconds: 500), String? eventId}) async {
  if (!{'sleep', 'wake'}.contains(event) || attempts < 1 || attempts > 5) {
    throw ArgumentError('Invalid power event or retry count.');
  }
  final token = eventId ?? '${DateTime.now().microsecondsSinceEpoch}-${++_powerEventSequence}';
  for (var attempt = 0; attempt < attempts; attempt++) {
    try {
      await _sendPowerEvent(event, token, port);
      return;
    } catch (error) {
      if (attempt == attempts - 1 ||
          !(error is SocketException || error is TimeoutException || error is HttpException)) {
        rethrow;
      }
      await Future<void>.delayed(retryDelay);
    }
  }
}

Future<void> _sendPowerEvent(String event, String eventId, int port) async {
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 3);
  try {
    final request = await client.postUrl(Uri.parse('http://127.0.0.1:$port/runtime/power-event'));
    request.headers.set('X-Model-Studio', 'desktop');
    request.headers.contentType = ContentType.json;
    final bytes = utf8.encode(jsonEncode({'event': event, 'event_id': eventId}));
    request.contentLength = bytes.length;
    request.add(bytes);
    final response = await request.close().timeout(const Duration(seconds: 5));
    await response.drain<void>().timeout(const Duration(seconds: 5));
    if (response.statusCode >= 500) throw HttpException('Power event temporarily unavailable.');
    if (response.statusCode >= 400) throw const FormatException('Power event was rejected.');
  } finally {
    client.close(force: true);
  }
}

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

  Future<void> _restoreProject() async {
    try {
      final file = await openFile(acceptedTypeGroups: const [XTypeGroup(label: 'ALMG project JSON', extensions: ['json'])]);
      if (file == null || !mounted) return;
      if (await file.length() > 20 * 1024 * 1024) throw const FormatException('Choose a project export up to 20 MiB.');
      final snapshot = jsonDecode(utf8.decode(await file.readAsBytes()));
      if (snapshot is! Map || snapshot['format'] != 'almg-project' || snapshot['project'] is! Map) {
        throw const FormatException('Choose an ALMG project export.');
      }
      if (!mounted) return;
      final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
        title: const Text('Restore project?'),
        content: Text('Restore “${snapshot['project']['name']}” as a separate project with saved settings, reference files and indexed sources. Existing projects stay intact. No websites will be contacted.'),
        actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Restore'))]));
      if (confirmed != true || !mounted) return;
      final request = await _client.postUrl(Uri.parse('http://127.0.0.1:$backendPort/projects/restore'));
      request.headers.set('X-Model-Studio', 'desktop');
      request.headers.contentType = ContentType.json;
      final bytes = utf8.encode(jsonEncode(snapshot));
      request.contentLength = bytes.length;
      request.add(bytes);
      final response = await request.close().timeout(const Duration(seconds: 15));
      final data = jsonDecode(await response.transform(utf8.decoder).join()) as Map;
      if (response.statusCode != 201) throw FormatException(data['error']?.toString() ?? 'Could not restore project.');
      if (!mounted) return;
      setState(() { _dashboard = _load(); });
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text('Restored ${data['name']} with ${data['page_count']} indexed sources.'),
        action: SnackBarAction(label: 'Open Model Training',
          onPressed: () => _open(StudioPage(initialProject: data['id'] as String))),
      ));
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.toString())));
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
          TextButton.icon(onPressed: _restoreProject, icon: const Icon(Icons.restore), label: const Text('Restore project export')),
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
  final Set<String> _excludedIndicators = {};
  final Set<String> _excludedNotices = {};
  final Set<String> _excludedBibliography = {};
  final Set<String> _excludedFilings = {};
  final Set<String> _excludedWebsitePages = {};
  final _secQuery = TextEditingController();
  final _secCik = TextEditingController();
  final _secContact = TextEditingController();
  final _indicatorFilter = TextEditingController();
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
    Duration timeout = const Duration(seconds: 8),
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
    final response = await request.close().timeout(timeout);
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
        if (_job?['id'] != job['id']) _indicatorFilter.clear();
        if (_job?['id'] != job['id'] || job['status'] != 'indicator_candidates') {
          _excludedIndicators.clear();
        }
        if (_job?['id'] != job['id'] ||
            !{'notice_candidates', 'reviewing_notice'}.contains(job['status'])) {
          _excludedNotices.clear();
        }
        if (_job?['id'] != job['id'] ||
            !{'bibliographic_candidates', 'reviewing_bibliography'}.contains(job['status'])) {
          _excludedBibliography.clear();
        }
        if (_job?['id'] != job['id'] ||
            !{'filing_candidates', 'reviewing_filing'}.contains(job['status'])) {
          _excludedFilings.clear();
        }
        if (_job?['id'] != job['id'] ||
            !{'website_candidates', 'reviewing_website_page'}.contains(job['status'])) {
          _excludedWebsitePages.clear();
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
        'searching_notices',
        'searching_bibliography',
        'searching_filings',
        'reviewing_filing',
        'reviewing_website_access',
        'discovering_website',
        'reviewing_website_page',
        'searching_companies',
        'reviewing_bibliography',
        'reviewing_notice',
        'loading_indicators',
        'reviewing_publication',
        'reviewing_catalog_item',
        'creating_dataset',
        'reviewing_labels',
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
    const providers = {'search-images': 'commons', 'download-images': 'commons', 'search-catalog': 'loc', 'search-publications': 'europe_pmc',
      'search-entities': 'wikidata', 'load-indicators': 'world_bank', 'search-notices': 'federal_register',
      'search-companies': 'sec_edgar', 'search-filings': 'sec_edgar', 'search-bibliography': 'crossref',
      'review-website-access': 'project_website'};
    final action = path.split('/').last;
    final provider = action == 'prepare' && body['mode'] == 'web' ? 'wikipedia' : providers[action];
    if (provider != null && !_providerEnabled(provider)) {
      setState(() => _error = 'This discovery provider is disabled for the project. Enable it in project settings first.');
      return;
    }
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
    _secQuery.dispose();
    _secCik.dispose();
    _secContact.dispose();
    _indicatorFilter.dispose();
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

  Future<void> _approveWebsiteRules(String id, Map review) async {
    var basis = '';
    final approved = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Record website access-rule review'),
      content: SizedBox(width: 460, child: Column(mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start, children: [
          SelectableText(review['website'] as String),
          const Text('Confirm you reviewed the site’s rules for automated access and the displayed robots guidance. Record the policy URL, owner permission, or other basis. This records access-rule review only; it does not approve content reuse or start crawling.'),
          TextField(autofocus: true, minLines: 2, maxLines: 4, maxLength: 2000,
            decoration: const InputDecoration(labelText: 'Basis for automated access'),
            onChanged: (value) => basis = value),
        ])),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm access-rule review'))],
    ));
    if (approved == true && mounted) {
      await _submit('/jobs/$id/approve-website-access-rules', {'approved_website': review['website'],
        'approved_scope': 'website_access_rules', 'access_basis': basis, 'confirmed': true});
    }
  }

  Future<void> _approveCatalogReuse(String id, Map record, {String action = 'approve-catalog-reuse', String? scope}) async {
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
              if (scope == 'catalog_description')
                const Text('This decision covers the displayed catalog description only. Country/year observations need separate review.'),
              if (scope == 'document_summary')
                const Text('This decision covers the displayed document summary only. Full-text reuse needs separate review.'),
              if (scope == 'wikipedia_excerpt')
                const Text('This decision covers only the displayed search excerpt. Review applicable licensing and attribution requirements for this source; full-article reuse needs separate review.'),
              if (scope == 'website_page_preview')
                const Text('This decision covers only the displayed page text preview, including any truncation. Website access permission and robots allowance do not establish permission to reuse content.'),
              if (scope == 'sec_filing_preview')
                const Text('This decision covers only the displayed filing text preview, including any truncation. Review the applicable permission; public access does not establish reuse rights.'),
              if (scope == 'crossref_abstract')
                const Text('This decision covers the displayed abstract only. Confirm that any supplied license statement applies to this abstract.'),
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
        'approved_scope': ?scope,
        'confirmed': true,
      });
    }
  }

  String _datasetSourceLabel(Map row, String source) {
    final provider = row['provider'];
    if (provider == 'local_index') return 'Saved project source: $source';
    if (provider == 'wikipedia' ||
        (provider == null && source.startsWith('https://en.wikipedia.org/wiki/'))) {
      return 'English Wikipedia: $source';
    }
    if (provider == 'loc') return 'Library of Congress: $source';
    if (provider == 'europe_pmc') return 'Europe PMC: $source';
    if (provider == 'wikidata') return 'Wikidata: $source';
    if (provider == 'world_bank') return 'World Bank indicator catalog: $source';
    if (provider == 'project_website') return 'Project website: $source';
    if (provider == 'sec_edgar') return 'SEC EDGAR: $source';
    if (provider == 'crossref') return 'Crossref: $source';
    if (provider == 'federal_register') return 'Federal Register: $source';
    if (provider == 'commons' ||
        (provider == null && source.startsWith('https://upload.wikimedia.org/'))) {
      return 'Wikimedia Commons: $source';
    }
    return source;
  }

  String _commonsFilePage(String title) =>
      'File page: https://commons.wikimedia.org/wiki/File:${Uri.encodeComponent(title)}';

  Future<void> _showSavedPages() async {
    final project = _project;
    final jobId = _activeJob;
    final canUse = _job?['status'] == 'approval' && _job?['recipe'] == 'classifier' && jobId != null;
    if (project == null) return;
    var query = '';
    var searchError = '';
    final selected = <String>{};
    try {
      var pages = (await _request('/project-pages?project_id=${Uri.encodeQueryComponent(project)}'))['pages'] as List;
      if (!mounted) return;
      final choices = await showDialog<List<dynamic>>(context: context, builder: (context) => StatefulBuilder(builder: (context, update) => AlertDialog(
        title: const Text('Saved project pages'),
        content: SizedBox(width: 600, height: 480, child: Column(children: [
          const Text('Searches this project’s collected text locally. No websites are contacted. Shows up to 20 saved sources.'),
          TextField(maxLength: 160, decoration: const InputDecoration(labelText: 'Search saved text or source URL'),
            onChanged: (value) => query = value),
          TextButton(onPressed: () async {
            try {
              final result = await _request('/project-pages?project_id=${Uri.encodeQueryComponent(project)}&q=${Uri.encodeQueryComponent(query)}');
              if (context.mounted) update(() { pages = result['pages'] as List; selected.clear(); searchError = ''; });
            } catch (error) {
              if (context.mounted) update(() => searchError = 'Local search failed: $error');
            }
          }, child: const Text('Search local pages')),
          if (searchError.isNotEmpty) Text(searchError),
          Expanded(child: ListView(children: [
            if (pages.isEmpty) const Text('No saved pages match this search.'),
            for (final page in pages) CheckboxListTile(
              title: Text(page['source'] as String),
              subtitle: Text('${(page['text'] as String).length > 1000 ? '${(page['text'] as String).substring(0, 1000)}…' : page['text']}\nReuse basis: ${page['metadata']['reuse_approval']?['permission_basis'] ?? 'No recorded reuse permission'}'),
              value: selected.contains(page['source']),
              onChanged: !canUse || page['metadata']['reuse_approval'] is! Map ? null : (checked) => update(() {
                if (checked == true) { selected.add(page['source'] as String); }
                else { selected.remove(page['source']); }
              })),
          ])),
        ])),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
          if (canUse) FilledButton(onPressed: selected.isEmpty ? null : () => Navigator.pop(context,
            [for (final page in pages) if (selected.contains(page['source'])) {'source': page['source'], 'revision': page['revision']}]),
            child: Text('Use saved sources (${selected.length} selected)'))],
      )));
      if (choices == null || !mounted) return;
      final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
        title: const Text('Approve saved text for this dataset'),
        content: Text('Use the stored text of ${choices.length} selected sources, up to 50,000 characters each, with their recorded reuse evidence. Confirm that the recorded permission still applies. Text will be labeled locally for this plan. No websites will be contacted.'),
        actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Approve saved-text reuse'))],
      ));
      if (confirmed == true) {
        await _submit('/jobs/$jobId/use-saved-pages', {'approved_pages': choices, 'confirmed': true, 'approved_scope': 'saved_project_text'});
      }
    } catch (error) {
      if (mounted) setState(() => _error = 'Saved page search failed: $error');
    }
  }

  bool _providerEnabled(String provider) {
    final project = _projects.where((item) => item['id'] == _project).firstOrNull;
    return (project?['enabled_providers'] as List? ?? discoveryProviderNames.keys.toList()).contains(provider);
  }

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
                  trailing: !_providerEnabled('wikipedia') ? const Text('Disabled') : hasQueries && !_imageRecipe ? const Text('Current plan') : null,
                  subtitle: const Text('en.wikipedia.org · Text classification'),
                ),
                ListTile(
                  title: const Text('Wikimedia Commons'),
                  trailing: !_providerEnabled('commons') ? const Text('Disabled') : hasQueries && _imageRecipe ? const Text('Current plan') : null,
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
                      trailing: _providerEnabled('project_website') ? null : const Text('Disabled'),
                      subtitle: const Text('Robots review and separately approved page previews'),
                    ),
                ],
                ListTile(
                  trailing: _providerEnabled('loc') ? null : const Text('Disabled'),
                  title: const Text('Library of Congress'),
                  subtitle: Text('www.loc.gov · Catalog preview for text classification'),
                ),
                ListTile(
                  trailing: _providerEnabled('europe_pmc') ? null : const Text('Disabled'),
                  title: const Text('Europe PMC'),
                  subtitle: Text('www.ebi.ac.uk · Publication preview for text classification'),
                ),
                ListTile(
                  trailing: _providerEnabled('wikidata') ? null : const Text('Disabled'),
                  title: const Text('Wikidata'),
                  subtitle: Text('www.wikidata.org · Entity preview for text classification'),
                ),
                ListTile(
                  trailing: _providerEnabled('world_bank') ? null : const Text('Disabled'),
                  title: const Text('World Bank Open Data'),
                  subtitle: Text('api.worldbank.org · Indicator catalog preview'),
                ),
                ListTile(
                  trailing: _providerEnabled('federal_register') ? null : const Text('Disabled'),
                  title: const Text('Federal Register'),
                  subtitle: Text('www.federalregister.gov · Document preview for text classification'),
                ),
                ListTile(
                  trailing: _providerEnabled('crossref') ? null : const Text('Disabled'),
                  title: const Text('Crossref'),
                  subtitle: Text('api.crossref.org · Bibliographic preview for text classification'),
                ),
                ListTile(
                  trailing: _providerEnabled('sec_edgar') ? null : const Text('Disabled'),
                  title: const Text('SEC EDGAR'),
                  subtitle: Text('www.sec.gov · Company name/ticker lookup\ndata.sec.gov · Recent filings by CIK\nSeparate approval for filing text and reuse; declared contact required.'),
                ),

              ],
            ),
          ),
        ),
        actions: [
          if (projectId != null)
            TextButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Project discovery settings'),
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

  Future<void> _showTrainingReadiness() async {
    try {
      final result = await _request('/runtime/training-readiness');
      if (!mounted) return;
      await showDialog<void>(context: context, builder: (context) => AlertDialog(
        title: Text(result['ready'] == true ? 'Device ready for idle-gated training' : 'Device waiting'),
        content: Text(result['message'] as String),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ));
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _validateLocalLora() async {
    try {
      final result = await _request('/runtime/lora-fixture', {'confirmed': true});
      if (!mounted) return;
      await showDialog<void>(context: context, builder: (context) => AlertDialog(
        title: const Text('Local LoRA fixture passed'),
        content: Text('${result['scope']}\n\n'
          'Device: ${result['device']} · rank ${result['rank']} · ${result['steps']} steps\n'
          'Loss: ${(result['initial_loss'] as num).toStringAsFixed(6)} → ${(result['final_loss'] as num).toStringAsFixed(6)}\n'
          'Held-out next-token accuracy: ${((result['held_out_next_token_accuracy'] as num) * 100).toStringAsFixed(1)}%\n'
          'Trainable / frozen parameters: ${result['trainable_parameters']} / ${result['frozen_parameters']}\n'
          'Generated token IDs: ${(result['generated_tokens'] as List).join(' ')}\n'
          'Causal prefix error: ${result['causal_prefix_max_error']}\n'
          'Base weights unchanged: ${result['base_weights_unchanged']}\n'
          'Adapter reload error: ${result['reload_max_error']}'),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ));
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _showDecoderDataset(Map<String, dynamic> manifest) async {
    await showDialog<void>(context: context, builder: (context) => AlertDialog(
      title: const Text('Decoder dataset prepared for review'), scrollable: true,
      content: SizedBox(width: 620, child: SelectableText(const JsonEncoder.withIndent('  ').convert(manifest))),
      actions: [
        if (manifest['tokenizer'] != null && !(manifest['findings'] as List).any((finding) =>
            ['tokenizer_limits', 'out_of_training_vocabulary'].contains(finding['kind'])))
          TextButton(onPressed: () {
            Navigator.pop(context);
            _approveDatasetTrial(manifest);
          }, child: const Text('Review bounded decoder training')),
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
      ],
    ));
  }

  Future<void> _approveDatasetTrial(Map<String, dynamic> dataset) async {
    final approved = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Approve local dataset trial'),
      content: Text('Train a tiny decoder from new weights on ${dataset['unique_documents']} reviewed documents. '
        'The trial uses the saved train/validation/test splits, 100 training steps, seed 7 and immediate Metal execution. '
        'Duplicate documents are excluded. Cancellation and checkpoint resume remain available. '
        'This experimental trial does not release a model.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Approve training on reviewed dataset'))],
    ));
    if (approved == true && mounted) await _startDecoderTrial(dataset: dataset);
  }

  Future<void> _prepareDecoderDataset() async {
    try {
      final files = await openFiles(acceptedTypeGroups: [const XTypeGroup(label: 'UTF-8 text', extensions: ['txt'])]);
      if (files.isEmpty) return;
      if (files.length < 3 || files.length > 16) throw const FormatException('Select 3 to 16 text documents.');
      final documents = <Map<String, String>>[];
      var total = 0;
      for (final file in files) {
        final length = await file.length();
        total += length;
        if (length > 65536 || total > 128000) throw const FormatException('Each document must fit 64 KiB; the selection must fit 128000 bytes.');
        final bytes = await file.readAsBytes();
        utf8.decode(bytes); // Validate without replacing the original bytes used for provenance.
        documents.add({'name': file.name, 'data': base64Encode(bytes)});
      }
      final manifest = await _request('/decoder-datasets', {'confirmed': true, 'documents': documents});
      if (mounted) {
        setState(() => _error = null);
        await _showDecoderDataset(manifest);
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _showSavedDecoderDatasets() async {
    try {
      final datasets = (await _request('/decoder-datasets'))['datasets'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Prepared decoder datasets'), children: [
          if (datasets.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No local datasets prepared yet.')),
          for (final dataset in datasets) SimpleDialogOption(
            onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(dataset as Map)),
            child: Text('${(dataset['id'] as String).substring(0, 8)} · ${dataset['unique_documents']} documents'),
          ),
        ],
      ));
      if (selected != null && mounted) {
        final verified = await _request('/decoder-datasets/${selected['id']}');
        if (mounted) await _showDecoderDataset(verified);
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _planDecoderTrial() async {
    final goal = await showDialog<String>(context: context,
      builder: (context) => const _DecoderTrialGoalDialog());
    if (goal == null || goal.trim().isEmpty || !mounted) return;
    var waitingShown = true;
    unawaited(showDialog<void>(context: context, barrierDismissible: false, builder: (context) => const AlertDialog(
      title: Text('Asking local Qwen'),
      content: Row(mainAxisSize: MainAxisSize.min, children: [CircularProgressIndicator(), SizedBox(width: 16), Text('Preparing an approach proposal…')]),
    )));
    try {
      final proposal = await _request('/decoder-trial-proposals', {'goal': goal}, const Duration(seconds: 120));
      if (!mounted) return;
      Navigator.pop(context);
      waitingShown = false;
      final approved = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
        title: const Text('Review trial approach'),
        scrollable: true,
        content: SizedBox(width: 520, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Goal: ${proposal['goal']}'),
          Text('Recommended approach: ${proposal['approach']}'),
          Text('Planner: ${proposal['planner']?['model'] ?? proposal['planner']?['provider'] ?? 'Unspecified'}'),
          Text(proposal['reason'] as String),
          const Text('Scope: fixed generated local text. This does not enable training on your own dataset or release a model.'),
          if (proposal['executable'] != true) const Text('This approach is unavailable in the decoder trial workflow. No execution will start.'),
        ])),
        actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Close')),
          if (proposal['executable'] == true) TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm from-scratch trial'))],
      ));
      if (approved == true && mounted) await _startDecoderTrial(proposal: proposal);
    } catch (error) {
      if (mounted && waitingShown) Navigator.pop(context);
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _startDecoderTrial({String? id, Map<String, dynamic>? proposal, Map<String, dynamic>? dataset}) async {
    try {
      final created = await _request(id == null ? '/decoder-trials' : '/decoder-trials/$id/resume', {
        'confirmed': true, if (proposal != null) 'proposal_id': proposal['id'],
        if (proposal != null) 'proposal_revision': proposal['revision'],
        'dataset': ?dataset,
      });
      final trialId = created['id'];
      var record = await _request('/decoder-trials/$trialId');
      for (var attempt = 0; attempt < 40 && ['queued', 'running'].contains(record['status']); attempt++) {
        await Future<void>.delayed(const Duration(milliseconds: 250));
        if (!mounted) return;
        record = await _request('/decoder-trials/$trialId');
      }
      if (mounted) await _showDecoderTrial(record);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _cancelDecoderTrial(String id) async {
    try {
      var record = await _request('/decoder-trials/$id/cancel', {'confirmed': true});
      for (var attempt = 0; attempt < 40 && ['queued', 'running'].contains(record['status']); attempt++) {
        await Future<void>.delayed(const Duration(milliseconds: 250));
        if (!mounted) return;
        record = await _request('/decoder-trials/$id');
      }
      if (mounted) await _showDecoderTrial(record);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _showDecoderTrial(Map<String, dynamic> record) async {
    await showDialog<void>(context: context, builder: (context) => AlertDialog(
      title: Text('Saved decoder trial · ${record['status']}'),
      scrollable: true,
      content: SizedBox(width: 620, child: SelectableText(const JsonEncoder.withIndent('  ').convert(record))),
      actions: [
        if (['queued', 'running'].contains(record['status'])) TextButton(onPressed: () {
          Navigator.pop(context);
          _cancelDecoderTrial(record['id'] as String);
        }, child: const Text('Cancel saved decoder trial')),
        if (record['status'] == 'interrupted') TextButton(onPressed: () {
          Navigator.pop(context);
          _startDecoderTrial(id: record['id'] as String);
        }, child: const Text('Approve resume of saved trial')),
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
      ],
    ));
  }

  Future<void> _showSavedDecoderTrials() async {
    try {
      final trials = (await _request('/decoder-trials'))['trials'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved decoder trials'),
        children: [
          if (trials.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved decoder trials yet.')),
          for (final trial in trials) SimpleDialogOption(
            onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(trial as Map)),
            child: Text('${(trial['id'] as String).substring(0, 8)} · ${trial['status']}'),
          ),
        ],
      ));
      if (selected != null && mounted) await _showDecoderTrial(selected);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _checkDecoderTraining() async {
    try {
      final result = await _request('/runtime/decoder-training', {'confirmed': true});
      if (!mounted) return;
      await showDialog<void>(context: context, builder: (context) => AlertDialog(
        title: const Text('Decoder training check passed'),
        scrollable: true,
        content: SelectableText(const JsonEncoder.withIndent('  ').convert(result)),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ));
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _checkDecoderInitialization() async {
    try {
      final result = await _request('/runtime/decoder-initialization', {'confirmed': true});
      if (!mounted) return;
      await showDialog<void>(context: context, builder: (context) => AlertDialog(
        title: const Text('Decoder initialization passed'),
        scrollable: true,
        content: SelectableText(const JsonEncoder.withIndent('  ').convert(result)),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ));
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _showRunManifest() async {
    try {
      final manifest = await _request('/jobs/${_job!['id']}/manifest');
      if (!mounted) return;
      await showDialog<void>(context: context, builder: (context) => AlertDialog(
        title: const Text('Run reproducibility record'),
        scrollable: true,
        content: SizedBox(width: 620, child: SelectableText(
          const JsonEncoder.withIndent('  ').convert(manifest))),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ));
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  /// Shows the current proposal, dataset preview, evaluation, and release gate.
  Future<void> _showRecipeContract() async {
    try {
      final recipe = _job?['recipe'] as String?;
      if (recipe == null) return;
      final contract = _job?['recipe_contract'] as Map? ?? await _request('/recipes/$recipe');
      if (!mounted) return;
      await showDialog<void>(context: context, builder: (context) => AlertDialog(
        title: Text('${contract['name']} · version ${contract['version']}'),
        scrollable: true,
        content: SizedBox(width: 520, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(contract['description'] as String),
          const SizedBox(height: 12),
          Text('Dataset: ${contract['dataset']['format']}'),
          Text('Input: ${contract['dataset']['imports']}'),
          if (contract['dataset']['modes'] is Map)
            Text('Supported sources: ${(contract['dataset']['modes'] as Map).values.map((mode) => mode['label']).toSet().join(', ')}'),
          Text('Training hardware: ${contract['hardware']['training']}'),
          Text('Planning: ${contract['hardware']['planning']}'),
          const SizedBox(height: 12),
          const Text('Parameters'),
          for (final parameter in contract['parameters'] as List)
            Text('${parameter['label']}: ${parameter['type']}, default ${parameter['default']}'
              '${parameter['maximum'] == null ? '' : ', greater than ${parameter['minimum_exclusive']} up to ${parameter['maximum']}'}'),
          const SizedBox(height: 12),
          const Text('Metrics'),
          for (final entry in (contract['metrics'] as Map).entries)
            Text('${entry.key}: ${(entry.value as List).join(', ')}'),
          const SizedBox(height: 12),
          const Text('Exported artifacts'),
          for (final artifact in contract['exports'] as List) Text(artifact as String),
          const SizedBox(height: 12),
          Text('Resume: ${contract['resume']}'),
          const Text('Prepare 3–16 local UTF-8 text documents for decoder dataset review. No training or external collection starts.'),
          TextButton(onPressed: () {
            Navigator.pop(context);
            _prepareDecoderDataset();
          }, child: const Text('Prepare local decoder text dataset')),
          TextButton(onPressed: () {
            Navigator.pop(context);
            _showSavedDecoderDatasets();
          }, child: const Text('View prepared decoder datasets')),

          const Text('Optional CPU check constructs a tiny decoder from new weights. No downloads; language-model training is not enabled.'),
          TextButton(onPressed: () {
            Navigator.pop(context);
            _checkDecoderInitialization();
          }, child: const Text('Check decoder initialization')),
          if (Platform.isMacOS) ...[
            const Text('Optional Apple silicon check trains every tiny decoder weight on generated tokens. User-dataset pretraining and export are not enabled.'),
            TextButton(onPressed: () {
              Navigator.pop(context);
              _checkDecoderTraining();
            }, child: const Text('Check from-scratch decoder training')),
            const Text('Saved trials keep their approval receipt, checkpoint and trained bundle locally. They use fixed generated text; general pretraining and release remain unavailable.'),
            TextButton(onPressed: () {
              Navigator.pop(context);
              _startDecoderTrial();
            }, child: const Text('Approve and save a local decoder trial')),
            TextButton(onPressed: () {
              Navigator.pop(context);
              _planDecoderTrial();
            }, child: const Text('Plan a local decoder trial with Qwen')),

            TextButton(onPressed: () {
              Navigator.pop(context);
              _showSavedDecoderTrials();
            }, child: const Text('View saved decoder trials')),

          ],


          if (['preview_ready', 'passed'].contains(_job?['status']))
            TextButton(onPressed: () {
              Navigator.pop(context);
              _showRunManifest();
            }, child: const Text('View run reproducibility record')),

          TextButton(onPressed: () {
            Navigator.pop(context);
            _showTrainingReadiness();
          }, child: const Text('Check current idle and power status')),
          if (Platform.isMacOS) ...[
            const Text('Local recovery fixture sends sleep/wake notifications inside ALMG only. Active training returns to approval; the Mac stays awake.'),
            TextButton(onPressed: () async {
              Navigator.pop(context);
              try {
                await const MethodChannel('almg/power_events').invokeMethod<void>('localNotificationFixture');
              } catch (error) {
                if (mounted) setState(() => _error = error.toString());
              }
            }, child: const Text('Run local sleep/wake recovery fixture')),
          ],
          const SizedBox(height: 12),
          const Text('Optional local LoRA check: trains rank-2 adapters in a tiny causal language model using generated token sequences. No downloads; fine-tuning your own models remains unavailable.'),
          TextButton(onPressed: () {
            Navigator.pop(context);
            _validateLocalLora();
          }, child: const Text('Run local LoRA fixture')),
        ])),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ));
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

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
        if (collectableWikipediaExcerpt(candidate as Map) && !_excludedTextSources.contains(candidate['source']))
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
    final indicatorRecords = job?['indicator_candidates'] as List? ?? const [];
    final visibleIndicators = filterIndicators(indicatorRecords, _indicatorFilter.text);
    final selectedIndicatorUrls = [
      for (final record in visibleIndicators)
        if (collectableIndicator(record) && !_excludedIndicators.contains(record['source']))
          record['source'] as String,
    ];
    final projectWebsite = _projects.where((project) => project['id'] == _project)
        .firstOrNull?['source_website'] as String? ?? '';
    final websiteRecords = job?['website_candidates'] as List? ?? const [];
    final selectedWebsiteUrls = [
      for (final record in websiteRecords)
        if (collectableWebsitePage(record as Map) && !_excludedWebsitePages.contains(record['source']))
          record['source'] as String,
    ];
    final filingRecords = job?['filing_candidates'] as List? ?? const [];
    final selectedFilingUrls = [
      for (final record in filingRecords)
        if (collectableFiling(record as Map) && !_excludedFilings.contains(record['source']))
          record['source'] as String,
    ];
    final bibliographyRecords = job?['bibliographic_candidates'] as List? ?? const [];
    final selectedBibliographyUrls = [
      for (final record in bibliographyRecords)
        if (collectableBibliography(record as Map) && !_excludedBibliography.contains(record['source']))
          record['source'] as String,
    ];
    final noticeRecords = job?['notice_candidates'] as List? ?? const [];
    final selectedNoticeUrls = [
      for (final record in noticeRecords)
        if (collectableNotice(record as Map) && !_excludedNotices.contains(record['source']))
          record['source'] as String,
    ];
    final states = {
      'planning': 'Qwen is drafting the plan',
      'approval': 'Dataset approval required',
      'clarification': 'Waiting for more details',
      'searching_images': 'Searching for images',
      'searching_text': 'Searching Wikipedia',
      'searching_catalog': 'Searching the Library of Congress',
      'searching_publications': 'Searching Europe PMC',
      'searching_entities': 'Searching Wikidata',
      'searching_notices': 'Searching Federal Register',
      'searching_companies': 'Finding SEC companies',
      'company_candidates': 'Choose an SEC company',
      'reviewing_website_page': 'Loading approved website page',
      'discovering_website': 'Discovering links from approved website page',
      'website_candidates': 'Review discovered website URLs',
      'reviewing_website_access': 'Loading approved robots.txt',
      'website_access_review': 'Review project website access guidance',
      'reviewing_filing': 'Loading approved SEC filing text',
      'searching_filings': 'Loading SEC company filings',
      'filing_candidates': 'Review SEC filing URLs',
      'searching_bibliography': 'Searching Crossref',
      'bibliographic_candidates': 'Review Crossref bibliographic records',
      'reviewing_bibliography': 'Loading Crossref abstract metadata',
      'notice_candidates': 'Review Federal Register documents',
      'reviewing_notice': 'Loading document summary metadata',
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
      'reviewing_labels': 'Reviewing labels with the local model',
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
      'reviewing_labels',
      'queued',
      'waiting_idle',
      'training',
      'exporting',
    }.contains(status);
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        if (_project != null)
          TextButton(onPressed: _busy ? null : _showSavedPages, child: const Text('Search saved project pages')),

        Text('Model creation', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 12),
        Text(states[status] ?? 'Waiting for a model goal'),
        if (status == 'waiting_idle' && _job?['training_readiness'] is Map)
          Text(_job!['training_readiness']['message'] as String),
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
        if (job?['recipe'] is String)
          TextButton(onPressed: _busy ? null : _showRecipeContract, child: const Text('Training recipe details')),
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
          if (discoveryProviderNames.keys.any((provider) => !_providerEnabled(provider)))
            const Text('Some providers are disabled for this project. Use Browse discovery providers, then Project discovery settings, to enable them.'),
          if (!_imageRecipe && projectWebsite.isNotEmpty) ...[
            SelectableText('Project website: $projectWebsite'),
            OutlinedButton(onPressed: _busy || !_providerEnabled('project_website') ? null : () async {
              final site = Uri.parse(projectWebsite);
              final destination = Uri(scheme: 'https', host: site.host, path: '/robots.txt').toString();
              final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
                title: const Text('Approve website robots review'),
                content: SelectableText('$destination\nUser-Agent: ALMG/1.0 (https://github.com/arpit-it/ALMG)\nOne request, at most 64 KiB. Redirects are not followed. No website pages are crawled. Access rules and reuse permission still need separate review.'),
                actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
                  FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Approve robots.txt request'))],
              ));
              if (confirmed == true) {
                await _submit('/jobs/$id/review-website-access', {'approved_website': projectWebsite,
                  'approved_url': destination, 'approved_byte_limit': 65536});
              }
            }, child: const Text('Review project website robots.txt request')),
          ],
          if (_imageRecipe && (plan['queries'] as List).isNotEmpty) ...[
            const ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text('Wikimedia Commons'),
              subtitle: Text('commons.wikimedia.org · Images and captions'),
            ),
            Text(
              'Approving these queries sends them to Wikimedia Commons for up to $searchLimit results per query and 40 total.',
            ),
            for (final query in plan['queries'] as List)
              SelectableText(query as String),
            OutlinedButton(
              onPressed: _busy || !_providerEnabled('commons')
                  ? null
                  : () => _submit('/jobs/$id/search-images', {
                      'approved_provider': 'commons',
                      'approved_result_limit': searchLimit,
                      'approved_total_limit': 40,
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
                  onPressed: _busy || !_providerEnabled('wikipedia')
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
            onPressed: _busy || !_providerEnabled('loc') ? null : () => _submit('/jobs/$id/search-catalog', {
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
            onPressed: _busy || !_providerEnabled('europe_pmc') ? null : () => _submit('/jobs/$id/search-publications', {
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
            onPressed: _busy || !_providerEnabled('wikidata') ? null : () => _submit('/jobs/$id/search-entities', {
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
            onPressed: _busy || !_providerEnabled('world_bank') ? null : () => _submit('/jobs/$id/load-indicators', {
              'approved_provider': 'world_bank', 'approved_scope': 'indicator_catalog',
              'approved_page': 1, 'approved_result_limit': 20,
            }),
            child: const Text('Approve World Bank catalog preview'),
          ),
        ],
        if (status == 'approval' && !_imageRecipe &&
            plan != null && (plan['queries'] as List).isNotEmpty) ...[
          const Text('Federal Register document preview · www.federalregister.gov. '
              'Sends the listed queries for up to 20 documents per query and 40 total.'),
          for (final query in plan['queries'] as List) SelectableText('• $query'),
          OutlinedButton(
            onPressed: _busy || !_providerEnabled('federal_register') ? null : () => _submit('/jobs/$id/search-notices', {
              'approved_provider': 'federal_register', 'approved_queries': plan['queries'],
              'approved_result_limit': 20, 'approved_total_limit': 40,
            }),
            child: const Text('Approve Federal Register search'),
          ),
        ],
        if (status == 'approval' && !_imageRecipe &&
            plan != null && (plan['queries'] as List).isNotEmpty) ...[
          const Text('SEC EDGAR company filing preview · data.sec.gov. Enter a CIK and contact email. One submissions request returns up to 20 recent filing records; model queries are not sent. Filing content is not loaded.'),
          TextField(controller: _secQuery, maxLength: 160, decoration: const InputDecoration(labelText: 'SEC company name or ticker')),
          OutlinedButton(
            onPressed: _busy || !_providerEnabled('sec_edgar') ? null : () async {
              final query = _secQuery.text.trim();
              final contact = _secContact.text.trim();
              if (query.isEmpty) {
                setState(() => _error = 'Enter a company name or ticker.');
                return;
              }
              const destination = 'https://www.sec.gov/files/company_tickers_exchange.json';
              final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
                title: const Text('Approve SEC company lookup'),
                content: SelectableText('$destination\nUser-Agent: ALMG/1.0 $contact\nYour contact email will be sent to www.sec.gov in this header. One catalog request. Match "$query" locally and show up to 20 companies. No company submissions or filing contents are loaded.'),
                actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
                  FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Approve company catalog request'))],
              ));
              if (confirmed == true) {
                await _submit('/jobs/$id/search-companies', {'approved_provider': 'sec_edgar', 'query': query,
                  'contact': contact, 'approved_url': destination, 'approved_result_limit': 20});
              }
            },
            child: const Text('Review SEC company lookup'),
          ),
          TextField(controller: _secCik, maxLength: 10, decoration: const InputDecoration(labelText: 'SEC company CIK')),
          TextField(controller: _secContact, maxLength: 200, decoration: const InputDecoration(labelText: 'SEC user agent contact email')),
          OutlinedButton(
            onPressed: _busy || !_providerEnabled('sec_edgar') ? null : () async {
              final cik = _secCik.text.trim();
              final contact = _secContact.text.trim();
              if (!RegExp(r'^[0-9]{1,10}$').hasMatch(cik) || int.parse(cik) == 0) {
                setState(() => _error = 'Enter a company CIK containing one to ten digits.');
                return;
              }
              final destination = 'https://data.sec.gov/submissions/CIK${cik.padLeft(10, '0')}.json';
              final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
                title: const Text('Approve SEC company preview'),
                content: SelectableText('$destination\nUser-Agent: ALMG/1.0 $contact\nYour contact email will be sent to data.sec.gov in this header. One request, up to 20 records. No filing contents or older submission files are fetched.'),
                actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
                  FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Approve SEC request'))],
              ));
              if (confirmed == true) {
                await _submit('/jobs/$id/search-filings', {'approved_provider': 'sec_edgar', 'cik': cik,
                  'contact': contact, 'approved_url': destination, 'approved_result_limit': 20});
              }
            },
            child: const Text('Review SEC preview request'),
          ),
          const Text('Crossref bibliographic preview · api.crossref.org. '
              'Sends the listed queries for up to 20 records per query and 40 total.'),
          for (final query in plan['queries'] as List) SelectableText('• $query'),
          OutlinedButton(
            onPressed: _busy || !_providerEnabled('crossref') ? null : () => _submit('/jobs/$id/search-bibliography', {
              'approved_provider': 'crossref', 'approved_queries': plan['queries'],
              'approved_result_limit': 20, 'approved_total_limit': 40,
            }),
            child: const Text('Approve Crossref search'),
          ),
        ],
        if (status == 'website_access_review') ...[
          SelectableText('Website: ${job?['website_access']['website']}\nRobots URL: ${job?['website_access']['robots_url']}'),
          const Text('Review the robots guidance and the site’s access rules. Content reuse remains unverified. Discovery can load only the approved starting page.'),
          SelectableText('Robots path check for ALMG: ${job?['website_access']['robots_decision'] ?? 'undetermined'}\n${job?['website_access']['robots_rule'] ?? 'Refresh the robots guidance to check this URL.'}'),
          const Text('This checks only the saved website URL. Other pages need their own robots checks before any crawl.'),
          if (job?['website_access']['robots_status'] == 404)
            const Text('robots.txt was not found (HTTP 404). This does not establish access or reuse permission.')
          else
            SelectableText('robots.txt:\n${job?['website_access']['robots_text']}'),
          if (job?['website_access']['access_approval'] case final Map approval)
            SelectableText('Access-rule review recorded: ${approval['access_basis']}')
          else
            TextButton(onPressed: _busy ? null : () => _approveWebsiteRules(id as String, job!['website_access'] as Map),
              child: const Text('Record website access-rule review')),
          if (job?['website_access']['access_approval'] is Map && job?['website_access']['robots_decision'] == 'allowed')
            OutlinedButton(onPressed: _busy ? null : () async {
              final website = job!['website_access']['website'];
              final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
                title: const Text('Approve website link discovery'),
                content: SelectableText('$website\nLoads this one HTML page, at most 512 KiB, and lists up to 20 same-site links allowed by the reviewed robots guidance. Model queries are not sent. Linked pages and resources are not loaded. Access review expires after one hour.'),
                actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
                  FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Approve discovery page request'))],
              ));
              if (confirmed == true) {
                await _submit('/jobs/$id/discover-website-links', {'approved_url': website,
                  'approved_byte_limit': 524288, 'approved_result_limit': 20});
              }
            }, child: const Text('Review website link discovery request')),
          TextButton(onPressed: _busy ? null : () => _submit('/jobs/$id/close-website-access', {}), child: const Text('Return to dataset approval')),
        ],
        if (status == 'website_candidates') ...[
          const Text('Approve collection of selected, reuse-approved website page previews for text classification. Only displayed text is collected, including any truncation.'),
          if ((job?['website_candidates'] as List? ?? const []).isEmpty)
            const Text('No supported same-site links were found within the preview limits.'),
          for (final record in websiteRecords)
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SelectableText(record['source'] as String),
              if (collectableWebsitePage(record as Map))
                CheckboxListTile(title: Text("Include page preview: ${record['source']}"),
                  value: !_excludedWebsitePages.contains(record['source']),
                  onChanged: _busy ? null : (checked) => setState(() {
                    final source = record['source'] as String;
                    if (checked == true) { _excludedWebsitePages.remove(source); }
                    else { _excludedWebsitePages.add(source); }
                  })),
              if (record['page_reviewed'] == true && (record['page_text'] as String).length < 40)
                const Text('This page preview is too short for collection. At least 40 characters are required.'),
              if (record['page_reviewed'] == true) ...[
                SelectableText('Page text preview: ${record['page_text']}'),
                if (record['page_text_truncated'] == true) const Text('Preview truncated to 20,000 characters.'),
                const Text('Loading a page does not establish reuse permission.'),
              ],
              if (record['reuse_approval'] case final Map approval)
                SelectableText('Website page preview reuse approval: ${approval['permission_basis']}')
              else if (record['page_reviewed'] == true)
                TextButton(onPressed: _busy ? null : () => _approveCatalogReuse(id as String, record,
                    action: 'approve-website-page-reuse', scope: 'website_page_preview'),
                  child: const Text('Record page preview reuse approval')),
              OutlinedButton(onPressed: _busy ? null : () async {
                final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
                  title: const Text('Approve website page preview'),
                  content: SelectableText('${record['source']}\nOne HTML request, at most 512 KiB; display at most 20,000 characters. Current site access review and robots rules are rechecked. Redirects and linked resources are not loaded. Refreshing clears any earlier reuse approval.'),
                  actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
                    FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Approve page preview request'))],
                ));
                if (confirmed == true) {
                  await _submit('/jobs/$id/review-website-page', {'approved_url': record['source'], 'approved_byte_limit': 524288});
                }
              }, child: const Text('Review page preview request')),
            ]),
          if (websiteRecords.any((record) => collectableWebsitePage(record as Map)))
            OutlinedButton(onPressed: _busy || selectedWebsiteUrls.isEmpty ? null
                : () => _submit('/jobs/$id/use-website-page-previews', {'approved_urls': selectedWebsiteUrls}),
              child: Text('Approve website page preview collection (${selectedWebsiteUrls.length} selected)')),
          TextButton(onPressed: _busy ? null : () => _submit('/jobs/$id/close-website-links', {}), child: const Text('Return to website access review')),
        ],
        if (status == 'company_candidates') ...[
          Text('Matches for "${job?['company_query']}" in the SEC association catalog. This catalog may be incomplete or inaccurate. Choosing a CIK does not load filings.'),
          if ((job?['company_candidates'] as List? ?? const []).isEmpty)
            const Text('No company matches found. Return to change the name or ticker, or enter a known CIK.'),
          for (final record in job?['company_candidates'] as List? ?? const [])
            ListTile(title: Text('${record['company']} · ${record['ticker']}'),
              subtitle: Text('CIK ${record['cik']} · ${record['exchange']}'),
              trailing: TextButton(onPressed: _busy ? null : () async {
                _secCik.text = record['cik'] as String;
                await _submit('/jobs/$id/close-companies', {});
              }, child: const Text('Use this CIK'))),
          TextButton(onPressed: _busy ? null : () => _submit('/jobs/$id/close-companies', {}), child: const Text('Return to dataset approval')),
        ],
        if (status == 'filing_candidates') ...[
          const Text('Approve collection of selected, reuse-approved filing previews for text classification. Only the displayed text is collected, including any truncation.'),
          if ((job?['filing_candidates'] as List? ?? const []).isEmpty)
            const Text('No supported recent filings were found for this company.'),
          for (final record in filingRecords)
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              ListTile(title: Text('${record['company']} · ${record['form']}'),
                subtitle: SelectableText('CIK ${record['cik']} · ${record['filing_date']}\nAccession ${record['accession']}\n${record['source']}')),
              if (collectableFiling(record as Map))
                CheckboxListTile(title: Text("Include filing preview: ${record['company']} · ${record['form']}"),
                  value: !_excludedFilings.contains(record['source']),
                  onChanged: _busy ? null : (checked) => setState(() {
                    final source = record['source'] as String;
                    if (checked == true) { _excludedFilings.remove(source); }
                    else { _excludedFilings.add(source); }
                  })),
              if (record['filing_reviewed'] == true && (record['filing_text'] as String).length < 40)
                const Text('This filing preview is too short for collection. At least 40 characters are required.'),
              if (record['filing_reviewed'] == true) ...[
                SelectableText('Filing text preview: ${record['filing_text']}'),
                if (record['filing_text_truncated'] == true) const Text('Preview truncated to 50,000 characters.'),
                const Text('Loading a filing does not establish permission to reuse its content.'),
              ],
              if (record['reuse_approval'] case final Map approval)
                SelectableText('SEC filing preview reuse approval: ${approval['permission_basis']}')
              else if (record['filing_reviewed'] == true)
                TextButton(onPressed: _busy ? null : () => _approveCatalogReuse(id as String, record,
                    action: 'approve-filing-reuse', scope: 'sec_filing_preview'),
                  child: const Text('Record filing preview reuse approval')),
              OutlinedButton(onPressed: _busy ? null : () async {
                final contact = _secContact.text.trim();
                final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
                  title: const Text('Approve SEC filing text preview'),
                  content: SelectableText('${record['source']}\nUser-Agent: ALMG/1.0 $contact\nYour contact email will be sent to www.sec.gov. One request, at most 1 MiB, HTML or plain text only. Preview at most 50,000 characters. Linked resources are not loaded. Refreshing clears earlier reuse approval.'),
                  actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
                    FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Approve filing text request'))],
                ));
                if (confirmed == true) {
                  await _submit('/jobs/$id/review-filing', {'approved_url': record['source'], 'contact': contact,
                    'approved_byte_limit': 1048576});
                }
              }, child: const Text('Review filing text request')),
            ]),
          if (filingRecords.any((record) => collectableFiling(record as Map)))
            OutlinedButton(onPressed: _busy || selectedFilingUrls.isEmpty ? null
                : () => _submit('/jobs/$id/use-filing-previews', {'approved_urls': selectedFilingUrls}),
              child: Text('Approve filing preview collection (${selectedFilingUrls.length} selected)')),
          TextButton(onPressed: _busy ? null : () => _submit('/jobs/$id/close-filings', {}), child: const Text('Return to dataset approval')),
        ],
        if (status == 'bibliographic_candidates') ...[
          const Text('Approve collection of selected, reuse-approved abstracts for text classification. Publisher pages are not loaded.'),
          for (final record in bibliographyRecords)
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ListTile(
                  title: Text(record['title'] as String),
                  subtitle: SelectableText('DOI: ${record['doi']}\n${record['publisher']} · ${record['work_type']}\n${record['source']}\nApproved query: ${record['approved_query']}'),
                ),
                if (collectableBibliography(record as Map))
                  CheckboxListTile(
                    title: Text("Include abstract: ${record['title']}"),
                    value: !_excludedBibliography.contains(record['source']),
                    onChanged: _busy ? null : (checked) => setState(() {
                      final source = record['source'] as String;
                      if (checked == true) { _excludedBibliography.remove(source); }
                      else { _excludedBibliography.add(source); }
                    }),
                  ),
                if (record['abstract_reviewed'] == true) ...[
                  SelectableText((record['abstract'] as String).isEmpty ? 'No abstract was supplied for this DOI.' : 'Abstract: ${record['abstract']}'),
                  if ((record['license_statements'] as List).isEmpty)
                    const Text('No license links were supplied. Reuse remains unverified.'),
                  for (final license in record['license_statements'] as List)
                    SelectableText('Publisher license metadata: ${license['url']}\nContent version: ${license['content_version']}'),
                  const Text('License metadata does not establish permission for this abstract. Review its scope before reuse.'),
                ],
                if (record['abstract_reviewed'] == true &&
                    (record['abstract'] as String).isNotEmpty && (record['abstract'] as String).length < 40)
                  const Text('This abstract is too short for collection. At least 40 characters are required, even with reuse permission.'),
                if (record['reuse_approval'] case final Map approval)
                  SelectableText('Crossref abstract reuse approval: ${approval['permission_basis']}')
                else if (record['abstract_reviewed'] == true && (record['abstract'] as String).isNotEmpty)
                  TextButton(
                    onPressed: _busy ? null : () => _approveCatalogReuse(id as String, record,
                        action: 'approve-bibliography-reuse', scope: 'crossref_abstract'),
                    child: const Text('Record Crossref abstract reuse approval'),
                  ),
                const Text('Loads abstract and license metadata from api.crossref.org for this DOI. Loading clears earlier reuse approval. Publisher and license links are not fetched.'),
                OutlinedButton(
                  onPressed: _busy ? null : () => _submit('/jobs/$id/review-bibliography', {'approved_url': record['source']}),
                  child: const Text('Approve loading Crossref abstract metadata'),
                ),
              ],
            ),
          if (bibliographyRecords.any((record) => collectableBibliography(record as Map)))
            OutlinedButton(
              onPressed: _busy || selectedBibliographyUrls.isEmpty ? null
                  : () => _submit('/jobs/$id/use-bibliographic-abstracts', {'approved_urls': selectedBibliographyUrls}),
              child: Text('Approve abstract collection (${selectedBibliographyUrls.length} selected)'),
            ),
          TextButton(
            onPressed: _busy ? null : () => _submit('/jobs/$id/close-bibliography', {}),
            child: const Text('Return to dataset approval'),
          ),
        ],
        if (status == 'notice_candidates') ...[
          const Text('Review summaries and reuse permission before approving selected summaries for the dataset. Full-text loading is not available yet.'),
          for (final record in job?['notice_candidates'] as List? ?? const [])
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ListTile(
                  title: Text('${record['title']} (${record['document_number']})'),
                  subtitle: SelectableText('${record['source']}\nApproved query: ${record['approved_query']}'),
                  trailing: collectableNotice(record as Map) ? Checkbox(
                    value: !_excludedNotices.contains(record['source']),
                    semanticLabel: "Include document summary: ${record['title']}",
                    onChanged: _busy ? null : (checked) => setState(() {
                      final source = record['source'] as String;
                      if (checked == true) { _excludedNotices.remove(source); }
                      else { _excludedNotices.add(source); }
                    }),
                  ) : null,
                ),
                if (record['summary_reviewed'] == true)
                  SelectableText((record['summary'] as String).isEmpty
                      ? 'No summary was supplied for this document.' : 'Summary: ${record['summary']}'),
                if (record['reuse_approval'] case final Map approval)
                  SelectableText('Document summary reuse approval: ${approval['permission_basis']}')
                else if (record['summary_reviewed'] == true && (record['summary'] as String).isNotEmpty)
                  TextButton(
                    onPressed: _busy ? null : () => _approveCatalogReuse(id as String, record,
                        action: 'approve-notice-reuse', scope: 'document_summary'),
                    child: const Text('Record summary reuse approval'),
                  ),
                const Text('Loads summary metadata from www.federalregister.gov for this document. Loading clears earlier reuse approval.'),
                OutlinedButton(
                  onPressed: _busy ? null : () => _submit('/jobs/$id/review-notice', {'approved_url': record['source']}),
                  child: const Text('Approve loading document summary'),
                ),
              ],
            ),
          if (noticeRecords.any((record) => collectableNotice(record as Map)))
            OutlinedButton(
              onPressed: _busy || selectedNoticeUrls.isEmpty ? null
                  : () => _submit('/jobs/$id/use-notice-summaries', {'approved_urls': selectedNoticeUrls}),
              child: Text('Approve document summary collection (${selectedNoticeUrls.length} selected)'),
            ),
          TextButton(
            onPressed: _busy ? null : () => _submit('/jobs/$id/close-notices', {}),
            child: const Text('Return to dataset approval'),
          ),
        ],
        if (status == 'indicator_candidates') ...[
          Text('World Bank catalog page $indicatorPage of $indicatorPages · up to 20 indicators. '
              'Approve collection of selected, reuse-approved catalog descriptions for text classification. Country/year observations are not loaded.'),
          const Text('The catalog supplies no per-indicator reuse license. Review the source organization and applicable terms. Permission recorded here covers catalog descriptions only.'),
          const SelectableText('Terms reference: https://www.worldbank.org/ext/en/legal/terms-conditions'),
          TextField(
            controller: _indicatorFilter,
            maxLength: 160,
            decoration: const InputDecoration(labelText: 'Filter loaded catalog page'),
            onChanged: (_) => setState(() {}),
          ),
          Text('Showing ${visibleIndicators.length} of ${indicatorRecords.length} indicators on this loaded page. Filtering stays on this machine.'),
          if (_indicatorFilter.text.isNotEmpty)
            TextButton(
              onPressed: () => setState(() => _indicatorFilter.clear()),
              child: const Text('Clear indicator filter'),
            ),
          if (visibleIndicators.isEmpty)
            const Text('No indicators on this loaded page match. Clear the filter or review another catalog page.'),
          for (final record in visibleIndicators)
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ListTile(
                  title: Text('${record['title']} (${record['indicator_id']})'),
                  subtitle: SelectableText('${record['description']}\nSource ${record['source_id']}: ${record['source_name']}\n${record['organization']}\n${record['source']}'),
                  trailing: collectableIndicator(record) ? Checkbox(
                    value: !_excludedIndicators.contains(record['source']),
                    semanticLabel: "Include indicator description: ${record['title']}",
                    onChanged: _busy ? null : (checked) => setState(() {
                      final source = record['source'] as String;
                      if (checked == true) { _excludedIndicators.remove(source); }
                      else { _excludedIndicators.add(source); }
                    }),
                  ) : null,
                ),
                if (record['reuse_approval'] case final Map approval)
                  SelectableText('Catalog description reuse approval: ${approval['permission_basis']}')
                else
                  TextButton(
                    onPressed: _busy ? null : () => _approveCatalogReuse(id as String, record,
                        action: 'approve-indicator-reuse', scope: 'catalog_description'),
                    child: const Text('Record description reuse approval'),
                  ),
              ],
            ),
          if (visibleIndicators.any(collectableIndicator)) ...[
            const Text('Collection includes only selected descriptions visible under this filter.'),
            OutlinedButton(
              onPressed: _busy || selectedIndicatorUrls.isEmpty ? null
                  : () => _submit('/jobs/$id/use-indicator-descriptions', {'approved_urls': selectedIndicatorUrls}),
              child: Text('Approve indicator description collection (${selectedIndicatorUrls.length} selected)'),
            ),
          ],
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
          const Text('Review reuse rights for each excerpt before collection. Permission recorded here covers the displayed excerpt only.'),
          const SelectableText('Licensing reference: https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use#7._Licensing_of_Content'),

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
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
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
                value: collectableWikipediaExcerpt(candidate as Map) && !_excludedTextSources.contains(candidate['source']),
                onChanged: _busy || !collectableWikipediaExcerpt(candidate)
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
            if (candidate['reuse_approval'] case final Map approval)
              SelectableText('Wikipedia excerpt reuse approval: ${approval['permission_basis']}')
            else
              TextButton(onPressed: _busy ? null : () => _approveCatalogReuse(id as String, candidate,
                  action: 'approve-wikipedia-reuse', scope: 'wikipedia_excerpt'),
                child: const Text('Record excerpt reuse approval')),
            ]),
          const Text(
            'ALMG labels only selected, reuse-approved search excerpts locally. '
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
        if (status == 'cancelled') ...[
          Text(_imageRecipe
            ? 'Reopen the saved dataset for fresh approval. Image fitting restarts; this recipe has no partial-fit checkpoint.'
            : 'Reopen the saved dataset for approval. Matching candidate checkpoints will be reused; unfinished fits restart.'),
          OutlinedButton(onPressed: _busy ? null : () => _submit('/jobs/$id/reopen-cancelled', {'confirmed': true}),
            child: const Text('Reopen cancelled training dataset')),
        ],
        if (status == 'dataset_ready') ...[
          if (!_imageRecipe)
            OutlinedButton(
              onPressed: _busy ? null : () => _importDataset(id as String),
              child: const Text('Replace dataset with CSV'),
            ),
          if (!_imageRecipe) ...[
            OutlinedButton(onPressed: _busy ? null : () => _submit('/jobs/$id/review-labels', {'confirmed': true}),
              child: const Text('Review label ambiguity locally')),
            const Text('Uses the local model to flag uncertain labels. Suggestions may be wrong; labels stay unchanged and training still needs approval.'),
            if ((job?['label_reviewed_rows'] as int? ?? 0) > 0)
              Text('Local label review: ${job?['label_reviewed_rows']} examples reviewed, ${job?['label_review_flags']} flagged.'),
          ],
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
          if ((job?['word_variant_groups'] as int? ?? 0) > 0)
            Text('Near-duplicate groups (one-word differences): ${job?['word_variant_groups']}. '
              'Review their labels. These phrases stay together in evaluation splits.'),
          if ((job?['ambiguous_variant_groups'] as int? ?? 0) > 0)
            Text('Potential label ambiguity: ${job?['ambiguous_variant_groups']} similar-text groups have different labels. '
              'Check whether the changed word justifies the label. These examples remain usable.'),
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
                        if (row['label_review'] is Map && row['label_review']['ambiguous'] == true)
                          'Local model review: ${row['label_review']['reason']}'
                            '${row['label_review']['model'] == null ? '' : '\nReview model: ${row['label_review']['model']}'}',
                        if (row['possible_label_ambiguity'] == true) 'Potential label ambiguity · Review changed word',
                        if (row['word_variant'] == true) 'One-word variant · Review label',
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
                                      : row['provider'] == 'world_bank'
                                          ? 'Indicator: $title'
                                          : row['provider'] == 'federal_register'
                                              ? 'Document: $title'
                                              : 'Article: $title',
                        if ({'loc', 'europe_pmc', 'wikidata', 'world_bank', 'federal_register', 'crossref', 'sec_edgar', 'project_website', 'wikipedia', 'local_index'}.contains(row['provider']) && row['reuse_approval'] is Map)
                          'User reuse approval: ${row['reuse_approval']['permission_basis']}',
                        if (row['provider'] == 'wikipedia' && row['reuse_approval'] is Map) 'Content scope: search excerpt',
                        if (row['collection_origin'] == 'project_index') ...[
                          'Loaded from this project’s local page index.',
                          'Original provider: ${row['source_provider']}',
                          'Stored content scope: ${row['collection_scope'] ?? 'collected text'}',
                        ],
                        if (row['provider'] == 'crossref') 'Content scope: abstract',
                        if (row['provider'] == 'project_website') ...[
                          'Content scope: website page preview',
                          'Discovered from: ${row['discovered_from']}',
                          if (row['site_access_approval'] is Map) 'Site access review: ${row['site_access_approval']['access_basis']}',
                          if (row['page_text_truncated'] == true) 'Text truncated to the reviewed preview.',
                        ],
                        if (row['provider'] == 'sec_edgar') ...[
                          'Content scope: filing preview',
                          'CIK ${row['cik']} · ${row['form']} · ${row['filing_date']}',
                          'Accession: ${row['accession']}',
                          if (row['filing_text_truncated'] == true) 'Text truncated to the reviewed preview.',
                        ],
                        if (row['provider'] == 'federal_register') ...[
                          'Content scope: document summary',
                          'Document number: ${row['document_number']}',
                        ],
                        if (row['provider'] == 'world_bank') ...[
                          'Content scope: catalog description',
                          'Source ${row['source_id']}: ${row['source_name']}',
                          'Source organization: ${row['organization']}',
                        ],
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
      if (!_imageRecipe) 'allow_repair': _allowRepair,
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

class _DecoderTrialGoalDialog extends StatefulWidget {
  const _DecoderTrialGoalDialog();

  @override
  State<_DecoderTrialGoalDialog> createState() => _DecoderTrialGoalDialogState();
}

class _DecoderTrialGoalDialogState extends State<_DecoderTrialGoalDialog> {
  final _input = TextEditingController();

  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Plan a local decoder trial'),
    content: SizedBox(width: 520, child: TextField(controller: _input, autofocus: true, maxLength: 3000, maxLines: 4,
      decoration: const InputDecoration(labelText: 'Trial goal', helperText: 'Local Qwen recommends an approach. Only a tiny generated-text trial can run.'))),
    actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
      TextButton(onPressed: () => Navigator.pop(context, _input.text), child: const Text('Ask local Qwen'))],
  );
}
