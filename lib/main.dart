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
import 'private_decoder_page.dart';
import 'local_backend_client.dart';
import 'streamed_source_client.dart';
import 'stream_index_records_dialog.dart';
import 'stream_index_export_client.dart';
import 'local_text_documents.dart';
import 'stream_model_batches_dialog.dart';

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
  final _backend = LocalBackendClient();
  late Future<Map<String, dynamic>> _models = _load();
  String _query = '';

  Future<Map<String, dynamic>> _request(String path, [Map<String, dynamic>? body]) => _backend.request(path, body);

  Future<Map<String, dynamic>> _load() => _request('/models');

  @override
  void dispose() {
    _backend.close();
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
    body: FutureBuilder<Map<String, dynamic>>(
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
        final allModels = [
          ...(snapshot.data!['models'] as List? ?? const []).cast<Map>(),
          ...(snapshot.data!['private_imports'] as List? ?? const []).cast<Map>(),
        ];
        if (allModels.isEmpty) {
          return const Center(
            child: Text('Trained candidates, releases and imported private decoders will appear here.'),
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
                        final privateImport = model['kind'] == 'private_decoder_import';
                        final missing =
                            (model['missing_files'] as List?) ?? const [];
                        final availability = missing.isEmpty
                            ? ''
                            : privateImport ? '\nUnavailable: ${missing.join(' ')}' : '\nMissing local files: ${missing.join(', ')}';
                        final created = model['created_at'] as num?;
                        final date = created == null
                            ? ''
                            : ' · ${MaterialLocalizations.of(context).formatCompactDate(DateTime.fromMillisecondsSinceEpoch((created * 1000).round()))}';
                        final recipe = switch (model['recipe']) {
                          'text_to_image' => 'Text to image',
                          'decoder_from_scratch' => 'Private decoder',
                          _ => 'Text classifier',
                        };
                        final stateLabel = privateImport ? 'Private CPU preview · evaluation claims unverified'
                            : model['status'] == 'passed' ? 'Released' : 'Candidate';
                        return ListTile(
                          leading: const Icon(Icons.memory),
                          title: Text(
                            model['name'] as String,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                          subtitle: Text(
                            "${model['project']} · $recipe · $stateLabel$date$availability",
                          ),
                          trailing: const Icon(Icons.chevron_right),
                          onTap: missing.isNotEmpty
                              ? null
                              : () => Navigator.of(context).push(
                                  MaterialPageRoute<void>(
                                    builder: (_) => privateImport
                                        ? PrivateDecoderPage(importId: model['id'] as String, name: model['name'] as String, request: _request)
                                        : StudioPage(initialModel: model['id'] as String),
                                  ),
                                ).then((_) {
                                  if (mounted) setState(() => _models = _load());
                                }),
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
  bool _decoderRequireIdle = false;
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
              'factory_review',
              'factory_trial',
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
        {'approval', 'clarification', 'factory_review', 'factory_trial', 'preview_ready'}.contains(_job?['status'])
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
        TextButton(onPressed: () { Navigator.pop(context); _reviewDecoderSourcePermission(manifest); }, child: const Text('Review source permissions')),
        TextButton(onPressed: () { Navigator.pop(context); _trainBpeExperiment(manifest); }, child: const Text('Train byte BPE experiment')),
        TextButton(onPressed: () { Navigator.pop(context); _trainBpeExperiment(manifest, algorithm: 'character_bpe'); }, child: const Text('Train character BPE experiment')),
        TextButton(onPressed: () { Navigator.pop(context); _savedTokenizerExperiments(manifest['id'] as String); }, child: const Text('View saved tokenizer experiments')),
        TextButton(onPressed: () { Navigator.pop(context); _mixDecoderDatasets(manifest); }, child: const Text('Mix with another local dataset')),
        TextButton(onPressed: () { Navigator.pop(context); _identifyDecoderLanguages(manifest['id'] as String); }, child: const Text('Identify local document languages')),
        TextButton(onPressed: () { Navigator.pop(context); _savedDecoderLanguages(manifest['id'] as String); }, child: const Text('View saved language reports')),
        TextButton(onPressed: () { Navigator.pop(context); _extendDecoderDataset(manifest); }, child: const Text('Add documents to new version')),
        TextButton(onPressed: () { Navigator.pop(context); _exportDecoderDataset(manifest['id'] as String); }, child: const Text('Review local dataset export')),
        TextButton(onPressed: () { Navigator.pop(context); _auditDecoderDataset(manifest['id'] as String); }, child: const Text('Analyze local text quality')),
        TextButton(onPressed: () { Navigator.pop(context); _showSavedDecoderAudits(manifest['id'] as String); }, child: const Text('View saved quality audits')),

        if (manifest['tokenizer'] != null && !(manifest['findings'] as List).any((finding) =>
            ['tokenizer_limits', 'out_of_training_vocabulary'].contains(finding['kind'])))
          TextButton(onPressed: () {
            Navigator.pop(context);
            _approveDatasetTrial(manifest);
          }, child: const Text('Review bounded decoder training')),
        if (manifest['tokenizer'] != null && !(manifest['findings'] as List).any((finding) =>
            ['tokenizer_limits', 'out_of_training_vocabulary'].contains(finding['kind'])))
          TextButton(onPressed: () {
            Navigator.pop(context);
            _planDecoderTrial(dataset: manifest);
          }, child: const Text('Plan with reviewed dataset')),
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
      ],
    ));
  }

  Future<void> _trainBpeExperiment(Map<String, dynamic> dataset, {String algorithm = 'byte_level_bpe'}) async {
    final character = algorithm == 'character_bpe';
    final cap = await showDialog<int>(context: context, builder: (context) => SimpleDialog(
      title: Text(character ? 'Choose character BPE vocabulary cap' : 'Choose byte BPE vocabulary cap'), children: [
        for (final size in (character ? [64, 128, 256, 512] : [256, 272, 320, 512])) SimpleDialogOption(onPressed: () => Navigator.pop(context, size), child: Text('$size tokens maximum')),
      ]));
    if (cap == null || !mounted) return;
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: Text(character ? 'Fit character BPE on the training split?' : 'Fit byte BPE on the training split?'),
      content: Text('${character ? 'Character BPE fits its alphabet from training only and rejects unseen characters without refitting. Coverage gaps will be reported; token-efficiency ratios compare encodable records only. ' : 'Byte BPE keeps the complete byte alphabet. '}Fit deterministic pair merges on ${dataset['splits']['train']} training records only, with a $cap-token vocabulary cap. '
        'Samples must fit 4096 UTF-8 bytes; this experiment supports at most 16 documents. Each unique training record contributes once; mixture weights are not expanded. Validation/test records are encoded for comparison and never fitted. '
        'Check NFC Unicode round trips and compare token counts with the fixed byte alphabet. Learned tokens may encode private training phrases. '
        'This saves a separate tokenizer experiment; the dataset tokenizer is preserved. Model training with this artifact, special tokens and Unigram are unavailable.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm BPE fitting'))]));
    if (confirmed != true || !mounted) return;
    try {
      final experiment = await _request('/decoder-datasets/${dataset['id']}/tokenizer-experiments',
        {'confirmed': true, 'reviewed': dataset, 'config': {'vocabulary_cap': cap, 'algorithm': algorithm}}, const Duration(minutes: 2));
      if (mounted) await _showTokenizerExperiment(experiment);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _showTokenizerExperiment(Map<String, dynamic> experiment) async {
    await showDialog<void>(context: context, builder: (context) => AlertDialog(
      title: Text(experiment['algorithm'] == 'character_bpe' ? 'Character BPE experiment verified' : 'Byte BPE experiment verified'), scrollable: true,
      content: SizedBox(width: 620, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('${experiment['vocabulary_size']} vocabulary entries · cap ${experiment['config']['vocabulary_cap']}'),
        const Text('Training records only were fitted. Encodable records passed NFC round-trip checks. Coverage gaps are retained without refitting or substitution. This experiment does not enable model training.'),
        for (final split in ['train', 'validation', 'test']) ...[
          Text('$split: ${experiment['comparison'][split]['documents_encoded'] ?? experiment['comparison'][split]['documents']}/${experiment['comparison'][split]['documents']} records encoded · ${experiment['comparison'][split]['uncovered_character_count'] ?? 0} uncovered characters'),
          Text('Encodable records: ${experiment['comparison'][split]['encoded_baseline_byte_tokens'] ?? experiment['comparison'][split]['baseline_byte_tokens']} byte tokens → ${experiment['comparison'][split]['bpe_tokens'] ?? 'unavailable'} BPE tokens'),
        ],
        SelectableText(const JsonEncoder.withIndent('  ').convert(experiment)),
      ])),
      actions: [TextButton(onPressed: () { Navigator.pop(context); _exportTokenizerExperiment(experiment); }, child: const Text('Export private tokenizer experiment')),
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))]));
  }

  Future<void> _savedTokenizerExperiments(String datasetId) async {
    try {
      final experiments = (await _request('/decoder-datasets/$datasetId/tokenizer-experiments'))['experiments'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved tokenizer experiments'), children: [
          if (experiments.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved tokenizer experiments.')),
          for (final experiment in experiments) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(experiment as Map)),
            child: Text('${(experiment['id'] as String).substring(0, 8)} · ${experiment['algorithm']} · ${experiment['vocabulary_size']} tokens')),
        ]));
      if (selected != null && mounted) await _showTokenizerExperiment(selected);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _exportTokenizerExperiment(Map<String, dynamic> experiment) async {
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Export private BPE tokenizer?'),
      content: const Text('Save the fitted tokenizer and comparison manifest in a private ZIP. Learned tokens may encode private training phrases. Dataset documents and model weights are excluded. No training approval is included.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Choose tokenizer ZIP destination'))]));
    if (confirmed != true || !mounted) return;
    try {
      final destination = await getSaveLocation(suggestedName: 'tokenizer-experiment-${(experiment['id'] as String).substring(0, 8)}.zip',
        acceptedTypeGroups: [const XTypeGroup(label: 'Private tokenizer ZIP', extensions: ['zip'])]);
      if (destination == null || !mounted) return;
      final result = await _request('/decoder-tokenizer-experiments/${experiment['id']}/export', {'confirmed': true, 'reviewed': experiment});
      await XFile.fromData(base64Decode(result['data'] as String), mimeType: 'application/zip', name: result['name'] as String).saveTo(destination.path);
      if (!mounted) return;
      await showDialog<void>(context: context, builder: (context) => AlertDialog(title: const Text('Private tokenizer ZIP saved'), content: Text(destination.path),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))]));
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _reviewDecoderSourcePermission(Map<String, dynamic> parent) async {
    final source = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
      title: const Text('Select source bytes to review'), children: [
        for (final source in parent['sources'] as List) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(source as Map)),
          child: Text('${source['name']} · ${(source['source_sha256'] as String).substring(0, 8)} · ${source['license']}')),
      ],
    ));
    if (source == null || !mounted) return;
    final basis = await showDialog<String>(context: context, builder: (context) => SimpleDialog(
      title: const Text('Choose user-declared source basis'), children: [
        SimpleDialogOption(onPressed: () => Navigator.pop(context, 'user_created'), child: const Text('I created this source')),
        SimpleDialogOption(onPressed: () => Navigator.pop(context, 'permission_recorded'), child: const Text('I have recorded permission')),
        SimpleDialogOption(onPressed: () => Navigator.pop(context, 'needs_review'), child: const Text('Needs further permission review')),
      ],
    ));
    if (basis == null || !mounted) return;
    var note = '';
    final confirmed = await showDialog<bool>(context: context, builder: (context) => StatefulBuilder(builder: (context, update) => AlertDialog(
      title: const Text('Review source declaration'),
      content: SizedBox(width: 520, child: Column(mainAxisSize: MainAxisSize.min, children: [
        Text('Source: ${source['name']}\nBasis: $basis\nThis records your declaration for these source bytes in a new version. '
          'It does not verify permission or transfer training approval. Original data is preserved. Notes are included in local exports.'),
        TextField(autofocus: true, maxLength: 1000, maxLines: 3, onChanged: (value) => update(() => note = value),
          decoration: const InputDecoration(labelText: 'Evidence or source note (required)')),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: note.trim().isEmpty ? null : () => Navigator.pop(context, true), child: const Text('Confirm source declaration'))],
    )));
    if (confirmed != true || !mounted) return;
    try {
      final dataset = await _request('/decoder-datasets/${parent['id']}/source-permission', {
        'confirmed': true, 'reviewed': parent, 'source_sha256': source['source_sha256'], 'basis': basis, 'note': note,
      });
      if (mounted) await _showDecoderDataset(dataset);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _mixDecoderDatasets(Map<String, dynamic> parent) async {
    try {
      final datasets = (await _request('/decoder-datasets'))['datasets'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Select a second local dataset'), children: [
          for (final dataset in datasets)
            if (dataset['id'] != parent['id']) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(dataset as Map)),
              child: Text('${(dataset['id'] as String).substring(0, 8)} · ${dataset['unique_documents']} documents')),
        ],
      ));
      if (selected == null || !mounted) return;
      final weight = await showDialog<int>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Review local dataset mixture'), children: [
          Padding(padding: const EdgeInsets.all(16), child: Text('Combine ${parent['unique_documents']} and ${selected['unique_documents']} saved records into a new version. '
            'Shared records are deduplicated and their weights added. Weights repeat training windows only; evaluation is unweighted. '
            'Splits and tokenizer are rebuilt; UTF-8 bytes are used if either parent uses them. Review the new version before training. Parents stay unchanged.')),
          SimpleDialogOption(onPressed: () => Navigator.pop(context, 1), child: const Text('Confirm equal mixture (1:1)')),
          SimpleDialogOption(onPressed: () => Navigator.pop(context, 2), child: const Text('Confirm selected dataset emphasis (1:2)')),
        ],
      ));
      if (weight == null || !mounted) return;
      final result = await _request('/decoder-dataset-mixtures', {'confirmed': true, 'selections': [
        {'dataset': parent, 'weight': 1}, {'dataset': selected, 'weight': weight},
      ]});
      if (mounted) await _showDecoderDataset(result);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _showDecoderLanguages(Map<String, dynamic> report) async {
    await showDialog<void>(context: context, builder: (context) => AlertDialog(
      title: const Text('Local document languages'), scrollable: true,
      content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, children: [
        Text('${report['identified_records']} identified · ${report['unknown_records']} unknown. Local estimates do not change data or training approval. Short, mixed or unsupported text may remain unknown.'),
        SelectableText(const JsonEncoder.withIndent('  ').convert(report)),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
    ));
  }

  Future<void> _identifyDecoderLanguages(String id) async {
    try {
      final report = await _request('/decoder-datasets/$id/languages', {'confirmed': true});
      if (mounted) await _showDecoderLanguages(report);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _savedDecoderLanguages(String id) async {
    try {
      final reports = (await _request('/decoder-datasets/$id/languages'))['reports'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved language reports'), children: [
          if (reports.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved language reports.')),
          for (final report in reports) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(report as Map)),
            child: Text('${(report['revision'] as String).substring(0, 8)} · ${report['identified_records']} identified · ${report['unknown_records']} unknown')),
        ],
      ));
      if (selected != null && mounted) await _showDecoderLanguages(selected);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _extendDecoderDataset(Map<String, dynamic> parent) async {
    try {
      final files = await openFiles(acceptedTypeGroups: localTextTypes);
      if (files.isEmpty) return;
      if (files.length + (parent['unique_documents'] as int) > 16) {
        throw const FormatException('The combined dataset supports at most 16 documents. Prepare a separate dataset.');
      }
      final documents = await readLocalTextDocuments(files);
      if (!mounted) return;
      final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
        title: const Text('Add documents to new dataset version?'),
        content: Text('Add ${files.length} selected local documents to ${parent['unique_documents']} saved documents. '
          'The parent dataset is preserved. The combined version rebuilds its tokenizer and splits and needs a new review. '
          'This does not start training.'),
        actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm additional documents'))],
      ));
      if (confirmed != true || !mounted) return;
      final result = await _request('/decoder-datasets/${parent['id']}/extend', {
        'confirmed': true, 'reviewed': parent, 'documents': documents,
      });
      if (mounted) await _showDecoderDataset(result);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _exportDecoderDataset(String id) async {
    try {
      final review = await _request('/decoder-datasets/$id/export-review', {'confirmed': true});
      if (!mounted) return;
      final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
        title: const Text('Review local dataset export'), scrollable: true,
        content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Text('Save a private local ZIP containing normalized document text, saved tokenizer, split manifest and source names, hashes, licenses, permission notes and derivation lineage. '
            'Text and source names may include personal information. This does not collect data, start training or include training approvals. File hashes are checked again before saving.'),
          SelectableText(const JsonEncoder.withIndent('  ').convert(review)),
        ])),
        actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Save private dataset ZIP'))],
      ));
      if (confirmed != true || !mounted) return;
      final destination = await getSaveLocation(suggestedName: 'decoder-dataset-${id.substring(0, 8)}.zip',
        acceptedTypeGroups: [const XTypeGroup(label: 'Private dataset ZIP', extensions: ['zip'])]);
      if (destination == null || !mounted) return;
      final result = await _request('/decoder-datasets/$id/export', {'confirmed': true, 'revision': review['revision']});
      await XFile.fromData(base64Decode(result['data'] as String), mimeType: 'application/zip', name: result['file_name'] as String).saveTo(destination.path);
      if (!mounted) return;
      await showDialog<void>(context: context, builder: (context) => AlertDialog(
        title: const Text('Private dataset ZIP saved'), content: Text(destination.path),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ));
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _showDecoderAudit(Map<String, dynamic> report) async {
    await showDialog<void>(context: context, builder: (context) => AlertDialog(
      title: const Text('Decoder dataset quality audit'), scrollable: true,
      content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Text('Local heuristic findings highlight records for review. Likely contact details are flagged by location without copying matched values; other personal information may remain. Original data and training approvals are preserved. This audit does not filter text or start training.'),
        if (report['quality_review_records'] != null)
          Text('Text hygiene review: ${report['quality_review_records']} records below the heuristic threshold. Scores do not assess meaning or factual accuracy.'),
        if ((report['token_distribution'] as Map?)?['available'] == true)
          Text('Saved tokenizer: ${(report['token_distribution'] as Map)['overall']['token_count']} tokens · '
            '${(report['token_distribution'] as Map)['overall']['unknown_tokens']} outside vocabulary'),
        SelectableText(const JsonEncoder.withIndent('  ').convert(report)),
      ])),
      actions: [
        if ((report['privacy_matches'] as num? ?? 0) > 0)
          TextButton(onPressed: () { Navigator.pop(context); _redactDecoderDataset(report); }, child: const Text('Create redacted dataset version')),
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
      ],
    ));
  }

  Future<void> _redactDecoderDataset(Map<String, dynamic> report) async {
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Create redacted dataset version?'),
      content: Text('Replace ${report['privacy_matches']} detected contact details with [CONTACT_REDACTED] in a new local dataset. '
        'The original dataset is preserved. Splits and tokenizer are rebuilt and need a new review. '
        'Other personal information may remain. This does not start training.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm redacted version'))],
    ));
    if (confirmed != true || !mounted) return;
    try {
      final dataset = await _request('/decoder-datasets/${report['dataset_id']}/redact', {
        'confirmed': true, 'audit_revision': report['revision'],
      });
      if (mounted) await _showDecoderDataset(dataset);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _auditDecoderDataset(String id) async {
    try {
      final report = await _request('/decoder-datasets/$id/audit', {'confirmed': true});
      if (mounted) await _showDecoderAudit(report);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _showSavedDecoderAudits(String id) async {
    try {
      final reports = (await _request('/decoder-datasets/$id/audits'))['audits'] as List;
      if (!mounted) return;
      final report = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved dataset quality audits'), children: [
          if (reports.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved audits yet.')),
          for (final report in reports) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(report as Map)),
            child: Text('${(report['revision'] as String).substring(0, 8)} · ${report['near_duplicate_pairs']} near-duplicate pairs · ${report['cross_split_pairs']} cross-split pairs · ${report['privacy_matches'] ?? 0} privacy matches')),
        ],
      ));
      if (report != null && mounted) await _showDecoderAudit(report);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _approveDatasetTrial(Map<String, dynamic> dataset) async {
    final approved = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Approve local dataset trial'),
      content: Text('Train a tiny decoder from new weights on ${dataset['unique_documents']} reviewed documents. '
        'The trial uses the saved train/validation/test splits, 100 training steps, seed 7 and immediate Metal execution. '
        'Exact duplicate documents are excluded; near-duplicate overlap across evaluation splits blocks training. '
        'Cancellation and checkpoint resume remain available. '
        'This experimental trial does not release a model.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Approve training on reviewed dataset'))],
    ));
    if (approved == true && mounted) await _startDecoderTrial(dataset: dataset);
  }

  Future<void> _selectFactoryDataset() async {
    try {
      final datasets = (await _request('/decoder-datasets'))['datasets'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Select reviewed decoder dataset'), children: [
          if (datasets.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('Prepare local text documents in Training recipe details first.')),
          for (final dataset in datasets) SimpleDialogOption(
            onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(dataset as Map)),
            child: Text('${(dataset['id'] as String).substring(0, 8)} · ${dataset['unique_documents']} documents'),
          ),
        ],
      ));
      if (selected == null || !mounted) return;
      final dataset = await _request('/decoder-datasets/${selected['id']}');
      if (!mounted) return;
      final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
        title: const Text('Review dataset for this conversation'), scrollable: true,
        content: SizedBox(width: 620, child: SelectableText(const JsonEncoder.withIndent('  ').convert(dataset))),
        actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Use reviewed dataset for planning'))],
      ));
      if (confirmed == true && mounted) {
        await _submit('/jobs/${_job!['id']}/plan-decoder-dataset', {
          'confirmed': true, 'dataset': dataset,
        });
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _showDatasetProviders() async {
    try {
      final contract = await _request('/decoder-provider-contract');
      if (!mounted) return;
      await showDialog<void>(context: context, builder: (context) => AlertDialog(
        title: const Text('Optional dataset providers'), scrollable: true,
        content: SizedBox(width: 620, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('No external data provider is connected. Local dataset preparation remains available. '
            'Future optional connections must preserve source permissions and provenance, and require the app’s collection consent. '
            'ADAP is an example of a possible adapter; no ADAP connection is included.'),
          ExpansionTile(title: const Text('View versioned provider requirements'), children: [
            SelectableText(const JsonEncoder.withIndent('  ').convert(contract)),
          ]),
        ])),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ));
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _exportStreamIndex(String indexId) async {
    var overlay = false;
    try {
      final review = await _request('/decoder-stream-indexes/$indexId/export-review', {'confirmed': true}, const Duration(minutes: 10));
      if (!mounted) return;
      final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
        title: const Text('Review private text-index export'), scrollable: true,
        content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Text('Save a new private folder with normalized document text in SQLite, its immutable manifest and an export receipt. '
            'This includes original text values and may include personal information. Source names, hashes and first-line locations are preserved. '
            'Recorded source permission declarations and notes are included in the receipt. The original raw-source file, saved audits and training approvals are excluded. Nothing is uploaded or released.'),
          SelectableText(const JsonEncoder.withIndent('  ').convert(review)),
        ])),
        actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Choose local export folder'))],
      ));
      if (confirmed != true || !mounted) return;
      final parent = await getDirectoryPath(confirmButtonText: 'Choose export folder');
      if (parent == null || !mounted) return;
      var completed = 0; var total = 1; var cancel = false; StateSetter? refresh;
      overlay = true;
      unawaited(showDialog<void>(context: context, barrierDismissible: false, builder: (context) => PopScope(canPop: false,
        child: StatefulBuilder(builder: (context, update) {
          refresh = update;
          return AlertDialog(title: const Text('Saving private text index'), content: Column(mainAxisSize: MainAxisSize.min, children: [
            LinearProgressIndicator(value: completed / total), Text('$completed / $total bytes copied; file hashes are verified before completion.'),
          ]), actions: [TextButton(onPressed: () => cancel = true, child: const Text('Cancel index export'))]);
        }))));
      final destination = await saveStreamIndexExport(review, Directory(parent),
        (path, body) => _request(path, body, const Duration(minutes: 10)), (path) async {
          final hashed = await Process.run('/usr/bin/shasum', ['-a', '256', '--', path]);
          final match = RegExp(r'^[a-fA-F0-9]{64}(?=\s)').firstMatch(hashed.stdout.toString());
          if (hashed.exitCode != 0 || match == null) throw const FormatException('The exported file hash could not be verified.');
          return match.group(0)!.toLowerCase();
        }, onProgress: (copied, expected) { completed = copied; total = expected; if (mounted) refresh?.call(() {}); }, shouldCancel: () => cancel);
      refresh = null;
      if (!mounted) return;
      Navigator.pop(context); overlay = false;
      await showDialog<void>(context: context, builder: (context) => AlertDialog(
        title: const Text('Private text index saved'), content: SelectableText(destination.path),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ));
    } on StreamIndexExportCancelled {
      if (mounted && overlay) Navigator.pop(context);
    } catch (error) {
      if (mounted) { if (overlay) Navigator.pop(context); setState(() => _error = error.toString()); }
    }
  }

  Future<void> _reviewStreamSourcePermissions(String indexId) async {
    try {
      final review = await _request('/decoder-stream-indexes/$indexId/source-permissions', null, const Duration(minutes: 10));
      if (!mounted) return;
      final add = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
        title: const Text('Streamed source permission history'), scrollable: true,
        content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Text('Declarations apply to the original source bytes and are saved separately from the unchanged index. '
            'They are user assertions, not verified permission or training approval. All recorded notes are included in future private index export receipts.'),
          SelectableText(const JsonEncoder.withIndent('  ').convert(review)),
        ])),
        actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Close')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Add source permission declaration'))],
      ));
      if (add != true || !mounted) return;
      final basis = await showDialog<String>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Choose streamed source basis'), children: [
          SimpleDialogOption(onPressed: () => Navigator.pop(context, 'user_created'), child: const Text('I created this source')),
          SimpleDialogOption(onPressed: () => Navigator.pop(context, 'permission_recorded'), child: const Text('I have recorded permission')),
          SimpleDialogOption(onPressed: () => Navigator.pop(context, 'needs_review'), child: const Text('Needs further permission review')),
        ],
      ));
      if (basis == null || !mounted) return;
      var note = '';
      final confirmed = await showDialog<bool>(context: context, builder: (context) => StatefulBuilder(builder: (context, update) => AlertDialog(
        title: const Text('Review streamed source declaration'),
        content: SizedBox(width: 520, child: Column(mainAxisSize: MainAxisSize.min, children: [
          Text('Source: ${review['source_provenance']['source_name']}\nBasis: $basis\n'
            'Append an immutable declaration without changing source data. Permission is not verified; no training approval is granted. Notes are included in private exports.'),
          TextField(autofocus: true, maxLength: 1000, maxLines: 3, onChanged: (value) => update(() => note = value),
            decoration: const InputDecoration(labelText: 'Streamed source evidence note (required)')),
        ])),
        actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(onPressed: note.trim().isEmpty ? null : () => Navigator.pop(context, true), child: const Text('Confirm streamed source declaration'))],
      )));
      if (confirmed != true || !mounted) return;
      await _request('/decoder-stream-indexes/$indexId/source-permissions', {
        'confirmed': true, 'reviewed': review, 'basis': basis, 'note': note,
      }, const Duration(minutes: 10));
      if (mounted) await _reviewStreamSourcePermissions(indexId);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _showStreamOverlap(Map<String, dynamic> record) async {
    final resume = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: Text('Streamed overlap · ${record['status']}'), scrollable: true,
      content: SizedBox(width: 620, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('${record['processed_pairs']} / ${record['total_pairs']} unique-record pairs checked.'),
        const Text('Exhaustive five-word shingle Jaccard check at 0.8 similarity, for records of at least 12 words. '
          'Quadratic comparison cost; large indexes can take a long time. Short pairs are skipped. Lexical findings do not establish complete contamination detection or training approval.'),
        Text('${record['near_duplicate_pairs']} near-duplicate pairs · ${record['cross_split_pairs']} cross-split pairs · ${record['short_pairs_skipped']} short pairs skipped'),
        ExpansionTile(title: const Text('View streamed overlaps and provenance'), children: [
          SelectableText(const JsonEncoder.withIndent('  ').convert(record)),
        ]),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Close')),
        if (record['status'] == 'complete') TextButton(onPressed: () {
          Navigator.pop(context, false);
          showDialog<void>(context: this.context, builder: (context) => StreamIndexRecordsDialog(
            indexId: record['id'] as String, recordsPath: '/decoder-stream-overlap/${record['id']}/records',
            title: 'Review streamed overlap records', description: 'Lexical overlap findings with both source locations. Split filters match either endpoint. Original texts are omitted; training remains disabled.',
            request: (path, body) => _request(path, body)));
        }, child: const Text('Review overlap findings')),
        if (record['status'] != 'complete') TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Resume streamed overlaps'))],
    ));
    if (resume == true && mounted) await _runStreamOverlap(record);
  }

  Future<void> _beginStreamOverlap(Map<String, dynamic> index) async {
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Analyze streamed overlaps?'),
      content: Text('Compare all pairs among ${index['unique_records']} unique normalized records with the existing five-word Jaccard rule. '
        'This has quadratic comparison cost and can take a long time for large indexes. Save resumable findings without changing the source or approving training.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm streamed overlap scan'))],
    ));
    if (confirmed != true || !mounted) return;
    try {
      final record = await _request('/decoder-stream-indexes/${index['id']}/overlap', {'confirmed': true}, const Duration(minutes: 10));
      if (mounted) await _runStreamOverlap(record);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _savedStreamOverlap(String indexId) async {
    try {
      final reports = (await _request('/decoder-stream-indexes/$indexId/overlap'))['reports'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved streamed overlap reports'), children: [
          if (reports.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved streamed overlaps.')),
          for (final report in reports) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(report as Map)),
            child: Text('${(report['id'] as String).substring(0, 8)} · ${report['status']} · ${report['processed_pairs']}/${report['total_pairs']} analyzed')),
        ],
      ));
      if (selected != null && mounted) await _showStreamOverlap(selected);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _runStreamOverlap(Map<String, dynamic> initial) async {
    var record = initial; var pause = false; var overlay = true; StateSetter? refresh;
    unawaited(showDialog<void>(context: context, barrierDismissible: false, builder: (context) => PopScope(canPop: false,
      child: StatefulBuilder(builder: (context, update) {
        refresh = update;
        return AlertDialog(title: const Text('Analyzing streamed overlaps'), content: Column(mainAxisSize: MainAxisSize.min, children: [
          LinearProgressIndicator(value: (record['total_pairs'] as num) == 0 ? 0 : (record['processed_pairs'] as num) / (record['total_pairs'] as num)),
          Text('${record['processed_pairs']} / ${record['total_pairs']} analyzed'),
        ]), actions: [TextButton(onPressed: () => pause = true, child: const Text('Pause streamed overlaps'))]);
      }))));
    try {
      while (!pause && record['status'] != 'complete') {
        record = await _request('/decoder-stream-overlap/${initial['id']}/step', {'confirmed': true}, const Duration(minutes: 10));
        if (!mounted) return;
        refresh?.call(() {});
      }
      refresh = null;
      if (!mounted) return;
      Navigator.pop(context); overlay = false;
      await _showStreamOverlap(record);
    } catch (error) {
      refresh = null;
      if (mounted) { if (overlay) Navigator.pop(context); setState(() => _error = error.toString()); }
    }
  }

  Future<void> _showStreamWindows(Map<String, dynamic> record) async {
    final resume = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: Text('Streamed windows · ${record['status']}'), scrollable: true,
      content: SizedBox(width: 620, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('${record['processed_records']} / ${record['total_records']} unique normalized records analyzed.'),
        const Text('Source-bound next-token windows, with original document boundaries and splits preserved. '
          'Token IDs can reconstruct personal text. The lexical overlap gate is limited; no model training or approval is enabled.'),
        Text('Windows by split: ${record['window_counts']} · ${record['target_tokens']} target tokens'),
        ExpansionTile(title: const Text('View streamed windows and provenance'), children: [
          SelectableText(const JsonEncoder.withIndent('  ').convert(record)),
        ]),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Close')),
        if (record['status'] == 'complete') TextButton(onPressed: () {
          Navigator.pop(context, false);
          showDialog<void>(context: this.context, builder: (context) => StreamIndexRecordsDialog(
            indexId: record['id'] as String, recordsPath: '/decoder-stream-windows/${record['id']}/records',
            title: 'Review streamed window records', description: 'Token IDs encode original text. Source references and split boundaries are preserved; training remains disabled.',
            request: (path, body) => _request(path, body)));
        }, child: const Text('Review token windows')),
        if (record['status'] == 'complete') TextButton(onPressed: () {
          Navigator.pop(context, false);
          showDialog<void>(context: this.context, builder: (context) => StreamModelBatchesDialog(
            reviewed: record, request: (path, body) => _request(path, body, const Duration(minutes: 10))));
        }, child: const Text('Inspect model input batches')),
        if (record['status'] == 'complete') TextButton(onPressed: () { Navigator.pop(context, false); _planStreamedApproach(record); }, child: const Text('Plan streamed approach')),
        if (record['status'] == 'complete') TextButton(onPressed: () { Navigator.pop(context, false); _savedStreamedPlans(record); }, child: const Text('View saved streamed plans')),
        if (record['status'] != 'complete') TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Resume streamed windows'))],
    ));
    if (resume == true && mounted) await _runStreamWindows(record);
  }

  Future<void> _showStreamedPlan(Map<String, dynamic> plan) async {
    final acknowledged = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Review streamed approach plan'), scrollable: true,
      content: SizedBox(width: 620, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Recommended approach: ${plan['approach']}'),
        Text('Planner: ${plan['planner']?['model'] ?? plan['planner']?['provider'] ?? 'Unspecified'}'),
        Text(plan['reason'] as String),
        const Text('Planning only. Full streamed training, scheduling and checkpoint recovery are unavailable. Acknowledging this plan does not approve or start training. Source evidence is rechecked before acknowledgment.'),
        SelectableText(const JsonEncoder.withIndent('  ').convert(plan)),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Close')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Acknowledge plan only'))],
    ));
    if (acknowledged != true || !mounted) return;
    try {
      final receipt = await _request('/decoder-stream-plans/${plan['id']}/acknowledge', {'confirmed': true, 'reviewed': plan});
      if (!mounted) return;
      await showDialog<void>(context: context, builder: (context) => AlertDialog(title: const Text('Plan acknowledged · training unavailable'),
        scrollable: true, content: SelectableText(const JsonEncoder.withIndent('  ').convert(receipt)),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))]));
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _planStreamedApproach(Map<String, dynamic> windows) async {
    final goal = await showDialog<String>(context: context, builder: (context) => const _DecoderTrialGoalDialog(planningOnly: true));
    if (goal == null || !mounted) return;
    var waiting = true;
    unawaited(showDialog<void>(context: context, barrierDismissible: false, builder: (context) => const AlertDialog(
      title: Text('Asking local Qwen'), content: Text('Planning from dataset counts and evidence revisions only. No source text or token arrays are sent.'))));
    try {
      final plan = await _request('/decoder-stream-windows/${windows['id']}/plans', {'confirmed': true, 'reviewed': windows, 'goal': goal}, const Duration(seconds: 120));
      if (!mounted) return;
      Navigator.pop(context); waiting = false;
      await _showStreamedPlan(plan);
    } catch (error) { if (mounted) { if (waiting) Navigator.pop(context); setState(() => _error = error.toString()); } }
  }

  Future<void> _savedStreamedPlans(Map<String, dynamic> windows) async {
    try {
      final plans = (await _request('/decoder-stream-windows/${windows['id']}/saved-plans', {'confirmed': true}))['plans'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved streamed plans'), children: [
          if (plans.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved streamed plans.')),
          for (final plan in plans) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(plan as Map)),
            child: Text('${(plan['id'] as String).substring(0, 8)} · ${plan['approach']} · planning only')),
        ]));
      if (selected != null && mounted) await _showStreamedPlan(selected);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _beginStreamWindows(Map<String, dynamic> tokenizer) async {
    try {
      final indexId = tokenizer['index_id'] as String;
      final reports = (await _request('/decoder-stream-indexes/$indexId/overlap'))['reports'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Select completed overlap evidence'), children: [
          if (reports.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('Run streamed overlap analysis first.')),
          for (final report in reports) if (report['status'] == 'complete') SimpleDialogOption(
            onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(report as Map)),
            child: Text('${(report['id'] as String).substring(0, 8)} · ${report['cross_split_pairs']} cross-split pairs · ${report['short_pairs_skipped']} short pairs skipped')),
        ],
      ));
      if (selected == null || !mounted) return;
      final index = await _request('/decoder-stream-indexes/$indexId');
      if (!mounted) return;
      final reviewed = {'index': index, 'tokenizer': tokenizer, 'overlap': selected};
      final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
        title: const Text('Prepare source-bound token windows?'), scrollable: true,
        content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Text('Save next-token windows of at most 17 byte IDs, with stride 16, without crossing document boundaries. '
            'A completed matching overlap report with zero cross-split findings is required; short or semantic overlap can remain unchecked. '
            'Token IDs encode original text and may contain personal information. No model training or approval starts.'),
          SelectableText(const JsonEncoder.withIndent('  ').convert(reviewed)),
        ])),
        actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm streamed token windows'))],
      ));
      if (confirmed != true || !mounted) return;
      final record = await _request('/decoder-stream-tokenizers/${tokenizer['id']}/windows', {
        'confirmed': true, 'overlap_id': selected['id'], 'reviewed': reviewed,
      }, const Duration(minutes: 10));
      if (mounted) await _runStreamWindows(record);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _savedStreamWindows(String indexId) async {
    try {
      final reports = (await _request('/decoder-stream-indexes/$indexId/windows'))['reports'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved streamed window reports'), children: [
          if (reports.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved streamed windows.')),
          for (final report in reports) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(report as Map)),
            child: Text('${(report['id'] as String).substring(0, 8)} · ${report['status']} · ${report['processed_records']}/${report['total_records']} analyzed')),
        ],
      ));
      if (selected != null && mounted) await _showStreamWindows(selected);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _runStreamWindows(Map<String, dynamic> initial) async {
    var record = initial; var pause = false; var overlay = true; StateSetter? refresh;
    unawaited(showDialog<void>(context: context, barrierDismissible: false, builder: (context) => PopScope(canPop: false,
      child: StatefulBuilder(builder: (context, update) {
        refresh = update;
        return AlertDialog(title: const Text('Analyzing streamed windows'), content: Column(mainAxisSize: MainAxisSize.min, children: [
          LinearProgressIndicator(value: (record['total_records'] as num) == 0 ? 0 : (record['processed_records'] as num) / (record['total_records'] as num)),
          Text('${record['processed_records']} / ${record['total_records']} analyzed'),
        ]), actions: [TextButton(onPressed: () => pause = true, child: const Text('Pause streamed windows'))]);
      }))));
    try {
      while (!pause && record['status'] != 'complete') {
        record = await _request('/decoder-stream-windows/${initial['id']}/step', {'confirmed': true}, const Duration(minutes: 10));
        if (!mounted) return;
        refresh?.call(() {});
      }
      refresh = null;
      if (!mounted) return;
      Navigator.pop(context); overlay = false;
      await _showStreamWindows(record);
    } catch (error) {
      refresh = null;
      if (mounted) { if (overlay) Navigator.pop(context); setState(() => _error = error.toString()); }
    }
  }

  Future<void> _showStreamLanguages(Map<String, dynamic> record) async {
    final resume = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: Text('Streamed languages · ${record['status']}'), scrollable: true,
      content: SizedBox(width: 620, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('${record['processed_records']} / ${record['total_records']} unique normalized records analyzed.'),
        const Text('Optional local dominant-language estimates only. Short, mixed or unsupported text can be unknown. '
          'Source data remains unchanged; no filtering or training approval is granted.'),
        Text('${record['identified_records']} identified · ${record['unknown_records']} unknown · ${record['unavailable_batches']} unavailable batches'),
        Text('Language counts: ${record['language_counts']}'),
        ExpansionTile(title: const Text('View streamed languages and provenance'), children: [
          SelectableText(const JsonEncoder.withIndent('  ').convert(record)),
        ]),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Close')),
        if (record['status'] == 'complete') TextButton(onPressed: () {
          Navigator.pop(context, false);
          showDialog<void>(context: this.context, builder: (context) => StreamIndexRecordsDialog(
            indexId: record['id'] as String, recordsPath: '/decoder-stream-languages/${record['id']}/records',
            title: 'Review streamed language records', description: 'Dominant-language estimates with source references. Original text is omitted. Unknown is retained; no training policy changes.',
            request: (path, body) => _request(path, body)));
        }, child: const Text('Review language records')),
        if (record['status'] != 'complete') TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Resume streamed languages'))],
    ));
    if (resume == true && mounted) await _runStreamLanguages(record);
  }

  Future<void> _beginStreamLanguages(Map<String, dynamic> index) async {
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Analyze streamed languages?'),
      content: Text('Identify the dominant language of all ${index['unique_records']} unique normalized records with the optional local recognizer. '
        'Save resumable per-record estimates and split counts without storing text or changing the source index. No collection or training starts.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm streamed language scan'))],
    ));
    if (confirmed != true || !mounted) return;
    try {
      final record = await _request('/decoder-stream-indexes/${index['id']}/languages', {'confirmed': true}, const Duration(minutes: 10));
      if (mounted) await _runStreamLanguages(record);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _savedStreamLanguages(String indexId) async {
    try {
      final reports = (await _request('/decoder-stream-indexes/$indexId/languages'))['reports'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved streamed language reports'), children: [
          if (reports.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved streamed languages.')),
          for (final report in reports) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(report as Map)),
            child: Text('${(report['id'] as String).substring(0, 8)} · ${report['status']} · ${report['processed_records']}/${report['total_records']} analyzed')),
        ],
      ));
      if (selected != null && mounted) await _showStreamLanguages(selected);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _runStreamLanguages(Map<String, dynamic> initial) async {
    var record = initial; var pause = false; var overlay = true; StateSetter? refresh;
    unawaited(showDialog<void>(context: context, barrierDismissible: false, builder: (context) => PopScope(canPop: false,
      child: StatefulBuilder(builder: (context, update) {
        refresh = update;
        return AlertDialog(title: const Text('Analyzing streamed languages'), content: Column(mainAxisSize: MainAxisSize.min, children: [
          LinearProgressIndicator(value: (record['total_records'] as num) == 0 ? 0 : (record['processed_records'] as num) / (record['total_records'] as num)),
          Text('${record['processed_records']} / ${record['total_records']} analyzed'),
        ]), actions: [TextButton(onPressed: () => pause = true, child: const Text('Pause streamed languages'))]);
      }))));
    try {
      while (!pause && record['status'] != 'complete') {
        record = await _request('/decoder-stream-languages/${initial['id']}/step', {'confirmed': true}, const Duration(minutes: 10));
        if (!mounted) return;
        refresh?.call(() {});
      }
      refresh = null;
      if (!mounted) return;
      Navigator.pop(context); overlay = false;
      await _showStreamLanguages(record);
    } catch (error) {
      refresh = null;
      if (mounted) { if (overlay) Navigator.pop(context); setState(() => _error = error.toString()); }
    }
  }

  Future<void> _showStreamTokenizer(Map<String, dynamic> tokenizer) async {
    await showDialog<void>(context: context, builder: (context) => AlertDialog(
      title: const Text('Saved streamed byte tokenizer'), scrollable: true,
      content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Text('Fixed 256-byte alphabet with training-only provenance. Every indexed record was checked against the existing 4096-byte document limit. '
          'This artifact does not fit a vocabulary or grant training/evaluation approval.'),
        SelectableText(const JsonEncoder.withIndent('  ').convert(tokenizer)),
      ])), actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
        TextButton(onPressed: () { Navigator.pop(context); _beginStreamWindows(tokenizer); }, child: const Text('Prepare streamed token windows'))],
    ));
  }

  Future<void> _saveStreamTokenizer(Map<String, dynamic> report) async {
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Save fixed-byte tokenizer?'),
      content: const Text('Save the existing fixed UTF-8 byte alphabet, binding only training-split text in stable group order. '
        'Validate every record against the current tokenizer limits. Validation and test text are excluded from the training hash. '
        'The final scan uses bounded reads and can take time for large indexes; publication is atomic. No training starts.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm streamed byte tokenizer'))],
    ));
    if (confirmed != true || !mounted) return;
    try {
      final tokenizer = await _request('/decoder-stream-byte-statistics/${report['id']}/tokenizer', {'confirmed': true, 'reviewed': report}, const Duration(minutes: 10));
      if (mounted) await _showStreamTokenizer(tokenizer);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _savedStreamTokenizers(String indexId) async {
    try {
      final tokenizers = (await _request('/decoder-stream-indexes/$indexId/tokenizers'))['tokenizers'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved streamed tokenizers'), children: [
          if (tokenizers.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved streamed tokenizers.')),
          for (final tokenizer in tokenizers) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(tokenizer as Map)),
            child: Text('${(tokenizer['id'] as String).substring(0, 8)} · fixed UTF-8 bytes · ${tokenizer['split_counts']['train']} training records')),
        ],
      ));
      if (selected != null && mounted) await _showStreamTokenizer(selected);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _showStreamByteStatistics(Map<String, dynamic> record) async {
    final resume = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: Text('Byte token distribution · ${record['status']}'), scrollable: true,
      content: SizedBox(width: 620, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('${record['processed_records']} / ${record['total_records']} unique normalized records analyzed.'),
        const Text('Fixed UTF-8 byte alphabet only. Counts exclude special tokens; repeated source occurrences are reported separately. '
          'Records over 4096 bytes exceed the current byte tokenizer’s document limit. No tokenizer is fitted and training remains disabled.'),
        for (final entry in (record['splits'] as Map).entries)
          Text('${entry.key}: ${entry.value['unique_records']} records · ${entry.value['tokens']} byte tokens · '
            '${entry.value['records_over_current_tokenizer_limit']} over the document limit'),
        ExpansionTile(title: const Text('View byte statistics and provenance'), children: [
          SelectableText(const JsonEncoder.withIndent('  ').convert(record)),
        ]),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Close')),
        if (record['status'] == 'complete') TextButton(onPressed: () {
          Navigator.pop(context, false); _saveStreamTokenizer(record);
        }, child: const Text('Save streamed byte tokenizer')),
        if (record['status'] != 'complete') TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Resume byte statistics'))],
    ));
    if (resume == true && mounted) await _runStreamByteStatistics(record);
  }

  Future<void> _beginStreamByteStatistics(Map<String, dynamic> index) async {
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Analyze byte token distribution?'),
      content: Text('Scan all ${index['unique_records']} unique normalized records using the fixed UTF-8 byte alphabet. '
        'Save resumable counts by split without storing text or changing the source index. This does not fit a tokenizer or approve training.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm byte statistics'))],
    ));
    if (confirmed != true || !mounted) return;
    try {
      final record = await _request('/decoder-stream-indexes/${index['id']}/byte-statistics', {'confirmed': true}, const Duration(minutes: 10));
      if (mounted) await _runStreamByteStatistics(record);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _savedStreamByteStatistics(String indexId) async {
    try {
      final reports = (await _request('/decoder-stream-indexes/$indexId/byte-statistics'))['reports'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved byte statistics'), children: [
          if (reports.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved byte statistics.')),
          for (final report in reports) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(report as Map)),
            child: Text('${(report['id'] as String).substring(0, 8)} · ${report['status']} · ${report['processed_records']}/${report['total_records']} analyzed')),
        ],
      ));
      if (selected != null && mounted) await _showStreamByteStatistics(selected);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _runStreamByteStatistics(Map<String, dynamic> initial) async {
    var record = initial; var pause = false; var overlay = true; StateSetter? refresh;
    unawaited(showDialog<void>(context: context, barrierDismissible: false, builder: (context) => PopScope(canPop: false,
      child: StatefulBuilder(builder: (context, update) {
        refresh = update;
        return AlertDialog(title: const Text('Analyzing byte distribution'), content: Column(mainAxisSize: MainAxisSize.min, children: [
          LinearProgressIndicator(value: (record['total_records'] as num) == 0 ? 0 : (record['processed_records'] as num) / (record['total_records'] as num)),
          Text('${record['processed_records']} / ${record['total_records']} analyzed'),
        ]), actions: [TextButton(onPressed: () => pause = true, child: const Text('Pause byte statistics'))]);
      }))));
    try {
      while (!pause && record['status'] != 'complete') {
        record = await _request('/decoder-stream-byte-statistics/${initial['id']}/step', {'confirmed': true}, const Duration(minutes: 10));
        if (!mounted) return;
        refresh?.call(() {});
      }
      refresh = null;
      if (!mounted) return;
      Navigator.pop(context); overlay = false;
      await _showStreamByteStatistics(record);
    } catch (error) {
      refresh = null;
      if (mounted) { if (overlay) Navigator.pop(context); setState(() => _error = error.toString()); }
    }
  }

  Future<void> _showStreamAudit(Map<String, dynamic> record) async {
    final action = await showDialog<String>(context: context, builder: (context) => AlertDialog(
      title: Text('Full-index audit · ${record['status']}'), scrollable: true,
      content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, children: [
        Text('${record['processed_records']} / ${record['total_records']} unique records checked · '
          '${record['hygiene_review_records']} hygiene reviews · ${record['privacy_records']} records with potential contacts.'),
        const Text('Raw text is omitted. These local heuristics do not establish complete PII detection, evaluation cleanliness or training approval. Source data remains unchanged.'),
        SelectableText(const JsonEncoder.withIndent('  ').convert(record)),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
        if (record['status'] != 'complete') TextButton(onPressed: () => Navigator.pop(context, 'resume'), child: const Text('Resume full-index audit')),
        if (record['status'] == 'complete') TextButton(onPressed: () => Navigator.pop(context, 'findings'), child: const Text('Review full-index findings'))],
    ));
    if (!mounted) return;
    if (action == 'resume') { await _runStreamAudit(record); return; }
    if (action == 'findings') {
      await showDialog<void>(context: context, builder: (context) => StreamIndexRecordsDialog(
        indexId: record['id'] as String, recordsPath: '/decoder-stream-audits/${record['id']}/records',
        title: 'Review full-index audit findings', description: 'Read-only diagnostic findings. Original text is omitted; inspect indexed source records separately. Current hygiene/contact heuristics do not grant training approval.',
        request: (path, body) => _request(path, body)));
    }
  }

  Future<void> _savedStreamAudits(String indexId) async {
    try {
      final audits = (await _request('/decoder-stream-indexes/$indexId/audits'))['audits'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved full-index audits'), children: [
          if (audits.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved full-index audits.')),
          for (final audit in audits) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(audit as Map)),
            child: Text('${(audit['id'] as String).substring(0, 8)} · ${audit['status']} · ${audit['processed_records']}/${audit['total_records']} checked')),
        ],
      ));
      if (selected != null && mounted) await _showStreamAudit(selected);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _beginStreamAudit(Map<String, dynamic> index) async {
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Audit the complete text index?'),
      content: Text('Check all ${index['unique_records']} unique normalized records with the current local hygiene and contact-detail heuristics. '
        'Save resumable findings and source references without copying raw text. This does not filter stored data, change training approval or perform comprehensive contamination checks.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm full-index audit'))],
    ));
    if (confirmed != true || !mounted) return;
    try {
      final record = await _request('/decoder-stream-indexes/${index['id']}/audits', {'confirmed': true}, const Duration(minutes: 10));
      if (mounted) await _runStreamAudit(record);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _runStreamAudit(Map<String, dynamic> initial) async {
    var record = initial; var pause = false; var overlay = true; StateSetter? refresh;
    unawaited(showDialog<void>(context: context, barrierDismissible: false, builder: (context) => PopScope(canPop: false,
      child: StatefulBuilder(builder: (context, update) {
        refresh = update;
        return AlertDialog(title: const Text('Auditing full text index'), content: Column(mainAxisSize: MainAxisSize.min, children: [
          LinearProgressIndicator(value: (record['total_records'] as num) == 0 ? 0 : (record['processed_records'] as num) / (record['total_records'] as num)),
          Text('${record['processed_records']} / ${record['total_records']} checked'),
        ]), actions: [TextButton(onPressed: () => pause = true, child: const Text('Pause full-index audit'))]);
      }))));
    try {
      while (!pause && record['status'] != 'complete') {
        record = await _request('/decoder-stream-audits/${initial['id']}/step', {'confirmed': true}, const Duration(minutes: 10));
        if (!mounted) return;
        refresh?.call(() {});
      }
      refresh = null;
      if (!mounted) return;
      Navigator.pop(context); overlay = false;
      await _showStreamAudit(record);
    } catch (error) {
      refresh = null;
      if (mounted) { if (overlay) Navigator.pop(context); setState(() => _error = error.toString()); }
    }
  }

  Future<void> _beginStreamRedaction(Map<String, dynamic> parent) async {
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Create contact-filtered text index?'),
      content: Text('Process all ${parent['unique_records']} unique records with the current contact patterns and replace detected spans with [CONTACT_REDACTED]. '
        'Create a new index with exact deduplication and fresh hash-based splits. Keep the original index and per-record lineage. '
        'Parent permission declarations are retained as a snapshot; notes are not filtered. Other personal information may remain. '
        'The result needs a new review and does not inherit audits, training approval or evaluation cleanliness.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm filtered index'))],
    ));
    if (confirmed != true || !mounted) return;
    try {
      final record = await _request('/decoder-stream-indexes/${parent['id']}/redact', {'confirmed': true, 'reviewed': parent}, const Duration(minutes: 10));
      if (mounted) await _runStreamIndex(record);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _showStreamIndex(Map<String, dynamic> record) async {
    final action = await showDialog<String>(context: context, builder: (context) => AlertDialog(
      title: Text('Streamed text index · ${record['status']}'), scrollable: true,
      content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Text('Line-based normalized text and exact-duplicate index. Source bytes are preserved. Full-index hygiene/contact audits are available. Training and broader evaluation integration are not yet enabled.'),
        SelectableText(const JsonEncoder.withIndent('  ').convert(record)),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
        if (record['status'] == 'complete') TextButton(onPressed: () => Navigator.pop(context, 'records'), child: const Text('Review indexed records')),
        if (record['status'] == 'complete') TextButton(onPressed: () => Navigator.pop(context, 'audit'), child: const Text('Audit full text index')),
        if (record['status'] == 'complete' && (record['derivation'] as Map?)?['operation'] != 'contact_pattern_filter') TextButton(onPressed: () => Navigator.pop(context, 'redact'), child: const Text('Create contact-filtered index')),
        if (record['status'] == 'complete') TextButton(onPressed: () => Navigator.pop(context, 'permissions'), child: const Text('Review streamed source permissions')),
        if (record['status'] == 'complete') TextButton(onPressed: () => Navigator.pop(context, 'languages'), child: const Text('Identify streamed record languages')),
        if (record['status'] == 'complete') TextButton(onPressed: () => Navigator.pop(context, 'overlap'), child: const Text('Analyze streamed record overlap')),
        if (record['status'] == 'complete') TextButton(onPressed: () => Navigator.pop(context, 'saved-overlap'), child: const Text('View saved streamed overlap reports')),
        if (record['status'] == 'complete') TextButton(onPressed: () => Navigator.pop(context, 'saved-languages'), child: const Text('View saved streamed language reports')),
        if (record['status'] == 'complete') TextButton(onPressed: () => Navigator.pop(context, 'byte-statistics'), child: const Text('Analyze byte token distribution')),
        if (record['status'] == 'complete') TextButton(onPressed: () => Navigator.pop(context, 'tokenizers'), child: const Text('View saved streamed tokenizers')),
        if (record['status'] == 'complete') TextButton(onPressed: () => Navigator.pop(context, 'windows'), child: const Text('View saved streamed token windows')),
        if (record['status'] == 'complete') TextButton(onPressed: () => Navigator.pop(context, 'saved-byte-statistics'), child: const Text('View saved byte statistics')),
        if (record['status'] == 'complete' && Platform.isMacOS) TextButton(onPressed: () => Navigator.pop(context, 'export'), child: const Text('Review private index export')),
        TextButton(onPressed: () => Navigator.pop(context, 'audits'), child: const Text('View saved full-index audits')),
        if (record['status'] != 'complete') TextButton(onPressed: () => Navigator.pop(context, 'resume'), child: const Text('Resume text indexing'))],
    ));
    if (!mounted) return;
    if (action == 'resume') {
      await _runStreamIndex(record);
      return;
    }
    if (action == 'records') {
      await showDialog<void>(context: context, builder: (context) => StreamIndexRecordsDialog(
        indexId: record['id'] as String, request: (path, body) => _request(path, body)));
      return;
    }
    if (action == 'export') await _exportStreamIndex(record['id'] as String);
    if (action == 'audit') await _beginStreamAudit(record);
    if (action == 'redact') await _beginStreamRedaction(record);
    if (action == 'permissions') await _reviewStreamSourcePermissions(record['id'] as String);
    if (action == 'languages') await _beginStreamLanguages(record);
    if (action == 'overlap') await _beginStreamOverlap(record);
    if (action == 'saved-overlap') await _savedStreamOverlap(record['id'] as String);
    if (action == 'saved-languages') await _savedStreamLanguages(record['id'] as String);
    if (action == 'byte-statistics') await _beginStreamByteStatistics(record);
    if (action == 'tokenizers') await _savedStreamTokenizers(record['id'] as String);
    if (action == 'windows') await _savedStreamWindows(record['id'] as String);
    if (action == 'saved-byte-statistics') await _savedStreamByteStatistics(record['id'] as String);
    if (action == 'audits') await _savedStreamAudits(record['id'] as String);
  }

  Future<void> _savedStreamIndexes(String sourceId) async {
    try {
      final indexes = (await _request('/decoder-streams/$sourceId/indexes'))['indexes'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved streamed text indexes'), children: [
          if (indexes.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved text indexes.')),
          for (final index in indexes) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(index as Map)),
            child: Text('${(index['id'] as String).substring(0, 8)} · ${index['status']} · ${index['lines']} lines · ${index['unique_records']} unique')),
        ],
      ));
      if (selected != null && mounted) await _showStreamIndex(selected);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _beginStreamIndex(Map<String, dynamic> source, {bool jsonl = false}) async {
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: Text(jsonl ? 'Prepare streamed JSONL text index?' : 'Prepare line-based text index?'),
      content: Text(jsonl ? 'Extract the text string from each nonblank JSONL line locally. Exactly one text field is required; unknown/duplicate fields, malformed JSON, invalid Unicode, empty text or unsupported limits reject the current transaction. Each original line must fit 64 KiB. Original source hashes, line numbers, byte offsets and raw-line hashes are preserved. Unicode/whitespace normalization, global exact deduplication and stable 80/10/10 split buckets apply. Processing is bounded and can pause/resume after restart. This creates a review index and never starts training.' : 'Treat each UTF-8 line as a document, normalize Unicode/whitespace and deduplicate exact normalized lines. '
        'Stable hash buckets assign train/validation/test splits (80/10/10). Empty lines are counted. '
        'Invalid UTF-8, oversized lines or unsupported word limits stop the current batch while preserving earlier progress. '
        'This creates an index for review and does not start training.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: Text(jsonl ? 'Confirm streamed JSONL preparation' : 'Confirm line-based preparation'))],
    ));
    if (confirmed != true || !mounted) return;
    try {
      final record = await _request('/decoder-streams/${source['id']}/${jsonl ? 'jsonl-indexes' : 'indexes'}', {'confirmed': true}, const Duration(minutes: 10));
      if (mounted) await _runStreamIndex(record);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _runStreamIndex(Map<String, dynamic> initial) async {
    var record = initial;
    final isRedaction = (initial['derivation'] as Map?)?['operation'] == 'contact_pattern_filter';
    var pause = false;
    StateSetter? refresh;
    var overlay = true;
    unawaited(showDialog<void>(context: context, barrierDismissible: false, builder: (context) => PopScope(canPop: false,
      child: StatefulBuilder(builder: (context, update) {
        refresh = update;
        return AlertDialog(title: Text(isRedaction ? 'Filtering streamed contacts' : 'Preparing streamed text'), content: Column(mainAxisSize: MainAxisSize.min, children: [
          LinearProgressIndicator(value: isRedaction
            ? ((record['total_parent_records'] as num) == 0 ? 0 : (record['processed_parent_records'] as num) / (record['total_parent_records'] as num))
            : (record['offset'] as num) / (record['source_bytes'] as num)),
          Text(isRedaction ? '${record['processed_parent_records']} / ${record['total_parent_records']} records · ${record['filtered_records']} filtered'
            : '${record['lines']} lines · ${record['unique_records']} unique records'),
        ]), actions: [TextButton(onPressed: () => pause = true, child: Text(isRedaction ? 'Pause contact filtering' : 'Pause text indexing'))]);
      }))));
    try {
      while (!pause && record['status'] != 'complete') {
        record = await _request('/decoder-stream-indexes/${initial['id']}/step', {'confirmed': true}, const Duration(minutes: 10));
        if (!mounted) return;
        refresh?.call(() {});
      }
      refresh = null;
      if (!mounted) return;
      Navigator.pop(context); overlay = false;
      await _showStreamIndex(record);
    } catch (error) {
      refresh = null;
      if (mounted) { if (overlay) Navigator.pop(context); setState(() => _error = error.toString()); }
    }
  }

  Future<void> _showStreamedSource(Map<String, dynamic> source) async {
    final action = await showDialog<String>(context: context, builder: (context) => AlertDialog(
      title: Text('Local source · ${source['status']}'), scrollable: true,
      content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Text('Original source is preserved. Line-based index preparation is available; training from large indexes is not yet enabled. Reopening an upload requires the same file hash.'),
        SelectableText(const JsonEncoder.withIndent('  ').convert(source)),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
        TextButton(onPressed: () => Navigator.pop(context, 'saved'), child: const Text('View saved text indexes')),
        if (source['status'] == 'stored_not_prepared') TextButton(onPressed: () => Navigator.pop(context, 'prepare'), child: const Text('Prepare streamed text index')),
        if (source['status'] == 'stored_not_prepared') TextButton(onPressed: () => Navigator.pop(context, 'prepare-jsonl'), child: const Text('Prepare JSONL text index')),
        if (source['status'] == 'uploading') TextButton(onPressed: () => Navigator.pop(context, 'upload'), child: const Text('Resume local source upload'))],
    ));
    if (!mounted) return;
    if (action == 'upload') await _uploadStreamedSource(existing: source);
    if (action == 'prepare') await _beginStreamIndex(source);
    if (action == 'prepare-jsonl') await _beginStreamIndex(source, jsonl: true);
    if (action == 'saved') await _savedStreamIndexes(source['id'] as String);
  }

  Future<void> _savedStreamedSources() async {
    try {
      final sources = (await _request('/decoder-streams'))['sources'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved streamed sources'), children: [
          if (sources.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No streamed local sources.')),
          for (final source in sources) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(source as Map)),
            child: Text('${(source['id'] as String).substring(0, 8)} · ${source['name']} · ${source['received_bytes']}/${source['total_bytes']} bytes · ${source['status']}')),
        ],
      ));
      if (selected != null && mounted) await _showStreamedSource(await _request('/decoder-streams/${selected['id']}'));
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _uploadStreamedSource({Map<String, dynamic>? existing}) async {
    var overlay = false;
    try {
      final file = await openFile(acceptedTypeGroups: [const XTypeGroup(label: 'Local text or JSONL source', extensions: ['txt', 'jsonl'])]);
      if (file == null || !mounted) return;
      final total = await file.length();
      if (!mounted) return;
      if (total < 1 || total > 1099511627776) throw const FormatException('Select a nonempty source of at most 1 TiB.');
      overlay = true;
      unawaited(showDialog<void>(context: context, barrierDismissible: false, builder: (context) => const PopScope(canPop: false,
        child: AlertDialog(title: Text('Hashing local source'), content: LinearProgressIndicator()))));
      final hashed = await Process.run('/usr/bin/shasum', ['-a', '256', '--', file.path]);
      final match = RegExp(r'^[a-fA-F0-9]{64}(?=\s)').firstMatch(hashed.stdout.toString());
      if (hashed.exitCode != 0 || match == null) throw const FormatException('The local source hash could not be read.');
      final sourceHash = match.group(0)!.toLowerCase();
      if (!mounted) return;
      Navigator.pop(context); overlay = false;
      var source = existing == null ? null : await _request('/decoder-streams/${existing['id']}');
      if (source != null && (source['source_sha256'] != sourceHash || source['total_bytes'] != total)) {
        throw const FormatException('This is not the original source. Select the file matching the saved hash.');
      }
      if (!mounted) return;
      final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
        title: Text(source == null ? 'Store local source in chunks?' : 'Resume saved source upload?'),
        content: Text('Store $total original bytes from ${file.name} privately on this machine. '
          'Copies use bounded batches of at most 1 MiB. Pause preserves the last completed batch; older uploads retain their advertised limits. '
          'This stores original bytes only. Text preparation needs separate confirmation and model training remains disabled.'),
        actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm local source upload'))],
      ));
      if (confirmed != true || !mounted) return;
      source ??= await _request('/decoder-streams', {'confirmed': true, 'name': file.name, 'total_bytes': total, 'source_sha256': sourceHash});
      if (!mounted) return;
      var received = source['received_bytes'] as int;
      var pause = false;
      StateSetter? refresh;
      overlay = true;
      unawaited(showDialog<void>(context: context, barrierDismissible: false, builder: (context) => PopScope(canPop: false,
        child: StatefulBuilder(builder: (context, update) {
          refresh = update;
          return AlertDialog(title: const Text('Uploading local source'), content: Column(mainAxisSize: MainAxisSize.min, children: [
            LinearProgressIndicator(value: received / total), Text('$received / $total bytes saved'),
          ]), actions: [TextButton(onPressed: () => pause = true, child: const Text('Pause source upload'))]);
        }))));
      final result = await sendStreamedSource(file, source, (path, body) => _request(path, body),
        onProgress: (value) { received = value; if (mounted) refresh?.call(() {}); }, shouldPause: () => pause);
      refresh = null;
      if (!mounted) return;
      Navigator.pop(context); overlay = false;
      await _showStreamedSource(result);
    } catch (error) {
      if (mounted) {
        if (overlay) Navigator.pop(context);
        setState(() => _error = error.toString());
      }
    }
  }

  Future<void> _showDecoderPreparation(Map<String, dynamic> draft) async {
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: Text('Saved preparation · ${draft['status']}'), scrollable: true,
      content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Text('Original inputs are saved locally. Preparation requires confirmation and never starts training. Interrupted publication reuses the same dataset ID.'),
        SelectableText(const JsonEncoder.withIndent('  ').convert(draft)),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Close')),
        if (draft['implementation_current'] == true || draft['status'] == 'complete')
          TextButton(onPressed: () => Navigator.pop(context, true), child: Text(draft['status'] == 'complete' ? 'Open prepared dataset' : 'Prepare saved inputs'))],
    ));
    if (confirmed != true || !mounted) return;
    try {
      final dataset = await _request('/decoder-preparations/${draft['id']}/prepare', {'confirmed': true});
      if (mounted) await _showDecoderDataset(dataset);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _showSavedPreparations() async {
    try {
      final drafts = (await _request('/decoder-preparations'))['drafts'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved local preparations'), children: [
          if (drafts.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved preparation drafts.')),
          for (final draft in drafts) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(draft as Map)),
            child: Text('${(draft['id'] as String).substring(0, 8)} · ${draft['status']} · ${draft['input_documents']} documents')),
        ],
      ));
      if (selected != null && mounted) await _showDecoderPreparation(selected);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _showHtmlPreparation(Map<String, dynamic> draft) async {
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: Text('Saved HTML preparation · ${draft['status']}'), scrollable: true,
      content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Text('Original HTML inputs and the extraction review are saved locally. Preparation requires confirmation, reuses the same dataset ID after interruptions and never starts training.'),
        if (draft['implementation_current'] != true && draft['status'] != 'complete')
          const Text('The extraction implementation changed. Keep this draft and start a newly reviewed HTML preparation.'),
        SelectableText(const JsonEncoder.withIndent('  ').convert(draft)),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Close')),
        if (draft['implementation_current'] == true || draft['status'] == 'complete')
          TextButton(onPressed: () => Navigator.pop(context, true), child: Text(draft['status'] == 'complete' ? 'Open prepared HTML dataset' : 'Prepare saved HTML inputs'))],
    ));
    if (confirmed != true || !mounted) return;
    try {
      final dataset = await _request('/decoder-html-preparations/${draft['id']}/prepare', {'confirmed': true});
      if (mounted) await _showDecoderDataset(dataset);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _savedHtmlPreparations() async {
    try {
      final drafts = (await _request('/decoder-html-preparations'))['drafts'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved HTML preparations'), children: [
          if (drafts.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved HTML preparations.')),
          for (final draft in drafts) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(draft as Map)),
            child: Text('${(draft['id'] as String).substring(0, 8)} · ${draft['status']} · ${draft['input_documents']} HTML documents')),
        ],
      ));
      if (selected != null && mounted) await _showHtmlPreparation(selected);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _prepareHtmlDataset() async {
    try {
      final files = await openFiles(acceptedTypeGroups: const [XTypeGroup(label: 'Local UTF-8 HTML', extensions: ['html', 'htm'])]);
      if (files.isEmpty) return;
      if (files.length < 3 || files.length > 16) throw const FormatException('Select 3 to 16 local HTML documents.');
      final documents = await readLocalTextDocuments(files);
      final review = await _request('/decoder-html-review', {'documents': documents});
      if (!mounted) return;
      final action = await showDialog<String>(context: context, builder: (context) => AlertDialog(
        title: const Text('Review local HTML extraction'), scrollable: true,
        content: SizedBox(width: 620, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Extract static body text locally. Scripts, styles, templates, head content and marked hidden sections are omitted; '
            'linked resources are not fetched and JavaScript is not run. This is not browser rendering. '
            'Create a new dataset with the existing UTF-8 byte tokenizer. Original HTML hashes are preserved in provenance; raw HTML is not included in prepared datasets. Saving a draft instead keeps the original inputs locally for explicit recovery after restart. No training starts.'),
          for (final source in review['sources'] as List) ...[
            Text('${source['name']} · ${source['original_bytes']} original bytes → ${source['extracted_bytes']} extracted bytes'),
            SelectableText(source['preview'] as String),
            if (source['preview_truncated'] == true) const Text('Preview limited to 512 characters.'),
          ],
          ExpansionTile(title: const Text('View extraction method and source hashes'), children: [
            SelectableText(const JsonEncoder.withIndent('  ').convert(review)),
          ]),
        ])),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, 'save'), child: const Text('Save HTML preparation draft')),
          TextButton(onPressed: () => Navigator.pop(context, 'prepare'), child: const Text('Confirm HTML dataset preparation'))],
      ));
      if (action == null || !mounted) return;
      if (action == 'save') {
        final draft = await _request('/decoder-html-preparations', {'documents': documents, 'confirmed': true, 'reviewed': review});
        if (mounted) await _showHtmlPreparation(draft);
        return;
      }
      final dataset = await _request('/decoder-html-datasets', {'documents': documents, 'confirmed': true, 'reviewed': review});
      if (mounted) await _showDecoderDataset(dataset);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _showJsonlPreparation(Map<String, dynamic> draft) async {
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: Text('Saved JSONL preparation · ${draft['status']}'), scrollable: true,
      content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Text('Original JSONL inputs and the extraction review are saved locally. Preparation requires confirmation, reuses the same dataset ID after interruptions and never starts training.'),
        if (draft['implementation_current'] != true && draft['status'] != 'complete')
          const Text('The extraction implementation changed. Keep this draft and start a newly reviewed JSONL preparation.'),
        SelectableText(const JsonEncoder.withIndent('  ').convert(draft)),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Close')),
        if (draft['implementation_current'] == true || draft['status'] == 'complete')
          TextButton(onPressed: () => Navigator.pop(context, true), child: Text(draft['status'] == 'complete' ? 'Open prepared JSONL dataset' : 'Prepare saved JSONL inputs'))],
    ));
    if (confirmed != true || !mounted) return;
    try {
      final dataset = await _request('/decoder-jsonl-preparations/${draft['id']}/prepare', {'confirmed': true});
      if (mounted) await _showDecoderDataset(dataset);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _savedJsonlPreparations() async {
    try {
      final drafts = (await _request('/decoder-jsonl-preparations'))['drafts'] as List;
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Saved JSONL preparations'), children: [
          if (drafts.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No saved JSONL preparations.')),
          for (final draft in drafts) SimpleDialogOption(onPressed: () => Navigator.pop(context, Map<String, dynamic>.from(draft as Map)),
            child: Text('${(draft['id'] as String).substring(0, 8)} · ${draft['status']} · ${draft['input_documents']} JSONL files · ${draft['text_records']} text records')),
        ],
      ));
      if (selected != null && mounted) await _showJsonlPreparation(selected);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _prepareJsonlDataset() async {
    try {
      final files = await openFiles(acceptedTypeGroups: const [XTypeGroup(label: 'Local UTF-8 JSONL text', extensions: ['jsonl'])]);
      if (files.isEmpty) return;
      final documents = await readLocalTextDocuments(files);
      final review = await _request('/decoder-jsonl-review', {'documents': documents});
      if (!mounted) return;
      final action = await showDialog<String>(context: context, builder: (context) => AlertDialog(
        title: const Text('Review local JSONL text import'), scrollable: true,
        content: SizedBox(width: 620, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Import 3 to 16 text records from bounded local JSONL files. Each nonblank line must be an object with exactly one string field named text; extra or duplicate fields are rejected. '
            'Each file must fit 64 KiB and the selection 128000 bytes. This is not streaming import. Original file and line hashes survive preprocessing and private export; raw JSONL is excluded. '
            'Saving a draft keeps the original JSONL inputs locally for explicit recovery after restart. Review the text for personal information and source permission. A new dataset uses the UTF-8 byte tokenizer and existing duplicate/split checks. No training starts.'),
          for (final source in review['sources'] as List) ...[
            Text('${source['name']} · ${source['original_bytes']} original bytes · ${source['blank_lines']} blank lines skipped'),
            for (final record in source['records'] as List) ...[
              Text('Line ${record['line']} · ${record['extracted_bytes']} text bytes'),
              SelectableText(record['preview'] as String),
              if (record['preview_truncated'] == true) const Text('Preview limited to 512 characters.'),
            ],
          ],
          ExpansionTile(title: const Text('View JSONL extraction method and source hashes'), children: [
            SelectableText(const JsonEncoder.withIndent('  ').convert(review)),
          ]),
        ])),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, 'save'), child: const Text('Save JSONL preparation draft')),
          TextButton(onPressed: () => Navigator.pop(context, 'prepare'), child: const Text('Confirm JSONL dataset preparation'))],
      ));
      if (action == null || !mounted) return;
      if (action == 'save') {
        final draft = await _request('/decoder-jsonl-preparations', {'documents': documents, 'confirmed': true, 'reviewed': review});
        if (mounted) await _showJsonlPreparation(draft);
        return;
      }
      final dataset = await _request('/decoder-jsonl-datasets', {'documents': documents, 'confirmed': true, 'reviewed': review});
      if (mounted) await _showDecoderDataset(dataset);
    } catch (error) { if (mounted) setState(() => _error = error.toString()); }
  }

  Future<void> _prepareDecoderDataset({bool saveDraft = false}) async {
    try {
      final files = await openFiles(acceptedTypeGroups: localTextTypes);
      if (files.isEmpty) return;
      if (files.length < 3 || files.length > 16) throw const FormatException('Select 3 to 16 text documents.');
      final documents = await readLocalTextDocuments(files);
      if (!mounted) return;
      final tokenizerKind = await showDialog<String>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Choose local tokenizer'), children: [
          SimpleDialogOption(onPressed: () => Navigator.pop(context, 'words'), child: const Text('Words · training vocabulary only (existing format)')),
          SimpleDialogOption(onPressed: () => Navigator.pop(context, 'utf8_bytes'), child: const Text('UTF-8 bytes · fixed alphabet, supports unseen words')),
        ],
      ));
      if (tokenizerKind == null || !mounted) return;
      if (saveDraft) {
        final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
          title: const Text('Save local preparation draft?'),
          content: Text('Save the ${files.length} selected original documents locally so preparation can be confirmed after restart. '
            'This does not publish a dataset or start training. The current bounded size limits apply.'),
          actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
            TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm saved inputs'))],
        ));
        if (confirmed != true || !mounted) return;
        final draft = await _request('/decoder-preparations', {'confirmed': true, 'documents': documents, 'tokenizer_kind': tokenizerKind});
        if (mounted) await _showDecoderPreparation(draft);
        return;
      }
      final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
        title: const Text('Review selected local documents'), scrollable: true,
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Create a new immutable dataset from these original UTF-8 files. Markdown formatting stays literal text; '
            'whitespace is normalized. Source names and original byte hashes are preserved. No training or external collection starts.'),
          for (final document in documents) Text('${document['name']} · ${base64Decode(document['data']!).length} bytes'),
          Text('Tokenizer: $tokenizerKind'),
        ]),
        actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm dataset preparation'))],
      ));
      if (confirmed != true || !mounted) return;
      final manifest = await _request('/decoder-datasets', {'confirmed': true, 'documents': documents, 'tokenizer_kind': tokenizerKind});
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

  Future<void> _planDecoderTrial({Map<String, dynamic>? dataset}) async {
    final goal = await showDialog<String>(context: context,
      builder: (context) => const _DecoderTrialGoalDialog());
    if (goal == null || goal.trim().isEmpty || !mounted) return;
    var waitingShown = true;
    unawaited(showDialog<void>(context: context, barrierDismissible: false, builder: (context) => const AlertDialog(
      title: Text('Asking local Qwen'),
      content: Row(mainAxisSize: MainAxisSize.min, children: [CircularProgressIndicator(), SizedBox(width: 16), Text('Preparing an approach proposal…')]),
    )));
    try {
      final proposal = await _request('/decoder-trial-proposals', {'goal': goal, 'dataset': ?dataset}, const Duration(seconds: 120));
      if (!mounted) return;
      Navigator.pop(context);
      waitingShown = false;
      final approved = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
        title: const Text('Review trial approach'),
        scrollable: true,
        content: SizedBox(width: 520, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Goal: ${proposal['goal']}'),
          Text('Recommended approach: ${proposal['approach']}'),
          Text('Registered recipe: ${proposal['recipe_contract']?['name'] ?? proposal['recipe']}'),
          Text('Planner: ${proposal['planner']?['model'] ?? proposal['planner']?['provider'] ?? 'Unspecified'}'),
          Text(proposal['reason'] as String),
          Text(dataset == null
            ? 'Scope: fixed generated local text. This trial does not release a model.'
            : 'Scope: reviewed dataset ${dataset['id']}, ${dataset['unique_documents']} documents; saved train/validation/test splits. New weights, 100 steps, seed 7, immediate Metal execution. This trial does not release a model.'),
          if (proposal['executable'] != true) const Text('This approach is unavailable in the decoder trial workflow. No execution will start.'),
        ])),
        actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Close')),
          if (proposal['executable'] == true) TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm from-scratch trial'))],
      ));
      if (approved == true && mounted) await _startDecoderTrial(proposal: proposal, dataset: dataset);
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
        TextButton(onPressed: () { Navigator.pop(context); _saveDecoderPipeline(record['id'] as String); }, child: const Text('Save and inspect pipeline manifest')),
        if (['waiting_idle', 'queued', 'running'].contains(record['status'])) TextButton(onPressed: () {
          Navigator.pop(context);
          _cancelDecoderTrial(record['id'] as String);
        }, child: const Text('Cancel saved decoder trial')),
        if (record['status'] == 'complete' && record['dataset'] is Map) TextButton(onPressed: () {
          Navigator.pop(context);
          _exportPrivateDecoder(record['id'] as String);
        }, child: const Text('Review private decoder export')),
        if (record['status'] == 'complete' && record['dataset'] is Map) TextButton(onPressed: () {
          Navigator.pop(context);
          _evaluateDecoderTrial(record['id'] as String);
        }, child: const Text('Re-evaluate saved decoder')),
        if (record['status'] == 'complete') TextButton(onPressed: () {
          Navigator.pop(context);
          _previewDecoderTrial(record['id'] as String);
        }, child: const Text('Preview private decoder')),
        if (record['status'] == 'interrupted') TextButton(onPressed: () {
          Navigator.pop(context);
          _startDecoderTrial(id: record['id'] as String);
        }, child: const Text('Approve resume of saved trial')),
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
      ],
    ));
  }

  Future<void> _saveDecoderPipeline(String id) async {
    try {
      final result = await _request('/decoder-trials/$id/pipeline', {'confirmed': true});
      if (!mounted) return;
      await showDialog<void>(context: context, builder: (context) => AlertDialog(
        title: const Text('Saved decoder pipeline manifest'), scrollable: true,
        content: SizedBox(width: 620, child: SelectableText(const JsonEncoder.withIndent('  ').convert(result))),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ));
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _exportPrivateDecoder(String id) async {
    try {
      final review = await _request('/decoder-trials/$id/export-review', {'confirmed': true});
      if (!mounted) return;
      final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
        title: const Text('Review private decoder export'), scrollable: true,
        content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Text('Save weights, tokenizer, versioned provenance and evaluation/preview receipts as a private ZIP. Preview receipts include your prompt. Dataset documents are excluded. This does not release a model. Evaluation and file hashes are checked again before saving.'),
          SelectableText(const JsonEncoder.withIndent('  ').convert(review)),
        ])),
        actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Save private decoder bundle'))],
      ));
      if (confirmed != true || !mounted) return;
      final destination = await getSaveLocation(suggestedName: 'decoder-private-${id.substring(0, 8)}.zip',
        acceptedTypeGroups: [const XTypeGroup(label: 'Private decoder ZIP', extensions: ['zip'])]);
      if (destination == null || !mounted) return;
      final result = await _request('/decoder-trials/$id/export', {'confirmed': true, 'revision': review['revision']});
      await XFile.fromData(base64Decode(result['data'] as String), mimeType: 'application/zip', name: result['file_name'] as String).saveTo(destination.path);
      if (!mounted) return;
      await showDialog<void>(context: context, builder: (context) => AlertDialog(
        title: const Text('Private decoder bundle saved'), content: Text(destination.path),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ));
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _evaluateDecoderTrial(String id) async {
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Re-evaluate private decoder'),
      content: const Text('Verify the saved bundle and reviewed dataset, then recompute training, validation and test metrics on CPU using the saved splits and tokenizer. The target remains 80%. This records a private evaluation and does not release a model.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Run local re-evaluation'))],
    ));
    if (confirmed != true || !mounted) return;
    try {
      final result = await _request('/decoder-trials/$id/evaluate', {'confirmed': true});
      if (!mounted) return;
      await showDialog<void>(context: context, builder: (context) => AlertDialog(
        title: const Text('Saved decoder evaluation'), scrollable: true,
        content: SizedBox(width: 620, child: SelectableText(const JsonEncoder.withIndent('  ').convert(result))),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ));
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _previewDecoderTrial(String id, {bool imported = false}) async {
    var prompt = '';
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Preview private decoder'),
      content: SizedBox(width: 520, child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Text('Use the saved tokenizer and fit the model context. Generate 12 tokens locally on CPU with greedy decoding. This does not release a model.'),
        TextField(autofocus: true, maxLength: 4096, decoration: const InputDecoration(labelText: 'Prompt'),
          onChanged: (value) => prompt = value),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Generate local text'))],
    ));
    if (confirmed != true || !mounted) return;
    try {
      final result = await _request(imported ? '/decoder-imports/$id/preview' : '/decoder-trials/$id/preview', {'confirmed': true, 'prompt': prompt, 'max_new_tokens': 12});
      if (!mounted) return;
      await showDialog<void>(context: context, builder: (context) => AlertDialog(
        title: const Text('Private decoder preview'), scrollable: true,
        content: SizedBox(width: 620, child: SelectableText(const JsonEncoder.withIndent('  ').convert(result))),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ));
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _showImportedDecoder(Map<String, dynamic> record) async {
    await showDialog<void>(context: context, builder: (context) => AlertDialog(
      title: const Text('Imported private decoder'), scrollable: true,
      content: SizedBox(width: 620, child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Text('File integrity is verified. Dataset documents are excluded, so imported evaluation claims have not been independently rechecked. CPU preview only; training and release are unavailable.'),
        SelectableText(const JsonEncoder.withIndent('  ').convert(record)),
      ])),
      actions: [TextButton(onPressed: () { Navigator.pop(context); _previewDecoderTrial(record['id'] as String, imported: true); }, child: const Text('Preview imported decoder')),
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
    ));
  }

  Future<void> _importPrivateDecoder() async {
    try {
      final file = await openFile(acceptedTypeGroups: [const XTypeGroup(label: 'Private decoder ZIP', extensions: ['zip'])]);
      if (file == null || !mounted) return;
      if (await file.length() > 8 * 1024 * 1024) throw const FormatException('Private decoder archives must fit 8 MiB.');
      if (!mounted) return;
      final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
        title: const Text('Import private decoder archive'),
        content: Text('Verify ${file.name} and save a separate private copy for CPU preview. Dataset documents are not included, so evaluation scores cannot be rechecked. This creates no training run or release.'),
        actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Import for private preview'))],
      ));
      if (confirmed != true || !mounted) return;
      final record = await _request('/decoder-imports', {'confirmed': true, 'source_name': file.name, 'data': base64Encode(await file.readAsBytes())});
      if (mounted) await _showImportedDecoder(record);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _showImportedDecoders() async {
    try {
      final imports = (await _request('/decoder-imports'))['imports'] as List;
      if (!mounted) return;
      final id = await showDialog<String>(context: context, builder: (context) => SimpleDialog(
        title: const Text('Imported private decoders'), children: [
          if (imports.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No private bundles imported yet.')),
          for (final record in imports) SimpleDialogOption(onPressed: () => Navigator.pop(context, record['id'] as String),
            child: Text('${record['source_name']} · ${(record['id'] as String).substring(0, 8)}')),
        ],
      ));
      if (id == null || !mounted) return;
      final record = await _request('/decoder-imports/$id');
      if (mounted) await _showImportedDecoder(record);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
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
          TextButton(onPressed: () { Navigator.pop(context); _prepareDecoderDataset(saveDraft: true); }, child: const Text('Save local preparation draft')),
          TextButton(onPressed: () { Navigator.pop(context); _prepareHtmlDataset(); }, child: const Text('Prepare local HTML text dataset')),
          TextButton(onPressed: () { Navigator.pop(context); _prepareJsonlDataset(); }, child: const Text('Prepare local JSONL text dataset')),
          TextButton(onPressed: () { Navigator.pop(context); _savedHtmlPreparations(); }, child: const Text('View saved HTML preparations')),
          TextButton(onPressed: () { Navigator.pop(context); _savedJsonlPreparations(); }, child: const Text('View saved JSONL preparations')),
          TextButton(onPressed: () { Navigator.pop(context); _showSavedPreparations(); }, child: const Text('View saved preparation drafts')),
          TextButton(onPressed: () { Navigator.pop(context); _showDatasetProviders(); }, child: const Text('Optional dataset providers')),
          if (Platform.isMacOS) TextButton(onPressed: () { Navigator.pop(context); _uploadStreamedSource(); }, child: const Text('Store a large local source in chunks')),
          if (Platform.isMacOS) TextButton(onPressed: () { Navigator.pop(context); _savedStreamedSources(); }, child: const Text('View saved streamed sources')),
          TextButton(onPressed: () {
            Navigator.pop(context);
            _showSavedDecoderDatasets();
          }, child: const Text('View prepared decoder datasets')),

          TextButton(onPressed: () { Navigator.pop(context); _importPrivateDecoder(); }, child: const Text('Import private decoder bundle')),
          TextButton(onPressed: () { Navigator.pop(context); _showImportedDecoders(); }, child: const Text('View imported private decoders')),
          const Text('Optional CPU initialization check uses fresh weights without downloads.'),
          TextButton(onPressed: () {
            Navigator.pop(context);
            _checkDecoderInitialization();
          }, child: const Text('Check decoder initialization')),
          if (Platform.isMacOS) ...[
            const Text('Optional Apple silicon diagnostic trains a tiny decoder on generated tokens.'),
            TextButton(onPressed: () {
              Navigator.pop(context);
              _checkDecoderTraining();
            }, child: const Text('Check from-scratch decoder training')),
            const Text('Saved trials keep their approval receipt, checkpoint and trained bundle locally. Reviewed local data uses a separate approval. General pretraining and public release remain unavailable.'),
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
      'factory_review': 'Review decoder approach',
      'factory_trial': 'Approved decoder trial',
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
        if (job?['decoder_proposal'] case final Map proposal when status == 'factory_review') ...[
          Text('Registered recipe: ${proposal['recipe_contract']['name']}'),
          Text('Recommended approach: ${proposal['approach']}'),
          SelectableText(proposal['reason'] as String),
          Text(job?['decoder_dataset'] == null
            ? 'Scope: fixed generated local text, fresh weights, 100 steps, seed 7 and Metal execution. This bounded trial does not release a model.'
            : 'Scope: reviewed dataset ${job!['decoder_dataset']['id']}, ${job['decoder_dataset']['unique_documents']} documents and saved train/validation/test splits. Fresh weights, 100 steps, seed 7 and Metal execution. This bounded trial does not release a model.'),
          CheckboxListTile(contentPadding: EdgeInsets.zero,
            title: const Text('Require idle time and AC power'),
            subtitle: const Text('Approval waits for AC power and 600 idle seconds without occupying the training worker. Readiness changes pause training; resume needs approval.'),
            value: _decoderRequireIdle,
            onChanged: _busy ? null : (value) => setState(() => _decoderRequireIdle = value ?? false)),
          if (!_decoderRequireIdle) const Text('Execution: start immediately after approval.'),
          OutlinedButton(onPressed: _busy ? null : _selectFactoryDataset, child: const Text('Choose reviewed local dataset')),
          if (proposal['executable'] == true)
            FilledButton(onPressed: _busy ? null : () => _submit('/jobs/$id/approve-decoder-trial', {
              'confirmed': true, 'proposal_revision': proposal['revision'], 'require_idle_ac': _decoderRequireIdle,
            }), child: const Text('Confirm from-scratch decoder trial'))
          else
            const Text('This approach is unavailable in the decoder trial workflow. Revise the goal to continue.'),
        ],
        if (status == 'factory_trial')
          OutlinedButton(onPressed: _busy ? null : () async {
            try {
              final record = await _request('/decoder-trials/${job!['decoder_trial_id']}');
              if (mounted) await _showDecoderTrial(record);
            } catch (error) {
              if (mounted) setState(() => _error = error.toString());
            }
          }, child: const Text('View linked decoder trial')),
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
  const _DecoderTrialGoalDialog({this.planningOnly = false});
  final bool planningOnly;

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
    title: Text(widget.planningOnly ? 'Plan a streamed approach' : 'Plan a local decoder trial'),
    content: SizedBox(width: 520, child: TextField(controller: _input, autofocus: true, maxLength: 3000, maxLines: 4,
      decoration: InputDecoration(labelText: 'Trial goal', helperText: widget.planningOnly ? 'Summary-only local planning. Streamed training is unavailable.' : 'Local Qwen recommends an approach. Only a tiny generated-text trial can run.'))),
    actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
      TextButton(onPressed: () => Navigator.pop(context, _input.text), child: const Text('Ask local Qwen'))],
  );
}
